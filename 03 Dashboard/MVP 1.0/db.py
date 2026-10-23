"""
(C) db.py — Datenbank-Zugriff fuer das Dashboard

Verwendet die gleiche SQLite DB wie der Bot.

Konfiguration via Umgebungsvariablen:
  BOT_CORE_PATH  — Pfad zum Bot-Core Ordner (Default: ../01 Bot-Core)
  DB_PATH        — Pfad zur SQLite DB (Default: BOT_CORE_PATH/copy_trading.db)
"""

import os
import sys

BOT_CORE_PATH = os.environ.get(
    "BOT_CORE_PATH",
    os.path.join(os.path.dirname(__file__), "..", "01 Bot-Core"),
)
sys.path.insert(0, BOT_CORE_PATH)

from database import Database

DB_PATH = os.environ.get(
    "DB_PATH",
    os.path.join(BOT_CORE_PATH, "copy_trading.db"),
)

_db: Database | None = None


def _run_dashboard_migrations(db: Database):
    """Dashboard-spezifische DB-Migrationen (Spalten hinzufuegen falls nicht vorhanden)."""
    conn = db._conn
    # Pruefen welche Spalten existieren
    cols = {row[1] for row in conn.execute("PRAGMA table_info(dashboard_users)").fetchall()}

    if "email_verified" not in cols:
        conn.execute("ALTER TABLE dashboard_users ADD COLUMN email_verified INTEGER DEFAULT 0")
    if "verification_token" not in cols:
        conn.execute("ALTER TABLE dashboard_users ADD COLUMN verification_token TEXT")
    if "verification_expires" not in cols:
        conn.execute("ALTER TABLE dashboard_users ADD COLUMN verification_expires TEXT")
    if "reset_token" not in cols:
        conn.execute("ALTER TABLE dashboard_users ADD COLUMN reset_token TEXT")
    if "reset_expires" not in cols:
        conn.execute("ALTER TABLE dashboard_users ADD COLUMN reset_expires TEXT")
    # Consent-Tracking (DSGVO Nachweispflicht)
    if "accepted_agb_at" not in cols:
        conn.execute("ALTER TABLE dashboard_users ADD COLUMN accepted_agb_at TEXT")
    if "accepted_privacy_at" not in cols:
        conn.execute("ALTER TABLE dashboard_users ADD COLUMN accepted_privacy_at TEXT")
    if "accepted_risk_at" not in cols:
        conn.execute("ALTER TABLE dashboard_users ADD COLUMN accepted_risk_at TEXT")
    if "accepted_marketing" not in cols:
        conn.execute("ALTER TABLE dashboard_users ADD COLUMN accepted_marketing INTEGER DEFAULT 0")
    if "accepted_marketing_at" not in cols:
        conn.execute("ALTER TABLE dashboard_users ADD COLUMN accepted_marketing_at TEXT")
    if "product_tier" not in cols:
        conn.execute("ALTER TABLE dashboard_users ADD COLUMN product_tier TEXT DEFAULT 'copy_trading'")
    if "telegram_chat_id" not in cols:
        conn.execute("ALTER TABLE dashboard_users ADD COLUMN telegram_chat_id TEXT")
    if "telegram_username" not in cols:
        conn.execute("ALTER TABLE dashboard_users ADD COLUMN telegram_username TEXT")
    if "telegram_invite_link" not in cols:
        conn.execute("ALTER TABLE dashboard_users ADD COLUMN telegram_invite_link TEXT")
    if "previous_tier" not in cols:
        conn.execute("ALTER TABLE dashboard_users ADD COLUMN previous_tier TEXT")
    if "phone" not in cols:
        conn.execute("ALTER TABLE dashboard_users ADD COLUMN phone TEXT")
    # Ablefy "Zugang gueltig bis" (payer.access.changed / GRANT) — Basis fuer Ablauf-Pruefung (2026-09-11)
    if "access_valid_until" not in cols:
        try:
            conn.execute("ALTER TABLE dashboard_users ADD COLUMN access_valid_until TEXT")
        except Exception:
            pass  # parallel startender Worker war schneller
    # Ablefy Payment-Tracking
    if "payment_status" not in cols:
        conn.execute("ALTER TABLE dashboard_users ADD COLUMN payment_status TEXT DEFAULT 'pending'")
    if "ablefy_order_id" not in cols:
        conn.execute("ALTER TABLE dashboard_users ADD COLUMN ablefy_order_id TEXT")
    if "ablefy_product_id" not in cols:
        conn.execute("ALTER TABLE dashboard_users ADD COLUMN ablefy_product_id TEXT")
    if "paid_amount" not in cols:
        conn.execute("ALTER TABLE dashboard_users ADD COLUMN paid_amount TEXT")
    if "paid_at" not in cols:
        conn.execute("ALTER TABLE dashboard_users ADD COLUMN paid_at TEXT")
    # Marketing Double-Opt-In
    if "marketing_optin_token" not in cols:
        conn.execute("ALTER TABLE dashboard_users ADD COLUMN marketing_optin_token TEXT")
    if "marketing_optin_verified" not in cols:
        conn.execute("ALTER TABLE dashboard_users ADD COLUMN marketing_optin_verified INTEGER DEFAULT 0")
    if "marketing_optin_verified_at" not in cols:
        conn.execute("ALTER TABLE dashboard_users ADD COLUMN marketing_optin_verified_at TEXT")

    # Webhook-Log Tabelle (alle Payloads speichern)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS webhook_logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL,
            payload TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    # Pending Payments (Zahlung vor Registrierung)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS pending_payments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            ablefy_order_id TEXT,
            ablefy_product_id TEXT,
            product_tier TEXT,
            amount TEXT,
            created_at TEXT NOT NULL,
            claimed_at TEXT
        )
    """)

    # BLOCKLIST — dauerhaft gesperrte E-Mails (kein Re-Signup / Re-Onboarding moeglich)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS blocklist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            telegram_user_id TEXT,
            reason TEXT,
            created_at TEXT NOT NULL
        )
    """)

    # pending_payments: Name-Spalten hinzufuegen (fuer Payment-First Flow)
    pp_cols = {row[1] for row in conn.execute("PRAGMA table_info(pending_payments)").fetchall()}
    if "first_name" not in pp_cols:
        conn.execute("ALTER TABLE pending_payments ADD COLUMN first_name TEXT")
    if "last_name" not in pp_cols:
        conn.execute("ALTER TABLE pending_payments ADD COLUMN last_name TEXT")

    conn.commit()


def is_email_blocked(db, email: str) -> bool:
    """BLOCKLIST: True, wenn diese E-Mail dauerhaft gesperrt ist."""
    if not email:
        return False
    try:
        row = db._conn.execute(
            "SELECT 1 FROM blocklist WHERE email = ?", (email.strip().lower(),)
        ).fetchone()
        return row is not None
    except Exception:
        return False


def get_db() -> Database:
    """Singleton DB-Instanz fuer das Dashboard."""
    global _db
    if _db is None:
        _db = Database(db_path=DB_PATH)
        _db.connect()
        _run_dashboard_migrations(_db)
    return _db
