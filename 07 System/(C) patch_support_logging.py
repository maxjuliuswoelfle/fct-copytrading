"""(C) Patch: Support-Bot schreibt jede Nachricht mit.

Anker-basiert, mit Treffer-Asserts. Legt Backup an. Schreibt in eine EIGENE
SQLite-DB (support_log.db) neben dem Bot -- NICHT in copy_trading.db.

Aufruf auf dem Server:  cd /opt/support-bot && python3 patch_support_logging.py
"""
import re
import shutil
import datetime

SRC = "support_bot.py"
BACKUP = f"support_bot.py.bak_logging_{datetime.datetime.now():%Y%m%d_%H%M%S}"

with open(SRC, encoding="utf-8") as f:
    code = f.read()

if "support_messages" in code:
    raise SystemExit("ABBRUCH: Patch scheint schon drin zu sein.")

# ---------------------------------------------------------------- Anker 1
A1 = '''import os
import re
import logging
import asyncio
'''

A1_NEW = '''import os
import re
import logging
import asyncio
import sqlite3
from datetime import datetime, timezone
'''

# ---------------------------------------------------------------- Anker 2
A2 = '''# In-memory mapping: group message_id → customer chat_id
# so we know where to relay replies
_customer_map: dict[int, int] = {}
'''

A2_NEW = '''# In-memory mapping: group message_id → customer chat_id
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
'''

# ---------------------------------------------------------------- Anker 3
A3 = '''    # Map the forwarded message to the customer's chat
    _customer_map[sent.message_id] = msg.chat.id
    log.info(f"Customer {name} ({user.id}) → Group msg {sent.message_id}")'''

A3_NEW = '''    # Map the forwarded message to the customer's chat
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
    )'''

# ---------------------------------------------------------------- Anker 4
A4 = '''        await msg.set_reaction("\U0001f44d")
        log.info(f"Reply sent to customer {customer_chat_id}")'''

A4_NEW = '''        await msg.set_reaction("\U0001f44d")
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
        )'''

# ---------------------------------------------------------------- Anker 5
A5 = '''    log.info("Support bot started")'''

A5_NEW = '''    _init_log_db()
    log.info("Support bot started")'''

for label, anchor, repl in (
    ("Imports", A1, A1_NEW),
    ("DB-Helper", A2, A2_NEW),
    ("Kundennachricht", A3, A3_NEW),
    ("Support-Antwort", A4, A4_NEW),
    ("Init beim Start", A5, A5_NEW),
):
    n = code.count(anchor)
    if n != 1:
        raise SystemExit(f"ABBRUCH: Anker '{label}' {n}x gefunden, erwartet 1")
    code = code.replace(anchor, repl)
    print(f"OK  Anker '{label}' ersetzt")

shutil.copy2(SRC, BACKUP)
print(f"Backup: {BACKUP}")

with open(SRC, "w", encoding="utf-8") as f:
    f.write(code)

print("PATCH GESCHRIEBEN")
