"""
(C) auth_routes.py — Login, Logout, Registrierung, Invite-Aktivierung, Setup, E-Mail-Verifizierung, Passwort-Reset
"""

import os
import uuid
from datetime import datetime, timedelta
from fastapi import APIRouter, Request, Form, Response
from fastapi.responses import RedirectResponse, HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from db import get_db
from dash_auth import hash_password, verify_password, create_session, get_current_user, SESSION_COOKIE, verify_csrf
from email_service import generate_token, send_verification_email, send_welcome_email, send_welcome_email_signals, send_password_reset_email, send_async
from telegram_invites import create_paid_invite
import logging
auth_logger = logging.getLogger("auth")

router = APIRouter()

# Copy-Trading-Einstieg (Phase 2) — seit 2026-10-29 aus (Entscheidung Max).
# Aus = /signup/copytrading und /setup/copytrading leiten um, keine Key-Eingabe moeglich.
COPYTRADING_SETUP_ENABLED = False


def _copytrading_closed(request: Request) -> RedirectResponse:
    """Copy-Trading-Einstieg geschlossen: Eingeloggte zurueck auf ihren alten Tier
    (/cancel-upgrade setzt Tier + Onboarding zurueck, keine Redirect-Schleife), sonst Login."""
    if get_current_user(request):
        return RedirectResponse(url="/cancel-upgrade", status_code=303)
    return RedirectResponse(url="/login", status_code=303)


templates = Jinja2Templates(directory=os.path.join(os.path.dirname(__file__), "..", "templates"))


def _setup_url_for_tier(customer_id: str) -> str:
    """Gibt die naechste URL im Onboarding-Flow passend zum Status zurueck."""
    db = get_db()
    du = db.get_dashboard_user_by_customer(customer_id)
    # Nicht bezahlt → /welcome mit E-Mail (Payment-First Flow)
    if not du or du.get("payment_status") != "paid":
        email = du.get("email", "") if du else ""
        if email:
            return f"/welcome?email={email}"
        return "/login"
    tier = db.get_dashboard_user_product_tier(customer_id)
    if tier == "paid_signals":
        return "/welcome/done"
    return "/setup/copytrading"


def _redirect_by_status(status: str, customer_id: str | None = None) -> RedirectResponse:
    """Redirect basierend auf Onboarding-Status + Product-Tier."""
    if status in ("registered", "paid", "setup_pending"):
        if customer_id:
            return RedirectResponse(url=_setup_url_for_tier(customer_id))
        return RedirectResponse(url="/login")
    else:
        return RedirectResponse(url="/dashboard")


@router.get("/login")
async def login_page(request: Request):
    user = get_current_user(request)
    if user:
        # Pruefen ob Onboarding abgeschlossen
        db = get_db()
        onb = db.get_onboarding_status(user["customer_id"])
        if onb and onb.get("onboarding_status") not in ("active", None):
            return _redirect_by_status(onb["onboarding_status"], user["customer_id"])
        return RedirectResponse(url="/dashboard")
    return templates.TemplateResponse(request, "login.html", {"error": None, "success": None})


@router.post("/login")
async def login(request: Request, email: str = Form(...), password: str = Form(...), csrf_token: str = Form("")):
    # CSRF-Check
    if not verify_csrf(request, csrf_token):
        return templates.TemplateResponse(request, "login.html", {
            "error": "Sicherheitsfehler. Bitte lade die Seite neu.", "success": None,
        })

    db = get_db()

    # User anhand Email finden
    user = db.get_dashboard_user_by_email(email)
    if not user or not user.get("password_hash"):
        return templates.TemplateResponse(request, "login.html", {
            "error": "E-Mail nicht gefunden oder kein Zugang.", "success": None,
        })

    if not verify_password(password, user["password_hash"]):
        return templates.TemplateResponse(request, "login.html", {
            "error": "Falsches Passwort.", "success": None,
        })

    # Session erstellen
    token = create_session(user["customer_id"])

    # E-Mail-Verifizierung prüfen
    if not user.get("email_verified"):
        redirect_url = "/verify-pending"
    else:
        # Redirect basierend auf Onboarding-Status + Tier
        onb = db.get_onboarding_status(user["customer_id"])
        if onb and onb.get("onboarding_status") not in ("active", None):
            redirect_url = _setup_url_for_tier(user["customer_id"])
        else:
            redirect_url = "/dashboard"

    response = RedirectResponse(url=redirect_url, status_code=303)
    response.set_cookie(
        SESSION_COOKIE, token,
        max_age=7 * 24 * 3600,
        httponly=True,
        samesite="strict",
        secure=True,
    )
    return response


@router.post("/logout")
async def logout(request: Request):
    user = get_current_user(request)
    if user:
        db = get_db()
        db.clear_session(user["customer_id"])
    response = RedirectResponse(url="/login", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response


@router.get("/invite/{token}")
async def invite_page(request: Request, token: str):
    db = get_db()
    invite = db.get_invite(token)

    if not invite:
        return templates.TemplateResponse(request, "login.html", {
            "error": "Einladungslink ungültig oder abgelaufen."
        })

    if invite["is_activated"]:
        return templates.TemplateResponse(request, "login.html", {
            "error": "Dieser Einladungslink wurde bereits verwendet. Bitte einloggen."
        })

    return templates.TemplateResponse(request, "invite.html", {
        "token": token,
        "customer_name": invite["customer_name"],
        "error": None,
    })


@router.post("/invite/{token}")
async def activate_invite(
    request: Request,
    token: str,
    email: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
):
    db = get_db()
    invite = db.get_invite(token)

    if not invite or invite["is_activated"]:
        return templates.TemplateResponse(request, "login.html", {
            "error": "Einladungslink ungültig."
        })

    if len(password) < 8:
        return templates.TemplateResponse(request, "invite.html", {
            "token": token,
            "customer_name": invite["customer_name"],
            "error": "Passwort muss mindestens 8 Zeichen lang sein.",
        })

    if password != password_confirm:
        return templates.TemplateResponse(request, "invite.html", {
            "token": token,
            "customer_name": invite["customer_name"],
            "error": "Passwörter stimmen nicht überein.",
        })

    # Pruefen ob Email schon vergeben
    existing = db.get_dashboard_user_by_email(email)
    if existing:
        return templates.TemplateResponse(request, "invite.html", {
            "token": token,
            "customer_name": invite["customer_name"],
            "error": "Diese E-Mail wird bereits verwendet.",
        })

    # Passwort + Email setzen + aktivieren
    db.activate_invite(token, hash_password(password), email)

    # Automatisch einloggen
    session_token = create_session(invite["customer_id"])
    response = RedirectResponse(url="/dashboard", status_code=303)
    response.set_cookie(
        SESSION_COOKIE, session_token,
        max_age=7 * 24 * 3600,
        httponly=True,
        samesite="strict",
        secure=True,
    )
    return response


# ==========================================================================
# SELF-SERVICE REGISTRIERUNG
# ==========================================================================

@router.get("/signup/copytrading")
async def register_page(request: Request):
    if not COPYTRADING_SETUP_ENABLED:
        return _copytrading_closed(request)
    user = get_current_user(request)
    if user:
        db = get_db()
        tier = db.get_dashboard_user_product_tier(user["customer_id"])
        onb = db.get_onboarding_status(user["customer_id"])
        setup_done = onb and onb.get("onboarding_status") == "active"
        # Bereits copy_trading → zurueck zum Dashboard
        if setup_done and tier == "copy_trading":
            return RedirectResponse(url="/dashboard")
        # Upgrade: Vorherigen Tier speichern, dann wechseln
        if tier != "copy_trading":
            if setup_done:
                db._conn.execute(
                    "UPDATE dashboard_users SET previous_tier = ? WHERE customer_id = ?",
                    (tier, user["customer_id"]))
                db._conn.commit()
            db.set_product_tier(user["customer_id"], "copy_trading")
        # Onboarding auf setup_pending setzen damit Copy Trading Setup durchlaufen wird
        db.set_onboarding_status(user["customer_id"], "setup_pending")
        db.set_onboarding_step(user["customer_id"], 1)
        return RedirectResponse(url="/setup/copytrading")
    return templates.TemplateResponse(request, "register.html", {
        "error": None, "first_name": "", "last_name": "", "email": "",
    })



@router.post("/signup/copytrading")
async def register(
    request: Request,
    first_name: str = Form(...),
    last_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    accept_agb: str = Form(None),
    accept_privacy: str = Form(None),
    accept_risk: str = Form(None),
    accept_marketing: str = Form(None),
    csrf_token: str = Form(""),
):
    if not COPYTRADING_SETUP_ENABLED:
        return _copytrading_closed(request)
    db = get_db()
    ctx = {"first_name": first_name, "last_name": last_name, "email": email}

    # CSRF-Check
    if not verify_csrf(request, csrf_token):
        return templates.TemplateResponse(request, "register.html", {
            **ctx, "error": "Sicherheitsfehler. Bitte lade die Seite neu.",
        })

    # Pflicht-Checkboxen prüfen
    if not accept_agb or not accept_privacy or not accept_risk:
        return templates.TemplateResponse(request, "register.html", {
            **ctx, "error": "Bitte akzeptiere die AGB, Datenschutzerklärung und den Risikohinweis.",
        })

    # Validierung
    if len(first_name.strip()) < 2 or len(last_name.strip()) < 2:
        return templates.TemplateResponse(request, "register.html", {
            **ctx, "error": "Bitte Vor- und Nachname eingeben.",
        })

    if len(password) < 8:
        return templates.TemplateResponse(request, "register.html", {
            **ctx, "error": "Passwort muss mindestens 8 Zeichen lang sein.",
        })

    if password != password_confirm:
        return templates.TemplateResponse(request, "register.html", {
            **ctx, "error": "Passwörter stimmen nicht überein.",
        })

    # Email-Check
    existing = db.get_dashboard_user_by_email(email)
    if existing:
        return templates.TemplateResponse(request, "register.html", {
            **ctx, "error": "Diese E-Mail wird bereits verwendet.",
        })

    # Kunden + Dashboard-User erstellen
    customer_id = str(uuid.uuid4())
    db.register_customer(
        customer_id=customer_id,
        first_name=first_name.strip(),
        last_name=last_name.strip(),
        email=email.strip().lower(),
        password_hash=hash_password(password),
    )

    # Consent-Daten speichern (DSGVO Nachweispflicht)
    now_iso = datetime.utcnow().isoformat()
    marketing = 1 if accept_marketing else 0
    db._conn.execute(
        """UPDATE dashboard_users SET
            accepted_agb_at = ?, accepted_privacy_at = ?, accepted_risk_at = ?,
            accepted_marketing = ?, accepted_marketing_at = ?
        WHERE email = ?""",
        (now_iso, now_iso, now_iso, marketing, now_iso if marketing else None, email.strip().lower()),
    )

    # Verifizierungs-Token generieren + speichern
    token = generate_token()
    expires = (datetime.utcnow() + timedelta(hours=24)).isoformat()
    db._conn.execute(
        "UPDATE dashboard_users SET verification_token = ?, verification_expires = ?, email_verified = 0 WHERE email = ?",
        (token, expires, email.strip().lower()),
    )
    db._conn.commit()

    # Verifizierungsmail senden (non-blocking)
    send_async(send_verification_email, email.strip().lower(), first_name.strip(), token, tier="copy_trading")

    # Automatisch einloggen (aber noch nicht verifiziert → wird beim Login/Setup geprüft)
    session_token = create_session(customer_id)
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
# E-MAIL VERIFIZIERUNG
# ==========================================================================

@router.get("/verify-pending")
async def verify_pending_page(request: Request):
    """Seite die nach Registrierung angezeigt wird: 'Bitte E-Mail bestätigen'."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")

    db = get_db()
    du = db.get_dashboard_user_by_customer(user["customer_id"])
    if du and du.get("email_verified"):
        return RedirectResponse(url=_setup_url_for_tier(user["customer_id"]))

    email = du.get("email", "") if du else ""
    return templates.TemplateResponse(request, "verify-pending.html", {
        "email": email,
    })


@router.get("/verify-email")
async def verify_email(request: Request, token: str = ""):
    """E-Mail-Verifizierung via Link aus der Mail."""
    if not token:
        return templates.TemplateResponse(request, "login.html", {
            "error": "Ungültiger Verifizierungslink.",
        })

    db = get_db()
    row = db._conn.execute(
        "SELECT customer_id, verification_expires FROM dashboard_users WHERE verification_token = ?",
        (token,),
    ).fetchone()

    if not row:
        return templates.TemplateResponse(request, "login.html", {
            "error": "Verifizierungslink ungültig oder bereits verwendet.",
        })

    # Ablauf prüfen
    expires = row["verification_expires"]
    if expires and datetime.utcnow() > datetime.fromisoformat(expires):
        return templates.TemplateResponse(request, "login.html", {
            "error": "Verifizierungslink abgelaufen. Bitte registriere dich erneut oder fordere einen neuen Link an.",
        })

    # Verifizieren + Marketing-DOI mit-bestätigen (wenn Checkbox gesetzt war)
    now_iso = datetime.utcnow().isoformat()
    db._conn.execute(
        """UPDATE dashboard_users SET
            email_verified = 1,
            verification_token = NULL,
            verification_expires = NULL,
            marketing_optin_verified = CASE WHEN accepted_marketing = 1 THEN 1 ELSE 0 END,
            marketing_optin_verified_at = CASE WHEN accepted_marketing = 1 THEN ? ELSE NULL END,
            marketing_optin_token = NULL
        WHERE verification_token = ?""",
        (now_iso, token),
    )
    db._conn.commit()

    customer_id = row["customer_id"]

    # Willkommensmail senden (jetzt nach Verifikation, nicht bei Account-Erstellung)
    du = db.get_dashboard_user_by_customer(customer_id)
    if du:
        email = du.get("email", "")
        onb = db.get_onboarding_status(customer_id)
        display_name = onb.get("first_name", "Trader") if onb else "Trader"
        # Telegram-Invite HIER generieren (nach E-Mail-Verifikation = zeitlich verteilt,
        # kein Burst beim Kauf) — und VOR der Willkommens-Mail, damit die Mail den echten
        # Link enthaelt (nicht "#"). /welcome/done liest ihn dann nur noch aus der DB.
        telegram_link = du.get("telegram_invite_link", "") or ""
        if not telegram_link or telegram_link == "#":
            try:
                invite_name = (du.get("customer_name", "") or display_name).strip() or "Trader"
                invite_link = await create_paid_invite(invite_name)
                if invite_link:
                    db._conn.execute(
                        "UPDATE dashboard_users SET telegram_invite_link = ? WHERE customer_id = ?",
                        (invite_link, customer_id),
                    )
                    db._conn.commit()
                    telegram_link = invite_link
            except Exception as e:
                auth_logger.warning(f"[VERIFY] Telegram-Invite konnte nicht generiert werden: {e}")
        if not telegram_link:
            telegram_link = "#"
        send_async(send_welcome_email_signals, email, display_name, telegram_link=telegram_link)

    # Einloggen + zu /welcome/done (Telegram-Link + Dashboard)
    session_token = create_session(customer_id)
    response = RedirectResponse(url="/welcome/done", status_code=303)
    response.set_cookie(
        SESSION_COOKIE, session_token,
        max_age=7 * 24 * 3600,
        httponly=True,
        samesite="lax",
        secure=True,
    )
    return response


@router.post("/resend-verification")
async def resend_verification(request: Request):
    """Verifizierungsmail erneut senden."""
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")

    db = get_db()
    du = db.get_dashboard_user_by_customer(user["customer_id"])
    if not du or du.get("email_verified"):
        return RedirectResponse(url=_setup_url_for_tier(user["customer_id"]))

    # Neuen Token generieren
    token = generate_token()
    expires = (datetime.utcnow() + timedelta(hours=24)).isoformat()
    db._conn.execute(
        "UPDATE dashboard_users SET verification_token = ?, verification_expires = ? WHERE customer_id = ?",
        (token, expires, user["customer_id"]),
    )
    db._conn.commit()

    email = du.get("email", "")
    onb = db.get_onboarding_status(user["customer_id"])
    first_name = onb.get("first_name", "Trader") if onb else "Trader"
    tier = db.get_dashboard_user_product_tier(user["customer_id"])
    send_async(send_verification_email, email, first_name, token, tier=tier)

    return templates.TemplateResponse(request, "verify-pending.html", {
        "email": email,
        "resent": True,
    })


# ==========================================================================
# MARKETING DOUBLE OPT-IN
# ==========================================================================

@router.get("/confirm-marketing")
async def confirm_marketing(request: Request, token: str = ""):
    """Marketing Double-Opt-In: Bestaetigt die Marketing-Einwilligung via Link aus der DOI-Mail."""
    if not token:
        return templates.TemplateResponse(request, "login.html", {
            "error": "Ungültiger Link.", "email": "",
        })

    db = get_db()
    row = db._conn.execute(
        "SELECT customer_id FROM dashboard_users WHERE marketing_optin_token = ?",
        (token,),
    ).fetchone()

    if not row:
        return templates.TemplateResponse(request, "login.html", {
            "error": "Marketing-Link ungültig oder bereits bestätigt.", "email": "",
        })

    now_iso = datetime.utcnow().isoformat()
    db._conn.execute(
        "UPDATE dashboard_users SET marketing_optin_verified = 1, marketing_optin_verified_at = ?, marketing_optin_token = NULL WHERE marketing_optin_token = ?",
        (now_iso, token),
    )
    db._conn.commit()

    logger.info(f"[MARKETING-DOI] Bestätigt für customer_id={row['customer_id']}")

    # Redirect zum Dashboard mit Erfolgsmeldung
    return RedirectResponse(url="/dashboard?marketing_confirmed=1")


# ==========================================================================
# PASSWORT VERGESSEN / RESET
# ==========================================================================

@router.get("/forgot-password")
async def forgot_password_page(request: Request):
    return templates.TemplateResponse(request, "forgot-password.html", {
        "error": None, "success": None,
    })


@router.post("/forgot-password")
async def forgot_password(request: Request, email: str = Form(...), csrf_token: str = Form("")):
    if not verify_csrf(request, csrf_token):
        return templates.TemplateResponse(request, "forgot-password.html", {
            "error": "Sicherheitsfehler. Bitte lade die Seite neu.", "success": None,
        })
    db = get_db()
    du = db.get_dashboard_user_by_email(email.strip().lower())

    # Immer Erfolg zeigen (verhindert E-Mail-Enumeration)
    if du:
        token = generate_token()
        expires = (datetime.utcnow() + timedelta(hours=1)).isoformat()
        db._conn.execute(
            "UPDATE dashboard_users SET reset_token = ?, reset_expires = ? WHERE email = ?",
            (token, expires, email.strip().lower()),
        )
        db._conn.commit()

        onb = db.get_onboarding_status(du["customer_id"])
        first_name = onb.get("first_name", "Trader") if onb else "Trader"
        send_async(send_password_reset_email, email.strip().lower(), first_name, token)

    return templates.TemplateResponse(request, "forgot-password.html", {
        "error": None,
        "success": "Falls ein Account mit dieser E-Mail existiert, erhältst du in Kürze eine E-Mail mit einem Reset-Link.",
    })


@router.get("/reset-password")
async def reset_password_page(request: Request, token: str = ""):
    if not token:
        return RedirectResponse(url="/forgot-password")

    db = get_db()
    row = db._conn.execute(
        "SELECT customer_id, reset_expires FROM dashboard_users WHERE reset_token = ?",
        (token,),
    ).fetchone()

    if not row:
        return templates.TemplateResponse(request, "forgot-password.html", {
            "error": "Reset-Link ungültig oder bereits verwendet.",
            "success": None,
        })

    expires = row["reset_expires"]
    if expires and datetime.utcnow() > datetime.fromisoformat(expires):
        return templates.TemplateResponse(request, "forgot-password.html", {
            "error": "Reset-Link abgelaufen. Bitte fordere einen neuen an.",
            "success": None,
        })

    return templates.TemplateResponse(request, "reset-password.html", {
        "token": token, "error": None,
    })


@router.post("/reset-password")
async def reset_password(
    request: Request,
    token: str = Form(...),
    password: str = Form(...),
    password_confirm: str = Form(...),
    csrf_token: str = Form(""),
):
    if not verify_csrf(request, csrf_token):
        return templates.TemplateResponse(request, "reset-password.html", {
            "token": token, "error": "Sicherheitsfehler. Bitte lade die Seite neu.",
        })

    db = get_db()
    row = db._conn.execute(
        "SELECT customer_id, reset_expires FROM dashboard_users WHERE reset_token = ?",
        (token,),
    ).fetchone()

    if not row:
        return templates.TemplateResponse(request, "forgot-password.html", {
            "error": "Reset-Link ungültig.", "success": None,
        })

    expires = row["reset_expires"]
    if expires and datetime.utcnow() > datetime.fromisoformat(expires):
        return templates.TemplateResponse(request, "forgot-password.html", {
            "error": "Reset-Link abgelaufen.", "success": None,
        })

    if len(password) < 8:
        return templates.TemplateResponse(request, "reset-password.html", {
            "token": token, "error": "Passwort muss mindestens 8 Zeichen lang sein.",
        })

    if password != password_confirm:
        return templates.TemplateResponse(request, "reset-password.html", {
            "token": token, "error": "Passwörter stimmen nicht überein.",
        })

    # Passwort setzen + Token löschen + alle Sessions invalidieren
    customer_id = row["customer_id"]
    db._conn.execute(
        "UPDATE dashboard_users SET password_hash = ?, reset_token = NULL, reset_expires = NULL WHERE reset_token = ?",
        (hash_password(password), token),
    )
    db._conn.execute(
        "UPDATE dashboard_users SET session_token = NULL WHERE customer_id = ?",
        (customer_id,),
    )
    db._conn.commit()

    return templates.TemplateResponse(request, "login.html", {
        "error": None,
        "success": "Passwort erfolgreich geändert. Du kannst dich jetzt einloggen.",
    })


# ==========================================================================
# GUIDED SETUP
# ==========================================================================

@router.get("/setup/copytrading")
async def setup_page(request: Request, step: int | None = None):
    if not COPYTRADING_SETUP_ENABLED:
        return _copytrading_closed(request)
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/signup/copytrading")

    # E-Mail-Verifizierung prüfen
    db = get_db()
    du = db.get_dashboard_user_by_customer(user["customer_id"])
    if du and not du.get("email_verified"):
        return RedirectResponse(url="/verify-pending")

    # Bezahlung prüfen — Setup erst nach Zahlung
    if not du or du.get("payment_status") != "paid":
        return RedirectResponse(url="/payment")

    onb = db.get_onboarding_status(user["customer_id"])
    if not onb:
        return RedirectResponse(url="/login")

    # Wenn schon aktiv -> Dashboard
    if onb["onboarding_status"] == "active":
        return RedirectResponse(url="/dashboard")

    db_step = max(onb.get("onboarding_step", 0), 1)
    # Erlaube Zurück-Navigation per Query-Param (aber nicht weiter als DB-Step)
    if step is not None and 1 <= step <= db_step:
        show_step = step
    else:
        show_step = db_step
    first_name = onb.get("first_name") or onb.get("name", "").split(" ")[0] or "Trader"

    # Upgrade-Modus? (User kann abbrechen)
    is_upgrade = bool(du and du.get("previous_tier"))

    return templates.TemplateResponse(request, "setup.html", {
        "step": show_step,
        "first_name": first_name,
        "error": None,
        "success": None,
        "is_upgrade": is_upgrade,
    })


@router.post("/setup/copytrading")
async def setup_action(request: Request):
    if not COPYTRADING_SETUP_ENABLED:
        return _copytrading_closed(request)
    user = get_current_user(request)
    if not user:
        return RedirectResponse(url="/login")

    db = get_db()

    # Bezahlung prüfen
    du = db.get_dashboard_user_by_customer(user["customer_id"])
    if not du or du.get("payment_status") != "paid":
        return RedirectResponse(url="/payment")

    form = await request.form()
    action = form.get("action", "")
    onb = db.get_onboarding_status(user["customer_id"])
    first_name = onb.get("first_name") or onb.get("name", "").split(" ")[0] or "Trader"

    if action == "go_back":
        current_step = onb.get("onboarding_step", 1) if onb else 1
        new_step = max(current_step - 1, 1)
        return RedirectResponse(url=f"/setup/copytrading?step={new_step}", status_code=303)

    elif action == "complete_step_1":
        db.set_onboarding_step(user["customer_id"], 2)
        db.set_onboarding_status(user["customer_id"], "setup_pending")
        return RedirectResponse(url="/setup/copytrading?step=2", status_code=303)

    elif action == "complete_step_2":
        db.set_onboarding_step(user["customer_id"], 3)
        return RedirectResponse(url="/setup/copytrading?step=3", status_code=303)

    elif action == "complete_step_3":
        api_key = form.get("api_key", "").strip()
        api_secret = form.get("api_secret", "").strip()
        read_api_key = form.get("read_api_key", "").strip()
        read_api_secret = form.get("read_api_secret", "").strip()

        if not api_key or not api_secret:
            return templates.TemplateResponse(request, "setup.html", {
                "step": 3, "first_name": first_name,
                "error": "Bitte Copy Trading API Key und Secret eingeben.",
                "success": None,
            })

        if not read_api_key or not read_api_secret:
            return templates.TemplateResponse(request, "setup.html", {
                "step": 3, "first_name": first_name,
                "error": "Bitte Futures Read API Key und Secret eingeben.",
                "success": None,
            })

        # Copy Trading Key validieren
        from api_key_validator import validate_api_key
        result = await validate_api_key(api_key, api_secret)

        if not result["valid"]:
            return templates.TemplateResponse(request, "setup.html", {
                "step": 3, "first_name": first_name,
                "error": "Copy Trading Key: " + result["error"],
                "success": None,
            })

        # Balance prüfen über Read API Key (via WebSocket)
        from api_key_validator import check_futures_balance
        balance_result = await check_futures_balance(read_api_key, read_api_secret)

        if balance_result["balance"] is None:
            return templates.TemplateResponse(request, "setup.html", {
                "step": 3, "first_name": first_name,
                "error": "Futures Read Key: " + balance_result["error"],
                "success": None,
            })

        min_deposit = float(os.getenv("MIN_DEPOSIT_USDT", "1000"))
        if balance_result["balance"] < min_deposit:
            return templates.TemplateResponse(request, "setup.html", {
                "step": 3, "first_name": first_name,
                "error": f"Dein Futures-Guthaben beträgt aktuell {balance_result['balance']:.2f} USDT. Bitte zahle mindestens {min_deposit:,.0f} USDT ein, bevor du das Setup abschließt.",
                "success": None,
            })

        # Setup abschliessen
        db.complete_setup(
            customer_id=user["customer_id"],
            uid=result["uid"],
            api_key=api_key,
            api_secret=api_secret,
            read_api_key=read_api_key,
            read_api_secret=read_api_secret,
        )

        # previous_tier leeren (Upgrade abgeschlossen)
        db._conn.execute(
            "UPDATE dashboard_users SET previous_tier = NULL WHERE customer_id = ?",
            (user["customer_id"],))
        db._conn.commit()

        # Willkommensmail senden
        du = db.get_dashboard_user_by_customer(user["customer_id"])
        if du and du.get("email"):
            send_async(send_welcome_email, du["email"], first_name)

        return RedirectResponse(url="/dashboard?welcome=1", status_code=303)

    return RedirectResponse(url="/setup/copytrading", status_code=303)
