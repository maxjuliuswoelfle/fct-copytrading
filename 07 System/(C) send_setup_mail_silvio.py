#!/usr/bin/env python3
"""Einmal-Script: Setup-/Onboarding-Mail an Silvio Kind (Lifetime-Free).
Laeuft im Dashboard-Ordner. Laedt die .env ueber einen RELATIVEN Pfad,
damit der Bash-Aufruf ohne absolute Pfade auskommt (Vault-Sperre)."""
import os

ENV = os.path.join("..", "copy-trading-bot", ".env")
with open(ENV) as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

import email_service

ok = email_service.send_purchase_setup_email("silviokind95@gmx.de", "Silvio")
print("RESULT:", ok)
