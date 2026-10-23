#!/usr/bin/env bash
# One-shot Kick fuer Ivan Latkovic / ivan.latkovic.laci@gmail.com, dashboard_users id 456.
# Kuendigung 2026-09-04 via Support-Bot ("Abo kuendigen", [ID: 6936844220]).
# Ablefy-Event `order.subscription.canceled` + `payer.access.changed` am 04.09. 11:23 bestaetigt,
# access_valid_until 2026-09-23T00:00:00Z. Order 16893931, Produkt 517561, Monatsabo 79,95 EUR,
# Kauf/letzte Zahlung 23.08.2026. Ansage Max: am 23.09.2026 kicken.
# Reiner Signal-Kunde — KEINE API-Keys (Laenge 0), 0 Positions-Mappings, kein Copy-Trading-Risiko.
# Telegram-user-id 6936844220 war via chat_member-Auto-Capture bereits in der DB und wurde per
# getChatMember verifiziert (loest auf "Ivanzz." — member in Main, left im Scalp -> Ban dort praeventiv).
# Das Script liest telegram_chat_id zur LAUFZEIT: vorhanden -> Ban in Main + Scalp,
# leer -> Admin-Alert an Max ("manuell entfernen"). DB-Updates + Invite-Revoke laufen in beiden Faellen.
# Siehe Projekt-CLAUDE.md (Copy Trading Bot).
set -o pipefail
BOTDIR=/home/botuser/copy-trading-bot
LOG=/home/botuser/scripts/kick_ivan_latkovic.log
ENVF="$BOTDIR/.env"
DB="$BOTDIR/copy_trading.db"
DUID=456
INVITE="https://telegram.me/+T1Pt0tdlA0NiNjcy"
CUST="eea91ac6-2f79-4379-b0a2-3b971e02f0c0"
TOKEN=$(grep -E "^TELEGRAM_BOT_TOKEN=" "$ENVF" | head -1 | cut -d= -f2-)
MAIN=$(grep -E "^SIGNAL_PAID_GROUP_ID=" "$ENVF" | head -1 | cut -d= -f2-)
SCALP=$(grep -E "^SIGNAL_SCALP_GROUP_ID=" "$ENVF" | head -1 | cut -d= -f2-)
ADMIN=$(grep -E "^TELEGRAM_CHAT_ID=" "$ENVF" | head -1 | cut -d= -f2-)
TG_ID=$(sqlite3 "$DB" "SELECT COALESCE(telegram_chat_id,'') FROM dashboard_users WHERE id=${DUID};")
echo "=== $(date -u) kick ivan_latkovic START (tg_id='${TG_ID}') ===" >> "$LOG"

# --- Laufzeit-Check (nachgeruestet 2026-09-11, Lehre Lihua/Timo): hat der Kunde wieder gezahlt? ---
# Liegt fuer unser Produkt ein Ablefy-GRANT mit SPAETEREM access_valid_until als dem
# Laufzeitende vor -> KEIN Ban, nur Admin-Alert.
# NICHT nach Zeitstempel filtern: das Kuendigungs-Event traegt selbst access_type=GRANT.
G_EMAIL="ivan.latkovic.laci@gmail.com"
G_UNTIL="2026-09-23T00:00:00Z"
G_SQL="FROM webhook_logs WHERE lower(payload) LIKE '%${G_EMAIL}%' AND json_extract(payload,'\$.access.access_type')='GRANT' AND CAST(json_extract(payload,'\$.product.product_id') AS TEXT) IN ('517561','517562') AND COALESCE(json_extract(payload,'\$.access.access_valid_until'),'') > '${G_UNTIL}'"
REGRANT=$(sqlite3 "$DB" "SELECT COUNT(*) ${G_SQL};")
G_MAXUNTIL=$(sqlite3 "$DB" "SELECT COALESCE(MAX(json_extract(payload,'\$.access.access_valid_until')),'') ${G_SQL};")
echo "Re-GRANT-Check (valid_until > ${G_UNTIL}): ${REGRANT} (max ${G_MAXUNTIL})" >> "$LOG"
if [ "$REGRANT" != "0" ]; then
  echo "ABBRUCH: neuerer GRANT gefunden -> KEIN Ban, nur Admin-Alert" >> "$LOG"
  [ -n "$ADMIN" ] && curl -s "https://api.telegram.org/bot${TOKEN}/sendMessage" -d chat_id="$ADMIN" --data-urlencode text="[KICK ABGEBROCHEN] ${G_EMAIL} sollte heute gekickt werden - laut Ablefy hat der Kunde aber WIEDER GEZAHLT (Zugang gueltig bis ${G_MAXUNTIL}). Kein Ban ausgefuehrt, Zugang bleibt. Falls er spaeter doch raus soll: neuen Kick-Termin setzen." >> "$LOG" 2>&1
  echo "=== $(date -u) kick_ivan_latkovic ABORTED (re-grant) ===" >> "$LOG"
  exit 0
fi

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
  curl -s "https://api.telegram.org/bot${TOKEN}/sendMessage" -d chat_id="$ADMIN" -d text="[KICK] ivan.latkovic.laci@gmail.com / Ivan Latkovic (id 456) Abo abgelaufen 23.09.2026 — Auto-Kick nicht sicher bestaetigt. Bitte MANUELL aus Paid-Gruppe/Scalp entfernen. Telegram-Name: Ivanzz. (ID 6936844220)." >> "$LOG" 2>&1
  echo "ADMIN-ALERT gesendet" >> "$LOG"
fi
echo "=== $(date -u) kick ivan_latkovic DONE ===" >> "$LOG"
