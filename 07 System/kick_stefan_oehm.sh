#!/usr/bin/env bash
# One-shot Kick fuer Stefan Oehm / stefan.oehm@gmail.com, dashboard_users id 173.
# Kuendigung gemeldet 2026-08-20 (Max hat in Ablefy gekuendigt, Event 20.08. 08:16 bestaetigt).
# Ablefy: access_valid_until 2026-08-28T00:00:00Z, Order 16520289 (Launch-Kauf 28.06.),
# Monatsabo 96,45 EUR, letzte Zahlung 29.07.2026. Ansage Max: am 28.08.2026 rausschmeissen.
# Telegram-ID 549193723 (@eisman88), bei Erfassung member in Main UND Scalp.
# Reiner Signal-Kunde (keine API-Keys, 0 Mappings). Siehe Projekt-CLAUDE.md (Copy Trading Bot).
set -o pipefail
BOTDIR=/home/botuser/copy-trading-bot
LOG=/home/botuser/scripts/kick_stefan_oehm.log
ENVF="$BOTDIR/.env"
DB="$BOTDIR/copy_trading.db"
TG_ID=549193723
INVITE="https://telegram.me/+SXyPVPA5KYNlY2Ni"
CUST="955b3968-aa1d-4b19-9f45-11519a809949"
TOKEN=$(grep -E "^TELEGRAM_BOT_TOKEN=" "$ENVF" | head -1 | cut -d= -f2-)
MAIN=$(grep -E "^SIGNAL_PAID_GROUP_ID=" "$ENVF" | head -1 | cut -d= -f2-)
SCALP=$(grep -E "^SIGNAL_SCALP_GROUP_ID=" "$ENVF" | head -1 | cut -d= -f2-)
ADMIN=$(grep -E "^TELEGRAM_CHAT_ID=" "$ENVF" | head -1 | cut -d= -f2-)
echo "=== $(date -u) kick stefan_oehm START ===" >> "$LOG"
OKALL=1
for CHAT in "$MAIN" "$SCALP"; do
  RESP=$(curl -s "https://api.telegram.org/bot${TOKEN}/banChatMember" -d chat_id="$CHAT" -d user_id="$TG_ID")
  echo "banChatMember $CHAT -> $RESP" >> "$LOG"
  echo "$RESP" | grep -q '"ok":true' || OKALL=0
done
RESP=$(curl -s "https://api.telegram.org/bot${TOKEN}/revokeChatInviteLink" -d chat_id="$MAIN" -d invite_link="$INVITE")
echo "revokeInviteLink -> $RESP" >> "$LOG"
sqlite3 "$DB" "UPDATE dashboard_users SET payment_status='cancelled' WHERE id=173; UPDATE customers SET is_active=0, deactivated_at=CURRENT_TIMESTAMP WHERE id='${CUST}';"
echo "DB: payment_status=cancelled, customer is_active=0" >> "$LOG"
if [ "$OKALL" != "1" ] && [ -n "$ADMIN" ]; then
  curl -s "https://api.telegram.org/bot${TOKEN}/sendMessage" -d chat_id="$ADMIN" -d text="[KICK] stefan.oehm@gmail.com / Stefan (@eisman88, id 173): banChatMember nicht ueberall ok=true -> bitte manuell aus Paid-Gruppe/Scalp entfernen. Siehe kick_stefan_oehm.log" >> "$LOG" 2>&1
  echo "ADMIN-ALERT gesendet (ban nicht ueberall ok)" >> "$LOG"
fi
echo "=== $(date -u) kick stefan_oehm DONE ===" >> "$LOG"
