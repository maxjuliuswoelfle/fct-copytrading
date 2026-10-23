"""
(C) email_service.py — Transaktionaler E-Mail-Service

Versendet System-Mails ueber Google Workspace SMTP.
Alle Credentials kommen aus Umgebungsvariablen.

Mails:
  - E-Mail-Verifizierung (Double-Opt-In)
  - Willkommen nach Setup
  - Passwort-Reset
  - Copy Trading pausiert / fortgesetzt
"""

import os
import re
import asyncio
import logging
import smtplib
import secrets
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Nicht-blockierender Mail-Versand
# --------------------------------------------------------------------------
# Der SMTP-Versand (smtplib) ist blockierend (bis 15s Timeout). In einer
# async-Route wuerde das die gesamte Event-Loop blockieren. send_async() schiebt
# den Versand in einen Hintergrund-Thread (fire-and-forget) — die Response geht
# sofort raus, die Mail laeuft parallel. Kritisch fuer Last (300-500 gleichzeitig).
_bg_tasks: set = set()


def send_async(fn, *args, **kwargs) -> None:
    """Mail-Funktion non-blocking im Hintergrund-Thread ausfuehren (fire-and-forget)."""
    async def _runner():
        try:
            await asyncio.to_thread(fn, *args, **kwargs)
        except Exception as e:
            logger.warning(f"[MAIL] Hintergrund-Versand fehlgeschlagen ({getattr(fn, '__name__', '?')}): {e}")

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # Kein laufender Event-Loop (synchroner Kontext) → direkt versenden
        try:
            fn(*args, **kwargs)
        except Exception as e:
            logger.warning(f"[MAIL] Versand fehlgeschlagen ({getattr(fn, '__name__', '?')}): {e}")
        return

    task = loop.create_task(_runner())
    _bg_tasks.add(task)            # Referenz halten, sonst GC den Task evtl. abbricht
    task.add_done_callback(_bg_tasks.discard)

# --- Config aus Umgebungsvariablen ---
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASS = os.getenv("SMTP_PASS", "")
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "FirstClass Copy Trading")
BASE_URL = os.getenv("DASHBOARD_BASE_URL", "https://dashboard.firstclass-trading.com")

# Logo Icon URL (gehostet auf dem Dashboard-Server)
ICON_URL = f"{BASE_URL}/static/logos/Icon%20White.png"


def _send_mail(to_email: str, subject: str, html_body: str) -> bool:
    """
    Mail ueber SMTP versenden. Gibt True bei Erfolg zurueck.
    Non-blocking: Fehler werden geloggt, nicht geworfen.
    """
    if not SMTP_USER or not SMTP_PASS:
        logger.error("[EMAIL] SMTP credentials nicht konfiguriert (SMTP_USER / SMTP_PASS)")
        return False

    msg = MIMEMultipart("alternative")
    msg["From"] = f"{SMTP_FROM_NAME} <{SMTP_USER}>"
    msg["To"] = to_email
    msg["Subject"] = subject
    msg["Reply-To"] = SMTP_USER

    # Plain-Text Fallback — Links als "Text (URL)" erhalten, BEVOR Tags gestrippt werden,
    # sonst geht bei Buttons/Links die URL verloren (Kunde sieht Text ohne Link).
    plain = re.sub(r'<a\s[^>]*href="([^"]+)"[^>]*>(.*?)</a>', r'\2: \1', html_body, flags=re.IGNORECASE | re.DOTALL)
    plain = plain.replace("<br>", "\n").replace("</p>", "\n")
    plain = re.sub(r"<[^>]+>", "", plain)

    msg.attach(MIMEText(plain, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)
        logger.info(f"[EMAIL] Gesendet an {to_email}: {subject}")
        return True
    except Exception as e:
        logger.error(f"[EMAIL] Fehler beim Senden an {to_email}: {e}")
        return False


def generate_token() -> str:
    """Sicheren Token generieren (fuer Verifizierung, Passwort-Reset)."""
    return secrets.token_urlsafe(32)


# ============================================================
# HTML E-Mail Template — Dashboard-Style
# ============================================================
#
# Aufbau:  Weisser Hintergrund → Dunkle Card (wie Dashboard)
# Logo:    Orange Icon + White Text (gehostet auf Server)
# Buttons: Dashboard-Gradient (warm orange, dunkle Schrift)
# Typo:    Inter / System-Font, Dashboard-Spacing
# ============================================================

def _wrap_html(title: str, content: str) -> str:
    """
    Wraps Content in ein responsives HTML-Mail-Template.
    Weisser Hintergrund, dunkle Card im Dashboard-Stil.
    """
    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<!--[if mso]>
<style>body,table,td{{font-family:Arial,Helvetica,sans-serif!important;}}</style>
<![endif]-->
</head>
<body style="margin:0;padding:0;background-color:#F5F5F5;font-family:-apple-system,BlinkMacSystemFont,'Inter','Segoe UI',Roboto,Helvetica,Arial,sans-serif;-webkit-font-smoothing:antialiased;">

<!-- Outer wrapper — weisser/heller Hintergrund -->
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color:#F5F5F5;">
<tr><td align="center" style="padding:40px 16px;">

<!-- Card — max 520px, responsive -->
<table role="presentation" cellspacing="0" cellpadding="0" border="0" style="width:100%;max-width:520px;">

<!-- Dark Card -->
<tr>
<td style="background-color:#111111;border-radius:14px;border:1px solid rgba(255,255,255,0.06);overflow:hidden;">

<!-- Card Content -->
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">

<!-- Logo Header (wie Login-Screen) -->
<tr>
<td align="center" style="padding:32px 32px 28px;">
  <table role="presentation" cellspacing="0" cellpadding="0" border="0">
  <tr>
  <td style="vertical-align:middle;">
    <div style="width:36px;height:36px;border-radius:8px;background:linear-gradient(135deg,#FFB07A 0%,#FF8528 55%,#C85A0F 100%);text-align:center;line-height:36px;">
      <img src="{ICON_URL}" alt="FC" width="20" height="20" style="display:inline-block;border:0;vertical-align:middle;" />
    </div>
  </td>
  <td style="vertical-align:middle;padding-left:12px;">
    <div style="font-size:18px;font-weight:600;color:#FAFAFA;line-height:1.2;letter-spacing:-0.01em;">FirstClass</div>
    <div style="font-size:9px;font-weight:600;color:#6B6B6B;letter-spacing:0.14em;text-transform:uppercase;margin-top:3px;">Copy Trading</div>
  </td>
  </tr>
  </table>
</td>
</tr>

<!-- Divider unter Logo -->
<tr>
<td style="padding:0 32px;">
  <hr style="border:none;border-top:1px solid rgba(255,255,255,0.06);margin:0;">
</td>
</tr>

<!-- Content -->
<tr>
<td style="padding:28px 32px 36px;">
  {content}
</td>
</tr>
</table>

</td>
</tr>

<!-- Footer — unter der Card, auf hellem Hintergrund -->
<tr>
<td align="center" style="padding:24px 16px 0;">
  <p style="margin:0;font-size:11px;color:#999999;line-height:1.7;">
    F&amp;S Coaching FZCO · Silicon Oasis, DDP, Building A1 · Dubai, UAE<br>
    <a href="{BASE_URL}/impressum" style="color:#999999;text-decoration:underline;">Impressum</a> &nbsp;·&nbsp;
    <a href="{BASE_URL}/datenschutz" style="color:#999999;text-decoration:underline;">Datenschutz</a>
  </p>
  <p style="margin:8px 0 0;font-size:11px;color:#BBBBBB;line-height:1.5;">
    Du erh&auml;ltst diese E-Mail, weil du ein Konto bei FirstClass Copy Trading hast.
  </p>
</td>
</tr>

</table>

</td></tr>
</table>
</body>
</html>"""


def _button(url: str, label: str) -> str:
    """CTA-Button im Dashboard-Stil (warmer Orange-Gradient, dunkle Schrift)."""
    return f"""<table role="presentation" cellspacing="0" cellpadding="0" border="0" style="margin:28px 0 20px;">
<tr>
<td align="center" bgcolor="#FF8528" style="background-color:#FF8528;background:linear-gradient(135deg,#FFB07A 0%,#FF8528 60%,#E5701A 100%);border-radius:9px;">
  <a href="{url}" target="_blank" style="display:inline-block;padding:14px 36px;color:#1a0d00;text-decoration:none;font-size:15px;font-weight:700;font-family:-apple-system,BlinkMacSystemFont,'Inter','Segoe UI',Roboto,Helvetica,Arial,sans-serif;letter-spacing:-0.01em;">{label} →</a>
</td>
</tr>
</table>"""


def _text(t: str, muted: bool = False) -> str:
    """Absatz mit Standard-Styling. muted=True fuer Hinweistexte."""
    if muted:
        return f'<p style="margin:0 0 12px;font-size:12px;color:#6B6B6B;line-height:1.6;">{t}</p>'
    return f'<p style="margin:0 0 16px;font-size:14px;color:#A1A1A1;line-height:1.7;">{t}</p>'


def _heading(t: str) -> str:
    """Ueberschrift im Dashboard-Stil."""
    return f'<h2 style="margin:0 0 20px;font-size:20px;font-weight:600;color:#FAFAFA;letter-spacing:-0.02em;line-height:1.3;">{t}</h2>'


def _divider() -> str:
    """Dezente Trennlinie."""
    return '<hr style="border:none;border-top:1px solid rgba(255,255,255,0.06);margin:24px 0;">'


def _link(url: str, label: str) -> str:
    """Inline-Link im FCT-Orange."""
    return f'<a href="{url}" style="color:#FF8528;text-decoration:none;font-weight:500;">{label}</a>'


# ============================================================
# E-Mail 1: Verifizierung
# ============================================================

def send_verification_email(to_email: str, first_name: str, token: str, tier: str = "copy_trading") -> bool:
    """E-Mail-Verifizierung nach Registrierung (Double-Opt-In). Tier-abhaengig."""
    url = f"{BASE_URL}/verify-email?token={token}"

    if tier == "free":
        subject = "E-Mail bestätigen — FirstClass Copy Trading"
        content = (
            _heading(f"Willkommen, {first_name}!")
            + _text("Danke für deine Anmeldung zum Copy Trading.")
            + _text("Bestätige deine E-Mail-Adresse, damit wir dich für die Copy Trading Gruppe freischalten können:")
            + _button(url, "E-Mail bestätigen")
            + _text(f'Falls der Button nicht funktioniert, {_link(url, "klicke hier")}.', muted=True)
            + _divider()
            + _text("Der Link ist 24 Stunden gültig. Wenn du dich nicht angemeldet hast, kannst du diese E-Mail ignorieren.", muted=True)
        )
    elif tier == "paid_signals":
        subject = "Noch ein Schritt — Bestätige deine E-Mail"
        content = (
            _heading(f"Fast geschafft, {first_name}!")
            + _text("Danke für deinen Kauf. Bestätige jetzt deine E-Mail-Adresse, damit wir dein Konto aktivieren und dich für die Copy Trading Gruppe freischalten können:")
            + _button(url, "E-Mail bestätigen & loslegen")
            + _text(f'Falls der Button nicht funktioniert, {_link(url, "klicke hier")}.', muted=True)
            + _divider()
            + _text("Der Link ist 48 Stunden gültig. Wenn du dich nicht angemeldet hast, kannst du diese E-Mail ignorieren.", muted=True)
        )
    else:
        subject = "E-Mail bestätigen — FirstClass Copy Trading"
        content = (
            _heading(f"Willkommen, {first_name}!")
            + _text("Danke für deine Registrierung beim FirstClass Copy Trading.")
            + _text("Bestätige bitte deine E-Mail-Adresse, damit wir dein Konto aktivieren können:")
            + _button(url, "E-Mail bestätigen")
            + _text(f'Falls der Button nicht funktioniert, {_link(url, "klicke hier")}.', muted=True)
            + _divider()
            + _text("Der Link ist 24 Stunden gültig. Wenn du dich nicht registriert hast, kannst du diese E-Mail ignorieren.", muted=True)
        )

    return _send_mail(to_email, subject, _wrap_html("E-Mail bestätigen", content))


# ============================================================
# E-Mail 2: Setup abgeschlossen — Willkommen
# ============================================================

def send_welcome_email(to_email: str, first_name: str) -> bool:
    """Willkommensmail nach abgeschlossenem Copy Trading Setup."""
    content = (
        _heading(f"Du bist startklar, {first_name}! 🚀")
        + _text("Dein Copy Trading Account ist eingerichtet und aktiv. Ab sofort werden alle Trades automatisch auf deinen Account gespiegelt — proportional zu deiner Kontogröße.")
        + _divider()
        + _text('<span style="color:#FAFAFA;font-weight:600;">Was jetzt passiert:</span>')
        + _text("• Trades werden automatisch eröffnet und geschlossen<br>"
                "• Stop-Loss und Take-Profit werden synchron gesetzt<br>"
                "• Dein Dashboard zeigt dir deine Performance")
        + _button(f"{BASE_URL}/dashboard", "Zum Dashboard")
        + _divider()
        + _text('<span style="color:#FAFAFA;font-weight:600;">Fragen?</span>')
        + _text(f'Erreichst du uns jederzeit über den {_link("https://t.me/FCT_Copy_Trading_Support_Bot", "Telegram Support")} oder per Mail an {_link("mailto:support@firstclass-trading.com", "support@firstclass-trading.com")}.')
    )
    return _send_mail(to_email, "Dein Copy Trading ist aktiv! — FirstClass Copy Trading", _wrap_html("Copy Trading aktiv", content))


def send_welcome_email_free(to_email: str, first_name: str, telegram_link: str = "#") -> bool:
    """Willkommensmail nach abgeschlossenem Free Signals Setup."""
    content = (
        _heading(f"Du bist dabei, {first_name}! 🎉")
        + _text("Dein Account ist eingerichtet. Du erhältst ab sofort alle Trades von Max in Echtzeit gespiegelt — direkt in deine Copy Trading Gruppe.")
        + _button(telegram_link, "Copy Trading Gruppe beitreten")
        + _divider()
        + _text('<span style="color:#FAFAFA;font-weight:600;">So funktioniert\'s:</span>')
        + _text("• Du bekommst alle Trades direkt in die Copy Trading Gruppe<br>"
                "• Jeder Trade enthält Entry, Stop-Loss und Take-Profit<br>"
                "• Du entscheidest selbst, ob und wie du handelst")
        + _divider()
        + _text('<span style="color:#FAFAFA;font-weight:600;">Noch mehr rausholen?</span>')
        + _text(f'Mit unserem {_link(f"{BASE_URL}/signup/copytrading", "Copy Trading")} werden alle Trades automatisch auf deinem Account ausgeführt — kein manuelles Trading nötig.')
        + _divider()
        + f'<p style="margin:0;font-size:12px;color:#6B6B6B;line-height:1.6;text-align:center;">Fragen?<br>{_link("https://t.me/FCT_Copy_Trading_Support_Bot", "Telegram Support")} oder {_link("mailto:support@firstclass-trading.com", "support@firstclass-trading.com")}.</p>'
    )
    return _send_mail(to_email, "Willkommen beim Copy Trading! — FirstClass", _wrap_html("Willkommen", content))


def send_welcome_email_signals(to_email: str, first_name: str, telegram_link: str = "#") -> bool:
    """Willkommensmail nach abgeschlossenem Paid Signals Setup."""
    content = (
        _heading(f"Du bist dabei, {first_name}! 🚀")
        + _text("Dein Copy Trading Account ist eingerichtet. Du erhältst ab sofort alle Trades von Max in Echtzeit gespiegelt — inkl. Trade Management, SL/TP Updates und Scale-In/Out.")
        + _button(telegram_link, "Copy Trading Gruppe beitreten")
        + _divider()
        + _text('<span style="color:#FAFAFA;font-weight:600;">Was du bekommst:</span>')
        + _text("• Alle Trades von Max in Echtzeit direkt in die Copy Trading Gruppe<br>"
                "• Komplettes Trade Management (Entry, SL, TP, Updates)<br>"
                "• Dein persönliches Dashboard mit Übersicht und Support")
        + _button(f"{BASE_URL}/dashboard", "Zum Dashboard")
        + _divider()
        + f'<p style="margin:0;font-size:12px;color:#6B6B6B;line-height:1.6;text-align:center;">Fragen?<br>{_link("https://t.me/FCT_Copy_Trading_Support_Bot", "Telegram Support")} oder {_link("mailto:support@firstclass-trading.com", "support@firstclass-trading.com")}.</p>'
    )
    return _send_mail(to_email, "Dein Copy Trading ist aktiv! — FirstClass", _wrap_html("Copy Trading aktiv", content))


# ============================================================
# E-Mail 3: Zahlung bestätigt
# ============================================================

def send_purchase_setup_email(to_email: str, first_name: str) -> bool:
    """Nach Kauf: Danke + Link zum Account-Setup (falls User die Danke-Seite nicht erreicht hat)."""
    from urllib.parse import quote
    setup_url = f"{BASE_URL}/welcome?email={quote(to_email)}"
    name = first_name or "Trader"
    content = (
        _heading(f"Danke für deinen Kauf, {name}! 🎉")
        + _text("Deine Zahlung ist eingegangen. Richte jetzt deinen Account ein, damit wir dich für die Copy Trading Gruppe freischalten können.")
        + _button(setup_url, "Account einrichten")
        + _text(f'Falls der Button nicht angezeigt wird, öffne diesen Link:<br>{_link(setup_url, setup_url)}', muted=True)
        + _divider()
        + _text('<span style="color:#FAFAFA;font-weight:600;">Was dich erwartet:</span>')
        + _text("• Alle Trades von Max in Echtzeit<br>"
                "• Entry, Stop-Loss, Take-Profit &amp; Trade Management<br>"
                "• Exklusive Copy Trading Gruppe<br>"
                "• Persönliches Dashboard")
        + _divider()
        + _text(f'Fragen? {_link("https://t.me/FCT_Copy_Trading_Support_Bot", "Telegram Support")} oder {_link("mailto:support@firstclass-trading.com", "support@firstclass-trading.com")}.', muted=True)
    )
    return _send_mail(to_email, "Richte deinen Account ein — FirstClass Copy Trading", _wrap_html("Account einrichten", content))


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


def send_payment_confirmed_email_signals(to_email: str, first_name: str) -> bool:
    """Zahlungsbestaetigung fuer Paid Signals Tier (bestehender User)."""
    content = (
        _heading(f"Zahlung bestätigt, {first_name}! ✅")
        + _text("Deine Zahlung für das Copy Trading ist eingegangen. Du kannst jetzt mit dem Setup fortfahren und deine Copy Trading Gruppe freischalten.")
        + _divider()
        + _text('<span style="color:#FAFAFA;font-weight:600;">Was du bekommst:</span>')
        + _text("• Alle Trades von Max in Echtzeit gespiegelt<br>"
                "• Entry, Stop-Loss, Take-Profit &amp; Trade Management<br>"
                "• Exklusive Copy Trading Gruppe")
        + _button(f"{BASE_URL}/welcome", "Weiter zum Setup")
        + _divider()
        + _text(f'Fragen? {_link("https://t.me/FCT_Copy_Trading_Support_Bot", "Telegram Support")} oder {_link("mailto:support@firstclass-trading.com", "support@firstclass-trading.com")}.', muted=True)
    )
    return _send_mail(to_email, "Zahlung bestätigt — FirstClass Copy Trading", _wrap_html("Zahlung bestätigt", content))


def send_payment_confirmed_email_copytrading(to_email: str, first_name: str) -> bool:
    """Zahlungsbestaetigung fuer Copy Trading Tier."""
    content = (
        _heading(f"Zahlung bestätigt, {first_name}! ✅")
        + _text("Deine Zahlung für das Copy Trading ist eingegangen. Du kannst jetzt mit dem Setup fortfahren und deinen Trading-Account verknüpfen.")
        + _divider()
        + _text('<span style="color:#FAFAFA;font-weight:600;">Was dich erwartet:</span>')
        + _text("• Automatisches Trade-Mirroring in Echtzeit<br>"
                "• Proportionale Skalierung auf deine Kontogröße<br>"
                "• Volles Trade Management (SL, TP, Scale)<br>"
                "• Live-Dashboard mit Equity Chart<br>"
                "• Alle Trades in Echtzeit gespiegelt")
        + _button(f"{BASE_URL}/setup/copytrading", "Weiter zum Setup")
        + _divider()
        + _text(f'Fragen? {_link("https://t.me/FCT_Copy_Trading_Support_Bot", "Telegram Support")} oder {_link("mailto:support@firstclass-trading.com", "support@firstclass-trading.com")}.', muted=True)
    )
    return _send_mail(to_email, "Zahlung bestätigt — FirstClass Copy Trading", _wrap_html("Zahlung bestätigt", content))


# ============================================================
# E-Mail 4: Passwort-Reset
# ============================================================

def send_password_reset_email(to_email: str, first_name: str, token: str) -> bool:
    """Passwort-Reset Link."""
    url = f"{BASE_URL}/reset-password?token={token}"
    content = (
        _heading("Passwort zurücksetzen")
        + _text(f"Hi {first_name}, du hast angefordert dein Passwort zurückzusetzen.")
        + _text("Klicke auf den Button um ein neues Passwort zu vergeben:")
        + _button(url, "Neues Passwort setzen")
        + _text(f'Falls der Button nicht funktioniert, {_link(url, "klicke hier")}.', muted=True)
        + _divider()
        + _text("Der Link ist 1 Stunde gültig. Wenn du keinen Reset angefordert hast, ignoriere diese E-Mail — dein Passwort bleibt unverändert.", muted=True)
    )
    return _send_mail(to_email, "Passwort zurücksetzen — FirstClass Copy Trading", _wrap_html("Passwort zurücksetzen", content))


# ============================================================
# E-Mail 4: Copy Trading pausiert / fortgesetzt
# ============================================================

def send_marketing_doi_email(to_email: str, first_name: str, token: str) -> bool:
    """Marketing Double-Opt-In: Bestaetigungsmail fuer Newsletter/Marketing-Einwilligung."""
    url = f"{BASE_URL}/confirm-marketing?token={token}"
    name = first_name or "Trader"
    content = (
        _heading(f"Marketing-Einwilligung bestätigen")
        + _text(f"Hi {name}, du hast dich für unseren Newsletter und Marketing-Updates angemeldet.")
        + _text("Bitte bestätige, dass wir dir gelegentlich Updates, Tipps und Angebote rund um Copy Trading senden dürfen:")
        + _button(url, "Ja, ich möchte Updates erhalten")
        + _text(f'Falls der Button nicht funktioniert, {_link(url, "klicke hier")}.', muted=True)
        + _divider()
        + _text("Wenn du keine Marketing-Mails erhalten möchtest, ignoriere diese E-Mail einfach. Dein Account funktioniert auch ohne diese Bestätigung ganz normal.", muted=True)
    )
    return _send_mail(to_email, "Marketing-Einwilligung bestätigen — FirstClass Copy Trading", _wrap_html("Marketing bestätigen", content))


def send_pause_email(to_email: str, first_name: str) -> bool:
    """Bestaetigung: Copy Trading pausiert."""
    content = (
        _heading("Copy Trading pausiert ⏸️")
        + _text(f"Hi {first_name}, dein Copy Trading wurde erfolgreich pausiert.")
        + _divider()
        + _text('<span style="color:#FAFAFA;font-weight:600;">Was das bedeutet:</span>')
        + _text("• Es werden keine neuen Trades eröffnet<br>"
                "• Bestehende Positionen bleiben offen und werden weiter gemanagt<br>"
                "• Du kannst das Copy Trading jederzeit über dein Dashboard wieder aktivieren")
        + _button(f"{BASE_URL}/dashboard", "Zum Dashboard")
        + _divider()
        + _text(f'Pausiert am {datetime.now().strftime("%d.%m.%Y um %H:%M Uhr")}.', muted=True)
    )
    return _send_mail(to_email, "Copy Trading pausiert — FirstClass Copy Trading", _wrap_html("Copy Trading pausiert", content))


def send_resume_email(to_email: str, first_name: str) -> bool:
    """Bestaetigung: Copy Trading fortgesetzt."""
    content = (
        _heading("Copy Trading wieder aktiv ✅")
        + _text(f"Hi {first_name}, dein Copy Trading wurde erfolgreich fortgesetzt. Ab sofort werden wieder alle Trades auf deinen Account gespiegelt.")
        + _button(f"{BASE_URL}/dashboard", "Zum Dashboard")
        + _divider()
        + _text(f'Fortgesetzt am {datetime.now().strftime("%d.%m.%Y um %H:%M Uhr")}.', muted=True)
    )
    return _send_mail(to_email, "Copy Trading wieder aktiv — FirstClass Copy Trading", _wrap_html("Copy Trading aktiv", content))
