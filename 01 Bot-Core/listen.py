"""
(C) listen.py — Copy Trading Bot Entry Point

Verbindet sich mit dem Levex WebSocket, hoert auf alle Events vom Master-Account
und spiegelt sie auf Kunden-Accounts.

Modi:
- DRY_RUN=true  -> Nur loggen, nichts ausfuehren (Phase 1)
- DRY_RUN=false -> Live-Mirroring auf Kunden-Accounts (Phase 2)

Starten mit: python listen.py
"""

import asyncio
import json
import os
import signal
from typing import Any

from config import config
from logger_setup import logger
from websocket_client import LevexWebSocket
from customer_ws import CustomerWebSocket
from parser import OrderParser
from scaling import ScalingEngine
from database import Database
from execution import ExecutionEngine, Customer
from telegram import TelegramAlert
from signal_bot import SignalBot
from bot_types import (
    PerpOrder,
    PerpFill,
    PerpPosition,
    PerpAccount,
    ParsedEvent,
    BotAction,
)


# ============================================================================
# SETUP
# ============================================================================

DRY_RUN = os.getenv("DRY_RUN", "false").lower() == "true"

# Reconciliation-Flag: wird nach erstem Position-Snapshot ausgefuehrt
_reconciliation_pending = False

# Komponenten initialisieren
ws = LevexWebSocket()
parser = OrderParser()
scaling = ScalingEngine()
db = Database()
db.connect()
telegram = TelegramAlert(
    bot_token=config.telegram_bot_token,
    chat_id=config.telegram_chat_id,
    team_password=config.telegram_team_password,
    db=db,
    paid_group_id=os.getenv("SIGNAL_PAID_GROUP_ID", ""),
    scalp_group_id=os.getenv("SIGNAL_SCALP_GROUP_ID", ""),
)
engine = ExecutionEngine(base_url=config.rest_url, scaling=scaling, db=db, parser=parser, telegram=telegram)

# Signal Bot fuer Telegram-Gruppen (Paid Signale + Marketing Channel)
signal_bot = SignalBot(
    bot_token=config.telegram_bot_token,
    paid_group_id=os.getenv("SIGNAL_PAID_GROUP_ID", ""),
    db=db,
    parser=parser,
    marketing_channel_id=os.getenv("MARKETING_CHANNEL_ID", ""),
    scalp_group_id=os.getenv("SIGNAL_SCALP_GROUP_ID", ""),
)

# Kunden-WebSocket-Verbindungen fuer Balance-Tracking
customer_ws_connections: list[CustomerWebSocket] = []

if not DRY_RUN:
    # Kunden aus Datenbank laden
    db_customers = db.get_active_customers()
    if db_customers:
        logger.info(f"Lade {len(db_customers)} Kunde(n) aus Datenbank...")
        for c in db_customers:
            engine.add_customer(Customer(
                id=c["id"],
                name=c["name"],
                api_key=c["api_key"],
                api_secret=c["api_secret"],
                uid=c["uid"],
                balance=0.0,  # Wird via WebSocket automatisch gesetzt
                read_api_key=c.get("read_api_key", ""),
                read_api_secret=c.get("read_api_secret", ""),
            ))

            # WebSocket fuer Balance-Tracking erstellen
            read_key = c.get("read_api_key", "")
            read_secret = c.get("read_api_secret", "")
            if read_key and read_secret:
                customer_ws_connections.append(CustomerWebSocket(
                    ws_url=config.ws_url,
                    customer_id=c["id"],
                    customer_name=c["name"],
                    api_key=read_key,
                    api_secret=read_secret,
                ))
    else:
        logger.warning("Keine aktiven Kunden in Datenbank — Bot laeuft im Leerlauf")


# ============================================================================
# DRY RUN — Was WUERDE bei einem echten Kunden passieren?
# ============================================================================

SIMULATED_CUSTOMER = {
    "id": "SIM-KUNDE-001",
    "balance": 5_000,
}


def process_events_dry_run(events: list[ParsedEvent]) -> None:
    """Dry Run: Nur loggen was passieren wuerde."""
    if not events:
        return

    master_balance = parser.master_balance

    for event in events:
        logger.info("")
        logger.info("*" * 50)
        logger.info(f"BOT AKTION: {event.action.value}")
        logger.info(f"Symbol: {event.symbol}")
        logger.info(f"Details: {json.dumps(event.details, indent=2, default=str)}")
        logger.info("*" * 50)

        logger.info("")
        logger.info(
            f"[DRY RUN] Kunde {SIMULATED_CUSTOMER['id']} "
            f"({SIMULATED_CUSTOMER['balance']} USDT):"
        )

        if master_balance <= 0:
            logger.warning(
                "[DRY RUN] Master Balance noch nicht bekannt — Skalierung nicht moeglich"
            )
            continue

        match event.action:
            case BotAction.OPEN_TRADE:
                master_qty = float(event.details.get("orderQty", 0) or 0)
                customer_qty = scaling.calculate_customer_qty(
                    master_balance, SIMULATED_CUSTOMER["balance"], master_qty, event.symbol)
                if customer_qty > 0:
                    logger.info(f"[DRY RUN] -> WUERDE platzieren: {event.details['side']} {event.symbol} | Qty: {customer_qty} (Master: {master_qty})")
                else:
                    logger.info(f"[DRY RUN] -> UEBERSPRUNGEN: Qty unter Minimum")

            case BotAction.TRADE_FILLED:
                logger.info(f"[DRY RUN] -> Fill: {event.details['side']} {event.details['execQty']} @ {event.details['execPrice']}")

            case BotAction.CANCEL_TRADE:
                logger.info(f"[DRY RUN] -> WUERDE stornieren: OrderID {event.details['orderID']}")

            case BotAction.SET_SL:
                logger.info(f"[DRY RUN] -> WUERDE SL setzen: {event.details.get('stopPrice', event.details.get('newStopPrice', '?'))}")

            case BotAction.SET_TP:
                logger.info(f"[DRY RUN] -> WUERDE TP setzen: {event.details.get('stopPrice', event.details.get('newStopPrice', '?'))}")

            case BotAction.CANCEL_SL:
                logger.info(f"[DRY RUN] -> WUERDE SL entfernen")

            case BotAction.CANCEL_TP:
                logger.info(f"[DRY RUN] -> WUERDE TP entfernen")

            case BotAction.AMEND_TRADE:
                logger.info(f"[DRY RUN] -> WUERDE aendern: Preis {event.details['oldPrice']} -> {event.details['newPrice']}")

            case BotAction.SCALE_IN:
                added = event.details["newSize"] - event.details["previousSize"]
                customer_added = scaling.calculate_customer_qty(master_balance, SIMULATED_CUSTOMER["balance"], added, event.symbol)
                logger.info(f"[DRY RUN] -> WUERDE nachkaufen: +{customer_added} (Master: +{added})")

            case BotAction.SCALE_OUT:
                pct = scaling.calculate_partial_close_percent(event.details["previousSize"], event.details["newSize"])
                logger.info(f"[DRY RUN] -> WUERDE teilschliessen: {pct:.1f}%")

            case BotAction.CLOSE_TRADE:
                logger.info(f"[DRY RUN] -> WUERDE komplett schliessen | PnL: {event.details['realisedPnL']}")

            case BotAction.UPDATE_LEVERAGE:
                logger.info(f"[DRY RUN] -> WUERDE Leverage aendern: {event.details['oldLeverage']}x -> {event.details['newLeverage']}x")

            case BotAction.UPDATE_MARGIN:
                logger.info(f"[DRY RUN] -> WUERDE Margin anpassen: {event.details['oldMargin']} -> {event.details['newMargin']}")

            case _:
                logger.info(f"[DRY RUN] -> Unbekannte Aktion: {event.action}")

        logger.info("")


# ============================================================================
# LIVE — Events auf Kunden-Accounts ausfuehren
# ============================================================================

async def process_events_live(events: list[ParsedEvent]) -> None:
    """Live: Events auf alle Kunden-Accounts ausfuehren."""
    if not events:
        return

    engine.master_balance = parser.master_balance

    # Signal Bot: Ganzen Batch senden (mergt SL/TP in Open-Nachrichten)
    asyncio.create_task(signal_bot.process_event_batch(events))

    for event in events:
        logger.info("")
        logger.info("=" * 50)
        logger.info(f"[LIVE] {event.action.value} | {event.symbol}")
        logger.info(f"Details: {json.dumps(event.details, indent=2, default=str)}")
        logger.info("=" * 50)

        # Telegram: Master-Trade Alerts (Team-intern)
        await _send_master_alert(event)

        try:
            await engine.execute(event)
        except Exception as e:
            logger.error(f"[LIVE] Execution Fehler: {e}")
            await telegram.error(f"Execution Fehler: {event.action.value} {event.symbol}\n{e}")


async def _send_master_alert(event: ParsedEvent) -> None:
    """Telegram Alert + Master-Trade-Historie fuer Master-Trade Events."""
    d = event.details

    if event.action == BotAction.TRADE_FILLED:
        closed_pnl = float(d.get("closedPnL", 0) or 0)
        if closed_pnl == 0:
            # Neuer Trade
            sl_tp = {}
            order_id = d.get("orderID", "")
            if order_id:
                sl_tp = parser.get_sl_tp_for_position(order_id)
            await telegram.master_trade_opened(
                symbol=event.symbol,
                side=d.get("side", "Buy"),
                entry_price=d.get("execPrice", "?"),
                sl=sl_tp.get("stopLoss", ""),
                tp=sl_tp.get("takeProfit", ""),
            )

            # Master-Trade-Historie speichern
            db.save_master_trade(
                position_id=order_id,
                symbol=event.symbol,
                side=d.get("side", "Buy"),
                action="OPEN",
                qty=float(d.get("execQty", 0) or 0),
                price=float(d.get("execPrice", 0) or 0),
            )

    elif event.action == BotAction.CLOSE_TRADE:
        pnl = d.get("realisedPnL", "")
        pnl_float = float(pnl) if pnl else 0
        pnl_percent = ""
        # Prozentsatz berechnen falls moeglich
        entry = float(d.get("avgEntryPrice", 0) or 0)
        exit_price = float(d.get("markPrice", 0) or 0)
        if entry > 0 and exit_price > 0:
            side = d.get("side", "Buy")
            if side == "Buy":
                pnl_percent = f"{((exit_price - entry) / entry * 100):.2f}"
            else:
                pnl_percent = f"{((entry - exit_price) / entry * 100):.2f}"

        await telegram.master_trade_closed(
            symbol=event.symbol,
            side=d.get("side", "Buy"),
            pnl=pnl,
            pnl_percent=pnl_percent,
        )

        # Master-Trade-Historie speichern
        db.save_master_trade(
            position_id=d.get("positionID", ""),
            symbol=event.symbol,
            side=d.get("side", "Buy"),
            action="CLOSE",
            qty=float(d.get("previousSize", 0) or 0),
            pnl=pnl_float,
        )

    elif event.action == BotAction.SCALE_OUT:
        previous = float(d.get("previousSize", 0) or 0)
        new = float(d.get("newSize", 0) or 0)
        if previous > 0:
            pct = ((previous - new) / previous) * 100
            await telegram.master_trade_closed(
                symbol=event.symbol,
                side=d.get("side", "Buy"),
                close_type=f"{pct:.0f}% geschlossen",
            )

        # Master-Trade-Historie speichern
        pnl_float = float(d.get("realisedPnL", 0) or 0)
        db.save_master_trade(
            position_id=d.get("positionID", ""),
            symbol=event.symbol,
            side=d.get("side", "Buy"),
            action="SCALE_OUT",
            qty=previous - new,
            pnl=pnl_float,
        )

    elif event.action == BotAction.SCALE_IN:
        # Scale In auch in Master-Historie
        db.save_master_trade(
            position_id=d.get("positionID", ""),
            symbol=event.symbol,
            side=d.get("side", "Buy"),
            action="SCALE_IN",
            qty=d.get("newSize", 0) - d.get("previousSize", 0),
        )


# ============================================================================
# EVENT HANDLER
# ============================================================================

def on_perp_order(data: dict[str, Any]) -> None:
    """perpOrder Events verarbeiten."""
    is_snapshot = data.get("_type") == "snapshot"

    if is_snapshot:
        logger.info("--- perpOrder.update (SNAPSHOT — nur State-Aufbau, keine Execution) ---")
    else:
        logger.info("--- perpOrder.update empfangen ---")

    open_orders: list[PerpOrder] = data.get("open", [])
    closed_orders: list[PerpOrder] = data.get("closed", [])
    fills: list[PerpFill] = data.get("fills", [])

    if open_orders:
        logger.info(f"  Aktive Orders: {len(open_orders)}")
        for order in open_orders:
            logger.info(
                f"    {order.side} {order.symbol} | Qty: {order.orderQty} "
                f"@ {order.price} | Status: {order.ordStatus} | Typ: {order.ordType}"
            )

    if closed_orders:
        logger.info(f"  Geschlossene Orders: {len(closed_orders)}")
        for order in closed_orders:
            logger.info(
                f"    {order.side} {order.symbol} | Status: {order.ordStatus} "
                f"| OrderID: {order.orderID}"
            )

    if fills:
        logger.info(f"  Fills: {len(fills)}")
        for fill in fills:
            logger.info(
                f"    {fill.side} {fill.symbol} | {fill.execQty} "
                f"@ {fill.execPrice} | Fee: {fill.execFee} | PnL: {fill.closedPnL}"
            )

    # Parser IMMER aufrufen (State aufbauen), aber nur bei Incremental ausfuehren
    events = parser.parse_order_update(data)

    if is_snapshot:
        logger.info(f"  [SNAPSHOT] {len(events)} Events erkannt — NICHT ausgefuehrt")
        return

    if DRY_RUN:
        process_events_dry_run(events)
    else:
        asyncio.get_event_loop().create_task(process_events_live(events))


def on_perp_position(data: dict[str, Any]) -> None:
    """perpPosition Events verarbeiten."""
    is_snapshot = data.get("_type") == "snapshot"
    positions: list[PerpPosition] = data.get("positions", [])

    if is_snapshot:
        logger.info("--- perpPosition.update (SNAPSHOT — nur State-Aufbau, keine Execution) ---")
    else:
        logger.info("--- perpPosition.update empfangen ---")

    for pos in positions:
        size = float(pos.size) if pos.size else 0.0
        if size > 0:
            logger.info(
                f"  {pos.side} {pos.symbol} | Size: {pos.size} | "
                f"Entry: {pos.avgEntryPrice} | Leverage: {pos.leverage}x | "
                f"uPnL: {pos.unrealisedPnL}"
            )
        else:
            logger.info(f"  {pos.symbol} — keine offene Position")

    # Mark-Preise + Master-Positionen in DB speichern (fuer Dashboard)
    mark_prices = {}
    master_positions = []
    for pos in positions:
        size = float(pos.size) if pos.size else 0.0
        mp = float(pos.markPrice) if pos.markPrice else 0.0
        entry = float(pos.avgEntryPrice) if pos.avgEntryPrice else 0.0
        if mp > 0 and pos.symbol:
            mark_prices[pos.symbol] = mp
        lev = float(pos.leverage) if pos.leverage else 0.0
        if size > 0 and pos.symbol:
            master_positions.append({
                "symbol": pos.symbol,
                "side": pos.side,
                "size": size,
                "entry": entry,
                "mark": mp,
                "leverage": lev,
            })
    if mark_prices:
        db.update_mark_prices(mark_prices)
    db.update_master_positions(master_positions)

    events = parser.parse_position_update(positions)

    if is_snapshot:
        logger.info(f"  [SNAPSHOT] {len(events)} Events erkannt — NICHT ausgefuehrt")

        # Signal-Display-Names gegen echte offene Positionen abgleichen.
        # Faengt verwaiste Karteileichen ab (z.B. Close waehrend Downtime verpasst).
        # NUR im Snapshot (vollstaendige Positionsliste) — niemals inkrementell!
        live_position_ids = [
            pos.positionID for pos in positions
            if pos.positionID and float(pos.size or 0) > 0
        ]
        orphaned = db.reconcile_signal_display_names(live_position_ids)
        if orphaned:
            names = ", ".join(o["display_name"] for o in orphaned)
            logger.info(f"[RECON] {len(orphaned)} verwaiste Signal-Name(n) deaktiviert: {names}")

        # Offene Positionen + zugeordnete SL/TP-Orders loggen (Transparenz/Diagnose)
        for pos in positions:
            if pos.positionID and float(pos.size or 0) > 0:
                sl_tp = parser.get_sl_tp_for_position(pos.positionID)
                dname = db.get_signal_display_name(pos.positionID) or "—"
                logger.info(
                    f"[POS-CHECK] {pos.side} {pos.symbol} | PosID: {pos.positionID[:12]} | "
                    f"Name: {dname} | SL: {sl_tp.get('stopLoss','—')} | TP: {sl_tp.get('takeProfit','—')}"
                )

        # Reconciliation nach Position-Snapshot starten
        global _reconciliation_pending
        if _reconciliation_pending:
            _reconciliation_pending = False
            logger.info("[RECON] Position-Snapshot empfangen — starte Abgleich...")
            asyncio.get_event_loop().create_task(engine.reconcile())

        return

    if DRY_RUN:
        process_events_dry_run(events)
    else:
        asyncio.get_event_loop().create_task(process_events_live(events))


def on_perp_account(data: dict[str, Any]) -> None:
    """perpAccount Events verarbeiten."""
    is_snapshot = data.get("_type") == "snapshot"
    accounts: list[PerpAccount] = data.get("accounts", [])

    if is_snapshot:
        logger.info("--- perpAccount.update (SNAPSHOT — nur State-Aufbau) ---")
    else:
        logger.info("--- perpAccount.update empfangen ---")

    for acc in accounts:
        logger.info(
            f"  Balance: {acc.accountBalance} {acc.currency} | "
            f"Used: {acc.usedBalance} | Bonus: {acc.bonusBalance}"
        )

    parser.parse_account_update(accounts)

    # Master Balance an Execution Engine weitergeben
    if not DRY_RUN:
        engine.master_balance = parser.master_balance

    # Master Balance in DB persistieren (fuer Dashboard %-Berechnung)
    if parser.master_balance > 0:
        try:
            db.update_master_balance(parser.master_balance)
        except Exception:
            pass


# ============================================================================
# MAIN
# ============================================================================

async def main() -> None:
    """Hauptfunktion — WebSocket verbinden und auf Events warten."""

    mode = "DRY RUN" if DRY_RUN else "LIVE"

    logger.info("=" * 60)
    logger.info(f"COPY TRADING BOT — {mode}")
    logger.info("=" * 60)
    logger.info(f"Umgebung: {config.env}")
    logger.info(f"WebSocket: {config.ws_url}")
    logger.info(f"REST API: {config.rest_url}")
    logger.info(f"Master UID: {config.master_uid}")
    logger.info(f"Log Level: {config.log_level}")
    logger.info(f"Modus: {mode}")
    logger.info(f"Datenbank: {db._db_path}")

    # Aktive Mappings aus DB laden und loggen
    active_mappings = db.get_all_active_mappings()
    if active_mappings:
        logger.info(f"Aktive Position-Mappings: {len(active_mappings)}")
        for m in active_mappings:
            logger.info(
                f"  {m['symbol']} | Master: {m['master_position_id'][:8]}... -> "
                f"Kunde: {m['customer_id']} ({m['customer_position_id'][:8]}...)"
            )
    else:
        logger.info("Keine aktiven Position-Mappings in DB")

    logger.info("=" * 60)

    if DRY_RUN:
        logger.info(
            f"Simulierter Kunde: {SIMULATED_CUSTOMER['id']} "
            f"mit {SIMULATED_CUSTOMER['balance']} USDT Balance"
        )
    else:
        customers = engine.get_active_customers()
        logger.info(f"Aktive Kunden: {len(customers)}")
        for c in customers:
            logger.info(f"  - {c.name} (UID: {c.uid}) | Balance wird via WebSocket geladen...")

        # Kunden-WebSockets verbinden und Balance holen
        if customer_ws_connections:
            logger.info("Verbinde Kunden-WebSockets fuer Balance-Tracking...")
            for cws in customer_ws_connections:
                success = await cws.connect()
                if success:
                    # Warten bis Snapshot-Balance da ist (max 5 Sekunden)
                    customer = engine._customers.get(cws._customer_id)
                    for _ in range(10):
                        await asyncio.sleep(0.5)
                        # Balance-Nachrichten verarbeiten
                        try:
                            raw = await asyncio.wait_for(cws._ws.recv(), timeout=0.5)
                            msg = json.loads(raw)
                            cws._handle_message(msg)
                        except asyncio.TimeoutError:
                            pass
                        if cws.balance > 0:
                            break

                    if customer and cws.balance > 0:
                        customer.balance = cws.balance
                        # Balance in DB persistieren (fuer Dashboard)
                        try:
                            db.update_customer_balance(cws._customer_id, cws.balance)
                        except Exception:
                            pass
                        logger.info(
                            f"  {customer.name}: Balance geladen: {cws.balance:.4f} USDT "
                            f"(Free: {cws.free_balance:.4f})"
                        )
                    elif customer:
                        logger.warning(f"  {customer.name}: Balance ist 0 — pruefen!")
                else:
                    logger.error(f"  {cws._customer_name}: WebSocket-Verbindung fehlgeschlagen")

        # Alle Kunden automatisch auf Multi-Trade Modus stellen
        logger.info("Stelle Kunden auf Multi-Trade Modus...")
        for c in customers:
            if c.client:
                try:
                    result = await c.client.switch_position_mode("BTCUSDT", "Multi")
                    if result.get("error"):
                        err = result["error"]
                        code = err.get("code", 0)
                        msg = err.get("message", "?")
                        if code == 2136:
                            # Offene Positionen vorhanden — Kunde kann nicht aktiviert werden
                            c.active = False
                            logger.error(
                                f"  {c.name}: DEAKTIVIERT — Offene Positionen vorhanden. "
                                f"Kunde muss alle Positionen schliessen bevor der Bot starten kann."
                            )
                        elif "invalid" in msg.lower() or "already" in msg.lower():
                            # Bereits im Multi-Trade Modus oder anderer harmloser Fehler
                            logger.info(f"  {c.name}: Bereits im Multi-Trade Modus")
                        else:
                            logger.warning(f"  {c.name}: Modus-Wechsel: [{code}] {msg}")
                    else:
                        logger.info(f"  {c.name}: Multi-Trade Modus aktiviert")
                except Exception as e:
                    c.active = False
                    logger.error(f"  {c.name}: DEAKTIVIERT — Fehler: {e}")

    logger.info("-" * 60)

    # Callbacks registrieren
    ws.on_perp_order(on_perp_order)
    ws.on_perp_position(on_perp_position)
    ws.on_perp_account(on_perp_account)

    # Echtzeit-Ticker fuer Dashboard-Preise
    import time as _time
    _last_ticker_db_write = 0.0

    def on_perp_ticker(data: dict[str, Any]) -> None:
        """perpTicker.update — Echtzeit-Preise in DB schreiben (max alle 2s)."""
        nonlocal _last_ticker_db_write
        now = _time.time()
        if now - _last_ticker_db_write < 2.0:
            return  # Throttle: max alle 2 Sekunden in DB schreiben

        prices = {}
        # Daten koennen als dict (einzelnes Symbol) oder als Liste kommen
        tickers = data if isinstance(data, list) else [data]
        for t in tickers:
            symbol = t.get("symbol", "")
            mark = float(t.get("markPrice", 0) or t.get("lastPrice", 0) or 0)
            if symbol and mark > 0:
                prices[symbol] = mark
        if prices:
            db.update_mark_prices(prices)
            _last_ticker_db_write = now

    ws.on_perp_ticker(on_perp_ticker)

    # Ticker-Subscription nach Verbindung starten
    ticker_symbols = list(set(m["symbol"] for m in active_mappings if m.get("symbol")))
    if not ticker_symbols:
        ticker_symbols = ["BTCUSDT"]  # Mindestens BTC fuer Benchmark

    async def _subscribe_tickers_after_connect():
        """Warte bis verbunden, dann Ticker subscriben."""
        for _ in range(30):  # max 30 Sekunden warten
            await asyncio.sleep(1)
            if ws._is_authenticated:
                await ws.subscribe_ticker(ticker_symbols)
                return
        logger.warning("Ticker-Subscription: Timeout — nicht verbunden")

    asyncio.ensure_future(_subscribe_tickers_after_connect())

    # Reconnect Alert
    def on_ws_reconnect(reason: str) -> None:
        if not DRY_RUN:
            asyncio.ensure_future(telegram.ws_reconnect(reason))
            # Ticker nach Reconnect erneut subscriben
            asyncio.ensure_future(_subscribe_tickers_after_connect())
    ws.on_reconnect(on_ws_reconnect)

    # Reconciliation nach Snapshot ausfuehren (wird durch Flag gesteuert)
    if not DRY_RUN and active_mappings:
        global _reconciliation_pending
        _reconciliation_pending = True

    # Graceful Shutdown bei Ctrl+C
    loop = asyncio.get_running_loop()

    async def shutdown() -> None:
        logger.info("Shutdown — Verbindungen werden getrennt...")
        ws.disconnect()
        if not DRY_RUN:
            # Kunden-WebSockets trennen
            for cws in customer_ws_connections:
                await cws.disconnect()
            await engine.cleanup()
            await signal_bot.close()

    def shutdown_handler() -> None:
        asyncio.ensure_future(shutdown())

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, shutdown_handler)

    # Kunden-WebSockets als Hintergrund-Tasks starten
    cws_tasks = []
    for cws in customer_ws_connections:
        task = asyncio.create_task(_run_customer_ws(cws))
        cws_tasks.append(task)

    logger.info("Bot laeuft — warte auf Events vom Master-Account...")
    logger.info("Beenden mit Ctrl+C")

    # Telegram: Referenzen setzen fuer Statusbericht
    if not DRY_RUN:
        telegram._engine = engine
        telegram._parser = parser
        telegram._env = config.env
        telegram._ws_connected = True

        # Startup Alert + Polling starten
        await telegram.bot_started(config.env, len(engine.get_active_customers()))
        telegram.start_polling()

        # Signal Bot Debounce-Worker starten
        signal_bot.start()

    # Signal Bot auch im DRY RUN starten (Signale sollen immer gesendet werden)
    if DRY_RUN:
        signal_bot.start()

    # Auto-Reload: Neue Kunden alle 60 Sekunden pruefen
    if not DRY_RUN:
        asyncio.create_task(_auto_reload_customers())

    await ws.connect()


async def _auto_reload_customers() -> None:
    """Alle 60 Sekunden pruefen ob neue Kunden aktiviert wurden."""
    while True:
        await asyncio.sleep(60)
        try:
            known_ids = set(engine._customers.keys())
            new_customers = db.get_new_active_customers(known_ids)
            for c in new_customers:
                from execution import Customer
                customer = Customer(
                    id=c["id"],
                    name=c["name"],
                    uid=c["uid"],
                    api_key=c["api_key"],
                    api_secret=c["api_secret"],
                    balance=float(c.get("last_known_balance", 0) or 0),
                )
                engine.add_customer(customer)
                logger.info(f"[AUTO-RELOAD] Neuer Kunde geladen: {c['name']} ({c['id'][:8]}...)")

                # WebSocket fuer Balance-Tracking starten
                read_key = c.get("read_api_key", "")
                read_secret = c.get("read_api_secret", "")
                if read_key and read_secret:
                    cws = CustomerWebSocket(
                        ws_url=config.ws_url,
                        customer_id=c["id"],
                        customer_name=c["name"],
                        api_key=read_key,
                        api_secret=read_secret,
                    )
                    customer_ws_connections.append(cws)
                    asyncio.create_task(_run_customer_ws(cws))
                    logger.info(f"[AUTO-RELOAD] WebSocket gestartet fuer {c['name']}")
        except Exception as e:
            logger.debug(f"[AUTO-RELOAD] Fehler: {e}")


async def _run_customer_ws(cws: CustomerWebSocket) -> None:
    """
    Kunden-WebSocket im Hintergrund laufen lassen.
    Synchronisiert die Balance laufend in das Customer-Objekt.
    """
    customer = engine._customers.get(cws._customer_id)

    while True:
        try:
            if cws._ws and cws._running:
                raw = await asyncio.wait_for(cws._ws.recv(), timeout=15)
                msg = json.loads(raw)
                cws._handle_message(msg)

                # Balance live in Customer-Objekt synchronisieren
                if customer and cws.balance > 0:
                    old_balance = customer.balance
                    customer.balance = cws.balance

                    # Balance in DB persistieren (fuer Dashboard)
                    # Nur bei signifikanter Aenderung (> 0.01 USDT) um DB-Writes zu minimieren
                    if abs(cws.balance - old_balance) > 0.01:
                        try:
                            db.update_customer_balance(cws._customer_id, cws.balance)
                        except Exception:
                            pass  # DB-Write nicht kritisch
            else:
                # Reconnect
                success = await cws.connect()
                if not success:
                    await asyncio.sleep(5)

        except asyncio.TimeoutError:
            continue
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning(f"[WS:{cws._customer_name}] Fehler: {e}")
            cws._running = False
            await asyncio.sleep(5)


if __name__ == "__main__":
    asyncio.run(main())
