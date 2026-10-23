#!/usr/bin/env bash
# One-shot Kick fuer Stephan Horn (1hornstephan@gmx.de), dashboard_users id 395.
# Kuendigung erfasst 2026-07-27 (in Ablefy gekuendigt), geplant 2026-08-09 (bezahlt bis dahin).
# Ansage Max: bis 09.08.2026 Zugriff, danach kicken + Abo kuendigen. Telegram-Name: Stephan Horn.
# Reiner Signal-Kunde (keine API-Keys, 0 Mappings) -> kein Copy-Trading-Risiko.
# ACHTUNG: telegram_chat_id war bei Erfassung LEER (Anzeigename laesst sich NICHT
# in die numerische user-id aufloesen) -> Auto-Kick nur, wenn die numerische Telegram-user-id
# bis dahin eingefangen + in dashboard_users.telegram_chat_id gespeichert wurde.
# Sonst: DB-Updates + Invite-Revoke + Admin-Alert (manuell entfernen).
# Siehe Projekt-CLAUDE.md (Copy Trading Bot).
set -o pipefail
BOTDIR=/home/botuser/copy-trading-bot
LOG=/home/botuser/scripts/kick_stephan_horn.log
ENVF="$BOTDIR/.env"
DB="$BOTDIR/copy_trading.db"
UID_DB=395
CUST="ed4e550c-28a6-4a8f-b0c5-c39888504829"
INVITE="https://telegram.me/+s8FDG-oiHwwxNzAy"
TOKEN=$(grep -E '^TELEGRAM_BOT_TOKEN=' "$ENVF" | head -1 | cut -d= -f2-)
ADMIN=$(grep -E '^TELEGRAM_CHAT_ID=' "$ENVF" | head -1 | cut -d= -f2-)
MAIN=$(grep -E '^SIGNAL_PAID_GROUP_ID=' "$ENVF" | head -1 | cut -d= -f2-)
SCALP=$(grep -E '^SIGNAL_SCALP_GROUP_ID=' "$ENVF" | head -1 | cut -d= -f2-)
TG_ID=$(sqlite3 "$DB" "SELECT COALESCE(telegram_chat_id,'') FROM dashboard_users WHERE id=${UID_DB};")
echo "=== $(date -u) kick stephan_horn START (tg_id='${TG_ID}') ===" >> "$LOG"
if [ -n "$TG_ID" ]; then
  for CHAT in "$MAIN" "$SCALP"; do
    RESP=$(curl -s "https://api.telegram.org/bot${TOKEN}/banChatMember" -d chat_id="$CHAT" -d user_id="$TG_ID")
    echo "banChatMember $CHAT -> $RESP" >> "$LOG"
  done
else
  MSG="⚠️ Stephan Horn (1hornstephan@gmx.de) Abo abgelaufen 09.08.2026 — KEINE telegram_chat_id gespeichert. Bitte MANUELL aus der Paid-Gruppe 'FCT | Copy Trading' entfernen. Telegram-Name: Stephan Horn."
  RESP=$(curl -s "https://api.telegram.org/bot${TOKEN}/sendMessage" -d chat_id="$ADMIN" --data-urlencode text="$MSG")
  echo "NO TG_ID -> admin alert -> $RESP" >> "$LOG"
fi
RESP=$(curl -s "https://api.telegram.org/bot${TOKEN}/revokeChatInviteLink" -d chat_id="$MAIN" -d invite_link="$INVITE")
echo "revokeInviteLink -> $RESP" >> "$LOG"
sqlite3 "$DB" "UPDATE dashboard_users SET payment_status='cancelled' WHERE id=${UID_DB}; UPDATE customers SET is_active=0, deactivated_at=CURRENT_TIMESTAMP WHERE id='${CUST}';"
echo "DB: payment_status=cancelled, customer is_active=0" >> "$LOG"
echo "=== $(date -u) kick stephan_horn DONE ===" >> "$LOG"
