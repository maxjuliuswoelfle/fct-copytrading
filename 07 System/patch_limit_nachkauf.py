# -*- coding: utf-8 -*-
p = "/home/botuser/copy-trading-bot/signal_bot.py"
s = open(p, encoding="utf-8").read()
old = '''                if display_name:
                    lines.append(f"⏳ {display_name}    →  Nachkauf @ {self._fmt_price(price)}")
                else:
                    side = info.get("side", "Buy")
                    direction = "Long" if side == "Buy" else "Short"
                    lines.append(f"⏳ {symbol} {direction}    →  Limit @ {self._fmt_price(price)}")'''
new = '''                # "Nachkauf" NUR wenn wirklich eine LIVE-Position offen ist (echter
                # Nachkauf-Limit auf eine bestehende Position). Eine normale Entry-Limit
                # bekommt zwar auch sofort einen Display-Namen in der DB (damit der Trade
                # von Anfang an gleich heisst), ist aber KEIN Nachkauf -- sonst wird jede
                # ganz normale Limit-Order faelschlich als "Nachkauf" gelabelt. Gleiche
                # Unterscheidung wie in _classify (limit_added vs new_limit).
                if display_name and self._has_live_position(pos_id):
                    lines.append(f"⏳ {display_name}    →  Nachkauf @ {self._fmt_price(price)}")
                elif display_name:
                    lines.append(f"⏳ {display_name}    →  Limit @ {self._fmt_price(price)}")
                else:
                    side = info.get("side", "Buy")
                    direction = "Long" if side == "Buy" else "Short"
                    lines.append(f"⏳ {symbol} {direction}    →  Limit @ {self._fmt_price(price)}")'''
n = s.count(old)
assert n == 1, "anchor count %d" % n
open(p, "w", encoding="utf-8").write(s.replace(old, new))
print("patched OK")
