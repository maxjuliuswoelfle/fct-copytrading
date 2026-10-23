#!/usr/bin/env bash
# One-shot Kick fuer "Moni" / Monica Masi Imoberdorf, moni1174@proton.me, dashboard_users id 336.
# JAHRESABO 74,94 EUR (Kauf 01.07.2026, 12 Monate gebunden) -> Max hat vorzeitig rausgelassen (Kulanz).
# Ablefy-Event 26.08. 14:33 bestaetigt: access_valid_until 2026-09-01T00:00:00Z.
# Order 16547115, letzte Zahlung 02.08.2026. Ansage Max: am 01.09.2026 kicken.
# WICHTIG: KEIN permanenter Ban (analog Aloy Ihenacho / Yanik Stadler) -> ban + sofortiges unban
# = entfernt, aber NICHT gesperrt. Invite-Link wird entwertet.
# Telegram-ID 5346127937 (@moni_74), bei Erfassung member in Main UND Scalp.
# Reine Signal-Kundin (keine API-Keys, 0 Mappings). Siehe Projekt-CLAUDE.md (Copy Trading Bot).
set -o pipefail
BOTDIR=/home/botuser/copy-trading-bot
LOG=/home/botuser/scripts/kick_monica_masi.log
ENVF="$BOTDIR/.env"
DB="$BOTDIR/copy_trading.db"
TG_ID=5346127937
INVITE="https://telegram.me/+XatHi-jvm1ZhNDZi"
CUST="3ba4a946-ff05-4a09-93c1-20b7f374f94e"
TOKEN=$(grep -E "^TELEGRAM_BOT_TOKEN=" "$ENVF" | head -1 | cut -d= -f2-)
MAIN=$(grep -E "^SIGNAL_PAID_GROUP_ID=" "$ENVF" | head -1 | cut -d= -f2-)
SCALP=$(grep -E "^SIGNAL_SCALP_GROUP_ID=" "$ENVF" | head -1 | cut -d= -f2-)
ADMIN=$(grep -E "^TELEGRAM_CHAT_ID=" "$ENVF" | head -1 | cut -d= -f2-)
echo "=== $(date -u) kick monica_masi START (kick ohne Ban) ===" >> "$LOG"
OKALL=1
for CHAT in "$MAIN" "$SCALP"; do
  RESP=$(curl -s "https://api.telegram.org/bot${TOKEN}/banChatMember" -d chat_id="$CHAT" -d user_id="$TG_ID")
  echo "banChatMember $CHAT -> $RESP" >> "$LOG"
  echo "$RESP" | grep -q '"ok":true' || OKALL=0
  RESP=$(curl -s "https://api.telegram.org/bot${TOKEN}/unbanChatMember" -d chat_id="$CHAT" -d user_id="$TG_ID" -d only_if_banned=true)
  echo "unbanChatMember $CHAT -> $RESP" >> "$LOG"
done
RESP=$(curl -s "https://api.telegram.org/bot${TOKEN}/revokeChatInviteLink" -d chat_id="$MAIN" -d invite_link="$INVITE")
echo "revokeInviteLink -> $RESP" >> "$LOG"
sqlite3 "$DB" "UPDATE dashboard_users SET payment_status='cancelled' WHERE id=336; UPDATE customers SET is_active=0, deactivated_at=CURRENT_TIMESTAMP WHERE id='${CUST}';"
echo "DB: payment_status=cancelled, customer is_active=0" >> "$LOG"
if [ "$OKALL" != "1" ] && [ -n "$ADMIN" ]; then
  curl -s "https://api.telegram.org/bot${TOKEN}/sendMessage" -d chat_id="$ADMIN" -d text="[KICK] moni1174@proton.me / Moni (id 336): Entfernen nicht ueberall ok=true -> bitte manuell aus Paid-Gruppe/Scalp entfernen. Siehe kick_monica_masi.log" >> "$LOG" 2>&1
  echo "ADMIN-ALERT gesendet (kick nicht ueberall ok)" >> "$LOG"
fi
echo "=== $(date -u) kick monica_masi DONE ===" >> "$LOG"
