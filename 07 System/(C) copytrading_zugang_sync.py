#!/usr/bin/env python3
"""
(C) copytrading_zugang_sync.py — Zugangsstatus Copytrading: Server 2 -> Server 1 (Haupt-DB + Close)

Server 2 ist einzige Wahrheit fuer drei Werte: aktiv ja/nein, Tier, Entzugsdatum.
Alles andere ueber den Kunden bleibt in der Haupt-DB/Close, nichts fliesst zurueck.

Laeuft auf Server 1 (Cron 03:45 UTC, nach den Backups):
  /root/copytrading_zugang_sync.py --dry-run   # nur lesen, Diff-Liste ausgeben
  /root/copytrading_zugang_sync.py             # echt: Tabelle + Close + system_logs + Telegram

Quelle:  GET https://dashboard.firstclass-trading.com/api/internal/access-status
         Header X-Internal-Token (eigener, nur lesender Token; kein SSH zwischen den Servern)
Ziel:    Tabelle copytrading_zugang (pro Server-2-Account eine Zeile, kunde_id falls zugeordnet)
         Close-Lead-Felder "Copytrading Status" / "Copytrading Tier" / "Copytrading Entzug"
Abgleich: E-Mail (kunden.email + kunden_emails, gmail = googlemail).
Abweichungen (nur NEUE -> Telegram Topic System):
  - Kunde auf Server 2 unbekannt auf Server 1
  - Copytrading-Kaeufer auf Server 1 ohne Account auf Server 2
Team-Testaccounts (INTERN_S2_IDS) bekommen Tier "Intern" und gelten nie als Abweichung.

Zugangsdaten: /etc/fct/copytrading-sync.env (600) — nie in diese Datei schreiben.
"""
import sys, json, time, hashlib, datetime
import requests, psycopg2, psycopg2.extras

DRY = "--dry-run" in sys.argv
ENV_FILE = "/etc/fct/copytrading-sync.env"
FLOW_NAME = "Copytrading Zugangs-Sync"
TG_CHAT = "-1003664924257"
TG_TOPIC_SYSTEM = 11
CLOSE_BASE = "https://api.close.com/api/v1"

# Team-Testaccounts (Max, 2026-10-29) — Server-2-IDs
INTERN_S2_IDS = {74, 160, 210}

FELDER = {
    "status": ("Copytrading Status", "choices", ["Aktiv", "Inaktiv"]),
    "tier":   ("Copytrading Tier", "choices", ["Signale", "Copy Trading", "Intern"]),
    "entzug": ("Copytrading Entzug", "date", None),
}
TIER_NAME = {"paid_signals": "Signale", "copy_trading": "Copy Trading"}


def env():
    werte = {}
    with open(ENV_FILE) as f:
        for zeile in f:
            zeile = zeile.strip()
            if zeile and not zeile.startswith("#") and "=" in zeile:
                k, v = zeile.split("=", 1)
                werte[k.strip()] = v.strip()
    return werte


def norm(email):
    e = (email or "").strip().lower()
    return e.replace("@googlemail.com", "@gmail.com")


E = env()
CLOSE_AUTH = (E["CLOSE_API_KEY"], "")


def telegram(text):
    if DRY:
        return
    try:
        requests.post(f"https://api.telegram.org/bot{E['TG_TOKEN']}/sendMessage",
                      json={"chat_id": TG_CHAT, "message_thread_id": TG_TOPIC_SYSTEM,
                            "text": text[:4000], "disable_web_page_preview": True}, timeout=20)
    except Exception as ex:
        print(f"Telegram fehlgeschlagen: {ex}")


def close_req(method, path, **kw):
    for versuch in range(5):
        r = requests.request(method, f"{CLOSE_BASE}/{path}", auth=CLOSE_AUTH, timeout=30, **kw)
        if r.status_code == 429:
            time.sleep(float(r.headers.get("Retry-After", 2)) + 0.5)
            continue
        r.raise_for_status()
        return r.json()
    r.raise_for_status()


def close_felder(anlegen):
    """Feld-IDs per Name holen; fehlende nur im echten Lauf anlegen."""
    vorhanden = {f["name"]: f["id"] for f in close_req("GET", "custom_field/lead/", params={"_limit": 500})["data"]}
    ids, fehlen = {}, []
    for key, (name, typ, choices) in FELDER.items():
        if name in vorhanden:
            ids[key] = vorhanden[name]
        elif anlegen:
            body = {"name": name, "type": typ}
            if choices:
                body["choices"] = choices
            ids[key] = close_req("POST", "custom_field/lead/", json=body)["id"]
        else:
            fehlen.append(name)
    return ids, fehlen


SCHEMA = """
CREATE TABLE IF NOT EXISTS copytrading_zugang (
    s2_user_id       integer PRIMARY KEY,
    email            text NOT NULL,
    kunde_id         uuid REFERENCES kunden(id),
    aktiv            boolean NOT NULL,
    tier             text NOT NULL,
    entzug           date,
    intern           boolean NOT NULL DEFAULT false,
    payment_status   text,
    ablefy_order_id  text,
    telegram_id      bigint,
    aktualisiert_at  timestamptz NOT NULL DEFAULT now(),
    close_lead_id    text,
    close_hash       text,
    close_synced_at  timestamptz
);
CREATE INDEX IF NOT EXISTS idx_ctz_kunde ON copytrading_zugang(kunde_id);
CREATE TABLE IF NOT EXISTS copytrading_sync_abweichungen (
    art          text NOT NULL,
    email        text NOT NULL,
    erstmals_at  timestamptz NOT NULL DEFAULT now(),
    zuletzt_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (art, email)
);
"""

ART_S2 = "server2_unbekannt_auf_server1"
ART_S1 = "server1_kaeufer_ohne_server2"


def log_system(cur, level, text, details):
    cur.execute("INSERT INTO system_logs (zeitpunkt, level, flow_name, fehler, details, gelesen) "
                "VALUES (now(), %s, %s, %s, %s, false)",
                (level, FLOW_NAME, text, json.dumps(details, default=str)))


def main():
    r = requests.get(E["S2_URL"], headers={"X-Internal-Token": E["S2_SYNC_TOKEN"]}, timeout=60)
    r.raise_for_status()
    quelle = r.json()
    s2 = quelle["users"]
    if not s2 or quelle.get("count") != len(s2):
        raise RuntimeError(f"Server 2 lieferte unplausible Daten (count={quelle.get('count')}, users={len(s2)})")

    con = psycopg2.connect(host="localhost", dbname="fct_os", user="fct_app", password=E["DB_PASSWORD"])
    con.autocommit = False
    cur = con.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Server 1: E-Mail -> Kunde (inkl. Zweitadressen)
    cur.execute("""SELECT k.id, lower(trim(k.email)) AS email, k.close_lead_id FROM kunden k
                   UNION
                   SELECT k.id, lower(trim(ke.email)), k.close_lead_id
                   FROM kunden_emails ke JOIN kunden k ON k.id = ke.kunde_id""")
    s1_mail = {}
    for row in cur.fetchall():
        if row["email"]:
            s1_mail.setdefault(norm(row["email"]), row)

    cur.execute("""SELECT DISTINCT k.id, lower(trim(k.email)) AS email FROM kaeufe ka
                   JOIN kunden k ON k.id = ka.kunde_id JOIN produkte p ON p.id = ka.produkt_id
                   WHERE p.kategorie = 'copytrading'""")
    s1_kaeufer = cur.fetchall()
    cur.execute("SELECT kunde_id, lower(trim(email)) AS email FROM kunden_emails")
    alias = {}
    for row in cur.fetchall():
        alias.setdefault(row["kunde_id"], set()).add(norm(row["email"]))

    cur.execute("SELECT to_regclass('copytrading_zugang') IS NOT NULL AS da")
    tabelle_da = cur.fetchone()["da"]
    alt = {}
    if tabelle_da:
        cur.execute("SELECT * FROM copytrading_zugang")
        alt = {row["s2_user_id"]: row for row in cur.fetchall()}
        cur.execute("SELECT art, email FROM copytrading_sync_abweichungen")
        bekannt = {(row["art"], row["email"]) for row in cur.fetchall()}
    else:
        bekannt = set()

    # Soll-Zustand aufbauen
    soll, abw = [], []
    s2_mails = set()
    for u in s2:
        mail = norm(u["email"])
        s2_mails.add(mail)
        intern = u["id"] in INTERN_S2_IDS
        k = s1_mail.get(mail)
        tier = "Intern" if intern else TIER_NAME.get(u["tier"], u["tier"] or "unbekannt")
        status = "Aktiv" if u["aktiv"] else "Inaktiv"
        soll.append({
            "s2_user_id": u["id"], "email": mail, "kunde_id": k["id"] if k else None,
            "close_lead_id": k["close_lead_id"] if k else None,
            "aktiv": u["aktiv"], "tier": tier, "status": status, "entzug": u["entzug"], "intern": intern,
            "payment_status": u.get("payment_status"), "ablefy_order_id": u.get("ablefy_order_id"),
            "telegram_id": int(u["telegram_id"]) if str(u.get("telegram_id") or "").lstrip("-").isdigit() else None,
            "close_hash": hashlib.sha1(f"{status}|{tier}|{u['entzug']}".encode()).hexdigest()[:16],
        })
        if not k and not intern:
            abw.append((ART_S2, mail))

    intern_mails = {norm(u["email"]) for u in s2 if u["id"] in INTERN_S2_IDS}
    for row in s1_kaeufer:
        mails = {norm(row["email"])} | alias.get(row["id"], set())
        if not (mails & s2_mails) and not (mails & intern_mails):
            abw.append((ART_S1, norm(row["email"])))

    neu_abw = [a for a in abw if a not in bekannt]

    # Diff gegen letzten Stand
    db_aenderungen, close_updates, ohne_lead = [], [], 0
    for s in soll:
        a = alt.get(s["s2_user_id"])
        felder_alt = None if not a else (a["aktiv"], a["tier"], str(a["entzug"]) if a["entzug"] else None, a["kunde_id"] and str(a["kunde_id"]))
        felder_neu = (s["aktiv"], s["tier"], s["entzug"], s["kunde_id"] and str(s["kunde_id"]))
        if felder_alt != felder_neu:
            db_aenderungen.append((s, a))
        if s["close_lead_id"]:
            if not a or a["close_hash"] != s["close_hash"] or a["close_lead_id"] != s["close_lead_id"]:
                close_updates.append(s)
        elif s["kunde_id"]:
            ohne_lead += 1

    zusammenfassung = {
        "dry_run": DRY, "server2_accounts": len(s2), "zugeordnet": sum(1 for s in soll if s["kunde_id"]),
        "aktiv": sum(1 for s in soll if s["aktiv"]), "intern": len(INTERN_S2_IDS),
        "db_aenderungen": len(db_aenderungen), "close_updates": len(close_updates),
        "kunde_ohne_close_lead": ohne_lead,
        "abweichungen_gesamt": len(abw), "abweichungen_neu": len(neu_abw),
    }

    if DRY:
        ids, fehlen = close_felder(anlegen=False)
        print(f"=== DRY-RUN {datetime.datetime.now(datetime.timezone.utc):%Y-%m-%d %H:%M} UTC — nichts geschrieben ===")
        print(json.dumps(zusammenfassung, indent=1))
        if fehlen:
            print(f"Close-Felder fehlen und werden im echten Lauf angelegt: {', '.join(fehlen)}")
        print(f"Tabelle copytrading_zugang vorhanden: {tabelle_da}")
        print("\n--- Abweichungen (alle, im echten Lauf nur NEUE nach Telegram) ---")
        for art, mail in sorted(abw):
            print(f"  {art:32} {mail}")
        print("\n--- Interne Testaccounts (keine Abweichung) ---")
        for s in soll:
            if s["intern"]:
                print(f"  s2={s['s2_user_id']:<4} {s['email']:38} {s['status']:8} Tier={s['tier']} zugeordnet={'ja' if s['kunde_id'] else 'nein'}")
        print("\n--- Kunden mit Entzugsdatum (Close-Feld 'Copytrading Entzug') ---")
        for s in sorted((s for s in soll if s["entzug"]), key=lambda x: x["entzug"], reverse=True)[:25]:
            print(f"  s2={s['s2_user_id']:<4} {s['email']:38} {s['status']:8} {s['tier']:12} Entzug={s['entzug']}  Close-Lead={'ja' if s['close_lead_id'] else 'NEIN'}")
        print(f"  … insgesamt {sum(1 for s in soll if s['entzug'])} mit Entzugsdatum")
        print("\n--- Stichprobe Close-Updates (erste 10) ---")
        for s in close_updates[:10]:
            print(f"  {s['close_lead_id']}  {s['email']:38} Status={s['status']:8} Tier={s['tier']:12} Entzug={s['entzug']}")
        con.rollback()
        return

    # --- echter Lauf ---
    for stmt in SCHEMA.strip().split(";"):
        if stmt.strip():
            cur.execute(stmt)
    ids, _ = close_felder(anlegen=True)

    for s in soll:
        cur.execute("""
            INSERT INTO copytrading_zugang (s2_user_id, email, kunde_id, aktiv, tier, entzug, intern,
                payment_status, ablefy_order_id, telegram_id, aktualisiert_at, close_lead_id)
            VALUES (%(s2_user_id)s, %(email)s, %(kunde_id)s, %(aktiv)s, %(tier)s, %(entzug)s, %(intern)s,
                %(payment_status)s, %(ablefy_order_id)s, %(telegram_id)s, now(), %(close_lead_id)s)
            ON CONFLICT (s2_user_id) DO UPDATE SET
                email = EXCLUDED.email, kunde_id = EXCLUDED.kunde_id, aktiv = EXCLUDED.aktiv,
                tier = EXCLUDED.tier, entzug = EXCLUDED.entzug, intern = EXCLUDED.intern,
                payment_status = EXCLUDED.payment_status, ablefy_order_id = EXCLUDED.ablefy_order_id,
                telegram_id = EXCLUDED.telegram_id, close_lead_id = EXCLUDED.close_lead_id,
                aktualisiert_at = CASE WHEN (copytrading_zugang.aktiv, copytrading_zugang.tier, copytrading_zugang.entzug)
                    IS DISTINCT FROM (EXCLUDED.aktiv, EXCLUDED.tier, EXCLUDED.entzug)
                    THEN now() ELSE copytrading_zugang.aktualisiert_at END
        """, s)
    for art, mail in abw:
        cur.execute("""INSERT INTO copytrading_sync_abweichungen (art, email) VALUES (%s, %s)
                       ON CONFLICT (art, email) DO UPDATE SET zuletzt_at = now()""", (art, mail))
    con.commit()

    close_fehler = []
    for s in close_updates:
        body = {f"custom.{ids['status']}": s["status"], f"custom.{ids['tier']}": s["tier"],
                f"custom.{ids['entzug']}": s["entzug"]}
        try:
            close_req("PUT", f"lead/{s['close_lead_id']}/", json=body)
            cur.execute("UPDATE copytrading_zugang SET close_hash = %s, close_synced_at = now() WHERE s2_user_id = %s",
                        (s["close_hash"], s["s2_user_id"]))
            con.commit()
        except Exception as ex:
            con.rollback()
            close_fehler.append(f"{s['email']}: {ex}")
        time.sleep(0.15)

    zusammenfassung["close_fehler"] = len(close_fehler)
    level = "error" if close_fehler else ("warning" if neu_abw else "info")
    text = (f"{zusammenfassung['zugeordnet']}/{len(s2)} zugeordnet, {len(db_aenderungen)} Änderungen, "
            f"{len(close_updates) - len(close_fehler)} Close-Updates, {len(neu_abw)} neue Abweichungen")
    log_system(cur, level, text, {**zusammenfassung, "neue_abweichungen": neu_abw, "close_fehler": close_fehler[:20]})
    con.commit()

    if neu_abw or close_fehler:
        zeilen = [f"🔄 Copytrading-Sync: {text}"]
        for art, mail in neu_abw[:40]:
            zeilen.append(("• Server 2, fehlt auf Server 1: " if art == ART_S2 else "• Käufer auf Server 1, kein Server-2-Account: ") + mail)
        if close_fehler:
            zeilen.append(f"⚠️ {len(close_fehler)} Close-Fehler, Details in system_logs")
        telegram("\n".join(zeilen))
    print(text)


if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        print(f"FEHLER: {ex}")
        if not DRY:
            try:
                con = psycopg2.connect(host="localhost", dbname="fct_os", user="fct_app", password=E["DB_PASSWORD"])
                with con, con.cursor() as c:
                    log_system(c, "error", f"Sync abgebrochen: {ex}"[:500], {"fehler": str(ex)})
            except Exception:
                pass
            telegram(f"❌ Copytrading-Sync abgebrochen: {ex}"[:500])
        sys.exit(1)
