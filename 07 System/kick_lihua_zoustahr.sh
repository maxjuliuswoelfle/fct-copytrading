#!/usr/bin/env bash
# One-shot Kick fuer "Li" / Lihua Zoustahr, lihua.zoustahr@yahoo.com, dashboard_users id 358.
# Kundin hat am 22.08.2026 selbst online gekuendigt (Ablefy-Event 22.08. 09:50 in webhook_logs bestaetigt).
# Ablefy: access_valid_until 2026-09-06T00:00:00Z, Order 16546966, Monatsabo 96,45 EUR (SEPA),
# letzte Zahlung 12.08.2026. KEIN Jahresvertrag. Ansage Max: Timer setzen -> 06.09.2026.
# Telegram-ID 7487353081 ("Li"), bei Erfassung member in Main UND Scalp.
# Reine Signal-Kundin (keine API-Keys, 0 Mappings). Siehe Projekt-CLAUDE.md (Copy Trading Bot).
set -o pipefail
BOTDIR=/home/botuser/copy-trading-bot
LOG=/home/botuser/scripts/kick_lihua_zoustahr.log
ENVF="$BOTDIR/.env"
DB="$BOTDIR/copy_trading.db"
TG_ID=7487353081
INVITE="https://telegram.me/+kKSGhLag0l4zNTgy"
CUST="557d1005-2300-4021-b47f-17d31bd97c7e"
TOKEN=$(grep -E "^TELEGRAM_BOT_TOKEN=" "$ENVF" | head -1 | cut -d= -f2-)
MAIN=$(grep -E "^SIGNAL_PAID_GROUP_ID=" "$ENVF" | head -1 | cut -d= -f2-)
SCALP=$(grep -E "^SIGNAL_SCALP_GROUP_ID=" "$ENVF" | head -1 | cut -d= -f2-)
ADMIN=$(grep -E "^TELEGRAM_CHAT_ID=" "$ENVF" | head -1 | cut -d= -f2-)
echo "=== $(date -u) kick lihua_zoustahr START ===" >> "$LOG"
OKALL=1
for CHAT in "$MAIN" "$SCALP"; do
  RESP=$(curl -s "https://api.telegram.org/bot${TOKEN}/banChatMember" -d chat_id="$CHAT" -d user_id="$TG_ID")
  echo "banChatMember $CHAT -> $RESP" >> "$LOG"
  echo "$RESP" | grep -q '"ok":true' || OKALL=0
done
RESP=$(curl -s "https://api.telegram.org/bot${TOKEN}/revokeChatInviteLink" -d chat_id="$MAIN" -d invite_link="$INVITE")
echo "revokeInviteLink -> $RESP" >> "$LOG"
sqlite3 "$DB" "UPDATE dashboard_users SET payment_status='cancelled' WHERE id=358; UPDATE customers SET is_active=0, deactivated_at=CURRENT_TIMESTAMP WHERE id='${CUST}';"
echo "DB: payment_status=cancelled, customer is_active=0" >> "$LOG"
if [ "$OKALL" != "1" ] && [ -n "$ADMIN" ]; then
  curl -s "https://api.telegram.org/bot${TOKEN}/sendMessage" -d chat_id="$ADMIN" -d text="[KICK] lihua.zoustahr@yahoo.com / Li (id 358): banChatMember nicht ueberall ok=true -> bitte manuell aus Paid-Gruppe/Scalp entfernen. Siehe kick_lihua_zoustahr.log" >> "$LOG" 2>&1
  echo "ADMIN-ALERT gesendet (ban nicht ueberall ok)" >> "$LOG"
fi
echo "=== $(date -u) kick lihua_zoustahr DONE ===" >> "$LOG"
