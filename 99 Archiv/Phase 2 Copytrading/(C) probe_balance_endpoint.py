"""
(C) probe_balance_endpoint.py — Read-Only Sondierung des Balance-Endpoints

Testet mehrere Endpoint-/Parameter-Varianten, um herauszufinden welcher Call
die Futures-Balance liefert. Macht ausschliesslich GET-Requests.

Aufruf (Keys NIE in diese Datei schreiben):
    CHECK_KEY=xxx CHECK_SECRET=yyy python3 "(C) probe_balance_endpoint.py"
"""

import os
import sys
import json
import time
import hmac
import hashlib
import urllib.request
import urllib.error
from urllib.parse import urlencode

REST_URL = "https://api.levex.com"
API_KEY = os.getenv("CHECK_KEY", "")
API_SECRET = os.getenv("CHECK_SECRET", "")

if not API_KEY or not API_SECRET:
    print("FEHLER: CHECK_KEY und CHECK_SECRET muessen gesetzt sein.")
    sys.exit(1)


def get(path: str, params: dict):
    params = dict(params)
    params["requestExpiry"] = str(int(time.time() * 1000) + 60_000)
    query = urlencode(params)
    content = path + "?" + query
    signature = hmac.new(
        API_SECRET.encode("utf-8"), content.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    req = urllib.request.Request(f"{REST_URL}{path}?{query}", method="GET")
    req.add_header("X-LX-APIKEY", API_KEY)
    req.add_header("X-LX-SIGNATURE", signature)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")
    except Exception as e:
        return -1, str(e)


VARIANTEN = [
    ("/api/perpetual/accounts/positions", {"currency": "USDT"}),
    ("/api/perpetual/accounts/positions", {"currency": "USDT", "symbol": "BTCUSDT"}),
    ("/api/perpetual/accounts/positions", {"symbol": "BTCUSDT"}),
    ("/api/perpetual/accounts/positions", {}),
    ("/api/perpetual/accounts/accountPositions", {"currency": "USDT"}),
    ("/api/service-perpetual/accounts/positions", {"currency": "USDT"}),
    ("/api/perpetual/accounts/wallet", {"currency": "USDT"}),
]

for path, params in VARIANTEN:
    status, body = get(path, params)
    marker = "OK " if status == 200 else "FAIL"
    print(f"\n[{marker}] {status}  {path}  {params}")
    print(f"      {body[:400]}")
