"""(C) Read-only Tools fuer den AI-Support-Agent.

Alle Funktionen LESEN nur. Kein Schreibzugriff, keine Telegram-Aktion ausser
getChatMember (ebenfalls lesend).

CLI-Test:  cd /home/botuser/scripts && python3 support_tools.py <telegram_id>
           cd /home/botuser/scripts && python3 support_tools.py --email <adresse>
"""
import os
import sys
import json
import sqlite3
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BOTDIR = os.path.join("..", "copy-trading-bot")
DB = os.path.join(BOTDIR, "copy_trading.db")
ENVF = os.path.join(BOTDIR, ".env")
PRODUCTS = ("517561", "517562")

# --------------------------------------------------------------------------
# Abo-Klassifizierung — HARTE WHITELIST, kein Raten.
# Am 2026-09-25 gegen alle echten Ablefy-Payloads unserer Produkte verifiziert.
# NIEMALS am monatlichen Betrag festmachen: 610909/616171 werden monatlich
# abgebucht, sind aber 12 Monate gebunden (Falle Patrick Sigl).
# --------------------------------------------------------------------------
PLAN_MONAT = {"610907"}
PLAN_JAHR = {"610909", "616171", "614741", "616295"}


def _env():
    env = {}
    try:
        with open(ENVF, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    except Exception:
        pass
    return env


ENV = _env()


def _con():
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True, timeout=10)
    con.row_factory = sqlite3.Row
    return con


def _tg(method, **params):
    url = f"https://api.telegram.org/bot{ENV.get('TELEGRAM_BOT_TOKEN','')}/{method}"
    try:
        data = urllib.parse.urlencode(params).encode()
        with urllib.request.urlopen(url, data=data, timeout=15) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"ok": False, "error": str(e)}


def _norm_mail(addr):
    """gmail.com und googlemail.com sind dieselbe Mailbox (Falle Pawel)."""
    a = (addr or "").strip().lower()
    return a.replace("@googlemail.com", "@gmail.com")


# --------------------------------------------------------------------------

def resolve_kunde(telegram_user_id=None, email=None):
    """Kunden identifizieren.

    Rueckgabe enthaelt 'identified_by':
      'telegram_id'   -> sicher (Nachricht kam aus diesem Account)
      'email_claimed' -> NUR behauptet. Keine sensiblen Daten herausgeben!
    """
    con = _con()
    row = None
    how = None

    if telegram_user_id:
        row = con.execute(
            "SELECT d.*, c.name AS kundenname, c.is_active "
            "FROM dashboard_users d LEFT JOIN customers c ON c.id = d.customer_id "
            "WHERE d.telegram_chat_id = ?", (str(telegram_user_id),)).fetchone()
        if row:
            how = "telegram_id"

    if row is None and email:
        n = _norm_mail(email)
        row = con.execute(
            "SELECT d.*, c.name AS kundenname, c.is_active "
            "FROM dashboard_users d LEFT JOIN customers c ON c.id = d.customer_id "
            "WHERE replace(lower(d.email),'@googlemail.com','@gmail.com') = ?",
            (n,)).fetchone()
        if row:
            how = "email_claimed"

    con.close()
    if row is None:
        return {"gefunden": False,
                "hinweis": "Kein Account gefunden. Bei Google-Adressen auch die "
                           "googlemail-Variante pruefen; Telegram-Anzeigename "
                           "kann vom Klarnamen abweichen."}

    d = dict(row)
    return {
        "gefunden": True,
        "identified_by": how,
        "dashboard_user_id": d.get("id"),
        "customer_id": d.get("customer_id"),
        "email": d.get("email"),
        "name": d.get("kundenname"),
        "tier": d.get("product_tier"),
        "email_verifiziert": bool(d.get("email_verified")),
        "aktiv": bool(d.get("is_active")),
        "payment_status": d.get("payment_status"),
        "telegram_id": d.get("telegram_chat_id") or None,
        "telegram_username": d.get("telegram_username") or None,
        "invite_link": d.get("telegram_invite_link") or None,
        "lifetime_free": (str(d.get("ablefy_order_id") or "") == "LIFETIME-FREE"),
    }


def get_kundenstatus(telegram_user_id=None, email=None):
    """Kontostatus inkl. anstehendem Zugangsentzug."""
    k = resolve_kunde(telegram_user_id, email)
    if not k.get("gefunden"):
        return k

    con = _con()
    r = con.execute(
        "SELECT revoke_at, status, mode, reason FROM scheduled_access_revocations "
        "WHERE dashboard_user_id = ? AND status = 'pending' "
        "ORDER BY revoke_at LIMIT 1", (k["dashboard_user_id"],)).fetchone()
    con.close()

    k["zugang_endet_am"] = r["revoke_at"] if r else None
    k["kuendigung_vorgemerkt"] = bool(r)
    return k


def get_abo_details(telegram_user_id=None, email=None):
    """Abo-Typ, bezahlt-bis und Zahlungshistorie — aus den Ablefy-Payloads.

    Abo-Typ NUR ueber die Plan-ID. 'bezahlt bis' IMMER aus
    payments_schedule_next_rate_date (access_valid_until ist bei
    Verlaengerungen haeufig veraltet — belegt am 2026-09-11).
    """
    k = resolve_kunde(telegram_user_id, email)
    if not k.get("gefunden"):
        return k

    mail = _norm_mail(k["email"])
    con = _con()
    # created_at der TABELLE mitlesen: das Feld im Payload ist das
    # Order-Datum, nicht der Zeitpunkt des Events (2026-09-25 verifiziert).
    rows = con.execute(
        "SELECT created_at AS event_ts, payload FROM webhook_logs "
        "WHERE replace(lower(payload),'@googlemail.com','@gmail.com') LIKE ? "
        "ORDER BY id DESC LIMIT 400", (f"%{mail}%",)).fetchall()
    con.close()

    plan_ids, plan_name = set(), None
    order_id = bezahlt_bis = letzte_zahlung = zahlungsart = None
    zahlungen, gekuendigt_am, gueltig_bis = [], None, None

    for r in rows:
        try:
            p = json.loads(r["payload"])
        except Exception:
            continue

        prod = str(p.get("product", {}).get("id")
                   or p.get("product", {}).get("product_id") or "")
        if prod not in PRODUCTS:
            continue

        pp = p.get("pricing_plan") or {}
        if pp.get("id"):
            # Kombinierte Orders liefern eine Liste: "611451,610909"
            for pid in str(pp["id"]).split(","):
                plan_ids.add(pid.strip())
            plan_name = plan_name or pp.get("name")

        order_id = order_id or p.get("order_id")
        bezahlt_bis = bezahlt_bis or p.get("payments_schedule_next_rate_date")
        zahlungsart = zahlungsart or p.get("payment_method")

        # Nur ECHTE Zahlungen zaehlen. payment_state='active_subscription'
        # taugt nicht als Kriterium — das tragen auch Nicht-Zahlungs-Events.
        if p.get("event") == "payment.successful":
            d = p.get("success_date_utc") or p.get("success_date")
            if d and d not in zahlungen:
                zahlungen.append(d)
                letzte_zahlung = letzte_zahlung or d

        if p.get("event") == "order.subscription.canceled":
            gekuendigt_am = gekuendigt_am or r["event_ts"]
        acc = p.get("access") or {}
        if acc.get("access_valid_until"):
            gueltig_bis = gueltig_bis or acc["access_valid_until"]

    # Konservativ: enthaelt die Order IRGENDEIN Jahresabo -> Jahresabo.
    # Lieber faelschlich "nur zum Laufzeitende" sagen (Kunde widerspricht,
    # Mensch uebernimmt) als faelschlich "sofort kuendbar" zusagen.
    if plan_ids & PLAN_JAHR:
        typ, kuendbar = "jahresabo", "nur zum Laufzeitende"
    elif plan_ids & PLAN_MONAT:
        typ, kuendbar = "monatsabo", "zum Ende des bezahlten Monats"
    else:
        typ, kuendbar = "unbekannt", "UNKLAR — eskalieren, nicht raten"

    k.update({
        "abo_typ": typ,
        "kuendbar": kuendbar,
        "plan_ids": sorted(plan_ids) or None,
        "plan_name": plan_name,
        "order_id": order_id,
        "bezahlt_bis": bezahlt_bis,
        "letzte_zahlung": letzte_zahlung,
        "anzahl_zahlungen": len(zahlungen),
        "zahlungsart": zahlungsart,
        "gekuendigt_am": gekuendigt_am,
        "ablefy_gueltig_bis": gueltig_bis,
    })
    return k


def check_gruppen_mitgliedschaft(telegram_user_id=None, email=None):
    """Mitgliedschaft in Hauptgruppe und Scalp-Channel."""
    k = resolve_kunde(telegram_user_id, email)
    if not k.get("gefunden"):
        return k
    tg_id = k.get("telegram_id") or telegram_user_id
    if not tg_id:
        return {**k, "hinweis": "Keine Telegram-ID hinterlegt — Status nicht pruefbar."}

    out = {}
    for label, chat in (("hauptgruppe", ENV.get("SIGNAL_PAID_GROUP_ID")),
                        ("scalp", ENV.get("SIGNAL_SCALP_GROUP_ID"))):
        if not chat:
            continue
        r = _tg("getChatMember", chat_id=chat, user_id=tg_id)
        out[label] = (r.get("result", {}).get("status")
                      if r.get("ok") else f"unbekannt ({r.get('description') or r.get('error')})")
    k["mitgliedschaft"] = out
    return k


def get_zahlungsseite(telegram_user_id=None, email=None):
    """Ablefy-Zahlungsverwaltung zur Bestellung (Rechnungen, Zahlungsmittel).

    SICHERHEIT: Nur herausgeben, wenn der Kunde ueber seine verknuepfte
    Telegram-ID identifiziert ist. Eine blosse E-Mail-Behauptung reicht NICHT —
    der Link fuehrt auf Bestell- und Zahlungsdaten.
    """
    k = resolve_kunde(telegram_user_id, email)
    if not k.get("gefunden"):
        return k
    if k.get("identified_by") != "telegram_id":
        return {"gefunden": True, "verweigert": True,
                "grund": "Kunde ist nur per E-Mail-Behauptung identifiziert. "
                         "Zahlungslink NICHT herausgeben — an Mensch uebergeben."}

    mail = _norm_mail(k["email"])
    con = _con()
    rows = con.execute(
        "SELECT payload FROM webhook_logs "
        "WHERE replace(lower(payload),'@googlemail.com','@gmail.com') LIKE ? "
        "ORDER BY id DESC LIMIT 200", (f"%{mail}%",)).fetchall()
    con.close()

    for r in rows:
        try:
            p = json.loads(r["payload"])
        except Exception:
            continue
        prod = str(p.get("product", {}).get("id")
                   or p.get("product", {}).get("product_id") or "")
        if prod not in PRODUCTS:
            continue
        if p.get("success_link"):
            return {"gefunden": True, "zahlungsseite": p["success_link"],
                    "rechnung_pdf": p.get("invoice_link"),
                    "rechnungsnummer": p.get("invoice_number")}
    return {"gefunden": True, "zahlungsseite": None,
            "hinweis": "Kein success_link in den Ablefy-Events gefunden."}


# --------------------------------------------------------------------------
if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)
    if args[0] == "--email":
        kw = {"email": args[1]}
    else:
        kw = {"telegram_user_id": args[0]}

    print(f"\n### {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC — Abfrage {kw}\n")
    for fn in (get_kundenstatus, get_abo_details,
               check_gruppen_mitgliedschaft, get_zahlungsseite):
        print(f"--- {fn.__name__} ---")
        try:
            print(json.dumps(fn(**kw), indent=2, ensure_ascii=False,
                             default=str))
        except Exception as e:
            print(f"FEHLER: {type(e).__name__}: {e}")
        print()
