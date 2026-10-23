#!/usr/bin/env python3
"""(C) patch_reactivation.py — Auto-Reaktivierung zahlender Rueckkehrer (2026-09-11).

Regel Max (2026-09-11): Wer (wieder) zahlt, ist automatisch wieder drin.

Aendert 4 Dateien im Dashboard (Anker-basiert, jeder Anker muss GENAU 1x vorkommen,
Backups *.bak_reactivation_20260911). Erst werden ALLE Anker geprueft, dann geschrieben.
  routes/webhook_routes.py  — Reaktivierung im Payment-Pfad, gmail/googlemail-Alias,
                              access_valid_until mitschreiben, REVOKE nie als Zahlung werten
  telegram_invites.py       — unban_from_groups() (Main + Scalp), notify_admin()
  email_service.py          — send_access_restored_email()
  db.py                     — Migration: Spalte dashboard_users.access_valid_until
Idempotent: bereits gepatchte Dateien werden uebersprungen.

Aufruf: cd /home/botuser/dashboard && python3 patch_reactivation.py
"""
import py_compile
import shutil
import sys

SUFFIX = ".bak_reactivation_20260911"

# ---------------------------------------------------------------------------
# telegram_invites.py
# ---------------------------------------------------------------------------
TG_ANCHOR = '        logger.error(f"[TELEGRAM] Kick fehlgeschlagen: {e}")\n        return False\n'
TG_ADD = r'''

# ==========================================================================
# RUECKKEHRER — Ban aufheben + Admin-Info (2026-09-11)
# ==========================================================================

SCALP_GROUP_ID = os.getenv("SIGNAL_SCALP_GROUP_ID", "")
ADMIN_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")


async def unban_from_groups(telegram_user_id: str) -> dict:
    """Hebt einen Ban in Main-Gruppe + Scalp-Channel auf.

    only_if_banned=True -> aktive Mitglieder bleiben unberuehrt (kein versehentlicher Kick).
    Rueckgabe: {"main": bool, "scalp": bool} fuer jede konfigurierte Gruppe.
    """
    results: dict = {}
    if not BOT_TOKEN or not telegram_user_id:
        return results
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/unbanChatMember"
    async with aiohttp.ClientSession() as session:
        for label, gid in (("main", PAID_GROUP_ID), ("scalp", SCALP_GROUP_ID)):
            if not gid:
                continue
            try:
                payload = {"chat_id": int(gid), "user_id": int(telegram_user_id), "only_if_banned": True}
                async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    data = await resp.json()
                    results[label] = bool(data.get("ok"))
                    if not data.get("ok"):
                        logger.warning(f"[TELEGRAM] unbanChatMember {label} fehlgeschlagen: {data}")
            except Exception as e:
                results[label] = False
                logger.error(f"[TELEGRAM] unbanChatMember {label} Fehler: {e}")
    logger.info(f"[TELEGRAM] Entbannung {telegram_user_id}: {results}")
    return results


async def notify_admin(text: str) -> bool:
    """Kurze Info-DM an Max (TELEGRAM_CHAT_ID). Best-effort, wirft nie."""
    if not BOT_TOKEN or not ADMIN_CHAT_ID:
        return False
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                json={"chat_id": ADMIN_CHAT_ID, "text": text[:4000], "disable_web_page_preview": True},
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                data = await resp.json()
                return bool(data.get("ok"))
    except Exception as e:
        logger.error(f"[TELEGRAM] Admin-Info fehlgeschlagen: {e}")
        return False
'''

# ---------------------------------------------------------------------------
# email_service.py
# ---------------------------------------------------------------------------
MAIL_ANCHOR = '    return _send_mail(to_email, "Richte deinen Account ein — FirstClass Copy Trading", _wrap_html("Account einrichten", content))\n'
MAIL_ADD = r'''

def send_access_restored_email(to_email: str, first_name: str, telegram_link: str) -> bool:
    """Rueckkehrer: Zahlung ist da, Zugang wieder freigeschaltet — mit frischem Einmal-Link (2026-09-11)."""
    name = first_name or "Trader"
    content = (
        _heading(f"Dein Zugang ist wieder aktiv, {name}! ✅")
        + _text("Deine Zahlung ist eingegangen — wir haben dich wieder für die Copy Trading Gruppe freigeschaltet. "
                "Tritt einfach über den Button bei. Der Link ist nur für dich und funktioniert genau einmal.")
        + _button(telegram_link, "Copy Trading Gruppe beitreten")
        + _text(f'Falls der Button nicht angezeigt wird, öffne diesen Link:<br>{_link(telegram_link, telegram_link)}', muted=True)
        + _divider()
        + _text("Den Zugang zum Scalping-Channel findest du wie gewohnt angepinnt in der Gruppe.")
        + _button(f"{BASE_URL}/dashboard", "Zum Dashboard")
        + _divider()
        + _text(f'Fragen? {_link("https://t.me/FCT_Copy_Trading_Support_Bot", "Telegram Support")} oder {_link("mailto:support@firstclass-trading.com", "support@firstclass-trading.com")}.', muted=True)
    )
    return _send_mail(to_email, "Dein Zugang ist wieder aktiv — FirstClass Copy Trading", _wrap_html("Zugang wieder aktiv", content))
'''

# ---------------------------------------------------------------------------
# db.py
# ---------------------------------------------------------------------------
DB_ANCHOR = '    if "phone" not in cols:\n        conn.execute("ALTER TABLE dashboard_users ADD COLUMN phone TEXT")\n'
DB_ADD = r'''    # Ablefy "Zugang gueltig bis" (payer.access.changed / GRANT) — Basis fuer Ablauf-Pruefung (2026-09-11)
    if "access_valid_until" not in cols:
        try:
            conn.execute("ALTER TABLE dashboard_users ADD COLUMN access_valid_until TEXT")
        except Exception:
            pass  # parallel startender Worker war schneller
'''

# ---------------------------------------------------------------------------
# routes/webhook_routes.py
# ---------------------------------------------------------------------------
WH_EDITS = [
    # 1) Imports
    ('from email_service import send_payment_confirmed_email_signals, send_payment_confirmed_email_copytrading, send_purchase_setup_email, send_async\n',
     'from email_service import send_payment_confirmed_email_signals, send_payment_confirmed_email_copytrading, send_purchase_setup_email, send_access_restored_email, send_async\n'),
    ('from telegram_invites import kick_from_paid_group\n',
     'from telegram_invites import kick_from_paid_group, create_paid_invite, unban_from_groups, notify_admin\n'),
    # 2) access_valid_until bei jedem Event mitschreiben (reine Datenerfassung)
    ('        # Payload in DB speichern (fuer spaetere Analyse)\n        _store_webhook_log(payload)\n',
     '        # Payload in DB speichern (fuer spaetere Analyse)\n        _store_webhook_log(payload)\n'
     '\n        # Ablefys "Zugang gueltig bis" am User mitschreiben (reine Datenerfassung, keine Aktion)\n'
     '        _record_access(payload)\n'),
    # 3) Defensiv: ein REVOKE darf nie als Zahlung durchgehen
    ('                and event_type in ("payment.pending", "payer.access.changed", "order.subscription.paying", "order.subscription.pending"))\n',
     '                and event_type in ("payment.pending", "payer.access.changed", "order.subscription.paying", "order.subscription.pending")\n'
     '                and _access_type(payload) != "REVOKE")\n'),
    # 4) User-Lookup inkl. gmail/googlemail-Alias
    ('    # User per E-Mail finden\n    user = db.get_dashboard_user_by_email(email.lower().strip())\n',
     '    # User per E-Mail finden (inkl. gmail.com <-> googlemail.com, gleiche Mailbox)\n    user = _find_user(db, email.lower().strip())\n'),
    # 5) War der Kunde vorher draussen?
    ('        # Idempotenz: gleicher Order schon als bezahlt verbucht',
     '        # War der Kunde vorher draussen (gekuendigt/gekickt/gesperrt)? Dann holen wir ihn nach der Zahlung\n'
     '        # automatisch zurueck (Entbannung + neuer Einmal-Link + Mail). Regel Max 2026-09-11: wer zahlt, ist drin.\n'
     '        _row = db._conn.execute("SELECT is_active FROM customers WHERE id = ?", (customer_id,)).fetchone()\n'
     '        was_inactive = _row is not None and not _row["is_active"]\n'
     '        # Idempotenz: gleicher Order schon als bezahlt verbucht'),
    # 6) Reaktivierung ausloesen (ersetzt dann die normale "Zahlung bestaetigt"-Mail)
    ('        if not already:\n            fn = user.get("first_name")',
     '        reactivated = False\n'
     '        if was_inactive:\n'
     '            reactivated = await _reactivate_user(db, user, email_norm, order_id, first_name)\n'
     '\n'
     '        if not already and not reactivated:\n            fn = user.get("first_name")'),
    # 7) Log-Zeile ergaenzen
    ("{'nein/schon verbucht' if already else 'ja'}\")\n",
     "{'nein/schon verbucht' if already else 'ja'} | Reaktiviert: {'ja' if reactivated else 'nein'}\")\n"),
    # 8) Helper-Funktionen hinter _handle_payment_failed
    ('    return JSONResponse({"status": "ok", "message": "chargeback processed"})\n',
     '    return JSONResponse({"status": "ok", "message": "chargeback processed"})\n' + r'''

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
'''),
]

PLAN = [
    ("telegram_invites.py", "def unban_from_groups", [(TG_ANCHOR, TG_ANCHOR + TG_ADD)]),
    ("email_service.py", "def send_access_restored_email", [(MAIL_ANCHOR, MAIL_ANCHOR + MAIL_ADD)]),
    ("db.py", "access_valid_until", [(DB_ANCHOR, DB_ANCHOR + DB_ADD)]),
    ("routes/webhook_routes.py", "def _reactivate_user", WH_EDITS),
]


def main() -> int:
    # Phase 1: alles pruefen, nichts schreiben
    todo = []
    for path, marker, edits in PLAN:
        text = open(path, encoding="utf-8").read()
        if marker in text:
            print(f"SKIP  {path}: bereits gepatcht ({marker!r} vorhanden)")
            continue
        for i, (old, _new) in enumerate(edits, 1):
            n = text.count(old)
            if n != 1:
                print(f"FAIL  {path}: Anker #{i} kommt {n}x vor (erwartet 1): {old[:70]!r}")
                return 1
        todo.append((path, text, edits))

    # Phase 2: schreiben + kompilieren
    for path, text, edits in todo:
        for old, new in edits:
            text = text.replace(old, new, 1)
        shutil.copy2(path, path + SUFFIX)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        py_compile.compile(path, doraise=True)
        print(f"OK    {path}: {len(edits)} Aenderung(en), Backup {path + SUFFIX}, py_compile OK")
    print("FERTIG")
    return 0


if __name__ == "__main__":
    sys.exit(main())
