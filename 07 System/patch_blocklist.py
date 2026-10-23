#!/usr/bin/env python3
"""
Blocklist-Feature Patch — dauerhafte Sperre einzelner E-Mails (kein Re-Signup / kein Re-Onboarding).
Patcht: db.py (Tabelle + Helper), routes/webhook_routes.py (_handle_payment Gate),
routes/welcome_routes.py (GET + POST Gate).
Anker-basiert mit Assertions (genau 1 Treffer). Erstellt Backups. Idempotent (bricht ab, wenn schon gepatcht).
"""
import re, shutil, sys, time

STAMP = "blocklist_20260730"
BASE = "/home/botuser/dashboard"

def patch(path, old, new, label):
    with open(path, "r", encoding="utf-8") as f:
        src = f.read()
    if new.strip().split("\n")[0] in src and "BLOCKLIST" in new and "BLOCKLIST" in src:
        print(f"[SKIP] {label}: schon gepatcht")
        return src, False
    n = src.count(old)
    assert n == 1, f"[FAIL] {label}: Anker {n}x gefunden (erwartet 1)"
    shutil.copy(path, f"{path}.bak_{STAMP}")
    src2 = src.replace(old, new, 1)
    with open(path, "w", encoding="utf-8") as f:
        f.write(src2)
    print(f"[OK] {label} gepatcht (Backup .bak_{STAMP})")
    return src2, True

# ---------------------------------------------------------------- db.py
db_path = f"{BASE}/db.py"
patch(
    db_path,
    '''    # pending_payments: Name-Spalten hinzufuegen (fuer Payment-First Flow)''',
    '''    # BLOCKLIST — dauerhaft gesperrte E-Mails (kein Re-Signup / Re-Onboarding moeglich)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS blocklist (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL UNIQUE,
            telegram_user_id TEXT,
            reason TEXT,
            created_at TEXT NOT NULL
        )
    """)

    # pending_payments: Name-Spalten hinzufuegen (fuer Payment-First Flow)''',
    "db.py: blocklist-Tabelle",
)
patch(
    db_path,
    '''def get_db() -> Database:''',
    '''def is_email_blocked(db, email: str) -> bool:
    """BLOCKLIST: True, wenn diese E-Mail dauerhaft gesperrt ist."""
    if not email:
        return False
    try:
        row = db._conn.execute(
            "SELECT 1 FROM blocklist WHERE email = ?", (email.strip().lower(),)
        ).fetchone()
        return row is not None
    except Exception:
        return False


def get_db() -> Database:''',
    "db.py: is_email_blocked Helper",
)

# ---------------------------------------------------------------- webhook_routes.py
wh_path = f"{BASE}/routes/webhook_routes.py"
patch(
    wh_path,
    "from db import get_db\n",
    "from db import get_db, is_email_blocked\n",
    "webhook: import is_email_blocked",
)
patch(
    wh_path,
    '''    # User per E-Mail finden
    user = db.get_dashboard_user_by_email(email.lower().strip())''',
    '''    # BLOCKLIST — dauerhaft gesperrte E-Mail: NICHT onboarden, keine Vormerkung, keine Mail
    if is_email_blocked(db, email):
        logger.warning(f"[WEBHOOK] [BLOCKLIST] Zahlung fuer gesperrte E-Mail {email} — ignoriert (kein Onboarding)")
        return JSONResponse({"status": "ok", "message": "Email blocklisted"})

    # User per E-Mail finden
    user = db.get_dashboard_user_by_email(email.lower().strip())''',
    "webhook: _handle_payment Gate",
)

# ---------------------------------------------------------------- welcome_routes.py
wc_path = f"{BASE}/routes/welcome_routes.py"
patch(
    wc_path,
    "from db import get_db\n",
    "from db import get_db, is_email_blocked\n",
    "welcome: import is_email_blocked",
)
# GET /welcome — nach db = get_db(), vor "Bereits registriert?"
patch(
    wc_path,
    '''    db = get_db()

    # Bereits registriert?
    existing = db.get_dashboard_user_by_email(email)
    if existing:
        return RedirectResponse(url="/login")''',
    '''    db = get_db()

    # BLOCKLIST — dauerhaft gesperrt: keine Registrierung moeglich
    if is_email_blocked(db, email):
        return templates.TemplateResponse(request, "welcome.html", {
            "error": "Für diese E-Mail-Adresse ist keine Registrierung möglich. Bei Fragen wende dich an den Support.",
            "email": "",
            "tier": "",
        })

    # Bereits registriert?
    existing = db.get_dashboard_user_by_email(email)
    if existing:
        return RedirectResponse(url="/login")''',
    "welcome: GET Gate",
)
# POST /welcome — nach "db = get_db()" (die Instanz im POST-Handler)
patch(
    wc_path,
    '''    db = get_db()

    # Pending Payment re-validieren
    pp = db._conn.execute(''',
    '''    db = get_db()

    # BLOCKLIST — dauerhaft gesperrt: Registrierung verweigern
    if is_email_blocked(db, email):
        ctx["error"] = "Für diese E-Mail-Adresse ist keine Registrierung möglich. Bei Fragen wende dich an den Support."
        return templates.TemplateResponse(request, "welcome.html", ctx)

    # Pending Payment re-validieren
    pp = db._conn.execute(''',
    "welcome: POST Gate",
)

print("ALLE PATCHES DURCH.")
