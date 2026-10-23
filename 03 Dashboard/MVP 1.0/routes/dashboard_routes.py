"""
(C) dashboard_routes.py — Dashboard-Seiten (HTML) — MVP 2.0
"""

import os
import locale
from datetime import datetime, timedelta
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from db import get_db

# Deutsche Wochentage/Monate
_WOCHENTAGE = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]
_MONATE = ["", "Januar", "Februar", "März", "April", "Mai", "Juni",
           "Juli", "August", "September", "Oktober", "November", "Dezember"]


def _heute_formatiert() -> tuple[int, str]:
    """Gibt (stunde, 'Dienstag, 12. Mai 2026') zurück."""
    now = datetime.now()
    tag = _WOCHENTAGE[now.weekday()]
    monat = _MONATE[now.month]
    return now.hour, f"{tag}, {now.day}. {monat} {now.year}"
from dash_auth import get_current_user


def _format_duration(opened_at: str, closed_at: str) -> str:
    """Haltedauer als lesbaren String formatieren, z.B. '4h 22 Min.' oder '2d 14h'."""
    try:
        fmt = "%Y-%m-%d %H:%M:%S"
        t_open = datetime.strptime(opened_at[:19], fmt)
        t_close = datetime.strptime(closed_at[:19], fmt)
        delta = t_close - t_open
        total_seconds = int(delta.total_seconds())
        if total_seconds < 0:
            return "—"
        days = total_seconds // 86400
        hours = (total_seconds % 86400) // 3600
        minutes = (total_seconds % 3600) // 60
        if days > 0:
            return f"{days}d {hours}h"
        elif hours > 0:
            return f"{hours}h {minutes} Min."
        else:
            return f"{minutes} Min."
    except Exception:
        return "—"


def _enrich_trades_with_duration(trades: list[dict]) -> list[dict]:
    """Haltedauer und PnL-Prozent zu jedem Trade hinzufuegen."""
    for t in trades:
        if t.get("opened_at") and t.get("closed_at"):
            t["duration"] = _format_duration(t["opened_at"], t["closed_at"])
        else:
            t["duration"] = "—"
        # PnL-Prozent berechnen (basierend auf Positionsgroesse)
        pnl = t.get("pnl", 0) or 0
        avg_entry = t.get("avg_entry", 0) or 0
        total_qty = t.get("total_qty", 0) or 0
        position_size = avg_entry * total_qty
        t["pnl_pct"] = round(pnl / position_size * 100, 2) if position_size > 0 else 0
    return trades

router = APIRouter()
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "..", "templates"))


def _get_product_tier(user) -> str:
    """Product-Tier des Users holen."""
    db = get_db()
    return db.get_dashboard_user_product_tier(user["customer_id"])


def _base_context(user, active_page: str) -> dict:
    """Gemeinsamer Kontext fuer alle authentifizierten Seiten."""
    db = get_db()
    active_mappings = db.get_mappings_for_customer(user["customer_id"])
    product_tier = _get_product_tier(user)
    return {
        "user": user,
        "active_page": active_page,
        "active_positions_count": len(active_mappings),
        "product_tier": product_tier,
    }


def _check_onboarding(user) -> RedirectResponse | None:
    """Prueft ob der Kunde das Onboarding abgeschlossen hat. Redirect wenn nicht."""
    db = get_db()
    onb = db.get_onboarding_status(user["customer_id"])
    if onb and onb.get("onboarding_status") not in ("active", None):
        # Tier-spezifischer Setup-Redirect
        tier = _get_product_tier(user)
        if tier == "paid_signals":
            return RedirectResponse(url="/setup/premium")
        return RedirectResponse(url="/setup/copytrading")
    return None


@router.get("/cancel-upgrade")
async def cancel_upgrade(request: Request):
    """Upgrade abbrechen — Tier und Onboarding auf vorherigen Stand zuruecksetzen."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")
    db = get_db()
    du = db.get_dashboard_user_by_customer(user["customer_id"])
    previous_tier = du.get("previous_tier") if du else None
    if previous_tier:
        db.set_product_tier(user["customer_id"], previous_tier)
        db.set_onboarding_status(user["customer_id"], "active")
        db._conn.execute(
            "UPDATE dashboard_users SET previous_tier = NULL WHERE customer_id = ?",
            (user["customer_id"],))
        db._conn.commit()
    else:
        # Kein vorheriger Tier → einfach Onboarding auf active setzen
        db.set_onboarding_status(user["customer_id"], "active")
    return RedirectResponse(url="/dashboard")


@router.get("/dashboard")
async def dashboard(request: Request, welcome: int = 0):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")

    # Product-Tier Routing
    product_tier = _get_product_tier(user)

    if product_tier == "paid_signals":
        # Onboarding-Check (Affiliate-Verifizierung)
        redirect = _check_onboarding(user)
        if redirect:
            return redirect
        # Paid Signal User: Dashboard Light
        hour, today_formatted = _heute_formatiert()
        db = get_db()
        du = db.get_dashboard_user_by_customer(user["customer_id"])
        telegram_link = du.get("telegram_invite_link", "#") if du else "#"
        ctx = _base_context(user, "dashboard")
        ctx.update({
            "hour": hour,
            "today_formatted": today_formatted,
            "telegram_link": telegram_link or "#",
        })
        return templates.TemplateResponse(request, "dashboard_signals.html", ctx)

    # Copy Trading: Volles Dashboard (bestehend)
    redirect = _check_onboarding(user)
    if redirect:
        return redirect

    db = get_db()

    # Kunden-Performance
    customer_pnl = db.get_customer_pnl(user["customer_id"])
    wins = customer_pnl["wins"]
    losses = customer_pnl["losses"]
    closed = wins + losses + customer_pnl.get("breakeven", 0)
    win_rate = (wins / closed * 100) if closed > 0 else 0

    # Aktive Positionen (mit qty, entry, leverage)
    active_mappings = db.get_mappings_for_customer(user["customer_id"])
    for pos in active_mappings:
        qty = pos.get("customer_qty", 0) or 0
        entry = pos.get("customer_entry_price", 0) or 0
        lev = pos.get("leverage", 0) or 0
        pos["size"] = qty * entry if qty and entry else 0
        pos["margin"] = (qty * entry / lev) if lev > 0 else 0

    # Letzte geschlossene Trades
    closed_trades = _enrich_trades_with_duration(
        db.get_closed_trades(user["customer_id"], limit=10)
    )

    # Bot-Performance (global)
    bot_perf = db.get_bot_performance()
    bot_wins = bot_perf["wins"]
    bot_losses = bot_perf["losses"]
    bot_closed = bot_perf.get("closed_trades", 0)
    bot_win_rate = (bot_wins / bot_closed * 100) if bot_closed > 0 else 0

    hour, today_formatted = _heute_formatiert()

    ctx = {
        "user": user,
        "hour": hour,
        "today_formatted": today_formatted,
        "active_page": "dashboard",
        "active_positions_count": len(active_mappings),
        # Kunden-Performance
        "total_pnl": customer_pnl["total_pnl"],
        "total_trades": customer_pnl["total_trades"],
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        # Aktive Positionen
        "active_positions": active_mappings,
        # Letzte Trades (geschlossen)
        "recent_trades": closed_trades,
        # Bot-Performance
        "bot_pnl": bot_perf["total_pnl"],
        "bot_trades": bot_perf["total_trades"],
        "bot_wins": bot_wins,
        "bot_losses": bot_losses,
        "bot_win_rate": bot_win_rate,
        "bot_since": bot_perf.get("first_trade_at", ""),
        # Follower
        "follower_count": db.get_active_customer_count(),
        "show_welcome_video": welcome == 1,
    }

    return templates.TemplateResponse(request, "dashboard.html", ctx)


@router.get("/verlauf")
async def verlauf(request: Request, page: int = 1):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")
    # Nur fuer Copy Trading User
    tier = _get_product_tier(user)
    if tier != "copy_trading":
        return RedirectResponse(url="/dashboard")
    redirect = _check_onboarding(user)
    if redirect:
        return redirect

    db = get_db()
    limit = 50
    offset = (page - 1) * limit
    trades = _enrich_trades_with_duration(
        db.get_closed_trades(user["customer_id"], limit=limit, offset=offset)
    )
    customer_pnl = db.get_customer_pnl(user["customer_id"])

    ctx = _base_context(user, "verlauf")
    ctx.update({
        "trades": trades,
        "total_pnl": customer_pnl["total_pnl"],
        "page": page,
        "has_next": len(trades) == limit,
    })

    return templates.TemplateResponse(request, "history.html", ctx)


# Legacy route redirect
@router.get("/history")
async def history_redirect(request: Request, page: int = 1):
    return RedirectResponse(url=f"/verlauf?page={page}")


# ============================================================
# STUB PAGES — Sidebar-Navigation (noch nicht implementiert)
# ============================================================

@router.get("/positionen")
async def positionen(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")
    redirect = _check_onboarding(user)
    if redirect:
        return redirect

    ctx = _base_context(user, "positionen")
    ctx.update({
        "page_title": "Positionen",
        "page_icon": "i-layers",
        "page_description": "Hier siehst du bald eine detaillierte Übersicht aller deiner aktiven und vergangenen Positionen. Dieses Feature wird in Kürze freigeschaltet.",
    })
    return templates.TemplateResponse(request, "stub.html", ctx)


@router.get("/live-feed")
async def live_feed(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")
    redirect = _check_onboarding(user)
    if redirect:
        return redirect

    ctx = _base_context(user, "live-feed")
    ctx.update({
        "page_title": "Live Feed",
        "page_icon": "i-activity",
        "page_description": "Der Live Feed zeigt dir in Echtzeit alle Trade-Aktionen des Master Accounts. Dieses Feature wird in Kürze freigeschaltet.",
    })
    return templates.TemplateResponse(request, "stub.html", ctx)


@router.get("/wallet")
async def wallet(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")
    redirect = _check_onboarding(user)
    if redirect:
        return redirect

    ctx = _base_context(user, "wallet")
    ctx.update({
        "page_title": "Wallet",
        "page_icon": "i-wallet",
        "page_description": "Hier verwaltest du deine Wallet-Verbindung und siehst deinen aktuellen Kontostand. Dieses Feature wird in Kürze freigeschaltet.",
    })
    return templates.TemplateResponse(request, "stub.html", ctx)


@router.get("/einstellungen")
async def einstellungen(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")
    redirect = _check_onboarding(user)
    if redirect:
        return redirect

    db = get_db()
    customer = db.get_customer(user["customer_id"])

    # API Key maskieren (nur letzte 4 Zeichen)
    api_key = customer.get("api_key", "") if customer else ""
    api_key_masked = "••••••••" + api_key[-4:] if len(api_key) >= 4 else "—"

    # Balance
    balance = float(customer.get("last_known_balance", 0) or 0) if customer else 0

    # is_active
    is_active = bool(customer.get("is_active", 1)) if customer else False

    # Erstellt am
    created_at = customer.get("created_at", "") if customer else ""
    created_at_formatted = "—"
    if created_at:
        try:
            dt = datetime.strptime(str(created_at)[:10], "%Y-%m-%d")
            created_at_formatted = f"{dt.day}. {_MONATE[dt.month]} {dt.year}"
        except Exception:
            created_at_formatted = str(created_at)[:10]

    ctx = _base_context(user, "einstellungen")
    ctx.update({
        "customer": customer,
        "api_key_masked": api_key_masked,
        "balance": balance,
        "is_active": is_active,
        "created_at_formatted": created_at_formatted,
    })
    return templates.TemplateResponse(request, "settings.html", ctx)


@router.get("/support")
async def support(request: Request):
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")
    redirect = _check_onboarding(user)
    if redirect:
        return redirect

    ctx = _base_context(user, "support")
    return templates.TemplateResponse(request, "support.html", ctx)
