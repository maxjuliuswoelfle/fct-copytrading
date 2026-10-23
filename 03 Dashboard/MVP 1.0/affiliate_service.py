"""
(C) affiliate_service.py — Levex Affiliate-Verifizierung

Prueft ob eine UID (clientId) in Max' Affiliate-Liste existiert.
Nutzt den Levex Affiliate API Endpoint:
  GET /api/service-affiliate/affiliate/client/summary

Auth: HMAC-SHA256 Signing (gleiche Logik wie Bot-Core).
Braucht eigene Keys: AFFILIATE_API_KEY, AFFILIATE_API_SECRET

Die Affiliate-Liste wird gecacht (max 5 Minuten), damit nicht bei
jedem Setup-Request alle Seiten abgefragt werden muessen.
"""

import os
import hmac
import hashlib
import time
import json
import logging
from urllib.parse import urlencode
import urllib.request

logger = logging.getLogger("affiliate")

AFFILIATE_API_KEY = os.getenv("AFFILIATE_API_KEY", "")
AFFILIATE_API_SECRET = os.getenv("AFFILIATE_API_SECRET", "")
BASE_URL = os.getenv("AFFILIATE_BASE_URL", "https://api.levex.com")

# Cache: {timestamp, client_ids}
_cache: dict = {"timestamp": 0.0, "client_ids": set()}
CACHE_TTL = 300  # 5 Minuten


def _sign_request(path: str, params: dict) -> tuple[str, dict]:
    """
    HMAC-SHA256 Signing fuer Levex API.
    Returns: (full_url, headers)
    """
    params["requestExpiry"] = str(int(time.time() * 1000) + 60000)
    query = urlencode(params)
    sign_content = path + "?" + query
    sig = hmac.new(
        AFFILIATE_API_SECRET.encode(),
        sign_content.encode(),
        hashlib.sha256,
    ).hexdigest()
    url = BASE_URL + path + "?" + query
    headers = {
        "X-LX-APIKEY": AFFILIATE_API_KEY,
        "X-LX-SIGNATURE": sig,
    }
    return url, headers


def _fetch_all_affiliate_client_ids() -> set[str]:
    """
    Alle clientIds aus der Affiliate-API laden (paginiert, max 500 pro Seite).
    Returns: Set von clientId-Strings.
    """
    if not AFFILIATE_API_KEY or not AFFILIATE_API_SECRET:
        logger.warning("[AFFILIATE] API Keys nicht konfiguriert — Verifizierung nicht moeglich")
        return set()

    path = "/api/service-affiliate/affiliate/client/summary"
    page_size = 500
    page = 1
    all_ids: set[str] = set()

    while True:
        params = {"pageSize": str(page_size), "pageNumber": str(page)}
        url, headers = _sign_request(path, params)

        try:
            req = urllib.request.Request(url, headers=headers)
            resp = urllib.request.urlopen(req, timeout=15)
            data = json.loads(resp.read())
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:300]
            logger.error(f"[AFFILIATE] API Fehler Seite {page}: HTTP {e.code} — {body}")
            break
        except Exception as e:
            logger.error(f"[AFFILIATE] API Request fehlgeschlagen Seite {page}: {e}")
            break

        # Response ist eine Liste von Affiliate-Records
        if isinstance(data, list):
            records = data
        elif isinstance(data, dict):
            # Levex: {"error": null, "result": {"total": N, "rows": [...]}}
            result = data.get("result", {})
            if isinstance(result, dict) and "rows" in result:
                records = result["rows"]
            else:
                records = data.get("data", data.get("records", data.get("items", [])))
        else:
            logger.warning(f"[AFFILIATE] Unerwartetes Response-Format: {type(data)}")
            break

        if not records:
            break

        for record in records:
            client_id = record.get("clientId", "")
            if client_id:
                all_ids.add(str(client_id))

        logger.debug(f"[AFFILIATE] Seite {page}: {len(records)} Records geladen (Gesamt: {len(all_ids)})")

        # Weniger als pageSize → letzte Seite
        if len(records) < page_size:
            break

        page += 1

        # Safety: max 20 Seiten (10.000 Affiliates)
        if page > 20:
            logger.warning("[AFFILIATE] Mehr als 20 Seiten — Abbruch")
            break

    logger.info(f"[AFFILIATE] {len(all_ids)} Affiliate-UIDs geladen")
    return all_ids


def _get_cached_client_ids() -> set[str]:
    """Client-IDs mit Cache holen (TTL: 5 Minuten)."""
    now = time.time()
    if now - _cache["timestamp"] < CACHE_TTL and _cache["client_ids"]:
        return _cache["client_ids"]

    ids = _fetch_all_affiliate_client_ids()
    if ids:  # Nur cachen wenn erfolgreich
        _cache["timestamp"] = now
        _cache["client_ids"] = ids
    return ids


def verify_affiliate_uid(uid: str) -> tuple[bool, str]:
    """
    Prueft ob eine UID in der Affiliate-Liste existiert.

    Returns:
        (success, message)
        - (True, "OK") wenn verifiziert
        - (False, "Fehlermeldung") wenn nicht gefunden oder Fehler
    """
    uid = uid.strip()
    if not uid:
        return False, "Bitte gib deine LeveX UID ein."

    if not AFFILIATE_API_KEY or not AFFILIATE_API_SECRET:
        # Fallback: UID speichern ohne Verifizierung (Keys fehlen)
        logger.warning("[AFFILIATE] Keys fehlen — UID wird ohne Verifizierung gespeichert")
        return True, "OK"

    client_ids = _get_cached_client_ids()

    if not client_ids:
        # API nicht erreichbar — trotzdem durchlassen mit Warning
        logger.warning("[AFFILIATE] Keine Affiliate-Daten verfuegbar — UID wird ohne Verifizierung gespeichert")
        return True, "OK"

    if uid in client_ids:
        logger.info(f"[AFFILIATE] UID {uid} verifiziert ✓")
        return True, "OK"

    logger.info(f"[AFFILIATE] UID {uid} NICHT in Affiliate-Liste gefunden")
    return False, (
        "Diese UID wurde nicht als Affiliate gefunden. "
        "Bitte stelle sicher, dass du dich über den Affiliate-Link von FirstClass Trading "
        "bei LeveX registriert hast. Deine UID findest du in deinem LeveX Dashboard unter Einstellungen."
    )
