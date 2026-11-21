"""
(C) test_usdc_filter.py — Trockentest: USDC-Paare (private Trades) werden nicht gespiegelt

Regel (Max W., 2026-11-21): alle USDC-Paare = Max Steinauers private Trades,
alle USDT-Paare = Copy Trading. Der Filter sitzt am Eingang (websocket_client.py),
die Regel selbst in bot_types.is_private_pair.

Der Test schickt nachgestellte Levex-Nachrichten durch den ECHTEN WebSocket-Handler
und den ECHTEN Parser. Es wird KEINE Verbindung aufgebaut, keine Datenbank beruehrt,
keine Telegram-Nachricht gesendet und keine echte .env gelesen (Dummy-Werte).

Starten:
    python3 "07 System/(C) test_usdc_filter.py"
    python3 test_usdc_filter.py /home/botuser/copy-trading-bot     # auf dem Server
"""

import logging
import os
import sys
import types

# --- Bot-Core finden -----------------------------------------------------------
HERE = os.path.dirname(os.path.abspath(__file__))
BOT_CORE = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "01 Bot-Core")
BOT_CORE = os.path.abspath(BOT_CORE)
sys.path.insert(0, BOT_CORE)

# --- Dummy-Umgebung: NIE echte Zugangsdaten laden --------------------------------
for _k in ("LEVEX_API_KEY", "LEVEX_API_SECRET", "LEVEX_MASTER_UID"):
    os.environ[_k] = "dummy-nur-fuer-test"
os.environ["LEVEX_ENV"] = "testnet"
os.environ["LOG_LEVEL"] = "debug"
os.chdir(HERE)  # nicht im Bot-Verzeichnis stehen

# --- Fehlende Pakete nur fuer den Import ersetzen (es wird nichts verbunden) -----
def _stub(name: str, **attrs) -> None:
    try:
        __import__(name)
    except Exception:
        mod = types.ModuleType(name)
        for k, v in attrs.items():
            setattr(mod, k, v)
        sys.modules[name] = mod

# dotenv IMMER ersetzen (auch wenn installiert): config.py ruft load_dotenv() auf und
# wuerde auf dem Server sonst die echte .env neben config.py einlesen.
_dotenv = types.ModuleType("dotenv")
_dotenv.load_dotenv = lambda *a, **k: False
sys.modules["dotenv"] = _dotenv
_stub("websockets", exceptions=types.SimpleNamespace(ConnectionClosed=Exception))
_stub("websockets.asyncio")
_stub("websockets.asyncio.client", ClientConnection=object)

import websocket_client as wsmod                      # noqa: E402
from websocket_client import LevexWebSocket, map_array_to_object  # noqa: E402
from parser import OrderParser                        # noqa: E402
from logger_setup import logger                       # noqa: E402
from bot_types import (                               # noqa: E402
    PERP_ORDER_KEYS, PERP_FILL_KEYS, PERP_POSITION_KEYS, PERP_ACCOUNT_KEYS,
    PerpOrder, PerpFill, PerpPosition, PerpAccount, is_private_pair,
)

# --- Log mitschneiden ------------------------------------------------------------
class _Capture(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.records: list[tuple[int, str]] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append((record.levelno, record.getMessage()))

CAP = _Capture()
logger.addHandler(CAP)
for _h in logger.handlers:
    if _h is not CAP:
        _h.setLevel(logging.CRITICAL)  # Konsole ruhig halten

# --- Mini-Testrahmen -------------------------------------------------------------
PASSED = 0
FAILED: list[str] = []

def check(name: str, cond: bool, detail: str = "") -> None:
    global PASSED
    if cond:
        PASSED += 1
        print(f"  PASS  {name}")
    else:
        FAILED.append(name)
        print(f"  FAIL  {name}  {detail}")

def row(keys: list[str], **vals) -> list:
    return [vals.get(k, "") for k in keys]

def order(**v) -> list:
    return row(PERP_ORDER_KEYS, **v)

def fill(**v) -> list:
    return row(PERP_FILL_KEYS, **v)

def position(**v) -> list:
    return row(PERP_POSITION_KEYS, **v)

def account(**v) -> list:
    return row(PERP_ACCOUNT_KEYS, **v)


class Harness:
    """Echter WebSocket-Handler + echter Parser, verdrahtet wie in listen.py."""

    def __init__(self) -> None:
        self.ws = LevexWebSocket()
        self.parser = OrderParser()
        self.events: list = []
        self.calls = {"order": 0, "position": 0, "account": 0}
        self.last: dict = {}
        self.ws.on_perp_order(self._on_order)
        self.ws.on_perp_position(self._on_position)
        self.ws.on_perp_account(self._on_account)

    def _on_order(self, data: dict) -> None:
        self.calls["order"] += 1
        self.last["order"] = data
        ev = self.parser.parse_order_update(data)
        if data.get("_type") != "snapshot":
            self.events.extend(ev)

    def _on_position(self, data: dict) -> None:
        self.calls["position"] += 1
        self.last["position"] = data
        ev = self.parser.parse_position_update(data.get("positions", []))
        if data.get("_type") != "snapshot":
            self.events.extend(ev)

    def _on_account(self, data: dict) -> None:
        self.calls["account"] += 1
        self.last["account"] = data
        self.parser.parse_account_update(data.get("accounts", []))

    # Nachrichten einspielen
    def orders(self, open=(), closed=(), fills=(), type="incremental") -> None:
        self.ws._handle_perp_order_update(
            {"open": list(open), "closed": list(closed), "fills": list(fills), "type": type})

    def positions(self, rows, type="incremental") -> None:
        self.ws._handle_perp_position_update({"positions": list(rows), "type": type})

    def accounts(self, rows, type="incremental") -> None:
        self.ws._handle_perp_account_update({"accounts": list(rows), "type": type})


def old_path_events(steps: list) -> list:
    """Referenz 'wie vorher': dieselben Nachrichten OHNE Filter direkt in den Parser."""
    p = OrderParser()
    out = []
    for kind, payload in steps:
        if kind == "orders":
            data = {
                "open": [map_array_to_object(PERP_ORDER_KEYS, r, PerpOrder) for r in payload.get("open", [])],
                "closed": [map_array_to_object(PERP_ORDER_KEYS, r, PerpOrder) for r in payload.get("closed", [])],
                "fills": [map_array_to_object(PERP_FILL_KEYS, r, PerpFill) for r in payload.get("fills", [])],
                "_type": "incremental",
            }
            out.extend(p.parse_order_update(data))
        elif kind == "positions":
            out.extend(p.parse_position_update(
                [map_array_to_object(PERP_POSITION_KEYS, r, PerpPosition) for r in payload]))
    return out

def play(h: Harness, steps: list) -> None:
    for kind, payload in steps:
        if kind == "orders":
            h.orders(**payload)
        elif kind == "positions":
            h.positions(payload)

def sig(events: list) -> list:
    return [(e.action.value, e.symbol, e.details) for e in events]


def lifecycle(symbol: str, currency: str, pid: str) -> list:
    """Kompletter Trade: Limit setzen -> Fill -> Position -> SL setzen -> Nachkauf -> Close."""
    return [
        ("orders", {"open": [order(symbol=symbol, currency=currency, side="Buy", posSide="Long",
                                   ordType="Limit", orderID=f"o-{pid}", price="90000", orderQty="0.01",
                                   ordStatus="New", positionID=pid, actionBy="ByUser")]}),
        ("orders", {"closed": [order(symbol=symbol, currency=currency, side="Buy", posSide="Long",
                                     ordType="Limit", orderID=f"o-{pid}", price="90000", orderQty="0.01",
                                     ordStatus="Filled", positionID=pid, actionBy="ByUser")],
                    "fills": [fill(symbol=symbol, currency=currency, side="Buy", posSide="Long",
                                   ordType="Limit", orderID=f"o-{pid}", execPrice="90000", execQty="0.01",
                                   execFee="0.5", closedPnL="0", positionID=pid)]}),
        ("positions", [position(symbol=symbol, currency=currency, side="Buy", posSide="Long", size="0.01",
                                leverage="10", avgEntryPrice="90000", posMargin="90", markPrice="90010",
                                positionID=pid)]),
        ("orders", {"open": [order(symbol=symbol, currency=currency, side="Sell", posSide="Long",
                                   ordType="StopMarket", orderID=f"sl-{pid}", stopPrice="88000",
                                   ordStatus="Untriggered", positionID=pid, actionBy="FromPosition",
                                   execInst="ReduceOnly")]}),
        ("positions", [position(symbol=symbol, currency=currency, side="Buy", posSide="Long", size="0.02",
                                leverage="10", avgEntryPrice="90050", posMargin="180", markPrice="90100",
                                positionID=pid)]),
        ("orders", {"fills": [fill(symbol=symbol, currency=currency, side="Sell", posSide="Long",
                                   ordType="Market", orderID=f"c-{pid}", execPrice="91000", execQty="0.02",
                                   execFee="0.9", closedPnL="19", positionID=pid)]}),
        ("positions", [position(symbol=symbol, currency=currency, side="Buy", posSide="Long", size="0",
                                leverage="10", avgEntryPrice="90050", markPrice="91000",
                                realisedPnL="19", positionID=pid)]),
    ]


# ================================================================================
print(f"Bot-Core: {BOT_CORE}\n")

print("1) Regel is_private_pair")
for sym, cur, expected in [
    ("BTCUSDT", "USDT", False), ("ETHUSDT", "", False), ("XAUUSDT", "USDT", False),
    ("BTCUSDC", "USDC", True), ("BTCUSDC", "", True), ("ethusdc", "", True),
    ("BTC-USDC", "", True), ("BTCUSDCPERP", "", True), ("BTCUSDTPERP", "", False),
    ("USDCUSDT", "USDT", False),          # USDC als Basis eines USDT-Paars = Copy Trading
    ("BTCUSDT", "USDC", False),           # Symbol entscheidet: USDT-Paar geht nie verloren
    ("BTCUSDC", "USDT", True),            # Symbol entscheidet
    ("", "USDC", True), ("", "usdc ", True), ("", "USDT", False), ("", "", False),
    ("XYZ", "USDC", True),                # unbekannte Schreibweise -> Waehrungsfeld
]:
    check(f"is_private_pair({sym!r}, {cur!r}) == {expected}", is_private_pair(sym, cur) is expected)

print("\n2) USDT-Trade laeuft exakt wie vorher durch")
steps_usdt = lifecycle("BTCUSDT", "USDT", "P-USDT")
h = Harness()
play(h, steps_usdt)
ref = old_path_events(steps_usdt)
check("USDT erzeugt Events", len(h.events) > 0, f"({len(h.events)})")
check("USDT-Events identisch zum Stand ohne Filter", sig(h.events) == sig(ref),
      f"neu={len(h.events)} alt={len(ref)}")
check("alle 7 Nachrichten erreichen listen.py", h.calls["order"] + h.calls["position"] == 7, str(h.calls))

print("\n3) Kompletter USDC-Trade erzeugt NICHTS")
steps_usdc = lifecycle("BTCUSDC", "USDC", "P-USDC")
h = Harness()
CAP.records.clear()
play(h, steps_usdc)
check("0 Events", len(h.events) == 0, f"({sig(h.events)})")
check("Callbacks nie aufgerufen (als haette es die Updates nie gegeben)",
      h.calls == {"order": 0, "position": 0, "account": 0}, str(h.calls))
check("Parser kennt keine USDC-Order", len(h.parser._active_orders) == 0)
check("Parser kennt keine USDC-Position", len(h.parser._positions) == 0)
check("kein gemerkter SL/TP", len(h.parser._last_sl_tp) == 0)
info = [m for lvl, m in CAP.records if lvl == logging.INFO and m.startswith("[PRIVAT]")]
dbg = [m for lvl, m in CAP.records if lvl == logging.DEBUG and m.startswith("[PRIVAT]")]
check("Orders/Fills stehen als [PRIVAT] im Log", sum("Order ignoriert" in m or "Fill ignoriert" in m for m in info) == 5,
      str(info))
check("Position nur 1x auf INFO, danach DEBUG", sum("Position ignoriert" in m for m in info) == 1
      and sum("Position ignoriert" in m for m in dbg) == 2, f"info={info} dbg={dbg}")

print("\n4) Gegenprobe: OHNE Filter waere derselbe USDC-Trade durchgegangen")
_orig = wsmod.is_private_pair
wsmod.is_private_pair = lambda *a, **k: False
try:
    h = Harness()
    play(h, steps_usdc)
    leaked = [e for e in h.events if e.symbol == "BTCUSDC"]
    check("ohne Filter gehen USDC-Events durch (Test erkennt das Leck)", len(leaked) > 0, f"({len(leaked)})")
finally:
    wsmod.is_private_pair = _orig

print("\n5) Gemischte Nachricht (USDT + USDC zusammen)")
mixed = [("orders", {"open": steps_usdt[0][1]["open"] + steps_usdc[0][1]["open"]}),
         ("orders", {"closed": steps_usdt[1][1]["closed"] + steps_usdc[1][1]["closed"],
                     "fills": steps_usdc[1][1]["fills"] + steps_usdt[1][1]["fills"]}),
         ("positions", steps_usdc[2][1] + steps_usdt[2][1])]
h = Harness()
play(h, mixed)
ref = old_path_events(steps_usdt[:3])
check("nur USDT kommt an", all(e.symbol == "BTCUSDT" for e in h.events) and len(h.events) > 0)
check("USDT-Events identisch zum reinen USDT-Ablauf", sig(h.events) == sig(ref))
check("Parser-State enthaelt nur USDT", set(h.parser._positions) == {"P-USDT"}, str(set(h.parser._positions)))

print("\n6) Snapshots (Start/Reconnect)")
h = Harness()
h.positions(steps_usdt[2][1] + steps_usdc[2][1], type="snapshot")
got = h.last["position"]
check("Snapshot: nur USDT-Position weitergereicht",
      [p.symbol for p in got["positions"]] == ["BTCUSDT"] and got["_type"] == "snapshot")
h = Harness()
h.positions(steps_usdc[2][1], type="snapshot")
check("Snapshot nur mit USDC: wird LEER weitergereicht (Abgleich verwaister Signal-Namen laeuft)",
      h.calls["position"] == 1 and h.last["position"]["positions"] == []
      and h.last["position"]["_type"] == "snapshot")
h = Harness()
h.orders(open=steps_usdc[0][1]["open"] + steps_usdc[3][1]["open"], type="snapshot")
check("Order-Snapshot nur mit USDC: leer, kein State",
      h.calls["order"] == 1 and len(h.parser._active_orders) == 0)
h = Harness()
h.positions([], type="incremental")
check("leeres Update ohne private Eintraege wird wie bisher weitergereicht", h.calls["position"] == 1)

print("\n7) Guthaben: USDC ueberschreibt die USDT-Master-Balance nicht")
usdt_acc = account(currency="USDT", accountBalance="1000")
usdc_acc = account(currency="USDC", accountBalance="5000")
h = Harness()
h.accounts([usdt_acc, usdc_acc], type="snapshot")
check("USDT zuerst, USDC danach -> Balance 1000", h.parser.master_balance == 1000.0, str(h.parser.master_balance))
h = Harness()
h.accounts([usdc_acc, usdt_acc], type="snapshot")
check("USDC zuerst, USDT danach -> Balance 1000", h.parser.master_balance == 1000.0, str(h.parser.master_balance))
calls_before = h.calls["account"]
h.accounts([account(currency="USDC", accountBalance="7777")])
check("reines USDC-Update: Callback nicht aufgerufen, Balance bleibt 1000",
      h.calls["account"] == calls_before and h.parser.master_balance == 1000.0)
h.accounts([account(currency="USDT", accountBalance="1200")])
check("USDT-Update kommt weiter an -> Balance 1200", h.parser.master_balance == 1200.0)
wsmod.is_private_pair = lambda *a, **k: False
try:
    h = Harness()
    h.accounts([usdt_acc, usdc_acc], type="snapshot")
    check("Gegenprobe: ohne Filter waere die Balance auf 5000 gesprungen", h.parser.master_balance == 5000.0,
          str(h.parser.master_balance))
finally:
    wsmod.is_private_pair = _orig

# ================================================================================
total = PASSED + len(FAILED)
print(f"\n{PASSED}/{total} PASS")
if FAILED:
    print("FEHLGESCHLAGEN: " + "; ".join(FAILED))
    sys.exit(1)
