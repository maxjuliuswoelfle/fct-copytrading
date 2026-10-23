#!/usr/bin/env python3
"""(C) check_nichtzahler.py — READ-ONLY: aktive Kunden ohne bezahlten Zeitraum pruefen (2026-09-11, v3).

Kickt NICHTS und schreibt NICHTS: DB schreibgeschuetzt (mode=ro), Telegram nur getChatMember.

Versionen:
  v1  Ablefy-access_valid_until           -> zu grob (bei Verlaengerungen veraltet, fehlt bei Einmalzahlung)
  v2  letzte Zahlung + 31 T / +365 T      -> falsch bei VORAUSZAHLUNG (Robin Ebner: 2 Raten am 29.07.,
                                             Manuela Orsag: Rate am 07.08. vorgezogen -> beide bis 28.09. bezahlt)
  v3  Ablefys eigenes Feld 'payments_schedule_next_rate_date' ("naechste Rate faellig am") aus jeder
      Zahlung = verbindlich bezahlt bis (in 1049/1060 Zahlungen befuellt, Einmalzahlung = +1 Jahr).

Deckung PRO ORDER unseres Produkts (517561/517562):
  - gekuendigt:  Ablefys Enddatum aus dem Kuendigungs-GRANT (sonst naechste Rate)
  - pausiert:    Ende am Pausentag (REVOKE) — eine SPAETERE Zahlung hebt die Pause auf
  - sonst:       naechste Rate faellig (Fallback ohne Feld: letzte Zahlung + 31 T bzw. + 365 T bei Einmalzahlung)
Kunde bezahlt, wenn irgendeine Order bis heute - 3 T Kulanz deckt oder SEPA in den letzten 10 T laeuft.
Mehrfach-Bestellungen (z. B. neue Order nach Kartenproblem) zaehlen zusammen (per E-Mail inkl. Alias + Order-ID).
Zusaetzlich fuer alle offenen Faelle: Suche nach Vor- + Nachname unter ANDERER E-Mail -> eigene Gruppe N.

Aufruf: cd /home/botuser/copy-trading-bot && python3 check_nichtzahler.py
"""
import json
import sqlite3
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

env = {}
with open(".env") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
TOKEN = env.get("TELEGRAM_BOT_TOKEN", "")
MAIN = env.get("SIGNAL_PAID_GROUP_ID", "")
SCALP = env.get("SIGNAL_SCALP_GROUP_ID", "")

con = sqlite3.connect("file:copy_trading.db?mode=ro", uri=True)   # schreibgeschuetzt
con.row_factory = sqlite3.Row
NOW = datetime.now(timezone.utc)
NOWS = NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
GRACE = timedelta(days=3)
PID = ("CAST(COALESCE(json_extract(payload,'$.product.id'), json_extract(payload,'$.product.product_id'), "
       "json_extract(payload,'$.product_id')) AS TEXT)")

NOTES = {
    "max.woelfle5@gmail.com": "INTERN: Max' eigener Account",
    "inaherrmann3@gmx.net": "TEAM/LIFETIME — Marker durch Rate am 03.08. ueberschrieben, NICHT kicken",
    "rico.andres@web.de": "TEAM/LIFETIME — Marker durch Rate am 03.08. ueberschrieben, NICHT kicken",
    "felix.roth87@gmail.com": "Laut CLAUDE.md Jahresabo bis 28.07.2027 — Ablefy bucht seit Kuendigung nicht mehr ab",
    "nblock70@googlemail.com": "Laut CLAUDE.md Jahresabo bis 29.07.2027 — Ablefy bucht seit Kuendigung nicht mehr ab",
}


def ts(s):
    if not s:
        return None
    try:
        t = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def tg_status(chat, uid):
    if not (TOKEN and chat and uid):
        return "?"
    try:
        q = urllib.parse.urlencode({"chat_id": chat, "user_id": uid})
        with urllib.request.urlopen(f"https://api.telegram.org/bot{TOKEN}/getChatMember?{q}", timeout=10) as r:
            d = json.loads(r.read())
        time.sleep(0.05)
        return d["result"]["status"] if d.get("ok") else "FEHLER"
    except Exception:
        return "FEHLER"


def aliases(email):
    e = (email or "").lower().strip()
    out = {e}
    if "@" in e:
        loc, dom = e.rsplit("@", 1)
        alt = {"gmail.com": "googlemail.com", "googlemail.com": "gmail.com"}.get(dom)
        if alt:
            out.add(f"{loc}@{alt}")
    return sorted(out)


def fmt(d):
    return d.strftime("%Y-%m-%d") if d else "-"


def analyse(rows):
    """Wertet Events aus -> (orders, best_end, best_oid, recent_pending, payer_name)."""
    orders, recent_pending, name = {}, False, ("", "")
    for r in rows:
        p = json.loads(r["payload"])
        t = ts(r["created_at"])
        oid = str(p.get("order_id", ""))
        o = orders.setdefault(oid, {"pays": [], "next_rate": None, "yearly": False, "cancel_end": None,
                                    "canceled_at": None, "revoke_at": None, "grant_end": None,
                                    "last_ev": None, "plan": "", "method": set()})
        ev, state = p.get("event", ""), p.get("payment_state", "")
        payer = p.get("payer") if isinstance(p.get("payer"), dict) else {}
        if payer.get("last_name"):
            name = (str(payer.get("first_name") or "").strip(), str(payer.get("last_name") or "").strip())
        acc = p.get("access") if isinstance(p.get("access"), dict) else {}
        plan = (p.get("pricing_plan") or {}).get("name", "") if isinstance(p.get("pricing_plan"), dict) else ""
        if plan:
            o["plan"] = plan
        if p.get("payment_method"):
            o["method"].add(p["payment_method"])
        try:
            amount = float(p.get("amount") or 0)
        except (TypeError, ValueError):
            amount = 0.0
        if ev == "payment.successful":
            o["pays"].append(t)
            if "einmalzahlung" in plan.lower() or amount >= 500:
                o["yearly"] = True
            nr = ts(p.get("payments_schedule_next_rate_date"))
            if nr and (o["next_rate"] is None or nr > o["next_rate"]):
                o["next_rate"] = nr
            if o["revoke_at"] and t and t > o["revoke_at"]:
                o["revoke_at"] = None                      # spaetere Zahlung hebt Pause auf
        if ev == "payment.pending" and state in ("payment_pending", "active_subscription") and t and NOW - t <= timedelta(days=10):
            recent_pending = True
        if ev == "order.subscription.canceled":
            o["canceled_at"] = t
        if ev == "payer.access.changed":
            if acc.get("access_type") == "REVOKE":
                o["revoke_at"] = t
            elif acc.get("access_type") == "GRANT":
                end = ts(acc.get("access_valid_until"))
                o["revoke_at"] = None
                if state == "subscription_canceled":
                    o["cancel_end"] = end
                elif end:
                    o["grant_end"] = max(o["grant_end"], end) if o["grant_end"] else end
        o["last_ev"] = (ev, state, t)

    best_end, best_oid = None, None
    for oid, o in orders.items():
        last_pay = max(o["pays"]) if o["pays"] else None
        if o["next_rate"]:
            paid_until = o["next_rate"]
        elif last_pay:
            paid_until = last_pay + timedelta(days=365 if o["yearly"] else 31)
        else:
            paid_until = None
        if o["canceled_at"]:
            end = o["cancel_end"] or paid_until
        elif o["revoke_at"]:
            end = o["revoke_at"]
        else:
            end = max([x for x in (paid_until, o["grant_end"]) if x], default=None)
        o["end"] = end
        if end and (best_end is None or end > best_end):
            best_end, best_oid = end, oid
    return orders, best_end, best_oid, recent_pending, name


cands = con.execute("""
    SELECT d.id, d.email, d.ablefy_order_id, d.telegram_chat_id AS tg
    FROM dashboard_users d JOIN customers c ON c.id = d.customer_id
    WHERE c.is_active = 1 AND COALESCE(d.ablefy_order_id,'') <> 'LIFETIME-FREE'
      AND d.access_valid_until IS NOT NULL AND d.access_valid_until < ?
    ORDER BY d.id""", (NOWS,)).fetchall()

open_list, cleared = [], []
for c in cands:
    em = aliases(c["email"])
    qs = ",".join("?" * len(em))
    rows = con.execute(
        f"SELECT created_at, payload FROM webhook_logs WHERE {PID} IN ('517561','517562') AND "
        f"(lower(json_extract(payload,'$.payer.email')) IN ({qs}) OR CAST(json_extract(payload,'$.order_id') AS TEXT) = ?) "
        f"ORDER BY id", (*em, str(c["ablefy_order_id"] or "-"))).fetchall()
    orders, best_end, best_oid, recent_pending, name = analyse(rows)

    note = NOTES.get((c["email"] or "").lower(), "")
    all_pays = sorted(p for o in orders.values() for p in o["pays"])
    base = {"id": c["id"], "email": c["email"], "note": note, "orders": len(orders),
            "n_pay": len(all_pays), "last_pay": fmt(all_pays[-1]) if all_pays else "-",
            "end": fmt(best_end), "overdue": (NOW - best_end).days if best_end else None}

    if recent_pending or (best_end and best_end >= NOW - GRACE):
        cleared.append({**base, "why": "SEPA laeuft" if recent_pending and not (best_end and best_end >= NOW - GRACE)
                        else f"bezahlt bis {fmt(best_end)}"})
        continue

    # Mehrfach-Bestellung unter ANDERER E-Mail? Suche nach exaktem Vor- + Nachnamen
    alt_hit = None
    if name[1]:
        alt = con.execute(
            f"SELECT created_at, payload FROM webhook_logs WHERE {PID} IN ('517561','517562') "
            f"AND lower(trim(json_extract(payload,'$.payer.first_name'))) = ? AND lower(trim(json_extract(payload,'$.payer.last_name'))) = ? "
            f"AND lower(json_extract(payload,'$.payer.email')) NOT IN ({qs}) ORDER BY id",
            (name[0].lower(), name[1].lower(), *em)).fetchall()
        if alt:
            _, a_end, _, a_pend, _ = analyse(alt)
            a_mail = json.loads(alt[-1]["payload"]).get("payer", {}).get("email", "?")
            if a_pend or (a_end and a_end >= NOW - GRACE):
                alt_hit = f"zahlt evtl. unter {a_mail} (bezahlt bis {fmt(a_end)})"

    o = orders.get(best_oid) if best_oid else None
    if alt_hit:
        cat, why = "N", alt_hit
    elif o and o["revoke_at"]:
        cat, why = "A", f"Ablefy pausiert/entzogen am {fmt(o['revoke_at'])}"
    elif o and o["canceled_at"]:
        cat, why = "B", f"gekuendigt am {fmt(o['canceled_at'])}, Zugang lt. Ablefy bis {fmt(o['end'])}"
    elif not all_pays:
        cat, why = "E", "nie erfolgreich bezahlt"
    else:
        le = o["last_ev"] if o else None
        cat = "C" if le and (le[0] in ("payment.error", "order.subscription.paused") or le[1] in ("payment_paused", "payment_not_completed")) else "F"
        why = (f"letztes Event {le[0]} / {le[1]} am {fmt(le[2])}" if le else "keine Events") + \
              (f" | naechste Rate lt. Ablefy {fmt(o['next_rate'])}" if o and o["next_rate"] else "")
    open_list.append({**base, "cat": cat, "why": why, "name": " ".join(name).strip() or "-",
                      "plan": (o["plan"] if o else "")[:40] or "-",
                      "method": ",".join(sorted(o["method"])) if o else "-",
                      "tg_main": tg_status(MAIN, c["tg"]) if c["tg"] else "keine ID",
                      "tg_scalp": tg_status(SCALP, c["tg"]) if c["tg"] else "keine ID"})

LABEL = {"N": "ZAHLT EVTL. UNTER ANDERER E-MAIL (Namens-Treffer, pruefen)",
         "A": "ABLEFY HAT PAUSIERT / ZUGANG ENTZOGEN (Zahlung fehlgeschlagen)",
         "B": "GEKUENDIGT + ABGELAUFEN, NIE GEKICKT",
         "C": "ZAHLUNG FEHLGESCHLAGEN, KEIN ENTZUG",
         "E": "NIE ERFOLGREICH BEZAHLT",
         "F": "BEZAHLTER ZEITRAUM ABGELAUFEN, KEIN EVENT (unklar)"}
print(f"Stand {NOWS} | Kandidaten (Ablefy-Datum abgelaufen): {len(cands)} | entlastet: {len(cleared)} | OFFEN: {len(open_list)}\n")
for cat in "NABCEF":
    grp = [r for r in open_list if r["cat"] == cat]
    if not grp:
        continue
    print(f"=== {cat} {LABEL[cat]} ({len(grp)}) ===")
    for r in sorted(grp, key=lambda x: -(x["overdue"] or 0)):
        note = f"  <<< {r['note']}" if r["note"] else ""
        print(f"  id {r['id']:>3} | {r['email']:<34} | {r['name']:<24} | {r['plan']:<40} | {r['method']:<9} | "
              f"{r['n_pay']} Zahl. auf {r['orders']} Order(s), letzte {r['last_pay']} | bezahlt bis {r['end']} (+{r['overdue']} T) | "
              f"TG {r['tg_main']}/{r['tg_scalp']} | {r['why']}{note}")
    print()
print("=== ENTLASTET GEGENUEBER v2 (Stichprobe) ===")
for mail in ("robinebner@web.de", "manu9180@aol.com", "s-duerr@wahle.de"):
    hit = [r for r in cleared if (r["email"] or "").lower() == mail]
    print(f"  {mail:<34} -> {hit[0]['why'] if hit else 'NICHT entlastet'}")
print()
print("ZUSAMMENFASSUNG OFFEN: " + " | ".join(f"{c}={sum(1 for r in open_list if r['cat'] == c)}" for c in "NABCEF")
      + f" | davon Sonderfall-Markierung: {sum(1 for r in open_list if r['note'])}")
drin = [r for r in open_list if "member" in (r["tg_main"], r["tg_scalp"]) or "administrator" in (r["tg_main"], r["tg_scalp"])]
print(f"Nachweislich noch in Main/Scalp: {len(drin)} ({', '.join(str(r['id']) for r in drin) or '-'}) | "
      f"ohne Telegram-ID: {sum(1 for r in open_list if r['tg_main'] == 'keine ID')}")
