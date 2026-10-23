"""
(C) customer_ws.py — WebSocket-Verbindung pro Kunde fuer Balance-Tracking

Jeder Kunde bekommt eine eigene, leichtgewichtige WebSocket-Verbindung
ueber seinen Futures Read API-Key. Trackt in Echtzeit:
- Account-Balance (accountBalance, usedBalance)
- Offene Positionen (fuer spaetere Features)

Die Balance wird direkt im Customer-Objekt aktualisiert, sodass die
Scaling Engine immer den aktuellen Wert hat.
"""

import asyncio
import json
from typing import Any

import websockets
from websockets.asyncio.client import ClientConnection

from auth import create_ws_auth_params
from logger_setup import logger


class CustomerWebSocket:
    """
    WebSocket-Verbindung fuer einen einzelnen Kunden.

    Nutzt den Futures Read Key (nicht den Copy Trading Key).
    Subscribed nur auf perpAccount (Balance + Positionen).
    Heartbeat und Auto-Reconnect integriert.
    """

    def __init__(
        self,
        ws_url: str,
        customer_id: str,
        customer_name: str,
        api_key: str,
        api_secret: str,
    ) -> None:
        self._ws_url = ws_url
        self._customer_id = customer_id
        self._customer_name = customer_name
        self._api_key = api_key
        self._api_secret = api_secret

        self._ws: ClientConnection | None = None
        self._msg_id = 0
        self._running = False
        self._heartbeat_task: asyncio.Task | None = None

        # Live-Daten — werden von aussen gelesen
        self.balance: float = 0.0
        self.used_balance: float = 0.0
        self.free_balance: float = 0.0

    # --------------------------------------------------------------------------
    # LIFECYCLE
    # --------------------------------------------------------------------------

    async def connect(self) -> bool:
        """Verbinden, authentifizieren, subscriben. Gibt True zurueck bei Erfolg."""
        try:
            self._ws = await websockets.connect(self._ws_url)

            # Auth
            auth_params = create_ws_auth_params(self._api_key, self._api_secret)
            await self._send({
                "method": "user.auth",
                "params": auth_params,
            })

            resp = await self._recv(timeout=5)
            if not resp or resp.get("error"):
                error = resp.get("error") if resp else "Timeout"
                logger.error(
                    f"[WS:{self._customer_name}] Auth fehlgeschlagen: {error}"
                )
                await self.disconnect()
                return False

            logger.info(f"[WS:{self._customer_name}] Verbunden + authentifiziert")

            # Subscribe auf Account (Balance)
            await self._send({
                "method": "perpAccount.subscribe",
                "params": {
                    "account": True,
                    "position": True,
                    "order": False,
                    "historyLimit": 0,
                },
            })

            self._running = True
            return True

        except Exception as e:
            logger.error(f"[WS:{self._customer_name}] Verbindungsfehler: {e}")
            return False

    async def disconnect(self) -> None:
        """Verbindung sauber trennen."""
        self._running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            self._heartbeat_task = None
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
            self._ws = None

    async def run(self) -> None:
        """
        Hauptloop — empfaengt Nachrichten und aktualisiert Balance.
        Laeuft als asyncio.Task im Hintergrund.
        Auto-Reconnect bei Verbindungsabbruch.
        """
        reconnect_delay = 1

        while True:
            if not self._running:
                success = await self.connect()
                if not success:
                    logger.warning(
                        f"[WS:{self._customer_name}] Reconnect in {reconnect_delay}s..."
                    )
                    await asyncio.sleep(reconnect_delay)
                    reconnect_delay = min(reconnect_delay * 2, 30)
                    continue
                reconnect_delay = 1
                # Heartbeat starten
                self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

            try:
                raw = await asyncio.wait_for(self._ws.recv(), timeout=15)
                msg = json.loads(raw)
                self._handle_message(msg)

            except asyncio.TimeoutError:
                # Kein Heartbeat-Timeout — einfach weiter warten
                continue

            except (websockets.ConnectionClosed, ConnectionError, OSError) as e:
                logger.warning(
                    f"[WS:{self._customer_name}] Verbindung verloren: {e}"
                )
                self._running = False
                if self._heartbeat_task:
                    self._heartbeat_task.cancel()
                    self._heartbeat_task = None

            except Exception as e:
                logger.error(
                    f"[WS:{self._customer_name}] Unerwarteter Fehler: {e}"
                )
                self._running = False

    # --------------------------------------------------------------------------
    # NACHRICHTENVERARBEITUNG
    # --------------------------------------------------------------------------

    def _handle_message(self, msg: dict[str, Any]) -> None:
        """Eingehende WebSocket-Nachricht verarbeiten."""
        method = msg.get("method", "")

        if method == "perpAccount.update":
            self._handle_account_update(msg.get("data", {}))
        elif method == "perpPosition.update":
            self._handle_position_update(msg.get("data", {}))
        # Andere Nachrichten (Responses, Heartbeats) ignorieren

    # Default-Keys fuer perpAccount (werden beim ersten Snapshot gesetzt)
    _account_keys: list[str] = []

    def _handle_account_update(self, data: dict[str, Any]) -> None:
        """Balance aktualisieren."""
        keys = data.get("keys", [])
        if keys:
            # Keys vom Snapshot merken fuer spaetere Updates ohne Keys
            self._account_keys = keys
            logger.debug(f"[WS:{self._customer_name}] Account-Keys: {keys}")
        else:
            keys = self._account_keys

        if not keys:
            logger.debug(f"[WS:{self._customer_name}] Account-Update ohne Keys — ignoriert")
            return

        for row in data.get("accounts", []):
            if not row:
                continue
            mapped = dict(zip(keys, row))

            logger.debug(f"[WS:{self._customer_name}] Account-Data: {mapped}")
            new_balance = float(mapped.get("accountBalance", 0))
            new_used = float(mapped.get("usedBalance", 0))
            new_free = new_balance - new_used

            # Ignoriere offensichtlich falsche Werte (0 wenn vorher > 0)
            if new_balance <= 0 and self.balance > 0:
                logger.debug(
                    f"[WS:{self._customer_name}] Balance 0 ignoriert "
                    f"(vorher {self.balance:.4f}) — wahrscheinlich partielles Update"
                )
                return

            if abs(new_balance - self.balance) > 0.001:
                logger.info(
                    f"[WS:{self._customer_name}] Balance: "
                    f"{self.balance:.4f} -> {new_balance:.4f} USDT "
                    f"(Free: {new_free:.4f})"
                )

            self.balance = new_balance
            self.used_balance = new_used
            self.free_balance = new_free

    def _handle_position_update(self, data: dict[str, Any]) -> None:
        """Position-Updates loggen (fuer spaetere Features)."""
        # Erstmal nur loggen wenn sich was aendert
        keys = data.get("keys", [])
        for row in data.get("positions", []):
            mapped = dict(zip(keys, row))
            size = float(mapped.get("size", 0))
            if size != 0:
                logger.debug(
                    f"[WS:{self._customer_name}] Position: "
                    f"{mapped.get('symbol')} | Size: {size} | "
                    f"Side: {mapped.get('side')}"
                )

    # --------------------------------------------------------------------------
    # HEARTBEAT
    # --------------------------------------------------------------------------

    async def _heartbeat_loop(self) -> None:
        """Alle 5 Sekunden einen Ping senden."""
        while self._running:
            try:
                await asyncio.sleep(5)
                if self._ws and self._running:
                    await self._send({"method": "server.ping", "params": []})
            except asyncio.CancelledError:
                break
            except Exception:
                break

    # --------------------------------------------------------------------------
    # HILFSFUNKTIONEN
    # --------------------------------------------------------------------------

    async def _send(self, msg: dict) -> None:
        """Nachricht senden mit auto-incrementing ID."""
        self._msg_id += 1
        msg["id"] = self._msg_id
        await self._ws.send(json.dumps(msg))

    async def _recv(self, timeout: float = 5) -> dict | None:
        """Nachricht empfangen mit Timeout."""
        try:
            raw = await asyncio.wait_for(self._ws.recv(), timeout=timeout)
            return json.loads(raw)
        except asyncio.TimeoutError:
            return None
