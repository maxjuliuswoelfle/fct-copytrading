"""
(C) bot_types.py — Alle Typen und Dataclasses fuer den Copy Trading Bot

Felder basieren auf den ECHTEN API-Responses von Levex (Stand 2026-05-08).
Jede Dataclass bildet exakt die Felder ab, die ueber WebSocket Push kommen.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# ============================================================================
# PERPETUAL ORDER — von perpOrder.update
# Echte orderKeys von der API (38 Felder)
# ============================================================================

@dataclass
class PerpOrder:
    userID: str = ""
    symbol: str = ""
    currency: str = ""
    side: str = ""            # "Buy" | "Sell"
    posSide: str = ""         # "Long" | "Short"
    action: str = ""          # "New" | "Cancel" | "Replace"
    actionBy: str = ""        # "ByUser" | "FromPosition"
    ordType: str = ""         # "Market" | "Limit" | "StopMarket" | "MarketIfTouched" etc.
    origOrdType: str = ""
    execInst: str = ""        # "ReduceOnly" etc.
    timeInForce: str = ""
    orderID: str = ""
    clOrdID: str = ""
    price: str = ""
    orderQty: str = ""
    ordStatus: str = ""       # "New", "Filled", "Canceled", "Untriggered" etc.
    leavesQty: str = ""
    execQty: str = ""
    cumQty: str = ""
    cumValue: str = ""
    activityID: str = ""
    positionID: str = ""
    positionName: str = ""
    execStatus: str = ""
    trigger: str = ""
    pegPriceType: str = ""
    pegOffsetPrice: str = ""
    stopDirection: str = ""
    stopPrice: str = ""       # SL-Preis bei StopMarket Orders
    tpTrigger: str = ""
    takeProfitPrice: str = ""
    slTrigger: str = ""
    stopLossPrice: str = ""
    cxlRejReason: str = ""
    errorCode: str = ""
    actionTimeNs: str = ""
    transactTimeNs: str = ""
    createdTimeNs: str = ""


# Keys-Array — nur als Fallback, im Normalfall nutzen wir die Keys von der API
PERP_ORDER_KEYS: list[str] = [
    "userID", "symbol", "currency", "side", "posSide", "action", "actionBy",
    "ordType", "origOrdType", "execInst", "timeInForce", "orderID", "clOrdID",
    "price", "orderQty", "ordStatus", "leavesQty", "execQty", "cumQty", "cumValue",
    "activityID", "positionID", "positionName", "execStatus", "trigger",
    "pegPriceType", "pegOffsetPrice", "stopDirection", "stopPrice", "tpTrigger",
    "takeProfitPrice", "slTrigger", "stopLossPrice", "cxlRejReason", "errorCode",
    "actionTimeNs", "transactTimeNs", "createdTimeNs",
]


# ============================================================================
# PERPETUAL FILL — Teil von perpOrder.update
# Echte fillKeys von der API (27 Felder)
# ============================================================================

@dataclass
class PerpFill:
    userID: str = ""
    symbol: str = ""
    currency: str = ""
    side: str = ""
    posSide: str = ""
    ordType: str = ""
    orderID: str = ""
    clOrdID: str = ""
    price: str = ""
    orderQty: str = ""
    cumQty: str = ""
    activityID: str = ""
    positionID: str = ""
    positionName: str = ""
    execStatus: str = ""
    execID: str = ""
    tradeType: str = ""
    execPrice: str = ""
    execQty: str = ""
    execValue: str = ""
    execFee: str = ""
    closedSize: str = ""
    bonusChangeAmount: str = ""
    closedPnL: str = ""
    execSeq: str = ""
    transactTimeNs: str = ""
    createdTimeNs: str = ""


PERP_FILL_KEYS: list[str] = [
    "userID", "symbol", "currency", "side", "posSide", "ordType", "orderID",
    "clOrdID", "price", "orderQty", "cumQty", "activityID", "positionID",
    "positionName", "execStatus", "execID", "tradeType", "execPrice",
    "execQty", "execValue", "execFee", "closedSize", "bonusChangeAmount",
    "closedPnL", "execSeq", "transactTimeNs", "createdTimeNs",
]


# ============================================================================
# PERPETUAL POSITION — von perpPosition.update
# Echte keys von der API
# ============================================================================

@dataclass
class PerpPosition:
    userID: str = ""
    symbol: str = ""
    currency: str = ""
    side: str = ""            # "Buy" | "Sell" | "None"
    posMode: str = ""         # "Hedged"
    posSide: str = ""         # "Long" | "Short"
    posStatus: str = ""
    marginMode: str = ""
    leverage: str = ""
    displayLeverage: str = ""
    riskLimit: str = ""
    size: str = ""
    value: str = ""
    initMarginRate: str = ""
    maintMarginRate: str = ""
    activityID: str = ""
    avgEntryPrice: str = ""
    posCost: str = ""
    posBalance: str = ""
    posMargin: str = ""
    bankruptPrice: str = ""
    liquidationPrice: str = ""
    orderCost: str = ""
    adjustedPosBalance: str = ""
    buyValueCostRate: str = ""
    sellValueCostRate: str = ""
    markPrice: str = ""
    unrealisedPnL: str = ""
    realisedPnL: str = ""
    positionID: str = ""
    positionName: str = ""
    term: str = ""
    transactTimeNs: str = ""
    createdTimeNs: str = ""
    updatedTimeNs: str = ""


PERP_POSITION_KEYS: list[str] = [
    "userID", "symbol", "currency", "side", "posMode", "posSide", "posStatus",
    "marginMode", "leverage", "displayLeverage", "riskLimit", "size", "value",
    "initMarginRate", "maintMarginRate", "activityID", "avgEntryPrice", "posCost",
    "posBalance", "posMargin", "bankruptPrice", "liquidationPrice", "orderCost",
    "adjustedPosBalance", "buyValueCostRate", "sellValueCostRate", "markPrice",
    "unrealisedPnL", "realisedPnL", "positionID", "positionName", "term",
    "transactTimeNs", "createdTimeNs", "updatedTimeNs",
]


# ============================================================================
# PERPETUAL ACCOUNT — von perpAccount.update
# Echte keys von der API (14 Felder)
# ============================================================================

@dataclass
class PerpAccount:
    userID: str = ""
    currency: str = ""
    accountBalance: str = ""
    usedBalance: str = ""
    availableBalance: str = ""
    unrealizedPnL: str = ""
    bonusBalance: str = ""
    activityBonus: str = ""
    usedActivityBonus: str = ""
    availableActivityBonus: str = ""
    defaultPosMode: str = ""
    bonusID: str = ""
    makerFeeRate: str = ""
    takerFeeRate: str = ""


PERP_ACCOUNT_KEYS: list[str] = [
    "userID", "currency", "accountBalance", "usedBalance", "availableBalance",
    "unrealizedPnL", "bonusBalance", "activityBonus", "usedActivityBonus",
    "availableActivityBonus", "defaultPosMode", "bonusID", "makerFeeRate",
    "takerFeeRate",
]


# ============================================================================
# BOT ACTIONS — Was der Bot als Reaktion auf Events tun kann
# ============================================================================

class BotAction(str, Enum):
    """Alle moeglichen Aktionen die der Bot erkennen und ausfuehren kann."""
    OPEN_TRADE = "OPEN_TRADE"               # Neuer Trade eroeffnet
    TRADE_FILLED = "TRADE_FILLED"           # Order wurde gefuellt
    AMEND_TRADE = "AMEND_TRADE"             # Bestehende Order geaendert
    CANCEL_TRADE = "CANCEL_TRADE"           # Order storniert
    SET_SL = "SET_SL"                       # Stop-Loss gesetzt/geaendert
    SET_TP = "SET_TP"                       # Take-Profit gesetzt/geaendert
    CANCEL_SL = "CANCEL_SL"                 # Stop-Loss entfernt
    CANCEL_TP = "CANCEL_TP"                 # Take-Profit entfernt
    SCALE_IN = "SCALE_IN"                   # Position vergroessert (nachgekauft)
    SCALE_OUT = "SCALE_OUT"                 # Position teilweise geschlossen
    CLOSE_TRADE = "CLOSE_TRADE"             # Position komplett geschlossen
    UPDATE_LEVERAGE = "UPDATE_LEVERAGE"     # Hebel geaendert
    UPDATE_MARGIN = "UPDATE_MARGIN"         # Margin angepasst
    RENAME_POSITION = "RENAME_POSITION"     # Position umbenannt


# ============================================================================
# PARSED EVENT — Ergebnis der Event-Analyse
# ============================================================================

@dataclass
class ParsedEvent:
    """
    Ein geparster Event mit der erkannten Aktion, dem Symbol und allen Details.
    Das ist die standardisierte Ausgabe des Parsers — darauf baut die Execution Engine auf.
    """
    action: BotAction
    symbol: str
    details: dict[str, Any]
    timestamp: float  # Epoch in Millisekunden
