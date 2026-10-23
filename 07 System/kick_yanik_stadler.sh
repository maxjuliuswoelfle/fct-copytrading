#!/usr/bin/env bash
# One-shot Kick fuer "yanik" (@yanik45427) / stadleryanik25@gmail.com, dashboard_users id 249.
# JAHRESABO 74,94 EUR (Kauf 30.06.2026, 12 Monate gebunden) — Max hat KULANZ gewaehrt und ihn
# vorzeitig rausgelassen. Ablefy-Event 24.08. 15:38 bestaetigt: access_valid_until 2026-08-30T00:00:00Z.
# Ansage Max: am 30.08.2026 kicken, "frueher raus gelassen".
# WICHTIG: KEIN permanenter Ban (analog Fall Aloy Ihenacho) -> ban + sofortiges unban = entfernt,
# aber NICHT gesperrt; er kann jederzeit wieder aufgenommen werden. Invite-Link wird entwertet.
# Telegram-ID 1344687283 (@yanik45427). NICHT verwechseln mit "Klotz Mensch" 7519922625 (anderer Kunde).
# Reiner Signal-Kunde (keine API-Keys, 0 Mappings). Siehe Projekt-CLAUDE.md (Copy Trading Bot).
set -o pipefail
BOTDIR=/home/botuser/copy-trading-bot
LOG=/home/botuser/scripts/kick_yanik_stadler.log
ENVF="$BOTDIR/.env"
DB="$BOTDIR/copy_trading.db"
TG_ID=1344687283
INVITE="https://telegram.me/+q9WzccvsWOJiNmUy"
CUST="618fb6c7-40cd-49d9-a543-0b35fd45c3ac"
TOKEN=$(grep -E "^TELEGRAM_BOT_TOKEN=" "$ENVF" | head -1 | cut -d= -f2-)
MAIN=$(grep -E "^SIGNAL_PAID_GROUP_ID=" "$ENVF" | head -1 | cut -d= -f2-)
SCALP=$(grep -E "^SIGNAL_SCALP_GROUP_ID=" "$ENVF" | head -1 | cut -d= -f2-)
ADMIN=$(grep -E "^TELEGRAM_CHAT_ID=" "$ENVF" | head -1 | cut -d= -f2-)
echo "=== $(date -u) kick yanik_stadler START (kick ohne Ban) ===" >> "$LOG"
OKALL=1
for CHAT in "$MAIN" "$SCALP"; do
  RESP=$(curl -s "https://api.telegram.org/bot${TOKEN}/banChatMember" -d chat_id="$CHAT" -d user_id="$TG_ID")
  echo "banChatMember $CHAT -> $RESP" >> "$LOG"
  echo "$RESP" | grep -q '"ok":true' || OKALL=0
  # Sperre sofort wieder aufheben -> User ist entfernt, aber NICHT gebannt (Kulanz-Fall)
  RESP=$(curl -s "https://api.telegram.org/bot${TOKEN}/unbanChatMember" -d chat_id="$CHAT" -d user_id="$TG_ID" -d only_if_banned=true)
  echo "unbanChatMember $CHAT -> $RESP" >> "$LOG"
done
RESP=$(curl -s "https://api.telegram.org/bot${TOKEN}/revokeChatInviteLink" -d chat_id="$MAIN" -d invite_link="$INVITE")
echo "revokeInviteLink -> $RESP" >> "$LOG"
sqlite3 "$DB" "UPDATE dashboard_users SET payment_status='cancelled' WHERE id=249; UPDATE customers SET is_active=0, deactivated_at=CURRENT_TIMESTAMP WHERE id='${CUST}';"
echo "DB: payment_status=cancelled, customer is_active=0" >> "$LOG"
if [ "$OKALL" != "1" ] && [ -n "$ADMIN" ]; then
  curl -s "https://api.telegram.org/bot${TOKEN}/sendMessage" -d chat_id="$ADMIN" -d text="[KICK] stadleryanik25@gmail.com / yanik (id 249): Entfernen nicht ueberall ok=true -> bitte manuell aus Paid-Gruppe/Scalp entfernen. Siehe kick_yanik_stadler.log" >> "$LOG" 2>&1
  echo "ADMIN-ALERT gesendet (kick nicht ueberall ok)" >> "$LOG"
fi
echo "=== $(date -u) kick yanik_stadler DONE ===" >> "$LOG"
