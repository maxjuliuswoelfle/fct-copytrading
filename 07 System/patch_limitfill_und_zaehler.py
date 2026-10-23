"""
patch_limitfill_und_zaehler.py — zwei Fixes, anker-basiert.

FIX 1: Normale Limit-Ausfuehrung wurde als "Nachkauf" gepostet.
       Ursache: der Display-Name wird schon BEIM SETZEN der Limit angelegt.
       Beim Fill fragte _classify nur "gibt es einen Namen?" -> immer True
       -> jede normale Entry-Limit galt als Nachkauf.
       Fix: die Entscheidung wird beim Setzen der Order getroffen (dort ist sie
       korrekt, via _has_live_position) und an der Order gemerkt. Der Fill liest
       sie aus statt neu zu raten.

FIX 2: Trade-Nummer war global pro Symbol+Side -> ein offener normaler BTC Short
       (#1, Main) liess jeden Scalp-Short als "#2" starten, obwohl er im
       Scalp-Channel der einzige Trade war.
       Fix: Zaehler getrennt pro Kanal (Scalp zaehlt unter sich, Main unter sich).

Aufruf auf dem Server im Bot-Ordner:  python3 patch_limitfill_und_zaehler.py
"""

import sys

SIGNAL = "signal_bot.py"
DB = "database.py"


def patch(path, old, new, label):
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    n = src.count(old)
    if n != 1:
        print(f"ABBRUCH [{label}]: Anker {n}x gefunden (erwartet: 1)")
        sys.exit(1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(src.replace(old, new))
    print(f"OK [{label}]")


# ---------------------------------------------------------------------------
# FIX 2a — database.py: Zaehlung optional auf Scalp/Main einschraenken
# ---------------------------------------------------------------------------
patch(
    DB,
    '''    def count_active_signal_names(self, symbol: str, side: str) -> int:
        """Anzahl aktiver Display-Names fuer ein Symbol+Side (fuer Nummerierung)."""
        row = self._conn.execute(
            "SELECT COUNT(*) FROM signal_display_names WHERE symbol = ? AND side = ? AND is_active = 1",
            (symbol, side),
        ).fetchone()
        return row[0] if row else 0''',
    '''    def count_active_signal_names(
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
        return row[0] if row else 0''',
    "FIX 2a database.count_active_signal_names",
)


# ---------------------------------------------------------------------------
# FIX 2b — signal_bot.py: Helper "wird das ein Scalp?" (vor _mark_scalp_if_qualifies)
# ---------------------------------------------------------------------------
patch(
    SIGNAL,
    '''    def _mark_scalp_if_qualifies(self, position_id: str) -> None:''',
    '''    def _will_be_scalp(self, position_id: str) -> bool:
        """True, wenn dieser Trade im Scalp-Channel landet (Hebel >= Schwelle).

        Wird NUR fuer die Nummerierung gebraucht, damit Scalp und Main getrennte
        Zaehler haben. Setzt nichts, schreibt nichts.
        """
        if not self._scalp_group_id or not position_id:
            return False
        if self._db.is_scalp_position(position_id):
            return True
        return self._get_leverage(position_id) >= self._scalp_min_leverage

    def _mark_scalp_if_qualifies(self, position_id: str) -> None:''',
    "FIX 2b signal_bot._will_be_scalp",
)


# ---------------------------------------------------------------------------
# FIX 2c — signal_bot.py: Nummerierung pro Kanal
# ---------------------------------------------------------------------------
patch(
    SIGNAL,
    '''        count = self._db.count_active_signal_names(event.symbol, side)
        number = count + 1''',
    '''        # Getrennte Zaehler fuer Scalp-Channel und Main-Gruppe: ein Scalp soll
        # nicht "#2" heissen, nur weil in der Main noch ein normaler Trade
        # desselben Symbols offen ist (und umgekehrt).
        scalp_bucket = 1 if self._will_be_scalp(position_id) else 0
        count = self._db.count_active_signal_names(
            event.symbol, side, is_scalp=scalp_bucket
        )
        number = count + 1''',
    "FIX 2c signal_bot Nummerierung",
)


# ---------------------------------------------------------------------------
# FIX 1a — signal_bot.py: Nachkauf-Entscheidung beim SETZEN der Limit merken
# ---------------------------------------------------------------------------
patch(
    SIGNAL,
    '''                # Tracke die Limit Order
                self._pending_limits[order_id] = {
                    "symbol": event.symbol,
                    "side": d.get("side", ""),
                    "price": price,
                    "positionID": position_id,
                    "posSide": d.get("posSide", ""),
                }

                # Hat diese Position schon einen Display-Name? → moeglicher Nachkauf.
                # ABER nur als "Nachkauf" labeln, wenn wirklich eine LIVE-Position
                # offen ist. Sonst ist es eine neu/wieder eingestellte Entry-Limit
                # (z.B. nach Cancel+Replace beim Editieren des Einstiegs) — die als
                # "Nachkauf hinzugefuegt" auszugeben ist irrefuehrend.
                if position_id and self._db.get_signal_display_name(position_id):
                    if self._has_live_position(position_id):
                        return "limit_added"
                    return "new_limit"
                return "new_limit"''',
    '''                # Ist das ein ECHTER Nachkauf auf eine bestehende LIVE-Position?
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

                return "limit_added" if is_scalein else "new_limit"''',
    "FIX 1a signal_bot OPEN_TRADE",
)


# ---------------------------------------------------------------------------
# FIX 1b — signal_bot.py: beim Fill die gemerkte Entscheidung nutzen
# ---------------------------------------------------------------------------
patch(
    SIGNAL,
    '''                    limit_info = self._pending_limits.pop(order_id, None)

                    # Gab es schon einen Display-Name? → Nachkauf-Fill
                    if position_id and self._db.get_signal_display_name(position_id):
                        return "limit_filled_scalein"
                    return "limit_filled"''',
    '''                    limit_info = self._pending_limits.pop(order_id, None)

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
                    return "limit_filled"''',
    "FIX 1b signal_bot TRADE_FILLED",
)

print("\nAlle 5 Patches sauber angewendet.")
