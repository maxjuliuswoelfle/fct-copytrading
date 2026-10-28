#!/usr/bin/env bash
# Tägliches Backup der Copytrading-SQLite (Server 2) — konsistent per sqlite3 .backup (WAL-sicher).
# Einrichten (einmalig, als root auf 178.105.135.197):
#   cp backup-copytrading-db.sh /root/ && chmod +x /root/backup-copytrading-db.sh
#   apt-get install -y sqlite3
#   (crontab -l 2>/dev/null; echo '30 3 * * * /root/backup-copytrading-db.sh >> /var/log/backup-copytrading.log 2>&1') | crontab -
# Prüfen:  /root/backup-copytrading-db.sh && ls -la /var/backups/copytrading/
set -euo pipefail
DB="/home/botuser/copy-trading-bot/copy_trading.db"
DEST="/var/backups/copytrading"
KEEP_DAYS=30
mkdir -p "$DEST"
STAMP="$(date '+%Y-%m-%d_%H%M')"
OUT="$DEST/copy_trading_$STAMP.db"
sqlite3 "$DB" ".backup '$OUT'"
sqlite3 "$OUT" "PRAGMA integrity_check;" | grep -q '^ok$' || { echo "$(date) Backup DEFEKT: $OUT"; exit 1; }
gzip -f "$OUT"
find "$DEST" -name 'copy_trading_*.db.gz' -mtime +$KEEP_DAYS -delete
echo "$(date '+%F %T') OK $OUT.gz ($(du -h "$OUT.gz" | cut -f1))"
