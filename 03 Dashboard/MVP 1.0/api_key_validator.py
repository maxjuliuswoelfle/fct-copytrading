"""
(C) api_key_validator.py — Levex API Key Validierung + Balance-Check

Prueft ob ein Copy Trading API Key gueltig ist und die richtige
Berechtigung hat. Prueft die Futures-Balance via WebSocket.
Wird im Setup-Wizard und als API-Endpoint verwendet.
"""

import asyncio
import hmac
import hashlib
import json
import os
import sys
import time

# Bot-Core Pfad fuer REST Client
# Lokal: ../01 Bot-Core/   Server: /home/botuser/copy-trading-bot/
BOT_CORE_PATH = os.path.join(os.path.dirname(__file__), "..", "01 Bot-Core")
BOT_CORE_SERVER = "/home/botuser/copy-trading-bot"
for p in [BOT_CORE_PATH, BOT_CORE_SERVER]:
    if os.path.isdir(p) and p not in sys.path:
        sys.path.insert(0, p)

from rest_client import LevexRESTClient

import websockets

# Base URL aus Config oder Fallback
LEVEX_BASE_URL = os.getenv("LEVEX_BASE_URL", "https://api.levex.com")
LEVEX_WS_URL = os.getenv("LEVEX_WS_URL", "wss://stream.levex.com")


async def validate_api_key(api_key: str, api_secret: str) -> dict:
    """
    Prueft ob der API Key gueltig ist und Copy Trading Berechtigung hat.

    Returns: {valid: bool, uid: str, error: str}
    """
    if not api_key or not api_secret:
        return {"valid": False, "uid": "", "error": "API Key und Secret sind erforderlich."}

    client = LevexRESTClient(
        base_url=LEVEX_BASE_URL,
        api_key=api_key,
        api_secret=api_secret,
    )

    try:
        # Account-Info abfragen um Key zu testen
        result = await client.get("/api/perpetual/orders/active-all", {"symbol": "BTCUSDT"})

        if result.get("error"):
            err = result["error"]
            code = str(err.get("code", ""))
            msg = err.get("message", "Unbekannter Fehler")

            if "401" in code or "auth" in msg.lower() or "10003" in code or "10004" in code:
                return {"valid": False, "uid": "", "error": "API Key ungültig. Bitte prüfen und erneut eingeben."}
            elif "permission" in msg.lower() or "403" in code:
                return {"valid": False, "uid": "", "error": "Falsche Berechtigung. Bitte einen Key mit 'Copy Trading' Berechtigung erstellen."}
            else:
                return {"valid": False, "uid": "", "error": f"API Fehler: {msg}"}

        # Key funktioniert — UID extrahieren falls vorhanden
        uid = ""
        if isinstance(result.get("result"), dict):
            uid = str(result["result"].get("userID", ""))
        elif result.get("userID"):
            uid = str(result["userID"])

        if not uid:
            uid = "unknown"

        return {"valid": True, "uid": uid, "error": ""}

    except Exception as e:
        return {"valid": False, "uid": "", "error": f"Verbindungsfehler: {str(e)}"}
    finally:
        await client.close()


async def check_futures_balance(api_key: str, api_secret: str) -> dict:
    """
    Futures-Balance via WebSocket abfragen.

    Baut eine temporaere WebSocket-Verbindung auf, subscribed auf
    perpAccount, liest die Balance und schliesst sofort wieder.

    Returns: {balance: float|None, error: str}
    """
    if not api_key or not api_secret:
        return {"balance": None, "error": "API Key und Secret sind erforderlich."}

    ws = None
    try:
        ws = await asyncio.wait_for(
            websockets.connect(LEVEX_WS_URL), timeout=10
        )

        # Auth
        expiry = int(time.time() * 1000) + 60_000
        sign_content = f"/tokens/self?requestExpiry={expiry}"
        signature = hmac.new(
            api_secret.encode("utf-8"),
            sign_content.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        msg_id = 1
        await ws.send(json.dumps({
            "id": msg_id,
            "method": "user.auth",
            "params": {
                "apiKey": api_key,
                "signature": signature,
                "expiry": expiry,
            },
        }))

        # Auth-Response abwarten
        resp = json.loads(await asyncio.wait_for(ws.recv(), timeout=5))
        if resp.get("error"):
            return {"balance": None, "error": "API Key ungültig oder keine Berechtigung."}

        # Subscribe auf perpAccount
        msg_id += 1
        await ws.send(json.dumps({
            "id": msg_id,
            "method": "perpAccount.subscribe",
            "params": {
                "account": True,
                "position": False,
                "order": False,
                "historyLimit": 0,
            },
        }))

        # Auf Account-Snapshot warten (max 10 Sekunden)
        deadline = time.time() + 10
        balance = None

        while time.time() < deadline:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=5)
                msg = json.loads(raw)

                if msg.get("method") == "perpAccount.update":
                    data = msg.get("data", {})
                    keys = data.get("keys", [])
                    accounts = data.get("accounts", [])

                    if keys and accounts:
                        for row in accounts:
                            mapped = dict(zip(keys, row))
                            bal = float(mapped.get("accountBalance", 0))
                            if bal >= 0:
                                balance = bal
                                break

                    if balance is not None:
                        break

            except asyncio.TimeoutError:
                break

        if balance is None:
            return {"balance": None, "error": "Konnte Balance nicht abfragen. Bitte erneut versuchen."}

        return {"balance": balance, "error": ""}

    except asyncio.TimeoutError:
        return {"balance": None, "error": "Zeitüberschreitung bei der Verbindung. Bitte erneut versuchen."}
    except Exception as e:
        return {"balance": None, "error": f"Verbindungsfehler: {str(e)}"}
    finally:
        if ws:
            try:
                await ws.close()
            except Exception:
                pass
