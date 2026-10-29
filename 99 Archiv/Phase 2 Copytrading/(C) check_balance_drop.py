#!/usr/bin/env python3
"""(C) check_balance_drop.py - READ-ONLY Klaerung.

Francescos Futures-Balance fiel am 09.09. um 14:10:47 UTC von
815,2797 USDT auf 0,0000004 USDT.

Dieses Script klaert ausschliesslich lesend, WAS passiert ist:
  - Order-Historie (kam um 14:10 eine Order dazu?)
  - Trade-Historie inkl. Transfer-Typen (TransferIn/ExchangeIn/ExchangeOut,
    Liq, Funding) - laut LeveX-Enum tauchen Transfers dort auf

Es wird NICHTS platziert oder veraendert.
Aufruf: cd /home/botuser/copy-trading-bot && python3 check_balance_drop.py
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
        return {"HTTP_ERROR": e.code, "body": e.read().decode()[:300]}


def rows_of(data):
    res = data.get("result") or {}
    return res if isinstance(res, list) else (res.get("rows") or res.get("list") or [])


def ts(v):
    if str(v).isdigit() and len(str(v)) >= 13:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(int(v) / 1000))
    return str(v)


print("Account:", NAME)
print("=" * 74)

print("\n[1] ORDER-HISTORIE (neueste 10)")
d = get("/api/service-perpetual/perp-trading/order",
        {"symbols": "BTCUSDT", "pageNumber": "1", "pageSize": "10"})
if "HTTP_ERROR" in d:
    print("   ", d)
else:
    for o in rows_of(d):
        print("  %s | %-4s %-16s qty=%-9s %-12s action=%s by=%s"
              % (ts(o.get("createTime") or o.get("actionTime")), o.get("side"),
                 o.get("ordType"), o.get("orderQty"), o.get("ordStatus"),
                 o.get("action"), o.get("actionBy")))

print("\n[2] TRADE-HISTORIE (neueste 15, inkl. Transfers)")
d = get("/api/service-perpetual/perp-trading/trade",
        {"pageNumber": "1", "pageSize": "15"})
if "HTTP_ERROR" in d:
    print("   ", d)
else:
    rws = rows_of(d)
    print("    Eintraege:", len(rws))
    for t in rws:
        print("  %s | type=%-12s %-8s qty=%-10s value=%-12s pnl=%s"
              % (ts(t.get("createTime") or t.get("tradeTime") or t.get("actionTime")),
                 t.get("tradeType") or t.get("type"), t.get("side"),
                 t.get("qty") or t.get("execQty"),
                 t.get("value") or t.get("execValue"),
                 t.get("closedPnL") or t.get("pnl")))
    if rws:
        print("\n    ROHDATEN neuester Eintrag:")
        print("   ", json.dumps(rws[0])[:600])

print("\n[3] AKTUELLER KONTOSTAND")
d = get("/api/perpetual/accounts/positions", {"currency": "USDT", "symbol": "BTCUSDT"})
if "HTTP_ERROR" in d:
    print("   ", d)
else:
    a = (d.get("result") or {}).get("account") or {}
    print("    accountBalance:", a.get("accountBalance"))
    print("    totalUsedBalance:", a.get("totalUsedBalance"))
    print("    Rohdaten:", json.dumps(a)[:400])
