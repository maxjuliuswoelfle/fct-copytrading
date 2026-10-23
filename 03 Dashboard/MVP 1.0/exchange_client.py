"""
(C) exchange_client.py — Leichtgewichtiger Exchange API Client fuer das Dashboard

Read-Only Zugriff auf die Levex API:
- Kunden-Balance abfragen (via Read API Key)
- Aktuelle Marktpreise abfragen (oeffentlich, kein Auth noetig)

Nutzt httpx fuer sync HTTP-Requests (Dashboard laeuft in FastAPI sync context).
"""

import time
import hmac
import hashlib
import os
import logging
from urllib.parse import urlencode
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Exchange REST URL — gleiche wie Bot
REST_URL = os.environ.get("LEVEX_REST_URL", "https://api.levex.com")

# Cache fuer Ticker-Preise (max 5 Sekunden alt)
_ticker_cache: dict[str, tuple[float, float]] = {}  # symbol -> (price, timestamp)
TICKER_CACHE_TTL = 5  # Sekunden


def _sign(api_secret: str, path: str, query: str = "") -> str:
    """HMAC-SHA256 Signatur erstellen."""
    sign_content = path
    if query:
        sign_content += "?" + query
    return hmac.new(
        api_secret.encode("utf-8"),
        sign_content.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _authenticated_get(api_key: str, api_secret: str, path: str, params: dict | None = None) -> dict:
    """Authentifizierter GET Request an die Levex API."""
    params = params or {}
    params["requestExpiry"] = str(int(time.time() * 1000) + 60_000)
    query_string = urlencode(params)
    signature = _sign(api_secret, path, query_string)

    headers = {
        "X-LX-APIKEY": api_key,
        "X-LX-SIGNATURE": signature,
        "Content-Type": "application/json",
    }

    url = f"{REST_URL}{path}?{query_string}"
    try:
        resp = httpx.get(url, headers=headers, timeout=10)
        raw_text = resp.text
        logger.warning(f"API {path} -> HTTP {resp.status_code}, Raw: {raw_text[:500]}")

        if not raw_text or not raw_text.strip():
            logger.warning(f"API {path} -> Leere Response (HTTP {resp.status_code})")
            return {"error": {"code": resp.status_code, "message": "Empty response"}}

        data = resp.json()
        return data
    except Exception as e:
        logger.error(f"API {path} -> Exception: {e}")
        return {"error": {"code": -1, "message": str(e)}}


def _get_perp_account_data(api_key: str, api_secret: str) -> dict | None:
    """
    Perpetual Account Daten abfragen (Balance + Positionen).

    Nutzt /api/perpetual/accounts/positions mit currency=USDT.
    Cached das Ergebnis damit Balance und Positions nicht doppelt abfragen.
    """
    result = _authenticated_get(
        api_key, api_secret,
        "/api/perpetual/accounts/positions",
        params={"currency": "USDT"},
    )

    if result.get("error"):
        logger.warning(f"Perp Account -> Error: {result['error']}")
        return None

    logger.warning(f"Perp Account -> Erfolg: {str(result)[:800]}")
    return result


# Cache fuer Account-Daten (pro API-Key, max 8 Sekunden)
_account_cache: dict[str, tuple[dict | None, float]] = {}
ACCOUNT_CACHE_TTL = 8


def _get_cached_account(api_key: str, api_secret: str) -> dict | None:
    """Account-Daten mit Cache abfragen (vermeidet doppelte API-Calls)."""
    now = time.time()
    if api_key in _account_cache:
        cached_data, cached_time = _account_cache[api_key]
        if now - cached_time < ACCOUNT_CACHE_TTL:
            return cached_data

    data = _get_perp_account_data(api_key, api_secret)
    _account_cache[api_key] = (data, now)
    return data


def get_customer_balance(api_key: str, api_secret: str) -> float | None:
    """
    Kunden-Balance (Perpetual Wallet) abfragen.

    Strategie:
    1. /api/perpetual/accounts/positions?currency=USDT (Perpetual Balance)
    2. /api/spot/wallet als Fallback (Spot Balance)
    """
    # 1. Perpetual Account abfragen
    result = _get_cached_account(api_key, api_secret)
    if result is not None:
        # Balance aus Account-Daten extrahieren
        data = result.get("result", result) if isinstance(result, dict) else result

        # Direkt im Result-Objekt suchen
        if isinstance(data, dict):
            for key in ("accountBalance", "walletBalance", "availableBalance", "balance"):
                val = data.get(key)
                if val is not None:
                    logger.warning(f"Balance gefunden (Perp, Key: {key}): {val}")
                    return float(val)

            # Vielleicht in einem Account-Unterobjekt
            for sub_key in ("account", "wallet"):
                sub = data.get(sub_key)
                if isinstance(sub, dict):
                    for key in ("accountBalance", "walletBalance", "availableBalance", "balance"):
                        val = sub.get(key)
                        if val is not None:
                            logger.warning(f"Balance gefunden (Perp, {sub_key}.{key}): {val}")
                            return float(val)

        # Liste durchsuchen
        items = data if isinstance(data, list) else []
        for item in items:
            if isinstance(item, dict):
                for key in ("accountBalance", "walletBalance", "availableBalance", "balance"):
                    val = item.get(key)
                    if val is not None:
                        logger.warning(f"Balance gefunden (Perp, Liste, Key: {key}): {val}")
                        return float(val)

    # 2. Spot Wallet als Fallback
    spot_result = _authenticated_get(api_key, api_secret, "/api/spot/wallet")
    if not spot_result.get("error"):
        inner = spot_result.get("result", {})
        if isinstance(inner, dict) and "rows" in inner:
            for row in inner["rows"]:
                if isinstance(row, dict):
                    bal = row.get("balance")
                    if bal is not None:
                        logger.warning(f"Balance gefunden (Spot Fallback): {bal}")
                        return float(bal)

    logger.warning("Balance: Kein Endpoint hat eine Balance zurueckgegeben")
    return None


def get_customer_positions(api_key: str, api_secret: str) -> list[dict]:
    """
    Aktive Positionen des Kunden von der Exchange abfragen.

    Nutzt den gleichen Endpoint wie Balance (/api/perpetual/accounts/positions).
    Gibt Liste von Positionen mit unrealisiertem P&L zurueck.
    """
    result = _get_cached_account(api_key, api_secret)
    if result is None:
        return []

    # Positionen aus Response extrahieren
    data = result.get("result", result) if isinstance(result, dict) else result

    # Positionen koennen unter verschiedenen Keys liegen
    positions = []
    if isinstance(data, dict):
        positions = data.get("positions", data.get("rows", []))
        if not isinstance(positions, list):
            positions = []
        # Falls die Positionen direkt im Result sind (Liste von Position-Objekten)
        if not positions and isinstance(data, dict):
            # Vielleicht ist data selbst eine Position? Dann in Liste packen
            if "symbol" in data:
                positions = [data]
    elif isinstance(data, list):
        positions = data

    logger.warning(f"Positions: {len(positions)} Eintraege gefunden")

    active = []
    for p in positions:
        if not isinstance(p, dict):
            continue
        size = float(p.get("size", 0) or 0)
        if size > 0:
            active.append({
                "symbol": p.get("symbol", ""),
                "side": p.get("side", ""),
                "size": size,
                "entry_price": float(p.get("avgEntryPrice", 0) or 0),
                "mark_price": float(p.get("markPrice", 0) or 0),
                "liq_price": float(p.get("liqPrice", 0) or 0),
                "unrealised_pnl": float(p.get("unrealisedPnl", 0) or 0),
                "leverage": float(p.get("leverage", 0) or 0),
                "position_id": p.get("positionID", ""),
            })

    return active


def get_ticker_price(symbol: str) -> float | None:
    """
    Aktuellen Marktpreis fuer ein Symbol abfragen (oeffentlich, kein Auth).

    Cached fuer TICKER_CACHE_TTL Sekunden um API-Limits zu vermeiden.
    """
    now = time.time()

    # Cache check
    if symbol in _ticker_cache:
        cached_price, cached_time = _ticker_cache[symbol]
        if now - cached_time < TICKER_CACHE_TTL:
            return cached_price

    try:
        url = f"{REST_URL}/api/perpetual/market/tickers?symbol={symbol}"
        resp = httpx.get(url, timeout=10)
        data = resp.json()

        # Verschiedene Response-Formate abfangen
        tickers = data if isinstance(data, list) else data.get("result", data)

        if isinstance(tickers, list) and tickers:
            price = float(tickers[0].get("lastPrice", 0) or 0)
        elif isinstance(tickers, dict):
            price = float(tickers.get("lastPrice", 0) or 0)
        else:
            return None

        if price > 0:
            _ticker_cache[symbol] = (price, now)
            return price

    except Exception:
        pass

    return None


def get_multiple_ticker_prices(symbols: list[str]) -> dict[str, float]:
    """Aktuelle Preise fuer mehrere Symbole abfragen."""
    prices = {}
    for symbol in set(symbols):
        price = get_ticker_price(symbol)
        if price is not None:
            prices[symbol] = price
    return prices


def get_btc_price() -> float | None:
    """Aktuellen BTC-Preis abfragen (fuer Benchmark)."""
    # Versuche gaengige BTC-Symbol-Namen
    for symbol in ("BTCUSDT", "BTC-PERP", "BTCUSD"):
        price = get_ticker_price(symbol)
        if price:
            return price
    return None
