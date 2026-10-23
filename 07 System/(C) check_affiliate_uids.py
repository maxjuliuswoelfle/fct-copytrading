#!/usr/bin/env python3
"""(C) check_affiliate_uids.py - READ-ONLY.

Prueft, ob bestimmte LeveX-UIDs in Max' Affiliate-Client-Liste stehen.

Hintergrund: place_order() im Bot nutzt den Copy-Affiliate-Order-Endpoint
(service-perpetual). Verdacht: LeveX akzeptiert dort nur Accounts, die als
Affiliate-Follower des Masters registriert sind. Ist der Ziel-Account NICHT
in der Liste, antwortet LeveX generisch mit HTTP 400 / code 600034
"Order not found".

Vergleich:
  1159249 = TEST KUNDE aus Mai (22 Orders liefen erfolgreich)
  1150608 = Francesco Buontempo (scheitert mit 600034)

Laeuft im Dashboard-Ordner, laedt die .env ueber RELATIVEN Pfad.
Aufruf: cd /home/botuser/dashboard && python3 check_affiliate_uids.py
"""
import os

ENV = os.path.join("..", "copy-trading-bot", ".env")
with open(ENV) as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

import affiliate_service

ids = affiliate_service._fetch_all_affiliate_client_ids()
print("Affiliate-Clients gesamt:", len(ids))

for uid, label in [("1159249", "TEST KUNDE (Mai, funktionierte)"),
                   ("1150608", "Francesco Buontempo (scheitert)"),
                   ("1080129", "Master LEVEX_MASTER_UID")]:
    print("  UID %9s  in Liste: %5s   <- %s" % (uid, str(uid in ids), label))

print("Beispiel-IDs aus der Liste:", sorted(ids)[:10])
