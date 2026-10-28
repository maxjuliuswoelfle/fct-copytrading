#!/usr/bin/env python3
# Einmal-Patch: _format_limit_added um Hebel + Einsatz (Groesse) erweitern.
import io, sys

PATH = "/home/botuser/copy-trading-bot/signal_bot.py"

OLD = '''    def _format_limit_added(self, event: ParsedEvent) -> str:
        d = event.details
        price = d.get("price", "?")
        position_id = d.get("positionID", "")
        display_name = self._db.get_signal_display_name(position_id) or event.symbol

        lines = [
            "\U0001f7e1 <b>Limit Order hinzugefügt</b>",
            "",
            f"Für {display_name}",
            f"Limit Preis: {self._fmt_price(price)}",
            "",
            "⏳ Wartet auf Ausführung",
            "",
            FOOTER,
        ]
        return "\\n".join(lines)'''

NEW = '''    def _format_limit_added(self, event: ParsedEvent) -> str:
        d = event.details
        price = float(d.get("price", 0) or 0)
        position_id = d.get("positionID", "")
        display_name = self._db.get_signal_display_name(position_id) or event.symbol

        leverage = self._get_leverage(position_id)

        lines = [
            "\U0001f7e1 <b>Limit Order hinzugefügt — Nachkauf</b>",
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
        return "\\n".join(lines)'''

with io.open(PATH, "r", encoding="utf-8") as f:
    src = f.read()

cnt = src.count(OLD)
if cnt != 1:
    print(f"ABORT: erwartete genau 1 Treffer, gefunden {cnt}")
    sys.exit(1)

src = src.replace(OLD, NEW)
with io.open(PATH, "w", encoding="utf-8") as f:
    f.write(src)
print("OK: _format_limit_added gepatcht (1 Block ersetzt)")
