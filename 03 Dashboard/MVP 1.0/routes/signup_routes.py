"""
(C) signup_routes.py — Legacy Onboarding Redirects

Der alte Flow (Signup → Verify → Payment → Setup) wurde durch den
Payment-First Flow ersetzt (/welcome). Alle alten URLs leiten um,
damit bestehende Links nicht brechen.

Neuer Flow: Landingpage → Ablefy Checkout → /welcome?email={email} → /welcome/done → Dashboard
"""

import os
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from db import get_db
from dash_auth import get_current_user

router = APIRouter()

# Ablefy Checkout-URLs (werden auch von welcome_routes importiert)
ABLEFY_CHECKOUT_SIGNALS = "https://myablefy.com/s/first-class-trading/firstclass-copytrading-signale-4bd1353c/payment"
ABLEFY_CHECKOUT_COPYTRADING = "https://myablefy.com/s/first-class-trading/firstclass-copy-trading-copytrading-2e12ab5f/payment"


# ==========================================================================
# LEGACY REDIRECTS — Alte URLs → neue Ziele
# ==========================================================================

# /signup/signals → Ablefy Checkout (oder Landingpage)
@router.get("/signup/signals")
async def signup_signals_redirect(request: Request):
    return RedirectResponse(url=ABLEFY_CHECKOUT_SIGNALS)

@router.post("/signup/signals")
async def signup_signals_post_redirect(request: Request):
    return RedirectResponse(url=ABLEFY_CHECKOUT_SIGNALS, status_code=303)

# /signup/free → Ablefy Checkout
@router.get("/signup/free")
async def signup_free_redirect(request: Request):
    return RedirectResponse(url=ABLEFY_CHECKOUT_SIGNALS)

@router.get("/setup/free")
async def setup_free_redirect(request: Request):
    return RedirectResponse(url="/dashboard")

@router.get("/signup/free/done")
async def signup_free_done_redirect(request: Request):
    return RedirectResponse(url="/dashboard")

# /payment → Login (nicht mehr noetig)
@router.get("/payment")
async def payment_redirect(request: Request):
    return RedirectResponse(url="/login")

# /payment/success → /welcome/done (wenn eingeloggt) oder /login
@router.get("/payment/success")
async def payment_success_redirect(request: Request):
    user = get_current_user(request)
    if user:
        return RedirectResponse(url="/welcome/done")
    return RedirectResponse(url="/login")

# /setup/premium → /dashboard (wenn aktiv) oder /welcome
@router.get("/setup/premium")
async def setup_premium_redirect(request: Request):
    user = get_current_user(request)
    if user:
        db = get_db()
        onb = db.get_onboarding_status(user["customer_id"])
        if onb and onb.get("onboarding_status") == "active":
            return RedirectResponse(url="/dashboard")
        # Nicht aktiv → eventuell neuen Flow nutzen
        du = db.get_dashboard_user_by_customer(user["customer_id"])
        email = du.get("email", "") if du else ""
        if email:
            return RedirectResponse(url=f"/welcome?email={email}")
    return RedirectResponse(url="/login")

@router.post("/setup/premium")
async def setup_premium_post_redirect(request: Request):
    return RedirectResponse(url="/login", status_code=303)

# /api/payment-status → Legacy Polling Endpoint (wird nicht mehr gebraucht)
@router.get("/api/payment-status")
async def payment_status_legacy(request: Request):
    from fastapi.responses import JSONResponse
    return JSONResponse({"payment_status": "deprecated", "message": "Use /api/welcome/check-payment instead"})
