#!/usr/bin/env python3
"""(C) backfill_access_valid_until.py — Nacharbeit nach dem Deploy der Auto-Reaktivierung (2026-09-11).

Traegt dashboard_users.access_valid_until fuer alle User nach, bei denen es noch leer ist:
letzter Ablefy-GRANT fuer UNSER Produkt (517561/517562) aus webhook_logs.
Reine Datenerfassung — loest keine Aktion aus (kein Kick, keine Mail, keine Reaktivierung).

Aufruf: cd /home/botuser/dashboard && python3 backfill_access_valid_until.py
"""
import os
import sys

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

# Wie in der systemd-Unit (dort per Environment=, NICHT in der .env)
os.environ.setdefault("BOT_CORE_PATH", os.path.abspath(os.path.join("..", "copy-trading-bot")))
os.environ.setdefault("DB_PATH", os.path.abspath(os.path.join("..", "copy-trading-bot", "copy_trading.db")))

sys.path.insert(0, os.getcwd())
from db import get_db  # noqa: E402

BACKFILL_SQL = """
UPDATE dashboard_users SET access_valid_until = (
    SELECT json_extract(w.payload, '$.access.access_valid_until') FROM webhook_logs w
    WHERE lower(json_extract(w.payload, '$.payer.email')) = lower(dashboard_users.email)
      AND json_extract(w.payload, '$.event') = 'payer.access.changed'
      AND json_extract(w.payload, '$.access.access_type') = 'GRANT'
      AND CAST(json_extract(w.payload, '$.product.product_id') AS TEXT) IN ('517561', '517562')
    ORDER BY w.id DESC LIMIT 1)
WHERE access_valid_until IS NULL
"""

db = get_db()  # fuehrt auch die Migration aus (Spalte anlegen falls noetig)
cur = db._conn.execute(BACKFILL_SQL)
db._conn.commit()
filled = db._conn.execute("SELECT COUNT(*) FROM dashboard_users WHERE access_valid_until IS NOT NULL").fetchone()[0]
total = db._conn.execute("SELECT COUNT(*) FROM dashboard_users").fetchone()[0]
print(f"Backfill: {cur.rowcount} Zeilen bearbeitet | mit Datum: {filled}/{total} "
      f"(Rest = nie ein GRANT fuer unser Produkt, z.B. LIFETIME-FREE)")
