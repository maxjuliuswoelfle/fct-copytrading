"""
(C) execution.py — Execution Engine fuer den Copy Trading Bot

Nimmt ParsedEvents vom Parser und fuehrt sie auf Kunden-Accounts aus.
Verwaltet das Position-Mapping (Master -> Kunde) und skaliert proportional.

Sicherheit:
- Fehler bei einem Kunden blockieren NICHT andere Kunden
- Jede Aktion wird geloggt
- Position-Mapping wird persistent gehalten
"""

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING

from logger_setup import logger
from rest_client import LevexRESTClient
from scaling import ScalingEngine
from database import Database
from bot_types import BotAction, ParsedEvent
from telegram import TelegramAlert

if TYPE_CHECKING:
    from parser import OrderParser


# ============================================================================
# CUSTOMER
# ============================================================================

@dataclass
class Customer:
    """Ein Kunde dessen Trades gespiegelt werden."""
    id: str
    name: str
    api_key: str          # Copy Trading Key (Order-Execution)
    api_secret: str
    uid: str
    balance: float
    read_api_key: str = ""     # Futures Read Key (WebSocket Balance-Tracking)
    read_api_secret: str = ""
    active: bool = True
    client: LevexRESTClient | None = None


# ============================================================================
# POSITION MAPPING
# ============================================================================

@dataclass
class PositionMapping:
    """Zuordnung: Master-Position -> Kunden-Position."""
    master_position_id: str
    customer_id: str
    customer_position_id: str
    customer_order_id: str
    symbol: str
    side: str = ""


# ============================================================================
# EXECUTION ENGINE
# ============================================================================


def _pos_side_from_side(side: str) -> str:
    """Buy -> Long, Sell -> Short. Fuer Multi-Trade Modus."""
    return "Long" if side == "Buy" else "Short"


class ExecutionEngine:
    """
    Fuehrt geparste Events auf Kunden-Accounts aus.

    Flow:
    1. Parser erkennt Event (z.B. OPEN_TRADE)
    2. ExecutionEngine bekommt das Event
    3. Fuer jeden aktiven Kunden:
       a. Skaliert die Qty/Margin proportional
       b. Platziert die Order via REST API
       c. Speichert das Position-Mapping
    """

    def __init__(self, base_url: str, scaling: ScalingEngine, db: Database,
                 parser: "OrderParser | None" = None, telegram: TelegramAlert | None = None) -> None:
        self._base_url = base_url
        self._scaling = scaling
        self._db = db
        self._parser = parser
        self._telegram = telegram
        self._customers: dict[str, Customer] = {}
        self.master_balance: float = 0.0
        # Lock pro Symbol+Kunde um Race Conditions bei gleichzeitigem Open zu verhindern
        self._open_locks: dict[str, asyncio.Lock] = {}

    # --------------------------------------------------------------------------
    # KUNDEN-VERWALTUNG
    # --------------------------------------------------------------------------

    def add_customer(self, customer: Customer) -> None:
        """Kunden hinzufuegen und REST Client erstellen."""
        customer.client = LevexRESTClient(
            base_url=self._base_url,
            api_key=customer.api_key,
            api_secret=customer.api_secret,
        )
        self._customers[customer.id] = customer
        logger.info(
            f"Kunde hinzugefuegt: {customer.name} (UID: {customer.uid}) | "
            f"Balance: {customer.balance} USDT"
        )

    def get_active_customers(self) -> list[Customer]:
        """Alle aktiven Kunden zurueckgeben.
        Liest is_active aus der DB, damit Dashboard-Pause sofort greift."""
        try:
            db_customers = {c["id"]: c for c in self._db.get_active_customers()}
            for cid, customer in self._customers.items():
                customer.active = cid in db_customers
        except Exception:
            pass  # Fallback: In-Memory Status nutzen
        return [c for c in self._customers.values() if c.active]

    def _get_open_lock(self, symbol: str, customer_id: str) -> asyncio.Lock:
        """Lock fuer ein Symbol+Kunde Paar holen (oder erstellen)."""
        key = f"{symbol}:{customer_id}"
        if key not in self._open_locks:
            self._open_locks[key] = asyncio.Lock()
        return self._open_locks[key]

    # --------------------------------------------------------------------------
    # EVENT VERARBEITUNG
    # --------------------------------------------------------------------------

    # Actions die neues Geld in den Markt bringen → nur fuer aktive Kunden
    _OPEN_ACTIONS = {
        BotAction.OPEN_TRADE,
        BotAction.TRADE_FILLED,
        BotAction.SCALE_IN,
    }

    async def execute(self, event: ParsedEvent) -> None:
        """
        Ein ParsedEvent auf alle Kunden-Accounts ausfuehren.
        Fehler bei einem Kunden blockieren nicht die anderen.

        Pause-Logik:
        - OPEN_TRADE, TRADE_FILLED, SCALE_IN → nur aktive Kunden (pausierte werden uebersprungen)
        - Alles andere (CLOSE, SL/TP, SCALE_OUT, etc.) → alle Kunden mit Mappings
          (bestehendes Geld schuetzen geht vor Pause)
        """
        if self.master_balance <= 0:
            logger.warning("Master Balance unbekannt — Execution uebersprungen")
            return

        is_open_action = event.action in self._OPEN_ACTIONS

        if is_open_action:
            # Neue Trades: nur aktive Kunden
            customers = self.get_active_customers()
        else:
            # Management: alle Kunden (auch pausierte) — damit offene Positionen
            # weiterhin geschlossen, SL/TP aktualisiert und gemanagt werden
            customers = list(self._customers.values())
            customers = [c for c in customers if c.client]

        if not customers:
            label = "aktiven" if is_open_action else "verfuegbaren"
            logger.warning(f"Keine {label} Kunden — nichts zu tun")
            return

        if not is_open_action and any(not c.active for c in customers):
            paused = [c.name for c in customers if not c.active]
            logger.info(
                f"[EXEC] Management-Event {event.action.value} {event.symbol} "
                f"wird auch an pausierte Kunden gesendet: {', '.join(paused)}"
            )

        logger.info(f"[EXEC] {event.action.value} {event.symbol} -> {len(customers)} Kunde(n)")

        # Alle Kunden parallel abarbeiten
        tasks = [self._execute_for_customer(event, c) for c in customers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Fehler loggen + Telegram Alert
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                logger.error(
                    f"[EXEC] Fehler bei Kunde {customers[i].name}: {result}"
                )
                if self._telegram:
                    await self._telegram.trade_error(
                        customers[i].name, event.symbol,
                        event.action.value, str(result)
                    )

    async def _execute_for_customer(self, event: ParsedEvent, customer: Customer) -> None:
        """Ein Event fuer einen einzelnen Kunden ausfuehren."""
        if not customer.client:
            logger.error(f"[EXEC] Kein REST Client fuer Kunde {customer.name}")
            return

        # Latenz-Messung starten
        self._exec_start_ms = int(time.time() * 1000)

        match event.action:
            case BotAction.OPEN_TRADE:
                await self._handle_open_trade(event, customer)
            case BotAction.TRADE_FILLED:
                await self._handle_trade_filled(event, customer)
            case BotAction.CANCEL_TRADE:
                await self._handle_cancel_trade(event, customer)
            case BotAction.AMEND_TRADE:
                await self._handle_amend_trade(event, customer)
            case BotAction.SET_SL:
                await self._handle_set_sl_tp(event, customer, is_sl=True)
            case BotAction.SET_TP:
                await self._handle_set_sl_tp(event, customer, is_sl=False)
            case BotAction.CANCEL_SL | BotAction.CANCEL_TP:
                await self._handle_cancel_sl_tp(event, customer)
            case BotAction.SCALE_IN:
                await self._handle_scale_in(event, customer)
            case BotAction.SCALE_OUT:
                await self._handle_scale_out(event, customer)
            case BotAction.CLOSE_TRADE:
                await self._handle_close_trade(event, customer)
            case BotAction.UPDATE_LEVERAGE:
                await self._handle_update_leverage(event, customer)
            case BotAction.UPDATE_MARGIN:
                await self._handle_update_margin(event, customer)
            case BotAction.RENAME_POSITION:
                await self._handle_rename_position(event, customer)
            case _:
                logger.warning(f"[EXEC] Unbekannte Aktion: {event.action}")

    # --------------------------------------------------------------------------
    # HANDLER
    # --------------------------------------------------------------------------

    async def _handle_trade_filled(self, event: ParsedEvent, customer: Customer) -> None:
        """
        Fill verarbeiten — bei Market Orders ist der Fill das ERSTE Event.
        Wenn kein Mapping existiert, ist es ein neuer Trade der gespiegelt werden muss.

        WICHTIG: Wenn closedPnL != 0, ist es ein CLOSE-Fill (Position wurde geschlossen),
        KEIN neuer Trade. Ohne diesen Check wuerde der Bot beim Close eine Gegenposition
        eroeffnen statt zu schliessen.

        Verwendet Lock pro Symbol+Kunde um Race Condition mit OPEN_TRADE zu verhindern.
        """
        d = event.details
        order_id = d.get("orderID", "")

        # CLOSE-ERKENNUNG: Wenn closedPnL != 0, ist es ein Close-Fill
        closed_pnl = float(d.get("closedPnL", 0) or 0)
        if closed_pnl != 0:
            logger.info(
                f"[EXEC] {customer.name}: Fill ist ein CLOSE (PnL: {closed_pnl}) "
                f"— kein neuer Trade (Close via CLOSE_TRADE Event)"
            )
            return

        # Lock holen — verhindert dass OPEN_TRADE gleichzeitig laeuft
        lock = self._get_open_lock(event.symbol, customer.id)
        async with lock:
            # Pruefen ob wir fuer dieses Symbol+Kunde schon ein Mapping haben
            if self._has_mapping_for_symbol(event.symbol, customer.id):
                return

            # Kein Mapping -> Neuer Market Trade
            master_qty = float(d.get("execQty", 0) or 0)
            if master_qty <= 0:
                return

            customer_qty = self._scaling.calculate_customer_qty(
                self.master_balance, customer.balance, master_qty, event.symbol
            )
            if customer_qty <= 0:
                logger.info(f"[EXEC] {customer.name}: Qty unter Minimum — uebersprungen")
                return

            side = d.get("side", "Buy")

            # SL/TP vom Master abfragen und beim Oeffnen mitschicken
            sl_tp = self._get_master_sl_tp(order_id)

            result = await customer.client.place_order(
                symbol=event.symbol,
                side=side,
                pos_side="Multi",
                order_qty=str(customer_qty),
                ord_type="Market",
            )
            # SL/TP bewusst NICHT im Open-Body (LeveX 600034) —
            # wird nach dem Mapping via _apply_sl_tp_after_open gesetzt.

            # Position-Mapping in DB speichern
            if not result.get("error"):
                # API gibt orderID direkt im Root zurueck
                customer_order_id = result.get("orderID", "")
                if not customer_order_id and isinstance(result.get("result"), dict):
                    customer_order_id = result["result"].get("orderID", "")

                entry_price = float(d.get("execPrice", 0) or 0)

                self._save_mapping(
                    master_pos_id=order_id,
                    customer_id=customer.id,
                    customer_pos_id=customer_order_id,
                    customer_order_id=customer_order_id,
                    symbol=event.symbol,
                    side=side,
                    customer_qty=customer_qty,
                    customer_entry_price=entry_price,
                    leverage=self._get_master_leverage(event.symbol),
                    stop_loss=float(sl_tp.get("stopLoss", 0) or 0),
                    take_profit=float(sl_tp.get("takeProfit", 0) or 0),
                )
                logger.info(
                    f"[EXEC] Mapping (Market Fill): Master {order_id[:8]}... -> "
                    f"Kunde {customer.name} ({customer_order_id[:8] if customer_order_id else 'no-id'}...)"
                )

                await self._apply_sl_tp_after_open(
                    customer=customer,
                    symbol=event.symbol,
                    pos_side=side,
                    position_id=customer_order_id,
                    sl_tp=sl_tp,
                )

                # Trade-Historie speichern (mit initial_risk fuer R-Multiple)
                sl_price = float(sl_tp.get("stopLoss", 0) or 0)
                initial_risk = abs(entry_price - sl_price) * customer_qty if sl_price > 0 and entry_price > 0 else 0
                self._db.save_trade_history(
                    customer_id=customer.id,
                    master_position_id=order_id,
                    symbol=event.symbol,
                    side=side,
                    action="OPEN",
                    qty=customer_qty,
                    price=entry_price,
                    initial_risk=round(initial_risk, 6),
                    execution_latency_ms=self._get_latency_ms(),
                )

    async def _handle_open_trade(self, event: ParsedEvent, customer: Customer) -> None:
        """
        Neuen Trade auf Kunden-Account platzieren.

        WORKAROUND: Limit Orders werden NICHT sofort platziert, weil der Copy Trading
        API Endpoint keine Limit Orders unterstuetzt (Error 600034).
        Stattdessen wird die Master-Position-ID vorgemerkt und beim Fill
        (TRADE_FILLED) als Market Order gespiegelt.
        TODO: Sobald Levex Limit Orders im Copy Trading Endpoint unterstuetzt,
        hier direkt als Limit durchreichen.
        """
        d = event.details
        ord_type = d.get("ordType", "Market")

        # Limit Orders: Nicht sofort platzieren, auf Fill warten
        if ord_type == "Limit":
            logger.info(
                f"[EXEC] {customer.name}: Master Limit Order {event.symbol} "
                f"({d.get('side')} @ {d.get('price')}) — warte auf Fill"
            )
            return

        # Lock holen — verhindert dass TRADE_FILLED gleichzeitig laeuft
        lock = self._get_open_lock(event.symbol, customer.id)
        async with lock:
            # Duplikat-Check: Wurde bereits via TRADE_FILLED gespiegelt?
            if self._has_mapping_for_symbol(event.symbol, customer.id):
                return

            master_qty = float(d.get("orderQty", 0) or 0)
            master_pos_id = d.get("positionID", "")

            # Pruefen ob das ein Nachkauf auf eine bestehende Position ist
            existing_mapping = self._find_mapping(master_pos_id, customer.id)
            customer_pos_id = existing_mapping.customer_position_id if existing_mapping else None

            # Qty skalieren
            customer_qty = self._scaling.calculate_customer_qty(
                self.master_balance, customer.balance, master_qty, event.symbol
            )
            if customer_qty <= 0:
                logger.info(f"[EXEC] {customer.name}: Qty unter Minimum — uebersprungen")
                return

            side = d["side"]

            # SL/TP vom Master abfragen und beim Oeffnen mitschicken
            sl_tp = self._get_master_sl_tp(master_pos_id)

            result = await customer.client.place_order(
                symbol=event.symbol,
                side=side,
                pos_side="Multi",
                order_qty=str(customer_qty),
                ord_type="Market",
                position_id=customer_pos_id,
            )
            # SL/TP bewusst NICHT im Open-Body (LeveX 600034) —
            # wird nach dem Mapping via _apply_sl_tp_after_open gesetzt.

            # Position-Mapping in DB speichern
            if not result.get("error"):
                # API gibt orderID direkt im Root zurueck
                customer_order_id = result.get("orderID", "")
                if not customer_order_id and isinstance(result.get("result"), dict):
                    customer_order_id = result["result"].get("orderID", "")
                new_customer_pos_id = customer_pos_id or customer_order_id

                if master_pos_id and not existing_mapping:
                    entry_price = float(d.get("price", 0) or 0)

                    self._save_mapping(
                        master_pos_id=master_pos_id,
                        customer_id=customer.id,
                        customer_pos_id=new_customer_pos_id,
                        customer_order_id=customer_order_id,
                        symbol=event.symbol,
                        side=d.get("side", ""),
                        customer_qty=customer_qty,
                        customer_entry_price=entry_price,
                        leverage=self._get_master_leverage(event.symbol),
                        stop_loss=float(sl_tp.get("stopLoss", 0) or 0),
                        take_profit=float(sl_tp.get("takeProfit", 0) or 0),
                    )
                    logger.info(
                        f"[EXEC] Mapping: Master {master_pos_id[:8]}... -> "
                        f"Kunde {customer.name} {new_customer_pos_id[:8]}..."
                    )

                    await self._apply_sl_tp_after_open(
                        customer=customer,
                        symbol=event.symbol,
                        pos_side=side,
                        position_id=new_customer_pos_id,
                        sl_tp=sl_tp,
                    )

                    # Trade-Historie speichern (mit initial_risk fuer R-Multiple)
                    sl_price = float(sl_tp.get("stopLoss", 0) or 0)
                    initial_risk = abs(entry_price - sl_price) * customer_qty if sl_price > 0 and entry_price > 0 else 0
                    self._db.save_trade_history(
                        customer_id=customer.id,
                        master_position_id=master_pos_id,
                        symbol=event.symbol,
                        side=side,
                        action="OPEN",
                        qty=customer_qty,
                        price=entry_price,
                        initial_risk=round(initial_risk, 6),
                        execution_latency_ms=self._get_latency_ms(),
                    )

    async def _handle_cancel_trade(self, event: ParsedEvent, customer: Customer) -> None:
        """Order auf Kunden-Account stornieren."""
        d = event.details
        mapping = self._find_mapping(d.get("positionID", ""), customer.id)
        if mapping:
            await customer.client.cancel_order(
                symbol=event.symbol,
                pos_side="Multi",
                position_id=mapping.customer_position_id,
            )
        else:
            logger.warning(f"[EXEC] {customer.name}: Kein Mapping fuer Cancel gefunden")

    async def _handle_amend_trade(self, event: ParsedEvent, customer: Customer) -> None:
        """
        Order aendern = Cancel + Replace.
        Levex hat keinen Amend-Endpoint, also canceln wir und platzieren neu.
        """
        d = event.details
        mapping = self._find_mapping(d.get("positionID", ""), customer.id)

        if not mapping:
            logger.warning(f"[EXEC] {customer.name}: Kein Mapping fuer Amend gefunden")
            return

        # Alte Order canceln
        side = d.get("side", mapping.side or "Buy")
        await customer.client.cancel_order(
            symbol=event.symbol,
            pos_side="Multi",
            position_id=mapping.customer_position_id,
        )

        # Neue Order mit neuem Preis platzieren
        new_qty = float(d.get("newQty", 0) or 0)
        customer_qty = self._scaling.calculate_customer_qty(
            self.master_balance, customer.balance, new_qty, event.symbol
        )
        if customer_qty > 0:
            await customer.client.place_order(
                symbol=event.symbol,
                side=side,
                pos_side="Multi",
                order_qty=str(customer_qty),
                ord_type="Limit",
                price=d.get("newPrice"),
                position_id=mapping.customer_position_id,
            )

    async def _apply_sl_tp_after_open(
        self,
        customer: Customer,
        symbol: str,
        pos_side: str,
        position_id: str,
        sl_tp: dict,
    ) -> None:
        """
        SL/TP NACH dem Oeffnen separat setzen.

        Grund (2026-09-07): LeveX lehnt copy-affiliate-order ab, wenn
        stopLoss/takeProfit direkt im Open-Body stehen
        (HTTP 400, code 600034 "Order not found"). Die Position wird deshalb
        erst nackt geoeffnet und SL/TP direkt danach via trading-stop gesetzt.
        """
        if not sl_tp or not position_id or not customer.client:
            return

        sl = sl_tp.get("stopLoss")
        tp = sl_tp.get("takeProfit")
        if not sl and not tp:
            return

        last_err = None
        for attempt in range(1, 4):
            if attempt > 1:
                # Position braucht nach dem Market-Fill kurz, bis sie existiert
                await asyncio.sleep(0.5)

            result = await customer.client.set_trading_stop(
                position_id=position_id,
                symbol=symbol,
                pos_side=pos_side,
                stop_loss=str(sl) if sl else None,
                take_profit=str(tp) if tp else None,
            )

            if not result.get("error"):
                logger.info(
                    f"[EXEC] {customer.name}: SL/TP nach Oeffnung gesetzt "
                    f"(SL={sl}, TP={tp}, Versuch {attempt}) OK"
                )
                return

            last_err = result.get("error") or {}
            logger.warning(
                f"[EXEC] {customer.name}: SL/TP-Setzen Versuch {attempt}/3 "
                f"fehlgeschlagen ({last_err.get('code')}: {last_err.get('message')})"
            )

        logger.error(
            f"[EXEC] {customer.name}: SL/TP konnte NICHT gesetzt werden — "
            f"Position laeuft OHNE Absicherung! (SL={sl}, TP={tp}, "
            f"PosID={position_id})"
        )
        if self._telegram:
            try:
                await self._telegram.trade_error(
                    customer.name,
                    symbol,
                    "SET_SL_TP_AFTER_OPEN",
                    f"Position offen OHNE SL/TP (SL={sl}, TP={tp}). "
                    f"Bitte manuell pruefen!",
                )
            except Exception:
                pass

    async def _handle_set_sl_tp(self, event: ParsedEvent, customer: Customer, is_sl: bool) -> None:
        """
        SL oder TP auf Kunden-Position setzen.

        Nutzt den trading-stop Endpoint um SL/TP direkt auf der
        Kunden-Exchange zu setzen. Falls der Endpoint fehlschlaegt,
        wird auf Event-Mirroring als Fallback zurueckgefallen.
        """
        d = event.details
        label = "SL" if is_sl else "TP"
        stop_price = d.get("stopPrice") or d.get("newStopPrice")
        old_price = d.get("oldStopPrice", "")

        master_pos_id = d.get("positionID", "")
        mapping = self._find_mapping(master_pos_id, customer.id)

        if not mapping:
            logger.warning(f"[EXEC] {customer.name}: Kein Mapping fuer {label} gefunden")
            return

        # SL/TP in DB speichern (fuer Dashboard-Anzeige)
        db_mapping = self._db.get_mapping(master_pos_id, customer.id)
        if db_mapping:
            current_sl = db_mapping.get("stop_loss", 0) or 0
            current_tp = db_mapping.get("take_profit", 0) or 0
            new_sl = float(stop_price) if is_sl else current_sl
            new_tp = float(stop_price) if not is_sl else current_tp
            self._db.update_mapping_sl_tp(master_pos_id, customer.id, new_sl, new_tp)

        # Auf Kunden-Exchange setzen via trading-stop Endpoint
        if customer.client:
            sl_param = str(stop_price) if is_sl else None
            tp_param = str(stop_price) if not is_sl else None

            result = await customer.client.set_trading_stop(
                position_id=mapping.customer_position_id,
                symbol=mapping.symbol,
                pos_side=mapping.side,
                stop_loss=sl_param,
                take_profit=tp_param,
            )

            err = result.get("error")
            if err:
                logger.warning(
                    f"[EXEC] {customer.name}: trading-stop fehlgeschlagen "
                    f"({err.get('code')}: {err.get('message')}). "
                    f"Fallback: Event-Mirroring aktiv."
                )
            else:
                action = "geaendert" if old_price else "gesetzt"
                extra = f" (vorher: {old_price})" if old_price else ""
                logger.info(
                    f"[EXEC] {customer.name}: {label} {action} @ {stop_price}{extra} | "
                    f"Erfolgreich auf Kunden-Exchange gesetzt ✅"
                )
                return

        # Fallback-Log wenn kein Client oder Endpoint fehlschlaegt
        action = "geaendert" if old_price else "gesetzt"
        extra = f" (vorher: {old_price})" if old_price else ""
        logger.info(
            f"[EXEC] {customer.name}: Master {label} {action} @ {stop_price}{extra} | "
            f"Fallback: Close wird ueber Event-Mirroring gehandelt."
        )

    async def _handle_cancel_sl_tp(self, event: ParsedEvent, customer: Customer) -> None:
        """SL oder TP auf Kunden-Position entfernen."""
        d = event.details
        mapping = self._find_mapping(d.get("positionID", ""), customer.id)
        if mapping:
            await customer.client.cancel_order(
                symbol=event.symbol,
                pos_side="Multi",
                order_id=d.get("orderID"),
                position_id=mapping.customer_position_id,
            )

    async def _handle_scale_in(self, event: ParsedEvent, customer: Customer) -> None:
        """Nachkauf — Position vergroessern."""
        d = event.details
        added = d["newSize"] - d["previousSize"]
        customer_qty = self._scaling.calculate_customer_qty(
            self.master_balance, customer.balance, added, event.symbol
        )
        if customer_qty <= 0:
            return

        mapping = self._find_mapping(d.get("positionID", ""), customer.id)
        if not mapping:
            logger.warning(f"[EXEC] {customer.name}: Kein Mapping fuer Scale In")
            return

        # Scale In: gleiche Seite wie offene Position
        scale_side = mapping.side or d.get("side", "Buy")
        result = await customer.client.place_order(
            symbol=event.symbol,
            side=scale_side,
            pos_side="Multi",
            order_qty=str(customer_qty),
            ord_type="Market",
            position_id=mapping.customer_position_id,
        )

        if not result.get("error"):
            master_pos_id = d.get("positionID", "")
            self._db.save_trade_history(
                customer_id=customer.id,
                master_position_id=master_pos_id,
                symbol=event.symbol,
                side=scale_side,
                action="SCALE_IN",
                qty=customer_qty,
                execution_latency_ms=self._get_latency_ms(),
            )

            # Mapping aktualisieren: neue Qty + gewichteter Durchschnittspreis
            db_mapping = self._db.get_mapping(master_pos_id, customer.id)
            if db_mapping:
                old_qty = db_mapping.get("customer_qty", 0) or 0
                old_entry = db_mapping.get("customer_entry_price", 0) or 0
                new_total_qty = old_qty + customer_qty
                # Gewichteter Durchschnitt
                scale_price = float(d.get("entryPrice", 0) or d.get("price", 0) or 0)
                if new_total_qty > 0 and scale_price > 0:
                    new_entry = (old_entry * old_qty + scale_price * customer_qty) / new_total_qty
                else:
                    new_entry = old_entry
                self._db.update_mapping_position(master_pos_id, customer.id, new_total_qty, new_entry)

    async def _handle_scale_out(self, event: ParsedEvent, customer: Customer) -> None:
        """Teilschliessung — prozentual gleich viel schliessen wie der Master."""
        await self._execute_close_for_customer(event, customer)

    async def _execute_close_for_customer(
        self, event: ParsedEvent, customer: Customer
    ) -> None:
        """
        Kunden-Position schliessen (voll oder teilweise).

        Wird von TRADE_FILLED (closedPnL != 0), CLOSE_TRADE und SCALE_OUT aufgerufen.

        Logik:
        1. Prozentsatz berechnen den der Master geschlossen hat
        2. Gleichen Prozentsatz beim Kunden schliessen
        3. Bei 100% Close → Mapping entfernen
        4. Bei Partial Close → Mapping behalten

        Beispiel:
        - Master: 0.0012 BTC, schliesst 0.0006 → 50%
        - Kunde: 0.001 BTC → schliesst 0.0005 (50%)
        """
        d = event.details

        # 1. Mapping finden — erst ueber positionID, dann orderID, dann Symbol
        master_pos_id = d.get("positionID", "") or d.get("orderID", "")
        open_side = ""
        db_mappings = []

        mapping = self._find_mapping(master_pos_id, customer.id)
        if mapping:
            open_side = mapping.side
            master_pos_id = mapping.master_position_id
        else:
            # Fallback: Mapping ueber Symbol suchen
            db_mappings = self._db.find_mapping_by_symbol(event.symbol, customer.id)
            if db_mappings:
                open_side = db_mappings[0]["side"]
                master_pos_id = db_mappings[0]["master_position_id"]
                logger.info(
                    f"[EXEC] {customer.name}: Mapping via Symbol gefunden: "
                    f"{master_pos_id[:8]}..."
                )
            else:
                logger.warning(
                    f"[EXEC] {customer.name}: Kein Mapping fuer Close {event.symbol}"
                )
                return

        # 2. Close-Prozentsatz berechnen
        previous_size = float(d.get("previousSize", 0) or 0)
        new_size = float(d.get("newSize", 0) or 0)
        exec_qty = float(d.get("execQty", 0) or 0)

        if previous_size > 0:
            # CLOSE_TRADE oder SCALE_OUT: previousSize und newSize verfuegbar
            close_percent = self._scaling.calculate_partial_close_percent(
                previous_size, new_size
            )
            is_full_close = (new_size == 0)
        elif exec_qty > 0:
            # TRADE_FILLED: Nur execQty verfuegbar — versuche Prozentsatz zu schaetzen
            # Wir checken den Parser fuer die aktuelle Master-Position-Size
            if self._parser:
                master_pos = self._parser._positions.get(master_pos_id)
                if master_pos:
                    current_size = float(master_pos.size) if master_pos.size else 0.0
                    original_size = current_size + exec_qty
                    close_percent = self._scaling.calculate_partial_close_percent(
                        original_size, current_size
                    )
                    is_full_close = (current_size == 0)
                else:
                    # Position nicht mehr im Parser → wahrscheinlich 100% Close
                    close_percent = 100.0
                    is_full_close = True
            else:
                close_percent = 100.0
                is_full_close = True
        else:
            # Kein Qty → 100% Close annehmen
            close_percent = 100.0
            is_full_close = True

        # 3. Close-Side bestimmen (Gegenseite der offenen Position)
        close_side = "Sell" if open_side == "Buy" else "Buy"

        # 4. Kunden-Qty berechnen
        # Wir kennen die exakte Kunden-Position-Size nicht, daher skalieren wir
        # die Master-Close-Qty proportional
        if exec_qty > 0:
            master_close_qty = exec_qty
        elif previous_size > 0:
            master_close_qty = previous_size - new_size
        else:
            master_close_qty = 0

        if master_close_qty > 0:
            customer_close_qty = self._scaling.calculate_customer_qty(
                self.master_balance, customer.balance,
                master_close_qty, event.symbol
            )
        else:
            customer_close_qty = 0

        # Minimum-Qty sicherstellen
        min_cfg = self._scaling._get_config(event.symbol)
        if customer_close_qty < min_cfg.min_order_size:
            customer_close_qty = min_cfg.min_order_size

        close_type = "FULL CLOSE" if is_full_close else f"PARTIAL CLOSE ({close_percent:.1f}%)"
        logger.info(
            f"[EXEC] {customer.name}: {close_type} {event.symbol} | "
            f"Side: {close_side} | Qty: {customer_close_qty}"
        )

        # 5. ReduceOnly Market Order — mit position_id fuer Multi-Trade Modus
        customer_pos_id = None
        if mapping:
            customer_pos_id = mapping.customer_position_id
        elif db_mappings:
            customer_pos_id = db_mappings[0].get("customer_position_id", "")

        result = await customer.client.place_order(
            symbol=event.symbol,
            side=close_side,
            pos_side="Multi",
            order_qty=str(customer_close_qty),
            ord_type="Market",
            reduce_only=True,
            position_id=customer_pos_id if customer_pos_id else None,
        )

        # 6. Mapping verwalten + Trade-Historie
        if not result.get("error"):
            # PnL proportional skalieren (Naeherung)
            master_pnl = float(d.get("realisedPnL", 0) or 0)
            if self.master_balance > 0 and master_pnl != 0:
                customer_pnl = master_pnl * (customer.balance / self.master_balance)
            else:
                customer_pnl = 0

            action = "CLOSE" if is_full_close else "SCALE_OUT"
            self._db.save_trade_history(
                customer_id=customer.id,
                master_position_id=master_pos_id,
                symbol=event.symbol,
                side=close_side,
                action=action,
                qty=customer_close_qty,
                pnl=round(customer_pnl, 6),
                execution_latency_ms=self._get_latency_ms(),
            )

            if is_full_close:
                self._remove_mapping(master_pos_id, customer.id)
                logger.info(
                    f"[EXEC] {customer.name}: Position {event.symbol} geschlossen ✓"
                )
            else:
                logger.info(
                    f"[EXEC] {customer.name}: Position {event.symbol} "
                    f"teilweise geschlossen ({close_percent:.1f}%) ✓"
                )
        else:
            error_msg = str(result.get('error'))
            logger.error(
                f"[EXEC] {customer.name}: Close fehlgeschlagen: {error_msg}"
            )
            if self._telegram:
                await self._telegram.trade_error(
                    customer.name, event.symbol, "CLOSE", error_msg
                )

    async def _handle_close_trade(self, event: ParsedEvent, customer: Customer) -> None:
        """Position komplett schliessen (via CLOSE_TRADE Event vom Parser)."""
        await self._execute_close_for_customer(event, customer)

    async def _handle_update_leverage(self, event: ParsedEvent, customer: Customer) -> None:
        """Leverage auf Kunden-Account aendern."""
        d = event.details
        new_leverage = float(d["newLeverage"])
        await customer.client.set_leverage(
            symbol=event.symbol,
            leverage=d["newLeverage"],
        )

        # Leverage in aktiven Mappings fuer dieses Symbol aktualisieren
        active_mappings = self._db.find_mapping_by_symbol(event.symbol, customer.id)
        for m in active_mappings:
            self._db._conn.execute("""
                UPDATE position_mappings SET leverage = ?
                WHERE id = ?
            """, (new_leverage, m["id"]))
        if active_mappings:
            self._db._conn.commit()

    async def _handle_update_margin(self, event: ParsedEvent, customer: Customer) -> None:
        """Margin auf Kunden-Position anpassen."""
        d = event.details
        mapping = self._find_mapping(d.get("positionID", ""), customer.id)
        if not mapping:
            return

        old_margin = float(d.get("oldMargin", 0))
        new_margin = float(d.get("newMargin", 0))
        change = new_margin - old_margin

        if abs(change) > 0.001:
            await customer.client.change_margin(
                position_id=mapping.customer_position_id,
                symbol=event.symbol,
                pos_side="Multi",
                change_amount=change,
            )

    async def _handle_rename_position(self, event: ParsedEvent, customer: Customer) -> None:
        """Position auf Kunden-Account umbenennen."""
        d = event.details
        mapping = self._find_mapping(d.get("positionID", ""), customer.id)
        if not mapping:
            logger.warning(f"[EXEC] {customer.name}: Kein Mapping fuer Rename gefunden")
            return

        new_name = d.get("newName", "")
        result = await customer.client.rename_position(
            position_id=mapping.customer_position_id,
            symbol=event.symbol,
            pos_side="Multi",
            display_name=new_name,
        )
        if not result.get("error"):
            logger.info(f"[EXEC] {customer.name}: Position umbenannt -> '{new_name}' ✓")
        else:
            logger.error(f"[EXEC] {customer.name}: Rename fehlgeschlagen: {result.get('error')}")

    # --------------------------------------------------------------------------
    # RECONCILIATION (bei Bot-Restart)
    # --------------------------------------------------------------------------

    async def reconcile(self) -> None:
        """
        Abgleich nach Bot-Restart: Master-Positionen vs. DB-Mappings.

        Logik:
        1. Master offen + Mapping aktiv       -> OK, nichts tun
        2. Master geschlossen + Mapping aktiv -> Kunden-Position schliessen (verwaist)
        3. Master offen + kein Mapping        -> SKIP (verpasster Trade, Preis waere anders)

        WICHTIG: Verpasste Trades werden NICHT nachgeholt — der Kunde wuerde einen
        komplett anderen Preis bekommen, das waere unfair.
        """
        if not self._parser:
            logger.warning("[RECON] Kein Parser — Reconciliation uebersprungen")
            return

        active_mappings = self._db.get_all_active_mappings()
        master_positions = self._parser._positions  # positionID -> PerpPosition

        # Aktive Master-Position-IDs sammeln (Size > 0)
        open_master_ids: set[str] = set()
        for pos_id, pos in master_positions.items():
            if float(pos.size) if pos.size else 0.0 > 0:
                open_master_ids.add(pos.positionID)

        logger.info(f"[RECON] Start: {len(active_mappings)} aktive Mappings, "
                     f"{len(open_master_ids)} offene Master-Positionen")

        # --- Fall 2: Verwaiste Kunden-Positionen schliessen ---
        orphaned = [m for m in active_mappings
                    if m["master_position_id"] not in open_master_ids]

        if orphaned:
            logger.warning(
                f"[RECON] {len(orphaned)} verwaiste Mapping(s) gefunden — "
                f"Master-Position geschlossen waehrend Bot offline war"
            )
            for m in orphaned:
                customer = self._customers.get(m["customer_id"])
                if not customer or not customer.client or not customer.active:
                    logger.warning(
                        f"[RECON] Kunde {m['customer_id']} nicht verfuegbar — "
                        f"Mapping {m['master_position_id'][:8]}... wird nur in DB geschlossen"
                    )
                    self._db.close_mapping(m["master_position_id"], m["customer_id"])
                    continue

                close_side = "Sell" if m.get("side") == "Buy" else "Buy"
                logger.info(
                    f"[RECON] {customer.name}: Schliesse verwaiste Position "
                    f"{m['symbol']} (Master {m['master_position_id'][:8]}... "
                    f"-> Kunde {m['customer_position_id'][:8]}...)"
                )

                result = await customer.client.place_order(
                    symbol=m["symbol"],
                    side=close_side,
                    pos_side="Multi",
                    order_qty="0",  # 0 = ganze Position
                    ord_type="Market",
                    reduce_only=True,
                    position_id=m["customer_position_id"],
                )

                if not result.get("error"):
                    self._db.close_mapping(m["master_position_id"], m["customer_id"])
                    logger.info(f"[RECON] {customer.name}: Verwaiste Position {m['symbol']} geschlossen ✓")
                else:
                    logger.error(
                        f"[RECON] {customer.name}: Close fehlgeschlagen: {result.get('error')} "
                        f"— Mapping bleibt aktiv, manuell pruefen!"
                    )
        else:
            logger.info("[RECON] Keine verwaisten Positionen gefunden ✓")

        # --- Fall 3: Verpasste Trades loggen (NICHT nachholen) ---
        mapped_master_ids = {m["master_position_id"] for m in active_mappings}
        missed = open_master_ids - mapped_master_ids

        if missed:
            logger.warning(
                f"[RECON] {len(missed)} Master-Position(en) ohne Mapping — "
                f"waehrend Bot-Downtime eroeffnet, werden NICHT nachgeholt (Preis waere anders)"
            )
            for pos_id in missed:
                pos = master_positions.get(pos_id)
                if pos:
                    logger.warning(
                        f"[RECON] Verpasst: {pos.side} {pos.symbol} | "
                        f"Size: {pos.size} | Entry: {pos.avgEntryPrice} | "
                        f"PosID: {pos.positionID[:8]}..."
                    )
        else:
            logger.info("[RECON] Keine verpassten Trades ✓")

        logger.info("[RECON] Abgleich abgeschlossen")

        # Telegram Alert
        if self._telegram:
            await self._telegram.reconciliation_result(
                orphaned=len(orphaned) if orphaned else 0,
                missed=len(missed) if missed else 0,
            )

    # --------------------------------------------------------------------------
    # LATENCY HELPER
    # --------------------------------------------------------------------------

    def _get_latency_ms(self) -> int:
        """Execution-Latenz in Millisekunden berechnen."""
        start = getattr(self, '_exec_start_ms', 0)
        if start <= 0:
            return 0
        return int(time.time() * 1000) - start

    # --------------------------------------------------------------------------
    # SL/TP HELPER
    # --------------------------------------------------------------------------

    def _get_master_sl_tp(self, master_pos_id: str) -> dict[str, str]:
        """
        SL/TP-Preise des Masters fuer eine Position abfragen.
        Nutzt den Parser um aktive StopMarket/MarketIfTouched Orders zu finden.
        """
        if not self._parser or not master_pos_id:
            return {}
        return self._parser.get_sl_tp_for_position(master_pos_id)

    # --------------------------------------------------------------------------
    # POSITION MAPPING (SQLite-backed)
    # --------------------------------------------------------------------------

    def _find_mapping(self, master_pos_id: str, customer_id: str) -> PositionMapping | None:
        """Mapping fuer eine Master-Position und einen Kunden finden."""
        if not master_pos_id:
            return None
        row = self._db.get_mapping(master_pos_id, customer_id)
        if row:
            return PositionMapping(
                master_position_id=row["master_position_id"],
                customer_id=row["customer_id"],
                customer_position_id=row["customer_position_id"],
                customer_order_id=row.get("customer_order_id", ""),
                symbol=row["symbol"],
                side=row.get("side", ""),
            )
        return None

    def _save_mapping(
        self,
        master_pos_id: str,
        customer_id: str,
        customer_pos_id: str,
        customer_order_id: str,
        symbol: str,
        side: str = "",
        customer_qty: float = 0,
        customer_entry_price: float = 0,
        leverage: float = 0,
        stop_loss: float = 0,
        take_profit: float = 0,
    ) -> None:
        """Neues Mapping in DB speichern."""
        self._db.save_mapping(
            master_position_id=master_pos_id,
            customer_id=customer_id,
            customer_position_id=customer_pos_id,
            customer_order_id=customer_order_id,
            symbol=symbol,
            side=side,
            customer_qty=customer_qty,
            customer_entry_price=customer_entry_price,
            leverage=leverage,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

    def _get_master_leverage(self, symbol: str) -> float:
        """Master-Leverage fuer ein Symbol aus gespeicherten Master-Positionen lesen."""
        try:
            positions = self._db.get_master_positions()
            for pos in positions:
                if pos.get("symbol") == symbol:
                    return float(pos.get("leverage", 0) or 0)
        except Exception:
            pass
        return 0.0

    def _remove_mapping(self, master_pos_id: str, customer_id: str) -> None:
        """Mapping als geschlossen markieren."""
        self._db.close_mapping(master_pos_id, customer_id)
        logger.info(
            f"[EXEC] Mapping geschlossen: Master {master_pos_id[:8]}... -> "
            f"Kunde {customer_id}"
        )

    def _has_mapping_for_symbol(self, symbol: str, customer_id: str) -> bool:
        """Prueft ob fuer ein Symbol+Kunde bereits ein aktives Mapping existiert."""
        rows = self._db.find_mapping_by_symbol(symbol, customer_id)
        return len(rows) > 0

    async def cleanup(self) -> None:
        """Alle REST Clients, DB und Telegram sauber schliessen."""
        if self._telegram:
            await self._telegram.bot_stopped()
            await self._telegram.close()
        for customer in self._customers.values():
            if customer.client:
                await customer.client.close()
        self._db.close()
