#!/usr/bin/env bash
# One-shot Kick fuer Maryna Litvinova / maryna.o.litvinova@gmail.com, dashboard_users id 136.
# Kuendigung per Support-Bot am 2026-08-17 ("i want to stop my subscription"), Max hat in Ablefy gekuendigt.
# Geplant 2026-08-28 (bezahlt bis dahin). Ablefy bestaetigt: access_valid_until 2026-08-28T00:00:00Z,
# Order 16519834 (Launch-Kauf 28.06.), Monatsabo 96,45 EUR, letzte Zahlung 29.07.2026.
# Telegram-ID 528984687 (@litvinovamarina), bei Erfassung member in Main UND Scalp.
# Reine Signal-Kundin (keine API-Keys, 0 Mappings). Siehe Projekt-CLAUDE.md (Copy Trading Bot).
set -o pipefail
BOTDIR=/home/botuser/copy-trading-bot
LOG=/home/botuser/scripts/kick_maryna_litvinova.log
ENVF="$BOTDIR/.env"
DB="$BOTDIR/copy_trading.db"
TG_ID=528984687
INVITE="https://telegram.me/+xImbhE7JcQUxMzIy"
CUST="415674e5-1f82-460f-b3ba-250404eccdff"
TOKEN=$(grep -E "^TELEGRAM_BOT_TOKEN=" "$ENVF" | head -1 | cut -d= -f2-)
MAIN=$(grep -E "^SIGNAL_PAID_GROUP_ID=" "$ENVF" | head -1 | cut -d= -f2-)
SCALP=$(grep -E "^SIGNAL_SCALP_GROUP_ID=" "$ENVF" | head -1 | cut -d= -f2-)
ADMIN=$(grep -E "^TELEGRAM_CHAT_ID=" "$ENVF" | head -1 | cut -d= -f2-)
echo "=== $(date -u) kick maryna_litvinova START ===" >> "$LOG"
OKALL=1
for CHAT in "$MAIN" "$SCALP"; do
  RESP=$(curl -s "https://api.telegram.org/bot${TOKEN}/banChatMember" -d chat_id="$CHAT" -d user_id="$TG_ID")
  echo "banChatMember $CHAT -> $RESP" >> "$LOG"
  echo "$RESP" | grep -q '"ok":true' || OKALL=0
done
RESP=$(curl -s "https://api.telegram.org/bot${TOKEN}/revokeChatInviteLink" -d chat_id="$MAIN" -d invite_link="$INVITE")
echo "revokeInviteLink -> $RESP" >> "$LOG"
sqlite3 "$DB" "UPDATE dashboard_users SET payment_status='cancelled' WHERE id=136; UPDATE customers SET is_active=0, deactivated_at=CURRENT_TIMESTAMP WHERE id='${CUST}';"
echo "DB: payment_status=cancelled, customer is_active=0" >> "$LOG"
if [ "$OKALL" != "1" ] && [ -n "$ADMIN" ]; then
  curl -s "https://api.telegram.org/bot${TOKEN}/sendMessage" -d chat_id="$ADMIN" -d text="[KICK] maryna.o.litvinova@gmail.com / Maryna Litvinova (id 136): banChatMember nicht ueberall ok=true -> bitte manuell aus Paid-Gruppe/Scalp entfernen. Siehe kick_maryna_litvinova.log" >> "$LOG" 2>&1
  echo "ADMIN-ALERT gesendet (ban nicht ueberall ok)" >> "$LOG"
fi
echo "=== $(date -u) kick maryna_litvinova DONE ===" >> "$LOG"
