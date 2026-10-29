#!/usr/bin/env python3
"""(C) compare_affiliate_records.py - READ-ONLY.

Vergleicht den VOLLEN Affiliate-Record von:
  1159249 = TEST KUNDE (Mai, 22 Copy-Orders liefen erfolgreich)
  1150608 = Francesco Buontempo (Copy-Orders scheitern mit 600034)

Beide stehen in der Affiliate-Liste. Frage: Unterscheiden sie sich in
einem Status-Feld (z.B. Copy-Trading-/Follow-Status), das erklaert, warum
der copy-affiliate-order-Endpoint bei einem funktioniert und beim anderen
'Order not found' liefert?

Nutzt die Affiliate-Keys aus der .env (relativer Pfad).
Es wird NICHTS veraendert.
Aufruf: cd /home/botuser/copy-trading-bot && python3 compare_affiliate_records.py
"""
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request
from urllib.parse import urlencode

REST_URL = "https://api.levex.com"

with open(".env") as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

API_KEY = os.environ["AFFILIATE_API_KEY"]
API_SECRET = os.environ["AFFILIATE_API_SECRET"]
TARGETS = {"1159249": "TEST KUNDE (Mai, funktionierte)",
           "1150608": "Francesco (scheitert)"}


def sign(path, query):
    return hmac.new(
        API_SECRET.encode("utf-8"),
        (path + "?" + query).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def get(path, params):
    params = dict(params)
    params["requestExpiry"] = str(int(time.time() * 1000) + 60_000)
    query = urlencode(params)
    req = urllib.request.Request(
        REST_URL + path + "?" + query,
        headers={
            "X-LX-APIKEY": API_KEY,
            "X-LX-SIGNATURE": sign(path, query),
            "Content-Type": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"HTTP_ERROR": e.code, "body": e.read().decode()[:400]}


path = "/api/service-affiliate/affiliate/client/summary"
found = {}
page = 1
while page <= 20 and len(found) < len(TARGETS):
    data = get(path, {"pageSize": "500", "pageNumber": str(page)})
    if "HTTP_ERROR" in data:
        print("FEHLER:", data)
        break
    res = data.get("result") or {}
    rows = res if isinstance(res, list) else (res.get("rows") or res.get("list") or [])
    if not rows:
        break
    for rec in rows:
        cid = str(rec.get("clientId", ""))
        if cid in TARGETS:
            found[cid] = rec
    if len(rows) < 500:
        break
    page += 1

for uid, label in TARGETS.items():
    print("=" * 70)
    print(uid, "-", label)
    print("=" * 70)
    rec = found.get(uid)
    print(json.dumps(rec, indent=2) if rec else "  NICHT GEFUNDEN")
    print()

if len(found) == 2:
    a, b = found["1159249"], found["1150608"]
    print("=" * 70)
    print("UNTERSCHIEDE (Feld: Mai-Testkunde  ->  Francesco)")
    print("=" * 70)
    for key in sorted(set(a) | set(b)):
        if a.get(key) != b.get(key):
            print("  %-28s %-22s -> %s" % (key, a.get(key), b.get(key)))
