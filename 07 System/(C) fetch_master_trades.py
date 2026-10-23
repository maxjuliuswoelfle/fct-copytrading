"""
(C) fetch_master_trades.py - read-only: Trade-Historie des Master-Accounts holen.

Wird im Bot-Ordner ausgefuehrt (liest .env ueber relativen Dateinamen).
Schreibt master_trades_raw.json in denselben Ordner.
"""
import sys
import json
import time
import hmac
import hashlib
import urllib.parse
import urllib.request

BASE = "https://api.levex.com"
PATH = "/api/service-perpetual/perp-trading/trade"


def load_env():
    env = {}
    with open(".env", "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    return env


env = load_env()
KEY = env["LEVEX_API_KEY"]
SECRET = env["LEVEX_API_SECRET"]


def call(params):
    params = dict(params)
    params["requestExpiry"] = str(int(time.time() * 1000) + 60_000)
    qs = urllib.parse.urlencode(params)
    sign = hmac.new(SECRET.encode(), (PATH + "?" + qs).encode(), hashlib.sha256).hexdigest()
    req = urllib.request.Request(
        BASE + PATH + "?" + qs,
        headers={
            "X-LX-APIKEY": KEY,
            "X-LX-SIGNATURE": sign,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print("HTTP", e.code, "BODY:", body[:800])
        print("QUERY:", qs)
        raise SystemExit(1)


PAGE_SIZE = 100
WINDOW_DAYS = 7
DAY_MS = 86_400_000

t_start = int(time.mktime(time.strptime("2025-12-01", "%Y-%m-%d")) * 1000)
t_end = int(time.time() * 1000)

all_rows = []
first = True
win_start = t_start
while win_start < t_end:
    win_end = min(win_start + WINDOW_DAYS * DAY_MS, t_end)
    page = 1
    while True:
        res = call({
            "start": win_start,
            "end": win_end,
            "pageNumber": page,
            "pageSize": PAGE_SIZE,
        })
        if res.get("error"):
            print("ERROR:", json.dumps(res["error"])[:500])
            sys.exit(1)
        result = res.get("result") or {}
        if isinstance(result, list):
            rows = result
        else:
            rows = result.get("rows") or result.get("list") or result.get("data") or []
        if first:
            print("TOP-LEVEL KEYS:", list(res.keys()))
            print("RESULT KEYS:", list(result.keys()) if isinstance(result, dict) else "list")
            if rows:
                print("SAMPLE ROW:", json.dumps(rows[0], indent=2)[:2000])
                first = False
        if not rows:
            break
        all_rows.extend(rows)
        if len(rows) < PAGE_SIZE:
            break
        page += 1
        if page > 50:
            break
    win_start = win_end

with open("master_trades_raw.json", "w", encoding="utf-8") as f:
    json.dump(all_rows, f)
print("GESAMT:", len(all_rows))
