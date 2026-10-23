#!/usr/bin/env python3
"""
Kick bei Kuendigung — ein Script fuer alle Faelle.

Ersetzt die bisherigen 48 Einzel-Scripts (kick_vorname_nachname.sh).
Die dort von Hand recherchierten Angaben (dashboard_users-ID, customer_id,
Einladungslink, Ablefy-Enddatum, Telegram-ID) ermittelt dieses Script selbst.

AUFRUF (auf dem Copytrading-Server):
    cd /home/botuser/copy-trading-bot
    python3 kick.py anna.stadl@icloud.com              # Trockenlauf (Standard!)
    python3 kick.py anna.stadl@icloud.com --wirklich   # wirklich kicken
    python3 kick.py --id 433                           # per dashboard_users-ID
    python3 kick.py --telegram 1549027963              # per Telegram-ID
    python3 kick.py --faellige                         # alle zeigen, die dran waeren

SICHERHEITEN (aus den Einzel-Scripts uebernommen):
  1. Trockenlauf ist Standard — ohne --wirklich passiert NICHTS.
  2. Re-GRANT-Pruefung: Hat der Kunde nach der Kuendigung wieder gezahlt,
     wird NICHT gekickt, sondern gemeldet. (Faelle Lihua/Timo)
  3. Produkt-Filter: nur unsere Produkte 517561/517562 zaehlen. Ein Kauf von
     Accelerator oder Betreuung darf den Kick NICHT verhindern.
  4. Zugang muss ABGELAUFEN sein. Laeuft er noch, bricht das Script ab —
     auch wenn jemand es versehentlich aufruft.
  5. Mehrdeutige Treffer (gleiche E-Mail mehrfach) fuehren zum Abbruch,
     nie zu einer Auswahl auf gut Glueck.
  6. Jeder Schritt wird protokolliert; bei unsicherem Ergebnis geht ein
     Telegram-Hinweis an den Administrator.
"""
import argparse
import ast
import json
import os
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BOTDIR = "/home/botuser/copy-trading-bot"
DB_PFAD = os.path.join(BOTDIR, "copy_trading.db")
ENV_PFAD = os.path.join(BOTDIR, ".env")
LOG_PFAD = "/home/botuser/scripts/kick.log"
UNSERE_PRODUKTE = ("517561", "517562")
KULANZ_TAGE = 0            # Zugang muss abgelaufen sein; hier ggf. Puffer setzen


# ----------------------------------------------------------------- Grundlagen

def env_lesen() -> dict:
    d = {}
    with open(ENV_PFAD, encoding="utf-8") as f:
        for z in f:
            z = z.strip()
            if z and not z.startswith("#") and "=" in z:
                n, _, v = z.partition("=")
                d[n.strip()] = v.strip()
    return d


def protokoll(text: str) -> None:
    zeile = f"{datetime.now(timezone.utc):%Y-%m-%d %H:%M:%S} | {text}"
    print(text)
    try:
        os.makedirs(os.path.dirname(LOG_PFAD), exist_ok=True)
        with open(LOG_PFAD, "a", encoding="utf-8") as f:
            f.write(zeile + "\n")
    except OSError:
        pass


def tg(token: str, methode: str, **felder) -> dict:
    daten = urllib.parse.urlencode(felder).encode()
    url = f"https://api.telegram.org/bot{token}/{methode}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=daten), timeout=20) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"ok": False, "description": f"{type(e).__name__}: {e}"}


def admin_hinweis(env: dict, text: str) -> None:
    chat = env.get("TELEGRAM_CHAT_ID", "")
    if chat:
        tg(env.get("TELEGRAM_BOT_TOKEN", ""), "sendMessage", chat_id=chat, text=text)



def sonderfaelle() -> dict:
    """
    Liest die Ausnahmeliste NOTES direkt aus check_nichtzahler.py.

    Warum nicht hier pflegen: Es darf nur EINE Quelle geben. Traegt Max dort
    jemanden ein (TEAM/LIFETIME, Jahresabo ohne Abbuchung, interne Konten),
    wirkt das sofort auch hier — ohne dass jemand daran denken muss.

    Dieses Script hat beim ersten Test Rico Andres zum Kick freigegeben,
    obwohl er in NOTES als "NICHT kicken" steht. Genau das verhindert diese
    Kopplung.
    """
    pfad = os.path.join(BOTDIR, "check_nichtzahler.py")
    try:
        baum = ast.parse(open(pfad, encoding="utf-8").read())
    except Exception as e:
        print(f"  ⚠️  check_nichtzahler.py nicht lesbar ({e}).")
        print( "     ABBRUCH — ohne die Ausnahmeliste wird nicht gekickt.")
        sys.exit(1)
    for knoten in baum.body:
        if isinstance(knoten, ast.Assign):
            for ziel in knoten.targets:
                if isinstance(ziel, ast.Name) and ziel.id == "NOTES":
                    return {k.lower(): v for k, v in ast.literal_eval(knoten.value).items()}
    print("  ⚠️  Ausnahmeliste NOTES nicht gefunden — ABBRUCH.")
    sys.exit(1)


# ----------------------------------------------------------------- Kundensuche

def kunde_finden(con, email=None, duid=None, telegram=None) -> dict:
    if duid:
        bed, wert = "du.id = ?", duid
    elif telegram:
        bed, wert = "du.telegram_chat_id = ?", str(telegram)
    else:
        bed, wert = "lower(du.email) = lower(?)", email

    reihen = con.execute(f"""
        SELECT du.id, du.customer_id, du.email, du.telegram_chat_id,
               du.telegram_invite_link, du.payment_status, du.product_tier,
               c.first_name, c.last_name, c.is_active
          FROM dashboard_users du
          LEFT JOIN customers c ON c.id = du.customer_id
         WHERE {bed}
    """, (wert,)).fetchall()

    if not reihen:
        sys.exit(f"ABBRUCH: kein Kunde gefunden ({bed.split()[0]} = {wert})")
    if len(reihen) > 1:
        # Nie raten — das ist die Lehre aus den Namensverwechslungen.
        print(f"ABBRUCH: {len(reihen)} Treffer, nicht eindeutig:")
        for r in reihen:
            print(f"   id={r['id']}  {r['email']}  {r['first_name']} {r['last_name']}")
        sys.exit("Bitte mit --id eindeutig angeben.")
    return dict(reihen[0])


def zugang_bis(con, email: str) -> tuple:
    """Spaetestes Ablefy-Enddatum fuer UNSERE Produkte. (datum, anzahl_events)"""
    reihen = con.execute("""
        SELECT json_extract(payload,'$.access.access_valid_until') bis,
               json_extract(payload,'$.access.access_type') art,
               CAST(json_extract(payload,'$.product.product_id') AS TEXT) produkt,
               created_at
          FROM webhook_logs
         WHERE lower(payload) LIKE '%' || lower(?) || '%'
           AND json_extract(payload,'$.access.access_valid_until') IS NOT NULL
    """, (email,)).fetchall()

    eigene = [r for r in reihen if r["produkt"] in UNSERE_PRODUKTE]
    if not eigene:
        return None, 0
    spaetestes = max(r["bis"] for r in eigene if r["bis"])
    return spaetestes, len(eigene)


# ----------------------------------------------------------------- Hauptablauf

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("email", nargs="?", help="E-Mail des Kunden")
    ap.add_argument("--id", type=int, help="dashboard_users-ID")
    ap.add_argument("--telegram", help="Telegram-ID")
    ap.add_argument("--wirklich", action="store_true",
                    help="wirklich kicken (ohne das passiert NICHTS)")
    ap.add_argument("--faellige", action="store_true",
                    help="nur auflisten, wer faellig waere")
    ap.add_argument("--trotzdem", action="store_true",
                    help="auch kicken, wenn der Zugang noch laeuft (sehr selten noetig)")
    a = ap.parse_args()

    env = env_lesen()
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    gruppen = [("Signal-Gruppe", env.get("SIGNAL_PAID_GROUP_ID", "")),
               ("Scalp-Gruppe", env.get("SIGNAL_SCALP_GROUP_ID", ""))]

    con = sqlite3.connect(f"file:{DB_PFAD}?mode={'rw' if a.wirklich else 'ro'}", uri=True)
    con.row_factory = sqlite3.Row

    if a.faellige:
        liste_faellige(con)
        return

    if not (a.email or a.id or a.telegram):
        ap.error("E-Mail, --id oder --telegram angeben (oder --faellige)")

    k = kunde_finden(con, a.email, a.id, a.telegram)
    name = f"{k['first_name'] or ''} {k['last_name'] or ''}".strip() or "(ohne Namen)"
    bis, anzahl = zugang_bis(con, k["email"])
    jetzt = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    print(f"\n{'='*66}")
    print(f"  {name}   <{k['email']}>")
    print(f"{'='*66}")
    print(f"  dashboard_users-ID : {k['id']}")
    print(f"  Produkt-Stufe      : {k['product_tier']}")
    print(f"  Zahlungsstatus     : {k['payment_status']}")
    print(f"  Telegram-ID        : {k['telegram_chat_id'] or '— FEHLT —'}")
    print(f"  Zugang gueltig bis : {bis or '— kein Ablefy-Event —'}  ({anzahl} Ereignisse)")
    print(f"  jetzt              : {jetzt}")

    # --- Sicherheit 0: steht er auf der Ausnahmeliste? ---
    ausnahmen = sonderfaelle()
    if k["email"].lower() in ausnahmen:
        print(f"\n  ⛔ ABBRUCH: steht auf der Ausnahmeliste in check_nichtzahler.py")
        print(f"     Grund: {ausnahmen[k['email'].lower()]}")
        print( "     Dieser Kunde wird NICHT gekickt.")
        sys.exit(1)

    # --- Sicherheit 4: laeuft der Zugang noch? ---
    if bis and bis > jetzt and not a.trotzdem:
        print(f"\n  ⛔ ABBRUCH: Der Zugang laeuft noch bis {bis}.")
        print( "     Dieser Kunde darf NICHT gekickt werden.")
        print( "     (Nur mit --trotzdem uebergehen, wenn du sicher bist.)")
        sys.exit(1)
    if not bis:
        print("\n  ⚠️  Kein Ablefy-Ereignis fuer unsere Produkte gefunden.")
        print( "     Vor dem Kick von Hand pruefen — Abbruch.")
        sys.exit(1)

    # --- Sicherheit 2+3: hat er nach der Kuendigung wieder gezahlt? ---
    spaeter = con.execute("""
        SELECT COUNT(*) n, COALESCE(MAX(json_extract(payload,'$.access.access_valid_until')),'') bis
          FROM webhook_logs
         WHERE lower(payload) LIKE '%' || lower(?) || '%'
           AND json_extract(payload,'$.access.access_type') = 'GRANT'
           AND CAST(json_extract(payload,'$.product.product_id') AS TEXT) IN (?,?)
           AND COALESCE(json_extract(payload,'$.access.access_valid_until'),'') > ?
    """, (k["email"], *UNSERE_PRODUKTE, jetzt)).fetchone()

    if spaeter["n"]:
        print(f"\n  ⛔ ABBRUCH: Neuere Zahlung gefunden — Zugang bis {spaeter['bis']}.")
        print( "     Der Kunde zahlt wieder. Kein Kick.")
        if a.wirklich:
            admin_hinweis(env, f"[KICK ABGEBROCHEN] {k['email']} ({name}) sollte gekickt "
                               f"werden, hat laut Ablefy aber wieder gezahlt "
                               f"(Zugang bis {spaeter['bis']}). Nichts unternommen.")
        sys.exit(1)

    print(f"\n  ✅ Alle Pruefungen bestanden — Kick waere berechtigt.")

    if not a.wirklich:
        print("\n  TROCKENLAUF — es wurde NICHTS veraendert.")
        print(f"  Wirklich ausfuehren:  python3 kick.py {k['email']} --wirklich\n")
        return

    # ------------------------------------------------------------ ausfuehren
    protokoll(f"KICK START {k['email']} (id {k['id']}, tg {k['telegram_chat_id']})")
    alles_ok = True

    if k["telegram_chat_id"]:
        for bezeichnung, chat in gruppen:
            if not chat:
                continue
            r = tg(token, "banChatMember", chat_id=chat, user_id=k["telegram_chat_id"])
            ok = r.get("ok")
            print(f"  {bezeichnung:<16} {'✅ entfernt' if ok else '❌ ' + str(r.get('description'))}")
            protokoll(f"  banChatMember {bezeichnung} -> {r}")
            alles_ok &= bool(ok)
    else:
        alles_ok = False
        print("  ⚠️  Keine Telegram-ID — automatisches Entfernen nicht moeglich")
        protokoll("  keine telegram_chat_id")

    if k["telegram_invite_link"]:
        r = tg(token, "revokeChatInviteLink", chat_id=gruppen[0][1],
               invite_link=k["telegram_invite_link"])
        print(f"  Einladungslink   {'✅ widerrufen' if r.get('ok') else '⚠️ ' + str(r.get('description'))}")
        protokoll(f"  revokeChatInviteLink -> {r}")

    con.execute("UPDATE dashboard_users SET payment_status='cancelled' WHERE id=?", (k["id"],))
    con.execute("UPDATE customers SET is_active=0, deactivated_at=CURRENT_TIMESTAMP WHERE id=?",
                (k["customer_id"],))
    con.commit()
    print("  Datenbank        ✅ auf gekuendigt gesetzt")
    protokoll("  DB: payment_status=cancelled, is_active=0")

    if not alles_ok:
        admin_hinweis(env, f"[KICK] {k['email']} ({name}, id {k['id']}) — Zugang abgelaufen "
                           f"am {bis}, automatisches Entfernen NICHT bestaetigt. "
                           f"Bitte von Hand aus Signal- und Scalp-Gruppe entfernen. "
                           f"Telegram-ID: {k['telegram_chat_id'] or 'unbekannt'}")
        print("\n  ⚠️  Nicht alles bestaetigt — Hinweis an den Administrator geschickt.")
    protokoll(f"KICK ENDE {k['email']} (vollstaendig={alles_ok})")
    print()


def liste_faellige(con):
    """Wer ist abgelaufen, aber noch als aktiv gefuehrt?"""
    jetzt = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    reihen = con.execute("""
        SELECT du.id, du.email, du.telegram_chat_id, du.payment_status,
               c.first_name, c.last_name, c.is_active
          FROM dashboard_users du
          LEFT JOIN customers c ON c.id = du.customer_id
         WHERE COALESCE(c.is_active,1) = 1
           AND COALESCE(du.payment_status,'') <> 'cancelled'
           AND du.telegram_chat_id IS NOT NULL
      ORDER BY du.id
    """).fetchall()

    ausnahmen = sonderfaelle()
    faellig, uebersprungen = [], []
    for r in reihen:
        if r["email"] and r["email"].lower() in ausnahmen:
            uebersprungen.append((r, ausnahmen[r["email"].lower()]))
            continue
        bis, n = zugang_bis(con, r["email"])
        if bis and bis < jetzt:
            faellig.append((r, bis))

    print(f"\n=== Faellige Kunden (Zugang abgelaufen, noch als aktiv gefuehrt) ===\n")
    if not faellig:
        print("  Keine. Alles sauber.\n"); return
    for r, bis in faellig:
        name = f"{r['first_name'] or ''} {r['last_name'] or ''}".strip()
        print(f"  id={r['id']:<5} {r['email']:<38} {name:<24} abgelaufen {bis[:10]}")
    print(f"\n  {len(faellig)} Faelle. Pruefen mit:  python3 kick.py <email>")
    if uebersprungen:
        print(f"\n  {len(uebersprungen)} uebersprungen (Ausnahmeliste):")
        for r, grund in uebersprungen:
            print(f"     {r['email']:<38} {grund[:46]}")
    print()


if __name__ == "__main__":
    main()
