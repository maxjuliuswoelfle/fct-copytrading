"""
(C) logger_setup.py — Zentraler Logger fuer den Copy Trading Bot

Nutzt Python logging mit Timestamp + farbiger Ausgabe in der Console.
Log-Level wird aus der Config gezogen (default: info).
"""

import logging
import sys
from config import config

# Farben fuer die Console (ANSI Escape Codes)
COLORS = {
    "DEBUG": "\033[36m",     # Cyan
    "INFO": "\033[32m",      # Gruen
    "WARNING": "\033[33m",   # Gelb
    "ERROR": "\033[31m",     # Rot
    "CRITICAL": "\033[35m",  # Magenta
    "RESET": "\033[0m",      # Reset
}


class ColoredFormatter(logging.Formatter):
    """Custom Formatter mit Farben fuer die Console."""

    def format(self, record: logging.LogRecord) -> str:
        color = COLORS.get(record.levelname, COLORS["RESET"])
        reset = COLORS["RESET"]
        # Format: [Timestamp] LEVEL: Message
        record.levelname = f"{color}{record.levelname}{reset}"
        return super().format(record)


def setup_logger(name: str = "bot") -> logging.Logger:
    """Logger erstellen mit farbiger Console-Ausgabe."""
    logger = logging.getLogger(name)

    # Level aus Config
    level = getattr(logging, config.log_level.upper(), logging.INFO)
    logger.setLevel(level)

    # Keine doppelten Handler
    if logger.handlers:
        return logger

    # Console Handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)

    formatter = ColoredFormatter(
        fmt="[%(asctime)s.%(msecs)03d] %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger


# Standard-Logger Instanz
logger = setup_logger()
