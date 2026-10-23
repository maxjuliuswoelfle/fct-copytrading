#!/usr/bin/env bash
# One-shot Kick fuer Uwe Siegert / electrocon@t-online.de, dashboard_users id 389.
# Kuendigung 2026-08-27 (Ablefy-Event 27.08. 14:50 bestaetigt), access_valid_until 2026-09-07T00:00:00Z.
# Order 16588451, Monatsabo 96,45 EUR, letzte Zahlung 08.08.2026. Ansage Max: am 07.09.2026 kicken.
# Kuendigungsgrund laut Kunde: "Die Signale werden bei mir nicht angezeigt" (vermutlich nie dem
# Scalp-Channel beigetreten).
# ⚠️ KEINE Telegram-user-id in der DB. Die aus ManyChat bekannte "ID" 2031039197 ist eine
# ManyChat-Subscriber-ID und fuer banChatMember UNBRAUCHBAR (siehe Fall Arne / PARTICIPANT_ID_INVALID).
# Das Script liest telegram_chat_id daher zur LAUFZEIT: vorhanden -> Ban in Main + Scalp,
# leer -> Admin-Alert an Max ("manuell entfernen"). DB-Updates + Invite-Revoke laufen in beiden Faellen.
# Siehe Projekt-CLAUDE.md (Copy Trading Bot).
set -o pipefail
BOTDIR=/home/botuser/copy-trading-bot
LOG=/home/botuser/scripts/kick_uwe_siegert.log
ENVF="$BOTDIR/.env"
DB="$BOTDIR/copy_trading.db"
DUID=389
INVITE="https://telegram.me/+GoiVvLL2q5BlMGRi"
CUST="f5bcea07-6223-4565-8c02-7322a176a9d2"
TOKEN=$(grep -E "^TELEGRAM_BOT_TOKEN=" "$ENVF" | head -1 | cut -d= -f2-)
MAIN=$(grep -E "^SIGNAL_PAID_GROUP_ID=" "$ENVF" | head -1 | cut -d= -f2-)
SCALP=$(grep -E "^SIGNAL_SCALP_GROUP_ID=" "$ENVF" | head -1 | cut -d= -f2-)
ADMIN=$(grep -E "^TELEGRAM_CHAT_ID=" "$ENVF" | head -1 | cut -d= -f2-)
TG_ID=$(sqlite3 "$DB" "SELECT COALESCE(telegram_chat_id,'') FROM dashboard_users WHERE id=${DUID};")
echo "=== $(date -u) kick uwe_siegert START (tg_id='${TG_ID}') ===" >> "$LOG"
OKALL=1
if [ -n "$TG_ID" ]; then
  for CHAT in "$MAIN" "$SCALP"; do
    RESP=$(curl -s "https://api.telegram.org/bot${TOKEN}/banChatMember" -d chat_id="$CHAT" -d user_id="$TG_ID")
    echo "banChatMember $CHAT -> $RESP" >> "$LOG"
    echo "$RESP" | grep -q '"ok":true' || OKALL=0
  done
else
  OKALL=0
  echo "KEINE telegram_chat_id -> kein Auto-Kick moeglich" >> "$LOG"
fi
RESP=$(curl -s "https://api.telegram.org/bot${TOKEN}/revokeChatInviteLink" -d chat_id="$MAIN" -d invite_link="$INVITE")
echo "revokeInviteLink -> $RESP" >> "$LOG"
sqlite3 "$DB" "UPDATE dashboard_users SET payment_status='cancelled' WHERE id=${DUID}; UPDATE customers SET is_active=0, deactivated_at=CURRENT_TIMESTAMP WHERE id='${CUST}';"
echo "DB: payment_status=cancelled, customer is_active=0" >> "$LOG"
if [ "$OKALL" != "1" ] && [ -n "$ADMIN" ]; then
  curl -s "https://api.telegram.org/bot${TOKEN}/sendMessage" -d chat_id="$ADMIN" -d text="[KICK] electrocon@t-online.de / Uwe Siegert (id 389) Abo abgelaufen 07.09.2026 — Auto-Kick nicht sicher bestaetigt. Bitte MANUELL aus Paid-Gruppe/Scalp entfernen. Telegram-Name: Uwe Siegert." >> "$LOG" 2>&1
  echo "ADMIN-ALERT gesendet" >> "$LOG"
fi
echo "=== $(date -u) kick uwe_siegert DONE ===" >> "$LOG"
