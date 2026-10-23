"""
(C) rest_client.py — REST API Client fuer die Levex Perpetual API

Stellt HTTP-Requests an die Levex REST API mit HMAC-SHA256 Authentifizierung.
Wird von der Execution Engine genutzt um Orders auf Kunden-Accounts zu platzieren.
"""

import time
import json
import hmac
import hashlib
from urllib.parse import urlencode
from typing import Any

import aiohttp

from logger_setup import logger


class LevexRESTClient:
    """Async REST Client fuer die Levex API."""

    def __init__(self, base_url: str, api_key: str, api_secret: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._api_secret = api_secret
        self._session: aiohttp.ClientSession | None = None

    # --------------------------------------------------------------------------
    # SESSION MANAGEMENT
    # --------------------------------------------------------------------------

    async def _get_session(self) -> aiohttp.ClientSession:
        """Lazy Session erstellen."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def close(self) -> None:
        """Session sauber schliessen."""
        if self._session and not self._session.closed:
            await self._session.close()

    # --------------------------------------------------------------------------
    # AUTHENTIFIZIERUNG
    # --------------------------------------------------------------------------

    def _sign(self, path: str, query: str = "", body: str = "") -> str:
        """
        HMAC-SHA256 Signatur erstellen.
        Format: path + (query ? "?" + query : "") + body
        """
        sign_content = path
        if query:
            sign_content += "?" + query
        if body:
            sign_content += body

        signature = hmac.new(
            self._api_secret.encode("utf-8"),
            sign_content.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

        return signature

    def _add_expiry(self, params: dict) -> dict:
        """requestExpiry zu Query/Body hinzufuegen (60 Sekunden ab jetzt)."""
        params["requestExpiry"] = str(int(time.time() * 1000) + 60_000)
        return params

    # --------------------------------------------------------------------------
    # HTTP METHODEN
    # --------------------------------------------------------------------------

    async def _request(
        self,
        method: str,
        path: str,
        params: dict | None = None,
        body: dict | None = None,
    ) -> dict:
        """
        Generischer API Request mit Authentifizierung.
        Returns: API Response als dict
        Raises: Exception bei HTTP oder API Fehlern
        """
        session = await self._get_session()
        params = params or {}
        params = self._add_expiry(params)

        query_string = urlencode(params) if params else ""
        body_string = json.dumps(body) if body else ""

        signature = self._sign(path, query_string, body_string)

        headers = {
            "X-LX-APIKEY": self._api_key,
            "X-LX-SIGNATURE": signature,
            "Content-Type": "application/json",
        }

        url = f"{self._base_url}{path}"
        if query_string:
            url += "?" + query_string

        logger.debug(f"REST {method} {path} | Query: {query_string[:100]}")

        try:
            async with session.request(
                method, url, headers=headers,
                data=body_string if body_string else None,
            ) as resp:
                response_text = await resp.text()
                logger.debug(f"REST Response [{resp.status}]: {response_text[:500]}")

                if resp.status != 200:
                    logger.error(f"REST HTTP Error {resp.status}: {response_text}")
                    return {"error": {"code": resp.status, "message": response_text}}

                result = json.loads(response_text)

                if result.get("error"):
                    err = result["error"]
                    logger.error(f"REST API Error: [{err.get('code')}] {err.get('message')}")

                return result

        except aiohttp.ClientError as e:
            logger.error(f"REST Client Error: {e}")
            return {"error": {"code": -1, "message": str(e)}}

    async def get(self, path: str, params: dict | None = None) -> dict:
        return await self._request("GET", path, params=params)

    async def post(self, path: str, params: dict | None = None, body: dict | None = None) -> dict:
        return await self._request("POST", path, params=params, body=body)

    async def delete(self, path: str, params: dict | None = None) -> dict:
        return await self._request("DELETE", path, params=params)

    # --------------------------------------------------------------------------
    # ORDER ENDPOINTS
    # --------------------------------------------------------------------------

    async def place_order(
        self,
        symbol: str,
        side: str,
        pos_side: str,
        order_qty: str,
        ord_type: str = "Market",
        price: str | None = None,
        leverage: str | None = None,
        position_id: str | None = None,
        stop_loss: str | None = None,
        take_profit: str | None = None,
        stop_price: str | None = None,
        reduce_only: bool = False,
        time_in_force: str = "GoodTillCancel",
        cl_ord_id: str | None = None,
    ) -> dict:
        """
        Order auf einem Kunden-Account platzieren.
        Nutzt den Copy Trading Endpoint.
        """
        body: dict[str, Any] = {
            "symbol": symbol,
            "side": side,
            "posSide": pos_side,
            "orderQty": order_qty,
            "ordType": ord_type,
            "timeInForce": time_in_force,
            "reduceOnly": reduce_only,
        }

        if price:
            body["price"] = price
        if leverage:
            body["leverage"] = leverage
        if position_id:
            body["positionID"] = position_id
        if stop_loss:
            body["stopLoss"] = stop_loss
        if take_profit:
            body["takeProfit"] = take_profit
        if stop_price:
            body["stopPrice"] = stop_price
        if cl_ord_id:
            body["clOrdID"] = cl_ord_id

        logger.info(
            f"[REST] Order platzieren: {side} {symbol} | Qty: {order_qty} | "
            f"Typ: {ord_type} | Preis: {price or 'Market'} | posSide: {pos_side}"
        )
        logger.info(f"[REST] Body: {json.dumps(body)}")

        result = await self.post(
            "/api/service-perpetual/order/copy-affiliate-order",
            body=body,
        )

        if not result.get("error"):
            # API gibt Daten direkt im Root zurueck, nicht unter "result"
            order_id = result.get("orderID", result.get("result", {}).get("orderID", "?") if isinstance(result.get("result"), dict) else "?")
            logger.info(f"[REST] Order erfolgreich: OrderID {order_id}")
        else:
            logger.error(f"[REST] Order fehlgeschlagen: {result.get('error')}")

        return result

    async def cancel_order(
        self,
        symbol: str,
        pos_side: str,
        order_id: str | None = None,
        position_id: str | None = None,
    ) -> dict:
        """Order stornieren."""
        params: dict[str, str] = {
            "symbol": symbol,
            "posSide": pos_side,
        }
        if order_id:
            params["orderID"] = order_id
        if position_id:
            params["positionID"] = position_id

        logger.info(f"[REST] Order stornieren: {symbol} | OrderID: {order_id}")
        return await self.delete("/api/perpetual/orders", params=params)

    async def cancel_all_orders(self, symbol: str | None = None) -> dict:
        """Alle Orders stornieren."""
        params: dict[str, str] = {}
        if symbol:
            params["symbol"] = symbol
        params["cancelAllOrdType"] = "true"

        logger.info(f"[REST] Alle Orders stornieren: {symbol or 'alle Symbole'}")
        return await self.delete("/api/perpetual/orders/cancel-all", params=params)

    async def close_all_positions(self, symbol: str | None = None) -> dict:
        """Alle Positionen schliessen."""
        params: dict[str, str] = {}
        if symbol:
            params["symbol"] = symbol

        logger.info(f"[REST] Alle Positionen schliessen: {symbol or 'alle Symbole'}")
        return await self.delete("/api/perpetual/orders/all-positions", params=params)

    async def get_active_orders(self, symbol: str) -> dict:
        """Aktive Orders abfragen."""
        return await self.get("/api/perpetual/orders/active-all", params={"symbol": symbol})

    # --------------------------------------------------------------------------
    # POSITION ENDPOINTS
    # --------------------------------------------------------------------------

    async def set_leverage(
        self,
        symbol: str,
        leverage: str,
        margin_mode: str = "Isolated",
    ) -> dict:
        """Leverage aendern."""
        body = {
            "symbol": symbol,
            "marginMode": margin_mode,
            "longLeverage": leverage,
            "shortLeverage": leverage,
        }
        logger.info(f"[REST] Leverage setzen: {symbol} | {leverage}x | {margin_mode}")
        return await self.post("/api/perpetual/positions/leverage", body=body)

    async def change_margin(
        self,
        position_id: str,
        symbol: str,
        pos_side: str,
        change_amount: float,
    ) -> dict:
        """Margin anpassen."""
        body = {
            "positionID": position_id,
            "symbol": symbol,
            "posSide": pos_side,
            "changeAmount": change_amount,
        }
        logger.info(f"[REST] Margin anpassen: {symbol} | PosID: {position_id} | {change_amount:+f}")
        return await self.post("/api/perpetual/positions/margin", body=body)

    async def rename_position(
        self,
        position_id: str,
        symbol: str,
        pos_side: str,
        display_name: str,
    ) -> dict:
        """Position umbenennen."""
        body = {
            "positionID": position_id,
            "symbol": symbol,
            "posSide": pos_side,
            "displayName": display_name,
        }
        logger.info(f"[REST] Position umbenennen: {symbol} | PosID: {position_id[:8]}... | -> '{display_name}'")
        return await self.post("/api/perpetual/positions/display-name", body=body)

    async def set_trading_stop(
        self,
        position_id: str,
        symbol: str,
        pos_side: str,
        stop_loss: str | None = None,
        take_profit: str | None = None,
    ) -> dict:
        """SL/TP auf bestehender Position setzen/aendern."""
        body = {
            "positionID": position_id,
            "symbol": symbol,
            "posSide": pos_side,
        }
        if stop_loss is not None:
            body["stopLoss"] = stop_loss
        if take_profit is not None:
            body["takeProfit"] = take_profit
        label_parts = []
        if stop_loss:
            label_parts.append(f"SL={stop_loss}")
        if take_profit:
            label_parts.append(f"TP={take_profit}")
        logger.info(f"[REST] Trading-Stop setzen: {symbol} | PosID: {position_id[:8]}... | {', '.join(label_parts)}")
        return await self.post("/api/service-perpetual/positions/trading-stop", body=body)

    async def switch_position_mode(self, symbol: str, target_mode: str) -> dict:
        """Position-Modus wechseln (Hedged/OneWay/Multi)."""
        body = {
            "symbol": symbol,
            "targetPosMode": target_mode,
        }
        logger.info(f"[REST] Position-Modus wechseln: {symbol} | -> {target_mode}")
        return await self.post("/api/perpetual/positions/switch-pos-mode", body=body)
