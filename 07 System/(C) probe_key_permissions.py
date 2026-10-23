#!/usr/bin/env python3
"""(C) probe_key_permissions.py - READ-ONLY Sondierung.

Befund aus dem Endpoint-Test:
  POST perpetual/orders            -> 600007 "auth.accessdenied"
  POST copy-affiliate-order        -> 600034 "Order not found"
  GET  (alle Lese-Endpoints)       -> 200 OK

Verdacht: Francescos API-Key hat NUR Leserechte, keine Trading-Rechte.
Am 31.08. wurde nur ein READ-Call (orders/active-all) verifiziert -
ein Schreib-Call wurde nie getestet.

Dieses Script sondiert rein lesend, welche Endpoints der Key beantwortet,
und sucht einen Endpoint, der die Key-Berechtigungen ausgibt.
Es wird NICHTS platziert oder veraendert.

Aufruf: cd /home/botuser/copy-trading-bot && python3 probe_key_permissions.py
"""
import hashlib
import hmac
import json
import sqlite3
import time
import urllib.error
import urllib.request
from urllib.parse import urlencode

REST_URL = "https://api.levex.com"
CUSTOMER_ID = "bdc19c7b-5a7c-4429-a7bc-67e93c66a28d"

con = sqlite3.connect("copy_trading.db")
NAME, API_KEY, API_SECRET = con.execute(
    "SELECT name, api_key, api_secret FROM customers WHERE id = ?", (CUSTOMER_ID,)
).fetchone()
con.close()

print("Account:", NAME, "| Key:", API_KEY[:6] + "..." + API_KEY[-4:])
print("=" * 72)


def sign(path, query="", body=""):
    content = path + ("?" + query if query else "") + body
    return hmac.new(
        API_SECRET.encode("utf-8"), content.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def get(path, params=None):
    params = dict(params or {})
    params["requestExpiry"] = str(int(time.time() * 1000) + 60_000)
    query = urlencode(params)
    req = urllib.request.Request(
        REST_URL + path + "?" + query,
        headers={
            "X-LX-APIKEY": API_KEY,
            "X-LX-SIGNATURE": sign(path, query, ""),
            "Content-Type": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, r.read().decode()[:300]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]
    except Exception as e:  # noqa: BLE001
        return -1, str(e)[:200]


CANDIDATES = [
    ("/api/perpetual/orders/active-all", {"symbol": "BTCUSDT"}),
    ("/api/perpetual/accounts/positions", {"currency": "USDT", "symbol": "BTCUSDT"}),
    ("/api/service-perpetual/perp-trading/order", {"symbols": "BTCUSDT", "pageSize": "1"}),
    ("/api/user/api-key", None),
    ("/api/user/api-key/info", None),
    ("/api/account/api-key", None),
    ("/api/user/info", None),
    ("/api/service-affiliate/affiliate/client/summary", {"pageSize": "1", "pageNumber": "1"}),
]

for path, params in CANDIDATES:
    status, body = get(path, params)
    flag = "OK " if status == 200 else "   "
    print("%s %-3s  %s" % (flag, status, path))
    if status != 200:
        print("        ", body[:160])
