"""
(C) welcome_routes.py — Payment-First Onboarding Flow

Neuer Flow: Landingpage → Ablefy Checkout → /welcome?email={email} → /welcome/done → Dashboard

Payment passiert VOR Account-Erstellung. Ablefy Webhook speichert Zahlung in
pending_payments. User kommt mit E-Mail auf /welcome, setzt Passwort + UID,
Account wird erstellt und Payment claimed in einem Schritt.
"""

import os
import uuid
import logging
from datetime import datetime

from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates

from db import get_db
from dash_auth import hash_password, create_session, get_current_user, SESSION_COOKIE, verify_csrf
from email_service import send_welcome_email_signals, send_marketing_doi_email, send_verification_email, generate_token, send_async
from telegram_invites import create_paid_invite

logger = logging.getLogger("welcome")

router = APIRouter()
templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "..", "templates"))


# ==========================================================================
# GET /welcome — Account-Erstellung nach Zahlung
# ==========================================================================

@router.get("/welcome")
async def welcome_page(request: Request, email: str = "", payer_email: str = ""):
    """Zeigt Formular fuer Account-Erstellung nach erfolgreicher Ablefy-Zahlung."""
    email = (email or payer_email).strip().lower()

    if not email:
        return templates.TemplateResponse(request, "welcome.html", {
            "error": "Kein offener Kauf gefunden. Bitte starte den Kauf über die Produktseite.",
            "email": "",
            "tier": "",
        })

    db = get_db()

    # Bereits registriert?
    existing = db.get_dashboard_user_by_email(email)
    if existing:
        return RedirectResponse(url="/login")

    # Pending Payment suchen
    pp = db._conn.execute(
        "SELECT * FROM pending_payments WHERE email = ? AND claimed_at IS NULL",
        (email,),
    ).fetchone()

    tier = pp["product_tier"] if pp else "paid_signals"

    return templates.TemplateResponse(request, "welcome.html", {
        "error": None,
        "email": email,
        "tier": tier,
    })


# ==========================================================================
# POST /welcome — Account erstellen + Payment claimen
# ==========================================================================

@router.post("/welcome")
async def welcome_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    phone: str = Form(""),
    levex_uid: str = Form(""),
    accept_agb: str = Form(None),
    accept_privacy: str = Form(None),
    accept_risk: str = Form(None),
    accept_marketing: str = Form(None),
    csrf_token: str = Form(""),
):
    email = email.strip().lower()
    ctx = {
        "error": None,
        "email": email,
        "tier": "",
    }

    # CSRF
    if not verify_csrf(request, csrf_token):
        ctx["error"] = "Sicherheitsfehler. Bitte lade die Seite neu."
        return templates.TemplateResponse(request, "welcome.html", ctx)

    db = get_db()

    # Pending Payment re-validieren
    pp = db._conn.execute(
        "SELECT * FROM pending_payments WHERE email = ? AND claimed_at IS NULL",
        (email,),
    ).fetchone()

    if not pp:
        ctx["error"] = "Kein offener Kauf gefunden. Bitte starte den Kauf über die Produktseite."
        ctx["payment_found"] = False
        return templates.TemplateResponse(request, "welcome.html", ctx)

    tier = pp["product_tier"] or "paid_signals"
    ctx["tier"] = tier

    # Bereits registriert?
    existing = db.get_dashboard_user_by_email(email)
    if existing:
        return RedirectResponse(url="/login", status_code=303)

    # Passwort validieren
    if len(password) < 8:
        ctx["error"] = "Passwort muss mindestens 8 Zeichen lang sein."
        return templates.TemplateResponse(request, "welcome.html", ctx)

    if password != password_confirm:
        ctx["error"] = "Passwörter stimmen nicht überein."
        return templates.TemplateResponse(request, "welcome.html", ctx)

    # Pflicht-Checkboxen
    if not all([accept_agb, accept_privacy, accept_risk]):
        ctx["error"] = "Bitte akzeptiere die AGB, Datenschutzerklärung und den Risikohinweis."
        return templates.TemplateResponse(request, "welcome.html", ctx)

    # Telefonnummer (Pflichtfeld)
    phone_clean = phone.strip()
    if not phone_clean or len(phone_clean) < 6:
        ctx["error"] = "Bitte gib eine gültige Telefonnummer an."
        return templates.TemplateResponse(request, "welcome.html", ctx)

    # UID-Verifizierung entfernt (2026-06-26): Kunden zahlen monatlich und bekommen
    # direkt Zugriff — keine LeveX-UID-Pruefung mehr noetig.
    uid = levex_uid.strip()  # bleibt optional, falls Feld noch befuellt wird

    # --- Account erstellen ---
    customer_id = str(uuid.uuid4())
    first_name = pp["first_name"] or ""
    last_name = pp["last_name"] or ""
    now_iso = datetime.utcnow().isoformat()

    db.register_customer(
        customer_id=customer_id,
        first_name=first_name,
        last_name=last_name,
        email=email,
        password_hash=hash_password(password),
    )

    # Product Tier + Payment Status + Ablefy-Felder (email_verified = 0 → muss per DOI bestätigt werden)
    verification_token = generate_token()
    from datetime import timedelta
    verification_expires = (datetime.utcnow() + timedelta(hours=48)).isoformat()
    db._conn.execute("""
        UPDATE dashboard_users SET
            product_tier = ?,
            payment_status = 'paid',
            ablefy_order_id = ?,
            ablefy_product_id = ?,
            paid_amount = ?,
            paid_at = ?,
            email_verified = 0,
            verification_token = ?,
            verification_expires = ?
        WHERE customer_id = ?
    """, (tier, pp["ablefy_order_id"], pp["ablefy_product_id"],
          pp["amount"], now_iso, verification_token, verification_expires, customer_id))

    # Consent-Tracking (DSGVO) + Telefonnummer
    db._conn.execute("""
        UPDATE dashboard_users SET
            accepted_agb_at = ?, accepted_privacy_at = ?, accepted_risk_at = ?,
            accepted_marketing = ?, accepted_marketing_at = ?,
            phone = ?
        WHERE customer_id = ?
    """, (now_iso, now_iso, now_iso,
          1 if accept_marketing else 0,
          now_iso if accept_marketing else None,
          phone_clean,
          customer_id))

    # Marketing-Einwilligung: Wird durch die allgemeine E-Mail-Verifikation abgedeckt (DOI).
    # Wenn User Marketing-Checkbox gesetzt hat UND E-Mail verifiziert → marketing_optin_verified wird
    # automatisch mit-gesetzt im verify-email Endpoint.

    # UID speichern (wenn vorhanden)
    if uid:
        db._conn.execute(
            "UPDATE customers SET uid = ? WHERE id = ?",
            (uid, customer_id),
        )

    # Pending Payment claimen
    db._conn.execute(
        "UPDATE pending_payments SET claimed_at = ? WHERE email = ? AND claimed_at IS NULL",
        (now_iso, email),
    )

    db._conn.commit()

    # Onboarding-Status auf active setzen
    db.set_onboarding_status(customer_id, "active")

    # Telegram Invite-Link wird LAZY in /welcome/done generiert (nicht hier im POST).
    # Das haelt den Account-Erstellungs-Request schlank und verteilt die Telegram-
    # API-Calls zeitlich (User muss erst die E-Mail bestaetigen) — kein Burst gegen
    # das Telegram-Rate-Limit bei vielen gleichzeitigen Kaeufen.

    # Session erstellen + einloggen
    session_token = create_session(customer_id)

    # Verifikationsmail NON-BLOCKING senden (Hintergrund-Thread) — blockiert die
    # Event-Loop nicht, Response geht sofort raus.
    display_name = first_name or "Trader"
    send_async(send_verification_email, email, display_name, verification_token, tier=tier)

    # Redirect zu /verify-pending (User muss erst E-Mail bestätigen)
    response = RedirectResponse(url="/verify-pending", status_code=303)
    response.set_cookie(
        SESSION_COOKIE, session_token,
        max_age=7 * 24 * 3600,
        httponly=True,
        samesite="strict",
        secure=True,
    )
    return response


# ==========================================================================
# GET /welcome/done — Erfolgsseite mit Telegram-Link
# ==========================================================================

@router.get("/welcome/done")
async def welcome_done(request: Request):
    """Erfolgsseite nach Account-Erstellung: Telegram-Link + Dashboard-Button."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")

    db = get_db()
    du = db.get_dashboard_user_by_customer(user["customer_id"])

    telegram_link = du.get("telegram_invite_link", "") if du else ""
    tier = du.get("product_tier", "paid_signals") if du else "paid_signals"
    first_name = user.get("customer_name", "").split(" ")[0] or "Trader"

    # Telegram-Invite LAZY generieren falls noch nicht vorhanden (erst hier, nicht
    # im Account-POST → verteilt die Telegram-Calls, kein Burst). Robust: schlaegt
    # die Generierung fehl, bleibt der Link leer und der Nutzer kann es neu laden.
    if not telegram_link or telegram_link == "#":
        try:
            customer_name = user.get("customer_name", "").strip() or "Trader"
            invite_link = await create_paid_invite(customer_name)
            if invite_link:
                db._conn.execute(
                    "UPDATE dashboard_users SET telegram_invite_link = ? WHERE customer_id = ?",
                    (invite_link, user["customer_id"]),
                )
                db._conn.commit()
                telegram_link = invite_link
        except Exception as e:
            logger.warning(f"[WELCOME] Telegram-Invite konnte nicht generiert werden: {e}")
    if not telegram_link:
        telegram_link = "#"

    return templates.TemplateResponse(request, "welcome_done.html", {
        "telegram_link": telegram_link,
        "tier": tier,
        "first_name": first_name,
    })


