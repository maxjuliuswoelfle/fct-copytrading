"""
(C) scaling.py — Skalierungs-Engine fuer den Copy Trading Bot

Berechnet die proportionale Positionsgroesse fuer Kunden-Accounts.
Kernprinzip: Ein Kunde mit 10% der Master-Balance bekommt 10% der Position.

Sicherheit:
- Minimum Order Size wird geprueft (unter dem Minimum wird nicht gehandelt)
- Rundung auf Tick Size / Lot Size der Exchange
- Keine negative Qty moeglich
"""

import math
from dataclasses import dataclass

from logger_setup import logger


# ============================================================================
# KONFIGURATION
# ============================================================================

@dataclass
class ScalingConfig:
    """Symbol-spezifische Skalierungs-Konfiguration."""
    min_order_size: float = 0.001   # Minimale Order-Groesse (Exchange-abhaengig)
    tick_size: float = 0.01         # Tick Size fuer Preise (z.B. 0.01 fuer USDT)
    lot_size: float = 0.001         # Lot Size fuer Mengen (z.B. 0.001 fuer BTC)


# Default-Werte — werden spaeter pro Symbol aus der Exchange geladen
DEFAULT_CONFIG = ScalingConfig()


# ============================================================================
# SCALING ENGINE
# ============================================================================

class ScalingEngine:

    def __init__(self) -> None:
        self._configs: dict[str, ScalingConfig] = {}

    def set_symbol_config(self, symbol: str, config: ScalingConfig) -> None:
        """
        Symbol-spezifische Konfiguration setzen.
        In Phase 2 wird das aus der Exchange API geladen.
        """
        self._configs[symbol] = config

    def _get_config(self, symbol: str | None = None) -> ScalingConfig:
        """Konfiguration fuer ein Symbol holen (oder Default)."""
        if symbol:
            return self._configs.get(symbol, DEFAULT_CONFIG)
        return DEFAULT_CONFIG

    # --------------------------------------------------------------------------
    # SKALIERUNG
    # --------------------------------------------------------------------------

    def calculate_customer_margin(
        self,
        master_balance: float,
        customer_balance: float,
        master_margin: float,
    ) -> float:
        """
        Kunden-Margin berechnen (proportional zur Account-Groesse).

        Formel: customer_margin = master_margin * (customer_balance / master_balance)

        Beispiel:
        - Master Balance: 100.000 USDT, Master Margin: 10.000 USDT
        - Kunde Balance: 5.000 USDT
        - -> Kunden Margin: 10.000 * (5.000 / 100.000) = 500 USDT
        """
        if master_balance <= 0:
            logger.warning("Master Balance ist 0 oder negativ — keine Skalierung moeglich")
            return 0.0

        ratio = customer_balance / master_balance
        customer_margin = master_margin * ratio

        logger.debug(
            f"Margin-Skalierung: Master {master_margin} x Ratio {ratio:.4f} "
            f"= Kunde {customer_margin:.4f}"
        )

        return self._round_to_tick(customer_margin)

    def calculate_customer_qty(
        self,
        master_balance: float,
        customer_balance: float,
        master_qty: float,
        symbol: str | None = None,
        customer_free_margin: float | None = None,
        leverage: float = 10.0,
        price: float = 0.0,
    ) -> float:
        """
        Kunden-Qty berechnen (proportional zur Account-Groesse).

        Formel: customer_qty = master_qty * (customer_balance / master_balance)

        Minimum-Qty Fallback:
        Wenn die skalierte Qty unter dem Exchange-Minimum liegt, wird auf das
        Minimum aufgerundet — SOFERN der Kunde genug freie Margin hat.
        Das stellt sicher, dass auch kleine Kunden Trades mitbekommen.
        """
        if master_balance <= 0:
            logger.warning("Master Balance ist 0 oder negativ — keine Skalierung moeglich")
            return 0.0

        cfg = self._get_config(symbol)
        ratio = customer_balance / master_balance
        raw_qty = master_qty * ratio
        rounded_qty = self._round_to_lot(raw_qty, symbol)

        # Minimum Order Size Check mit Fallback
        if rounded_qty < cfg.min_order_size:
            # Fallback: Auf Minimum setzen wenn Margin reicht
            min_qty = cfg.min_order_size

            if customer_free_margin is not None and price > 0 and leverage > 0:
                # Margin-Check: Hat der Kunde genug freie Margin fuer die Minimum-Qty?
                required_margin = (min_qty * price) / leverage
                if required_margin > customer_free_margin:
                    logger.warning(
                        f"[SCALING] {symbol or '?'}: Qty {rounded_qty} unter Minimum {min_qty} "
                        f"— Minimum braucht {required_margin:.2f} USDT Margin, "
                        f"Kunde hat nur {customer_free_margin:.2f} frei — UEBERSPRUNGEN"
                    )
                    return 0.0

            # Auf Minimum aufgerundet
            logger.info(
                f"[SCALING] {symbol or '?'}: Skalierte Qty {rounded_qty} unter Minimum "
                f"— auf Minimum {min_qty} aufgerundet (Ratio: {ratio:.4f})"
            )
            return min_qty

        logger.debug(
            f"Qty-Skalierung: Master {master_qty} x Ratio {ratio:.4f} "
            f"= Kunde {rounded_qty} ({symbol or '?'})"
        )

        return rounded_qty

    def calculate_partial_close_percent(
        self,
        previous_size: float,
        new_size: float,
    ) -> float:
        """
        Prozentsatz einer Teilschliessung berechnen.

        Beispiel: previous_size 10, new_size 7 -> 30% geschlossen
        Wird genutzt um bei Kunden den gleichen Prozentsatz zu schliessen.
        """
        if previous_size <= 0:
            logger.warning("Previous Size ist 0 — kann keinen Prozentsatz berechnen")
            return 0.0

        closed_size = previous_size - new_size
        percent = (closed_size / previous_size) * 100

        logger.debug(
            f"Teilschliessung: {previous_size} -> {new_size} = {percent:.2f}% geschlossen"
        )

        # Sicherheitscheck: Zwischen 0% und 100%
        return max(0.0, min(100.0, percent))

    # --------------------------------------------------------------------------
    # RUNDUNG
    # --------------------------------------------------------------------------

    def _round_to_tick(self, value: float, symbol: str | None = None) -> float:
        """
        Auf Tick Size runden (fuer Preise und Margins).
        Beispiel: tick_size 0.01 -> 123.456 wird zu 123.45
        """
        cfg = self._get_config(symbol)
        return self._round_to_step(value, cfg.tick_size)

    def _round_to_lot(self, value: float, symbol: str | None = None) -> float:
        """
        Auf Lot Size runden (fuer Mengen/Qty).
        Beispiel: lot_size 0.001 -> 1.23456 wird zu 1.234
        """
        cfg = self._get_config(symbol)
        return self._round_to_step(value, cfg.lot_size)

    @staticmethod
    def _round_to_step(value: float, step: float) -> float:
        """
        Generische Rundung auf eine Schrittgroesse.
        Rundet immer ab (Floor) — lieber zu wenig als zu viel riskieren.
        """
        if step <= 0:
            return value
        # Floor-Rundung: Sicherheit geht vor
        decimals = ScalingEngine._get_decimals(step)
        result = math.floor(value / step) * step
        # Floating-Point Artefakte bereinigen
        return round(result, decimals)

    @staticmethod
    def _get_decimals(num: float) -> int:
        """
        Anzahl Dezimalstellen einer Zahl ermitteln.
        0.001 -> 3, 0.01 -> 2, 1 -> 0
        """
        s = str(num)
        dot_index = s.find(".")
        if dot_index == -1:
            return 0
        return len(s) - dot_index - 1
