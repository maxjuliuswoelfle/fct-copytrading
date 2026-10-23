"""
(C) signal_bot.py — Telegram Signal Bot fuer Kunden-Gruppen + Marketing Channel

Empfaengt ParsedEvents vom Parser (gleicher Stream wie Execution Engine)
und postet formatierte Signale in Telegram-Gruppen:
- Paid Gruppe: Alle Signale + Management (16 Nachrichtentypen)
- Marketing Channel: Profitable Trade-Ergebnisse (>8%) + Wochen-/Monats-Summaries

Trade-Nummerierung: "BTC Short #1", "BTC Short #2" etc.
Updates referenzieren immer den Trade-Namen.

Nachrichtentypen:
 1. Neue Position (Market)          — 🟢
 2. Neue Limit Order                — 🟡
 3. Limit hinzugefuegt (Nachkauf)   — 🟡
 4. Limit ausgefuehrt (neue Pos.)   — 🟢
 5. Limit ausgefuehrt (Nachkauf)    — ✅
 6. Limit storniert                 — ⚪
 7. Position geschlossen            — 🔴
 8. Teilschliessung (Scale-Out)     — 📉
 9. Nachkauf (Market Scale-In)      — 📈
10. SL Anpassung                    — ⚙️
11. TP Anpassung                    — ⚙️
12. SL entfernt                     — ⚙️
13. TP entfernt                     — ⚙️
14. Hebel Anpassung                 — ⚙️
15. Margin Anpassung                — ⚙️
16. Offene Positionen (taeglich)    — 📋
"""

import os
import asyncio
import time
import aiohttp
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from logger_setup import logger
from bot_types import BotAction, ParsedEvent

if TYPE_CHECKING:
    from database import Database
    from parser import OrderParser


# Config aus Environment
MARKETING_MIN_PNL_PCT = float(os.getenv("MARKETING_MIN_PNL_PCT", "8.0"))
SIGNUP_URL = os.getenv("MARKETING_SIGNUP_URL", "https://copytrading.firstclass-trading.com")

# Footer fuer alle Signale
FOOTER = ""


class SignalBot:
    """
    Postet Trading-Signale in Telegram-Gruppen.
    Haengt sich an denselben Event-Stream wie die Execution Engine.
    """

    def __init__(
        self,
        bot_token: str,
        paid_group_id: str,
        db: "Database",
        parser: "OrderParser | None" = None,
        marketing_channel_id: str = "",
        scalp_group_id: str = "",
    ) -> None:
        self._bot_token = bot_token
        self._paid_group_id = paid_group_id
        self._marketing_channel_id = marketing_channel_id
        # Scalp-Gruppe: Trades die BEIM OEFFNEN mit >= SCALP_MIN_LEVERAGE Hebel
        # aufgemacht wurden gehen komplett (Open + Management + Close) hierhin
        # statt in die Main-Gruppe. Ein spaeteres Hochsetzen des Hebels zaehlt NICHT.
        self._scalp_group_id = scalp_group_id
        self._scalp_min_leverage = float(os.getenv("SCALP_MIN_LEVERAGE", "80"))
        # Auto-Like: jede eigene Nachricht in Main + Scalp bekommt automatisch eine
        # Reaktion (Social Proof). Emoji via Env SIGNAL_REACTION_EMOJI (Default Daumen hoch).
        self._auto_react_emoji = os.getenv("SIGNAL_REACTION_EMOJI", "👍")
        self._db = db
        self._parser = parser
        self._base_url = f"https://api.telegram.org/bot{bot_token}"
        self._session: aiohttp.ClientSession | None = None
        self._enabled = bool(bot_token and paid_group_id)

        # Debounce: Events kurz sammeln bevor sie verarbeitet werden
        self._event_queue: asyncio.Queue[ParsedEvent] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None
        self._debounce_seconds = 0.5

        # Scheduled tasks (summaries + daily overview)
        self._summary_task: asyncio.Task | None = None
        self._daily_overview_task: asyncio.Task | None = None

        # Limit Order Tracking: orderID -> {symbol, side, price, positionID, display_name}
        self._pending_limits: dict[str, dict] = {}

        # Limit-Fill-Tracking: positionID -> Zeitpunkt des letzten Limit-Fills.
        # Ein Limit-Fill (Order-Stream) und das zugehoerige SCALE_IN (Positions-Stream)
        # koennen in VERSCHIEDENEN Debounce-Batches ankommen. Damit ein Nachkauf nicht
        # doppelt gepostet wird (einmal als "Limit ausgefuehrt", einmal als "Skalierung"),
        # merken wir den Fill-Zeitpunkt und unterdruecken EIN SCALE_IN, das kurz danach kommt.
        self._recent_limit_fills: dict[str, float] = {}
        self._limit_fill_window = 8.0  # Sekunden — Fenster fuer die Unterdrueckung

        if self._enabled:
            logger.info(
                f"[SIGNAL] Signal Bot aktiviert — "
                f"Paid: ja | "
                f"Marketing: {'ja' if marketing_channel_id else 'nein'} | "
                f"Scalp: {'ja (>=' + str(self._scalp_min_leverage).rstrip('0').rstrip('.') + 'x)' if scalp_group_id else 'nein'}"
            )
        else:
            logger.info("[SIGNAL] Signal Bot deaktiviert (Token oder Paid Group ID fehlt)")

    # --------------------------------------------------------------------------
    # LIFECYCLE
    # --------------------------------------------------------------------------

    def start(self) -> None:
        """Debounce-Worker + Scheduler starten. Muss nach Event-Loop Start aufgerufen werden."""
        if self._enabled and self._worker_task is None:
            self._worker_task = asyncio.create_task(self._debounce_worker())
            logger.info("[SIGNAL] Debounce-Worker gestartet")
        if self._marketing_channel_id and self._summary_task is None:
            self._summary_task = asyncio.create_task(self._summary_scheduler())
            logger.info("[SIGNAL] Summary-Scheduler gestartet")
        if self._enabled and self._daily_overview_task is None:
            self._daily_overview_task = asyncio.create_task(self._daily_overview_scheduler())
            logger.info("[SIGNAL] Taegliche-Uebersicht-Scheduler gestartet")

    async def _debounce_worker(self) -> None:
        """Hintergrund-Worker: Sammelt Events und verarbeitet sie als Batch."""
        while True:
            try:
                first = await self._event_queue.get()
                batch: list[ParsedEvent] = [first]
                await asyncio.sleep(self._debounce_seconds)
                while not self._event_queue.empty():
                    try:
                        batch.append(self._event_queue.get_nowait())
                    except asyncio.QueueEmpty:
                        break
                logger.info(f"[SIGNAL] Debounce: {len(batch)} Events gesammelt, verarbeite...")
                await self._process_debounced_batch(batch)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[SIGNAL] Worker-Fehler: {e}")

    # --------------------------------------------------------------------------
    # SESSION
    # --------------------------------------------------------------------------

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    # --------------------------------------------------------------------------
    # SENDEN
    # --------------------------------------------------------------------------

    async def _send_to_group(self, group_id: str, text: str, max_attempts: int = 3) -> bool:
        """Nachricht an eine Telegram-Gruppe senden — mit Wiederholung.

        Telegram kann bei vielen Nachrichten kurz "zu schnell" (429 Rate-Limit) melden
        oder es gibt einen kurzen Netz-/Serverfehler (5xx). Frueher wurde die Nachricht
        in dem Fall still verworfen → ein Kunde verpasst evtl. ein Signal. Jetzt wird
        bis zu max_attempts-mal erneut versucht:
        - 429: so lange warten wie Telegram via retry_after vorgibt (gedeckelt)
        - 5xx / Netzfehler: kurzer Backoff, dann erneut
        - 4xx (ausser 429, z.B. kaputtes HTML): permanenter Fehler → KEIN Retry
        """
        if not group_id:
            return False
        url = f"{self._base_url}/sendMessage"
        payload = {
            "chat_id": group_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        for attempt in range(1, max_attempts + 1):
            try:
                session = await self._get_session()
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        # Auto-Like: eigene Nachricht in Main + Scalp automatisch mit
                        # einer Reaktion versehen. Best effort — Fehler hier duerfen den
                        # Versand NIE beeinflussen (geschluckt).
                        if self._auto_react_emoji and group_id in (self._paid_group_id, self._scalp_group_id):
                            try:
                                data = await resp.json()
                                mid = data.get("result", {}).get("message_id")
                                if mid:
                                    await self._react_to_message(group_id, mid)
                            except Exception:
                                pass
                        return True
                    body = await resp.text()
                    # 429 = Rate-Limit: Telegram sagt via retry_after wie lange warten
                    if resp.status == 429:
                        retry_after = 1.0
                        try:
                            data = await resp.json()
                            retry_after = float(data.get("parameters", {}).get("retry_after", 1))
                        except Exception:
                            pass
                        wait = min(retry_after, 15.0)
                        logger.warning(
                            f"[SIGNAL] Telegram Rate-Limit (429) — warte {wait:.0f}s "
                            f"(Versuch {attempt}/{max_attempts})"
                        )
                        if attempt < max_attempts:
                            await asyncio.sleep(wait)
                            continue
                        return False
                    # 4xx (ausser 429) = permanenter Fehler → kein Retry, waere sinnlos
                    if 400 <= resp.status < 500:
                        logger.warning(f"[SIGNAL] Telegram API Fehler {resp.status} (kein Retry): {body}")
                        return False
                    # 5xx = Server-Fehler → Retry mit Backoff
                    logger.warning(
                        f"[SIGNAL] Telegram API Fehler {resp.status} "
                        f"(Versuch {attempt}/{max_attempts}): {body}"
                    )
            except Exception as e:
                logger.warning(f"[SIGNAL] Senden fehlgeschlagen (Versuch {attempt}/{max_attempts}): {e}")
            # Backoff vor naechstem Versuch (1s, 2s, ...), nur wenn noch Versuche uebrig
            if attempt < max_attempts:
                await asyncio.sleep(min(2 ** (attempt - 1), 5))
        return False

    async def _send_to_paid(self, text: str) -> bool:
        return await self._send_to_group(self._paid_group_id, text)

    async def _send_to_marketing(self, text: str) -> bool:
        return await self._send_to_group(self._marketing_channel_id, text)

    async def _send_to_scalp(self, text: str) -> bool:
        return await self._send_to_group(self._scalp_group_id, text)

    async def _react_to_message(self, chat_id: str, message_id: int) -> None:
        """Eigene Nachricht automatisch mit einer Reaktion (Like) versehen.

        Best effort — schlaegt es fehl (z.B. Reaktion im Chat nicht erlaubt), wird es
        nur geloggt und beeinflusst den Signal-Versand nicht.
        """
        try:
            session = await self._get_session()
            payload = {
                "chat_id": chat_id,
                "message_id": message_id,
                "reaction": [{"type": "emoji", "emoji": self._auto_react_emoji}],
            }
            async with session.post(
                f"{self._base_url}/setMessageReaction",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.warning(f"[SIGNAL] setMessageReaction Fehler {resp.status}: {body}")
        except Exception as e:
            logger.warning(f"[SIGNAL] Reaktion fehlgeschlagen (msg {message_id}): {e}")

    # --------------------------------------------------------------------------
    # SCALP-ROUTING — Trades die BEIM OEFFNEN >= Schwellen-Hebel hatten
    # --------------------------------------------------------------------------

    def _will_be_scalp(self, position_id: str) -> bool:
        """True, wenn dieser Trade im Scalp-Channel landet (Hebel >= Schwelle).

        Wird NUR fuer die Nummerierung gebraucht, damit Scalp und Main getrennte
        Zaehler haben. Setzt nichts, schreibt nichts.
        """
        if not self._scalp_group_id or not position_id:
            return False
        if self._db.is_scalp_position(position_id):
            return True
        return self._get_leverage(position_id) >= self._scalp_min_leverage

    def _mark_scalp_if_qualifies(self, position_id: str) -> None:
        """Position als Scalp markieren, wenn der Hebel BEIM OEFFNEN >= Schwelle ist.

        Nur setzen, nie zuruecksetzen. Wird ausschliesslich bei Oeffnungs-Events
        (neue Position / Limit-Fill) aufgerufen — niemals bei UPDATE_LEVERAGE, damit
        ein nachtraegliches Hochsetzen des Hebels eine Position NICHT zum Scalp macht.
        """
        if not self._scalp_group_id or not position_id:
            return
        if self._db.is_scalp_position(position_id):
            return
        leverage = self._get_leverage(position_id)
        if leverage >= self._scalp_min_leverage:
            self._db.mark_signal_scalp(position_id)
            logger.info(
                f"[SIGNAL] SCALP markiert | pos={position_id} | "
                f"Hebel {self._fmt_leverage(leverage)} >= {self._scalp_min_leverage:g}x"
            )

    # --------------------------------------------------------------------------
    # DISPLAY NAMES — "BTC Short #1", "ETH Long #2" etc.
    # --------------------------------------------------------------------------

    def _get_or_create_display_name(self, event: ParsedEvent, entry_price: float = 0) -> str:
        """Display-Name fuer eine Position holen oder erstellen."""
        d = event.details
        position_id = d.get("positionID", d.get("orderID", ""))
        if not position_id:
            return event.symbol

        existing = self._db.get_signal_display_name(position_id)
        if existing:
            return existing

        side = d.get("side", "")
        if not side:
            pos_side = d.get("posSide", "")
            side = "Buy" if pos_side == "Long" else "Sell"

        short_symbol = event.symbol.replace("USDT", "").replace("PERP", "")
        direction = "Long" if side == "Buy" else "Short"
        # Getrennte Zaehler fuer Scalp-Channel und Main-Gruppe: ein Scalp soll
        # nicht "#2" heissen, nur weil in der Main noch ein normaler Trade
        # desselben Symbols offen ist (und umgekehrt).
        scalp_bucket = 1 if self._will_be_scalp(position_id) else 0
        count = self._db.count_active_signal_names(
            event.symbol, side, is_scalp=scalp_bucket
        )
        number = count + 1
        display_name = f"{short_symbol} {direction} #{number}"

        self._db.save_signal_display_name(
            position_id, display_name, event.symbol, side, number,
            entry_price=entry_price, open_timestamp=time.time(),
        )
        # Direkt beim Anlegen pruefen, ob es ein Scalp (>= Schwellen-Hebel) ist.
        self._mark_scalp_if_qualifies(position_id)
        return display_name

    def _get_display_name_for_close(self, event: ParsedEvent) -> str:
        d = event.details
        position_id = d.get("positionID", "")
        if position_id:
            name = self._db.get_signal_display_name(position_id)
            if name:
                return name
        side = d.get("side", "Buy")
        short_symbol = event.symbol.replace("USDT", "").replace("PERP", "")
        direction = "Long" if side == "Buy" else "Short"
        return f"{short_symbol} {direction}"

    # --------------------------------------------------------------------------
    # ZAHLENFORMATIERUNG — Deutsche Formatierung (76.840,7$)
    # --------------------------------------------------------------------------

    @staticmethod
    def _fmt_price(value) -> str:
        """Preis deutsch formatieren: 76840.7 → '76.840,7$'"""
        try:
            num = float(value)
        except (ValueError, TypeError):
            return str(value) if value else "?"

        if num >= 100:
            formatted = f"{num:,.1f}"
        elif num >= 1:
            formatted = f"{num:,.2f}"
        elif num >= 0.01:
            formatted = f"{num:,.4f}"
        else:
            formatted = f"{num:,.6f}"

        formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
        return f"{formatted}$"

    @staticmethod
    def _fmt_qty(value) -> str:
        """Menge formatieren."""
        try:
            num = float(value)
        except (ValueError, TypeError):
            return str(value) if value else "?"
        if num >= 1:
            formatted = f"{num:,.4f}".rstrip("0").rstrip(",")
        else:
            formatted = f"{num:.6f}".rstrip("0").rstrip(".")
        formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
        return formatted

    @staticmethod
    def _fmt_pnl_usdt(value) -> str:
        """USDT-Betrag deutsch formatieren."""
        try:
            num = float(value)
        except (ValueError, TypeError):
            return str(value) if value else "0"
        formatted = f"{num:,.2f}"
        formatted = formatted.replace(",", "X").replace(".", ",").replace("X", ".")
        return formatted

    @staticmethod
    def _fmt_pct(value: float) -> str:
        """Prozent formatieren: 6.5 → '+6,5%', -1.2 → '-1,2%'"""
        sign = "+" if value >= 0 else ""
        formatted = f"{value:.1f}".replace(".", ",")
        return f"{sign}{formatted}%"

    @staticmethod
    def _fmt_account_pct(value: float) -> str:
        """Kontoanteil formatieren (ohne Vorzeichen): 2.5 → '2,5 %'"""
        # Unter 0,1% nicht auf 0 runden, damit kleine Einsaetze sichtbar bleiben
        if 0 < value < 0.1:
            return "<0,1 %"
        return f"{value:.1f}".replace(".", ",") + " %"

    @staticmethod
    def _fmt_leverage(leverage: float) -> str:
        """Hebel formatieren, Nachkommastellen erhalten: 7.5 → '7,5x', 20 → '20x'.
        Leer wenn kein gueltiger Hebel."""
        if not leverage or leverage <= 0:
            return ""
        if leverage == int(leverage):
            return f"{int(leverage)}x"
        s = f"{leverage:.2f}".rstrip("0").rstrip(".")
        return f"{s.replace('.', ',')}x"

    def _get_pos_margin(self, position_id: str) -> float:
        """Echte Positionsmarge (posMargin) aus Parser-State holen. 0 wenn keine offene Position."""
        if not self._parser or not position_id:
            return 0
        m_str = self._parser.get_pos_margin_for_position(position_id)
        if m_str:
            try:
                return float(m_str)
            except (ValueError, TypeError):
                pass
        return 0

    def _calc_account_pct(self, qty: float, entry: float, leverage: float,
                          position_id: str | None = None,
                          added_ratio: float | None = None) -> float | None:
        """
        Margin dieser Position als % des Master-Futures-Guthabens.
        So wissen Follower, mit wie viel % ihres eigenen Accounts sie reingehen koennen.

        Bevorzugt die ECHTE Positionsmarge (posMargin) von Levex (deckt Cross-Margin,
        nachgeschossene Marge und Rundung ab). Faellt nur auf die Rekonstruktion
        (Margin = Menge x Entry / Hebel) zurueck, wenn noch KEINE Position existiert
        (z.B. wartende Limit-Order) — dann gibt es keine posMargin.
        added_ratio: bei Nachkauf nur den hinzugefuegten Anteil (added_qty / new_size).
        """
        if not self._parser:
            return None
        balance = float(getattr(self._parser, "master_balance", 0) or 0)
        if balance <= 0:
            return None
        # 1) Echte Positionsmarge bevorzugen (nur wenn eine Position existiert)
        if position_id:
            real_margin = self._get_pos_margin(position_id)
            if real_margin > 0:
                if added_ratio is not None and added_ratio > 0:
                    real_margin = real_margin * added_ratio
                return real_margin / balance * 100
        # 2) Fallback: Rekonstruktion (wartende Limit-Order ohne Position)
        if qty <= 0 or entry <= 0 or leverage <= 0:
            return None
        margin = (qty * entry) / leverage
        return margin / balance * 100

    # --------------------------------------------------------------------------
    # BERECHNUNGEN — Risiko, CRV, SL/TP%, Close-Type, Trade-Dauer
    # --------------------------------------------------------------------------

    @staticmethod
    def _calc_risk_rating(leverage: float) -> tuple[str, str]:
        """
        Risikobewertung basierend auf Hebel.
        Returns: (emoji_bar, label) z.B. ("🟩🟩⬜️⬜️⬜️", "moderat")
        """
        if leverage <= 5:
            return "🟩⬜️⬜️⬜️⬜️", "solide"
        elif leverage <= 15:
            return "🟩🟩⬜️⬜️⬜️", "moderat"
        elif leverage <= 25:
            return "🟨🟨🟨⬜️⬜️", "ausgewogen"
        elif leverage <= 50:
            return "🟨🟨🟨🟨⬜️", "aggressiv"
        else:
            return "🟥🟥🟥🟥🟥", "spekulativ"

    @staticmethod
    def _calc_crv(entry: float, sl: float, tp: float, side: str) -> float | None:
        """CRV = |TP - Entry| / |SL - Entry|. Returns None wenn nicht berechenbar."""
        if not entry or not sl or not tp:
            return None
        risk = abs(sl - entry)
        reward = abs(tp - entry)
        if risk <= 0:
            return None
        return round(reward / risk, 1)

    @staticmethod
    def _calc_sl_tp_pct(entry: float, price: float, side: str) -> float:
        """Prozentuale Distanz von Entry zu SL/TP. Positiv = in Richtung Gewinn."""
        if not entry or entry <= 0:
            return 0
        if side == "Buy":
            return (price - entry) / entry * 100
        else:
            return (entry - price) / entry * 100

    def _calc_position_pnl_pct(self, entry: float, exit_price: float, side: str, position_id: str) -> str:
        """Position-Profit berechnen: (Kursaenderung%) × Hebel."""
        if entry <= 0 or exit_price <= 0:
            return ""

        if side == "Buy":
            price_change_pct = (exit_price - entry) / entry * 100
        else:
            price_change_pct = (entry - exit_price) / entry * 100

        leverage = 1.0
        if self._parser and position_id:
            lev_str = self._parser.get_leverage_for_position(position_id)
            if lev_str:
                try:
                    leverage = float(lev_str)
                except (ValueError, TypeError):
                    pass

        position_pnl = price_change_pct * leverage
        return f"{position_pnl:+.2f}%"

    @staticmethod
    def _detect_close_type(entry: float, exit_price: float, sl: float, tp: float, side: str) -> str:
        """
        Erkennt wie ein Trade geschlossen wurde.
        Returns: "tp" / "sl_profit" / "sl_loss" / "manual"
        """
        tolerance = 0.001  # 0.1%

        # TP Check
        if tp > 0 and entry > 0:
            if abs(exit_price - tp) / tp <= tolerance:
                return "tp"

        # SL Check
        if sl > 0 and entry > 0:
            if abs(exit_price - sl) / sl <= tolerance:
                # War SL im Gewinn?
                if side == "Buy" and sl > entry:
                    return "sl_profit"
                elif side == "Sell" and sl < entry:
                    return "sl_profit"
                else:
                    return "sl_loss"

        return "manual"

    @staticmethod
    def _format_duration(open_ts: float, close_ts: float) -> str:
        """Trade-Dauer formatieren: 'X Tage Xh' oder 'Xh Xmin'."""
        if open_ts <= 0:
            return ""
        diff = close_ts - open_ts
        if diff < 0:
            return ""

        days = int(diff // 86400)
        hours = int((diff % 86400) // 3600)
        minutes = int((diff % 3600) // 60)

        if days > 0:
            return f"{days} {'Tag' if days == 1 else 'Tage'} {hours}h"
        elif hours > 0:
            return f"{hours}h {minutes}min"
        else:
            return f"{minutes}min"

    # --------------------------------------------------------------------------
    # EVENT VERARBEITUNG
    # --------------------------------------------------------------------------

    async def process_event(self, event: ParsedEvent) -> None:
        if not self._enabled:
            return
        await self._event_queue.put(event)

    async def process_event_batch(self, events: list[ParsedEvent]) -> None:
        if not self._enabled:
            return
        for ev in events:
            await self._event_queue.put(ev)

    async def _process_debounced_batch(self, events: list[ParsedEvent]) -> None:
        """
        Verarbeitet einen gesammelten Batch (nach Debounce).

        Logik:
        - SL/TP-Events die zu einem Open im selben Batch gehoeren → in Open-Nachricht integrieren
        - CANCEL_SL/TP bei Close → unterdruecken
        - Limit Fills → tracked, SCALE_IN unterdrueckt wenn aus Limit
        """
        # Alte Limit-Fill-Marker aufraeumen (aelter als das Unterdrueckungs-Fenster).
        # NICHT mehr komplett leeren wie frueher — sonst geht die Info zwischen zwei
        # Batches verloren und ein Nachkauf wird doppelt gepostet (Bug #6).
        now_ts = time.time()
        self._recent_limit_fills = {
            pid: ts for pid, ts in self._recent_limit_fills.items()
            if now_ts - ts < self._limit_fill_window
        }

        # Schritt 1: Open-Events identifizieren (TRADE_FILLED mit closedPnL == 0)
        open_position_ids: set[str] = set()
        open_order_ids: set[str] = set()
        for ev in events:
            if ev.action == BotAction.TRADE_FILLED:
                closed_pnl = float(ev.details.get("closedPnL", 0) or 0)
                if closed_pnl == 0:
                    order_id = ev.details.get("orderID", "")
                    pos_id = ev.details.get("positionID", "")
                    if order_id:
                        open_order_ids.add(order_id)
                    if pos_id:
                        open_position_ids.add(pos_id)

        # Schritt 2: Close-Events identifizieren
        closing_symbols: set[str] = set()
        for ev in events:
            if ev.action == BotAction.CLOSE_TRADE:
                closing_symbols.add(ev.symbol)

        # Schritt 2b: Close-Grund aus dem ausloesenden Fill ableiten (zuverlaessiger
        # als die Preis-Heuristik). Ein StopMarket-Fill = SL getroffen, ein
        # MarketIfTouched-Fill = TP getroffen. Der Fill traegt die eindeutige Info;
        # markPrice vs Stop-Trigger kann bei schnellen Bewegungen (v.a. SL im Gewinn)
        # auseinanderlaufen und wurde sonst faelschlich als "manuell" klassifiziert.
        close_fill_reason: dict[str, str] = {}
        for ev in events:
            if ev.action != BotAction.TRADE_FILLED:
                continue
            if float(ev.details.get("closedPnL", 0) or 0) == 0:
                continue  # Opening-Fill, kein Close
            pid = ev.details.get("positionID", "")
            ot = ev.details.get("ordType", "")
            if not pid:
                continue
            if ot == "StopMarket":
                close_fill_reason[pid] = "sl"
            elif ot == "MarketIfTouched":
                close_fill_reason[pid] = "tp"
        if close_fill_reason:
            for ev in events:
                if ev.action == BotAction.CLOSE_TRADE:
                    pid = ev.details.get("positionID", "")
                    if pid in close_fill_reason:
                        ev.details["closeFillType"] = close_fill_reason[pid]

        # Schritt 3: SL/TP-Events finden die zu Opens gehoeren ODER bei Close unterdrueckt werden
        suppressed: set[int] = set()
        merged_sl_tp: dict[str, dict[str, str]] = {}

        for i, ev in enumerate(events):
            if ev.action in (BotAction.SET_SL, BotAction.SET_TP):
                pos_id = ev.details.get("positionID", "")
                # Merge in Open-Nachricht wenn Position gerade geoeffnet wird
                if pos_id and pos_id in open_position_ids:
                    if pos_id not in merged_sl_tp:
                        merged_sl_tp[pos_id] = {}
                    if ev.action == BotAction.SET_SL:
                        merged_sl_tp[pos_id]["stopLoss"] = ev.details.get("stopPrice", ev.details.get("newStopPrice", ""))
                    else:
                        merged_sl_tp[pos_id]["takeProfit"] = ev.details.get("stopPrice", ev.details.get("newStopPrice", ""))
                    suppressed.add(i)

            if ev.action in (BotAction.CANCEL_SL, BotAction.CANCEL_TP):
                if ev.symbol in closing_symbols:
                    suppressed.add(i)

        # Schritt 4: SL/TP in Open-Events einfuegen
        for ev in events:
            if ev.action == BotAction.TRADE_FILLED:
                pos_id = ev.details.get("positionID", ev.details.get("orderID", ""))
                if pos_id in merged_sl_tp:
                    ev.details.update(merged_sl_tp[pos_id])

        # Schritt 5: Alle Events sequentiell verarbeiten (ausser suppressed).
        # Jedes Event einzeln absichern (Bug #7): faellt eines mit einer Exception aus,
        # werden die uebrigen Events des Batches trotzdem noch gesendet — eine kaputte
        # Nachricht reisst nicht mehr die nachfolgenden mit.
        for i, ev in enumerate(events):
            if i in suppressed:
                continue
            try:
                await self._send_single_event(ev)
            except Exception as e:
                logger.warning(f"[SIGNAL] Event uebersprungen ({ev.action}): {e}")

    async def _send_single_event(self, event: ParsedEvent) -> None:
        """Einzelnes Event klassifizieren, formatieren und senden."""
        d = event.details
        signal_type = self._classify(event)
        if not signal_type:
            return

        position_id = d.get("positionID", d.get("orderID", ""))
        message = self._format_message(signal_type, event)
        if not message:
            return

        # Bei einem Limit-Fill (neue Position aus Limit-Order) ist der Hebel jetzt
        # sicher bekannt — Scalp-Markierung ggf. nachziehen (nur upgrade, nie downgrade).
        if signal_type == "limit_filled":
            self._mark_scalp_if_qualifies(position_id)

        # Routing: Scalp-Positionen (>= Schwellen-Hebel beim Oeffnen) gehen komplett
        # in die Scalp-Gruppe, alles andere wie bisher in die Main-Gruppe.
        is_scalp = bool(self._scalp_group_id) and self._db.is_scalp_position(position_id)
        if is_scalp:
            sent_paid = await self._send_to_scalp(message)
        else:
            sent_paid = await self._send_to_paid(message)
        sent_marketing = False

        if position_id:
            self._db.log_signal(
                position_id=position_id,
                signal_type=signal_type,
                message_text=message,
                sent_to_paid=sent_paid,
                sent_to_free=False,
            )

        # Bei Close: Display-Name deaktivieren + Marketing
        if signal_type == "close":
            self._db.close_signal_display_name(position_id)
            sent_marketing = await self._maybe_send_marketing_showcase(event, position_id)

        # Bei Limit-Stornierung: Display-Name deaktivieren, damit die stornierte
        # Limit-Order nicht als verwaiste "aktive" Position in der Datenbank haengt
        # (und z.B. in der taeglichen Uebersicht faelschlich als offener Trade auftaucht).
        # ABER: Nur wenn es KEINE echte offene Position zu dieser ID gibt — ein
        # storniertes Nachkauf-Limit teilt sich die position_id mit der noch offenen
        # Position; die darf nicht deaktiviert werden.
        if signal_type == "limit_cancelled" and position_id:
            live_pos = self._parser._positions.get(position_id) if self._parser else None
            pos_size = float(getattr(live_pos, "size", 0) or 0) if live_pos else 0
            if pos_size == 0:
                self._db.close_signal_display_name(position_id)
                logger.info(f"[SIGNAL] LIMIT_CANCELLED | Display-Name deaktiviert | pos={position_id}")

        dest = "Scalp" if is_scalp else "Paid"
        logger.info(
            f"[SIGNAL] {signal_type.upper()} | {event.symbol} | "
            f"{dest}: {'✓' if sent_paid else '✗'} | Marketing: {'✓' if sent_marketing else '—'}"
        )

    # --------------------------------------------------------------------------
    # EVENT KLASSIFIZIERUNG — 16 Nachrichtentypen
    # --------------------------------------------------------------------------

    def _classify(self, event: ParsedEvent) -> str | None:
        """BotAction -> Signal-Typ mappen."""
        d = event.details
        action = event.action

        if action == BotAction.OPEN_TRADE:
            # Limit Order? → "new_limit" oder "limit_added"
            ord_type = d.get("ordType", "")
            if ord_type == "Limit":
                position_id = d.get("positionID", "")
                order_id = d.get("orderID", "")
                price = d.get("price", "")

                # Ist das ein ECHTER Nachkauf auf eine bestehende LIVE-Position?
                # Nur dann "Nachkauf" labeln. Eine neu/wieder eingestellte Entry-Limit
                # (z.B. nach Cancel+Replace beim Editieren des Einstiegs) hat zwar
                # evtl. schon einen Display-Name, aber KEINE offene Position.
                # Diese Entscheidung wird HIER getroffen und an der Order gemerkt —
                # der spaetere Fill liest sie aus, statt sie neu zu raten (siehe FIX 1b).
                is_scalein = bool(
                    position_id
                    and self._db.get_signal_display_name(position_id)
                    and self._has_live_position(position_id)
                )

                # Tracke die Limit Order
                self._pending_limits[order_id] = {
                    "symbol": event.symbol,
                    "side": d.get("side", ""),
                    "price": price,
                    "positionID": position_id,
                    "posSide": d.get("posSide", ""),
                    "is_scalein": is_scalein,
                }

                return "limit_added" if is_scalein else "new_limit"
            # Market Orders werden ueber TRADE_FILLED behandelt
            return None

        if action == BotAction.TRADE_FILLED:
            closed_pnl = float(d.get("closedPnL", 0) or 0)
            if closed_pnl == 0:
                # Neuer Trade Fill
                ord_type = d.get("ordType", "")
                order_id = d.get("orderID", "")
                position_id = d.get("positionID", "")

                if ord_type == "Limit" or order_id in self._pending_limits:
                    # Limit Order ausgefuehrt — Zeitpunkt merken, damit ein kurz darauf
                    # folgendes SCALE_IN (auch in einem spaeteren Batch) unterdrueckt wird.
                    if position_id:
                        self._recent_limit_fills[position_id] = time.time()
                    limit_info = self._pending_limits.pop(order_id, None)

                    # Nachkauf-Fill NUR, wenn die Order beim Setzen bereits als
                    # Nachkauf auf eine LIVE-Position erkannt wurde. Frueher wurde
                    # hier nur geprueft, ob ein Display-Name existiert — der wird
                    # aber bei JEDER Limit schon beim Setzen angelegt, also galt
                    # jede ganz normale Entry-Limit beim Ausfuehren faelschlich
                    # als "Nachkauf".
                    if limit_info is not None:
                        if limit_info.get("is_scalein"):
                            return "limit_filled_scalein"
                        return "limit_filled"

                    # Fallback: Order nicht mehr getrackt (z.B. gesetzt vor einem
                    # Bot-Neustart) — dann anhand einer echten Live-Position
                    # entscheiden statt allein am Display-Name.
                    if (
                        position_id
                        and self._db.get_signal_display_name(position_id)
                        and self._has_live_position(position_id)
                    ):
                        return "limit_filled_scalein"
                    return "limit_filled"
                else:
                    # Market Fill: Hat die Position schon einen Display-Name, ist das
                    # ein Market-Nachkauf einer bestehenden Position. Der wird ueber das
                    # SCALE_IN Event (Position-Stream) als Skalierung gesendet. FILL hier
                    # unterdruecken — sonst kommt der Nachkauf doppelt (neuer Trade + Skalierung).
                    if position_id and self._db.get_signal_display_name(position_id):
                        return None
                    return "open_market"
            return None  # Close-Fills ueber CLOSE_TRADE

        if action == BotAction.CANCEL_TRADE:
            order_id = d.get("orderID", "")
            position_id = d.get("positionID", order_id)
            if order_id in self._pending_limits:
                self._pending_limits.pop(order_id, None)
                return "limit_cancelled"
            # Auch ohne pending_limits: wenn Display-Name existiert → Signal senden
            if position_id and self._db.get_signal_display_name(position_id):
                return "limit_cancelled"
            # Fallback: ordType prüfen (z.B. nach Bot-Restart)
            ord_type = d.get("ordType", "")
            if ord_type == "Limit":
                return "limit_cancelled"
            return None

        if action == BotAction.AMEND_TRADE:
            # Bestehende Order in-place geaendert (gleiche OrderID, neuer Preis/Menge).
            # Nur fuer Limit-Orders ein Signal — Market-Amends sind irrelevant.
            if d.get("ordType", "") != "Limit":
                return None
            order_id = d.get("orderID", "")
            # Getrackten Limit-Preis mitziehen (fuer spaetere limit_filled-Korrelation)
            if order_id in self._pending_limits:
                new_price = d.get("newPrice", "")
                if new_price:
                    self._pending_limits[order_id]["price"] = new_price
            return "limit_amended"

        if action == BotAction.SCALE_IN:
            # Suppress wenn gerade aus Limit-Fill → wurde schon als limit_filled gesendet.
            # Funktioniert auch ueber Batch-Grenzen hinweg (Bug #6): wir pruefen, ob es
            # kurz zuvor einen Limit-Fill fuer diese Position gab. Den Marker danach
            # entfernen, damit nur EIN Scale-In unterdrueckt wird — ein spaeterer echter
            # Nachkauf wird wieder ganz normal gepostet.
            position_id = d.get("positionID", "")
            last_fill = self._recent_limit_fills.get(position_id, 0)
            if last_fill and (time.time() - last_fill) < self._limit_fill_window:
                self._recent_limit_fills.pop(position_id, None)
                return None
            return "scale_in"

        mapping = {
            BotAction.CLOSE_TRADE: "close",
            BotAction.SET_SL: "update_sl",
            BotAction.SET_TP: "update_tp",
            BotAction.CANCEL_SL: "cancel_sl",
            BotAction.CANCEL_TP: "cancel_tp",
            BotAction.SCALE_OUT: "scale_out",
            BotAction.UPDATE_LEVERAGE: "leverage",
            BotAction.UPDATE_MARGIN: "margin",
        }
        return mapping.get(action)

    # --------------------------------------------------------------------------
    # NACHRICHTENFORMATIERUNG — Dispatcher
    # --------------------------------------------------------------------------

    def _format_message(self, signal_type: str, event: ParsedEvent) -> str | None:
        formatters = {
            "open_market": self._format_open_market,
            "new_limit": self._format_new_limit,
            "limit_amended": self._format_limit_amended,
            "limit_added": self._format_limit_added,
            "limit_filled": self._format_limit_filled,
            "limit_filled_scalein": self._format_limit_filled_scalein,
            "limit_cancelled": self._format_limit_cancelled,
            "close": self._format_close,
            "scale_out": self._format_scale_out,
            "scale_in": self._format_scale_in,
            "update_sl": self._format_sl_update,
            "update_tp": self._format_tp_update,
            "cancel_sl": self._format_sl_cancel,
            "cancel_tp": self._format_tp_cancel,
            "leverage": self._format_leverage,
            "margin": self._format_margin,
        }
        formatter = formatters.get(signal_type)
        return formatter(event) if formatter else None

    # --------------------------------------------------------------------------
    # HELPER — Leverage + SL/TP aus Parser-State holen
    # --------------------------------------------------------------------------

    def _has_live_position(self, position_id: str) -> bool:
        """True, wenn zu dieser positionID eine echte offene Position (size > 0)
        im Parser-State existiert. Unterscheidet einen echten Nachkauf von einer
        nur wartenden/neu eingestellten Limit-Order."""
        if not self._parser or not position_id:
            return False
        pos = self._parser._positions.get(position_id)
        return bool(pos and float(pos.size or 0) > 0)

    def _get_leverage(self, position_id: str) -> float:
        """Leverage aus Parser-State holen."""
        if not self._parser or not position_id:
            return 0
        lev_str = self._parser.get_leverage_for_position(position_id)
        if lev_str:
            try:
                return float(lev_str)
            except (ValueError, TypeError):
                pass
        return 0

    def _get_sl_tp(self, position_id: str) -> tuple[float, float]:
        """SL und TP aus Parser-State holen. Returns (sl, tp)."""
        if not self._parser or not position_id:
            return 0, 0
        sl_tp = self._parser.get_sl_tp_for_position(position_id)
        sl = float(sl_tp.get("stopLoss", 0) or 0)
        tp = float(sl_tp.get("takeProfit", 0) or 0)
        return sl, tp

    def _get_liquidation(self, position_id: str) -> float:
        """Liquidationspreis aus Parser-State holen. 0 wenn keine offene Position."""
        if not self._parser or not position_id:
            return 0
        liq_str = self._parser.get_liquidation_for_position(position_id)
        if liq_str:
            try:
                return float(liq_str)
            except (ValueError, TypeError):
                pass
        return 0

    # --------------------------------------------------------------------------
    # 1. NEUE POSITION (Market Order)
    # --------------------------------------------------------------------------

    def _format_open_market(self, event: ParsedEvent) -> str:
        d = event.details
        entry = float(d.get("execPrice", d.get("price", 0)) or 0)
        position_id = d.get("positionID", d.get("orderID", ""))
        display_name = self._get_or_create_display_name(event, entry_price=entry)

        # SL/TP aus Batch-Merge oder Parser-State
        sl = float(d.get("stopLoss", 0) or 0)
        tp = float(d.get("takeProfit", 0) or 0)
        if (not sl or not tp) and self._parser and position_id:
            parser_sl, parser_tp = self._get_sl_tp(position_id)
            if not sl:
                sl = parser_sl
            if not tp:
                tp = parser_tp

        leverage = self._get_leverage(position_id)
        side = d.get("side", "Buy")

        lines = [
            f"🟢 <b>Neue Position — {display_name}</b>",
            "",
            f"Entry:       {self._fmt_price(entry)}",
        ]

        if tp > 0:
            tp_pct = self._calc_sl_tp_pct(entry, tp, side)
            lines.append(f"TP:          {self._fmt_price(tp)} ({self._fmt_pct(tp_pct)})")
        if sl > 0:
            sl_pct = self._calc_sl_tp_pct(entry, sl, side)
            lines.append(f"SL:          {self._fmt_price(sl)} ({self._fmt_pct(sl_pct)})")

        liq = self._get_liquidation(position_id)
        if liq > 0:
            lines.append(f"Liquidation: {self._fmt_price(liq)}")

        lines.append(f"Type:        Market Order")

        lev_str = self._fmt_leverage(leverage)
        if lev_str:
            lines.append(f"Hebel:       {lev_str}")

        # Kontoanteil: wie viel % des Accounts dieser Trade ausmacht
        qty = float(d.get("execQty", d.get("orderQty", 0)) or 0)
        acct_pct = self._calc_account_pct(qty, entry, leverage, position_id=position_id)
        if acct_pct is not None:
            lines.append(f"Einsatz:     {self._fmt_account_pct(acct_pct)} des Kontos")

        crv = self._calc_crv(entry, sl, tp, side)
        if crv:
            lines.append(f"CRV:         {str(crv).replace('.', ',')}")

        if leverage > 0:
            risk_bar, risk_label = self._calc_risk_rating(leverage)
            lines.append(f"Risiko:      {risk_bar} {risk_label}")

        lines.extend(["", FOOTER])
        return "\n".join(lines)

    # --------------------------------------------------------------------------
    # 2. NEUE LIMIT ORDER
    # --------------------------------------------------------------------------

    def _format_new_limit(self, event: ParsedEvent) -> str:
        d = event.details
        entry = float(d.get("price", 0) or 0)
        position_id = d.get("positionID", d.get("orderID", ""))
        display_name = self._get_or_create_display_name(event, entry_price=entry)

        sl = float(d.get("stopLoss", 0) or 0)
        tp = float(d.get("takeProfit", 0) or 0)
        if (not sl or not tp) and self._parser and position_id:
            parser_sl, parser_tp = self._get_sl_tp(position_id)
            if not sl:
                sl = parser_sl
            if not tp:
                tp = parser_tp

        leverage = self._get_leverage(position_id)
        side = d.get("side", "Buy")

        lines = [
            f"🟡 <b>Neue Limit Order — {display_name}</b>",
            "",
            f"Entry:       {self._fmt_price(entry)}",
        ]

        if tp > 0:
            tp_pct = self._calc_sl_tp_pct(entry, tp, side)
            lines.append(f"TP:          {self._fmt_price(tp)} ({self._fmt_pct(tp_pct)})")
        if sl > 0:
            sl_pct = self._calc_sl_tp_pct(entry, sl, side)
            lines.append(f"SL:          {self._fmt_price(sl)} ({self._fmt_pct(sl_pct)})")

        lev_str = self._fmt_leverage(leverage)
        if lev_str:
            lines.append(f"Hebel:       {lev_str}")

        # Kontoanteil: wie viel % des Accounts dieser Trade ausmacht
        qty = float(d.get("orderQty", 0) or 0)
        acct_pct = self._calc_account_pct(qty, entry, leverage)
        if acct_pct is not None:
            lines.append(f"Einsatz:     {self._fmt_account_pct(acct_pct)} des Kontos")

        crv = self._calc_crv(entry, sl, tp, side)
        if crv:
            lines.append(f"CRV:         {str(crv).replace('.', ',')}")

        if leverage > 0:
            risk_bar, risk_label = self._calc_risk_rating(leverage)
            lines.append(f"Risiko:      {risk_bar} {risk_label}")

        lines.extend(["", "⏳ Wartet auf Ausführung", "", FOOTER])
        return "\n".join(lines)

    # --------------------------------------------------------------------------
    # 2b. LIMIT ORDER ANGEPASST (Einstieg/Menge einer wartenden Limit geaendert)
    # --------------------------------------------------------------------------

    def _format_limit_amended(self, event: ParsedEvent) -> str:
        d = event.details
        old_price = float(d.get("oldPrice", 0) or 0)
        new_price = float(d.get("newPrice", 0) or 0)
        old_qty = float(d.get("oldQty", 0) or 0)
        new_qty = float(d.get("newQty", 0) or 0)
        position_id = d.get("positionID", "")

        display_name = self._db.get_signal_display_name(position_id) if position_id else None
        if not display_name:
            side = d.get("side", "Buy")
            symbol = event.symbol.replace("USDT", "").replace("PERP", "")
            direction = "Long" if side == "Buy" else "Short"
            display_name = f"{symbol} {direction}"

        lines = [
            "🔄 <b>Limit Order angepasst</b>",
            "",
            f"{display_name}",
        ]
        if old_price and new_price and old_price != new_price:
            lines.append(f"Einstieg: {self._fmt_price(old_price)} → {self._fmt_price(new_price)}")
        if old_qty and new_qty and old_qty != new_qty:
            lines.append(f"Menge: {self._fmt_qty(old_qty)} → {self._fmt_qty(new_qty)}")

        lines.extend(["", "⏳ Wartet auf Ausführung", "", FOOTER])
        return "\n".join(lines)

    # --------------------------------------------------------------------------
    # 3. LIMIT ORDER HINZUGEFUEGT (Nachkauf fuer bestehende Position)
    # --------------------------------------------------------------------------

    def _format_limit_added(self, event: ParsedEvent) -> str:
        d = event.details
        price = float(d.get("price", 0) or 0)
        position_id = d.get("positionID", "")
        display_name = self._db.get_signal_display_name(position_id) or event.symbol

        leverage = self._get_leverage(position_id)

        lines = [
            "🟡 <b>Limit Order hinzugefügt — Nachkauf</b>",
            "",
            f"Für {display_name}",
            f"Limit Preis: {self._fmt_price(price)}",
        ]

        lev_str = self._fmt_leverage(leverage)
        if lev_str:
            lines.append(f"Hebel:       {lev_str}")

        # Zusaetzlicher Kontoanteil durch diesen Limit-Nachkauf
        qty = float(d.get("orderQty", 0) or 0)
        acct_pct = self._calc_account_pct(qty, price, leverage)
        if acct_pct is not None:
            lines.append(f"Einsatz:     +{self._fmt_account_pct(acct_pct)} des Kontos")

        lines.extend(["", "⏳ Wartet auf Ausführung", "", FOOTER])
        return "\n".join(lines)

    # --------------------------------------------------------------------------
    # 4. LIMIT ORDER AUSGEFUEHRT (neue Position)
    # --------------------------------------------------------------------------

    def _format_limit_filled(self, event: ParsedEvent) -> str:
        d = event.details
        exec_price = float(d.get("execPrice", 0) or 0)
        position_id = d.get("positionID", d.get("orderID", ""))
        display_name = self._get_or_create_display_name(event, entry_price=exec_price)
        side = d.get("side", "Buy")

        sl, tp = self._get_sl_tp(position_id)
        leverage = self._get_leverage(position_id)
        liq = self._get_liquidation(position_id)

        lines = [
            "🟢 <b>Limit Order ausgeführt — {}</b>".format(display_name),
            "",
            f"Entry:       {self._fmt_price(exec_price)}",
        ]

        if tp > 0:
            tp_pct = self._calc_sl_tp_pct(exec_price, tp, side)
            lines.append(f"TP:          {self._fmt_price(tp)} ({self._fmt_pct(tp_pct)})")
        if sl > 0:
            sl_pct = self._calc_sl_tp_pct(exec_price, sl, side)
            lines.append(f"SL:          {self._fmt_price(sl)} ({self._fmt_pct(sl_pct)})")
        if liq > 0:
            lines.append(f"Liquidation: {self._fmt_price(liq)}")

        lev_str = self._fmt_leverage(leverage)
        if lev_str:
            lines.append(f"Hebel:       {lev_str}")

        lines.extend(["", FOOTER])
        return "\n".join(lines)

    # --------------------------------------------------------------------------
    # 5. LIMIT ORDER AUSGEFUEHRT (Nachkauf)
    # --------------------------------------------------------------------------

    def _format_limit_filled_scalein(self, event: ParsedEvent) -> str:
        d = event.details
        exec_price = float(d.get("execPrice", 0) or 0)
        position_id = d.get("positionID", "")
        display_name = self._db.get_signal_display_name(position_id) or event.symbol

        # Avg Entry aus Parser-State
        avg_entry = ""
        if self._parser and position_id:
            pos = self._parser._positions.get(position_id)
            if pos and pos.avgEntryPrice:
                avg_entry = pos.avgEntryPrice

        lines = [
            f"✅ <b>Limit Order ausgeführt — Nachkauf</b>",
            "",
            f"{display_name}",
            f"Nachkauf @   {self._fmt_price(exec_price)}",
        ]
        if avg_entry:
            lines.append(f"Avg Entry:   {self._fmt_price(avg_entry)}")

        liq = self._get_liquidation(position_id)
        if liq > 0:
            lines.append(f"Liquidation: {self._fmt_price(liq)}")

        lines.extend(["", FOOTER])
        return "\n".join(lines)

    # --------------------------------------------------------------------------
    # 6. LIMIT ORDER STORNIERT
    # --------------------------------------------------------------------------

    def _format_limit_cancelled(self, event: ParsedEvent) -> str:
        d = event.details
        price = d.get("price", "?")
        position_id = d.get("positionID", "")
        order_id = d.get("orderID", "")

        display_name = self._db.get_signal_display_name(position_id) if position_id else None
        if not display_name:
            display_name = event.symbol.replace("USDT", "").replace("PERP", "")

        lines = [
            "⚪ <b>Limit Order storniert</b>",
            "",
            f"{display_name}",
            f"Limit war: {self._fmt_price(price)}",
            "",
            FOOTER,
        ]
        return "\n".join(lines)

    # --------------------------------------------------------------------------
    # 7. POSITION GESCHLOSSEN
    # --------------------------------------------------------------------------

    def _format_close(self, event: ParsedEvent) -> str:
        d = event.details
        display_name = self._get_display_name_for_close(event)
        position_id = d.get("positionID", "")

        entry = float(d.get("avgEntryPrice", 0) or 0)
        exit_price = float(d.get("markPrice", 0) or 0)
        side = d.get("side", "Buy")
        pnl_pct = self._calc_position_pnl_pct(entry, exit_price, side, position_id)

        pnl_float = 0
        if pnl_pct:
            try:
                pnl_float = float(pnl_pct.replace("%", ""))
            except ValueError:
                pass

        # Close-Type erkennen: zuerst der eindeutige Hinweis aus dem ausloesenden
        # Fill (StopMarket=SL, MarketIfTouched=TP), sonst Fallback auf die
        # Preis-Heuristik (markPrice vs SL/TP-Trigger).
        fill_hint = d.get("closeFillType", "")
        if fill_hint == "sl":
            close_type = "sl_profit" if pnl_float >= 0 else "sl_loss"
        elif fill_hint == "tp":
            close_type = "tp"
        else:
            sl, tp = self._get_sl_tp(position_id)
            close_type = self._detect_close_type(entry, exit_price, sl, tp, side)

        # Trade-Dauer
        trade_info = self._db.get_signal_trade_info(position_id)
        duration = ""
        if trade_info and trade_info.get("open_timestamp"):
            duration = self._format_duration(trade_info["open_timestamp"], time.time())

        # P&L Zeile
        if pnl_float >= 0:
            pnl_line = f"✅ Gewinn: <b>{pnl_pct}</b>"
        else:
            pnl_line = f"❌ Verlust: <b>{pnl_pct}</b>"

        # Headline + Close-Info basierend auf Close-Type
        if close_type == "tp":
            headline = f"🟢 <b>Take Profit getroffen — {display_name}</b>"
            close_label = "TP getroffen, ganze Position geschlossen"
        elif close_type == "sl_profit":
            headline = f"🟡 <b>SL im Gewinn — {display_name}</b>"
            close_label = "SL im Gewinn getroffen, ganze Position geschlossen"
        elif close_type == "sl_loss":
            headline = f"🔴 <b>Stop Loss getroffen — {display_name}</b>"
            close_label = "Stop Loss getroffen"
        else:
            headline = f"🔴 <b>Position geschlossen — {display_name}</b>"
            close_label = "Manuell geschlossen"

        lines = [
            headline,
            "",
            pnl_line,
        ]
        if entry > 0:
            lines.append(f"Entry:       {self._fmt_price(entry)}")
        if exit_price > 0:
            lines.append(f"Exit:        {self._fmt_price(exit_price)}")
        if duration:
            lines.append(f"Dauer:       {duration}")
        lines.append(f"Geschlossen: {close_label}")
        lines.extend(["", FOOTER])
        return "\n".join(lines)

    # --------------------------------------------------------------------------
    # 8. TEILSCHLIESSUNG (Scale-Out)
    # --------------------------------------------------------------------------

    def _format_scale_out(self, event: ParsedEvent) -> str:
        d = event.details
        position_id = d.get("positionID", "")
        display_name = self._db.get_signal_display_name(position_id) or event.symbol

        prev_size = float(d.get("previousSize", 0) or 0)
        new_size = float(d.get("newSize", 0) or 0)
        pct = 0
        remaining_pct = 100
        if prev_size > 0:
            pct = ((prev_size - new_size) / prev_size) * 100
            remaining_pct = (new_size / prev_size) * 100

        # Exit-Preis aus Parser-State
        exit_price = ""
        exit_price_float = 0
        if self._parser and position_id:
            pos = self._parser._positions.get(position_id)
            if pos and pos.markPrice:
                exit_price = pos.markPrice
                try:
                    exit_price_float = float(pos.markPrice)
                except (ValueError, TypeError):
                    pass

        # Close-Type erkennen (TP-Teilschliessung?)
        entry = 0
        side = ""
        if self._parser and position_id:
            pos = self._parser._positions.get(position_id)
            if pos:
                try:
                    entry = float(pos.avgEntryPrice or 0)
                except (ValueError, TypeError):
                    pass
                side = pos.side or ""

        sl, tp = self._get_sl_tp(position_id)
        close_type = self._detect_close_type(entry, exit_price_float, sl, tp, side)

        # Headline basierend auf Close-Type
        if close_type == "tp":
            headline = f"🟢 <b>Take Profit getroffen — {display_name}</b>"
            action_line = f"TP getroffen, {pct:.0f}% der Position geschlossen."
        elif close_type == "sl_profit":
            headline = f"🟡 <b>SL im Gewinn — {display_name}</b>"
            action_line = f"SL im Gewinn getroffen, {pct:.0f}% der Position geschlossen."
        elif close_type == "sl_loss":
            headline = f"🔴 <b>Stop Loss getroffen — {display_name}</b>"
            action_line = f"Stop Loss getroffen, {pct:.0f}% der Position geschlossen."
        else:
            headline = f"📉 <b>Trade Update — {display_name}</b>"
            action_line = f"Ich habe soeben {pct:.0f}% der Position geschlossen."

        lines = [
            headline,
            "",
            action_line,
        ]
        if exit_price:
            lines.append(f"Exit:        {self._fmt_price(exit_price)}")
        lines.append(f"Verbleibend: {remaining_pct:.0f}%")
        lines.extend(["", FOOTER])
        return "\n".join(lines)

    # --------------------------------------------------------------------------
    # 9. NACHKAUF / SCALE-IN (Market)
    # --------------------------------------------------------------------------

    def _format_scale_in(self, event: ParsedEvent) -> str:
        d = event.details
        position_id = d.get("positionID", "")
        display_name = self._db.get_signal_display_name(position_id) or event.symbol
        avg_entry = d.get("avgEntryPrice", "")

        # Exec-Preis: Differenz ableiten oder aus Parser
        exec_price = ""
        if self._parser and position_id:
            pos = self._parser._positions.get(position_id)
            if pos and pos.markPrice:
                exec_price = pos.markPrice

        lines = [
            f"📈 <b>Position Skalierung — {display_name}</b>",
            "",
            "Scale-In / Nachkauf",
        ]
        if exec_price:
            lines.append(f"Nachkauf @   {self._fmt_price(exec_price)}")
        if avg_entry:
            lines.append(f"Avg Entry:   {self._fmt_price(avg_entry)}")

        liq = self._get_liquidation(position_id)
        if liq > 0:
            lines.append(f"Liquidation: {self._fmt_price(liq)}")

        # Zusaetzlicher Kontoanteil durch den Nachkauf (nur die hinzugefuegte Menge).
        # Nutzt die ECHTE Gesamt-posMargin der Position und rechnet den hinzugefuegten
        # Anteil (added_qty / new_size) heraus; Rekonstruktion nur als Fallback.
        try:
            new_size = float(d.get("newSize", 0) or 0)
            added_qty = new_size - float(d.get("previousSize", 0) or 0)
            ref_price = float(exec_price or avg_entry or 0)
            leverage = self._get_leverage(position_id)
            added_ratio = (added_qty / new_size) if new_size > 0 else None
            acct_pct = self._calc_account_pct(added_qty, ref_price, leverage,
                                              position_id=position_id, added_ratio=added_ratio)
            if acct_pct is not None:
                lines.append(f"Einsatz:     +{self._fmt_account_pct(acct_pct)} des Kontos")
        except (ValueError, TypeError):
            pass

        lines.extend(["", FOOTER])
        return "\n".join(lines)

    # --------------------------------------------------------------------------
    # 10. SL ANPASSUNG
    # --------------------------------------------------------------------------

    def _format_sl_update(self, event: ParsedEvent) -> str:
        d = event.details
        position_id = d.get("positionID", d.get("orderID", ""))
        display_name = self._db.get_signal_display_name(position_id) or event.symbol

        old_price = d.get("oldStopPrice", "")
        new_price = d.get("newStopPrice", d.get("stopPrice", "?"))

        # Kontext: "im Gewinn", "Break-Even", oder nichts
        context = ""
        trade_info = self._db.get_signal_trade_info(position_id)
        if trade_info and trade_info.get("entry_price"):
            entry = trade_info["entry_price"]
            side = trade_info.get("side", "Buy")
            try:
                new_sl = float(new_price)
                # Break-Even? (SL ≈ Entry ±0.2%)
                if entry > 0 and abs(new_sl - entry) / entry <= 0.002:
                    context = " — Break-Even"
                elif side == "Buy" and new_sl > entry:
                    context = " — im Gewinn ✅"
                elif side == "Sell" and new_sl < entry:
                    context = " — im Gewinn ✅"
            except (ValueError, TypeError):
                pass

        lines = [
            f"⚙️ <b>Trade Management — {display_name}</b>",
            "",
            f"🛡️ Stop Loss angepasst{context}",
        ]
        if old_price:
            lines.append(f"SL: {self._fmt_price(old_price)} → {self._fmt_price(new_price)}")
        else:
            lines.append(f"SL: {self._fmt_price(new_price)}")
        lines.extend(["", FOOTER])
        return "\n".join(lines)

    # --------------------------------------------------------------------------
    # 11. TP ANPASSUNG
    # --------------------------------------------------------------------------

    def _format_tp_update(self, event: ParsedEvent) -> str:
        d = event.details
        position_id = d.get("positionID", d.get("orderID", ""))
        display_name = self._db.get_signal_display_name(position_id) or event.symbol

        old_price = d.get("oldStopPrice", "")
        new_price = d.get("newStopPrice", d.get("stopPrice", "?"))

        lines = [
            f"⚙️ <b>Trade Management — {display_name}</b>",
            "",
            "🎯 Take Profit angepasst",
        ]
        if old_price:
            lines.append(f"TP: {self._fmt_price(old_price)} → {self._fmt_price(new_price)}")
        else:
            lines.append(f"TP: {self._fmt_price(new_price)}")
        lines.extend(["", FOOTER])
        return "\n".join(lines)

    # --------------------------------------------------------------------------
    # 12. SL ENTFERNT
    # --------------------------------------------------------------------------

    def _format_sl_cancel(self, event: ParsedEvent) -> str:
        d = event.details
        position_id = d.get("positionID", d.get("orderID", ""))
        display_name = self._db.get_signal_display_name(position_id) or event.symbol

        return (
            f"⚙️ <b>Trade Management — {display_name}</b>\n"
            "\n"
            "🛡️ Stop Loss entfernt\n"
            f"\n{FOOTER}"
        )

    # --------------------------------------------------------------------------
    # 13. TP ENTFERNT
    # --------------------------------------------------------------------------

    def _format_tp_cancel(self, event: ParsedEvent) -> str:
        d = event.details
        position_id = d.get("positionID", d.get("orderID", ""))
        display_name = self._db.get_signal_display_name(position_id) or event.symbol

        return (
            f"⚙️ <b>Trade Management — {display_name}</b>\n"
            "\n"
            "🎯 Take Profit entfernt\n"
            f"\n{FOOTER}"
        )

    # --------------------------------------------------------------------------
    # 14. HEBEL ANPASSUNG
    # --------------------------------------------------------------------------

    def _format_leverage(self, event: ParsedEvent) -> str:
        d = event.details
        position_id = d.get("positionID", "")
        display_name = self._db.get_signal_display_name(position_id) or event.symbol

        old_lev = d.get("oldLeverage", "?")
        new_lev = d.get("newLeverage", "?")

        try:
            old_f = float(old_lev)
            new_f = float(new_lev)
            old_str = self._fmt_leverage(old_f)
            new_str = self._fmt_leverage(new_f)
            if new_f > old_f:
                explanation = (
                    f"Ich habe den Hebel bei {display_name} von {old_str} auf {new_str} erhöht "
                    f"und dadurch einen Großteil der zuvor gebundenen Margin aus der Position entnommen."
                )
            else:
                explanation = (
                    f"Ich habe den Hebel bei {display_name} von {old_str} auf {new_str} reduziert "
                    f"und dadurch zusätzliche Margin in der Position hinterlegt."
                )
            hebel_line = f"Hebel: {old_str} → {new_str}"
        except (ValueError, TypeError):
            explanation = f"Hebel: {old_lev}x → {new_lev}x"
            hebel_line = f"Hebel: {old_lev}x → {new_lev}x"

        lines = [
            f"⚙️ <b>Trade Update — {display_name} (Hebel)</b>",
            "",
            explanation,
            "",
            hebel_line,
            "",
            FOOTER,
        ]
        return "\n".join(lines)

    # --------------------------------------------------------------------------
    # 15. MARGIN ANPASSUNG
    # --------------------------------------------------------------------------

    def _format_margin(self, event: ParsedEvent) -> str:
        d = event.details
        position_id = d.get("positionID", "")
        display_name = self._db.get_signal_display_name(position_id) or event.symbol

        old_margin = float(d.get("oldMargin", 0) or 0)
        new_margin = float(d.get("newMargin", 0) or 0)

        # Liquidierungspreis aus Parser-State
        liq_price = ""
        if self._parser and position_id:
            pos = self._parser._positions.get(position_id)
            if pos and pos.liquidationPrice:
                liq_price = pos.liquidationPrice

        if new_margin > old_margin:
            explanation = f"Ich habe bei {display_name} zusätzliche Margin hinzugefügt."
            if liq_price:
                explanation += f" Mein Liquidierungspreis liegt jetzt bei {self._fmt_price(liq_price)}."
            lines = [
                f"⚙️ <b>Trade Update — {display_name} (Margin)</b>",
                "",
                f"💰 {explanation}",
                "",
                FOOTER,
            ]
        else:
            explanation = f"Ich habe bei {display_name} Margin entnommen."
            if liq_price:
                explanation += f" Mein Liquidierungspreis liegt jetzt bei {self._fmt_price(liq_price)}."
            lines = [
                f"⚙️ <b>Trade Update — {display_name} (Margin)</b>",
                "",
                f"💰 {explanation}",
                "",
                FOOTER,
            ]
        return "\n".join(lines)

    # --------------------------------------------------------------------------
    # MARKETING CHANNEL — Profitable Trades + Summaries
    # --------------------------------------------------------------------------

    async def _maybe_send_marketing_showcase(self, event: ParsedEvent, position_id: str) -> bool:
        if not self._marketing_channel_id:
            return False

        d = event.details
        display_name = self._db.get_signal_display_name(position_id)
        if not display_name:
            short_symbol = event.symbol.replace("USDT", "").replace("PERP", "")
            display_name = short_symbol

        entry = float(d.get("avgEntryPrice", 0) or 0)
        exit_price = float(d.get("markPrice", 0) or 0)
        side = d.get("side", "Buy")
        pnl_pct = self._calc_position_pnl_pct(entry, exit_price, side, position_id)

        if not pnl_pct:
            return False

        try:
            pnl_float = float(pnl_pct.replace("%", ""))
            if pnl_float < MARKETING_MIN_PNL_PCT:
                return False
        except ValueError:
            return False

        showcase_msg = (
            f"🔥 <b>TRADE GESCHLOSSEN: {pnl_pct}</b>\n"
            "\n"
            f"📊 <b>{display_name}</b>\n"
            "\n"
            f"Unsere Premium-Mitglieder haben diesen Trade in Echtzeit erhalten "
            f"— inklusive Entry, Stop-Loss und Take-Profit.\n"
            "\n"
            f"👉 <a href=\"{SIGNUP_URL}\">Jetzt Copy Trading freischalten</a>"
        )

        sent = await self._send_to_marketing(showcase_msg)
        if sent:
            logger.info(f"[SIGNAL] MARKETING | {display_name} ({pnl_pct}) → Community Channel")
        return sent

    # --------------------------------------------------------------------------
    # 16. OFFENE POSITIONEN — Taegliche Uebersicht (21:00 DE)
    # --------------------------------------------------------------------------

    async def _send_daily_overview(self) -> None:
        """Taegliche Uebersicht aller offenen Positionen senden.

        Nach Scalp/Main getrennt: Scalp-Positionen (>= Schwellen-Hebel) gehen in
        die Scalp-Gruppe, alle uebrigen in die Main-Gruppe.
        """
        active = self._db.get_all_active_signals()

        # Nur ECHTE offene Positionen als "Aktive Trades" zeigen.
        # Eine wartende Limit-Order bekommt zwar schon einen Namen in der DB
        # (damit der Trade von Anfang an gleich heisst), hat aber noch KEINE echte
        # Position — sie steht also nicht im Parser-Positions-State. Solche Eintraege
        # duerfen hier NICHT als offener Trade auftauchen; sie erscheinen ausschliesslich
        # unten unter "Offene Limit Orders". Sobald die Limit ausgefuehrt ist, existiert
        # eine echte Position und der Trade wird hier ganz normal als aktiv gelistet.
        open_trades = []
        for trade in active:
            pos_id = trade["position_id"]
            if not self._parser or not pos_id:
                open_trades.append(trade)  # ohne Parser kein Abgleich moeglich -> behalten
                continue
            pos = self._parser._positions.get(pos_id)
            if pos and float(pos.size or 0) > 0:
                open_trades.append(trade)

        # Nach Scalp/Main partitionieren (Trades + wartende Limit Orders)
        scalp_enabled = bool(self._scalp_group_id)
        main_trades = [t for t in open_trades if not (scalp_enabled and t.get("is_scalp"))]
        scalp_trades = [t for t in open_trades if scalp_enabled and t.get("is_scalp")]

        # Wartende Limit-Orders aus dem PARSER-State holen (nicht aus dem fluechtigen
        # _pending_limits-Dict): Der Parser wird bei jedem Snapshot/Reconnect neu
        # aufgebaut, das In-Memory-Dict des Signal-Bots NICHT. Frueher fehlten nach
        # einem Neustart deshalb alle wartenden Limits in der Uebersicht.
        if self._parser:
            pending_source = {
                o["orderID"]: o for o in self._parser.get_pending_limit_orders()
            }
        else:
            pending_source = dict(self._pending_limits)

        main_limits: dict[str, dict] = {}
        scalp_limits: dict[str, dict] = {}
        for oid, info in pending_source.items():
            pid = info.get("positionID", "")
            if scalp_enabled and pid and self._db.is_scalp_position(pid):
                scalp_limits[oid] = info
            else:
                main_limits[oid] = info

        await self._send_overview_message(
            main_trades, main_limits, self._paid_group_id, "📋 <b>Offene Positionen</b>"
        )
        if scalp_enabled:
            await self._send_overview_message(
                scalp_trades, scalp_limits, self._scalp_group_id,
                "📋 <b>Offene Positionen — Scalp ⚡</b>",
            )

    async def _send_overview_message(
        self, open_trades: list[dict], pending_limits: dict, group_id: str, title: str
    ) -> None:
        """Eine Uebersichts-Nachricht bauen und an eine Gruppe senden."""
        if not open_trades and not pending_limits:
            msg = (
                f"{title}\n"
                "\n"
                "Aktuell keine aktiven Trades oder Limit Orders.\n"
                f"\n{FOOTER}"
            )
            await self._send_to_group(group_id, msg)
            logger.info(f"[SIGNAL] DAILY OVERVIEW ({title}) | Keine aktiven Positionen")
            return

        lines = [title, ""]

        if open_trades:
            lines.append("Aktive Trades:")

        for trade in open_trades:
            pos_id = trade["position_id"]
            display_name = trade["display_name"]
            entry = trade.get("entry_price", 0)

            # Aktueller P&L aus Parser-State
            pnl_str = ""
            lev_str = ""
            if self._parser and pos_id:
                pos = self._parser._positions.get(pos_id)
                if pos:
                    mark = float(pos.markPrice) if pos.markPrice else 0
                    side = trade.get("side", "Buy")
                    leverage = float(pos.leverage) if pos.leverage else 1
                    if entry > 0 and mark > 0:
                        if side == "Buy":
                            pct = (mark - entry) / entry * 100 * leverage
                        else:
                            pct = (entry - mark) / entry * 100 * leverage
                        pnl_str = f"{pct:+.1f}%".replace(".", ",")
                    fmt_lev = self._fmt_leverage(leverage)
                    if fmt_lev:
                        lev_str = f"({fmt_lev})"

            detail = f"📊 {display_name}"
            if pnl_str:
                detail += f"    →  {pnl_str}"
            if lev_str:
                detail += f"  {lev_str}"
            lines.append(detail)

        # Offene Limit Orders
        if pending_limits:
            lines.extend(["", "Offene Limit Orders:"])
            for order_id, info in pending_limits.items():
                symbol = info.get("symbol", "?").replace("USDT", "").replace("PERP", "")
                price = info.get("price", "?")
                pos_id = info.get("positionID", "")
                display_name = self._db.get_signal_display_name(pos_id) if pos_id else None

                # "Nachkauf" NUR wenn wirklich eine LIVE-Position offen ist (echter
                # Nachkauf-Limit auf eine bestehende Position). Eine normale Entry-Limit
                # bekommt zwar auch sofort einen Display-Namen in der DB (damit der Trade
                # von Anfang an gleich heisst), ist aber KEIN Nachkauf -- sonst wird jede
                # ganz normale Limit-Order faelschlich als "Nachkauf" gelabelt. Gleiche
                # Unterscheidung wie in _classify (limit_added vs new_limit).
                if display_name and self._has_live_position(pos_id):
                    lines.append(f"⏳ {display_name}    →  Nachkauf @ {self._fmt_price(price)}")
                elif display_name:
                    lines.append(f"⏳ {display_name}    →  Limit @ {self._fmt_price(price)}")
                else:
                    side = info.get("side", "Buy")
                    direction = "Long" if side == "Buy" else "Short"
                    lines.append(f"⏳ {symbol} {direction}    →  Limit @ {self._fmt_price(price)}")

        lines.extend(["", FOOTER])
        msg = "\n".join(lines)
        sent = await self._send_to_group(group_id, msg)
        logger.info(
            f"[SIGNAL] DAILY OVERVIEW ({title}) | {len(open_trades)} aktive Trades | "
            f"{len(pending_limits)} offene Limits | Gesendet: {'✓' if sent else '✗'}"
        )

    async def _daily_overview_scheduler(self) -> None:
        """Hintergrund-Task: Sendet taeglich um 21:00 deutscher Zeit eine Uebersicht."""
        while True:
            try:
                now = datetime.utcnow()
                # 21:00 CEST = 19:00 UTC (Sommer), 21:00 CET = 20:00 UTC (Winter)
                # Wir pruefen beide Stunden, da Sommer/Winter-Zeitumstellung
                if now.hour in (19, 20) and now.minute == 0:
                    await self._send_daily_overview()
                    # Nach dem Senden 23 Stunden warten um doppeltes Senden zu vermeiden
                    await asyncio.sleep(82800)
                else:
                    await asyncio.sleep(55)  # Jede Minute pruefen
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[SIGNAL] Daily-Overview-Scheduler Fehler: {e}")
                await asyncio.sleep(60)

    # --------------------------------------------------------------------------
    # SCHEDULED SUMMARIES — Woechentlich + Monatlich → Marketing Channel
    # --------------------------------------------------------------------------

    async def _summary_scheduler(self) -> None:
        """Hintergrund-Task: Prueft jede Stunde ob eine Summary faellig ist."""
        while True:
            try:
                now = datetime.utcnow()
                if now.weekday() == 6 and now.hour == 18:
                    await self._send_weekly_summary()
                tomorrow = now + timedelta(days=1)
                if tomorrow.day == 1 and now.hour == 18:
                    await self._send_monthly_summary()
                await asyncio.sleep(3540)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[SIGNAL] Summary-Scheduler Fehler: {e}")
                await asyncio.sleep(60)

    async def _send_weekly_summary(self) -> None:
        if not self._marketing_channel_id:
            return
        try:
            perf = self._db.get_period_performance(days=7)
            if perf["total_trades"] == 0:
                logger.info("[SIGNAL] Wochen-Summary uebersprungen — keine Trades")
                return

            msg = (
                "📊 <b>WOCHEN-PERFORMANCE</b>\n"
                "\n"
                f"📈 Trades: <b>{perf['total_trades']}</b>\n"
                f"✅ Wins: <b>{perf['wins']}</b> | ❌ Losses: <b>{perf['losses']}</b>\n"
                f"🎯 Win Rate: <b>{perf['win_rate']:.0f}%</b>\n"
                f"💰 Gesamt P&amp;L: <b>{self._fmt_pnl_usdt(perf['total_pnl'])} USDT</b>\n"
                "\n"
                "Das sind die Ergebnisse unserer Copy Trading Gruppe "
                "der letzten 7 Tage.\n"
                "\n"
                f"👉 <a href=\"{SIGNUP_URL}\">Du willst dabei sein? Jetzt anmelden</a>"
            )
            sent = await self._send_to_marketing(msg)
            if sent:
                logger.info(f"[SIGNAL] WEEKLY SUMMARY → Marketing Channel")
        except Exception as e:
            logger.warning(f"[SIGNAL] Wochen-Summary fehlgeschlagen: {e}")

    async def _send_monthly_summary(self) -> None:
        if not self._marketing_channel_id:
            return
        try:
            perf = self._db.get_period_performance(days=30)
            if perf["total_trades"] == 0:
                logger.info("[SIGNAL] Monats-Summary uebersprungen — keine Trades")
                return

            now = datetime.utcnow()
            _monate = ["", "Januar", "Februar", "März", "April", "Mai", "Juni",
                       "Juli", "August", "September", "Oktober", "November", "Dezember"]
            monat = _monate[now.month]

            msg = (
                f"📈 <b>MONATS-PERFORMANCE — {monat} {now.year}</b>\n"
                "\n"
                f"📊 Trades: <b>{perf['total_trades']}</b>\n"
                f"✅ Wins: <b>{perf['wins']}</b> | ❌ Losses: <b>{perf['losses']}</b>\n"
                f"🎯 Win Rate: <b>{perf['win_rate']:.0f}%</b>\n"
                f"💰 Gesamt P&amp;L: <b>{self._fmt_pnl_usdt(perf['total_pnl'])} USDT</b>\n"
                "\n"
                f"So hat unsere Copy Trading Gruppe im {monat} performt.\n"
                "\n"
                f"👉 <a href=\"{SIGNUP_URL}\">Du willst dabei sein? Jetzt anmelden</a>"
            )
            sent = await self._send_to_marketing(msg)
            if sent:
                logger.info(f"[SIGNAL] MONTHLY SUMMARY → Marketing Channel | {monat} {now.year}")
        except Exception as e:
            logger.warning(f"[SIGNAL] Monats-Summary fehlgeschlagen: {e}")

    # --------------------------------------------------------------------------
    # CLEANUP
    # --------------------------------------------------------------------------

    async def close(self) -> None:
        if self._summary_task and not self._summary_task.done():
            self._summary_task.cancel()
        if self._daily_overview_task and not self._daily_overview_task.done():
            self._daily_overview_task.cancel()
        if self._session and not self._session.closed:
            await self._session.close()
