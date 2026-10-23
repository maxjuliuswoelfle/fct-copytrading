"""(C) Taeglicher Zugangsentzug — ersetzt die 49 Einzel-Timer.

Arbeitet alle faelligen Zeilen aus scheduled_access_revocations ab.

  (ohne Flag)  DRY-RUN: zeigt nur, was passieren wuerde
  --apply      fuehrt aus

Aufruf:  cd /home/botuser/scripts && python3 revoke_access_daily.py --apply

Logik uebernommen aus den bewaehrten Einzel-Scripts, plus zwei Verbesserungen:
  1. Endstatus nach dem Ban wird per getChatMember GEGENGEPRUEFT und notfalls
     wiederholt. Lehre aus Micha73 (2026-09-24): die API meldete ok:true,
     der Kunde stand aber weiter auf "kicked" statt "left".
  2. Fehlende telegram_chat_id wird ein Tabellen-Status (needs_manual) statt
     einer Admin-DM. Lehre aus Tobias Falke: die DM ging unter, er sass
     3 Tage laenger drin. Offene Faelle bleiben jetzt sichtbar.
"""
import os
import sys
import json
import time
import sqlite3
import urllib.parse
import urllib.request
from datetime import datetime, timezone

APPLY = "--apply" in sys.argv
BOTDIR = os.path.join("..", "copy-trading-bot")
DB = os.path.join(BOTDIR, "copy_trading.db")
ENVF = os.path.join(BOTDIR, ".env")
LOG = "revoke_access_daily.log"
PRODUCTS = ("517561", "517562")


def log(msg):
    line = f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} {msg}"
    print(line)
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def load_env():
    env = {}
    with open(ENVF, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    return env


ENV = load_env()
TOKEN = ENV.get("TELEGRAM_BOT_TOKEN", "")
MAIN = ENV.get("SIGNAL_PAID_GROUP_ID", "")
SCALP = ENV.get("SIGNAL_SCALP_GROUP_ID", "")
ADMIN = ENV.get("TELEGRAM_CHAT_ID", "")


def tg(method, **params):
    """Telegram-API-Aufruf. Gibt dict zurueck, wirft nie."""
    url = f"https://api.telegram.org/bot{TOKEN}/{method}"
    data = urllib.parse.urlencode(params).encode()
    try:
        with urllib.request.urlopen(url, data=data, timeout=20) as r:
            return json.loads(r.read().decode())
    except Exception as e:
        return {"ok": False, "error": str(e)}


def member_status(chat_id, user_id):
    r = tg("getChatMember", chat_id=chat_id, user_id=user_id)
    if r.get("ok"):
        return r.get("result", {}).get("status")
    return None


def enforce(chat_id, user_id, mode):
    """Ban (permanent) bzw. Ban+Unban (kulanz), mit Gegenpruefung.

    Liefert (erfolg, endstatus).
    """
    want = "kicked" if mode == "permanent" else ("left", "kicked")
    for versuch in range(1, 4):
        tg("banChatMember", chat_id=chat_id, user_id=user_id)
        if mode == "kulanz":
            time.sleep(1.5)
            tg("unbanChatMember", chat_id=chat_id, user_id=user_id,
               only_if_banned="true")
        time.sleep(2.5)
        st = member_status(chat_id, user_id)
        if mode == "permanent" and st == "kicked":
            return True, st
        if mode == "kulanz" and st == "left":
            return True, st
        log(f"    Versuch {versuch}: Status '{st}' — wiederhole")
    return False, st


def had_regrant(con, email, valid_until):
    """Hat der Kunde nach der Kuendigung neu gekauft?

    Produkt-Filter ueber BEIDE Payload-Varianten. NICHT nach Zeitstempel
    filtern — das Kuendigungs-Event traegt selbst access_type=GRANT.
    """
    if not valid_until:
        return False, None
    sql = """
        SELECT COALESCE(MAX(json_extract(payload,'$.access.access_valid_until')),'')
        FROM webhook_logs
        WHERE lower(payload) LIKE ?
          AND json_extract(payload,'$.access.access_type')='GRANT'
          AND COALESCE(
                CAST(json_extract(payload,'$.product.id') AS TEXT),
                CAST(json_extract(payload,'$.product.product_id') AS TEXT),
                '') IN (?,?)
          AND COALESCE(json_extract(payload,'$.access.access_valid_until'),'') > ?
    """
    row = con.execute(sql, (f"%{email.lower()}%", *PRODUCTS,
                            valid_until)).fetchone()
    return (bool(row and row[0]), row[0] if row else None)


def main():
    heute = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    # --date YYYY-MM-DD: Stichtag simulieren (nur fuer Tests, nur im DRY-RUN)
    for i, a in enumerate(sys.argv):
        if a == "--date" and i + 1 < len(sys.argv):
            if APPLY:
                print("ABBRUCH: --date ist im APPLY-Modus nicht erlaubt.")
                return
            heute = sys.argv[i + 1]
    modus = "APPLY" if APPLY else "DRY-RUN"
    log(f"=== Lauf {modus} — faellig bis {heute} ===")

    if not TOKEN or not MAIN:
        log("ABBRUCH: TELEGRAM_BOT_TOKEN oder SIGNAL_PAID_GROUP_ID fehlt")
        return

    con = sqlite3.connect(DB, timeout=15)
    con.execute("PRAGMA busy_timeout=10000")

    faellig = con.execute(
        "SELECT id, dashboard_user_id, customer_id, email, name, revoke_at, "
        "       valid_until, invite_link, telegram_user_id, mode, source "
        "FROM scheduled_access_revocations "
        "WHERE status='pending' AND revoke_at <= ? ORDER BY revoke_at",
        (heute,)).fetchall()

    if not faellig:
        log("Nichts faellig.")
        con.close()
        return

    log(f"{len(faellig)} faellige Eintraege")

    for (rid, duid, cust, email, name, revoke_at, valid_until, invite,
         tg_row, mode, source) in faellig:
        try:
            log(f"[{rid}] {email} ({name or '?'}) faellig seit {revoke_at}, "
                f"modus={mode}, quelle={source}")

            # 1) Hat er zwischenzeitlich neu gekauft?
            regrant, bis = had_regrant(con, email, valid_until)
            if regrant:
                log(f"    ABBRUCH: neuerer GRANT bis {bis} -> kein Ban")
                if APPLY:
                    con.execute(
                        "UPDATE scheduled_access_revocations SET status=?, "
                        "executed_at=?, result=? WHERE id=?",
                        ("aborted_regrant",
                         datetime.now(timezone.utc).isoformat(timespec="seconds"),
                         f"Neuer GRANT bis {bis}", rid))
                    con.commit()
                    if ADMIN:
                        tg("sendMessage", chat_id=ADMIN,
                           text=f"[KICK ABGEBROCHEN] {email} sollte heute den "
                                f"Zugang verlieren — hat laut Ablefy aber wieder "
                                f"gezahlt (gueltig bis {bis}). Kein Ban.")
                continue

            # 2) Telegram-ID: DB gewinnt, Tabellenwert ist Fallback
            tg_id = None
            if duid:
                row = con.execute(
                    "SELECT COALESCE(telegram_chat_id,'') FROM dashboard_users "
                    "WHERE id=?", (duid,)).fetchone()
                tg_id = (row[0] or None) if row else None
            tg_id = tg_id or tg_row

            if not tg_id:
                log("    KEINE Telegram-ID -> needs_manual")
                if APPLY:
                    con.execute(
                        "UPDATE scheduled_access_revocations SET status=?, "
                        "executed_at=?, result=? WHERE id=?",
                        ("needs_manual",
                         datetime.now(timezone.utc).isoformat(timespec="seconds"),
                         "Keine telegram_chat_id bekannt", rid))
                    con.commit()
                    if ADMIN:
                        tg("sendMessage", chat_id=ADMIN,
                           text=f"[MANUELL NOETIG] {email} ({name or '?'}) muss "
                                f"aus den Gruppen entfernt werden — keine "
                                f"Telegram-ID bekannt. Steht als 'needs_manual' "
                                f"in scheduled_access_revocations (id {rid}).")
                continue

            if not APPLY:
                for chat in (MAIN, SCALP):
                    st = member_status(chat, tg_id)
                    log(f"    [dry] chat {chat}: aktueller Status '{st}' "
                        f"-> wuerde {mode} anwenden")
                log(f"    [dry] wuerde Invite widerrufen + DB auf cancelled setzen")
                continue

            # 3) Durchsetzen
            ok_all = True
            for chat in (MAIN, SCALP):
                if not chat:
                    continue
                ok, st = enforce(chat, tg_id, mode)
                log(f"    chat {chat}: {'OK' if ok else 'FEHLER'} (Status '{st}')")
                ok_all = ok_all and ok

            # 4) Invite widerrufen
            if invite:
                r = tg("revokeChatInviteLink", chat_id=MAIN, invite_link=invite)
                log(f"    Invite widerrufen: ok={r.get('ok')}")

            # 5) DB-Updates
            if duid:
                con.execute("UPDATE dashboard_users SET payment_status='cancelled' "
                            "WHERE id=?", (duid,))
            if cust:
                con.execute("UPDATE customers SET is_active=0, "
                            "deactivated_at=CURRENT_TIMESTAMP WHERE id=?", (cust,))

            con.execute(
                "UPDATE scheduled_access_revocations SET status=?, executed_at=?, "
                "result=? WHERE id=?",
                ("done" if ok_all else "needs_manual",
                 datetime.now(timezone.utc).isoformat(timespec="seconds"),
                 "Ban bestaetigt" if ok_all else "Ban NICHT bestaetigt", rid))
            con.commit()

            if not ok_all and ADMIN:
                tg("sendMessage", chat_id=ADMIN,
                   text=f"[KICK UNSICHER] {email} ({name or '?'}) — Ban wurde "
                        f"nicht bestaetigt. Bitte manuell pruefen. "
                        f"Telegram-ID {tg_id}, Eintrag id {rid}.")

            log(f"    fertig: {'done' if ok_all else 'needs_manual'}")

        except Exception as e:
            log(f"    FEHLER bei id {rid}: {type(e).__name__}: {e}")

    con.close()
    log(f"=== Lauf {modus} beendet ===")


main()
