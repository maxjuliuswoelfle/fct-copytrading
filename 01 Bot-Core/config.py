"""
(C) config.py — Zentrale Konfiguration fuer den Copy Trading Bot

Laedt Umgebungsvariablen aus .env und exportiert ein typisiertes Config-Objekt.
Alle sensiblen Daten (API Keys, Secrets) kommen ausschliesslich aus Environment Variables.
"""

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

# Unterstuetzte Umgebungen
VALID_ENVIRONMENTS = ("testnet", "production")

# URLs je nach Umgebung
WS_URLS = {
    "testnet": "wss://stream-testnet.levex.com",
    "production": "wss://stream.levex.com",
}

REST_URLS = {
    "testnet": "https://api-testnet.levex.com",
    "production": "https://api.levex.com",
}


def _require_env(key: str) -> str:
    """
    Pflichtfeld aus Environment laden — wirft Fehler wenn nicht gesetzt.
    Bei echtem Geld anderer Leute darf nichts fehlen.
    """
    value = os.getenv(key)
    if not value:
        raise RuntimeError(
            f"Umgebungsvariable {key} ist nicht gesetzt. Bitte in .env Datei konfigurieren."
        )
    return value


@dataclass(frozen=True)
class BotConfig:
    """Zentrale Bot-Konfiguration."""

    # Levex API Key
    api_key: str
    # Levex API Secret (HMAC-SHA256)
    api_secret: str
    # UID des Master-Accounts (Max' Trading-Account)
    master_uid: str
    # Aktive Umgebung — testnet fuer Entwicklung, production fuer Live
    env: str
    # WebSocket URL basierend auf Umgebung
    ws_url: str
    # REST API URL basierend auf Umgebung
    rest_url: str
    # Log-Level (debug, info, warning, error)
    log_level: str
    # Telegram Alerts (optional)
    telegram_bot_token: str
    telegram_chat_id: str
    telegram_team_password: str


# Umgebung bestimmen — Default ist testnet (Sicherheit geht vor)
_env = os.getenv("LEVEX_ENV", "testnet")
if _env not in VALID_ENVIRONMENTS:
    _env = "testnet"

config = BotConfig(
    api_key=_require_env("LEVEX_API_KEY"),
    api_secret=_require_env("LEVEX_API_SECRET"),
    master_uid=_require_env("LEVEX_MASTER_UID"),
    env=_env,
    ws_url=WS_URLS[_env],
    rest_url=REST_URLS[_env],
    log_level=os.getenv("LOG_LEVEL", "info"),
    telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
    telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
    telegram_team_password=os.getenv("TELEGRAM_TEAM_PASSWORD", ""),
)
