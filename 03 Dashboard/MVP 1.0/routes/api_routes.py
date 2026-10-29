"""
(C) api_routes.py — JSON API Endpoints fuer Frontend-Polling

Endpoints:
  /api/stats         — Statische Stats (PnL, Trades, Win Rate)
  /api/positions     — Aktive Positionen aus DB
  /api/history       — Geschlossene Trades
  /api/live          — Live-Daten von der Exchange (Balance, Preise, Unrealisierter P&L)
  /api/equity        — Equity-Kurve fuer Charts
  /api/feed          — Live-Aktivitaeten (Trade-Events)
  /api/recent-trades — Letzte geschlossene Trades
  /api/toggle-pause  — Copy Trading pausieren/fortsetzen
"""

import logging
import os
from datetime import datetime, timedelta
from fastapi import APIRouter, Request, HTTPException

logger = logging.getLogger(__name__)

from db import get_db
from dash_auth import require_auth, get_current_user
from exchange_client import (
    get_multiple_ticker_prices,
    get_btc_price,
)

router = APIRouter()


# --------------------------------------------------------------------------
# STATIC STATS (aus DB)
# --------------------------------------------------------------------------

@router.get("/stats")
async def get_stats(request: Request):
    user = require_auth(request)
    db = get_db()

    customer_pnl = db.get_customer_pnl(user["customer_id"])
    bot_perf = db.get_bot_performance()

    wins = customer_pnl["wins"]
    losses = customer_pnl["losses"]
    closed = wins + losses + customer_pnl.get("breakeven", 0)

    bot_closed = bot_perf.get("closed_trades", 0)

    return {
        "customer": {
            "total_pnl": customer_pnl["total_pnl"],
            "total_trades": customer_pnl["total_trades"],
            "wins": wins,
            "losses": losses,
            "win_rate": (wins / closed * 100) if closed > 0 else 0,
        },
        "bot": {
            "total_pnl": bot_perf["total_pnl"],
            "total_trades": bot_perf["total_trades"],
            "wins": bot_perf["wins"],
            "losses": bot_perf["losses"],
            "win_rate": (bot_perf["wins"] / bot_closed * 100) if bot_closed > 0 else 0,
            "since": bot_perf.get("first_trade_at"),
        },
        "follower_count": db.get_active_customer_count(),
    }


@router.get("/positions")
async def get_positions(request: Request):
    user = require_auth(request)
    db = get_db()
    mappings = db.get_mappings_for_customer(user["customer_id"])
    for pos in mappings:
        qty = pos.get("customer_qty", 0) or 0
        entry = pos.get("customer_entry_price", 0) or 0
        lev = pos.get("leverage", 0) or 0
        pos["size"] = qty * entry if qty and entry else 0
        pos["margin"] = (qty * entry / lev) if lev > 0 else (qty * entry if qty and entry else 0)
    return {"positions": mappings}


@router.get("/history")
async def get_history(request: Request, page: int = 1, limit: int = 50):
    user = require_auth(request)
    db = get_db()
    offset = (page - 1) * limit
    trades = db.get_closed_trades(user["customer_id"], limit=limit, offset=offset)
    return {"trades": trades, "page": page}


# --------------------------------------------------------------------------
# COPY TRADING PAUSE / RESUME
# --------------------------------------------------------------------------

@router.post("/toggle-pause")
async def toggle_pause(request: Request):
    """Copy Trading pausieren oder fortsetzen."""
    user = require_auth(request)
    db = get_db()
    body = await request.json()
    action = body.get("action")  # "pause" oder "resume"

    # E-Mail + Name fuer Bestaetigungsmail laden
    du = db.get_dashboard_user_by_customer(user["customer_id"])
    onb = db.get_onboarding_status(user["customer_id"])
    email = du.get("email", "") if du else ""
    first_name = onb.get("first_name", "Trader") if onb else "Trader"

    if action == "pause":
        db._conn.execute(
            "UPDATE customers SET is_active = 0 WHERE id = ?",
            (user["customer_id"],)
        )
        db._conn.commit()
        if email:
            from email_service import send_pause_email
            send_pause_email(email, first_name)
        return {"success": True, "is_active": False}
    elif action == "resume":
        db._conn.execute(
            "UPDATE customers SET is_active = 1, deactivated_at = NULL WHERE id = ?",
            (user["customer_id"],)
        )
        db._conn.commit()
        if email:
            from email_service import send_resume_email
            send_resume_email(email, first_name)
        return {"success": True, "is_active": True}
    else:
        raise HTTPException(status_code=400, detail="Ungültige Aktion")


# --------------------------------------------------------------------------
# LIVE DATA (von Exchange API)
# --------------------------------------------------------------------------

@router.get("/live")
async def get_live_data(request: Request):
    """
    Live-Daten von der Exchange abfragen:
    - Kunden-Balance (Kontostand)
    - Aktuelle Preise fuer alle offenen Positionen
    - Unrealisierter P&L pro Position
    - Performance-Berechnungen (%, Return)
    - BTC-Preis fuer Benchmark

    Wird vom Frontend alle 10 Sekunden gepollt.
    """
    user = require_auth(request)
    db = get_db()

    # Kunden-Daten laden
    customer = db.get_customer(user["customer_id"])
    if not customer:
        raise HTTPException(status_code=404, detail="Kunde nicht gefunden")

    # Balance: DB-Wert vom Bot, Fallback via WebSocket wenn 0/leer
    balance = float(customer.get("last_known_balance", 0) or 0) or None

    if not balance or balance <= 0:
        read_key = customer.get("read_api_key", "")
        read_secret = customer.get("read_api_secret", "")
        if read_key and read_secret:
            from api_key_validator import check_futures_balance
            bal_result = await check_futures_balance(read_key, read_secret)
            if bal_result.get("balance") and bal_result["balance"] > 0:
                balance = bal_result["balance"]
                # In DB cachen fuer naechste Abfragen
                try:
                    db._conn.execute(
                        "UPDATE customers SET last_known_balance = ?, balance_updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (balance, user["customer_id"])
                    )
                    db._conn.commit()
                except Exception:
                    pass

    # Aktive Mappings aus DB (fuer Symbol-Liste)
    active_mappings = db.get_mappings_for_customer(user["customer_id"])
    symbols = list(set(m["symbol"] for m in active_mappings if m.get("symbol")))

    # Aktuelle Preise LIVE von der Exchange (fuer alle offenen Positionen)
    ticker_prices = {}
    if symbols:
        ticker_prices = get_multiple_ticker_prices(symbols)

    # Positionen mit Live-Daten anreichern
    positions_live = []
    total_unrealised_pnl = 0.0

    for mapping in active_mappings:
        symbol = mapping["symbol"]
        qty = mapping.get("customer_qty", 0) or 0
        entry = mapping.get("customer_entry_price", 0) or 0
        side = mapping.get("side", "Buy")
        lev = mapping.get("leverage", 0) or 0
        sl = mapping.get("stop_loss", 0) or 0
        tp = mapping.get("take_profit", 0) or 0

        current_price = ticker_prices.get(symbol, 0)
        size = qty * entry if qty and entry else 0
        margin = (qty * entry / lev) if lev > 0 else (qty * entry if qty and entry else 0)

        # Unrealisierten P&L berechnen
        unrealised_pnl = 0.0
        pnl_percent = 0.0
        price_change_pct = 0.0

        if current_price > 0 and entry > 0 and qty > 0:
            if side == "Buy":
                unrealised_pnl = (current_price - entry) * qty
            else:
                unrealised_pnl = (entry - current_price) * qty
            if margin > 0:
                pnl_percent = (unrealised_pnl / margin) * 100
            price_change_pct = ((current_price - entry) / entry) * 100

        total_unrealised_pnl += unrealised_pnl

        positions_live.append({
            "master_position_id": mapping["master_position_id"],
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "entry_price": entry,
            "current_price": current_price,
            "price_change_pct": round(price_change_pct, 2),
            "size": round(size, 2),
            "margin": round(margin, 2),
            "leverage": lev,
            "stop_loss": sl,
            "take_profit": tp,
            "unrealised_pnl": round(unrealised_pnl, 2),
            "pnl_percent": round(pnl_percent, 2),
        })

    # Performance-Berechnungen
    customer_pnl = db.get_customer_pnl(user["customer_id"])
    total_realised_pnl = customer_pnl["total_pnl"]
    total_pnl_incl_open = total_realised_pnl + total_unrealised_pnl

    # Startkapital schaetzen: aktuelle Balance - gesamter PnL (realisiert + unrealisiert)
    starting_balance = (balance - total_pnl_incl_open) if balance else None
    total_return_pct = (total_pnl_incl_open / starting_balance * 100) if starting_balance and starting_balance > 0 else None
    realised_return_pct = (total_realised_pnl / starting_balance * 100) if starting_balance and starting_balance > 0 else None

    # Tages-PnL (Trades die heute geschlossen wurden)
    today_pnl = db.get_today_pnl(user["customer_id"]) if hasattr(db, "get_today_pnl") else None

    # Bot-Performance fuer Master-Return (inkl. unrealisiertem P&L)
    bot_perf = db.get_bot_performance()
    master_balance = db.get_master_balance()

    # Fallback: Master-Balance live via WebSocket wenn DB-Wert 0/stale
    if not master_balance or master_balance <= 0:
        master_read_key = os.getenv("LEVEX_API_KEY", "")
        master_read_secret = os.getenv("LEVEX_API_SECRET", "")
        if master_read_key and master_read_secret:
            from api_key_validator import check_futures_balance
            master_bal = await check_futures_balance(master_read_key, master_read_secret)
            if master_bal.get("balance") and master_bal["balance"] > 0:
                master_balance = master_bal["balance"]
                try:
                    db.set_state("master_balance", str(master_balance))
                except Exception:
                    pass

    master_realised_pnl = bot_perf["total_pnl"]

    # Master unrealisierten P&L aus gespeicherten Positionen berechnen
    master_unrealised_pnl = 0.0
    master_positions = db.get_master_positions()
    for mp in master_positions:
        mark = mp.get("mark", 0)
        entry = mp.get("entry", 0)
        size = mp.get("size", 0)
        side = mp.get("side", "Buy")
        # Mark-Preis aktualisieren falls Ticker-Daten neuer sind
        sym = mp.get("symbol", "")
        if sym in ticker_prices and ticker_prices[sym] > 0:
            mark = ticker_prices[sym]
        if mark > 0 and entry > 0 and size > 0:
            if side == "Buy":
                master_unrealised_pnl += (mark - entry) * size
            else:
                master_unrealised_pnl += (entry - mark) * size

    master_total_pnl = master_realised_pnl + master_unrealised_pnl
    master_starting = master_balance - master_total_pnl if master_balance > 0 else 0
    master_return_pct = (master_total_pnl / master_starting * 100) if master_starting > 0 else None

    # Kunden-Stats (Trefferquote, Trades)
    cust_wins = customer_pnl["wins"]
    cust_losses = customer_pnl["losses"]
    cust_closed = cust_wins + cust_losses + customer_pnl.get("breakeven", 0)
    cust_win_rate = (cust_wins / cust_closed * 100) if cust_closed > 0 else 0

    # Master YTD (inkl. unrealisiertem P&L)
    now = datetime.now()
    ytd_start = datetime(now.year, 1, 1).strftime("%Y-%m-%d")
    master_ytd_curve = db.get_master_daily_pnl_curve(ytd_start)
    master_ytd_pnl = (master_ytd_curve[-1]["cumulative_pnl"] if master_ytd_curve else 0) + master_unrealised_pnl
    master_ytd_pct = (master_ytd_pnl / master_starting * 100) if master_starting > 0 else None

    # Max Drawdown (Gesamt-Laufzeit Master)
    all_time_curve = db.get_master_daily_pnl_curve("2000-01-01")
    max_dd_pct = 0.0
    peak_equity = master_starting if master_starting > 0 else 0
    for point in all_time_curve:
        equity = master_starting + point["cumulative_pnl"]
        if equity > peak_equity:
            peak_equity = equity
        if peak_equity > 0:
            dd = (peak_equity - equity) / peak_equity * 100
            if dd > max_dd_pct:
                max_dd_pct = dd

    # Sync-Stats
    sync_stats = db.get_sync_stats(user["customer_id"])

    # BTC-Preis + 30-Tage Benchmark
    btc_price = get_btc_price()
    btc_benchmark_pct = None

    if btc_price and btc_price > 0:
        # Heutigen BTC-Preis speichern
        today_str = datetime.now().strftime("%Y-%m-%d")
        db.set_state(f"btc_price:{today_str}", str(btc_price))

        # 30-Tage alten Preis laden
        date_30d_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        # Suche den naechsten verfuegbaren Preis (falls genau 30 Tage nicht existiert)
        btc_old = None
        for offset in range(0, 7):  # bis zu 7 Tage Toleranz
            check_date = (datetime.now() - timedelta(days=30 + offset)).strftime("%Y-%m-%d")
            val = db.get_state(f"btc_price:{check_date}")
            if val:
                try:
                    btc_old = float(val)
                    break
                except (ValueError, TypeError):
                    pass

        if btc_old and btc_old > 0:
            btc_benchmark_pct = round((btc_price - btc_old) / btc_old * 100, 2)

    return {
        "balance": round(balance + total_unrealised_pnl, 2) if balance else None,
        "wallet_balance": round(balance, 2) if balance else None,
        "starting_balance": round(starting_balance, 2) if starting_balance else None,
        "total_return_pct": round(total_return_pct, 2) if total_return_pct else None,
        "realised_return_pct": round(realised_return_pct, 2) if realised_return_pct else None,
        "total_pnl": round(total_pnl_incl_open, 2),
        "total_realised_pnl": round(total_realised_pnl, 2),
        "total_unrealised_pnl": round(total_unrealised_pnl, 2),
        "today_pnl": round(today_pnl, 2) if today_pnl is not None else None,
        "positions": positions_live,
        "ticker_prices": ticker_prices,
        "btc_price": btc_price,
        "btc_benchmark_pct": btc_benchmark_pct,
        "bot": {
            "total_pnl": round(master_total_pnl, 2),
            "return_pct": round(master_return_pct, 2) if master_return_pct is not None else None,
            "ytd_pct": round(master_ytd_pct, 2) if master_ytd_pct is not None else None,
            "max_drawdown_pct": round(max_dd_pct, 2),
        },
        "customer": {
            "total_trades": customer_pnl["total_trades"],
            "wins": cust_wins,
            "losses": cust_losses,
            "win_rate": round(cust_win_rate, 1),
        },
        "follower_count": db.get_active_customer_count(),
        "sync": {
            "accuracy": sync_stats["sync_accuracy"],
            "avg_latency_ms": sync_stats["avg_latency_ms"],
        },
    }


# --------------------------------------------------------------------------
# LIVE FEED (Trade-Aktivitaet)
# --------------------------------------------------------------------------

@router.get("/feed")
async def get_feed(request: Request, limit: int = 6):
    """
    Letzte Trade-Aktivitaeten fuer den Live Feed.
    Zeigt: Trade eroeffnet, geschlossen, Scale-In/Out.
    """
    user = require_auth(request)
    db = get_db()

    rows = db._conn.execute("""
        SELECT action, symbol, side, qty, price, pnl, created_at
        FROM trade_history
        WHERE customer_id = ?
        ORDER BY created_at DESC
        LIMIT ?
    """, (user["customer_id"], limit)).fetchall()

    events = []
    for r in rows:
        action = r["action"]
        action_labels = {
            "OPEN": "Trade eröffnet",
            "CLOSE": "Geschlossen",
            "SCALE_IN": "Position erweitert",
            "SCALE_OUT": "Teilweise geschlossen",
        }
        label = action_labels.get(action, action)
        pnl = float(r["pnl"] or 0)

        events.append({
            "action": action,
            "label": label,
            "symbol": r["symbol"],
            "side": r["side"],
            "qty": r["qty"],
            "price": float(r["price"] or 0),
            "pnl": round(pnl, 2),
            "created_at": r["created_at"],
        })

    return {"events": events}


# --------------------------------------------------------------------------
# LETZTE TRADES (geschlossene Trades fuer Sidebar)
# --------------------------------------------------------------------------

@router.get("/recent-trades")
async def get_recent_trades(request: Request, limit: int = 6):
    """
    Letzte geschlossene Trades mit PnL und Prozent.
    """
    user = require_auth(request)
    db = get_db()

    trades = db.get_closed_trades(user["customer_id"], limit=limit)
    result = []
    for t in trades:
        pnl = t.get("pnl", 0) or 0
        avg_entry = t.get("avg_entry", 0) or 0
        total_qty = t.get("total_qty", 0) or 0
        lev = t.get("leverage", 0) or 0
        position_size = avg_entry * total_qty
        margin = (position_size / lev) if lev > 0 else position_size
        pnl_pct = round(pnl / margin * 100, 2) if margin > 0 else 0

        # Dauer berechnen
        duration = "—"
        if t.get("opened_at") and t.get("closed_at"):
            try:
                fmt = "%Y-%m-%d %H:%M:%S"
                t_open = datetime.strptime(t["opened_at"][:19], fmt)
                t_close = datetime.strptime(t["closed_at"][:19], fmt)
                delta = t_close - t_open
                total_seconds = int(delta.total_seconds())
                if total_seconds >= 0:
                    days = total_seconds // 86400
                    hours = (total_seconds % 86400) // 3600
                    minutes = (total_seconds % 3600) // 60
                    if days > 0:
                        duration = f"{days}d {hours}h"
                    elif hours > 0:
                        duration = f"{hours}h {minutes} Min."
                    else:
                        duration = f"{minutes} Min."
            except Exception:
                pass

        result.append({
            "symbol": t["symbol"],
            "side": t["side"],
            "pnl": round(pnl, 2),
            "pnl_pct": pnl_pct,
            "closed_at": t.get("closed_at", "")[:10] if t.get("closed_at") else "",
            "duration": duration,
        })

    return {"trades": result}


# --------------------------------------------------------------------------
# EQUITY CURVE (fuer Charts)
# --------------------------------------------------------------------------

@router.get("/equity")
async def get_equity_curve(request: Request, period: str = "1M"):
    """
    Equity-Kurve aus Trade-Historie berechnen.

    Aggregiert PnL-Summen und baut kumulative Kurven mit Dollar + Prozent.
    Perioden: 1T (stuendlich), 1W, 1M, 3M, YTD, All (taeglich)

    Response pro Datenpunkt: {date, daily_pnl, cumulative_pnl, cumulative_pct}
    """
    user = require_auth(request)
    db = get_db()

    # Zeitraum bestimmen
    now = datetime.now()
    period_map = {
        "1T": timedelta(days=0),  # Heute = 0 Tage zurueck
        "1W": timedelta(weeks=1),
        "1M": timedelta(days=30),
        "3M": timedelta(days=90),
        "YTD": now - datetime(now.year, 1, 1),
        "All": timedelta(days=3650),
    }
    delta = period_map.get(period, timedelta(days=30))
    start_date = (now - delta).strftime("%Y-%m-%d")

    # Resolution: stuendlich fuer 1T, taeglich fuer alles andere
    is_hourly = (period == "1T")

    if is_hourly:
        customer_curve = db.get_hourly_pnl_curve(user["customer_id"], start_date)
        master_curve = db.get_master_hourly_pnl_curve(start_date)
    else:
        customer_curve = db.get_daily_pnl_curve(user["customer_id"], start_date)
        master_curve = db.get_master_daily_pnl_curve(start_date)

    # Starting Balances fuer %-Berechnung ermitteln
    customer = db.get_customer(user["customer_id"])
    customer_balance = float(customer.get("last_known_balance", 0) or 0) if customer else 0
    customer_pnl = db.get_customer_pnl(user["customer_id"])
    customer_total_pnl = customer_pnl["total_pnl"]
    master_balance = db.get_master_balance()
    bot_perf = db.get_bot_performance()
    master_total_pnl = bot_perf["total_pnl"]

    # Unrealisierten P&L berechnen und als Live-Datenpunkt anhaengen
    # --- Kunden unrealisierter P&L ---
    active_mappings = db.get_mappings_for_customer(user["customer_id"])
    customer_unrealised = 0.0
    for m in active_mappings:
        mark = m.get("last_mark_price", 0) or 0
        entry = m.get("customer_entry_price", 0) or 0
        qty = m.get("customer_qty", 0) or 0
        side = m.get("side", "Buy")
        if mark > 0 and entry > 0 and qty > 0:
            if side == "Buy":
                customer_unrealised += (mark - entry) * qty
            else:
                customer_unrealised += (entry - mark) * qty

    # --- Master unrealisierter P&L ---
    master_positions = db.get_master_positions()
    master_unrealised = 0.0
    for mp in master_positions:
        mark = mp.get("mark", 0)
        entry = mp.get("entry", 0)
        size = mp.get("size", 0)
        side = mp.get("side", "Buy")
        if mark > 0 and entry > 0 and size > 0:
            if side == "Buy":
                master_unrealised += (mark - entry) * size
            else:
                master_unrealised += (entry - mark) * size

    # Starting Balances korrigieren (inkl. unrealisiertem P&L)
    customer_total_pnl_incl = customer_total_pnl + customer_unrealised
    master_total_pnl_incl = master_total_pnl + master_unrealised
    customer_starting = customer_balance - customer_total_pnl_incl if customer_balance > 0 else 0
    master_starting = master_balance - master_total_pnl_incl if master_balance > 0 else 0

    # Prozent-Werte zu jedem Datenpunkt hinzufuegen
    for point in customer_curve:
        if customer_starting > 0:
            point["cumulative_pct"] = round(point["cumulative_pnl"] / customer_starting * 100, 4)
        else:
            point["cumulative_pct"] = 0

    for point in master_curve:
        if master_starting > 0:
            point["cumulative_pct"] = round(point["cumulative_pnl"] / master_starting * 100, 4)
        else:
            point["cumulative_pct"] = 0

    # Live-Datenpunkt mit unrealisiertem P&L anhaengen
    now_str = now.strftime("%Y-%m-%d %H:%M" if is_hourly else "%Y-%m-%d")
    last_cust_cum = customer_curve[-1]["cumulative_pnl"] if customer_curve else 0
    last_master_cum = master_curve[-1]["cumulative_pnl"] if master_curve else 0

    live_cust_cum = last_cust_cum + customer_unrealised
    live_master_cum = last_master_cum + master_unrealised

    customer_curve.append({
        "date": now_str,
        "daily_pnl": round(customer_unrealised, 4),
        "cumulative_pnl": round(live_cust_cum, 4),
        "cumulative_pct": round(live_cust_cum / customer_starting * 100, 4) if customer_starting > 0 else 0,
    })
    master_curve.append({
        "date": now_str,
        "daily_pnl": round(master_unrealised, 4),
        "cumulative_pnl": round(live_master_cum, 4),
        "cumulative_pct": round(live_master_cum / master_starting * 100, 4) if master_starting > 0 else 0,
    })

    logger.warning(
        f"Equity {period} ({'hourly' if is_hourly else 'daily'}): "
        f"Customer {len(customer_curve)} pts (start={customer_starting:.2f}$), "
        f"Master {len(master_curve)} pts (start={master_starting:.2f}$)"
    )

    return {
        "period": period,
        "resolution": "hourly" if is_hourly else "daily",
        "customer": customer_curve,
        "master": master_curve,
        "starting_balances": {
            "customer": round(customer_starting, 2),
            "master": round(master_starting, 2),
        },
    }


# --------------------------------------------------------------------------
# SETUP — API Key Validierung
# --------------------------------------------------------------------------

@router.post("/setup/validate-key")
async def validate_key(request: Request):
    """API Key gegen Levex validieren (Setup Schritt 3)."""
    # Copy-Trading-Setup (Phase 2) seit 2026-10-29 geschlossen
    raise HTTPException(status_code=410, detail="Copy Trading Setup ist geschlossen")
    user = get_current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Nicht eingeloggt")

    body = await request.json()
    api_key = body.get("api_key", "").strip()
    api_secret = body.get("api_secret", "").strip()

    from api_key_validator import validate_api_key
    result = await validate_api_key(api_key, api_secret)
    return result


# --------------------------------------------------------------------------
# INTERNAL — Telefonnummer-Lookup per E-Mail (fuer Automationen / Make)
# Auth: Header  X-Internal-Token: <INTERNAL_API_TOKEN>
# --------------------------------------------------------------------------

@router.get("/internal/phone")
async def internal_phone_lookup(request: Request, email: str = ""):
    """Gibt die Telefonnummer eines Users anhand der E-Mail zurueck.

    Geschuetzt durch einen Secret-Token (Env: INTERNAL_API_TOKEN).
    Aufruf:
      GET /api/internal/phone?email=kunde@example.com
      Header: X-Internal-Token: <token>
    """
    expected = os.environ.get("INTERNAL_API_TOKEN", "")
    provided = request.headers.get("X-Internal-Token", "")

    # Token muss gesetzt UND korrekt sein (konstante Pruefung)
    import hmac
    if not expected or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")

    email = (email or "").strip().lower()
    if not email:
        raise HTTPException(status_code=400, detail="email fehlt")

    db = get_db()
    user = db.get_dashboard_user_by_email(email)
    if not user:
        raise HTTPException(status_code=404, detail="not found")

    return {
        "email": email,
        "phone": user.get("phone") or None,
        "first_name": (user.get("customer_name") or "").split(" ")[0] or None,
        "product_tier": user.get("product_tier"),
        "found": True,
    }


# --------------------------------------------------------------------------
# INTERNAL — Zugangsstatus aller Kunden fuer den naechtlichen Sync nach Server 1
# Auth: Header  X-Internal-Token: <INTERNAL_SYNC_TOKEN>  (eigener Token, nur lesend)
# --------------------------------------------------------------------------

@router.get("/internal/access-status")
async def internal_access_status(request: Request):
    """Server 2 ist einzige Wahrheit fuer: aktiv ja/nein, Tier, Entzugsdatum.

    aktiv   = payment_status 'paid' UND nicht per Kick/Chargeback deaktiviert
              (is_active=0 allein ist die Selbst-Pause, zaehlt nicht).
    entzug  = naechster offener Termin in scheduled_access_revocations,
              sonst (wenn inaktiv) das Deaktivierungsdatum.
    """
    expected = os.environ.get("INTERNAL_SYNC_TOKEN", "")
    provided = request.headers.get("X-Internal-Token", "")

    import hmac
    if not expected or not hmac.compare_digest(provided, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")

    db = get_db()
    rows = db._conn.execute("""
        SELECT du.id, lower(trim(du.email)) AS email, du.product_tier, du.payment_status,
               du.ablefy_order_id, du.telegram_chat_id, c.is_active, c.deactivated_at,
               (SELECT min(r.revoke_at) FROM scheduled_access_revocations r
                 WHERE r.status = 'pending'
                   AND (r.dashboard_user_id = du.id OR lower(r.email) = lower(du.email))) AS revoke_pending
        FROM dashboard_users du
        JOIN customers c ON c.id = du.customer_id
        ORDER BY du.id
    """).fetchall()

    users = []
    for r in rows:
        r = dict(r)
        deaktiviert = r["is_active"] == 0 and r["deactivated_at"] is not None
        aktiv = r["payment_status"] == "paid" and not deaktiviert
        entzug = r["revoke_pending"] or (None if aktiv else r["deactivated_at"])
        users.append({
            "id": r["id"],
            "email": r["email"],
            "aktiv": aktiv,
            "tier": r["product_tier"],
            "payment_status": r["payment_status"],
            "entzug": entzug[:10] if entzug else None,
            "ablefy_order_id": r["ablefy_order_id"] or None,
            "telegram_id": r["telegram_chat_id"] or None,
        })

    return {"generated_at": datetime.utcnow().isoformat() + "Z", "count": len(users), "users": users}
