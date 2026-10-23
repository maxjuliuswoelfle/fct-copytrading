"""
(C) analyse_master_performance.py - wertet die Master-Trade-Historie Trade fuer Trade aus.

Liest master_trades_raw.json (Rohdaten aus der LeveX Trade-Historie) und baut
pro Position eine vollstaendige Abrechnung: gewichteter Entry/Exit, Teilverkaeufe,
Hebel, eingesetzte Margin, Brutto-PnL, Handelsgebuehren, Funding, Netto-PnL.
"""
import json
import csv
from datetime import datetime, timezone
from collections import defaultdict

ROWS = json.load(open("master_trades_raw.json"))


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def ts(ms):
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


positions = defaultdict(lambda: {
    "symbol": "", "side": "", "name": "", "fills": [], "funding": 0.0,
})

for r in ROWS:
    pid = r["positionID"]
    p = positions[pid]
    if not p["symbol"]:
        p["symbol"] = r["symbol"]
        p["name"] = r.get("positionName") or ""
    if r["tradeType"] == "Funding":
        p["funding"] += f(r["execFee"])
        continue
    p["fills"].append(r)

trades = []
for pid, p in positions.items():
    fills = sorted(p["fills"], key=lambda r: r["transactTimeNs"])
    if not fills:
        continue

    open_qty = open_val = open_margin = 0.0
    close_qty = close_val = 0.0
    gross = fees = 0.0
    n_open = n_close = 0
    levs = []
    liquidated = False
    side = ""

    for r in fills:
        qty = f(r["execQty"])
        val = f(r["execValue"])
        lev = f(r["leverage"]) or 1.0
        fees += f(r["execFee"])
        closed = f(r["closedSize"])
        if r.get("action") == "LiqRequest":
            liquidated = True
        if closed > 0:
            n_close += 1
            close_qty += qty
            close_val += val
            gross += f(r["closedPnl"])
        else:
            n_open += 1
            if not side:
                side = r["side"]
            open_qty += qty
            open_val += val
            open_margin += val / lev
            levs.append(lev)

    if open_qty <= 0:
        continue

    net = gross - fees - p["funding"]
    entry = open_val / open_qty if open_qty else 0.0
    exit_ = close_val / close_qty if close_qty else 0.0
    lev_avg = (sum(levs) / len(levs)) if levs else 0.0
    offen = close_qty < open_qty * 0.999

    trades.append({
        "pid": pid,
        "symbol": p["symbol"],
        "name": p["name"],
        "side": "Long" if side == "Buy" else "Short",
        "open_time": ts(fills[0]["transactTimeNs"] / 1e6),
        "close_time": ts(fills[-1]["transactTimeNs"] / 1e6),
        "entry": entry,
        "exit": exit_,
        "qty": open_qty,
        "notional": open_val,
        "margin": open_margin,
        "leverage": lev_avg,
        "n_open": n_open,
        "n_close": n_close,
        "gross": gross,
        "fees": fees,
        "funding": p["funding"],
        "net": net,
        "roi_margin": (net / open_margin * 100) if open_margin else 0.0,
        "liquidated": liquidated,
        "offen": offen,
    })

trades.sort(key=lambda t: t["open_time"])

with open("master_performance.csv", "w", newline="", encoding="utf-8") as fh:
    w = csv.writer(fh, delimiter=";")
    w.writerow([
        "Nr", "Eroeffnet", "Geschlossen", "Symbol", "Richtung", "Name",
        "Entry", "Exit", "Menge", "Notional", "Margin", "Hebel",
        "Einstiege", "Ausstiege", "Brutto_PnL", "Gebuehren", "Funding",
        "Netto_PnL", "ROI_auf_Margin_%", "Liquidiert", "Noch_offen",
    ])
    for i, t in enumerate(trades, 1):
        w.writerow([
            i,
            t["open_time"].strftime("%Y-%m-%d %H:%M"),
            t["close_time"].strftime("%Y-%m-%d %H:%M"),
            t["symbol"], t["side"], t["name"],
            round(t["entry"], 4), round(t["exit"], 4), round(t["qty"], 6),
            round(t["notional"], 2), round(t["margin"], 2), round(t["leverage"], 2),
            t["n_open"], t["n_close"],
            round(t["gross"], 2), round(t["fees"], 2), round(t["funding"], 2),
            round(t["net"], 2), round(t["roi_margin"], 2),
            "ja" if t["liquidated"] else "", "ja" if t["offen"] else "",
        ])

json.dump(
    [{**t, "open_time": t["open_time"].isoformat(), "close_time": t["close_time"].isoformat()}
     for t in trades],
    open("master_performance.json", "w"), indent=1,
)

print("Trades:", len(trades))
print("Netto gesamt:", round(sum(t["net"] for t in trades), 2))
print("CSV: master_performance.csv")
