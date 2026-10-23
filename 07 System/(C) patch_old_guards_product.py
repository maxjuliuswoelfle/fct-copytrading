#!/usr/bin/env python3
"""(C) patch_old_guards_product.py — Produkt-Filter fuer die Kick-Checks Brendler + Kocemba (2026-09-11).

Befund 2026-09-11: Der Re-GRANT-Check vom 10.09. zaehlt JEDEN Ablefy-GRANT der E-Mail — auch fuer
andere Produkte der Firma (Trading Accelerator 517573, Betreuungs-Abo 517583, Intensiv-Betreuung
517575/517576/517577). Kauft ein Gekuendigter so ein Produkt, wuerde sein Kick faelschlich
abgebrochen. Beleg: Timo Heusel kaufte am 03.09. den Accelerator -> GRANT bis 03.10.
Jetzt zaehlen nur noch unsere Produkte 517561/517562 (wie in den 7 nachgeruesteten Scripts).

Backups *.bak_product_20260911, danach bash -n.
Aufruf: cd /home/botuser/scripts && python3 patch_old_guards_product.py
"""
import shutil
import subprocess
import sys

FILES = ["kick_pawel_brendler.sh", "kick_matthias_kocemba.sh"]
OLD = "json_extract(payload,'\\$.access.access_type')='GRANT' AND COALESCE("
NEW = ("json_extract(payload,'\\$.access.access_type')='GRANT' AND "
       "CAST(json_extract(payload,'\\$.product.product_id') AS TEXT) IN ('517561','517562') AND COALESCE(")
SUFFIX = ".bak_product_20260911"


def main() -> int:
    rc = 0
    for fname in FILES:
        text = open(fname, encoding="utf-8").read()
        if "IN ('517561','517562')" in text:
            print(f"SKIP  {fname}: Produkt-Filter schon drin")
            continue
        n = text.count(OLD)
        if n != 1:
            print(f"FAIL  {fname}: Anker {n}x gefunden (erwartet 1) — nichts geaendert")
            rc = 1
            continue
        shutil.copy2(fname, fname + SUFFIX)
        with open(fname, "w", encoding="utf-8") as f:
            f.write(text.replace(OLD, NEW, 1))
        syn = subprocess.run(["bash", "-n", fname], capture_output=True, text=True)
        if syn.returncode != 0:
            shutil.copy2(fname + SUFFIX, fname)
            print(f"FAIL  {fname}: bash -n {syn.stderr.strip()} -> Backup zurueckgespielt")
            rc = 1
        else:
            print(f"OK    {fname}: Produkt-Filter ergaenzt, bash -n OK, Backup {fname + SUFFIX}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
