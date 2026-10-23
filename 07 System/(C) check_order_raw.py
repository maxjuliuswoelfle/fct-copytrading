#!/usr/bin/env python3
"""(C) check_order_raw.py - READ-ONLY.

Zeigt die Order-Historie von Francescos Account MIT allen Feldern und
Zeitstempeln. Ziel: (a) sehen ob die Bot-Order von heute 13:44 ueberhaupt
bei LeveX ankam, (b) den Grund der 'Rejected'-Order lesen, (c) den
Unterschied zwischen seinen eigenen (funktionierenden) Orders und der
Bot-Order finden.

Es wird NICHTS platziert oder veraendert.
Aufruf: cd /home/botuser/copy-trading-bot && python3 check_order_raw.py
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


def sign(path, query="", body=""):
    content = path + ("?" + query if query else "") + body
    return hmac.new(
        API_SECRET.encode("utf-8"), content.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def get(path, params):
    params = dict(params)
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
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return {"HTTP_ERROR": e.code, "body": e.read().decode()[:500]}


hist = get(
    "/api/service-perpetual/perp-trading/order",
    {"symbols": "BTCUSDT", "pageNumber": "1", "pageSize": "10"},
)
res = hist.get("result") or {}
rows = res if isinstance(res, list) else (res.get("rows") or res.get("list") or [])

print("Account:", NAME, "| Eintraege:", len(rows))
print("=" * 70)
print("\n--- NEUESTER EINTRAG, ALLE FELDER ---")
if rows:
    print(json.dumps(rows[0], indent=2)[:2500])

print("\n--- KOMPAKT MIT ZEIT ---")
for o in rows:
    ts = o.get("createdAt") or o.get("createTime") or o.get("transactTime") or ""
    if str(ts).isdigit() and len(str(ts)) >= 13:
        ts = time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(int(ts) / 1000))
    print(
        "%s | %-4s %-6s qty=%-9s posSide=%-6s %-12s reject=%s"
        % (
            ts,
            o.get("side"),
            o.get("orderType") or o.get("ordType"),
            o.get("orderQty"),
            o.get("posSide"),
            o.get("ordStatus"),
            o.get("rejectReason") or o.get("bizError") or "-",
        )
    )
