#!/usr/bin/env bash
# (C) audit_gekuendigte_mitglieder.sh — READ-ONLY Audit.
# Prueft fuer jeden gekuendigten/erstatteten Account mit bekannter telegram_chat_id,
# ob er noch Mitglied der Main-Gruppe bzw. des Scalp-Channels ist.
# Aendert NICHTS — nur getChatMember (Lesezugriff).
set -o pipefail
BOTDIR=/home/botuser/copy-trading-bot
ENVF="$BOTDIR/.env"
DB="$BOTDIR/copy_trading.db"
TOKEN=$(grep -E "^TELEGRAM_BOT_TOKEN=" "$ENVF" | head -1 | cut -d= -f2-)
MAIN=$(grep -E "^SIGNAL_PAID_GROUP_ID=" "$ENVF" | head -1 | cut -d= -f2-)
SCALP=$(grep -E "^SIGNAL_SCALP_GROUP_ID=" "$ENVF" | head -1 | cut -d= -f2-)

echo "STATUS | ID | EMAIL | MAIN | SCALP"
echo "-------------------------------------------------------------"

sqlite3 -separator '|' "$DB" \
  "SELECT id, email, COALESCE(telegram_chat_id,'') FROM dashboard_users
   WHERE payment_status IN ('cancelled','refunded') ORDER BY id;" |
while IFS='|' read -r DUID EMAIL TGID; do
  if [ -z "$TGID" ]; then
    echo "KEINE-ID | $DUID | $EMAIL | ? | ?"
    continue
  fi
  M=$(curl -s "https://api.telegram.org/bot${TOKEN}/getChatMember?chat_id=${MAIN}&user_id=${TGID}" \
      | grep -oE '"status":"[a-z]+"' | cut -d'"' -f4)
  S=$(curl -s "https://api.telegram.org/bot${TOKEN}/getChatMember?chat_id=${SCALP}&user_id=${TGID}" \
      | grep -oE '"status":"[a-z]+"' | cut -d'"' -f4)
  [ -z "$M" ] && M="FEHLER"
  [ -z "$S" ] && S="FEHLER"
  FLAG="ok"
  case "$M" in member|administrator|creator|restricted) FLAG="!! DRIN" ;; esac
  case "$S" in member|administrator|creator|restricted) FLAG="!! DRIN" ;; esac
  echo "$FLAG | $DUID | $EMAIL | $M | $S"
  sleep 0.15
done
