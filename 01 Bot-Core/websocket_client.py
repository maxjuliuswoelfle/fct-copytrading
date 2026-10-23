"""
(C) websocket_client.py — WebSocket-Verbindung zur Levex API

Verwaltet die komplette WebSocket-Lifecycle:
- Verbindungsaufbau
- Authentifizierung (HMAC-SHA256)
- Subscription auf perpAccount (Orders, Positions, Account)
- Heartbeat (alle 5 Sekunden)
- Auto-Reconnect mit exponentiellem Backoff
- Callback-Pattern fuer geparste Nachrichten
"""

import asyncio
import json
from typing import Callable, Any

import websockets
from websockets.asyncio.client import ClientConnection

from config import config
from auth import create_ws_auth_params
from logger_setup import logger
from bot_types import (
    PERP_ORDER_KEYS,
    PERP_FILL_KEYS,
    PERP_POSITION_KEYS,
    PERP_ACCOUNT_KEYS,
    PerpOrder,
    PerpFill,
    PerpPosition,
    PerpAccount,
)


# ============================================================================
# HILFSFUNKTIONEN
# ============================================================================

def map_array_to_object(keys: list[str], values: list, cls: type) -> Any:
    """
    Mappt ein Array von Werten auf ein Objekt anhand eines Keys-Arrays.
    Levex sendet Daten als Arrays (platzsparend) — wir wandeln sie in lesbare Objekte um.

    Nur Felder die im Dataclass definiert sind werden uebernommen — Extra-Felder ignoriert.
    Beispiel: keys = ["a", "b"], values = ["1", "2"] -> cls(a="1", b="2")
    """
    import dataclasses
    valid_fields = {f.name for f in dataclasses.fields(cls)}
    kwargs = {}
    for i in range(min(len(keys), len(values))):
        if keys[i] in valid_fields:
            kwargs[keys[i]] = str(values[i]) if values[i] is not None else ""
    return cls(**kwargs)


# ============================================================================
# LEVEX WEBSOCKET CLASS
# ============================================================================

class LevexWebSocket:
    """Async WebSocket Client fuer die Levex API."""

    def __init__(self) -> None:
        self._ws: ClientConnection | None = None
        self._message_id: int = 0
        self._is_connected: bool = False
        self._is_authenticated: bool = False
        self._should_reconnect: bool = True
        self._reconnect_delay: float = 1.0      # Startet bei 1 Sekunde
        self._max_reconnect_delay: float = 30.0  # Maximal 30 Sekunden
        self._heartbeat_task: asyncio.Task | None = None
        self._receive_task: asyncio.Task | None = None
        self._last_message_time: float = 0.0     # Letzter Empfangszeitpunkt
        self._stale_timeout: float = 30.0        # Sekunden ohne Message = stale

        # Callbacks — werden von aussen gesetzt
        self._on_perp_order: Callable | None = None
        self._on_perp_position: Callable | None = None
        self._on_perp_account: Callable | None = None
        self._on_perp_ticker: Callable | None = None
        self._on_reconnect: Callable | None = None

    # --------------------------------------------------------------------------
    # CALLBACK REGISTRIERUNG
    # --------------------------------------------------------------------------

    def on_perp_order(self, callback: Callable) -> None:
        """Callback fuer perpOrder.update Events."""
        self._on_perp_order = callback

    def on_perp_position(self, callback: Callable) -> None:
        """Callback fuer perpPosition.update Events."""
        self._on_perp_position = callback

    def on_perp_account(self, callback: Callable) -> None:
        """Callback fuer perpAccount.update Events."""
        self._on_perp_account = callback

    def on_perp_ticker(self, callback: Callable) -> None:
        """Callback fuer perpTicker.update Events (oeffentliche Marktdaten)."""
        self._on_perp_ticker = callback

    def on_reconnect(self, callback: Callable) -> None:
        """Callback bei Reconnect (wird aufgerufen bevor Reconnect startet)."""
        self._on_reconnect = callback

    # --------------------------------------------------------------------------
    # VERBINDUNG
    # --------------------------------------------------------------------------

    async def connect(self) -> None:
        """
        Verbindung zum Levex WebSocket herstellen.
        Nach erfolgreicher Verbindung wird automatisch authentifiziert und subscribed.
        Reconnect-Loop laeuft bis disconnect() aufgerufen wird.
        """
        self._should_reconnect = True

        while self._should_reconnect:
            try:
                logger.info(f"Verbinde mit Levex WebSocket: {config.ws_url}")
                self._ws = await websockets.connect(config.ws_url)
                self._is_connected = True
                self._reconnect_delay = 1.0  # Backoff zuruecksetzen

                logger.info("WebSocket Verbindung hergestellt")
                await self._authenticate()

                # Heartbeat starten
                self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

                # Nachrichten empfangen bis Verbindung abbricht
                await self._receive_loop()

            except websockets.exceptions.ConnectionClosed as e:
                logger.warning(
                    f"WebSocket geschlossen: Code {e.code}, Grund: {e.reason}"
                )
            except (OSError, websockets.exceptions.WebSocketException) as e:
                logger.error(f"WebSocket Fehler: {e}")
            except Exception as e:
                logger.error(f"Unerwarteter Fehler: {e}")
            finally:
                self._cleanup()

            # Reconnect mit exponentiellem Backoff
            if self._should_reconnect:
                logger.info(
                    f"Reconnect in {self._reconnect_delay:.0f} Sekunden..."
                )
                if self._on_reconnect:
                    try:
                        self._on_reconnect(f"Reconnect in {self._reconnect_delay:.0f}s")
                    except Exception:
                        pass
                await asyncio.sleep(self._reconnect_delay)
                # Exponentieller Backoff, maximal 30 Sekunden
                self._reconnect_delay = min(
                    self._reconnect_delay * 2, self._max_reconnect_delay
                )

    def disconnect(self) -> None:
        """Verbindung sauber trennen (kein Reconnect)."""
        logger.info("WebSocket wird getrennt (manuell)")
        self._should_reconnect = False
        self._cleanup()

    # --------------------------------------------------------------------------
    # AUTHENTIFIZIERUNG
    # --------------------------------------------------------------------------

    async def _authenticate(self) -> None:
        """Authentifizierung ueber HMAC-SHA256 Signatur."""
        auth_params = create_ws_auth_params(config.api_key, config.api_secret)

        auth_message = {
            "id": self._next_id(),
            "method": "user.auth",
            "params": {
                "apiKey": auth_params["apiKey"],
                "signature": auth_params["signature"],
                "expiry": auth_params["expiry"],
            },
        }

        logger.debug("Sende Authentifizierung...")
        await self._send(auth_message)

    # --------------------------------------------------------------------------
    # SUBSCRIPTION
    # --------------------------------------------------------------------------

    async def _subscribe_perp_account(self) -> None:
        """
        Auf perpAccount subscriben — damit bekommen wir alle Trade-Events des Master-Accounts.
        """
        subscribe_message = {
            "id": self._next_id(),
            "method": "perpAccount.subscribe",
            "params": {
                "account": True,
                "position": True,
                "order": True,
                "positionInfo": True,
                "historyLimit": 0,
                "allPositions": True,
            },
        }

        logger.info("Subscribing auf perpAccount (Orders, Positions, Account)...")
        await self._send(subscribe_message)

    async def subscribe_ticker(self, symbols: list[str]) -> None:
        """
        Auf oeffentliche Ticker-Daten subscriben fuer Echtzeit-Preise.
        Liefert lastPrice, markPrice, etc. fuer jedes Symbol.
        """
        if not symbols:
            return
        subscribe_message = {
            "id": self._next_id(),
            "method": "perpTicker.subscribe",
            "params": symbols,
        }
        logger.info(f"Subscribing auf perpTicker: {symbols}")
        await self._send(subscribe_message)

    # --------------------------------------------------------------------------
    # HEARTBEAT
    # --------------------------------------------------------------------------

    async def _heartbeat_loop(self) -> None:
        """
        Heartbeat — alle 5 Sekunden:
        - server.ping senden
        - Stale-Detection: Wenn > 30 Sek keine Nachricht → Force Reconnect
        - Alle 60 Sekunden Health-Log
        """
        import time
        logger.debug("Heartbeat gestartet (alle 5 Sekunden)")
        health_counter = 0
        try:
            while self._is_connected:
                await asyncio.sleep(5)
                health_counter += 1

                if self._is_connected and self._ws:
                    # Ping senden
                    await self._send({
                        "id": self._next_id(),
                        "method": "server.ping",
                        "params": {},
                    })

                    # Stale-Detection: Keine Nachricht seit > 30 Sekunden?
                    if self._last_message_time > 0:
                        silence = time.time() - self._last_message_time
                        if silence > self._stale_timeout:
                            logger.warning(
                                f"[HEALTH] Keine Nachricht seit {silence:.0f}s — "
                                f"Force Reconnect"
                            )
                            if self._ws:
                                await self._ws.close()
                            break

                    # Health-Log alle 60 Sekunden (12 × 5s)
                    if health_counter >= 12:
                        health_counter = 0
                        since_last = time.time() - self._last_message_time
                        logger.info(
                            f"[HEALTH] Bot alive | Letzte Nachricht vor {since_last:.0f}s"
                        )
        except asyncio.CancelledError:
            pass

    # --------------------------------------------------------------------------
    # NACHRICHTENVERARBEITUNG
    # --------------------------------------------------------------------------

    async def _receive_loop(self) -> None:
        """Eingehende Nachrichten empfangen und verarbeiten."""
        import time
        if not self._ws:
            return

        self._last_message_time = time.time()

        async for raw_message in self._ws:
            self._last_message_time = time.time()
            try:
                message = json.loads(raw_message)
            except json.JSONDecodeError:
                logger.error(f"Konnte Nachricht nicht parsen: {raw_message}")
                continue

            # Debug: Alle Nachrichten loggen (voll, nicht abgeschnitten)
            logger.debug(f"WS Nachricht: {json.dumps(message)}")

            # Response auf einen Request (hat eine ID)
            if "id" in message:
                await self._handle_response(message)
                continue

            # Push-Nachrichten (kein ID-Feld) — Levex nutzt "method" Feld
            msg_method = message.get("method")
            if not msg_method:
                continue

            match msg_method:
                case "perpOrder.update":
                    self._handle_perp_order_update(message.get("data"))
                case "perpPosition.update":
                    self._handle_perp_position_update(message.get("data"))
                case "perpAccount.update":
                    self._handle_perp_account_update(message.get("data"))
                case "perpTicker.update":
                    self._handle_perp_ticker_update(message.get("data"))
                case _:
                    logger.debug(f"Unbekannter Push-Typ: {msg_method}")

    async def _handle_response(self, message: dict) -> None:
        """Responses auf unsere Requests verarbeiten (Auth, Subscribe, Ping)."""
        # Fehler?
        if "error" in message and message["error"]:
            err = message["error"]
            logger.error(
                f"API Fehler (ID {message.get('id')}): [{err.get('code')}] {err.get('message')}"
            )
            if not self._is_authenticated:
                logger.error("Authentifizierung fehlgeschlagen — pruefen API Keys")
            return

        # Auth-Response erkennen (erste Response nach Connect)
        if not self._is_authenticated and "result" in message:
            self._is_authenticated = True
            logger.info("Authentifizierung erfolgreich")
            await self._subscribe_perp_account()
            return

        # Alles andere (Subscribe-Bestaetigung, Pong etc.)
        logger.debug(
            f"Response (ID {message.get('id')}): {json.dumps(message.get('result'))}"
        )

    # --------------------------------------------------------------------------
    # PUSH-HANDLER — Arrays zu Objekten mappen und Callbacks aufrufen
    # --------------------------------------------------------------------------

    def _handle_perp_order_update(self, data: Any) -> None:
        """perpOrder.update verarbeiten."""
        if not data or not self._on_perp_order:
            return

        # Keys aus der Nachricht verwenden falls vorhanden, sonst unsere Konstanten
        order_keys = data.get("orderKeys") or PERP_ORDER_KEYS
        fill_keys = data.get("fillKeys") or PERP_FILL_KEYS

        # Debug: Vollstaendige Keys loggen (einmalig)
        logger.debug(f"orderKeys von API: {order_keys}")
        logger.debug(f"fillKeys von API: {fill_keys}")

        # Debug: Erstes open/closed Order-Array roh loggen
        for row in (data.get("open") or [])[:1]:
            logger.debug(f"RAW open order: {row}")
        for row in (data.get("closed") or [])[:1]:
            logger.debug(f"RAW closed order: {row}")

        open_orders = [
            map_array_to_object(order_keys, row, PerpOrder)
            for row in (data.get("open") or [])
        ]
        closed_orders = [
            map_array_to_object(order_keys, row, PerpOrder)
            for row in (data.get("closed") or [])
        ]
        fills = [
            map_array_to_object(fill_keys, row, PerpFill)
            for row in (data.get("fills") or [])
        ]

        self._on_perp_order({
            "open": open_orders,
            "closed": closed_orders,
            "fills": fills,
            "_type": data.get("type", "incremental"),  # snapshot | incremental
        })

    def _handle_perp_position_update(self, data: Any) -> None:
        """perpPosition.update verarbeiten."""
        if not data or not self._on_perp_position:
            return

        keys = data.get("keys") or PERP_POSITION_KEYS
        # Levex sendet Position-Daten in "positions", nicht "data"
        rows = data.get("positions") or data.get("data") or []
        positions = [
            map_array_to_object(keys, row, PerpPosition)
            for row in rows
        ]

        self._on_perp_position({
            "positions": positions,
            "_type": data.get("type", "incremental"),
        })

    def _handle_perp_account_update(self, data: Any) -> None:
        """perpAccount.update verarbeiten."""
        if not data or not self._on_perp_account:
            return

        keys = data.get("keys") or PERP_ACCOUNT_KEYS
        # Levex sendet Account-Daten in "accounts", nicht "data"
        rows = data.get("accounts") or data.get("data") or []
        accounts = [
            map_array_to_object(keys, row, PerpAccount)
            for row in rows
        ]

        self._on_perp_account({
            "accounts": accounts,
            "_type": data.get("type", "incremental"),
        })

    def _handle_perp_ticker_update(self, data: Any) -> None:
        """perpTicker.update verarbeiten — oeffentliche Marktdaten."""
        if not data or not self._on_perp_ticker:
            return
        self._on_perp_ticker(data)

    # --------------------------------------------------------------------------
    # HILFSFUNKTIONEN
    # --------------------------------------------------------------------------

    async def _send(self, message: dict) -> None:
        """Nachricht senden (JSON-serialisiert)."""
        if self._ws:
            try:
                await self._ws.send(json.dumps(message))
            except websockets.exceptions.ConnectionClosed:
                logger.warning("Kann nicht senden — WebSocket ist nicht verbunden")
        else:
            logger.warning("Kann nicht senden — WebSocket ist nicht verbunden")

    def _next_id(self) -> int:
        """Naechste inkrementelle Message-ID."""
        self._message_id += 1
        return self._message_id

    def _cleanup(self) -> None:
        """Aufraeumen — Heartbeat stoppen, Flags zuruecksetzen."""
        self._is_connected = False
        self._is_authenticated = False
        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            self._heartbeat_task = None
        if self._ws:
            try:
                asyncio.get_event_loop().create_task(self._ws.close())
            except Exception:
                pass
            self._ws = None
