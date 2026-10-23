"""(C) Stufe 1 — Migration der Einzel-Timer in eine Tabelle.

Liest alle AUSSTEHENDEN systemd-Kick-Timer, parst die zugehoerigen Scripts
und legt daraus Zeilen in scheduled_access_revocations an.

  --dry     nur anzeigen, nichts schreiben (Default)
  --apply   Tabelle anlegen + Zeilen einfuegen

Aufruf:  cd /home/botuser/scripts && python3 migrate_kick_timers.py --dry
"""
import os
import re
import sys
import glob
import sqlite3
import subprocess
from datetime import datetime, timezone

DB = "/home/botuser/copy-trading-bot/copy_trading.db"
UNITDIR = "/etc/systemd/system"
APPLY = "--apply" in sys.argv

DDL = """
CREATE TABLE IF NOT EXISTS scheduled_access_revocations (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    dashboard_user_id INTEGER,
    customer_id       TEXT,
    email             TEXT NOT NULL,
    name              TEXT,
    revoke_at         TEXT NOT NULL,
    valid_until       TEXT,
    invite_link       TEXT,
    telegram_user_id  INTEGER,
    mode              TEXT NOT NULL DEFAULT 'permanent',
    source            TEXT NOT NULL DEFAULT 'support',
    reason            TEXT,
    status            TEXT NOT NULL DEFAULT 'pending',
    created_at        TEXT NOT NULL,
    executed_at       TEXT,
    result            TEXT,
    legacy_unit       TEXT
);
CREATE INDEX IF NOT EXISTS idx_sar_due ON scheduled_access_revocations(status, revoke_at);
CREATE INDEX IF NOT EXISTS idx_sar_user ON scheduled_access_revocations(dashboard_user_id);
CREATE UNIQUE INDEX IF NOT EXISTS idx_sar_unit ON scheduled_access_revocations(legacy_unit)
    WHERE legacy_unit IS NOT NULL;
"""


def pending_timers():
    """Timer mit einem NEXT-Datum in der Zukunft."""
    out = subprocess.run(
        ["systemctl", "list-timers", "--all", "--no-pager", "--output=json"],
        capture_output=True, text=True).stdout
    found = []
    try:
        import json
        for t in json.loads(out):
            unit = t.get("unit") or ""
            nxt = t.get("next")
            if unit.startswith("kick-") and nxt:
                found.append(unit)
    except Exception:
        # Fallback: Textausgabe parsen
        txt = subprocess.run(
            ["systemctl", "list-timers", "--all", "--no-pager"],
            capture_output=True, text=True).stdout
        for line in txt.splitlines():
            m = re.search(r"(kick-[\w.-]+)\.timer", line)
            if m and not line.strip().startswith("-"):
                found.append(m.group(1) + ".timer")
    return sorted(set(found))


def oncalendar(unit):
    p = os.path.join(UNITDIR, unit)
    if not os.path.exists(p):
        return None
    m = re.search(r"OnCalendar=(.+)", open(p).read())
    return m.group(1).strip() if m else None


def script_for(unit):
    svc = os.path.join(UNITDIR, unit.replace(".timer", ".service"))
    if not os.path.exists(svc):
        return None
    m = re.search(r"ExecStart=(\S+)", open(svc).read())
    if not m:
        return None
    path = m.group(1)
    if path.endswith("bash") or path.endswith("sh"):
        m2 = re.search(r"ExecStart=\S+\s+(\S+)", open(svc).read())
        if m2:
            path = m2.group(1)
    return path if os.path.exists(path) else None


def parse_script(path):
    src = open(path, encoding="utf-8", errors="replace").read()

    def val(name):
        m = re.search(rf'^{name}=("?)([^"\n]*)\1', src, re.M)
        return m.group(2).strip() if m else None

    # Aeltere Scripts nutzen G_EMAIL/G_UNTIL statt EMAIL/VALID_UNTIL,
    # und drei haben kein DUID, sondern eine fest eingetragene TG_ID.
    tg = val("TG_ID")
    tg = tg if (tg or "").isdigit() else None

    return {
        "duid": val("DUID"),
        "email": val("EMAIL") or val("G_EMAIL"),
        "cust": val("CUST"),
        "invite": val("INVITE"),
        "valid_until": val("VALID_UNTIL") or val("G_UNTIL"),
        "tg_id": tg,
        "mode": "kulanz" if "unbanChatMember" in src else "permanent",
        "has_grant_check": "REGRANT" in src,
    }


rows = []
for unit in pending_timers():
    cal = oncalendar(unit)
    script = script_for(unit)
    if not script:
        print(f"!! {unit}: Script nicht gefunden")
        continue
    d = parse_script(script)
    if not d["email"]:
        print(f"!! {unit}: EMAIL nicht parsebar ({script})")
        continue
    revoke_at = (cal or "").split()[0] if cal else None
    rows.append({**d, "unit": unit, "revoke_at": revoke_at, "cal": cal})

con0 = sqlite3.connect(DB, timeout=10)

# DUID nachschlagen, wo es im Script fehlt (ueber die customer_id)
for r in rows:
    if not r["duid"] and r["cust"]:
        row = con0.execute(
            "SELECT id FROM dashboard_users WHERE customer_id=?",
            (r["cust"],)).fetchone()
        if row:
            r["duid"] = str(row[0])
            r["duid_resolved"] = True

# Telegram-ID: DB gewinnt, Script-Wert ist Fallback
for r in rows:
    db_tg = None
    if r["duid"]:
        row = con0.execute(
            "SELECT COALESCE(telegram_chat_id,'') FROM dashboard_users WHERE id=?",
            (r["duid"],)).fetchone()
        db_tg = (row[0] or None) if row else None
    r["tg_db"] = db_tg
    r["tg_final"] = db_tg or r["tg_id"]
con0.close()

print(f"\n{'DATUM':<12} {'MODUS':<10} {'DUID':<7} {'TG-ID':<13} {'EMAIL':<34} UNIT")
print("-" * 125)
for r in sorted(rows, key=lambda x: x["revoke_at"] or ""):
    tg = r["tg_final"] or "FEHLT"
    src = "" if r["tg_db"] else ("(aus Script)" if r["tg_id"] else "")
    duid = (r["duid"] or "?") + ("*" if r.get("duid_resolved") else "")
    print(f"{r['revoke_at'] or '?':<12} {r['mode']:<10} {duid:<7} "
          f"{tg:<13} {(r['email'] or '?')[:33]:<34} {r['unit']} {src}")
print(f"\n{len(rows)} ausstehende Timer gefunden.   "
      f"(* = DUID ueber customer_id ermittelt)")

fehlend = [r for r in rows
           if not r["valid_until"] or not r["cust"] or not r["duid"]
           or not r["tg_final"]]
if fehlend:
    print("\n!! Unvollstaendig (bitte pruefen):")
    for r in fehlend:
        print(f"   {r['unit']}: valid_until={r['valid_until']} "
              f"cust={r['cust']} duid={r['duid']} tg={r['tg_final']}")
else:
    print("\nAlle Datensaetze vollstaendig.")

if not APPLY:
    print("\n(DRY-RUN — nichts geschrieben. Mit --apply ausfuehren.)")
    sys.exit(0)

con = sqlite3.connect(DB, timeout=10)
con.execute("PRAGMA busy_timeout=5000")
con.executescript(DDL)

now = datetime.now(timezone.utc).isoformat(timespec="seconds")
ins = skip = 0
for r in rows:
    name = None
    if r["duid"]:
        cur = con.execute(
            "SELECT COALESCE(c.name, d.email) FROM dashboard_users d "
            "LEFT JOIN customers c ON c.id = d.customer_id WHERE d.id=?",
            (r["duid"],))
        row = cur.fetchone()
        name = row[0] if row else None
    try:
        con.execute(
            "INSERT INTO scheduled_access_revocations "
            "(dashboard_user_id, customer_id, email, name, revoke_at, "
            " valid_until, invite_link, telegram_user_id, mode, source, "
            " reason, status, created_at, legacy_unit) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (int(r["duid"]) if r["duid"] else None, r["cust"], r["email"],
             name, r["revoke_at"], r["valid_until"], r["invite"],
             int(r["tg_final"]) if r["tg_final"] else None, r["mode"],
             "support", f"Migriert aus {r['unit']}", "pending", now,
             r["unit"]))
        ins += 1
    except sqlite3.IntegrityError:
        skip += 1

con.commit()
total = con.execute(
    "SELECT COUNT(*) FROM scheduled_access_revocations").fetchone()[0]
con.close()
print(f"\nEingefuegt: {ins} | uebersprungen (schon da): {skip} | "
      f"Tabelle gesamt: {total}")
