"""
(C) webhook_routes.py — Ablefy Webhook Endpoint

Empfaengt Payment-Events von Ablefy (ehemals elopage) und verarbeitet sie:
- Neue Zahlung → User freischalten / Payment Status setzen
- Abo-Status geaendert → User deaktivieren bei Kuendigung
- Refund → User sperren

Ablefy sendet Webhooks als JSON POST an:
  https://dashboard.firstclass-trading.com/webhooks/ablefy

Produkte:
- 517561 = FirstClass Copytrading (Signale) — 100€/mo
- 517562 = FirstClass Copy Trading (Copytrading) — 500€ Setup + 300€/mo

WICHTIG: Beim ersten echten Webhook den Raw-Payload loggen, damit wir die
exakte Struktur kennen und die Felder korrekt mappen koennen.
"""

import os
import json
import logging
from datetime import datetime

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from db import get_db, is_email_blocked
from email_service import send_payment_confirmed_email_signals, send_payment_confirmed_email_copytrading, send_purchase_setup_email, send_access_restored_email, send_async
from telegram_invites import kick_from_paid_group, create_paid_invite, unban_from_groups, notify_admin

logger = logging.getLogger("webhook")

router = APIRouter()

# Ablefy Produkt-IDs → internes Tier-Mapping
ABLEFY_PRODUCT_MAP = {
    517561: "paid_signals",
    "517561": "paid_signals",
    517562: "copy_trading",
    "517562": "copy_trading",
}

# Ablefy API Secret fuer Webhook-Verifikation (optional, falls Ablefy einen Header mitschickt)
ABLEFY_WEBHOOK_SECRET = os.getenv("ABLEFY_WEBHOOK_SECRET", "")


# ==========================================================================
# WEBHOOK ENDPOINT
# ==========================================================================

@router.post("/webhooks/ablefy")
async def ablefy_webhook(request: Request):
    """
    Empfaengt alle Ablefy Webhook-Events.

    Ablefy schickt verschiedene Events (Payment, Refund, Order State etc.)
    als JSON POST. Wir loggen den vollen Payload und verarbeiten bekannte Events.
    """
    try:
        # Raw Body lesen + loggen (KRITISCH fuer Debugging)
        body = await request.body()
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            logger.warning(f"[WEBHOOK] Ablefy: Kein valides JSON empfangen: {body[:500]}")
            return JSONResponse({"status": "error", "message": "Invalid JSON"}, status_code=400)

        # IMMER den vollen Payload loggen (fuer Debugging der Payload-Struktur)
        logger.info(f"[WEBHOOK] Ablefy Event empfangen: {json.dumps(payload, indent=2, default=str)[:2000]}")

        # Payload in DB speichern (fuer spaetere Analyse)
        _store_webhook_log(payload)

        # Ablefys "Zugang gueltig bis" am User mitschreiben (reine Datenerfassung, keine Aktion)
        _record_access(payload)

        # Event-Typ bestimmen — Ablefy-Payloads variieren je nach Event
        # Moegliche Felder: event, event_type, action, type
        event_type = (
            payload.get("event")
            or payload.get("event_type")
            or payload.get("action")
            or payload.get("type")
            or "unknown"
        )

        payment_state = str(payload.get("payment_state", "") or "")
        payment_method = str(payload.get("payment_method", "") or "").lower()
        logger.info(f"[WEBHOOK] Event-Typ: {event_type} | State: {payment_state} | Method: {payment_method}")

        # 0. Ruecklastschrift / Chargeback (v.a. geplatzte SEPA) → Zugang wieder entziehen.
        #    Kommt als payment_state=payment_chargebacked ODER als chargeback.*-Event.
        if payment_state == "payment_chargebacked" or event_type in ("chargeback", "chargeback.successful", "order.subscription.chargebacked"):
            return await _handle_payment_failed(payload, reason="chargeback")

        # 1. Fehlgeschlagene/abgebrochene Zahlungen → ignorieren (kein Kunde, keine Mail!)
        if payment_state == "payment_not_completed" or event_type in ("payment.error", "order.subscription.not_completed"):
            logger.info(f"[WEBHOOK] Zahlung nicht abgeschlossen ({event_type}/{payment_state}) — ignoriert")
            return JSONResponse({"status": "ok", "message": "payment not completed, ignored"})

        # 2. Refunds / Stornos
        if event_type in ("refund", "refund.created", "new_refund"):
            return await _handle_refund(payload)
        if event_type in ("order_state_update", "order.state_changed", "subscription.cancelled", "subscription_state_changed"):
            return await _handle_order_state(payload)

        # 3. Realer, aktiver Kunde? — SEPA-sicher (Kernfix):
        #    Karte → payment.successful (Geld sofort da)
        #    SEPA  → payment.pending mit payment_state=active_subscription (Zugang sofort aktiv,
        #            Geld kommt erst 2-3 Tage spaeter mit payment.successful). Wer nur auf
        #            payment.successful triggert, laesst jeden SEPA-Erstkaeufer im Dunkeln.
        is_real_payment = (
            event_type in ("payment", "payment.created", "payment.successful", "initial_payment", "new_payment", "order.one_time.paid")
            or (payment_state == "active_subscription"
                and event_type in ("payment.pending", "payer.access.changed", "order.subscription.paying", "order.subscription.pending")
                and _access_type(payload) != "REVOKE")
            # SEPA-Erstkauf: Ablefy feuert payment.pending/order.subscription.pending mit
            # payment_state=payment_pending (OHNE active_subscription). Geld kommt erst in 2-3 Tagen.
            # Sofort freischalten (Option A) -- eine spaetere Ruecklastschrift (chargeback, oben) sperrt wieder.
            or (payment_state == "payment_pending" and payment_method == "sepa"
                and event_type in ("payment.pending", "order.subscription.pending"))
        )
        if is_real_payment:
            return await _handle_payment(payload)

        # 4. Alles andere (order.* Vor-Events etc.) → loggen, keine Aktion
        logger.info(f"[WEBHOOK] Event '{event_type}' (state={payment_state}) — keine Aktion noetig")
        return JSONResponse({"status": "ok", "message": f"Event '{event_type}' logged but not processed"})

    except Exception as e:
        logger.error(f"[WEBHOOK] Ablefy Webhook Fehler: {e}", exc_info=True)
        # Immer 200 zurueckgeben — sonst retry'd Ablefy endlos
        return JSONResponse({"status": "error", "message": str(e)})


# ==========================================================================
# EVENT HANDLER
# ==========================================================================

async def _handle_payment(payload: dict) -> JSONResponse:
    """
    Neue Zahlung empfangen.

    Versucht den Kunden per E-Mail zu matchen und den Payment-Status zu setzen.
    """
    db = get_db()

    # E-Mail und Produkt-ID aus Payload extrahieren
    # Ablefy-Felder koennen variieren — wir probieren mehrere Pfade
    email = _extract_email(payload)
    product_id = _extract_product_id(payload)
    order_id = _extract_order_id(payload)
    amount = _extract_amount(payload)

    logger.info(
        f"[WEBHOOK] Payment | Email: {email} | Product: {product_id} | "
        f"Order: {order_id} | Amount: {amount}"
    )

    first_name, last_name = _extract_name(payload)

    if not email:
        logger.warning("[WEBHOOK] Payment ohne E-Mail — kann User nicht zuordnen")
        return JSONResponse({"status": "ok", "message": "No email found, logged"})

    # Tier bestimmen — NUR unsere beiden Produkte verarbeiten
    tier = ABLEFY_PRODUCT_MAP.get(product_id, ABLEFY_PRODUCT_MAP.get(str(product_id), ""))
    if not tier:
        logger.info(f"[WEBHOOK] Payment fuer unbekanntes Produkt '{product_id}' — ignoriert (kein Copy Trading Produkt)")
        return JSONResponse({"status": "ok", "message": f"Product '{product_id}' not managed by this system"})

    # BLOCKLIST — dauerhaft gesperrte E-Mail: NICHT onboarden, keine Vormerkung, keine Mail
    if is_email_blocked(db, email):
        logger.warning(f"[WEBHOOK] [BLOCKLIST] Zahlung fuer gesperrte E-Mail {email} — ignoriert (kein Onboarding)")
        return JSONResponse({"status": "ok", "message": "Email blocklisted"})

    # User per E-Mail finden (inkl. gmail.com <-> googlemail.com, gleiche Mailbox)
    user = _find_user(db, email.lower().strip())

    email_norm = email.lower().strip()
    if user:
        # Bestehender User — Payment Status updaten
        customer_id = user["customer_id"]
        # War der Kunde vorher draussen (gekuendigt/gekickt/gesperrt)? Dann holen wir ihn nach der Zahlung
        # automatisch zurueck (Entbannung + neuer Einmal-Link + Mail). Regel Max 2026-09-11: wer zahlt, ist drin.
        _row = db._conn.execute("SELECT is_active FROM customers WHERE id = ?", (customer_id,)).fetchone()
        was_inactive = _row is not None and not _row["is_active"]
        # Idempotenz: gleicher Order schon als bezahlt verbucht? → keine erneute Mail (Events feuern mehrfach)
        already = (user.get("payment_status") == "paid"
                   and str(user.get("ablefy_order_id") or "") == str(order_id or ""))
        _update_payment_status(db, customer_id, "paid", order_id, product_id, amount)
        if tier:
            db.set_product_tier(customer_id, tier)

        reactivated = False
        if was_inactive:
            reactivated = await _reactivate_user(db, user, email_norm, order_id, first_name)

        if not already and not reactivated:
            fn = user.get("first_name") or user.get("customer_name", "").split(" ")[0] or "Trader"
            if tier == "paid_signals":
                send_async(send_payment_confirmed_email_signals, email, fn)
            elif tier == "copy_trading":
                send_async(send_payment_confirmed_email_copytrading, email, fn)
        logger.info(f"[WEBHOOK] Payment (bestehender User): {email} → {tier} | Mail: {'nein/schon verbucht' if already else 'ja'} | Reaktiviert: {'ja' if reactivated else 'nein'}")
    else:
        # Kein User — Payment vormerken. Idempotenz: schon vorgemerkt? → keine zweite Setup-Mail.
        existing = db._conn.execute(
            "SELECT claimed_at FROM pending_payments WHERE email = ?", (email_norm,)
        ).fetchone()
        _store_pending_payment(db, email_norm, order_id, product_id, tier, amount, first_name, last_name)
        if existing is None:
            send_async(send_purchase_setup_email, email_norm, first_name)
            logger.info(f"[WEBHOOK] Payment vorgemerkt (NEU) + Setup-Mail: {email} → {tier}")
        else:
            logger.info(f"[WEBHOOK] Vormerkung schon vorhanden — aktualisiert, keine zweite Mail: {email}")

    return JSONResponse({"status": "ok", "message": "Payment processed"})


async def _handle_refund(payload: dict) -> JSONResponse:
    """Refund empfangen — User sperren (nur fuer unsere Produkte)."""
    db = get_db()
    email = _extract_email(payload)
    product_id = _extract_product_id(payload)
    order_id = _extract_order_id(payload)

    # Nur unsere Produkte verarbeiten
    tier = ABLEFY_PRODUCT_MAP.get(product_id, ABLEFY_PRODUCT_MAP.get(str(product_id), ""))
    if not tier:
        logger.info(f"[WEBHOOK] Refund fuer unbekanntes Produkt '{product_id}' — ignoriert")
        return JSONResponse({"status": "ok", "message": "Product not managed by this system"})

    logger.info(f"[WEBHOOK] Refund | Email: {email} | Order: {order_id} | Product: {product_id}")

    if email:
        user = db.get_dashboard_user_by_email(email.lower().strip())
        if user:
            _update_payment_status(db, user["customer_id"], "refunded", order_id)
            # User deaktivieren
            db._conn.execute(
                "UPDATE customers SET is_active = 0, deactivated_at = ? WHERE id = ?",
                (datetime.utcnow().isoformat(), user["customer_id"]),
            )
            db._conn.commit()
            logger.info(f"[WEBHOOK] User deaktiviert nach Refund: {email}")

            # Telegram Auto-Kick
            telegram_id = user.get("telegram_chat_id", "")
            if telegram_id:
                kicked = await kick_from_paid_group(telegram_id)
                if kicked:
                    logger.info(f"[WEBHOOK] User aus Telegram-Gruppe gekickt: {email}")
                else:
                    logger.warning(f"[WEBHOOK] Telegram-Kick fehlgeschlagen: {email}")

    return JSONResponse({"status": "ok", "message": "Refund processed"})


async def _handle_order_state(payload: dict) -> JSONResponse:
    """Order-Status geaendert — bei Kuendigung User deaktivieren (nur fuer unsere Produkte)."""
    db = get_db()
    email = _extract_email(payload)
    product_id = _extract_product_id(payload)
    order_id = _extract_order_id(payload)

    # Nur unsere Produkte verarbeiten
    tier = ABLEFY_PRODUCT_MAP.get(product_id, ABLEFY_PRODUCT_MAP.get(str(product_id), ""))
    if not tier:
        logger.info(f"[WEBHOOK] Order State fuer unbekanntes Produkt '{product_id}' — ignoriert")
        return JSONResponse({"status": "ok", "message": "Product not managed by this system"})

    # Neuen Status extrahieren
    new_state = (
        payload.get("state")
        or payload.get("new_state")
        or payload.get("order_state")
        or payload.get("status")
        or ""
    ).lower()

    logger.info(f"[WEBHOOK] Order State | Email: {email} | Order: {order_id} | State: {new_state}")

    if email and new_state in ("cancelled", "canceled", "expired", "refunded", "suspended"):
        user = db.get_dashboard_user_by_email(email.lower().strip())
        if user:
            _update_payment_status(db, user["customer_id"], new_state, order_id)
            db._conn.execute(
                "UPDATE customers SET is_active = 0, deactivated_at = ? WHERE id = ?",
                (datetime.utcnow().isoformat(), user["customer_id"]),
            )
            db._conn.commit()
            logger.info(f"[WEBHOOK] User deaktiviert nach Order State '{new_state}': {email}")

            # Telegram Auto-Kick
            telegram_id = user.get("telegram_chat_id", "")
            if telegram_id:
                kicked = await kick_from_paid_group(telegram_id)
                if kicked:
                    logger.info(f"[WEBHOOK] User aus Telegram-Gruppe gekickt: {email}")
                else:
                    logger.warning(f"[WEBHOOK] Telegram-Kick fehlgeschlagen: {email}")

    return JSONResponse({"status": "ok", "message": "Order state processed"})


async def _handle_payment_failed(payload: dict, reason: str = "chargeback") -> JSONResponse:
    """SEPA-Ruecklastschrift / Chargeback -- Zugang wieder entziehen.

    Gegenstueck zum SEPA-Sofort-Freischalten: platzt die Lastschrift, entfernen wir
    eine noch offene Vormerkung und sperren einen bereits registrierten User (+ Telegram-Kick).
    Nur fuer unsere Produkte.
    """
    db = get_db()
    email = _extract_email(payload)
    product_id = _extract_product_id(payload)
    order_id = _extract_order_id(payload)

    tier = ABLEFY_PRODUCT_MAP.get(product_id, ABLEFY_PRODUCT_MAP.get(str(product_id), ""))
    if not email or not tier:
        logger.info(f"[WEBHOOK] {reason}: keine Email / kein passendes Produkt ({product_id}) -- ignoriert")
        return JSONResponse({"status": "ok", "message": "chargeback ignored"})

    email_norm = email.lower().strip()
    logger.warning(f"[WEBHOOK] {reason} | Email: {email_norm} | Order: {order_id} | Product: {product_id}")

    row = db._conn.execute(
        "SELECT claimed_at FROM pending_payments WHERE email = ?", (email_norm,)
    ).fetchone()
    if row is not None and row["claimed_at"] is None:
        db._conn.execute(
            "DELETE FROM pending_payments WHERE email = ? AND claimed_at IS NULL", (email_norm,)
        )
        db._conn.commit()
        logger.warning(f"[WEBHOOK] {reason}: offene Vormerkung entfernt: {email_norm}")

    user = db.get_dashboard_user_by_email(email_norm)
    if user:
        _update_payment_status(db, user["customer_id"], "chargebacked", order_id)
        db._conn.execute(
            "UPDATE customers SET is_active = 0, deactivated_at = ? WHERE id = ?",
            (datetime.utcnow().isoformat(), user["customer_id"]),
        )
        db._conn.commit()
        logger.warning(f"[WEBHOOK] {reason}: User gesperrt: {email_norm}")

        telegram_id = user.get("telegram_chat_id", "")
        if telegram_id:
            kicked = await kick_from_paid_group(telegram_id)
            kres = "ok" if kicked else "fehlgeschlagen"
            logger.info(f"[WEBHOOK] {reason}: Telegram-Kick {kres}: {email_norm}")

    return JSONResponse({"status": "ok", "message": "chargeback processed"})


# ==========================================================================
# RUECKKEHRER — Wer wieder zahlt, ist automatisch wieder drin (2026-09-11)
# ==========================================================================

def _access_type(payload: dict) -> str:
    """access.access_type aus payer.access.changed ('GRANT' / 'REVOKE' / '')."""
    access = payload.get("access")
    if isinstance(access, dict):
        return str(access.get("access_type") or "").upper()
    return ""


def _find_user(db, email_norm: str):
    """User per E-Mail finden — inkl. gmail.com <-> googlemail.com (gleiche Google-Mailbox).

    Anlass Pawel Brendler (2026-09-10): er nannte ...@gmail.com, in der DB stand ...@googlemail.com.
    """
    user = db.get_dashboard_user_by_email(email_norm)
    if user or "@" not in email_norm:
        return user
    local, domain = email_norm.rsplit("@", 1)
    alias = {"gmail.com": "googlemail.com", "googlemail.com": "gmail.com"}.get(domain)
    if alias:
        user = db.get_dashboard_user_by_email(f"{local}@{alias}")
        if user:
            logger.info(f"[WEBHOOK] User ueber Mail-Alias gefunden: {email_norm} -> {local}@{alias}")
    return user


def _record_access(payload: dict) -> None:
    """Ablefys 'Zugang gueltig bis' (payer.access.changed + GRANT) am User mitschreiben.

    Reine Datenerfassung — loest KEINE Aktion aus. Letzter GRANT gewinnt (= Ablefys aktueller
    Stand). NULL = unbefristet. Grundlage fuer Kick-Pruefungen / spaeteren Ablauf-Job.
    """
    try:
        if str(payload.get("event") or "") != "payer.access.changed" or _access_type(payload) != "GRANT":
            return
        product_id = _extract_product_id(payload)
        if not ABLEFY_PRODUCT_MAP.get(product_id, ABLEFY_PRODUCT_MAP.get(str(product_id), "")):
            return
        email = _extract_email(payload)
        if not email:
            return
        db = get_db()
        user = _find_user(db, email.lower().strip())
        if not user:
            return
        valid_until = (payload.get("access") or {}).get("access_valid_until")
        db._conn.execute(
            "UPDATE dashboard_users SET access_valid_until = ? WHERE customer_id = ?",
            (valid_until, user["customer_id"]),
        )
        db._conn.commit()
    except Exception as e:
        logger.warning(f"[WEBHOOK] access_valid_until nicht gespeichert: {e}")


async def _reactivate_user(db, user: dict, email_norm: str, order_id: str, first_name: str = "") -> bool:
    """Kunde war draussen (gekuendigt/gekickt/gesperrt) und hat wieder gezahlt -> automatisch zurueckholen.

    1. customers.is_active 0 -> 1, race-sicher: nur der Worker, der kippt, macht weiter
       (Ablefy feuert pro Kauf mehrere Events, das Dashboard laeuft mit 3 Workern)
    2. Ban in Main + Scalp aufheben (der Ban ist permanent — ohne Entbannung nuetzt kein Link)
    3. Frischer Einmal-Link -> DB + Mail an den Kunden
    4. Info an Max (Telegram-DM)
    Blocklist hat Vorrang: gesperrte E-Mails werden nie reaktiviert.
    """
    customer_id = user["customer_id"]
    stored_email = str(user.get("email") or email_norm).lower().strip()
    if is_email_blocked(db, stored_email) or is_email_blocked(db, email_norm):
        logger.warning(f"[WEBHOOK] [REAKTIVIERUNG] {email_norm} steht auf der Blocklist — NICHT reaktiviert")
        return False

    cur = db._conn.execute(
        "UPDATE customers SET is_active = 1, deactivated_at = NULL WHERE id = ? AND is_active = 0",
        (customer_id,),
    )
    db._conn.commit()
    if cur.rowcount != 1:
        return False  # anderer Worker/Event war schneller — der kuemmert sich

    tg_id = str(user.get("telegram_chat_id") or "").strip()
    unban = await unban_from_groups(tg_id) if tg_id else {}

    link = await create_paid_invite(f"Reaktiv {stored_email}"[:32])
    if link:
        db._conn.execute(
            "UPDATE dashboard_users SET telegram_invite_link = ? WHERE customer_id = ?",
            (link, customer_id),
        )
        db._conn.commit()
        fn = first_name or user.get("first_name") or (user.get("customer_name") or "").split(" ")[0] or "Trader"
        send_async(send_access_restored_email, email_norm, fn, link)

    if tg_id:
        unban_txt = ", ".join(f"{k}: {'ok' if v else 'FEHLER'}" for k, v in unban.items()) or "keine Gruppe konfiguriert"
    else:
        unban_txt = "keine Telegram-ID bekannt (falls er nicht reinkommt: manuell entbannen)"
    await notify_admin(
        f"[REAKTIVIERT] {email_norm} hat wieder gezahlt (Order {order_id or '?'}) und war draussen.\n"
        f"Automatisch erledigt: Kunde aktiv | Entbannung {unban_txt} | "
        f"neuer Einmal-Link {'per Mail verschickt' if link else 'FEHLGESCHLAGEN - bitte manuell erstellen'}."
    )
    logger.warning(
        f"[WEBHOOK] [REAKTIVIERT] {email_norm} | Order {order_id} | Unban {unban or '-'} | Link {'ok' if link else 'FEHLER'}"
    )
    return True


# ==========================================================================
# PAYLOAD EXTRACTION — Verschiedene Pfade da Ablefy-Format unbekannt
# ==========================================================================

def _extract_email(payload: dict) -> str:
    """E-Mail aus verschiedenen moeglichen Payload-Pfaden extrahieren."""
    # Direkt
    if payload.get("email"):
        return payload["email"]
    # Nested: payer, customer, buyer, user
    for key in ("payer", "customer", "buyer", "user", "contact"):
        nested = payload.get(key, {})
        if isinstance(nested, dict) and nested.get("email"):
            return nested["email"]
    # Flache Felder mit Prefix
    for key in ("payer_email", "customer_email", "buyer_email", "user_email"):
        if payload.get(key):
            return payload[key]
    return ""


def _extract_product_id(payload: dict) -> str:
    """Produkt-ID aus Payload extrahieren (robust gegen verschachtelte Strukturen)."""
    # Verschachtelt: product = {"product_id": 517561} — so feuert Ablefy bei vielen Events.
    # WICHTIG: hier NICHT str(dict) zurueckgeben (war der Bug — SEPA-Kunden fielen durchs Raster).
    product = payload.get("product")
    if isinstance(product, dict):
        for k in ("product_id", "productId", "id"):
            if product.get(k):
                return str(product[k])
    # Flacher Wert direkt im Payload
    for key in ("product_id", "productId"):
        val = payload.get(key)
        if val and not isinstance(val, (dict, list)):
            return str(val)
    if product and not isinstance(product, (dict, list)):
        return str(product)
    # sellables[] / line_items[] (Bumps: mehrere Produkte pro Bestellung)
    for list_key in ("sellables", "line_items", "items"):
        items = payload.get(list_key)
        if isinstance(items, list) and items and isinstance(items[0], dict):
            for k in ("product_id", "productId", "id"):
                if items[0].get(k):
                    return str(items[0][k])
    return ""


def _extract_order_id(payload: dict) -> str:
    """Order-ID aus Payload extrahieren."""
    for key in ("order_id", "orderId", "id", "payment_id", "transaction_id"):
        val = payload.get(key)
        if val:
            return str(val)
    return ""


def _extract_amount(payload: dict) -> str:
    """Zahlungsbetrag aus Payload extrahieren."""
    for key in ("amount", "total", "price", "gross_amount", "net_amount"):
        val = payload.get(key)
        if val:
            return str(val)
    return ""


def _extract_name(payload: dict) -> tuple[str, str]:
    """Vor- und Nachname aus verschiedenen moeglichen Payload-Pfaden extrahieren."""
    # Nested: payer, customer, buyer, user
    for key in ("payer", "customer", "buyer", "user", "contact"):
        nested = payload.get(key, {})
        if isinstance(nested, dict):
            fn = nested.get("first_name", "")
            ln = nested.get("last_name", "")
            if fn or ln:
                return str(fn), str(ln)
    # buyer_name / payer_name (vollerName)
    for key in ("buyer_name", "payer_name", "customer_name", "name"):
        val = payload.get(key)
        if val and isinstance(val, str):
            parts = val.strip().split(" ", 1)
            return parts[0], parts[1] if len(parts) > 1 else ""
    # Flache Felder
    fn = payload.get("first_name", "")
    ln = payload.get("last_name", "")
    if fn or ln:
        return str(fn), str(ln)
    return "", ""


# ==========================================================================
# DB OPERATIONS
# ==========================================================================

def _update_payment_status(
    db, customer_id: str, status: str,
    order_id: str = "", product_id: str = "", amount: str = "",
):
    """Payment-Status in dashboard_users updaten."""
    now = datetime.utcnow().isoformat()
    db._conn.execute("""
        UPDATE dashboard_users SET
            payment_status = ?,
            ablefy_order_id = COALESCE(?, ablefy_order_id),
            ablefy_product_id = COALESCE(?, ablefy_product_id),
            paid_amount = COALESCE(?, paid_amount),
            paid_at = CASE WHEN ? IN ('paid', 'active') THEN ? ELSE paid_at END
        WHERE customer_id = ?
    """, (status, order_id or None, product_id or None, amount or None,
          status, now, customer_id))
    db._conn.commit()


def _store_pending_payment(
    db, email: str, order_id: str,
    product_id: str, tier: str, amount: str,
    first_name: str = "", last_name: str = "",
):
    """Payment vormerken fuer User der sich noch nicht registriert hat."""
    now = datetime.utcnow().isoformat()
    db._conn.execute("""
        INSERT OR REPLACE INTO pending_payments
        (email, ablefy_order_id, ablefy_product_id, product_tier, amount, created_at, first_name, last_name)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (email, order_id, product_id, tier, amount, now, first_name or None, last_name or None))
    db._conn.commit()
    logger.info(f"[WEBHOOK] Pending Payment gespeichert: {email} → {tier}")


def _store_webhook_log(payload: dict):
    """Jeden Webhook-Payload in einer Log-Tabelle speichern."""
    try:
        db = get_db()
        db._conn.execute("""
            INSERT INTO webhook_logs (source, payload, created_at)
            VALUES (?, ?, ?)
        """, ("ablefy", json.dumps(payload, default=str), datetime.utcnow().isoformat()))
        db._conn.commit()
    except Exception as e:
        logger.warning(f"[WEBHOOK] Log speichern fehlgeschlagen: {e}")
