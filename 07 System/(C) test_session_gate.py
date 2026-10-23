#!/usr/bin/env python3
"""
(C) test_session_gate.py - Trockentest des Session-Gates auf einer DB-KOPIE.
Die Produktions-DB wird NICHT veraendert (Kopie im aktuellen Ordner).
"""
import sqlite3, shutil, os, secrets
from datetime import datetime, timedelta

SRC = "copy_trading.db"
COPY = "gate_test_copy.db"
for suf in ("", "-wal", "-shm"):
    if os.path.exists(SRC + suf):
        shutil.copy2(SRC + suf, COPY + suf)

conn = sqlite3.connect(COPY)
conn.row_factory = sqlite3.Row
exp = datetime.utcnow() + timedelta(days=7)

SQL_ALT = """SELECT du.*, c.name as customer_name FROM dashboard_users du
  JOIN customers c ON c.id = du.customer_id
  WHERE du.session_token = ? AND du.session_expires_at > CURRENT_TIMESTAMP
    AND du.is_activated = 1"""
SQL_NEU = SQL_ALT + """
    AND COALESCE(du.payment_status,'') NOT IN ('cancelled','refunded','chargebacked','suspended')
    AND NOT (c.is_active = 0 AND c.deactivated_at IS NOT NULL)"""

def setze(duid, ps, is_active, deact):
    tok = secrets.token_hex(16)
    cur = conn.execute("SELECT customer_id FROM dashboard_users WHERE id=?", (duid,)).fetchone()
    conn.execute("UPDATE dashboard_users SET session_token=?, session_expires_at=?, "
                 "payment_status=?, is_activated=1 WHERE id=?",
                 (tok, exp.isoformat(), ps, duid))
    conn.execute("UPDATE customers SET is_active=?, deactivated_at=? WHERE id=?",
                 (is_active, deact, cur["customer_id"]))
    conn.commit()
    return tok

def darf_rein(sql, tok):
    return conn.execute(sql, (tok,)).fetchone() is not None

duid = conn.execute("SELECT id FROM dashboard_users LIMIT 1").fetchone()["id"]

FAELLE = [
    ("zahlender Kunde",         "paid",         1, None,         True,  True),
    ("Kunde PAUSIERT selbst",   "paid",         0, None,         True,  True),
    ("gekuendigt (Kick)",       "cancelled",    0, "2026-09-01",  True,  False),
    ("erstattet",               "refunded",     0, "2026-09-01",  True,  False),
    ("chargeback",              "chargebacked", 0, "2026-09-01",  True,  False),
    ("suspendiert",             "suspended",    0, "2026-09-01",  True,  False),
    ("gekickt, zahlt weiter",   "paid",         0, "2026-09-01",  True,  False),
    ("Onboarding (pending)",    "pending",      1, None,         True,  True),
    ("payment_status NULL",     None,           1, None,         True,  True),
    ("reaktiviert",             "paid",         1, None,         True,  True),
    ("gekuendigt, aber aktiv",  "cancelled",    1, None,         True,  False),
]

print(f"{'Fall':<26} {'alt':<6} {'neu':<6} {'erwartet':<9} Ergebnis")
print("-" * 64)
fehler = 0
for name, ps, act, deact, e_alt, e_neu in FAELLE:
    tok = setze(duid, ps, act, deact)
    a, n = darf_rein(SQL_ALT, tok), darf_rein(SQL_NEU, tok)
    gut = (a == e_alt and n == e_neu)
    fehler += 0 if gut else 1
    print(f"{name:<26} {str(a):<6} {str(n):<6} {str(e_neu):<9} {'PASS' if gut else 'FAIL <<<'}")
print("-" * 64)
print(f"{len(FAELLE)-fehler}/{len(FAELLE)} PASS")

conn.close()
for suf in ("", "-wal", "-shm"):
    if os.path.exists(COPY + suf):
        os.remove(COPY + suf)

ro = sqlite3.connect(f"file:{SRC}?mode=ro", uri=True)
ro.row_factory = sqlite3.Row
ges = ro.execute("SELECT COUNT(*) n FROM dashboard_users WHERE session_token IS NOT NULL "
                 "AND session_expires_at > CURRENT_TIMESTAMP").fetchone()["n"]
betroffen = ro.execute("""SELECT du.id, du.email, du.payment_status FROM dashboard_users du
  JOIN customers c ON c.id=du.customer_id
  WHERE du.session_token IS NOT NULL AND du.session_expires_at > CURRENT_TIMESTAMP
    AND du.is_activated=1
    AND (COALESCE(du.payment_status,'') IN ('cancelled','refunded','chargebacked','suspended')
         OR (c.is_active=0 AND c.deactivated_at IS NOT NULL))""").fetchall()
print(f"\nAktive Sessions gesamt: {ges}")
print(f"Davon sofort beendet:   {len(betroffen)}")
for r in betroffen:
    print(f"   id {r['id']:>4}  {r['payment_status']:<13} {r['email']}")
ro.close()
print("\nDB-Kopie geloescht. Produktions-DB unberuehrt.")
