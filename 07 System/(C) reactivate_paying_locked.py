#!/usr/bin/env python3
"""(C) reactivate_paying_locked.py — Gesperrten Kunden, der nachweislich weiterzahlt, zurueckholen (2026-09-11).

Fuer Altfaelle VOR dem Deploy der Auto-Reaktivierung (z. B. icebox23: SEPA geplatzt 21.08. -> gesperrt,
danach am 26.08. + 02.09. wieder gezahlt, blieb aber draussen).

Spielt die LETZTE echte payment.successful fuer UNSER Produkt (517561/517562) durch den normalen
Webhook-Payment-Pfad -> exakt das, was ab jetzt automatisch passiert:
Entbannung Main + Scalp, frischer Einmal-Link, Mail 'Dein Zugang ist wieder aktiv', DM an Max.

Sicherheitsnetze — bricht ab, wenn:
  (a) der Kunde nicht existiert, (b) er schon aktiv ist, (c) er auf der Blocklist steht,
  (d) keine Zahlung fuer unser Produkt vorliegt, (e) die letzte Zahlung VOR der Sperre liegt.

Aufruf: cd /home/botuser/dashboard && python3 reactivate_paying_locked.py <email>
"""
import asyncio
import json
import os
import sys
import time

# Wie der Dienst: im venv laufen. Selbst-Neustart statt venv-Pfad im Bash-Befehl.
_VENV = os.path.abspath(os.path.join("..", "copy-trading-bot", "venv"))
if os.path.isdir(_VENV) and os.path.abspath(sys.prefix) != _VENV:
    _py = os.path.join(_VENV, "bin", "python")
    os.execv(_py, [_py] + sys.argv)

ENV = os.path.join("..", "copy-trading-bot", ".env")
with open(ENV) as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
os.environ.setdefault("BOT_CORE_PATH", os.path.abspath(os.path.join("..", "copy-trading-bot")))
os.environ.setdefault("DB_PATH", os.path.abspath(os.path.join("..", "copy-trading-bot", "copy_trading.db")))

sys.path.insert(0, os.getcwd())
from db import get_db, is_email_blocked  # noqa: E402
from routes import webhook_routes as wr  # noqa: E402

if len(sys.argv) != 2:
    sys.exit("Aufruf: python3 reactivate_paying_locked.py <email>")
email = sys.argv[1].lower().strip()
db = get_db()

u = db._conn.execute(
    "SELECT d.id, d.payment_status, c.is_active, c.deactivated_at FROM dashboard_users d "
    "JOIN customers c ON c.id=d.customer_id WHERE lower(d.email)=?", (email,)
).fetchone()
if not u:
    sys.exit("ABBRUCH: Kunde nicht gefunden")
if u["is_active"]:
    sys.exit("ABBRUCH: Kunde ist bereits aktiv — nichts zu tun")
if is_email_blocked(db, email):
    sys.exit("ABBRUCH: E-Mail steht auf der Blocklist")

row = db._conn.execute(
    "SELECT payload, created_at FROM webhook_logs WHERE lower(json_extract(payload,'$.payer.email'))=? "
    "AND json_extract(payload,'$.event')='payment.successful' "
    "AND CAST(json_extract(payload,'$.product.id') AS TEXT) IN ('517561','517562') ORDER BY id DESC LIMIT 1",
    (email,),
).fetchone()
if not row:
    sys.exit("ABBRUCH: keine Zahlung fuer unser Produkt gefunden")
lock = (u["deactivated_at"] or "")[:10]
if lock and row["created_at"][:10] < lock:
    sys.exit(f"ABBRUCH: letzte Zahlung {row['created_at'][:10]} liegt VOR der Sperre {lock} — zahlt nicht weiter")

payload = json.loads(row["payload"])
print(f"Kunde id {u['id']} | Status {u['payment_status']} | gesperrt {lock or '(leer)'} | "
      f"letzte Zahlung {row['created_at'][:16]} (Order {payload.get('order_id')})")
resp = asyncio.run(wr._handle_payment(payload))
print("Handler:", json.loads(resp.body))
r = db._conn.execute(
    "SELECT d.payment_status, c.is_active, d.telegram_chat_id, d.telegram_invite_link FROM dashboard_users d "
    "JOIN customers c ON c.id=d.customer_id WHERE lower(d.email)=?", (email,)
).fetchone()
print(f"Nachher: payment_status={r[0]} | is_active={r[1]} | tg_id={r[2] or '(leer)'} | link={r[3]}")
time.sleep(8)  # send_async laeuft im Threadpool — Mail sicher rausgehen lassen
print("Fertig.")
