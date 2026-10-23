#!/usr/bin/env python3
"""
(C) kick_gekuendigt_abgelaufen.py - Rueckwirkender Entzug fuer Kunden,
die gekuendigt haben UND deren bezahlter Zeitraum abgelaufen ist.

DRY_RUN=1 (Default) -> zeigt nur an, aendert NICHTS.
DRY_RUN=0           -> fuehrt aus.

Sicherungen:
  - Schutzliste (Max, Team, Lifetime, ungeklaerte Faelle)
  - Laufzeit-Re-Check: neuerer GRANT (active_subscription/paid) oder Zahlung
    nach der Kuendigung -> UEBERSPRINGEN
  - Enddatum muss < heute sein
  - Telegram: ban + sofort unban  = entfernt, aber NICHT dauergesperrt
    (Rueckkehrer holt die Auto-Reaktivierung automatisch zurueck)
  - Es wird NICHTS geloescht. Nur Status-Updates + Invite-Revoke.
"""
import json, os, sqlite3, sys, time, urllib.parse, urllib.request
from datetime import datetime, timezone

DRY = os.environ.get("DRY_RUN", "1") != "0"
DB = "copy_trading.db"
TOK = os.environ.get("TELEGRAM_BOT_TOKEN", "")
MAIN, SCALP = "-1003888563475", "-1004292274970"
UNSERE = {517561, 517562}
HEUTE = datetime.now(timezone.utc).date()

SCHUTZ = {
    "max.woelfle5@gmail.com", "inaherrmann3@gmx.net", "rico.andres@web.de",
    "dr.sabai@pm.me", "felix.roth87@gmail.com", "nblock70@gmail.com",
    "francesco@firstclass-trading.com", "elena.ceylan@mail.de",
    "christoph.kln@gmx.de", "sandro@hovr-agency.com", "silviokind95@gmx.de",
}

def tg(method, **p):
    if not TOK:
        return {"ok": False, "error": "kein Token"}
    url = f"https://api.telegram.org/bot{TOK}/{method}?" + urllib.parse.urlencode(p)
    try:
        return json.load(urllib.request.urlopen(url, timeout=20))
    except Exception as e:
        return {"ok": False, "error": str(e)}

def norm(e):
    return (e or "").strip().lower().replace("@googlemail.com", "@gmail.com")

def pid(p):
    pr = p.get("product") or {}
    if not isinstance(pr, dict): return None
    v = pr.get("id") or pr.get("product_id")
    try: return int(v)
    except (TypeError, ValueError): return None

def dt(s):
    if not s: return None
    try: return datetime.fromisoformat(str(s).replace("Z", "+00:00")).date()
    except Exception: return None

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

cancel, regrant, zahlung = {}, {}, {}
for row in conn.execute("SELECT payload, created_at FROM webhook_logs ORDER BY id"):
    try: p = json.loads(row["payload"])
    except Exception: continue
    if pid(p) not in UNSERE: continue
    pa = p.get("payer") or {}
    m = norm(pa.get("email") if isinstance(pa, dict) else "")
    if not m: continue
    ev, st = p.get("event") or "", p.get("payment_state") or ""
    acc = p.get("access") or {}
    at, until, ts = acc.get("access_type"), dt(acc.get("access_valid_until")), row["created_at"]
    if ev == "payer.access.changed" and st == "subscription_canceled":
        if m not in cancel or ts > cancel[m]["ts"]:
            cancel[m] = {"ts": ts, "bis": until}
    elif ev == "order.subscription.canceled":
        cancel.setdefault(m, {"ts": ts, "bis": None})
    if ev == "payer.access.changed" and at == "GRANT" and st in ("active_subscription", "paid"):
        if m not in regrant or ts > regrant[m]["ts"]:
            regrant[m] = {"ts": ts}
    if ev in ("payment.successful", "order.one_time.paid", "order.installment.paid"):
        nr = dt(p.get("payments_schedule_next_rate_date"))
        if m not in zahlung or ts > zahlung[m]["ts"]:
            zahlung[m] = {"ts": ts, "next": nr}

users = {}
for r in conn.execute("""SELECT du.id, du.email, du.customer_id, du.payment_status,
       du.telegram_chat_id, du.ablefy_order_id, du.paid_amount, du.telegram_invite_link,
       c.is_active, LENGTH(COALESCE(c.api_key,'')) keylen
       FROM dashboard_users du JOIN customers c ON c.id = du.customer_id"""):
    users[norm(r["email"])] = dict(r)

ziele, skip = [], []
for m, c in cancel.items():
    u = users.get(m)
    if not u: continue
    if m in SCHUTZ or u["ablefy_order_id"] == "LIFETIME-FREE" or str(u["paid_amount"]) == "0":
        skip.append((m, "Schutzliste/Lifetime")); continue
    if not u["is_active"] or u["payment_status"] in ("cancelled","refunded","chargebacked","suspended"):
        continue
    bis = c["bis"]
    if not bis:
        z = zahlung.get(m)
        bis = z["next"] if z and z["next"] else None
    rg, z = regrant.get(m), zahlung.get(m)
    if rg and rg["ts"] > c["ts"]:
        skip.append((m, f"RUECKKAUF (GRANT {rg['ts'][:10]})")); continue
    if z and z["ts"] > c["ts"]:
        skip.append((m, f"Zahlung nach Kuendigung ({z['ts'][:10]})")); continue
    if not bis:
        skip.append((m, "Enddatum unbekannt")); continue
    if bis > HEUTE:
        skip.append((m, f"laeuft bis {bis}")); continue
    if u["keylen"] > 0:
        skip.append((m, "HAT API-KEYS -> manuell pruefen")); continue
    u["bis"] = bis
    ziele.append(u)

ziele.sort(key=lambda r: r["bis"])
print(f"{'DRY-RUN (nichts wird geaendert)' if DRY else 'SCHARF'} | Stichtag {HEUTE}")
print(f"Ziele: {len(ziele)} | Uebersprungen: {len(skip)}\n")

stat = {"db": 0, "invite": 0, "tg_raus": 0, "tg_keine_id": 0, "tg_fehler": 0}
for u in ziele:
    tgid = (u["telegram_chat_id"] or "").strip()
    aktion = []
    if tgid:
        if DRY:
            aktion.append("TG: ban+unban (geplant)")
        else:
            okc = 0
            for chat in (MAIN, SCALP):
                r1 = tg("banChatMember", chat_id=chat, user_id=tgid)
                time.sleep(0.4)
                r2 = tg("unbanChatMember", chat_id=chat, user_id=tgid, only_if_banned="true")
                time.sleep(0.4)
                st = tg("getChatMember", chat_id=chat, user_id=tgid)
                s = st.get("result", {}).get("status") if st.get("ok") else "?"
                if s == "kicked":  # Nachfassen, bekannter Telegram-Fallstrick
                    time.sleep(3)
                    tg("unbanChatMember", chat_id=chat, user_id=tgid, only_if_banned="true")
                    st = tg("getChatMember", chat_id=chat, user_id=tgid)
                    s = st.get("result", {}).get("status") if st.get("ok") else "?"
                okc += 1 if (r1.get("ok") and s in ("left", "kicked")) else 0
                aktion.append(f"{'Main' if chat==MAIN else 'Scalp'}={s}")
            stat["tg_raus"] += 1 if okc == 2 else 0
            stat["tg_fehler"] += 0 if okc == 2 else 1
    else:
        stat["tg_keine_id"] += 1
        aktion.append("TG: KEINE ID -> bleibt in Gruppe")

    link = u["telegram_invite_link"]
    if link and not DRY:
        tg("revokeChatInviteLink", chat_id=MAIN, invite_link=link)
        stat["invite"] += 1
        time.sleep(0.3)
    elif link:
        aktion.append("Invite: revoke (geplant)")

    if not DRY:
        conn.execute("UPDATE dashboard_users SET payment_status='cancelled' WHERE id=?", (u["id"],))
        conn.execute("UPDATE customers SET is_active=0, deactivated_at=CURRENT_TIMESTAMP WHERE id=?",
                     (u["customer_id"],))
        conn.commit()
        stat["db"] += 1
    print(f"  id {u['id']:>4} bis {u['bis']} {u['email']:<36} {' | '.join(aktion)}")

print(f"\nDB-Updates: {stat['db']} | Invites widerrufen: {stat['invite']}")
print(f"Telegram entfernt: {stat['tg_raus']} | ohne ID: {stat['tg_keine_id']} | Fehler: {stat['tg_fehler']}")
print("\nUEBERSPRUNGEN:")
for m, g in sorted(skip, key=lambda x: x[1]):
    print(f"  {g:<38} {m}")
conn.close()
