#!/usr/bin/env python3
"""
(C) patch_session_gate.py - Session-Gate in database.py::get_user_by_session.

Sperrt gekuendigte/erstattete/gesperrte Kunden aus dem Dashboard.

BEWUSST NICHT im Gate: c.is_active allein.
  Grund: Die Route toggle-pause setzt is_active=0, wenn ein Kunde sein
  Copy Trading SELBST pausiert. Ein Gate auf is_active wuerde Pausierer
  aussperren - sie kaemen nicht mal mehr rein, um zu resumen.
  Unterscheidung stattdessen ueber deactivated_at:
    Kick/Chargeback -> is_active=0 UND deactivated_at gesetzt
    Selbst-Pause    -> is_active=0 UND deactivated_at NULL
"""
import shutil, sys, datetime

PFAD = "database.py"
STAMP = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

ALT = """            WHERE du.session_token = ?
            AND du.session_expires_at > CURRENT_TIMESTAMP
            AND du.is_activated = 1
        \"\"\", (session_token,)).fetchone()"""

NEU = """            WHERE du.session_token = ?
            AND du.session_expires_at > CURRENT_TIMESTAMP
            AND du.is_activated = 1
            AND COALESCE(du.payment_status, '') NOT IN
                ('cancelled', 'refunded', 'chargebacked', 'suspended')
            AND NOT (c.is_active = 0 AND c.deactivated_at IS NOT NULL)
        \"\"\", (session_token,)).fetchone()"""

src = open(PFAD, encoding="utf-8").read()
if "'cancelled', 'refunded', 'chargebacked', 'suspended'" in src:
    print("SKIP: Patch ist bereits drin."); sys.exit(0)
n = src.count(ALT)
if n != 1:
    print(f"ABBRUCH: Anker {n}x gefunden (erwartet genau 1). Nichts geaendert.")
    sys.exit(1)
shutil.copy2(PFAD, f"{PFAD}.bak_sessiongate_{STAMP}")
open(PFAD, "w", encoding="utf-8").write(src.replace(ALT, NEU))
print(f"OK: gepatcht. Backup: {PFAD}.bak_sessiongate_{STAMP}")
