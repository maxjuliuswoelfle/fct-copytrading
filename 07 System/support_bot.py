"""
(C) FCT Copy Trading — Telegram Support Relay Bot

Kunden schreiben dem Bot privat → Nachricht wird in die Support-Gruppe weitergeleitet.
Support antwortet per Reply in der Gruppe → Bot schickt es zurück an den Kunden.

Umgebungsvariablen:
  SUPPORT_BOT_TOKEN   — Telegram Bot Token (@BotFather)
  SUPPORT_GROUP_ID    — Telegram Gruppen-ID (z.B. -5109929023)
"""

import os
import re
import logging
import asyncio
import sqlite3
from datetime import datetime, timezone
from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("support_bot")

TOKEN = os.environ["SUPPORT_BOT_TOKEN"]
GROUP_ID = int(os.environ["SUPPORT_GROUP_ID"])

# In-memory mapping: group message_id → customer chat_id
# so we know where to relay replies
_customer_map: dict[int, int] = {}

# --------------------------------------------------------------------------
# Mitschreiben: jede Kundennachricht + jede Support-Antwort landen in einer
# EIGENEN SQLite-Datei neben dem Bot. Bewusst NICHT in copy_trading.db --
# die bedient Trading-Bot + Dashboard, dort hat ein Support-Log nichts zu
# suchen (Locking-Risiko an einer Stelle, wo echtes Geld laeuft).
# Verknuepfung beider Welten spaeter ueber telegram_user_id.
#
# Zweck: Trainingsmaterial fuer den AI-Support-Agent (Tonfall + Faelle).
# Grundsatz: Ein Fehler beim Loggen darf den Support NIEMALS blockieren.
# --------------------------------------------------------------------------
LOG_DB = os.environ.get("SUPPORT_LOG_DB", "support_log.db")


def _init_log_db() -> None:
    """Tabelle anlegen, falls noch nicht vorhanden."""
    try:
        con = sqlite3.connect(LOG_DB, timeout=5)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("""
            CREATE TABLE IF NOT EXISTS support_messages (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                ts               TEXT    NOT NULL,
                direction        TEXT    NOT NULL,
                telegram_user_id INTEGER,
                display_name     TEXT,
                username         TEXT,
                group_message_id INTEGER,
                content_type     TEXT,
                text             TEXT,
                responder_id     INTEGER,
                responder_name   TEXT
            )
        """)
        con.execute("CREATE INDEX IF NOT EXISTS idx_sm_user "
                    "ON support_messages(telegram_user_id, ts)")
        con.execute("CREATE INDEX IF NOT EXISTS idx_sm_gmid "
                    "ON support_messages(group_message_id)")
        con.commit()
        con.close()
        log.info(f"[LOG-DB] bereit: {LOG_DB}")
    except Exception as e:
        log.error(f"[LOG-DB] Init fehlgeschlagen: {e}")


def _log_message(direction, telegram_user_id=None, display_name=None,
                 username=None, group_message_id=None, content_type=None,
                 text=None, responder_id=None, responder_name=None) -> None:
    """Eine Zeile wegschreiben. Schluckt jeden Fehler bewusst."""
    try:
        con = sqlite3.connect(LOG_DB, timeout=5)
        con.execute("PRAGMA busy_timeout=5000")
        con.execute(
            "INSERT INTO support_messages (ts, direction, telegram_user_id, "
            "display_name, username, group_message_id, content_type, text, "
            "responder_id, responder_name) VALUES (?,?,?,?,?,?,?,?,?,?)",
            (datetime.now(timezone.utc).isoformat(timespec="seconds"),
             direction, telegram_user_id, display_name, username,
             group_message_id, content_type, text, responder_id,
             responder_name),
        )
        con.commit()
        con.close()
    except Exception as e:
        log.error(f"[LOG-DB] Schreiben fehlgeschlagen ({direction}): {e}")


def _content_type(msg) -> str:
    for attr in ("text", "photo", "document", "video", "voice", "sticker"):
        if getattr(msg, attr, None):
            return attr
    return "other"


WELCOME = (
    "Willkommen beim FirstClassTrading Support 👋\n\n"
    "Schreib uns einfach deine Frage — unser Team antwortet "
    "in der Regel innerhalb von 30 Minuten.\n\n"
    "Erreichbarkeit: Mo–Fr, 9–21 Uhr"
)


async def cmd_start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Handle /start — send welcome message."""
    await update.message.reply_text(WELCOME)


async def customer_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Customer writes to bot privately → forward to support group."""
    msg = update.message
    if not msg:
        return

    user = msg.from_user
    name = user.full_name or user.username or str(user.id)
    username = f" (@{user.username})" if user.username else ""

    header = f"💬 <b>{name}</b>{username}  [ID: {user.id}]"

    # Forward based on content type
    if msg.text:
        sent = await ctx.bot.send_message(
            chat_id=GROUP_ID,
            text=f"{header}\n\n{msg.text}",
            parse_mode="HTML",
        )
    elif msg.photo:
        sent = await ctx.bot.send_photo(
            chat_id=GROUP_ID,
            photo=msg.photo[-1].file_id,
            caption=f"{header}\n\n{msg.caption or ''}",
            parse_mode="HTML",
        )
    elif msg.document:
        sent = await ctx.bot.send_document(
            chat_id=GROUP_ID,
            document=msg.document.file_id,
            caption=f"{header}\n\n{msg.caption or ''}",
            parse_mode="HTML",
        )
    elif msg.video:
        sent = await ctx.bot.send_video(
            chat_id=GROUP_ID,
            video=msg.video.file_id,
            caption=f"{header}\n\n{msg.caption or ''}",
            parse_mode="HTML",
        )
    elif msg.voice:
        sent = await ctx.bot.send_voice(
            chat_id=GROUP_ID,
            voice=msg.voice.file_id,
            caption=header,
            parse_mode="HTML",
        )
    elif msg.sticker:
        # Send header first, then sticker
        await ctx.bot.send_message(
            chat_id=GROUP_ID, text=header, parse_mode="HTML"
        )
        sent = await ctx.bot.send_sticker(
            chat_id=GROUP_ID, sticker=msg.sticker.file_id
        )
    else:
        sent = await ctx.bot.send_message(
            chat_id=GROUP_ID,
            text=f"{header}\n\n[Nicht unterstützter Nachrichtentyp]",
            parse_mode="HTML",
        )

    # Map the forwarded message to the customer's chat
    _customer_map[sent.message_id] = msg.chat.id
    log.info(f"Customer {name} ({user.id}) → Group msg {sent.message_id}")

    _log_message(
        direction="in",
        telegram_user_id=user.id,
        display_name=name,
        username=user.username,
        group_message_id=sent.message_id,
        content_type=_content_type(msg),
        text=msg.text or msg.caption,
    )


async def group_reply(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """Support replies in group (via Reply) → send back to customer."""
    msg = update.message
    if not msg or not msg.reply_to_message:
        return

    replied_id = msg.reply_to_message.message_id
    customer_chat_id = _customer_map.get(replied_id)

    if not customer_chat_id:
        # Maybe replying to a sticker/header — check the message before
        prev_id = replied_id - 1
        customer_chat_id = _customer_map.get(prev_id)

    if not customer_chat_id:
        # Fallback: Kunden-ID direkt aus dem [ID: NNN]-Header der beantworteten
        # Nachricht lesen. Ueberlebt Bot-Neustarts (die in-memory _customer_map ist
        # dann leer). Bei Privat-Chats gilt chat_id == user_id.
        _src = (msg.reply_to_message.text or msg.reply_to_message.caption or "")
        _m = re.search(r"\[ID:\s*(\d+)\]", _src)
        if _m:
            customer_chat_id = int(_m.group(1))
            log.info(f"Kunde ueber [ID]-Header aufgeloest: {customer_chat_id}")

    if not customer_chat_id:
        await msg.reply_text("⚠️ Konnte den Kunden nicht zuordnen. Nachricht wurde nicht weitergeleitet.")
        return

    try:
        if msg.text:
            await ctx.bot.send_message(chat_id=customer_chat_id, text=msg.text)
        elif msg.photo:
            await ctx.bot.send_photo(
                chat_id=customer_chat_id,
                photo=msg.photo[-1].file_id,
                caption=msg.caption or "",
            )
        elif msg.document:
            await ctx.bot.send_document(
                chat_id=customer_chat_id,
                document=msg.document.file_id,
                caption=msg.caption or "",
            )
        elif msg.video:
            await ctx.bot.send_video(
                chat_id=customer_chat_id,
                video=msg.video.file_id,
                caption=msg.caption or "",
            )
        elif msg.voice:
            await ctx.bot.send_voice(
                chat_id=customer_chat_id, voice=msg.voice.file_id
            )
        elif msg.sticker:
            await ctx.bot.send_sticker(
                chat_id=customer_chat_id, sticker=msg.sticker.file_id
            )
        else:
            await msg.reply_text("⚠️ Nachrichtentyp wird nicht unterstützt.")
            return

        await msg.set_reaction("👍")
        log.info(f"Reply sent to customer {customer_chat_id}")

        _responder = msg.from_user
        _log_message(
            direction="out",
            telegram_user_id=customer_chat_id,
            group_message_id=replied_id,
            content_type=_content_type(msg),
            text=msg.text or msg.caption,
            responder_id=_responder.id if _responder else None,
            responder_name=(_responder.full_name or _responder.username)
            if _responder else None,
        )

    except Exception as e:
        log.error(f"Failed to relay to {customer_chat_id}: {e}")
        await msg.reply_text(f"⚠️ Fehler beim Senden: {e}")


def main():
    app = ApplicationBuilder().token(TOKEN).build()

    # /start command — only in private chats
    app.add_handler(CommandHandler("start", cmd_start, filters=filters.ChatType.PRIVATE))

    # Customer messages (private chat, not commands)
    app.add_handler(MessageHandler(
        filters.ChatType.PRIVATE & ~filters.COMMAND,
        customer_message,
    ))

    # Support replies in the group (must be a reply to a forwarded message)
    app.add_handler(MessageHandler(
        filters.Chat(GROUP_ID) & filters.REPLY & ~filters.COMMAND,
        group_reply,
    ))

    _init_log_db()
    log.info("Support bot started")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
