#!/usr/bin/env python3
"""(C) patch_kick_guards.py — Zahlungs-Check in die 7 ausstehenden Kick-Scripts nachruesten (2026-09-11).

Lehre Lihua (06.09.) + Timo Heusel (08.09.): Kick-Timer feuerten blind und bannten Kunden,
die nach der Kuendigung NEU gekauft hatten. Pawel Brendler + Matthias Kocemba haben den Check
schon — hier werden die restlichen 7 nachgeruestet.

Der Check (direkt nach der START-Zeile): Gibt es fuer UNSER Produkt (517561/517562) einen
Ablefy-GRANT mit SPAETEREM access_valid_until als dem bekannten Laufzeitende? -> kein Ban,
nur Admin-Alert. NICHT nach Zeitstempel filtern: das Kuendigungs-Event traegt selbst GRANT.

Backups *.bak_guard_20260911, danach bash -n + Probe-Abfrage je Script.
Aufruf: cd /home/botuser/scripts && python3 patch_kick_guards.py
"""
import re
import shutil
import sqlite3
import subprocess
import sys

DB = "../copy-trading-bot/copy_trading.db"
SUFFIX = ".bak_guard_20260911"

GUARDS = [
    ("kick_schreibetobi.sh", "schreibetobi@gmail.com", "2026-09-17T00:00:00Z"),
    ("kick_ivan_latkovic.sh", "ivan.latkovic.laci@gmail.com", "2026-09-23T00:00:00Z"),
    ("kick_samuel_landert.sh", "samuellandert@gmx.ch", "2026-09-28T00:00:00Z"),
    ("kick_daniel_risling.sh", "d.risling@live.de", "2026-10-03T00:00:00Z"),
    ("kick_volged.sh", "volged@web.de", "2027-06-28T00:00:00Z"),
    ("kick_harry19851985.sh", "harry19851985@gmail.com", "2027-06-29T00:00:00Z"),
    ("kick_markus_aschenbrenner.sh", "markus2aschenbrenner@gmail.com", "2027-07-01T00:00:00Z"),
]

BLOCK = r'''
# --- Laufzeit-Check (nachgeruestet 2026-09-11, Lehre Lihua/Timo): hat der Kunde wieder gezahlt? ---
# Liegt fuer unser Produkt ein Ablefy-GRANT mit SPAETEREM access_valid_until als dem
# Laufzeitende vor -> KEIN Ban, nur Admin-Alert.
# NICHT nach Zeitstempel filtern: das Kuendigungs-Event traegt selbst access_type=GRANT.
G_EMAIL="__EMAIL__"
G_UNTIL="__UNTIL__"
G_SQL="FROM webhook_logs WHERE lower(payload) LIKE '%${G_EMAIL}%' AND json_extract(payload,'\$.access.access_type')='GRANT' AND CAST(json_extract(payload,'\$.product.product_id') AS TEXT) IN ('517561','517562') AND COALESCE(json_extract(payload,'\$.access.access_valid_until'),'') > '${G_UNTIL}'"
REGRANT=$(sqlite3 "$DB" "SELECT COUNT(*) ${G_SQL};")
G_MAXUNTIL=$(sqlite3 "$DB" "SELECT COALESCE(MAX(json_extract(payload,'\$.access.access_valid_until')),'') ${G_SQL};")
echo "Re-GRANT-Check (valid_until > ${G_UNTIL}): ${REGRANT} (max ${G_MAXUNTIL})" >> "$LOG"
if [ "$REGRANT" != "0" ]; then
  echo "ABBRUCH: neuerer GRANT gefunden -> KEIN Ban, nur Admin-Alert" >> "$LOG"
  [ -n "$ADMIN" ] && curl -s "https://api.telegram.org/bot${TOKEN}/sendMessage" -d chat_id="$ADMIN" --data-urlencode text="[KICK ABGEBROCHEN] ${G_EMAIL} sollte heute gekickt werden - laut Ablefy hat der Kunde aber WIEDER GEZAHLT (Zugang gueltig bis ${G_MAXUNTIL}). Kein Ban ausgefuehrt, Zugang bleibt. Falls er spaeter doch raus soll: neuen Kick-Termin setzen." >> "$LOG" 2>&1
  echo "=== $(date -u) __NAME__ ABORTED (re-grant) ===" >> "$LOG"
  exit 0
fi
'''

START_RE = re.compile(r'^echo "=== \$\(date -u\) kick .*START.*$', re.M)


def probe(email, until):
    con = sqlite3.connect(DB)
    sql = ("SELECT COUNT(*) FROM webhook_logs WHERE lower(payload) LIKE ? "
           "AND json_extract(payload,'$.access.access_type')='GRANT' "
           "AND CAST(json_extract(payload,'$.product.product_id') AS TEXT) IN ('517561','517562') "
           "AND COALESCE(json_extract(payload,'$.access.access_valid_until'),'') > ?")
    real = con.execute(sql, (f"%{email}%", until)).fetchone()[0]
    sanity = con.execute(sql, (f"%{email}%", "2026-01-01")).fetchone()[0]
    con.close()
    return real, sanity


def main() -> int:
    rc = 0
    for fname, email, until in GUARDS:
        text = open(fname, encoding="utf-8").read()
        if "REGRANT" in text:
            print(f"SKIP  {fname}: Check schon vorhanden")
            continue
        m = list(START_RE.finditer(text))
        if len(m) != 1:
            print(f"FAIL  {fname}: START-Zeile {len(m)}x gefunden (erwartet 1)")
            rc = 1
            continue
        head = text[:m[0].start()]
        missing = [v for v in ("DB=", "TOKEN=", "ADMIN=", "LOG=") if v not in head]
        if missing:
            print(f"FAIL  {fname}: Variablen fehlen vor START: {missing}")
            rc = 1
            continue
        name = fname[:-3]
        block = BLOCK.replace("__EMAIL__", email).replace("__UNTIL__", until).replace("__NAME__", name)
        new = text[:m[0].end()] + "\n" + block + text[m[0].end():]
        shutil.copy2(fname, fname + SUFFIX)
        with open(fname, "w", encoding="utf-8") as f:
            f.write(new)
        syn = subprocess.run(["bash", "-n", fname], capture_output=True, text=True)
        real, sanity = probe(email, until)
        verdict = "OK" if syn.returncode == 0 else "SYNTAXFEHLER"
        warn = "  <-- HAT BEREITS WIEDER GEZAHLT, Kick wuerde abbrechen!" if real else ""
        print(f"{verdict:4}  {fname}: bash -n {'OK' if syn.returncode == 0 else syn.stderr.strip()} | "
              f"Re-GRANT jetzt={real} | Gegenprobe(ab 2026-01-01)={sanity}{warn}")
        if syn.returncode != 0:
            shutil.copy2(fname + SUFFIX, fname)
            print(f"      -> Backup zurueckgespielt")
            rc = 1
    return rc


if __name__ == "__main__":
    sys.exit(main())
