#!/usr/bin/env python3
"""(C) check_possides_francesco.py - READ-ONLY Diagnose.

Frage: Warum scheitert die Copy-Order fuer Francesco mit
HTTP 400 / code 600034 "Order not found", obwohl im Mai mit identischem
Body (posSide "Multi") 22 Orders sauber durchliefen?

Verdacht: Die LeveX-Doku listet fuer den Copy-Order-Endpoint
posSide als "Long/Short". "Multi" ist nur im Multi-Position-Modus gueltig.
Der Modus-Wechsel-Call ist tot (HTTP 405), wir haben also nie verifiziert,
in welchem Modus Francescos Account wirklich steht.

Dieses Script liest NUR:
  1. Order-Historie seines Accounts (perp-trading/order)
     -> zeigt den posSide, den LeveX bei SEINEN eigenen, manuell
        platzierten Orders tatsaechlich gespeichert hat
  2. Account/Positions-Endpoint (mit currency UND symbol, wegen
     dem bekannten Bug vom 31.08.)

Es wird KEINE Order platziert, storniert oder veraendert.

Keys kommen aus der Bot-DB (customers.api_key/api_secret).
Aufruf: cd /home/botuser/copy-trading-bot && python3 check_possides_francesco.py
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
CUSTOMER_ID = "bdc19c7b-5a7c-4429-a7bc-67e93c66a28d"  # Francesco Buontempo

con = sqlite3.connect("copy_trading.db")
row = con.execute(
    "SELECT name, api_key, api_secret FROM customers WHERE id = ?",
    (CUSTOMER_ID,),
).fetchone()
con.close()

if not row or not row[1]:
    raise SystemExit("FEHLER: Kunde/Keys nicht gefunden")

NAME, API_KEY, API_SECRET = row
print("Account:", NAME)
print("=" * 70)


def sign(path, query="", body=""):
    content = path
    if query:
        content += "?" + query
    if body:
        content += body
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
        return {"HTTP_ERROR": e.code, "body": e.read().decode()[:400]}


# --- 1. Order-Historie: welchen posSide nutzt sein Account wirklich? ---
print("\n[1] ORDER-HISTORIE (seine eigenen, manuell platzierten Orders)")
hist = get(
    "/api/service-perpetual/perp-trading/order",
    {"symbols": "BTCUSDT", "pageNumber": "1", "pageSize": "20"},
)

if "HTTP_ERROR" in hist:
    print("    FEHLER:", hist)
else:
    res = hist.get("result") or {}
    rows = res if isinstance(res, list) else (res.get("rows") or res.get("list") or [])
    print("    Eintraege:", len(rows))
    for o in rows[:12]:
        print(
            "      %-8s %-5s posSide=%-8s qty=%-10s status=%-12s %s"
            % (
                o.get("symbol"),
                o.get("side"),
                o.get("posSide"),
                o.get("orderQty"),
                o.get("ordStatus"),
                o.get("createdAt", ""),
            )
        )
    if not rows:
        print("    (leer) Rohantwort:", json.dumps(hist)[:400])

# --- 2. Account-Zustand (mit symbol, wegen Bug vom 31.08.) ---
print("\n[2] ACCOUNT + POSITIONEN")
acc = get("/api/perpetual/accounts/positions", {"currency": "USDT", "symbol": "BTCUSDT"})
if "HTTP_ERROR" in acc:
    print("    FEHLER:", acc)
else:
    r = acc.get("result") or {}
    a = r.get("account") or {}
    print("    Balance:", a.get("accountBalance"), "| Used:", a.get("totalUsedBalance"))
    pos = r.get("positions") or []
    print("    Offene Positionen:", len(pos))
    for p in pos:
        print(
            "      posSide=%-8s size=%-10s lev=%-6s marginMode=%s"
            % (
                p.get("posSide"),
                p.get("size"),
                p.get("leverage"),
                p.get("marginMode"),
            )
        )
    # Interessant: enthaelt die Antwort ein Modus-Feld?
    for key in ("posMode", "positionMode", "mode"):
        if key in a or key in r:
            print("    MODUS-FELD %s:" % key, a.get(key, r.get(key)))
