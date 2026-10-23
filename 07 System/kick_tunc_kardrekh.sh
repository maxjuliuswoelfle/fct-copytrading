#!/usr/bin/env bash
# One-shot Kick fuer Tunc / kardrekh@gmail.com, dashboard_users id 386.
# Kuendigung erfasst 2026-07-30, geplant 2026-08-07 (bezahlt bis dahin).
# Ansage Max: am 07.08. rauswerfen. Telegram-ID 7598310427 (verifiziert member in beiden).
# Reiner Signal-Kunde (keine API-Keys, 0 Mappings). Siehe Projekt-CLAUDE.md (Copy Trading Bot).
set -o pipefail
BOTDIR=/home/botuser/copy-trading-bot
LOG=/home/botuser/scripts/kick_tunc_kardrekh.log
ENVF="$BOTDIR/.env"
DB="$BOTDIR/copy_trading.db"
TG_ID=7598310427
INVITE="https://telegram.me/+h65-HLCSYYBiYWMy"
CUST="569255ac-2ba4-4008-867f-b28b7872d1fe"
TOKEN=$(grep -E "^TELEGRAM_BOT_TOKEN=" "$ENVF" | head -1 | cut -d= -f2-)
MAIN=$(grep -E "^SIGNAL_PAID_GROUP_ID=" "$ENVF" | head -1 | cut -d= -f2-)
SCALP=$(grep -E "^SIGNAL_SCALP_GROUP_ID=" "$ENVF" | head -1 | cut -d= -f2-)
ADMIN=$(grep -E "^TELEGRAM_CHAT_ID=" "$ENVF" | head -1 | cut -d= -f2-)
echo "=== $(date -u) kick tunc START ===" >> "$LOG"
OKALL=1
for CHAT in "$MAIN" "$SCALP"; do
  RESP=$(curl -s "https://api.telegram.org/bot${TOKEN}/banChatMember" -d chat_id="$CHAT" -d user_id="$TG_ID")
  echo "banChatMember $CHAT -> $RESP" >> "$LOG"
  echo "$RESP" | grep -q '"ok":true' || OKALL=0
done
RESP=$(curl -s "https://api.telegram.org/bot${TOKEN}/revokeChatInviteLink" -d chat_id="$MAIN" -d invite_link="$INVITE")
echo "revokeInviteLink -> $RESP" >> "$LOG"
sqlite3 "$DB" "UPDATE dashboard_users SET payment_status='cancelled' WHERE id=386; UPDATE customers SET is_active=0, deactivated_at=CURRENT_TIMESTAMP WHERE id='${CUST}';"
echo "DB: payment_status=cancelled, customer is_active=0" >> "$LOG"
if [ "$OKALL" != "1" ] && [ -n "$ADMIN" ]; then
  curl -s "https://api.telegram.org/bot${TOKEN}/sendMessage" -d chat_id="$ADMIN" -d text="[KICK] kardrekh@gmail.com / Tunc (id 386): banChatMember nicht ueberall ok=true -> bitte manuell aus Paid-Gruppe/Scalp entfernen. Siehe kick_tunc_kardrekh.log" >/dev/null
  echo "ADMIN-ALERT gesendet (ban nicht ueberall ok)" >> "$LOG"
fi
echo "=== $(date -u) kick tunc DONE ===" >> "$LOG"
