#!/usr/bin/env python3
"""(C) test_reactivation.py — Trockentest der Auto-Reaktivierung auf einer DB-KOPIE (2026-09-11).

- Kopiert die Live-DB nach test_reactivation.db und zwingt DB_PATH darauf.
- Telegram-Token wird geleert, Mail-Versand stumm geschaltet, Telegram-/Mail-Funktionen gemockt.
  -> Es geht NICHTS raus, die Live-DB bleibt unberuehrt.
- Spielt ECHTE gespeicherte Ablefy-Payloads durch den echten Webhook-Dispatcher.
- Hauptfall = Lihua Zoustahr: gekuendigt 22.08., Neukauf 28.08. (Order 16930311), bezahlt 02.09.,
  am 06.09. vom Timer gekickt. In der KOPIE wird der Kick-Zustand nachgestellt, dann ihre Zahlung
  vom 02.09. erneut eingespielt -> sie muss automatisch zurueckkommen.
- Loescht die Kopie am Ende (enthaelt Kundendaten).

Aufruf: cd /home/botuser/dashboard && python3 test_reactivation.py
"""
import asyncio
import copy
import json
import os
import sqlite3
import sys

# Wie der Dienst: im venv laufen (fastapi/aiohttp). Selbst-Neustart statt venv-Pfad im Bash-Befehl.
_VENV = os.path.abspath(os.path.join("..", "copy-trading-bot", "venv"))
if os.path.isdir(_VENV) and os.path.abspath(sys.prefix) != _VENV:
    _py = os.path.join(_VENV, "bin", "python")
    os.execv(_py, [_py] + sys.argv)

LIVE_DB = os.path.join("..", "copy-trading-bot", "copy_trading.db")
TEST_DB = os.path.abspath("test_reactivation.db")
ENV = os.path.join("..", "copy-trading-bot", ".env")

with open(ENV) as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
os.environ["DB_PATH"] = TEST_DB
# Wie in der systemd-Unit (dort per Environment=, NICHT in der .env) — sonst findet db.py 'database' nicht
os.environ["BOT_CORE_PATH"] = os.path.abspath(os.path.join("..", "copy-trading-bot"))
os.environ["TELEGRAM_BOT_TOKEN"] = ""          # Sicherheitsnetz: echte Telegram-Calls unmoeglich

# Sicherheitsnetz Mails: SMTP-Env NICHT leeren (email_service castet den Port beim Import per int()),
# stattdessen den eigentlichen Versand stumm schalten, bevor irgendetwas anderes importiert wird.
sys.path.insert(0, os.getcwd())
import email_service as _es  # noqa: E402
_es._send_mail = lambda *a, **k: True

for suffix in ("", "-wal", "-shm"):
    if os.path.exists(TEST_DB + suffix):
        os.remove(TEST_DB + suffix)
src = sqlite3.connect(LIVE_DB)
dst = sqlite3.connect(TEST_DB)
src.backup(dst)
dst.close()
src.close()

import db as dbmod  # noqa: E402
assert os.path.abspath(dbmod.DB_PATH) == TEST_DB, f"FALSCHE DB: {dbmod.DB_PATH}"
from routes import webhook_routes as wr  # noqa: E402

CALLS = []


async def fake_unban(tg):
    CALLS.append(("unban", str(tg)))
    return {"main": True, "scalp": True}


async def fake_invite(name=""):
    CALLS.append(("invite", name))
    return "https://telegram.me/+TESTLINK"


async def fake_admin(text):
    CALLS.append(("admin", text[:90]))
    return True


async def fake_kick(tg):
    CALLS.append(("kick", str(tg)))
    return True


def fake_send_async(fn, *a, **k):
    CALLS.append(("mail", fn.__name__, a[0] if a else ""))


wr.unban_from_groups = fake_unban
wr.create_paid_invite = fake_invite
wr.notify_admin = fake_admin
wr.kick_from_paid_group = fake_kick
wr.send_async = fake_send_async


class Req:
    def __init__(self, p):
        self._b = json.dumps(p).encode()

    async def body(self):
        return self._b


def hit(p):
    CALLS.clear()
    resp = asyncio.run(wr.ablefy_webhook(Req(p)))
    return list(CALLS), json.loads(resp.body)


T = sqlite3.connect(TEST_DB)
T.row_factory = sqlite3.Row


def q(sql, *a):
    return T.execute(sql, a).fetchone()


def payload_of(email, event, day, order_id=None):
    sql = ("SELECT payload FROM webhook_logs WHERE lower(payload) LIKE ? AND json_extract(payload,'$.event')=? "
           "AND created_at LIKE ?")
    args = [f"%{email}%", event, day + "%"]
    if order_id:
        sql += " AND CAST(json_extract(payload,'$.order_id') AS TEXT)=?"
        args.append(str(order_id))
    r = q(sql + " ORDER BY id LIMIT 1", *args)
    assert r, f"Payload fehlt: {email} {event} {day} {order_id}"
    return json.loads(r["payload"])


def active(duid):
    return q("SELECT c.is_active FROM customers c JOIN dashboard_users d ON d.customer_id=c.id WHERE d.id=?", duid)["is_active"]


def col(duid, name):
    return q(f"SELECT {name} FROM dashboard_users WHERE id=?", duid)[0]


def kinds(calls, kind):
    return [c for c in calls if c[0] == kind]


RESULTS = []


def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond)))
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f"   [{detail}]" if detail and not cond else ""))


LIHUA, LID, LTG = "lihua.zoustahr@yahoo.com", 358, "7487353081"
TIMO, TID = "heusel-timo@t-online.de", 442
print(f"Test-DB: {TEST_DB}")

# Ausgangslage vom 06.09. nachstellen — NUR in der Kopie: Kick-Timer hat Lihua rausgeworfen
T.execute("UPDATE dashboard_users SET payment_status='cancelled' WHERE id=?", (LID,))
T.execute("UPDATE customers SET is_active=0 WHERE id=(SELECT customer_id FROM dashboard_users WHERE id=?)", (LID,))
T.commit()
check("Ausgangslage: Lihua draussen (wie nach dem Kick am 06.09.)", active(LID) == 0)

# D) Ihr Kuendigungs-GRANT (22.08., alte Order) darf sie NICHT zurueckholen
calls, body = hit(payload_of(LIHUA, "payer.access.changed", "2026-08-22"))
check("D Kuendigungs-GRANT: keine Aktion", calls == [] and body.get("status") == "ok", f"{calls} {body}")
check("D Kuendigungs-GRANT: Lihua bleibt draussen", active(LID) == 0)

# X) Fremdes Produkt: Timos Trading-Accelerator-Zahlung (517573) -> komplett ignorieren
calls, body = hit(payload_of(TIMO, "payment.successful", "2026-09-03"))
check("X Accelerator-Zahlung (fremdes Produkt): keine Aktion", calls == [], calls)
check("X Accelerator-Zahlung: Timo bleibt draussen", active(TID) == 0)
calls, body = hit(payload_of(TIMO, "payer.access.changed", "2026-09-03"))
check("X Accelerator-GRANT: kein Datum uebernommen", col(TID, "access_valid_until") != "2026-10-03T00:00:00Z",
      col(TID, "access_valid_until"))

# A) Ihre echte Zahlung vom 02.09. (Order 16930311) -> automatisch zurueck
pay = payload_of(LIHUA, "payment.successful", "2026-09-02", 16930311)
calls, body = hit(pay)
check("A Rueckkauf: Webhook ohne Fehler", body.get("status") == "ok", body)
check("A Rueckkauf: Kundin wieder aktiv", active(LID) == 1)
check("A Rueckkauf: Entbannung mit richtiger TG-ID", ("unban", LTG) in calls, calls)
check("A Rueckkauf: genau 1 neuer Link", len(kinds(calls, "invite")) == 1, calls)
check("A Rueckkauf: Link in DB", col(LID, "telegram_invite_link") == "https://telegram.me/+TESTLINK")
check("A Rueckkauf: Reaktivierungs-Mail an Lihua", ("mail", "send_access_restored_email", LIHUA) in calls, calls)
check("A Rueckkauf: KEINE zusaetzliche 'Zahlung bestaetigt'-Mail",
      not [c for c in kinds(calls, "mail") if c[1] != "send_access_restored_email"], calls)
check("A Rueckkauf: Admin-Info an Max", len(kinds(calls, "admin")) == 1, calls)
check("A Rueckkauf: payment_status = paid", col(LID, "payment_status") == "paid")
check("A Rueckkauf: kein Kick", not kinds(calls, "kick"), calls)

# B) Dasselbe Event nochmal (Ablefy feuert mehrfach) -> nichts doppelt
calls, body = hit(pay)
check("B Duplikat: keine zweite Aktion", calls == [], calls)

# C) GRANT desselben Kaufs (28.08., bis 28.09.) -> keine Aktion, nur Datum mitschreiben
calls, body = hit(payload_of(LIHUA, "payer.access.changed", "2026-08-28", 16930311))
check("C GRANT: keine Aktion", calls == [], calls)
check("C GRANT: access_valid_until = 2026-09-28", col(LID, "access_valid_until") == "2026-09-28T00:00:00Z",
      col(LID, "access_valid_until"))

# E) Normale Verlaengerung eines aktiven Kunden -> KEINE Reaktivierung
r = q("SELECT w.payload FROM webhook_logs w JOIN dashboard_users d ON lower(d.email)=lower(json_extract(w.payload,'$.payer.email')) "
      "JOIN customers c ON c.id=d.customer_id WHERE c.is_active=1 AND d.id NOT IN (358, 442) "
      "AND CAST(json_extract(w.payload,'$.product.id') AS TEXT)='517561' "
      "AND json_extract(w.payload,'$.event')='payment.successful' ORDER BY w.id DESC LIMIT 1")
calls, body = hit(json.loads(r["payload"]))
check("E Aktiver Kunde verlaengert: keine Reaktivierung",
      not kinds(calls, "unban") and not kinds(calls, "invite") and not kinds(calls, "admin"), calls)

# F) Blocklist (rmkt1) zahlt unser Produkt -> bleibt draussen
blk = copy.deepcopy(pay)
blk["payer"]["email"] = "rmkt1@t-online.de"
calls, body = hit(blk)
check("F Blocklist: keine Aktion", calls == [], calls)
check("F Blocklist: rmkt1 (193) bleibt draussen", active(193) == 0)

# G) REVOKE mit active_subscription (defensiv) -> darf nie als Zahlung zaehlen
rv = copy.deepcopy(payload_of(LIHUA, "payer.access.changed", "2026-08-28", 16930311))
rv["access"]["access_type"] = "REVOKE"
calls, body = hit(rv)
check("G REVOKE: keine Aktion", calls == [], calls)

# H) Alias gmail <-> googlemail + Rueckkehr nach Chargeback (sabaton84, id 211)
before_211 = active(211)
al = copy.deepcopy(pay)
al["payer"]["email"] = "sabaton84@gmail.com"      # in der DB steht @googlemail.com
al["order_id"] = 99999901
calls, body = hit(al)
check("H Vorher: sabaton84 inaktiv", before_211 == 0)
check("H Alias gefunden + reaktiviert", active(211) == 1, calls)
check("H Reaktivierungs-Mail", any(c[0] == "mail" and c[1] == "send_access_restored_email" for c in calls), calls)

T.close()
for suffix in ("", "-wal", "-shm"):
    if os.path.exists(TEST_DB + suffix):
        os.remove(TEST_DB + suffix)

failed = [n for n, ok in RESULTS if not ok]
print(f"\nERGEBNIS: {len(RESULTS) - len(failed)}/{len(RESULTS)} PASS" + (f" | FAIL: {failed}" if failed else ""))
print("Test-DB geloescht.")
sys.exit(1 if failed else 0)
