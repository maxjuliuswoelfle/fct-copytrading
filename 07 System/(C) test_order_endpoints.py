#!/usr/bin/env python3
"""(C) test_order_endpoints.py - ISOLATIONS-TEST auf Francescos Account.

FRAGE: Warum liefert der Copy-Endpoint 600034 "Order not found",
obwohl derselbe Body im Mai auf einem anderen Account funktionierte?
Liegt es am Endpoint / an der Key-Berechtigung - oder am Account?

METHODE: Dieselbe Limit-Order ueber ZWEI Endpoints:
  A) service-perpetual/order/copy-affiliate-order  (der Weg des Bots)
  B) perpetual/orders                              (normaler Trading-Endpoint)

SICHERHEIT:
  - Limit Buy 0.001 BTC @ 60000, Markt steht bei ~79146
    -> ca. 24 % unter Markt, kann NICHT gefuellt werden
  - Minimalgroesse (0.001 BTC = ~79 USDT Notional, bei 50x ~1,6 USDT Margin)
  - Jede angenommene Order wird SOFORT wieder storniert + verifiziert
  - Am Ende werden alle aktiven Orders aufgelistet zur Kontrolle

Aufruf: cd /home/botuser/copy-trading-bot && python3 test_order_endpoints.py
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

SYMBOL = "BTCUSDT"
QTY = "0.001"
LIMIT_PRICE = "60000"  # Markt ~79146 -> fuellt garantiert nicht

con = sqlite3.connect("copy_trading.db")
NAME, API_KEY, API_SECRET = con.execute(
    "SELECT name, api_key, api_secret FROM customers WHERE id = ?", (CUSTOMER_ID,)
).fetchone()
con.close()

print("Account:", NAME)
print("Test: Limit Buy %s %s @ %s (Markt ~79146 -> kein Fill moeglich)"
      % (QTY, SYMBOL, LIMIT_PRICE))
print("=" * 72)


def sign(path, query="", body=""):
    content = path + ("?" + query if query else "") + body
    return hmac.new(
        API_SECRET.encode("utf-8"), content.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def call(method, path, params=None, body_obj=None):
    params = dict(params or {})
    params["requestExpiry"] = str(int(time.time() * 1000) + 60_000)
    query = urlencode(params)
    body = json.dumps(body_obj) if body_obj is not None else ""
    url = REST_URL + path + ("?" + query if query else "")
    req = urllib.request.Request(
        url,
        data=body.encode() if body else None,
        headers={
            "X-LX-APIKEY": API_KEY,
            "X-LX-SIGNATURE": sign(path, query, body),
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:400]
    except Exception as e:  # noqa: BLE001
        return -1, str(e)


ORDER_BODY = {
    "symbol": SYMBOL,
    "side": "Buy",
    "posSide": "Multi",
    "orderQty": QTY,
    "ordType": "Limit",
    "price": LIMIT_PRICE,
    "timeInForce": "GoodTillCancel",
    "reduceOnly": False,
}

placed = []


def try_endpoint(label, path):
    print("\n[%s] POST %s" % (label, path))
    print("    Body:", json.dumps(ORDER_BODY))
    status, resp = call("POST", path, body_obj=ORDER_BODY)
    print("    HTTP:", status)
    print("    Antwort:", json.dumps(resp)[:400] if isinstance(resp, dict) else resp)
    if isinstance(resp, dict) and not resp.get("error"):
        r = resp.get("result") or resp
        oid = r.get("orderID") if isinstance(r, dict) else None
        if oid:
            print("    ==> ORDER ANGENOMMEN, OrderID:", oid)
            placed.append(oid)
    return status, resp


# --- A) Der Weg des Bots ---
try_endpoint("A  COPY-ENDPOINT (Bot-Weg)",
             "/api/service-perpetual/order/copy-affiliate-order")

# --- B) Normaler Trading-Endpoint ---
try_endpoint("B  NORMALER ENDPOINT", "/api/perpetual/orders")

# --- Aufraeumen ---
print("\n" + "=" * 72)
print("AUFRAEUMEN")
print("=" * 72)
for oid in placed:
    status, resp = call(
        "DELETE",
        "/api/perpetual/orders",
        params={"symbol": SYMBOL, "posSide": "Multi", "orderID": oid},
    )
    print("  Cancel %s -> HTTP %s | %s"
          % (oid, status, json.dumps(resp)[:200] if isinstance(resp, dict) else resp))

print("\nKONTROLLE - aktive Orders auf dem Account:")
status, resp = call("GET", "/api/perpetual/orders/active-all", params={"symbol": SYMBOL})
if isinstance(resp, dict):
    res = resp.get("result") or {}
    rows = res if isinstance(res, list) else (res.get("rows") or res.get("list") or [])
    print("  Anzahl:", len(rows))
    for o in rows:
        print("   ", o.get("orderID"), o.get("side"), o.get("ordType"),
              o.get("price"), o.get("orderQty"), o.get("ordStatus"))
else:
    print(" ", status, resp)
