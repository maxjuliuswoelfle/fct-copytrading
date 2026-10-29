"""
(C) check_pos_mode.py — Position-Modus eines Levex-Accounts pruefen/setzen

Hintergrund: Beim Bot-Start ruft listen.py fuer jeden Kunden
`switch_position_mode(symbol, "Multi")` auf. Bei Francesco kam dabei
Fehlercode [405] mit leerer Message zurueck — der Bot hat ihn NICHT
deaktiviert (das passiert nur bei code 2136 = offene Positionen), aber
es blieb unklar, ob der Multi-Trade-Modus jetzt aktiv ist.

Dieses Script macht exakt denselben Call wie der Bot und druckt die
VOLLE Antwort, damit der Fehlercode lesbar wird.

Aufruf (Keys NIE in diese Datei schreiben):
    CHECK_KEY=xxx CHECK_SECRET=yyy python3 check_pos_mode.py

Signatur-Logik 1:1 wie 01 Bot-Core/rest_client.py.
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
SYMBOL = os.getenv("CHECK_SYMBOL", "BTCUSDT")
TARGET = os.getenv("CHECK_TARGET", "Multi")

if not API_KEY or not API_SECRET:
    print("FEHLER: CHECK_KEY und CHECK_SECRET muessen gesetzt sein.")
    sys.exit(1)


def sign(path: str, query: str = "", body: str = "") -> str:
    content = path
    if query:
        content += "?" + query
    if body:
        content += body
    return hmac.new(
        API_SECRET.encode("utf-8"),
        content.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def request(method: str, path: str, params: dict = None, body_obj: dict = None) -> tuple:
    params = dict(params or {})
    params["requestExpiry"] = str(int(time.time() * 1000) + 60_000)
    query = urlencode(params)
    body = json.dumps(body_obj) if body_obj is not None else ""
    signature = sign(path, query, body)

    url = f"{REST_URL}{path}?{query}"
    data = body.encode("utf-8") if body else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("X-LX-APIKEY", API_KEY)
    req.add_header("X-LX-SIGNATURE", signature)
    req.add_header("Content-Type", "application/json")

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read().decode("utf-8")
            try:
                return resp.status, json.loads(raw)
            except json.JSONDecodeError:
                return resp.status, raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8")
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, raw
    except Exception as e:
        return -1, str(e)


print("=" * 60)
print("LEVEX POSITION-MODUS CHECK")
print(f"Key: {API_KEY[:6]}...{API_KEY[-4:]}   Symbol: {SYMBOL}   Ziel: {TARGET}")
print("=" * 60)

# 1) Aktueller Account-Zustand (read-only) — enthaelt ggf. den Modus
s1, p1 = request("GET", "/api/perpetual/accounts/positions",
                 {"currency": "USDT", "symbol": SYMBOL})
print(f"\n--- 1) Account-Zustand (GET, read-only) --- HTTP {s1}")
if isinstance(p1, dict):
    result = p1.get("result") or {}
    acc = result.get("account") or {}
    print("account-Felder:", json.dumps(acc, ensure_ascii=False)[:700])
    print("Anzahl positions:", len(result.get("positions") or []))
else:
    print(p1)

# 2) Derselbe Call wie im Bot beim Start — volle Fehlermeldung sichtbar machen
s2, p2 = request("POST", "/api/perpetual/positions/switch-pos-mode",
                 {}, {"symbol": SYMBOL, "targetPosMode": TARGET})
print(f"\n--- 2) switch-pos-mode (POST, wie im Bot) --- HTTP {s2}")
print(json.dumps(p2, ensure_ascii=False)[:900] if isinstance(p2, dict) else str(p2)[:900])

print("\n" + "=" * 60)
if isinstance(p2, dict) and not p2.get("error"):
    print("ERGEBNIS: Modus-Wechsel erfolgreich — Multi-Trade Modus aktiv.")
elif isinstance(p2, dict):
    err = p2.get("error") or {}
    print(f"ERGEBNIS: Fehler [{err.get('code')}] {err.get('message')}")
    print("Hinweis: Bedeutet der Code 'bereits im Zielmodus', ist alles in Ordnung.")
print("=" * 60)
