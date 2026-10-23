"""
(C) telegram.py — Telegram Alert System fuer den Copy Trading Bot

Schickt Benachrichtigungen ans Team via Telegram Bot.
Alerts fuer: Trade-Execution, Fehler, Restart, Reconciliation, Reconnects.

Features:
- Multi-Subscriber: Jeder im Team kann sich selbst onboarden
- Self-Service: /start + Team-Passwort zum Subscriben, /stop zum Abmelden
- Non-blocking: Sendefehler werden geloggt, crashen den Bot aber nicht

Subscriber-Verwaltung laeuft als Background-Task der Telegram getUpdates pollt.
"""

import asyncio
import json
import time
import aiohttp
from typing import TYPE_CHECKING

from logger_setup import logger

if TYPE_CHECKING:
    from database import Database
    from execution import ExecutionEngine
    from parser import OrderParser


class TelegramAlert:
    """
    Sendet Nachrichten an alle registrierten Telegram Subscriber.
    Verarbeitet eingehende Commands (/start, /stop, /status) via Polling.
    """

    def __init__(self, bot_token: str, chat_id: str, team_password: str = "",
                 db: "Database | None" = None,
                 paid_group_id: str = "", scalp_group_id: str = "") -> None:
        self._bot_token = bot_token
        self._admin_chat_id = chat_id  # Admin (Max) — immer aktiv, auch ohne DB
        self._team_password = team_password
        self._db = db
        # Gruppen-IDs fuer die Beitritts-Gate (Scalp-Gruppe):
        # Eine Beitrittsanfrage zur Scalp-Gruppe wird NUR freigegeben, wenn der User
        # bereits Mitglied der (zahlungs-gated) Main-Paid-Gruppe ist. So ist ein
        # weitergegebener Invite-Link fuer Aussenstehende wertlos.
        self._paid_group_id = str(paid_group_id or "")
        self._scalp_group_id = str(scalp_group_id or "")
        self._base_url = f"https://api.telegram.org/bot{bot_token}"
        self._session: aiohttp.ClientSession | None = None
        self._enabled = bool(bot_token and chat_id)
        self._polling_task: asyncio.Task | None = None
        self._last_update_id: int = 0
        self._start_time: float = time.time()

        # Werden von listen.py gesetzt nach Initialisierung
        self._engine: "ExecutionEngine | None" = None
        self._parser: "OrderParser | None" = None
        self._env: str = ""
        self._ws_connected: bool = False

        if not self._enabled:
            logger.info("[TG] Telegram Alerts deaktiviert (Token oder Chat ID fehlt)")
        else:
            logger.info("[TG] Telegram Alerts aktiviert")
            if self._db and self._team_password:
                logger.info("[TG] Self-Service Onboarding aktiv (Team-Passwort gesetzt)")

    # --------------------------------------------------------------------------
    # SESSION
    # --------------------------------------------------------------------------

    async def _get_session(self) -> aiohttp.ClientSession:
        """Lazy Session-Erstellung."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    # --------------------------------------------------------------------------
    # SUBSCRIBER MANAGEMENT
    # --------------------------------------------------------------------------

    def _get_all_chat_ids(self) -> list[str]:
        """Alle Chat IDs sammeln: Admin + DB-Subscriber."""
        chat_ids = set()

        # Admin immer dabei
        if self._admin_chat_id:
            chat_ids.add(self._admin_chat_id)

        # DB Subscriber
        if self._db:
            try:
                db_ids = self._db.get_active_telegram_subscribers()
                chat_ids.update(db_ids)
            except Exception as e:
                logger.warning(f"[TG] DB Subscriber laden fehlgeschlagen: {e}")

        return list(chat_ids)

    # --------------------------------------------------------------------------
    # SENDEN
    # --------------------------------------------------------------------------

    async def _send_to(self, chat_id: str, text: str, parse_mode: str = "HTML") -> None:
        """Nachricht an einen spezifischen Chat senden."""
        try:
            session = await self._get_session()
            url = f"{self._base_url}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
            }
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.warning(f"[TG] Telegram API Fehler {resp.status} (Chat {chat_id}): {body}")
        except Exception as e:
            logger.warning(f"[TG] Senden fehlgeschlagen (Chat {chat_id}): {e}")

    async def _send(self, text: str, parse_mode: str = "HTML") -> None:
        """Nachricht an ALLE Subscriber senden."""
        if not self._enabled:
            return

        chat_ids = self._get_all_chat_ids()
        if not chat_ids:
            return

        # Parallel an alle senden
        tasks = [self._send_to(cid, text, parse_mode) for cid in chat_ids]
        await asyncio.gather(*tasks, return_exceptions=True)

    # --------------------------------------------------------------------------
    # POLLING — Eingehende Nachrichten verarbeiten
    # --------------------------------------------------------------------------

    def start_polling(self) -> None:
        """Polling als Background-Task starten."""
        if not self._enabled or not self._db:
            return
        self._polling_task = asyncio.create_task(self._poll_loop())
        logger.info("[TG] Polling gestartet — warte auf /start und /stop Commands")

    async def _poll_loop(self) -> None:
        """Endlos-Loop der Telegram getUpdates pollt."""
        while True:
            try:
                await self._process_updates()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"[TG] Polling Fehler: {e}")
            await asyncio.sleep(3)

    async def _process_updates(self) -> None:
        """Neue Nachrichten von Telegram abholen und verarbeiten."""
        session = await self._get_session()
        url = f"{self._base_url}/getUpdates"
        # allowed_updates explizit setzen — sonst liefert Telegram KEINE
        # chat_join_request-Events (die brauchen wir fuer das Scalp-Beitritts-Gate).
        params = {
            "offset": self._last_update_id + 1,
            "timeout": 5,
            "allowed_updates": json.dumps(["message", "chat_join_request"]),
        }

        try:
            async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    return
                data = await resp.json()
        except Exception:
            return

        if not data.get("ok"):
            return

        for update in data.get("result", []):
            self._last_update_id = update["update_id"]
            # Beitrittsanfrage (Scalp-Gruppe) zuerst behandeln
            join_req = update.get("chat_join_request")
            if join_req:
                await self._handle_join_request(join_req)
                continue
            message = update.get("message")
            # Scalp-Gruppe: "beigetreten/verlassen"-Systemmeldungen wegraeumen
            if message and await self._maybe_delete_service_message(message):
                continue
            if not message or not message.get("text"):
                continue
            await self._handle_command(message)

    # --------------------------------------------------------------------------
    # SCALP-GRUPPE — Beitritts-/Verlassen-Systemmeldungen automatisch loeschen
    # --------------------------------------------------------------------------

    async def _maybe_delete_service_message(self, message: dict) -> bool:
        """"X ist beigetreten / hat verlassen"-Meldungen in der Scalp-Gruppe loeschen.

        Telegram postet diese Systemnachrichten automatisch; ein natives Aus gibt es
        in Gruppen nicht. Der Bot (Admin) loescht sie sofort wieder, damit Mitglieder
        nicht sehen wer bei-/austritt. Returns True, wenn es eine solche Meldung war.
        """
        if not self._scalp_group_id:
            return False
        chat_id = str(message.get("chat", {}).get("id", ""))
        if chat_id != self._scalp_group_id:
            return False
        is_service = (
            "new_chat_members" in message
            or "new_chat_member" in message
            or "left_chat_member" in message
        )
        if not is_service:
            return False
        mid = message.get("message_id")
        if mid:
            await self._delete_message(chat_id, mid)
            logger.info(f"[TG] Scalp: Beitritts-/Verlassen-Meldung geloescht (msg {mid})")
        return True

    async def _delete_message(self, chat_id: str, message_id) -> None:
        """Eine Nachricht loeschen (Bot muss Admin mit Loeschrecht sein)."""
        try:
            session = await self._get_session()
            async with session.post(
                f"{self._base_url}/deleteMessage",
                json={"chat_id": chat_id, "message_id": message_id},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.warning(f"[TG] deleteMessage Fehler {resp.status}: {body}")
        except Exception as e:
            logger.warning(f"[TG] deleteMessage fehlgeschlagen: {e}")

    # --------------------------------------------------------------------------
    # BEITRITTS-GATE — Scalp-Gruppe: nur Main-Paid-Mitglieder reinlassen
    # --------------------------------------------------------------------------

    async def _handle_join_request(self, req: dict) -> None:
        """Beitrittsanfrage zur Scalp-Gruppe automatisch freigeben/ablehnen.

        Freigabe NUR wenn der anfragende User bereits Mitglied der Main-Paid-Gruppe
        ist (die selbst zahlungs-gated ist). Weitergeleiteter Link -> Aussenstehender
        -> automatisch abgelehnt. Bei API-Fehler: Anfrage offen lassen + Admin-Alert
        (fail-safe, damit kein zahlender Kunde faelschlich abgelehnt wird).
        """
        chat = req.get("chat", {})
        chat_id = str(chat.get("id", ""))
        user = req.get("from", {})
        user_id = user.get("id")
        username = user.get("username", "")
        first_name = user.get("first_name", "")

        # Nur die Scalp-Gruppe gaten — andere Gruppen ignorieren
        if not self._scalp_group_id or chat_id != self._scalp_group_id:
            return
        if not user_id:
            return

        member = await self._membership_status(self._paid_group_id, user_id)

        if member is True:
            ok = await self._answer_join_request(chat_id, user_id, approve=True)
            logger.info(
                f"[TG] Scalp-Beitritt FREIGEGEBEN | {first_name} (@{username}) "
                f"id={user_id} | approve_ok={ok}"
            )
        elif member is False:
            await self._answer_join_request(chat_id, user_id, approve=False)
            logger.info(
                f"[TG] Scalp-Beitritt ABGELEHNT (kein Main-Mitglied) | "
                f"{first_name} (@{username}) id={user_id}"
            )
        else:
            # Unbekannt (API-Fehler) — Anfrage offen lassen, Admin informieren
            logger.warning(
                f"[TG] Scalp-Beitritt UNENTSCHIEDEN (getChatMember-Fehler) | "
                f"{first_name} (@{username}) id={user_id} — bleibt offen"
            )
            await self._send_to(
                self._admin_chat_id,
                f"⚠️ <b>Scalp-Beitritt manuell prüfen</b>\n"
                f"{first_name} (@{username}, id {user_id}) — Mitgliedschaft konnte "
                f"nicht geprüft werden. Anfrage steht offen in der Scalp-Gruppe."
            )

    async def _membership_status(self, group_id: str, user_id) -> "bool | None":
        """Ist user_id Mitglied von group_id?  True/False, None bei API-Fehler."""
        if not group_id or not user_id:
            return False
        try:
            session = await self._get_session()
            url = f"{self._base_url}/getChatMember"
            async with session.get(
                url, params={"chat_id": group_id, "user_id": user_id},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
            if not data.get("ok"):
                # "user not found" o.ae. bei Nicht-Mitglied -> als kein Mitglied werten
                desc = str(data.get("description", "")).lower()
                if "not found" in desc or "user_id_invalid" in desc or "participant" in desc:
                    return False
                return None
            status = data.get("result", {}).get("status", "")
            if status in ("creator", "administrator", "member"):
                return True
            if status == "restricted":
                return bool(data.get("result", {}).get("is_member", False))
            # left, kicked
            return False
        except Exception as e:
            logger.warning(f"[TG] getChatMember Fehler (group {group_id}, user {user_id}): {e}")
            return None

    async def _answer_join_request(self, chat_id: str, user_id, approve: bool) -> bool:
        """Beitrittsanfrage freigeben (approve) oder ablehnen (decline)."""
        method = "approveChatJoinRequest" if approve else "declineChatJoinRequest"
        try:
            session = await self._get_session()
            async with session.post(
                f"{self._base_url}/{method}",
                json={"chat_id": chat_id, "user_id": user_id},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status == 200:
                    return True
                body = await resp.text()
                logger.warning(f"[TG] {method} Fehler {resp.status}: {body}")
                return False
        except Exception as e:
            logger.warning(f"[TG] {method} fehlgeschlagen: {e}")
            return False

    async def _handle_command(self, message: dict) -> None:
        """Eingehende Telegram-Nachricht verarbeiten."""
        text = message.get("text", "").strip()
        chat = message.get("chat", {})
        chat_id = str(chat.get("id", ""))
        chat_type = chat.get("type", "")
        user = message.get("from", {})
        username = user.get("username", "")
        first_name = user.get("first_name", "")

        if not chat_id:
            return

        # Kommandos NUR im privaten Chat verarbeiten. In Gruppen/Channels reagiert der
        # Bot auf KEIN Kommando (auch nicht /status, /start, /stop) — dort postet er
        # ausschliesslich Signale. Verhindert, dass jemand in einer Gruppe per /status
        # einen internen Bericht ausloest.
        if chat_type != "private":
            return

        # --- /start oder /start <password> ---
        if text.startswith("/start"):
            parts = text.split(maxsplit=1)
            password = parts[1].strip() if len(parts) > 1 else ""

            # Admin ist immer berechtigt
            if chat_id == self._admin_chat_id:
                self._db.add_telegram_subscriber(chat_id, username, first_name)
                await self._send_to(chat_id,
                    "✅ <b>Du bist registriert</b> (Admin)\n"
                    "Du bekommst alle Bot-Alerts."
                )
                return

            # Team-Passwort pruefen
            if not self._team_password:
                await self._send_to(chat_id,
                    "❌ Self-Service Onboarding ist nicht aktiviert.\n"
                    "Kontaktiere den Admin."
                )
                return

            if not password:
                await self._send_to(chat_id,
                    "🔐 <b>Passwort erforderlich</b>\n\n"
                    "Schreib:\n<code>/start DEIN-PASSWORT</code>"
                )
                return

            if password == self._team_password:
                is_new = self._db.add_telegram_subscriber(chat_id, username, first_name)
                if is_new:
                    await self._send_to(chat_id,
                        f"✅ <b>Willkommen, {first_name}!</b>\n"
                        f"Du bekommst ab jetzt alle Bot-Alerts.\n\n"
                        f"/stop — Alerts abbestellen\n"
                        f"/status — Bot-Status abfragen"
                    )
                    # Admin benachrichtigen
                    if chat_id != self._admin_chat_id:
                        await self._send_to(self._admin_chat_id,
                            f"👤 <b>Neuer Subscriber</b>\n"
                            f"{first_name} (@{username})"
                        )
                else:
                    await self._send_to(chat_id,
                        f"ℹ️ Du bist bereits registriert, {first_name}."
                    )
            else:
                await self._send_to(chat_id, "❌ Falsches Passwort.")

        # --- /stop ---
        elif text.startswith("/stop"):
            removed = self._db.remove_telegram_subscriber(chat_id)
            if removed:
                await self._send_to(chat_id,
                    "👋 <b>Alerts deaktiviert</b>\n"
                    "Du bekommst keine Benachrichtigungen mehr.\n"
                    "Mit /start kannst du dich jederzeit wieder anmelden."
                )
                # Admin benachrichtigen
                if chat_id != self._admin_chat_id:
                    await self._send_to(self._admin_chat_id,
                        f"👤 <b>Subscriber abgemeldet</b>\n"
                        f"{first_name} (@{username})"
                    )
            else:
                await self._send_to(chat_id, "ℹ️ Du warst nicht registriert.")

        # --- /status ---
        elif text.startswith("/status"):
            # NUR Admin + registrierte Team-Subscriber duerfen den internen
            # Statusbericht sehen (enthaelt Master-Positionen, Kundenzahl etc.).
            # Alle anderen (z.B. neugierige Gruppen-Mitglieder per DM oder /status
            # in der Gruppe) bekommen nur eine neutrale Antwort, die nichts verraet.
            if chat_id in self._get_all_chat_ids():
                await self._send_status_report(chat_id)
            else:
                logger.info(f"[TG] /status von Nicht-Berechtigtem abgewiesen (chat {chat_id})")
                await self._send_to(
                    chat_id,
                    "🤖 Dieser Bot verschickt automatische Signale und beantwortet "
                    "keine Anfragen. Fragen zum Copy Trading? → Support-Kontakt in deinem "
                    "Dashboard."
                )

    # --------------------------------------------------------------------------
    # STATUSBERICHT
    # --------------------------------------------------------------------------

    def _format_uptime(self) -> str:
        """Uptime als lesbaren String formatieren."""
        elapsed = int(time.time() - self._start_time)
        days, remainder = divmod(elapsed, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, seconds = divmod(remainder, 60)
        parts = []
        if days > 0:
            parts.append(f"{days}d")
        if hours > 0:
            parts.append(f"{hours}h")
        if minutes > 0:
            parts.append(f"{minutes}m")
        parts.append(f"{seconds}s")
        return " ".join(parts)

    async def _send_status_report(self, chat_id: str) -> None:
        """Detaillierten Statusbericht senden."""
        lines = ["📊 <b>Statusbericht</b>\n"]

        # 1. Bot-Status + Uptime
        lines.append(f"✅ Bot laeuft seit {self._format_uptime()}")
        lines.append(f"🌐 Umgebung: <code>{self._env}</code>")
        lines.append("")

        # 2. Offene Positionen
        if self._parser:
            open_positions = []
            for pos_id, pos in self._parser._positions.items():
                size = float(pos.size) if pos.size else 0.0
                if size > 0:
                    open_positions.append(pos)

            if open_positions:
                lines.append(f"📈 <b>Offene Positionen ({len(open_positions)})</b>")
                for pos in open_positions:
                    emoji = "🟢" if pos.side == "Buy" else "🔴"
                    upnl = pos.unrealisedPnL or "0"
                    lines.append(
                        f"  {emoji} {pos.side} <code>{pos.symbol}</code> | "
                        f"Size: {pos.size} | Entry: {pos.avgEntryPrice} | "
                        f"uPnL: {upnl}"
                    )
            else:
                lines.append("📈 Keine offenen Positionen")
            lines.append("")

        # 3. Kunden
        if self._engine:
            customers = self._engine.get_active_customers()
            lines.append(f"👥 Aktive Kunden: {len(customers)}")

        # 4. Neukunden heute
        if self._db:
            new_today = self._db.count_new_customers_today()
            lines.append(f"🆕 Neukunden heute: {new_today}")

        # 5. Aktive Mappings
        if self._db:
            active_mappings = self._db.count_active_mappings()
            lines.append(f"🔗 Aktive Mappings: {active_mappings}")

        # 6. Subscriber
        if self._db:
            subscribers = self._db.get_active_telegram_subscribers()
            lines.append(f"📡 Alert-Subscriber: {len(subscribers)}")

        await self._send_to(chat_id, "\n".join(lines))

    # --------------------------------------------------------------------------
    # ALERT METHODEN
    # --------------------------------------------------------------------------

    async def bot_started(self, env: str, num_customers: int) -> None:
        """Bot wurde gestartet."""
        await self._send(
            f"🟢 <b>Bot gestartet</b>\n"
            f"Umgebung: <code>{env}</code>\n"
            f"Kunden: {num_customers}"
        )

    async def bot_stopped(self) -> None:
        """Bot wurde gestoppt."""
        await self._send("🔴 <b>Bot gestoppt</b>")

    async def master_trade_opened(self, symbol: str, side: str, entry_price: str,
                                  sl: str = "", tp: str = "") -> None:
        """Master hat einen Trade eroeffnet."""
        direction = "Long" if side == "Buy" else "Short"
        emoji = "🟢" if side == "Buy" else "🔴"

        text = f"{emoji} <b>{direction} {symbol}</b>\n"
        text += f"Entry: <code>{entry_price}</code>"
        if sl:
            text += f"\nSL: <code>{sl}</code>"
        if tp:
            text += f"\nTP: <code>{tp}</code>"

        await self._send(text)

    async def master_trade_closed(self, symbol: str, side: str,
                                  pnl: str = "", pnl_percent: str = "",
                                  close_type: str = "CLOSE") -> None:
        """Master hat einen Trade geschlossen."""
        direction = "Long" if side == "Buy" else "Short"

        text = f"⬜ <b>{direction} {symbol} geschlossen</b>"
        if close_type != "CLOSE":
            text += f" ({close_type})"
        if pnl:
            pnl_float = float(pnl)
            pnl_emoji = "✅" if pnl_float >= 0 else "❌"
            text += f"\n{pnl_emoji} PnL: <code>{pnl} USDT</code>"
        if pnl_percent:
            text += f" (<code>{pnl_percent}%</code>)"

        await self._send(text)

    async def trade_error(self, customer_name: str, symbol: str,
                          action: str, error: str) -> None:
        """Fehler bei Trade-Execution."""
        await self._send(
            f"❌ <b>Fehler</b>\n"
            f"Kunde: {customer_name}\n"
            f"<code>{symbol}</code> | {action}\n"
            f"<code>{error}</code>"
        )

    async def reconciliation_result(self, orphaned: int, missed: int,
                                    details: str = "") -> None:
        """Reconciliation abgeschlossen."""
        if orphaned == 0 and missed == 0:
            await self._send(
                f"🔄 <b>Reconciliation</b>\n"
                f"Alles sauber ✓"
            )
        else:
            text = f"🔄 <b>Reconciliation</b>\n"
            if orphaned > 0:
                text += f"⚠️ {orphaned} verwaiste Position(en) geschlossen\n"
            if missed > 0:
                text += f"⏭️ {missed} verpasste(r) Trade(s) (nicht nachgeholt)\n"
            if details:
                text += f"\n{details}"
            await self._send(text)

    async def ws_reconnect(self, reason: str = "") -> None:
        """WebSocket Reconnect."""
        text = "🔁 <b>WebSocket Reconnect</b>"
        if reason:
            text += f"\nGrund: {reason}"
        await self._send(text)

    async def error(self, message: str) -> None:
        """Allgemeiner Fehler."""
        await self._send(f"⚠️ <b>Fehler</b>\n{message}")

    async def close(self) -> None:
        """Polling stoppen und Session schliessen."""
        if self._polling_task and not self._polling_task.done():
            self._polling_task.cancel()
            try:
                await self._polling_task
            except asyncio.CancelledError:
                pass
        if self._session and not self._session.closed:
            await self._session.close()
