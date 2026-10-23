#!/usr/bin/env bash
# One-shot Kick fuer "Klotz Mensch" / yannickensy@gmail.com, dashboard_users id 357.
# Kuendigung 2026-08-24 (Ablefy-Event 24.08. 15:36 in webhook_logs bestaetigt),
# access_valid_until 2026-09-07T00:00:00Z. Order 16551315, Monatsabo 96,45 EUR (SEPA),
# letzte Zahlung 12.08.2026. Ansage Max: am 07.09.2026 kicken.
# Telegram-ID 7519922625 ("Klotz Mensch") — von Max bestaetigt (im Support-Chat tauchte zusaetzlich
# "yanik" 1344687283 auf, der NICHT gemeint ist). Bei Erfassung member in Main UND Scalp.
# Reiner Signal-Kunde (keine API-Keys). Siehe Projekt-CLAUDE.md (Copy Trading Bot).
set -o pipefail
BOTDIR=/home/botuser/copy-trading-bot
LOG=/home/botuser/scripts/kick_yannickensy.log
ENVF="$BOTDIR/.env"
DB="$BOTDIR/copy_trading.db"
TG_ID=7519922625
INVITE="https://telegram.me/+WO3eFVxlNhdlYWQ6"
CUST="bc84ed9d-06c5-488c-b032-b60e7f2fd1f2"
TOKEN=$(grep -E "^TELEGRAM_BOT_TOKEN=" "$ENVF" | head -1 | cut -d= -f2-)
MAIN=$(grep -E "^SIGNAL_PAID_GROUP_ID=" "$ENVF" | head -1 | cut -d= -f2-)
SCALP=$(grep -E "^SIGNAL_SCALP_GROUP_ID=" "$ENVF" | head -1 | cut -d= -f2-)
ADMIN=$(grep -E "^TELEGRAM_CHAT_ID=" "$ENVF" | head -1 | cut -d= -f2-)
echo "=== $(date -u) kick yannickensy START ===" >> "$LOG"
OKALL=1
for CHAT in "$MAIN" "$SCALP"; do
  RESP=$(curl -s "https://api.telegram.org/bot${TOKEN}/banChatMember" -d chat_id="$CHAT" -d user_id="$TG_ID")
  echo "banChatMember $CHAT -> $RESP" >> "$LOG"
  echo "$RESP" | grep -q '"ok":true' || OKALL=0
done
RESP=$(curl -s "https://api.telegram.org/bot${TOKEN}/revokeChatInviteLink" -d chat_id="$MAIN" -d invite_link="$INVITE")
echo "revokeInviteLink -> $RESP" >> "$LOG"
sqlite3 "$DB" "UPDATE dashboard_users SET payment_status='cancelled' WHERE id=357; UPDATE customers SET is_active=0, deactivated_at=CURRENT_TIMESTAMP WHERE id='${CUST}';"
echo "DB: payment_status=cancelled, customer is_active=0" >> "$LOG"
if [ "$OKALL" != "1" ] && [ -n "$ADMIN" ]; then
  curl -s "https://api.telegram.org/bot${TOKEN}/sendMessage" -d chat_id="$ADMIN" -d text="[KICK] yannickensy@gmail.com / Klotz Mensch (id 357): banChatMember nicht ueberall ok=true -> bitte manuell aus Paid-Gruppe/Scalp entfernen. Siehe kick_yannickensy.log" >> "$LOG" 2>&1
  echo "ADMIN-ALERT gesendet (ban nicht ueberall ok)" >> "$LOG"
fi
echo "=== $(date -u) kick yannickensy DONE ===" >> "$LOG"
