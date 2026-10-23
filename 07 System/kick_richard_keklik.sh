#!/usr/bin/env bash
# One-shot Kick fuer Richard Keklik (richardkeklik@gmail.com), dashboard_users id 180.
# Kuendigung erfasst 2026-07-22 (in Ablefy gekuendigt), geplant 2026-07-28 (bezahlt bis dahin).
# Ansage Max: abgeschlossen 28.06., bis 28.07.2026 Zugriff, danach kicken. Handle: @Richikek82.
# Reiner Signal-Kunde (keine API-Keys, 0 Mappings) -> kein Copy-Trading-Risiko.
# ACHTUNG: telegram_chat_id war bei Erfassung LEER (Handle @username laesst sich NICHT
# in die numerische user-id aufloesen) -> Auto-Kick nur, wenn die numerische Telegram-user-id
# bis dahin eingefangen + in dashboard_users.telegram_chat_id gespeichert wurde.
# Sonst: DB-Updates + Invite-Revoke + Admin-Alert (manuell entfernen).
# Siehe Projekt-CLAUDE.md (Copy Trading Bot).
set -o pipefail
BOTDIR=/home/botuser/copy-trading-bot
LOG=/home/botuser/scripts/kick_richard_keklik.log
ENVF="$BOTDIR/.env"
DB="$BOTDIR/copy_trading.db"
UID_DB=180
CUST="44ff9e77-26bd-4b43-a781-db73983370bf"
INVITE="https://telegram.me/+agHwjUDW7Ps2OTNi"
TOKEN=$(grep -E '^TELEGRAM_BOT_TOKEN=' "$ENVF" | head -1 | cut -d= -f2-)
ADMIN=$(grep -E '^TELEGRAM_CHAT_ID=' "$ENVF" | head -1 | cut -d= -f2-)
MAIN=$(grep -E '^SIGNAL_PAID_GROUP_ID=' "$ENVF" | head -1 | cut -d= -f2-)
SCALP=$(grep -E '^SIGNAL_SCALP_GROUP_ID=' "$ENVF" | head -1 | cut -d= -f2-)
TG_ID=$(sqlite3 "$DB" "SELECT COALESCE(telegram_chat_id,'') FROM dashboard_users WHERE id=${UID_DB};")
echo "=== $(date -u) kick richard_keklik START (tg_id='${TG_ID}') ===" >> "$LOG"
if [ -n "$TG_ID" ]; then
  for CHAT in "$MAIN" "$SCALP"; do
    RESP=$(curl -s "https://api.telegram.org/bot${TOKEN}/banChatMember" -d chat_id="$CHAT" -d user_id="$TG_ID")
    echo "banChatMember $CHAT -> $RESP" >> "$LOG"
  done
else
  MSG="⚠️ Richard Keklik (richardkeklik@gmail.com) Abo abgelaufen 28.07.2026 — KEINE telegram_chat_id gespeichert. Bitte MANUELL aus der Paid-Gruppe 'FCT | Copy Trading' entfernen. Handle: @Richikek82."
  RESP=$(curl -s "https://api.telegram.org/bot${TOKEN}/sendMessage" -d chat_id="$ADMIN" --data-urlencode text="$MSG")
  echo "NO TG_ID -> admin alert -> $RESP" >> "$LOG"
fi
RESP=$(curl -s "https://api.telegram.org/bot${TOKEN}/revokeChatInviteLink" -d chat_id="$MAIN" -d invite_link="$INVITE")
echo "revokeInviteLink -> $RESP" >> "$LOG"
sqlite3 "$DB" "UPDATE dashboard_users SET payment_status='cancelled' WHERE id=${UID_DB}; UPDATE customers SET is_active=0, deactivated_at=CURRENT_TIMESTAMP WHERE id='${CUST}';"
echo "DB: payment_status=cancelled, customer is_active=0" >> "$LOG"
echo "=== $(date -u) kick richard_keklik DONE ===" >> "$LOG"
