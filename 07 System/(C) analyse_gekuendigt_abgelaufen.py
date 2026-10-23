#!/usr/bin/env python3
"""
(C) analyse_gekuendigt_abgelaufen.py  — v2, READ-ONLY. Aendert NICHTS.

Findet Kunden, die in Ablefy gekuendigt haben UND deren bezahlter Zeitraum
abgelaufen ist.

Echte Ablefy-Semantik (an Payloads verifiziert 2026-09-25):
  GRANT  + subscription_canceled -> Kuendigung, access_valid_until = bezahlt bis
  REVOKE + subscription_canceled -> Kuendigung mit Sofortentzug
  GRANT  + active_subscription   -> laufende Verlaengerung = RUECKKAUF-Signal
  REVOKE + payment_paused        -> Zahlungsausfall (NICHT Teil dieses Auftrags)
"""
import json, sqlite3
from datetime import datetime, timezone

DB = "copy_trading.db"
UNSERE = {517561, 517562}
HEUTE = datetime.now(timezone.utc).date()

# Harte Schutzliste: NIEMALS anfassen (Team, Max, ungeklaerte Sonderfaelle).
# Ina + Rico: LIFETIME-Marker wurde durch Rate am 03.08. ueberschrieben.
# Felix + Norbert: Max 11.09. -> "vorerst drin lassen".
SCHUTZ = {
    "max.woelfle5@gmail.com", "inaherrmann3@gmx.net", "rico.andres@web.de",
    "dr.sabai@pm.me", "felix.roth87@gmail.com", "nblock70@gmail.com",
    "francesco@firstclass-trading.com", "elena.ceylan@mail.de",
    "christoph.kln@gmx.de", "sandro@hovr-agency.com", "silviokind95@gmx.de",
}

conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
conn.row_factory = sqlite3.Row

def norm(e):
    e = (e or "").strip().lower()
    return e.replace("@googlemail.com", "@gmail.com")

def pid(p):
    pr = p.get("product") or {}
    if not isinstance(pr, dict): return None
    v = pr.get("id") or pr.get("product_id")
    try: return int(v)
    except (TypeError, ValueError): return None

def mail(p):
    pa = p.get("payer") or {}
    return norm(pa.get("email") if isinstance(pa, dict) else "")

def dt(s):
    if not s: return None
    try: return datetime.fromisoformat(str(s).replace("Z", "+00:00")).date()
    except Exception: return None

cancel, regrant, zahlung = {}, {}, {}

for row in conn.execute("SELECT payload, created_at FROM webhook_logs ORDER BY id"):
    try: p = json.loads(row["payload"])
    except Exception: continue
    if pid(p) not in UNSERE: continue
    m = mail(p)
    if not m: continue
    ev, st = p.get("event") or "", p.get("payment_state") or ""
    acc = p.get("access") or {}
    at, until = acc.get("access_type"), dt(acc.get("access_valid_until"))
    ts = row["created_at"]

    if ev == "payer.access.changed" and st == "subscription_canceled":
        prev = cancel.get(m)
        if not prev or ts > prev["ts"]:
            cancel[m] = {"ts": ts, "bis": until, "sofort": at == "REVOKE",
                         "order": p.get("order_id")}
    elif ev == "order.subscription.canceled":
        cancel.setdefault(m, {"ts": ts, "bis": None, "sofort": False,
                              "order": p.get("order_id")})
    if ev == "payer.access.changed" and at == "GRANT" and st in ("active_subscription", "paid"):
        if m not in regrant or ts > regrant[m]["ts"]:
            regrant[m] = {"ts": ts, "bis": until}
    if ev in ("payment.successful", "order.one_time.paid", "order.installment.paid"):
        nr = dt(p.get("payments_schedule_next_rate_date"))
        if m not in zahlung or ts > zahlung[m]["ts"]:
            zahlung[m] = {"ts": ts, "next": nr}

users = {}
for r in conn.execute("""
    SELECT du.id, du.email, du.customer_id, du.payment_status, du.telegram_chat_id,
           du.telegram_username, du.product_tier, du.ablefy_order_id, du.paid_amount,
           du.telegram_invite_link, c.is_active, c.name,
           LENGTH(COALESCE(c.api_key,'')) AS keylen
    FROM dashboard_users du JOIN customers c ON c.id = du.customer_id"""):
    users[norm(r["email"])] = dict(r)

kick, schutz, laufend, raus, kein_acc = [], [], [], [], []

for m, c in cancel.items():
    u = users.get(m)
    if not u:
        kein_acc.append(m); continue
    rec = {"mail": m, "cancel_ts": c["ts"], "sofort": c["sofort"], **u}

    if m in SCHUTZ or u["ablefy_order_id"] == "LIFETIME-FREE" or str(u["paid_amount"]) == "0":
        schutz.append(rec); continue

    bis, quelle = c["bis"], "cancel-GRANT"
    if not bis:
        z = zahlung.get(m)
        if z and z["next"]: bis, quelle = z["next"], "next_rate_date"
    rec["bis"], rec["quelle"] = bis, quelle

    # Rueckkauf: GRANT(active/paid) ODER Zahlung NACH der Kuendigung
    rg, z = regrant.get(m), zahlung.get(m)
    if rg and rg["ts"] > c["ts"]:
        rec["grund"] = f"REKAUF (GRANT {rg['ts'][:10]}, bis {rg['bis']})"
        laufend.append(rec); continue
    if z and z["ts"] > c["ts"]:
        rec["grund"] = f"ZAHLUNG nach Kuendigung ({z['ts'][:10]})"
        laufend.append(rec); continue

    if not u["is_active"] or u["payment_status"] in ("cancelled", "refunded", "chargebacked", "suspended"):
        raus.append(rec); continue
    if not bis:
        rec["grund"] = "Enddatum UNBEKANNT -> nicht anfassen"
        laufend.append(rec); continue
    if bis > HEUTE:
        rec["grund"] = f"laeuft noch bis {bis}"
        laufend.append(rec); continue
    kick.append(rec)

kick.sort(key=lambda r: r["bis"])

print(f"Stichtag (UTC): {HEUTE}")
print(f"Kuendigungen unsere Produkte : {len(cancel)}")
print(f"  kein Account               : {len(kein_acc)}")
print(f"  Schutzliste/Lifetime       : {len(schutz)}")
print(f"  bereits deaktiviert        : {len(raus)}")
print(f"  laeuft noch / Rueckkauf    : {len(laufend)}")
print(f"  >>> KICK-KANDIDATEN        : {len(kick)}")
print()
print("=" * 104)
print("KICK-KANDIDATEN")
print("=" * 104)
print(f"{'id':>4} {'bis':<11} {'gek.am':<11} {'TG-ID':>12} {'Key':>4} {'Sof':>4} {'Quelle':<15} E-Mail")
for r in kick:
    print(f"{r['id']:>4} {str(r['bis']):<11} {r['cancel_ts'][:10]:<11} "
          f"{str(r['telegram_chat_id'] or '-'):>12} {r['keylen']:>4} "
          f"{('JA' if r['sofort'] else '-'):>4} {r['quelle']:<15} {r['mail']}")
mit_id = [r for r in kick if r["telegram_chat_id"]]
print(f"\n  mit Telegram-ID (echt kickbar): {len(mit_id)}")
print(f"  ohne ID (nur DB + Invite)     : {len(kick) - len(mit_id)}")
print(f"  mit API-Keys                  : {len([r for r in kick if r['keylen'] > 0])}")

print("\n" + "=" * 104)
print("NICHT ANFASSEN")
print("=" * 104)
for r in schutz:
    print(f"{r['id']:>4} SCHUTZ   {r['mail']}")
for r in sorted(laufend, key=lambda x: x["mail"]):
    print(f"{r['id']:>4} {r.get('grund','')[:48]:<50} {r['mail']}")
conn.close()
