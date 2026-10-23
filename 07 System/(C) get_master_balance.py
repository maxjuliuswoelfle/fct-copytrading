"""(C) get_master_balance.py - read-only: aktuelle Futures-Balance des Master-Accounts."""
import json
import time
import hmac
import hashlib
import urllib.parse
import urllib.request

BASE = "https://api.levex.com"
PATH = "/api/perpetual/accounts/positions"

env = {}
with open(".env", "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()

params = {
    "currency": "USDT",
    "symbol": "BTCUSDT",
    "requestExpiry": str(int(time.time() * 1000) + 60_000),
}
qs = urllib.parse.urlencode(params)
sign = hmac.new(env["LEVEX_API_SECRET"].encode(), (PATH + "?" + qs).encode(), hashlib.sha256).hexdigest()
req = urllib.request.Request(
    BASE + PATH + "?" + qs,
    headers={
        "X-LX-APIKEY": env["LEVEX_API_KEY"],
        "X-LX-SIGNATURE": sign,
        "Content-Type": "application/json",
    },
)
with urllib.request.urlopen(req, timeout=30) as r:
    res = json.loads(r.read().decode())
acc = (res.get("result") or {}).get("account") or {}
print(json.dumps(acc, indent=2)[:1200])
