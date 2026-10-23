#!/usr/bin/env bash
# One-shot Kick fuer "Mateo", Telegram-ID 1995859812. Kuendigung per Support-Bot am 2026-08-20
# (Gruende: Signale kommen waehrend der Arbeitszeit, finanziell am Ende nach negativen Trades).
# Ansage Max: am 28.08.2026 kicken.
# ACHTUNG: Zum Zeitpunkt des Deploys war KEIN Account zuordenbar (keine E-Mail, keine Zeile in
# dashboard_users mit telegram_chat_id=1995859812). Das Script sucht den Account daher zur LAUFZEIT
# ueber telegram_chat_id -- wenn er bis dahin verknuepft ist, laufen DB-Updates + Invite-Revoke
# automatisch mit; sonst wird nur gebannt und ein Admin-Hinweis geschickt.
# Siehe Projekt-CLAUDE.md (Copy Trading Bot).
set -o pipefail
BOTDIR=/home/botuser/copy-trading-bot
LOG=/home/botuser/scripts/kick_mateo.log
ENVF="$BOTDIR/.env"
DB="$BOTDIR/copy_trading.db"
TG_ID=1995859812
TOKEN=$(grep -E "^TELEGRAM_BOT_TOKEN=" "$ENVF" | head -1 | cut -d= -f2-)
MAIN=$(grep -E "^SIGNAL_PAID_GROUP_ID=" "$ENVF" | head -1 | cut -d= -f2-)
SCALP=$(grep -E "^SIGNAL_SCALP_GROUP_ID=" "$ENVF" | head -1 | cut -d= -f2-)
ADMIN=$(grep -E "^TELEGRAM_CHAT_ID=" "$ENVF" | head -1 | cut -d= -f2-)
echo "=== $(date -u) kick mateo START ===" >> "$LOG"
OKALL=1
for CHAT in "$MAIN" "$SCALP"; do
  RESP=$(curl -s "https://api.telegram.org/bot${TOKEN}/banChatMember" -d chat_id="$CHAT" -d user_id="$TG_ID")
  echo "banChatMember $CHAT -> $RESP" >> "$LOG"
  echo "$RESP" | grep -q '"ok":true' || OKALL=0
done
# Account zur Laufzeit suchen (falls bis dahin verknuepft)
UID_ROW=$(sqlite3 "$DB" "SELECT id || '|' || COALESCE(customer_id,'') || '|' || COALESCE(telegram_invite_link,'') FROM dashboard_users WHERE telegram_chat_id='${TG_ID}' LIMIT 1;")
if [ -n "$UID_ROW" ]; then
  DUID=$(echo "$UID_ROW" | cut -d'|' -f1)
  CUST=$(echo "$UID_ROW" | cut -d'|' -f2)
  INVITE=$(echo "$UID_ROW" | cut -d'|' -f3)
  echo "Account gefunden: dashboard_users id=$DUID customer=$CUST" >> "$LOG"
  if [ -n "$INVITE" ]; then
    RESP=$(curl -s "https://api.telegram.org/bot${TOKEN}/revokeChatInviteLink" -d chat_id="$MAIN" -d invite_link="$INVITE")
    echo "revokeInviteLink -> $RESP" >> "$LOG"
  fi
  sqlite3 "$DB" "UPDATE dashboard_users SET payment_status='cancelled' WHERE id=${DUID};"
  [ -n "$CUST" ] && sqlite3 "$DB" "UPDATE customers SET is_active=0, deactivated_at=CURRENT_TIMESTAMP WHERE id='${CUST}';"
  echo "DB: payment_status=cancelled, customer is_active=0" >> "$LOG"
else
  echo "KEIN Account zu telegram_chat_id=${TG_ID} gefunden -> nur Telegram-Ban, keine DB-Updates" >> "$LOG"
  [ -n "$ADMIN" ] && curl -s "https://api.telegram.org/bot${TOKEN}/sendMessage" -d chat_id="$ADMIN" -d text="[KICK] Mateo (TG 1995859812) wurde gebannt. ACHTUNG: kein Account zuordenbar -> Abo-Status/Ablefy bitte manuell pruefen und Account deaktivieren." >> "$LOG" 2>&1
fi
if [ "$OKALL" != "1" ] && [ -n "$ADMIN" ]; then
  curl -s "https://api.telegram.org/bot${TOKEN}/sendMessage" -d chat_id="$ADMIN" -d text="[KICK] Mateo (TG 1995859812): banChatMember nicht ueberall ok=true -> bitte manuell aus Paid-Gruppe/Scalp entfernen. Siehe kick_mateo.log" >> "$LOG" 2>&1
  echo "ADMIN-ALERT gesendet (ban nicht ueberall ok)" >> "$LOG"
fi
echo "=== $(date -u) kick mateo DONE ===" >> "$LOG"
