"""
(C) check_api_key.py — Read-Only Pruefung eines Levex API Keys

Prueft, ob ein Kunden-Key funktioniert, BEVOR er ins System eingetragen wird.
Macht ausschliesslich GET-Requests — platziert NIEMALS eine Order.

Aufruf (Keys kommen aus der Umgebung, NIE in diese Datei schreiben):
    CHECK_KEY=xxx CHECK_SECRET=yyy python3 "(C) check_api_key.py"

Signatur-Logik ist 1:1 identisch zu 01 Bot-Core/rest_client.py.
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

if not API_KEY or not API_SECRET:
    print("FEHLER: CHECK_KEY und CHECK_SECRET muessen als Umgebungsvariablen gesetzt sein.")
    sys.exit(1)


def sign(path: str, query: str = "", body: str = "") -> str:
    """HMAC-SHA256 wie im Bot: path + ?query + body"""
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


def get(path: str, params: dict) -> tuple:
    """GET-Request mit Auth. Returns (http_status, parsed_body_or_text)."""
    params = dict(params)
    params["requestExpiry"] = str(int(time.time() * 1000) + 60_000)
    query = urlencode(params)
    signature = sign(path, query)

    url = f"{REST_URL}{path}?{query}"
    req = urllib.request.Request(url, method="GET")
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
    except Exception as e:  # Netz-/DNS-Fehler
        return -1, str(e)


def show(label: str, status, payload) -> bool:
    """Ergebnis ausgeben. Returns True wenn der Call sauber durchlief."""
    print(f"\n--- {label} ---")
    print(f"HTTP: {status}")
    if isinstance(payload, dict) and payload.get("error"):
        print(f"API-FEHLER: {json.dumps(payload['error'], ensure_ascii=False)}")
        return False
    text = json.dumps(payload, ensure_ascii=False)[:900] if isinstance(payload, (dict, list)) else str(payload)[:900]
    print(f"Antwort: {text}")
    return status == 200


print("=" * 60)
print("LEVEX API KEY CHECK (read-only)")
print(f"Key: {API_KEY[:6]}...{API_KEY[-4:]}  (Laenge {len(API_KEY)})")
print(f"Secret-Laenge: {len(API_SECRET)}")
print("=" * 60)

# 1) Auth + IP-Whitelist: derselbe Call, den der Setup-Wizard nutzt
s1, p1 = get("/api/perpetual/orders/active-all", {"symbol": "BTCUSDT"})
ok_auth = show("1) Auth-Check (aktive Orders BTCUSDT)", s1, p1)

# 2) Account/Balance: zeigt ob Futures-Wallet erreichbar ist
s2, p2 = get("/api/perpetual/accounts/positions", {"currency": "USDT"})
ok_acc = show("2) Account/Balance (Perpetual USDT)", s2, p2)

print("\n" + "=" * 60)
if ok_auth and ok_acc:
    print("ERGEBNIS: KEY FUNKTIONIERT — Auth ok, IP freigeschaltet, Account lesbar.")
elif ok_auth:
    print("ERGEBNIS: Auth ok, aber Account-Abfrage fehlgeschlagen (siehe oben).")
else:
    print("ERGEBNIS: KEY FUNKTIONIERT NICHT — Details oben pruefen.")
    print("Typisch: 401/403 = Key/Secret falsch oder IP nicht freigeschaltet.")
print("=" * 60)
