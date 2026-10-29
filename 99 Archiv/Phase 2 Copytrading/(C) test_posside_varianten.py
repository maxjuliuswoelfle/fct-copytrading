#!/usr/bin/env python3
"""(C) test_posside_varianten.py - Variantentest am Copy-Endpoint.

STAND: Francescos Key hat nachweislich (Screenshot) die Berechtigung
"Affiliate Copy Trade" + "Futures Read", IP-Whitelist korrekt.
-> 600034 ist also KEIN Berechtigungsfehler, sondern fachlich.

HYPOTHESE: Die LeveX-Doku schreibt fuer copy-affiliate-order
posSide = "Long/Short" vor. Der Bot sendet "Multi". Francescos eigene
Orders stehen zwar auf "Multi", die liefen aber ueber die Weboberflaeche,
NICHT ueber diesen Endpoint.

TEST: Dieselbe nicht fuellbare Limit-Order mit verschiedenen posSide-Werten
und Zusatzfeldern. Ziel: herausfinden, welche Variante LeveX akzeptiert.

SICHERHEIT: Limit Buy 0.001 BTC @ 60000 (Markt ~79146) -> kein Fill moeglich.
Jede angenommene Order wird SOFORT storniert, danach Kontrolle auf 0 aktive.

Aufruf: cd /home/botuser/copy-trading-bot && python3 test_posside_varianten.py
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
PATH = "/api/service-perpetual/order/copy-affiliate-order"

SYMBOL = "BTCUSDT"
QTY = "0.001"
PRICE = "60000"

con = sqlite3.connect("copy_trading.db")
NAME, API_KEY, API_SECRET = con.execute(
    "SELECT name, api_key, api_secret FROM customers WHERE id = ?", (CUSTOMER_ID,)
).fetchone()
con.close()

print("Account:", NAME, "| Limit Buy", QTY, SYMBOL, "@", PRICE, "(kein Fill moeglich)")
print("=" * 74)


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
    req = urllib.request.Request(
        REST_URL + path + ("?" + query if query else ""),
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
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:  # noqa: BLE001
            return e.code, "<nicht lesbar>"
    except Exception as e:  # noqa: BLE001
        return -1, str(e)[:200]


BASE = {
    "symbol": SYMBOL,
    "side": "Buy",
    "orderQty": QTY,
    "ordType": "Limit",
    "price": PRICE,
    "timeInForce": "GoodTillCancel",
    "reduceOnly": False,
}

VARIANTEN = [
    ("1  posSide=Multi  (aktueller Bot-Stand)", {**BASE, "posSide": "Multi"}),
    ("2  posSide=Long   (laut Doku)", {**BASE, "posSide": "Long"}),
    ("3  posSide=Long + leverage", {**BASE, "posSide": "Long", "leverage": "50"}),
    ("4  posSide=Long + positionName", {**BASE, "posSide": "Long", "positionName": "Test"}),
    ("5  Market statt Limit, posSide=Long",
     {"symbol": SYMBOL, "side": "Buy", "posSide": "Long", "orderQty": QTY,
      "ordType": "Market", "timeInForce": "GoodTillCancel", "reduceOnly": False}),
]

placed = []

for label, body in VARIANTEN:
    # Variante 5 (Market) nur ausfuehren, wenn vorher KEINE Variante klappte
    if label.startswith("5") and placed:
        print("\n[%s] uebersprungen - eine Limit-Variante war bereits erfolgreich" % label)
        continue
    print("\n[%s]" % label)
    status, resp = call("POST", PATH, body_obj=body)
    txt = json.dumps(resp) if isinstance(resp, dict) else str(resp)
    err = resp.get("error") if isinstance(resp, dict) else None
    if status == 200 and not err:
        r = resp.get("result") or resp
        oid = r.get("orderID") if isinstance(r, dict) else None
        print("    ==> ERFOLG! HTTP 200, OrderID:", oid)
        if oid:
            placed.append(oid)
    else:
        code = err.get("code") if isinstance(err, dict) else status
        msg = err.get("message") if isinstance(err, dict) else txt[:150]
        print("    HTTP %s | code %s | %s" % (status, code, msg))

print("\n" + "=" * 74)
print("AUFRAEUMEN")
for oid in placed:
    s, r = call("DELETE", "/api/perpetual/orders",
                params={"symbol": SYMBOL, "posSide": "Long", "orderID": oid})
    print("  Cancel(Long) %s -> HTTP %s %s" % (oid, s, json.dumps(r)[:150]))
    if s != 200:
        s2, r2 = call("DELETE", "/api/perpetual/orders",
                      params={"symbol": SYMBOL, "posSide": "Multi", "orderID": oid})
        print("  Cancel(Multi) %s -> HTTP %s %s" % (oid, s2, json.dumps(r2)[:150]))

print("\nKONTROLLE - aktive Orders:")
s, resp = call("GET", "/api/perpetual/orders/active-all", params={"symbol": SYMBOL})
if isinstance(resp, dict):
    res = resp.get("result") or {}
    rows = res if isinstance(res, list) else (res.get("rows") or res.get("list") or [])
    print("  Anzahl:", len(rows))
    for o in rows:
        print("   ", o.get("orderID"), o.get("side"), o.get("ordType"),
              o.get("price"), o.get("orderQty"), o.get("posSide"), o.get("ordStatus"))

print("\nKONTROLLE - offene Positionen:")
s, resp = call("GET", "/api/perpetual/accounts/positions",
               params={"currency": "USDT", "symbol": SYMBOL})
if isinstance(resp, dict):
    r = resp.get("result") or {}
    a = r.get("account") or {}
    print("  Balance:", a.get("accountBalance"), "| Used:", a.get("totalUsedBalance"))
    for p in (r.get("positions") or []):
        print("   posSide=%s size=%s" % (p.get("posSide"), p.get("size")))
