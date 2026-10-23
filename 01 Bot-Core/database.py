"""
(C) database.py — SQLite-Datenbank fuer den Copy Trading Bot

Persistiert Position-Mappings (Master -> Kunde), damit nach einem Restart
alle Zuordnungen erhalten bleiben und Trade-Management weiter funktioniert.

Schema:
- position_mappings: Master-Position <-> Kunden-Position Zuordnung
- customers: Kunden-Stammdaten
- trade_history: Kopierte Trades pro Kunde (fuer Dashboard)
- master_trade_history: Alle Master-Trades (Bot-Performance)
- dashboard_users: Login-Daten fuer das Kunden-Dashboard
- telegram_subscribers: Telegram Alert Empfaenger

SQLite ist die Endloesung — reicht locker fuer 500+ Kunden.
"""

import sqlite3
import os
from dataclasses import dataclass
from typing import Any

from logger_setup import logger


# ============================================================================
# DATABASE
# ============================================================================

DB_PATH = os.path.join(os.path.dirname(__file__), "copy_trading.db")


class Database:
    """SQLite-Datenbank fuer persistente Daten."""

    def __init__(self, db_path: str = DB_PATH) -> None:
        self._db_path = db_path
        self._conn: sqlite3.Connection | None = None

    # --------------------------------------------------------------------------
    # LIFECYCLE
    # --------------------------------------------------------------------------

    def connect(self) -> None:
        """Verbindung herstellen und Schema erstellen."""
        self._conn = sqlite3.connect(self._db_path)
        self._conn.row_factory = sqlite3.Row
        # WAL-Modus fuer bessere Performance bei gleichzeitigem Lesen/Schreiben
        self._conn.execute("PRAGMA journal_mode=WAL")
        # Bei gleichzeitigen Schreibzugriffen (mehrere Dashboard-Worker + Bot) bis zu
        # 5s warten statt sofort "database is locked" zu werfen — kritisch unter Last.
        self._conn.execute("PRAGMA busy_timeout=5000")
        self._create_tables()
        logger.info(f"[DB] Verbunden: {self._db_path}")

    def close(self) -> None:
        """Verbindung schliessen."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def _create_tables(self) -> None:
        """Tabellen erstellen falls sie nicht existieren."""
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS position_mappings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                master_position_id TEXT NOT NULL,
                customer_id TEXT NOT NULL,
                customer_position_id TEXT NOT NULL,
                customer_order_id TEXT,
                symbol TEXT NOT NULL,
                side TEXT,
                customer_qty REAL DEFAULT 0,
                customer_entry_price REAL DEFAULT 0,
                leverage REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                closed_at TIMESTAMP,
                is_active INTEGER DEFAULT 1,
                UNIQUE(master_position_id, customer_id)
            );

            CREATE INDEX IF NOT EXISTS idx_mappings_active
                ON position_mappings(is_active)
                WHERE is_active = 1;

            CREATE INDEX IF NOT EXISTS idx_mappings_master_pos
                ON position_mappings(master_position_id)
                WHERE is_active = 1;

            CREATE INDEX IF NOT EXISTS idx_mappings_customer
                ON position_mappings(customer_id)
                WHERE is_active = 1;

            CREATE TABLE IF NOT EXISTS telegram_subscribers (
                chat_id TEXT PRIMARY KEY,
                username TEXT DEFAULT '',
                first_name TEXT DEFAULT '',
                subscribed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                is_active INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS trade_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id TEXT NOT NULL,
                master_position_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                action TEXT NOT NULL,
                qty REAL NOT NULL,
                price REAL DEFAULT 0,
                pnl REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_history_customer
                ON trade_history(customer_id);

            CREATE INDEX IF NOT EXISTS idx_history_customer_time
                ON trade_history(customer_id, created_at DESC);

            CREATE TABLE IF NOT EXISTS master_trade_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                position_id TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                action TEXT NOT NULL,
                qty REAL NOT NULL,
                price REAL DEFAULT 0,
                pnl REAL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_master_history_time
                ON master_trade_history(created_at DESC);

            CREATE TABLE IF NOT EXISTS dashboard_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id TEXT NOT NULL,
                email TEXT,
                invite_token TEXT UNIQUE,
                password_hash TEXT,
                session_token TEXT,
                session_expires_at TIMESTAMP,
                is_activated INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS bot_state (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS signal_display_names (
                position_id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                symbol TEXT NOT NULL,
                side TEXT NOT NULL,
                number INTEGER NOT NULL,
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS signal_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                position_id TEXT NOT NULL,
                signal_type TEXT NOT NULL,
                message_text TEXT,
                sent_to_paid INTEGER DEFAULT 0,
                sent_to_free INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_signal_log_position
                ON signal_log(position_id);

            CREATE INDEX IF NOT EXISTS idx_signal_log_time
                ON signal_log(created_at DESC);

            CREATE TABLE IF NOT EXISTS customers (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                uid TEXT NOT NULL,
                api_key TEXT NOT NULL,
                api_secret TEXT NOT NULL,
                read_api_key TEXT DEFAULT '',
                read_api_secret TEXT DEFAULT '',
                is_active INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                deactivated_at TIMESTAMP
            );
        """)
        self._conn.commit()

        # Migrationen — neue Spalten zu bestehenden Tabellen
        migrations = [
            ("dashboard_users", "email", "TEXT"),
            ("position_mappings", "customer_qty", "REAL DEFAULT 0"),
            ("position_mappings", "customer_entry_price", "REAL DEFAULT 0"),
            ("position_mappings", "leverage", "REAL DEFAULT 0"),
            ("position_mappings", "stop_loss", "REAL DEFAULT 0"),
            ("position_mappings", "take_profit", "REAL DEFAULT 0"),
            ("trade_history", "initial_risk", "REAL DEFAULT 0"),
            ("trade_history", "execution_latency_ms", "INTEGER DEFAULT 0"),
            ("position_mappings", "last_mark_price", "REAL DEFAULT 0"),
            ("customers", "last_known_balance", "REAL DEFAULT 0"),
            ("customers", "balance_updated_at", "TIMESTAMP"),
            ("customers", "first_name", "TEXT DEFAULT ''"),
            ("customers", "last_name", "TEXT DEFAULT ''"),
            ("customers", "onboarding_status", "TEXT DEFAULT 'active'"),
            ("customers", "onboarding_step", "INTEGER DEFAULT 0"),
            ("customers", "paid_at", "TIMESTAMP"),
            ("customers", "setup_completed_at", "TIMESTAMP"),
            ("dashboard_users", "product_tier", "TEXT DEFAULT 'copy_trading'"),
            ("dashboard_users", "email_verified", "INTEGER DEFAULT 0"),
            ("dashboard_users", "email_verify_token", "TEXT"),
            ("dashboard_users", "reset_token", "TEXT"),
            ("dashboard_users", "reset_token_expires", "TIMESTAMP"),
            ("dashboard_users", "accept_marketing", "INTEGER DEFAULT 0"),
            ("dashboard_users", "telegram_chat_id", "TEXT"),
            ("dashboard_users", "telegram_username", "TEXT"),
            ("signal_display_names", "entry_price", "REAL DEFAULT 0"),
            ("signal_display_names", "open_timestamp", "REAL DEFAULT 0"),
            ("signal_display_names", "is_scalp", "INTEGER DEFAULT 0"),
        ]
        for table, column, col_type in migrations:
            try:
                self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
                self._conn.commit()
                logger.info(f"[DB] Migration: {column} zu {table} hinzugefuegt")
            except Exception:
                pass  # Spalte existiert bereits

    # --------------------------------------------------------------------------
    # POSITION MAPPINGS — CRUD
    # --------------------------------------------------------------------------

    def save_mapping(
        self,
        master_position_id: str,
        customer_id: str,
        customer_position_id: str,
        customer_order_id: str,
        symbol: str,
        side: str = "",
        customer_qty: float = 0,
        customer_entry_price: float = 0,
        leverage: float = 0,
        stop_loss: float = 0,
        take_profit: float = 0,
    ) -> None:
        """
        Neues Position-Mapping speichern.
        Bei Duplikat (gleiche master_position_id + customer_id) wird aktualisiert.
        """
        self._conn.execute("""
            INSERT INTO position_mappings
                (master_position_id, customer_id, customer_position_id,
                 customer_order_id, symbol, side, customer_qty,
                 customer_entry_price, leverage, stop_loss, take_profit, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(master_position_id, customer_id) DO UPDATE SET
                customer_position_id = excluded.customer_position_id,
                customer_order_id = excluded.customer_order_id,
                customer_qty = excluded.customer_qty,
                customer_entry_price = excluded.customer_entry_price,
                leverage = excluded.leverage,
                stop_loss = excluded.stop_loss,
                take_profit = excluded.take_profit,
                is_active = 1,
                closed_at = NULL
        """, (master_position_id, customer_id, customer_position_id,
              customer_order_id, symbol, side, customer_qty,
              customer_entry_price, leverage, stop_loss, take_profit))
        self._conn.commit()
        logger.info(
            f"[DB] Mapping gespeichert: Master {master_position_id[:8]}... -> "
            f"Kunde {customer_id} ({symbol} | Qty: {customer_qty} | Entry: {customer_entry_price})"
        )

    def update_mapping_sl_tp(
        self,
        master_position_id: str,
        customer_id: str,
        stop_loss: float = 0,
        take_profit: float = 0,
    ) -> None:
        """SL/TP auf einem aktiven Mapping aktualisieren."""
        self._conn.execute("""
            UPDATE position_mappings
            SET stop_loss = ?, take_profit = ?
            WHERE master_position_id = ? AND customer_id = ? AND is_active = 1
        """, (stop_loss, take_profit, master_position_id, customer_id))
        self._conn.commit()

    def update_mark_prices(self, prices: dict[str, float]) -> None:
        """Mark-Preise fuer alle aktiven Mappings aktualisieren (Symbol -> Preis)."""
        for symbol, price in prices.items():
            self._conn.execute("""
                UPDATE position_mappings
                SET last_mark_price = ?
                WHERE symbol = ? AND is_active = 1
            """, (price, symbol))
        self._conn.commit()

    def update_mapping_position(
        self,
        master_position_id: str,
        customer_id: str,
        customer_qty: float,
        customer_entry_price: float,
    ) -> None:
        """Mapping aktualisieren (nach Scale-In oder Scale-Out)."""
        self._conn.execute("""
            UPDATE position_mappings
            SET customer_qty = ?, customer_entry_price = ?
            WHERE master_position_id = ? AND customer_id = ? AND is_active = 1
        """, (customer_qty, customer_entry_price, master_position_id, customer_id))
        self._conn.commit()

    def close_mapping(self, master_position_id: str, customer_id: str) -> None:
        """Mapping als geschlossen markieren (Position wurde geclosed)."""
        self._conn.execute("""
            UPDATE position_mappings
            SET is_active = 0, closed_at = CURRENT_TIMESTAMP
            WHERE master_position_id = ? AND customer_id = ? AND is_active = 1
        """, (master_position_id, customer_id))
        self._conn.commit()
        logger.debug(
            f"[DB] Mapping geschlossen: Master {master_position_id[:8]}... -> "
            f"Kunde {customer_id}"
        )

    def get_mapping(
        self, master_position_id: str, customer_id: str
    ) -> dict[str, Any] | None:
        """Ein spezifisches aktives Mapping finden."""
        row = self._conn.execute("""
            SELECT * FROM position_mappings
            WHERE master_position_id = ? AND customer_id = ? AND is_active = 1
        """, (master_position_id, customer_id)).fetchone()
        return dict(row) if row else None

    def get_mappings_for_master(self, master_position_id: str) -> list[dict[str, Any]]:
        """Alle aktiven Mappings fuer eine Master-Position."""
        rows = self._conn.execute("""
            SELECT * FROM position_mappings
            WHERE master_position_id = ? AND is_active = 1
        """, (master_position_id,)).fetchall()
        return [dict(r) for r in rows]

    def get_mappings_for_customer(self, customer_id: str) -> list[dict[str, Any]]:
        """Alle aktiven Mappings fuer einen Kunden."""
        rows = self._conn.execute("""
            SELECT * FROM position_mappings
            WHERE customer_id = ? AND is_active = 1
        """, (customer_id,)).fetchall()
        return [dict(r) for r in rows]

    def get_all_active_mappings(self) -> list[dict[str, Any]]:
        """Alle aktiven Mappings laden (fuer Bot-Start)."""
        rows = self._conn.execute("""
            SELECT * FROM position_mappings
            WHERE is_active = 1
            ORDER BY created_at
        """).fetchall()
        return [dict(r) for r in rows]

    def find_mapping_by_symbol(
        self, symbol: str, customer_id: str
    ) -> list[dict[str, Any]]:
        """Alle aktiven Mappings fuer ein Symbol + Kunde finden."""
        rows = self._conn.execute("""
            SELECT * FROM position_mappings
            WHERE symbol = ? AND customer_id = ? AND is_active = 1
        """, (symbol, customer_id)).fetchall()
        return [dict(r) for r in rows]

    # --------------------------------------------------------------------------
    # CUSTOMERS — CRUD
    # --------------------------------------------------------------------------

    def add_customer(
        self,
        customer_id: str,
        name: str,
        uid: str,
        api_key: str,
        api_secret: str,
        read_api_key: str = "",
        read_api_secret: str = "",
    ) -> None:
        """Neuen Kunden hinzufuegen oder reaktivieren."""
        self._conn.execute("""
            INSERT INTO customers
                (id, name, uid, api_key, api_secret, read_api_key, read_api_secret, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, 1)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                uid = excluded.uid,
                api_key = excluded.api_key,
                api_secret = excluded.api_secret,
                read_api_key = excluded.read_api_key,
                read_api_secret = excluded.read_api_secret,
                is_active = 1,
                deactivated_at = NULL
        """, (customer_id, name, uid, api_key, api_secret, read_api_key, read_api_secret))
        self._conn.commit()
        logger.info(f"[DB] Kunde hinzugefuegt: {name} (ID: {customer_id})")

    def deactivate_customer(self, customer_id: str) -> bool:
        """Kunden deaktivieren (nicht loeschen — Mapping-Historie bleibt erhalten)."""
        cursor = self._conn.execute("""
            UPDATE customers
            SET is_active = 0, deactivated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND is_active = 1
        """, (customer_id,))
        self._conn.commit()
        if cursor.rowcount > 0:
            logger.info(f"[DB] Kunde deaktiviert: {customer_id}")
            return True
        return False

    def get_active_customers(self) -> list[dict[str, Any]]:
        """Alle aktiven Kunden laden."""
        rows = self._conn.execute("""
            SELECT * FROM customers WHERE is_active = 1 ORDER BY created_at
        """).fetchall()
        return [dict(r) for r in rows]

    def get_all_customers(self) -> list[dict[str, Any]]:
        """Alle Kunden laden (inkl. deaktivierte)."""
        rows = self._conn.execute("""
            SELECT * FROM customers ORDER BY created_at
        """).fetchall()
        return [dict(r) for r in rows]

    def get_customer(self, customer_id: str) -> dict[str, Any] | None:
        """Einen Kunden laden."""
        row = self._conn.execute("""
            SELECT * FROM customers WHERE id = ?
        """, (customer_id,)).fetchone()
        return dict(row) if row else None

    def update_customer_balance(self, customer_id: str, balance: float) -> None:
        """Kunden-Balance in DB persistieren (vom WebSocket-Tracking)."""
        self._conn.execute("""
            UPDATE customers
            SET last_known_balance = ?, balance_updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (balance, customer_id))
        self._conn.commit()

    # --------------------------------------------------------------------------
    # TELEGRAM SUBSCRIBERS — CRUD
    # --------------------------------------------------------------------------

    def add_telegram_subscriber(self, chat_id: str, username: str = "", first_name: str = "") -> bool:
        """Telegram Subscriber hinzufuegen oder reaktivieren. Gibt True zurueck wenn neu."""
        existing = self._conn.execute(
            "SELECT is_active FROM telegram_subscribers WHERE chat_id = ?", (chat_id,)
        ).fetchone()

        self._conn.execute("""
            INSERT INTO telegram_subscribers (chat_id, username, first_name, is_active)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(chat_id) DO UPDATE SET
                username = excluded.username,
                first_name = excluded.first_name,
                is_active = 1
        """, (chat_id, username, first_name))
        self._conn.commit()

        is_new = existing is None or existing["is_active"] == 0
        if is_new:
            logger.info(f"[DB] Telegram Subscriber hinzugefuegt: {first_name} (@{username}, {chat_id})")
        return is_new

    def remove_telegram_subscriber(self, chat_id: str) -> bool:
        """Telegram Subscriber deaktivieren."""
        cursor = self._conn.execute("""
            UPDATE telegram_subscribers SET is_active = 0
            WHERE chat_id = ? AND is_active = 1
        """, (chat_id,))
        self._conn.commit()
        if cursor.rowcount > 0:
            logger.info(f"[DB] Telegram Subscriber entfernt: {chat_id}")
            return True
        return False

    def get_active_telegram_subscribers(self) -> list[str]:
        """Alle aktiven Telegram Chat IDs zurueckgeben."""
        rows = self._conn.execute(
            "SELECT chat_id FROM telegram_subscribers WHERE is_active = 1"
        ).fetchall()
        return [row["chat_id"] for row in rows]

    # --------------------------------------------------------------------------
    # TRADE HISTORY — Kunden-Trades (fuer Dashboard)
    # --------------------------------------------------------------------------

    def save_trade_history(
        self,
        customer_id: str,
        master_position_id: str,
        symbol: str,
        side: str,
        action: str,
        qty: float,
        price: float = 0,
        pnl: float = 0,
        initial_risk: float = 0,
        execution_latency_ms: int = 0,
    ) -> None:
        """Trade in Kunden-Historie speichern."""
        self._conn.execute("""
            INSERT INTO trade_history
                (customer_id, master_position_id, symbol, side, action, qty, price, pnl,
                 initial_risk, execution_latency_ms)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (customer_id, master_position_id, symbol, side, action, qty, price, pnl,
              initial_risk, execution_latency_ms))
        self._conn.commit()

    def get_trade_history(self, customer_id: str, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        """Trade-Historie fuer einen Kunden laden."""
        rows = self._conn.execute("""
            SELECT * FROM trade_history
            WHERE customer_id = ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """, (customer_id, limit, offset)).fetchall()
        return [dict(r) for r in rows]

    def get_customer_pnl(self, customer_id: str) -> dict[str, Any]:
        """Gesamt-PnL und Stats fuer einen Kunden berechnen.
        1 Trade = 1 unique master_position_id (Open+Close+Scale = 1 Trade)."""
        row = self._conn.execute("""
            SELECT
                COALESCE(SUM(total_pnl), 0) as total_pnl,
                COUNT(*) as total_trades,
                COUNT(CASE WHEN total_pnl > 0 AND is_closed = 1 THEN 1 END) as wins,
                COUNT(CASE WHEN total_pnl < 0 AND is_closed = 1 THEN 1 END) as losses,
                COUNT(CASE WHEN total_pnl = 0 AND is_closed = 1 THEN 1 END) as breakeven
            FROM (
                SELECT
                    master_position_id,
                    SUM(pnl) as total_pnl,
                    MAX(CASE WHEN action = 'CLOSE' THEN 1 ELSE 0 END) as is_closed
                FROM trade_history
                WHERE customer_id = ?
                GROUP BY master_position_id
            )
        """, (customer_id,)).fetchone()
        return dict(row) if row else {"total_pnl": 0, "total_trades": 0, "wins": 0, "losses": 0, "breakeven": 0}

    def get_closed_trades(self, customer_id: str, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        """Geschlossene Trades fuer einen Kunden (1 Zeile pro Trade).
        Nur komplett geschlossene Trades (mit CLOSE-Aktion).
        Berechnet R-Multiple aus initial_risk (gespeichert beim OPEN)."""
        rows = self._conn.execute("""
            SELECT
                th.master_position_id,
                th.symbol,
                th.side,
                SUM(CASE WHEN th.action IN ('OPEN', 'SCALE_IN') THEN th.qty ELSE 0 END) as total_qty,
                SUM(CASE WHEN th.action IN ('OPEN', 'SCALE_IN') THEN th.qty * th.price ELSE 0 END)
                    / NULLIF(SUM(CASE WHEN th.action IN ('OPEN', 'SCALE_IN') THEN th.qty ELSE 0 END), 0) as avg_entry,
                SUM(th.pnl) as pnl,
                MIN(th.created_at) as opened_at,
                MAX(th.created_at) as closed_at,
                MAX(CASE WHEN th.action = 'OPEN' THEN th.initial_risk ELSE 0 END) as initial_risk,
                COALESCE(pm.leverage, 0) as leverage
            FROM trade_history th
            LEFT JOIN position_mappings pm
                ON pm.master_position_id = th.master_position_id
                AND pm.customer_id = th.customer_id
            WHERE th.customer_id = ?
            AND th.master_position_id IN (
                SELECT DISTINCT master_position_id FROM trade_history
                WHERE customer_id = ? AND action = 'CLOSE'
            )
            GROUP BY th.master_position_id
            ORDER BY MAX(th.created_at) DESC
            LIMIT ? OFFSET ?
        """, (customer_id, customer_id, limit, offset)).fetchall()
        results = []
        for r in rows:
            d = dict(r)
            ir = d.get("initial_risk", 0) or 0
            pnl = d.get("pnl", 0) or 0
            d["r_multiple"] = round(pnl / ir, 2) if ir > 0 else None
            results.append(d)
        return results

    # --------------------------------------------------------------------------
    # MASTER TRADE HISTORY — Bot-Performance (global)
    # --------------------------------------------------------------------------

    def save_master_trade(
        self,
        position_id: str,
        symbol: str,
        side: str,
        action: str,
        qty: float,
        price: float = 0,
        pnl: float = 0,
    ) -> None:
        """Master-Trade in Historie speichern."""
        self._conn.execute("""
            INSERT INTO master_trade_history
                (position_id, symbol, side, action, qty, price, pnl)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (position_id, symbol, side, action, qty, price, pnl))
        self._conn.commit()

    def get_master_trade_history(self, limit: int = 50, offset: int = 0) -> list[dict[str, Any]]:
        """Master-Trade-Historie laden."""
        rows = self._conn.execute("""
            SELECT * FROM master_trade_history
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """, (limit, offset)).fetchall()
        return [dict(r) for r in rows]

    def get_bot_performance(self) -> dict[str, Any]:
        """Gesamt-Performance des Bots (alle Master-Trades).
        1 Trade = 1 unique position_id."""
        row = self._conn.execute("""
            SELECT
                COALESCE(SUM(total_pnl), 0) as total_pnl,
                COUNT(*) as total_trades,
                COUNT(CASE WHEN total_pnl > 0 AND is_closed = 1 THEN 1 END) as wins,
                COUNT(CASE WHEN total_pnl < 0 AND is_closed = 1 THEN 1 END) as losses,
                COUNT(CASE WHEN is_closed = 1 THEN 1 END) as closed_trades,
                MIN(first_trade) as first_trade_at
            FROM (
                SELECT
                    position_id,
                    SUM(pnl) as total_pnl,
                    MAX(CASE WHEN action = 'CLOSE' THEN 1 ELSE 0 END) as is_closed,
                    MIN(created_at) as first_trade
                FROM master_trade_history
                GROUP BY position_id
            )
        """).fetchone()
        return dict(row) if row else {"total_pnl": 0, "total_trades": 0, "wins": 0, "losses": 0, "closed_trades": 0, "first_trade_at": None}

    # --------------------------------------------------------------------------
    # DASHBOARD USERS — Login/Auth
    # --------------------------------------------------------------------------

    def create_invite(self, customer_id: str, invite_token: str) -> None:
        """Einladungslink fuer einen Kunden erstellen."""
        self._conn.execute("""
            INSERT INTO dashboard_users (customer_id, invite_token)
            VALUES (?, ?)
        """, (customer_id, invite_token))
        self._conn.commit()
        logger.info(f"[DB] Dashboard-Einladung erstellt fuer Kunde {customer_id}")

    def get_invite(self, invite_token: str) -> dict[str, Any] | None:
        """Einladung anhand des Tokens laden."""
        row = self._conn.execute("""
            SELECT du.*, c.name as customer_name
            FROM dashboard_users du
            JOIN customers c ON c.id = du.customer_id
            WHERE du.invite_token = ?
        """, (invite_token,)).fetchone()
        return dict(row) if row else None

    def activate_invite(self, invite_token: str, password_hash: str, email: str) -> None:
        """Einladung aktivieren (Passwort + Email setzen)."""
        self._conn.execute("""
            UPDATE dashboard_users
            SET password_hash = ?, email = ?, is_activated = 1
            WHERE invite_token = ?
        """, (password_hash, email, invite_token))
        self._conn.commit()

    def set_telegram_chat_id_by_invite(self, invite_token: str, chat_id: str, username: str = "") -> str | None:
        """Speichert telegram_chat_id am Kunden, dessen telegram_invite_link das
        Token enthaelt. Nur wenn noch leer (nicht ueberschreiben). Gibt E-Mail
        des getroffenen Users zurueck (Logging) oder None."""
        if not invite_token or not chat_id:
            return None
        cur = self._conn.execute(
            "SELECT email FROM dashboard_users "
            "WHERE telegram_invite_link LIKE ? "
            "AND (telegram_chat_id IS NULL OR telegram_chat_id='') LIMIT 1",
            (f"%{invite_token}%",),
        )
        row = cur.fetchone()
        if not row:
            return None
        email = row[0]
        if username:
            self._conn.execute(
                "UPDATE dashboard_users SET telegram_chat_id=?, "
                "telegram_username=COALESCE(NULLIF(telegram_username,''), ?) "
                "WHERE email=?",
                (str(chat_id), username, email),
            )
        else:
            self._conn.execute(
                "UPDATE dashboard_users SET telegram_chat_id=? WHERE email=?",
                (str(chat_id), email),
            )
        self._conn.commit()
        return email

    def get_dashboard_user_by_email(self, email: str) -> dict[str, Any] | None:
        """Dashboard-User anhand der Email laden."""
        row = self._conn.execute("""
            SELECT du.*, c.name as customer_name
            FROM dashboard_users du
            JOIN customers c ON c.id = du.customer_id
            WHERE LOWER(du.email) = LOWER(?) AND du.is_activated = 1
        """, (email,)).fetchone()
        return dict(row) if row else None

    def get_dashboard_user_by_customer(self, customer_id: str) -> dict[str, Any] | None:
        """Dashboard-User anhand der Kunden-ID laden."""
        row = self._conn.execute("""
            SELECT du.*, c.name as customer_name
            FROM dashboard_users du
            JOIN customers c ON c.id = du.customer_id
            WHERE du.customer_id = ? AND du.is_activated = 1
        """, (customer_id,)).fetchone()
        return dict(row) if row else None

    def set_session(self, customer_id: str, session_token: str, expires_at: str) -> None:
        """Session-Token setzen."""
        self._conn.execute("""
            UPDATE dashboard_users
            SET session_token = ?, session_expires_at = ?
            WHERE customer_id = ? AND is_activated = 1
        """, (session_token, expires_at, customer_id))
        self._conn.commit()

    def get_user_by_session(self, session_token: str) -> dict[str, Any] | None:
        """User anhand des Session-Tokens laden (nur wenn nicht abgelaufen)."""
        row = self._conn.execute("""
            SELECT du.*, c.name as customer_name
            FROM dashboard_users du
            JOIN customers c ON c.id = du.customer_id
            WHERE du.session_token = ?
            AND du.session_expires_at > CURRENT_TIMESTAMP
            AND du.is_activated = 1
            AND COALESCE(du.payment_status, '') NOT IN
                ('cancelled', 'refunded', 'chargebacked', 'suspended')
            AND NOT (c.is_active = 0 AND c.deactivated_at IS NOT NULL)
        """, (session_token,)).fetchone()
        return dict(row) if row else None

    def clear_session(self, customer_id: str) -> None:
        """Session loeschen (Logout)."""
        self._conn.execute("""
            UPDATE dashboard_users
            SET session_token = NULL, session_expires_at = NULL
            WHERE customer_id = ?
        """, (customer_id,))
        self._conn.commit()

    # --------------------------------------------------------------------------
    # SELF-SERVICE REGISTRIERUNG & ONBOARDING
    # --------------------------------------------------------------------------

    def register_customer(
        self,
        customer_id: str,
        first_name: str,
        last_name: str,
        email: str,
        password_hash: str,
    ) -> None:
        """Neuen Kunden per Self-Service registrieren (ohne API Keys)."""
        name = f"{first_name} {last_name}"
        self._conn.execute("""
            INSERT INTO customers
                (id, name, first_name, last_name, uid, api_key, api_secret, is_active, onboarding_status)
            VALUES (?, ?, ?, ?, '', '', '', 0, 'registered')
        """, (customer_id, name, first_name, last_name))
        self._conn.execute("""
            INSERT INTO dashboard_users (customer_id, email, password_hash, is_activated, invite_token)
            VALUES (?, ?, ?, 1, ?)
        """, (customer_id, email, password_hash, f"self-reg-{customer_id[:8]}"))
        self._conn.commit()
        logger.info(f"[DB] Self-Service Registrierung: {name} ({email})")

    def get_onboarding_status(self, customer_id: str) -> dict[str, Any] | None:
        """Onboarding-Status eines Kunden laden."""
        row = self._conn.execute("""
            SELECT id, name, first_name, last_name, onboarding_status, onboarding_step,
                   api_key, uid, is_active, paid_at, setup_completed_at
            FROM customers WHERE id = ?
        """, (customer_id,)).fetchone()
        return dict(row) if row else None

    def set_onboarding_status(self, customer_id: str, status: str) -> None:
        """Onboarding-Status setzen."""
        extra = ""
        if status == "paid":
            extra = ", paid_at = CURRENT_TIMESTAMP"
        elif status == "active":
            extra = ", setup_completed_at = CURRENT_TIMESTAMP, is_active = 1"
        self._conn.execute(f"""
            UPDATE customers SET onboarding_status = ?{extra}
            WHERE id = ?
        """, (status, customer_id))
        self._conn.commit()

    def set_onboarding_step(self, customer_id: str, step: int) -> None:
        """Aktuellen Setup-Schritt setzen."""
        self._conn.execute("""
            UPDATE customers SET onboarding_step = ? WHERE id = ?
        """, (step, customer_id))
        self._conn.commit()

    def complete_setup(
        self, customer_id: str, uid: str,
        api_key: str, api_secret: str,
        read_api_key: str = "", read_api_secret: str = "",
    ) -> None:
        """Setup abschliessen: API Keys speichern und Kunden aktivieren."""
        self._conn.execute("""
            UPDATE customers
            SET uid = ?, api_key = ?, api_secret = ?,
                read_api_key = ?, read_api_secret = ?,
                onboarding_status = 'active', onboarding_step = 3,
                is_active = 1, setup_completed_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (uid, api_key, api_secret, read_api_key, read_api_secret, customer_id))
        self._conn.commit()
        logger.info(f"[DB] Setup abgeschlossen fuer Kunde {customer_id}")

    def get_new_active_customers(self, known_ids: set[str]) -> list[dict[str, Any]]:
        """Neue aktive Kunden finden die noch nicht geladen sind (fuer Bot Auto-Reload)."""
        rows = self._conn.execute("""
            SELECT * FROM customers
            WHERE is_active = 1 AND onboarding_status = 'active'
            AND api_key != '' AND api_secret != ''
        """).fetchall()
        return [dict(r) for r in rows if r["id"] not in known_ids]

    # --------------------------------------------------------------------------
    # STATS
    # --------------------------------------------------------------------------

    def count_active_mappings(self) -> int:
        """Anzahl aktiver Mappings."""
        row = self._conn.execute(
            "SELECT COUNT(*) FROM position_mappings WHERE is_active = 1"
        ).fetchone()
        return row[0] if row else 0

    def count_total_mappings(self) -> int:
        """Anzahl aller Mappings (inkl. geschlossene)."""
        row = self._conn.execute(
            "SELECT COUNT(*) FROM position_mappings"
        ).fetchone()
        return row[0] if row else 0

    def count_new_customers_today(self) -> int:
        """Anzahl heute hinzugefuegter Kunden."""
        row = self._conn.execute(
            "SELECT COUNT(*) FROM customers WHERE DATE(created_at) = DATE('now')"
        ).fetchone()
        return row[0] if row else 0

    def get_active_customer_count(self) -> int:
        """Anzahl aktiver Kunden (Follower-Zahl fuer Dashboard)."""
        row = self._conn.execute(
            "SELECT COUNT(*) FROM customers WHERE is_active = 1"
        ).fetchone()
        return row[0] if row else 0

    # --------------------------------------------------------------------------
    # PERFORMANCE & EQUITY CURVE (fuer Dashboard)
    # --------------------------------------------------------------------------

    def get_today_pnl(self, customer_id: str) -> float:
        """Heutiger realisierter PnL fuer einen Kunden."""
        row = self._conn.execute("""
            SELECT COALESCE(SUM(pnl), 0) as today_pnl
            FROM trade_history
            WHERE customer_id = ? AND DATE(created_at) = DATE('now')
        """, (customer_id,)).fetchone()
        return float(row["today_pnl"]) if row else 0.0

    def get_daily_pnl_curve(self, customer_id: str, start_date: str) -> list[dict[str, Any]]:
        """
        Taegliche kumulative PnL-Kurve fuer einen Kunden.

        Gibt Liste von {date, daily_pnl, cumulative_pnl} zurueck.
        """
        rows = self._conn.execute("""
            SELECT
                DATE(created_at) as date,
                SUM(pnl) as daily_pnl
            FROM trade_history
            WHERE customer_id = ? AND DATE(created_at) >= ?
            GROUP BY DATE(created_at)
            ORDER BY DATE(created_at)
        """, (customer_id, start_date)).fetchall()

        curve = []
        cumulative = 0.0
        for r in rows:
            daily = float(r["daily_pnl"])
            cumulative += daily
            curve.append({
                "date": r["date"],
                "daily_pnl": round(daily, 2),
                "cumulative_pnl": round(cumulative, 2),
            })
        return curve

    def get_sync_stats(self, customer_id: str) -> dict[str, Any]:
        """
        Sync-Statistiken fuer einen Kunden:
        - Sync-Genauigkeit (% erfolgreicher Trades)
        - Durchschnittliche Latenz in ms
        """
        row = self._conn.execute("""
            SELECT
                COUNT(*) as total_actions,
                COUNT(CASE WHEN action IN ('OPEN', 'CLOSE') THEN 1 END) as trade_actions,
                AVG(CASE WHEN execution_latency_ms > 0 THEN execution_latency_ms END) as avg_latency_ms
            FROM trade_history
            WHERE customer_id = ?
        """, (customer_id,)).fetchone()

        if not row:
            return {"sync_accuracy": 0, "avg_latency_ms": 0, "total_actions": 0}

        # Sync-Genauigkeit: Vergleiche Kunden-Trades mit Master-Trades
        master_trades = self._conn.execute("""
            SELECT COUNT(DISTINCT position_id) FROM master_trade_history
        """).fetchone()
        customer_trades = self._conn.execute("""
            SELECT COUNT(DISTINCT master_position_id) FROM trade_history
            WHERE customer_id = ?
        """, (customer_id,)).fetchone()

        master_count = master_trades[0] if master_trades else 0
        customer_count = customer_trades[0] if customer_trades else 0
        sync_accuracy = (customer_count / master_count * 100) if master_count > 0 else 100

        return {
            "sync_accuracy": round(min(sync_accuracy, 100), 1),
            "avg_latency_ms": round(row["avg_latency_ms"] or 0),
            "total_actions": row["total_actions"],
        }

    def get_master_daily_pnl_curve(self, start_date: str) -> list[dict[str, Any]]:
        """
        Taegliche kumulative PnL-Kurve des Masters (Bot-Performance).

        Gibt Liste von {date, daily_pnl, cumulative_pnl} zurueck.
        """
        rows = self._conn.execute("""
            SELECT
                DATE(created_at) as date,
                SUM(pnl) as daily_pnl
            FROM master_trade_history
            WHERE DATE(created_at) >= ?
            GROUP BY DATE(created_at)
            ORDER BY DATE(created_at)
        """, (start_date,)).fetchall()

        curve = []
        cumulative = 0.0
        for r in rows:
            daily = float(r["daily_pnl"])
            cumulative += daily
            curve.append({
                "date": r["date"],
                "daily_pnl": round(daily, 2),
                "cumulative_pnl": round(cumulative, 2),
            })
        return curve

    # --------------------------------------------------------------------------
    # BOT STATE — Key/Value fuer globale Bot-Daten
    # --------------------------------------------------------------------------

    def set_state(self, key: str, value: str) -> None:
        """Einen Bot-State-Wert setzen (Upsert)."""
        self._conn.execute("""
            INSERT INTO bot_state (key, value, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET value = ?, updated_at = CURRENT_TIMESTAMP
        """, (key, value, value))
        self._conn.commit()

    def get_state(self, key: str, default: str = "") -> str:
        """Einen Bot-State-Wert lesen."""
        row = self._conn.execute(
            "SELECT value FROM bot_state WHERE key = ?", (key,)
        ).fetchone()
        return row["value"] if row else default

    def update_master_balance(self, balance: float) -> None:
        """Master-Balance in DB persistieren (fuer Dashboard %-Berechnung)."""
        self.set_state("master_balance", str(balance))

    def update_master_positions(self, positions: list[dict]) -> None:
        """Master-Positionen speichern (fuer Dashboard unrealisierten P&L).
        positions = [{"symbol": "BTCUSDT", "side": "Buy", "size": 0.001, "entry": 79000, "mark": 79200}]
        """
        import json
        self.set_state("master_positions", json.dumps(positions))

    def get_master_positions(self) -> list[dict]:
        """Master-Positionen aus DB lesen."""
        import json
        val = self.get_state("master_positions", "[]")
        try:
            return json.loads(val)
        except (ValueError, TypeError):
            return []

    def get_master_balance(self) -> float:
        """Master-Balance aus DB lesen."""
        val = self.get_state("master_balance", "0")
        try:
            return float(val)
        except (ValueError, TypeError):
            return 0.0

    # --------------------------------------------------------------------------
    # HOURLY PNL CURVES — fuer 1T-Ansicht im Dashboard
    # --------------------------------------------------------------------------

    def get_hourly_pnl_curve(self, customer_id: str, start_date: str) -> list[dict[str, Any]]:
        """
        Stuendliche kumulative PnL-Kurve fuer einen Kunden (fuer 1T-Ansicht).

        Gibt Liste von {date, daily_pnl, cumulative_pnl} zurueck,
        wobei date = 'YYYY-MM-DD HH:00'.
        """
        rows = self._conn.execute("""
            SELECT
                strftime('%Y-%m-%d %H:00', created_at) as hour_bucket,
                SUM(pnl) as hourly_pnl
            FROM trade_history
            WHERE customer_id = ? AND DATE(created_at) >= ?
            GROUP BY hour_bucket
            ORDER BY hour_bucket
        """, (customer_id, start_date)).fetchall()

        curve = []
        cumulative = 0.0
        for r in rows:
            hourly = float(r["hourly_pnl"])
            cumulative += hourly
            curve.append({
                "date": r["hour_bucket"],
                "daily_pnl": round(hourly, 4),
                "cumulative_pnl": round(cumulative, 4),
            })
        return curve

    def get_master_hourly_pnl_curve(self, start_date: str) -> list[dict[str, Any]]:
        """
        Stuendliche kumulative PnL-Kurve des Masters (fuer 1T-Ansicht).
        """
        rows = self._conn.execute("""
            SELECT
                strftime('%Y-%m-%d %H:00', created_at) as hour_bucket,
                SUM(pnl) as hourly_pnl
            FROM master_trade_history
            WHERE DATE(created_at) >= ?
            GROUP BY hour_bucket
            ORDER BY hour_bucket
        """, (start_date,)).fetchall()

        curve = []
        cumulative = 0.0
        for r in rows:
            hourly = float(r["hourly_pnl"])
            cumulative += hourly
            curve.append({
                "date": r["hour_bucket"],
                "daily_pnl": round(hourly, 4),
                "cumulative_pnl": round(cumulative, 4),
            })
        return curve

    # --------------------------------------------------------------------------
    # SIGNAL BOT — Display Names & Logging
    # --------------------------------------------------------------------------

    def get_signal_display_name(self, position_id: str) -> str | None:
        """Display-Name fuer eine Position holen (z.B. 'BTC Short #1')."""
        row = self._conn.execute(
            "SELECT display_name FROM signal_display_names WHERE position_id = ?",
            (position_id,),
        ).fetchone()
        return row["display_name"] if row else None

    def count_active_signal_names(
        self, symbol: str, side: str, is_scalp: int | None = None
    ) -> int:
        """Anzahl aktiver Display-Names fuer ein Symbol+Side (fuer Nummerierung).

        is_scalp=None  -> alle (altes Verhalten)
        is_scalp=0/1   -> nur Main- bzw. nur Scalp-Trades zaehlen. Damit haben
                          Scalp-Channel und Main-Gruppe getrennte Zaehler und ein
                          Scalp startet nicht bei #2, nur weil in der Main noch ein
                          normaler Trade desselben Symbols offen ist.
        """
        sql = (
            "SELECT COUNT(*) FROM signal_display_names "
            "WHERE symbol = ? AND side = ? AND is_active = 1"
        )
        params = [symbol, side]
        if is_scalp is not None:
            sql += " AND COALESCE(is_scalp, 0) = ?"
            params.append(int(is_scalp))
        row = self._conn.execute(sql, tuple(params)).fetchone()
        return row[0] if row else 0

    def save_signal_display_name(
        self, position_id: str, display_name: str, symbol: str, side: str, number: int,
        entry_price: float = 0, open_timestamp: float = 0,
    ) -> None:
        """Neuen Display-Name speichern."""
        self._conn.execute(
            "INSERT OR REPLACE INTO signal_display_names "
            "(position_id, display_name, symbol, side, number, is_active, entry_price, open_timestamp) "
            "VALUES (?,?,?,?,?,1,?,?)",
            (position_id, display_name, symbol, side, number, entry_price, open_timestamp),
        )
        self._conn.commit()

    def get_signal_trade_info(self, position_id: str) -> dict | None:
        """Alle gespeicherten Infos fuer einen Trade holen (fuer Close-Nachricht etc.)."""
        row = self._conn.execute(
            "SELECT display_name, symbol, side, entry_price, open_timestamp, is_active "
            "FROM signal_display_names WHERE position_id = ?",
            (position_id,),
        ).fetchone()
        return dict(row) if row else None

    def get_all_active_signals(self) -> list[dict]:
        """Alle aktiven Signal-Positionen holen (fuer taegliche Uebersicht)."""
        rows = self._conn.execute(
            "SELECT position_id, display_name, symbol, side, entry_price, open_timestamp, is_scalp "
            "FROM signal_display_names WHERE is_active = 1 ORDER BY created_at ASC"
        ).fetchall()
        return [dict(r) for r in rows]

    def is_scalp_position(self, position_id: str) -> bool:
        """Ist diese Position als Scalp (>= Schwellen-Hebel BEIM OEFFNEN) markiert?"""
        if not position_id:
            return False
        row = self._conn.execute(
            "SELECT is_scalp FROM signal_display_names WHERE position_id = ?",
            (position_id,),
        ).fetchone()
        return bool(row["is_scalp"]) if row else False

    def mark_signal_scalp(self, position_id: str) -> None:
        """Position dauerhaft als Scalp markieren (nur setzen, nie zuruecksetzen)."""
        self._conn.execute(
            "UPDATE signal_display_names SET is_scalp = 1 WHERE position_id = ?",
            (position_id,),
        )
        self._conn.commit()

    def close_signal_display_name(self, position_id: str) -> None:
        """Display-Name als inaktiv markieren (Position geschlossen)."""
        self._conn.execute(
            "UPDATE signal_display_names SET is_active = 0 WHERE position_id = ?",
            (position_id,),
        )
        self._conn.commit()

    def reconcile_signal_display_names(self, live_position_ids: list[str]) -> list[dict]:
        """
        Aktive Display-Names gegen die echten offenen Master-Positionen abgleichen.
        Alle aktiven Eintraege, deren position_id NICHT in der Live-Liste ist,
        werden deaktiviert (verwaiste Karteileichen — z.B. wenn ein Close waehrend
        Bot-Downtime verpasst wurde).

        WICHTIG: Nur mit einem VOLLSTAENDIGEN Positions-Snapshot aufrufen, niemals
        mit einem inkrementellen Update (sonst werden offene Positionen faelschlich
        deaktiviert).

        Returns: Liste der deaktivierten Eintraege (fuer Logging).
        """
        live = set(live_position_ids)
        active = self._conn.execute(
            "SELECT position_id, display_name FROM signal_display_names WHERE is_active = 1"
        ).fetchall()
        orphaned = [dict(r) for r in active if r["position_id"] not in live]
        if orphaned:
            self._conn.executemany(
                "UPDATE signal_display_names SET is_active = 0 WHERE position_id = ?",
                [(o["position_id"],) for o in orphaned],
            )
            self._conn.commit()
        return orphaned

    def log_signal(
        self, position_id: str, signal_type: str, message_text: str,
        sent_to_paid: bool = False, sent_to_free: bool = False,
    ) -> None:
        """Signal in Log speichern (Audit-Trail)."""
        self._conn.execute(
            "INSERT INTO signal_log (position_id, signal_type, message_text, sent_to_paid, sent_to_free) VALUES (?,?,?,?,?)",
            (position_id, signal_type, message_text, 1 if sent_to_paid else 0, 1 if sent_to_free else 0),
        )
        self._conn.commit()

    def was_signal_sent_to_free(self, position_id: str, signal_type: str) -> bool:
        """Pruefen ob ein Signal fuer diese Position an die Free-Gruppe gesendet wurde."""
        row = self._conn.execute(
            "SELECT 1 FROM signal_log WHERE position_id = ? AND signal_type = ? AND sent_to_free = 1 LIMIT 1",
            (position_id, signal_type),
        ).fetchone()
        return row is not None

    def count_free_signals_this_week(self) -> int:
        """Anzahl OPEN-Signale die diese Woche an die Free-Gruppe gesendet wurden."""
        row = self._conn.execute("""
            SELECT COUNT(*) FROM signal_log
            WHERE signal_type = 'open' AND sent_to_free = 1
            AND created_at >= datetime('now', 'weekday 0', '-7 days')
        """).fetchone()
        return row[0] if row else 0

    def get_last_free_signal_hours_ago(self) -> float | None:
        """Stunden seit dem letzten OPEN-Signal an die Free-Gruppe. None wenn noch keines."""
        row = self._conn.execute("""
            SELECT (julianday('now') - julianday(created_at)) * 24 AS hours_ago
            FROM signal_log
            WHERE signal_type = 'open' AND sent_to_free = 1
            ORDER BY created_at DESC LIMIT 1
        """).fetchone()
        return row[0] if row else None

    def get_period_performance(self, days: int = 7) -> dict[str, Any]:
        """Performance der letzten N Tage (fuer Marketing Summaries).
        1 Trade = 1 unique position_id."""
        row = self._conn.execute("""
            SELECT
                COALESCE(SUM(total_pnl), 0) as total_pnl,
                COUNT(*) as total_trades,
                COUNT(CASE WHEN total_pnl > 0 AND is_closed = 1 THEN 1 END) as wins,
                COUNT(CASE WHEN total_pnl < 0 AND is_closed = 1 THEN 1 END) as losses,
                COUNT(CASE WHEN is_closed = 1 THEN 1 END) as closed_trades
            FROM (
                SELECT
                    position_id,
                    SUM(pnl) as total_pnl,
                    MAX(CASE WHEN action = 'CLOSE' THEN 1 ELSE 0 END) as is_closed
                FROM master_trade_history
                WHERE created_at >= datetime('now', ?)
                GROUP BY position_id
            )
        """, (f"-{days} days",)).fetchone()
        result = dict(row) if row else {"total_pnl": 0, "total_trades": 0, "wins": 0, "losses": 0, "closed_trades": 0}
        closed = result["wins"] + result["losses"]
        result["win_rate"] = (result["wins"] / closed * 100) if closed > 0 else 0
        return result

    def get_dashboard_user_product_tier(self, customer_id: str) -> str:
        """Product-Tier eines Users holen."""
        row = self._conn.execute(
            "SELECT product_tier FROM dashboard_users WHERE customer_id = ?",
            (customer_id,),
        ).fetchone()
        return row["product_tier"] if row else "paid_signals"

    def set_product_tier(self, customer_id: str, tier: str) -> None:
        """Product-Tier eines Users setzen (free, paid_signals, copy_trading)."""
        self._conn.execute(
            "UPDATE dashboard_users SET product_tier = ? WHERE customer_id = ?",
            (tier, customer_id),
        )
        self._conn.commit()
