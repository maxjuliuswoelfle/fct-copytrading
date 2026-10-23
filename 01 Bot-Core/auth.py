"""
(C) auth.py — Authentifizierung fuer die Levex API

HMAC-SHA256 Signatur-Erstellung fuer WebSocket und REST Requests.
Der Server probiert zuerst den Raw Key, dann den Base64-decodierten Key —
wir probieren beides und geben beide Varianten zurueck.
"""

import hmac
import hashlib
import base64
import time


def create_signature(secret: str, content: str) -> str:
    """
    Erstellt eine HMAC-SHA256 Signatur.

    Args:
        secret: Der API Secret (raw string)
        content: Der zu signierende Content-String

    Returns:
        Hex-encoded Signatur
    """
    return hmac.new(
        secret.encode("utf-8"),
        content.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def create_signature_base64(base64_secret: str, content: str) -> str:
    """
    Erstellt eine HMAC-SHA256 Signatur mit Base64-decodiertem Secret.
    Manche APIs erwarten, dass der Secret erst aus Base64 decoded wird.

    Args:
        base64_secret: Der API Secret als Base64-String
        content: Der zu signierende Content-String

    Returns:
        Hex-encoded Signatur
    """
    decoded_secret = base64.b64decode(base64_secret)
    return hmac.new(
        decoded_secret,
        content.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def create_ws_auth_params(api_key: str, api_secret: str) -> dict:
    """
    WebSocket Auth Parameter erstellen.

    Levex erwartet fuer die WS-Authentifizierung:
    - apiKey
    - signature (HMAC-SHA256 ueber den signContent)
    - expiry (Ablaufzeitpunkt in Millisekunden)

    signContent Format: /tokens/self?requestExpiry=<epoch_ms>
    Expiry = jetzt + 60 Sekunden

    Der Server probiert erst den Raw Key, dann Base64-decoded.
    Wir senden die Raw-Signatur — wenn das nicht klappt, wird Base64 versucht.
    """
    # Expiry: 60 Sekunden ab jetzt (in Millisekunden)
    expiry = int(time.time() * 1000) + 60_000
    sign_content = f"/tokens/self?requestExpiry={expiry}"

    # Primaer: Raw Secret verwenden (Server probiert das zuerst)
    try:
        signature = create_signature(api_secret, sign_content)
    except Exception:
        # Fallback: Base64-decoded Secret
        signature = create_signature_base64(api_secret, sign_content)

    return {
        "apiKey": api_key,
        "signature": signature,
        "expiry": expiry,
    }
