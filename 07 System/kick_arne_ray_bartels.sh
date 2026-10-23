#!/usr/bin/env bash
# One-shot Kick fuer Arne / ray.bartels@icloud.com, dashboard_users id 385.
# Kuendigung erfasst 2026-07-27 (Max hat Abo gekuendigt), geplant 2026-08-06 (bezahlt bis dahin).
# Ansage Max: am 06.08.2026 kicken. Telegram-Name: Arne.
# Reiner Signal-Kunde (keine API-Keys, 0 Mappings) -> kein Copy-Trading-Risiko.
# Telegram-user-id 747060583 aus ManyChat uebernommen und in telegram_chat_id gespeichert.
# HINWEIS: Bei Erfassung meldete getChatMember 'PARTICIPANT_ID_INVALID' (evtl. noch nicht
# beigetreten). Script versucht trotzdem banChatMember (praeventiv) + Admin-Alert bei Fehler.
# Siehe Projekt-CLAUDE.md (Copy Trading Bot).
set -o pipefail
BOTDIR=/home/botuser/copy-trading-bot
LOG=/home/botuser/scripts/kick_arne_ray_bartels.log
ENVF="$BOTDIR/.env"
DB="$BOTDIR/copy_trading.db"
UID_DB=385
CUST="84ba7e89-9f56-4437-aa05-cc7dde808cba"
INVITE="https://telegram.me/+-20zTKfqyIRmYzAy"
TOKEN=$(grep -E '^TELEGRAM_BOT_TOKEN=' "$ENVF" | head -1 | cut -d= -f2-)
ADMIN=$(grep -E '^TELEGRAM_CHAT_ID=' "$ENVF" | head -1 | cut -d= -f2-)
MAIN=$(grep -E '^SIGNAL_PAID_GROUP_ID=' "$ENVF" | head -1 | cut -d= -f2-)
SCALP=$(grep -E '^SIGNAL_SCALP_GROUP_ID=' "$ENVF" | head -1 | cut -d= -f2-)
TG_ID=$(sqlite3 "$DB" "SELECT COALESCE(telegram_chat_id,'') FROM dashboard_users WHERE id=${UID_DB};")
echo "=== $(date -u) kick arne_ray_bartels START (tg_id='${TG_ID}') ===" >> "$LOG"
FAILED=0
if [ -n "$TG_ID" ]; then
  for CHAT in "$MAIN" "$SCALP"; do
    RESP=$(curl -s "https://api.telegram.org/bot${TOKEN}/banChatMember" -d chat_id="$CHAT" -d user_id="$TG_ID")
    echo "banChatMember $CHAT -> $RESP" >> "$LOG"
    echo "$RESP" | grep -q '"ok":true' || FAILED=1
  done
else
  FAILED=1
fi
if [ "$FAILED" = "1" ]; then
  MSG="⚠️ Arne (ray.bartels@icloud.com, id 385) Abo abgelaufen 06.08.2026 — Auto-Kick nicht sicher bestaetigt (tg_id='${TG_ID}'). Bitte PRUEFEN und ggf. MANUELL aus der Paid-Gruppe 'FCT | Copy Trading' entfernen. Telegram-Name: Arne."
  RESP=$(curl -s "https://api.telegram.org/bot${TOKEN}/sendMessage" -d chat_id="$ADMIN" --data-urlencode text="$MSG")
  echo "FAILED/NO TG_ID -> admin alert -> $RESP" >> "$LOG"
fi
RESP=$(curl -s "https://api.telegram.org/bot${TOKEN}/revokeChatInviteLink" -d chat_id="$MAIN" -d invite_link="$INVITE")
echo "revokeInviteLink -> $RESP" >> "$LOG"
sqlite3 "$DB" "UPDATE dashboard_users SET payment_status='cancelled' WHERE id=${UID_DB}; UPDATE customers SET is_active=0, deactivated_at=CURRENT_TIMESTAMP WHERE id='${CUST}';"
echo "DB: payment_status=cancelled, customer is_active=0" >> "$LOG"
echo "=== $(date -u) kick arne_ray_bartels DONE ===" >> "$LOG"
