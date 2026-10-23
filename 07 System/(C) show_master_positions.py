"""
(C) show_master_positions.py — Read-Only: offene Master-Positionen inkl. positionID

Aufruf auf dem Server (Keys aus .env, nie in die Datei schreiben):
    cd /home/botuser/copy-trading-bot && export $(grep -E "^LEVEX_API_(KEY|SECRET)=" .env | xargs) \
      && CHECK_KEY=$LEVEX_API_KEY CHECK_SECRET=$LEVEX_API_SECRET python3 /home/botuser/scripts/show_master_positions.py
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
SYMBOLS = os.getenv("CHECK_SYMBOLS", "BTCUSDT").split(",")

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


for symbol in SYMBOLS:
    symbol = symbol.strip()
    data = get("/api/perpetual/accounts/positions", {"currency": "USDT", "symbol": symbol})
    if data.get("error"):
        print(f"[{symbol}] FEHLER: {data['error']}")
        continue
    result = data.get("result") or {}
    acc = result.get("account") or {}
    print("=" * 62)
    print(f"{symbol} | accountBalance={acc.get('accountBalance')} used={acc.get('totalUsedBalance')}")
    for p in (result.get("positions") or []):
        try:
            size = float(p.get("size") or 0)
        except (TypeError, ValueError):
            size = 0.0
        print(
            f"  posID={p.get('positionID')} side={p.get('side')} posSide={p.get('posSide')} "
            f"size={p.get('size')} entry={p.get('avgEntryPrice')} lev={p.get('leverage')} "
            f"uPnL={p.get('unrealisedPnl')} liq={p.get('liquidationPrice')}"
        )
