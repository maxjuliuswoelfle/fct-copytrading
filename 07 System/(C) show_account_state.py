"""
(C) show_account_state.py — Read-Only Account-Zustand eines Levex Keys

Zeigt Balance + offene Positionen fuer mehrere Symbole. Nur GET-Requests.

Aufruf (Keys NIE in diese Datei schreiben):
    CHECK_KEY=xxx CHECK_SECRET=yyy python3 "(C) show_account_state.py"
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
SYMBOLS = os.getenv("CHECK_SYMBOLS", "BTCUSDT,ETHUSDT,SOLUSDT,XRPUSDT").split(",")

if not API_KEY or not API_SECRET:
    print("FEHLER: CHECK_KEY und CHECK_SECRET muessen gesetzt sein.")
    sys.exit(1)


def get(path: str, params: dict):
    params = dict(params)
    params["requestExpiry"] = str(int(time.time() * 1000) + 60_000)
    query = urlencode(params)
    signature = hmac.new(
        API_SECRET.encode("utf-8"),
        (path + "?" + query).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    req = urllib.request.Request(f"{REST_URL}{path}?{query}", method="GET")
    req.add_header("X-LX-APIKEY", API_KEY)
    req.add_header("X-LX-SIGNATURE", signature)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"error": {"code": e.code, "message": e.read().decode("utf-8")[:300]}}
    except Exception as e:
        return {"error": {"code": -1, "message": str(e)}}


account_shown = False

for symbol in SYMBOLS:
    symbol = symbol.strip()
    data = get("/api/perpetual/accounts/positions", {"currency": "USDT", "symbol": symbol})

    if data.get("error"):
        print(f"[{symbol}] FEHLER: {data['error']}")
        continue

    result = data.get("result") or {}
    acc = result.get("account") or {}

    if not account_shown and acc:
        print("=" * 62)
        print("ACCOUNT")
        print(f"  userID          : {acc.get('userID')}")
        print(f"  accountId       : {acc.get('accountId')}")
        print(f"  currency        : {acc.get('currency')}")
        print(f"  accountBalance  : {acc.get('accountBalance')}")
        print(f"  totalUsedBalance: {acc.get('totalUsedBalance')}")
        print(f"  bonusBalance    : {acc.get('bonusBalance')}")
        print("=" * 62)
        account_shown = True

    positions = result.get("positions") or []
    offen = []
    for p in positions:
        try:
            size = float(p.get("size") or 0)
        except (TypeError, ValueError):
            size = 0.0
        if size != 0:
            offen.append(p)

    if offen:
        for p in offen:
            print(f"\n[{symbol}] OFFENE POSITION")
            print(f"  side      : {p.get('side')}   posSide: {p.get('posSide')}")
            print(f"  size      : {p.get('size')}")
            print(f"  entry     : {p.get('avgEntryPrice')}")
            print(f"  leverage  : {p.get('leverage')}  crossMargin: {p.get('crossMargin')}")
            print(f"  posMargin : {p.get('positionMargin') or p.get('posMargin')}")
            print(f"  uPnL      : {p.get('unrealisedPnl')}")
            print(f"  liq       : {p.get('liquidationPrice')}")
    else:
        print(f"[{symbol}] keine offene Position (size=0)")
