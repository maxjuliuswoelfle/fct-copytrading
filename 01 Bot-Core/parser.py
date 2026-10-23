"""
(C) parser.py — Event-Parser fuer den Copy Trading Bot

Levex Besonderheiten:
- SL/TP werden als SEPARATE Orders gesendet (StopMarket = SL, MarketIfTouched = TP)
- Diese haben actionBy="FromPosition" und execInst="ReduceOnly"
- Multi-Trade Mode: Mehrere Positionen pro Symbol moeglich -> Tracking per positionID
"""

import time
from logger_setup import logger
from bot_types import (
    PerpOrder, PerpFill, PerpPosition, PerpAccount,
    BotAction, ParsedEvent,
)


class OrderParser:

    def __init__(self) -> None:
        self._active_orders: dict[str, PerpOrder] = {}
        # Multi-Trade Mode: Positionen per positionID tracken (nicht mehr per symbol+posSide)
        self._positions: dict[str, PerpPosition] = {}
        # Letzter bekannter SL/TP pro positionID — ueberlebt das Entfernen der Order,
        # damit beim Schliessen (SL/TP-Trigger entfernt die Order!) noch erkannt wird,
        # ob ein SL/TP getroffen wurde. Wird bei manuellem Cancel geleert, beim Trigger behalten.
        self._last_sl_tp: dict[str, dict[str, str]] = {}
        self.master_balance: float = 0.0

    # --------------------------------------------------------------------------
    # ORDER UPDATES
    # --------------------------------------------------------------------------

    def parse_order_update(self, data: dict) -> list[ParsedEvent]:
        events: list[ParsedEvent] = []
        now = time.time()
        amended_ids: set[str] = set()  # OrderIDs die in diesem Batch geaendert wurden

        for order in data.get("open", []):
            existing = self._active_orders.get(order.orderID)
            is_sl_tp = self._is_sl_tp_order(order)

            if not existing:
                if is_sl_tp:
                    action = BotAction.SET_SL if order.ordType == "StopMarket" else BotAction.SET_TP
                    logger.info(
                        f"{action.value}: {order.symbol} | Typ: {order.ordType} | "
                        f"Trigger-Preis: {order.stopPrice} | Richtung: {order.stopDirection}"
                    )
                    events.append(ParsedEvent(
                        action=action, symbol=order.symbol, timestamp=now,
                        details={"orderID": order.orderID, "ordType": order.ordType,
                                 "stopPrice": order.stopPrice, "positionID": order.positionID},
                    ))
                else:
                    logger.info(
                        f"Neue Order: {order.side} {order.symbol} | "
                        f"Qty: {order.orderQty} @ {order.price} | Typ: {order.ordType}"
                    )
                    # Limit-/Market-Orders koennen SL/TP DIREKT am Order-Objekt tragen
                    # (stopLossPrice / takeProfitPrice) — nicht nur als separate Orders.
                    # Diese mitgeben, sonst fehlen sie im Signal: bei einer frischen
                    # Limit-Order existiert noch keine Position und keine separate
                    # SL/TP-Order, also wuerde get_sl_tp_for_position() nichts finden.
                    open_details = {"orderID": order.orderID, "side": order.side,
                                    "ordType": order.ordType, "price": order.price,
                                    "orderQty": order.orderQty, "posSide": order.posSide,
                                    "positionID": order.positionID}
                    if order.stopLossPrice:
                        open_details["stopLoss"] = order.stopLossPrice
                    if order.takeProfitPrice:
                        open_details["takeProfit"] = order.takeProfitPrice
                    # Attached SL/TP auch im Position-State merken (ueberlebt Order-Removal)
                    if order.positionID and (order.stopLossPrice or order.takeProfitPrice):
                        slot = self._last_sl_tp.setdefault(order.positionID, {})
                        if order.stopLossPrice:
                            slot["stopLoss"] = order.stopLossPrice
                        if order.takeProfitPrice:
                            slot["takeProfit"] = order.takeProfitPrice
                    events.append(ParsedEvent(
                        action=BotAction.OPEN_TRADE, symbol=order.symbol, timestamp=now,
                        details=open_details,
                    ))
            else:
                if is_sl_tp and existing.stopPrice != order.stopPrice:
                    action = BotAction.SET_SL if order.ordType == "StopMarket" else BotAction.SET_TP
                    logger.info(f"SL/TP verschoben: {order.symbol} | {existing.stopPrice} -> {order.stopPrice}")
                    events.append(ParsedEvent(
                        action=action, symbol=order.symbol, timestamp=now,
                        details={"orderID": order.orderID, "oldStopPrice": existing.stopPrice,
                                 "newStopPrice": order.stopPrice, "positionID": order.positionID},
                    ))
                    amended_ids.add(order.orderID)
                elif not is_sl_tp and (existing.price != order.price or existing.orderQty != order.orderQty):
                    logger.info(f"Order geaendert: {order.symbol} | Preis: {existing.price} -> {order.price}")
                    events.append(ParsedEvent(
                        action=BotAction.AMEND_TRADE, symbol=order.symbol, timestamp=now,
                        details={"orderID": order.orderID, "oldPrice": existing.price,
                                 "newPrice": order.price, "oldQty": existing.orderQty, "newQty": order.orderQty,
                                 "positionID": order.positionID, "side": order.side,
                                 "posSide": order.posSide, "ordType": order.ordType},
                    ))
                    amended_ids.add(order.orderID)

            # Letzten bekannten SL/TP-Wert pro Position merken (ueberlebt Order-Removal beim Trigger)
            if is_sl_tp and order.positionID and order.stopPrice:
                slot = self._last_sl_tp.setdefault(order.positionID, {})
                if order.ordType == "StopMarket":
                    slot["stopLoss"] = order.stopPrice
                elif order.ordType == "MarketIfTouched":
                    slot["takeProfit"] = order.stopPrice

            self._active_orders[order.orderID] = order

        for order in data.get("closed", []):
            if order.ordStatus in ("Canceled", "Rejected", "Deactivated"):
                # Cancel-als-Teil-eines-Amends ignorieren (Levex sendet Cancel+Replace)
                if order.orderID in amended_ids:
                    logger.debug(f"Cancel ignoriert (Teil von Amend): {order.orderID}")
                    self._active_orders.pop(order.orderID, None)
                    continue
                if self._is_sl_tp_order(order):
                    action = BotAction.CANCEL_SL if order.ordType == "StopMarket" else BotAction.CANCEL_TP
                    logger.info(f"{action.value}: {order.symbol} | OrderID: {order.orderID}")
                    # Manueller Cancel (nicht getriggert) → gemerkten Wert loeschen,
                    # damit ein spaeterer manueller Close nicht faelschlich als SL/TP-Hit gilt.
                    if order.positionID and order.positionID in self._last_sl_tp:
                        key = "stopLoss" if order.ordType == "StopMarket" else "takeProfit"
                        self._last_sl_tp[order.positionID].pop(key, None)
                else:
                    action = BotAction.CANCEL_TRADE
                    logger.info(f"Order {order.ordStatus}: {order.side} {order.symbol}")
                events.append(ParsedEvent(
                    action=action, symbol=order.symbol, timestamp=now,
                    details={"orderID": order.orderID, "ordStatus": order.ordStatus,
                             "ordType": order.ordType, "price": order.price,
                             "positionID": order.positionID, "side": order.side,
                             "posSide": order.posSide},
                ))
            self._active_orders.pop(order.orderID, None)

        for fill in data.get("fills", []):
            logger.info(f"Fill: {fill.side} {fill.symbol} | {fill.execQty} @ {fill.execPrice} | Fee: {fill.execFee} | Type: {fill.ordType}")
            events.append(ParsedEvent(
                action=BotAction.TRADE_FILLED, symbol=fill.symbol, timestamp=now,
                details={"orderID": fill.orderID, "side": fill.side, "execPrice": fill.execPrice,
                         "execQty": fill.execQty, "execFee": fill.execFee, "closedPnL": fill.closedPnL,
                         "ordType": fill.ordType, "positionID": fill.positionID, "posSide": fill.posSide},
            ))

        return events

    # --------------------------------------------------------------------------
    # POSITION UPDATES
    # --------------------------------------------------------------------------

    def parse_position_update(self, positions: list[PerpPosition]) -> list[ParsedEvent]:
        events: list[ParsedEvent] = []
        now = time.time()

        for pos in positions:
            # Multi-Trade Mode: positionID ist der eindeutige Schluessel
            # Fallback auf (symbol, posSide) falls positionID leer (Hedged Mode Kompatibilitaet)
            key = pos.positionID if pos.positionID else f"{pos.symbol}_{pos.posSide}"
            existing = self._positions.get(key)
            new_size = float(pos.size) if pos.size else 0.0

            if existing:
                old_size = float(existing.size) if existing.size else 0.0

                if new_size == 0 and old_size > 0:
                    logger.info(f"Position geschlossen: {pos.symbol} ({pos.posSide}) [PosID: {pos.positionID}] | War: {old_size}")
                    events.append(ParsedEvent(action=BotAction.CLOSE_TRADE, symbol=pos.symbol, timestamp=now,
                        details={"previousSize": old_size, "posSide": pos.posSide,
                                 "positionID": pos.positionID, "realisedPnL": pos.realisedPnL,
                                 "side": existing.side, "avgEntryPrice": existing.avgEntryPrice,
                                 "markPrice": pos.markPrice}))

                elif new_size > old_size and old_size > 0:
                    logger.info(f"Scale In: {pos.symbol} ({pos.posSide}) [PosID: {pos.positionID}] | {old_size} -> {new_size}")
                    events.append(ParsedEvent(action=BotAction.SCALE_IN, symbol=pos.symbol, timestamp=now,
                        details={"previousSize": old_size, "newSize": new_size,
                                 "positionID": pos.positionID, "avgEntryPrice": pos.avgEntryPrice}))

                elif new_size < old_size and new_size > 0:
                    logger.info(f"Scale Out: {pos.symbol} ({pos.posSide}) [PosID: {pos.positionID}] | {old_size} -> {new_size}")
                    events.append(ParsedEvent(action=BotAction.SCALE_OUT, symbol=pos.symbol, timestamp=now,
                        details={"previousSize": old_size, "newSize": new_size,
                                 "positionID": pos.positionID, "realisedPnL": pos.realisedPnL}))

                if existing.leverage != pos.leverage and new_size > 0:
                    logger.info(f"Leverage: {pos.symbol} [PosID: {pos.positionID}] | {existing.leverage}x -> {pos.leverage}x")
                    events.append(ParsedEvent(action=BotAction.UPDATE_LEVERAGE, symbol=pos.symbol, timestamp=now,
                        details={"oldLeverage": existing.leverage, "newLeverage": pos.leverage,
                                 "positionID": pos.positionID}))

                if existing.positionName != pos.positionName and pos.positionName and new_size > 0:
                    logger.info(f"Position umbenannt: {pos.symbol} [PosID: {pos.positionID}] | '{existing.positionName}' -> '{pos.positionName}'")
                    events.append(ParsedEvent(action=BotAction.RENAME_POSITION, symbol=pos.symbol, timestamp=now,
                        details={"positionID": pos.positionID, "oldName": existing.positionName,
                                 "newName": pos.positionName, "posSide": pos.posSide}))

                if existing.posMargin != pos.posMargin and existing.size == pos.size and new_size > 0:
                    logger.info(f"Margin: {pos.symbol} [PosID: {pos.positionID}] | {existing.posMargin} -> {pos.posMargin}")
                    events.append(ParsedEvent(action=BotAction.UPDATE_MARGIN, symbol=pos.symbol, timestamp=now,
                        details={"oldMargin": existing.posMargin, "newMargin": pos.posMargin,
                                 "positionID": pos.positionID}))
            else:
                if new_size > 0:
                    logger.info(f"Neue Position: {pos.side} {pos.symbol} ({pos.posSide}) [PosID: {pos.positionID}] | Size: {new_size} | Leverage: {pos.leverage}x")

            self._positions[key] = pos

        return events

    # --------------------------------------------------------------------------
    # ACCOUNT UPDATES
    # --------------------------------------------------------------------------

    def parse_account_update(self, accounts: list[PerpAccount]) -> None:
        for acc in accounts:
            balance = float(acc.accountBalance) if acc.accountBalance else 0.0
            if balance != self.master_balance:
                logger.info(f"Master Balance: {self.master_balance} -> {balance} {acc.currency}")
                self.master_balance = balance

    # --------------------------------------------------------------------------
    # HELPER
    # --------------------------------------------------------------------------

    def get_sl_tp_for_position(self, position_id: str) -> dict[str, str]:
        """
        SL/TP-Preise fuer eine Master-Position aus den aktiven Orders ableiten.
        Returns: {"stopLoss": "80000", "takeProfit": "85000"} — nur gesetzte Werte.
        """
        result: dict[str, str] = {}
        for order in self._active_orders.values():
            if order.positionID != position_id:
                continue
            if not self._is_sl_tp_order(order):
                continue
            if order.ordType == "StopMarket" and order.stopPrice:
                result["stopLoss"] = order.stopPrice
            elif order.ordType == "MarketIfTouched" and order.stopPrice:
                result["takeProfit"] = order.stopPrice

        # Fallback auf zuletzt bekannten Wert: Beim SL/TP-Trigger wird die Order entfernt,
        # bevor das CLOSE-Event verarbeitet wird — sonst koennte ein getroffener SL/TP
        # nie als solcher erkannt werden (wuerde faelschlich als "manuell" gelten).
        last = self._last_sl_tp.get(position_id, {})
        if "stopLoss" not in result and last.get("stopLoss"):
            result["stopLoss"] = last["stopLoss"]
        if "takeProfit" not in result and last.get("takeProfit"):
            result["takeProfit"] = last["takeProfit"]
        return result

    def get_leverage_for_position(self, position_id: str) -> str:
        """Leverage fuer eine Master-Position aus dem Position-State holen."""
        pos = self._positions.get(position_id)
        if pos and pos.leverage:
            return pos.leverage
        # Fallback: alle Positionen nach positionID durchsuchen
        for pos in self._positions.values():
            if pos.positionID == position_id and pos.leverage:
                return pos.leverage
        return ""

    def get_liquidation_for_position(self, position_id: str) -> str:
        """Liquidationspreis fuer eine Master-Position aus dem Position-State holen.
        Leer wenn keine (offene) Position existiert (z.B. nicht gefuellte Limit-Order)."""
        pos = self._positions.get(position_id)
        if pos and pos.liquidationPrice:
            return pos.liquidationPrice
        # Fallback: alle Positionen nach positionID durchsuchen
        for pos in self._positions.values():
            if pos.positionID == position_id and pos.liquidationPrice:
                return pos.liquidationPrice
        return ""

    def get_pos_margin_for_position(self, position_id: str) -> str:
        """Echte Positionsmarge (posMargin) fuer eine Master-Position aus dem Position-State holen.
        Leer wenn keine (offene) Position existiert (z.B. nicht gefuellte Limit-Order)."""
        pos = self._positions.get(position_id)
        if pos and pos.posMargin:
            return pos.posMargin
        # Fallback: alle Positionen nach positionID durchsuchen
        for pos in self._positions.values():
            if pos.positionID == position_id and pos.posMargin:
                return pos.posMargin
        return ""

    def _is_sl_tp_order(self, order: PerpOrder) -> bool:
        return (order.actionBy == "FromPosition" or order.execInst == "ReduceOnly") \
            and order.ordType in ("StopMarket", "MarketIfTouched")

    def get_pending_limit_orders(self) -> list[dict]:
        """Alle aktuell wartenden Limit-Orders aus dem Order-State.

        Wird fuer die Tages-Uebersicht genutzt: Anders als das In-Memory-Dict
        des Signal-Bots ueberlebt dieser State einen Reconnect/Neustart, da der
        Parser bei jedem Snapshot neu aufgebaut wird. SL/TP-Orders und Nicht-Limit
        Orders werden ausgeschlossen.
        """
        result: list[dict] = []
        for order in self._active_orders.values():
            if order.ordType != "Limit":
                continue
            if self._is_sl_tp_order(order):
                continue
            result.append({
                "orderID": order.orderID,
                "symbol": order.symbol,
                "side": order.side,
                "posSide": order.posSide,
                "price": order.price,
                "positionID": order.positionID,
            })
        return result
