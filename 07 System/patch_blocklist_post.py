#!/usr/bin/env python3
"""Nachtrag: POST /welcome Blocklist-Gate (wurde im Hauptpatch faelschlich uebersprungen)."""
path = "/home/botuser/dashboard/routes/welcome_routes.py"
with open(path, "r", encoding="utf-8") as f:
    src = f.read()

old = '''    db = get_db()

    # Pending Payment re-validieren
    pp = db._conn.execute('''
new = '''    db = get_db()

    # BLOCKLIST — dauerhaft gesperrt: Registrierung verweigern
    if is_email_blocked(db, email):
        ctx["error"] = "Für diese E-Mail-Adresse ist keine Registrierung möglich. Bei Fragen wende dich an den Support."
        return templates.TemplateResponse(request, "welcome.html", ctx)

    # Pending Payment re-validieren
    pp = db._conn.execute('''

assert src.count(old) == 1, f"Anker {src.count(old)}x (erwartet 1)"
assert new not in src, "POST-Gate schon vorhanden"
with open(path, "w", encoding="utf-8") as f:
    f.write(src.replace(old, new, 1))
print("[OK] POST-Gate nachgetragen")
