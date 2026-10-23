#!/usr/bin/env bash
# One-shot Kick fuer Michael Adams / mikeadmore@proton.me, dashboard_users id 268.
# Ansage Max (2026-09-23): am 30.06.2027 kicken.
#
# JAHRESABO Launch-Angebot (Plan 610909, 74,94 EUR/Monat, Karte, 12 Monate gebunden),
#   Order 16536637, Produkt 517561, Kauf 30.06.2026 -> Laufzeitende 30.06.2027.
#   Zahlungen: 30.06. / 31.07. / 31.08.2026, naechste Rate laut Ablefy 30.09.2026.
# Reiner Signal-Kunde — KEINE API-Keys, 0 Positions-Mappings, nicht auf der Blocklist.
#
# ⚠️ telegram_chat_id ist LEER (Launch-Kohorte, Beitritt vor der Auto-Capture vom 28.07.2026).
#   Das Script liest die ID zur LAUFZEIT: ist sie bis dahin da -> echter Ban;
#   ist sie leer -> nur Admin-Alert (Max muss dann manuell entfernen).
# ⚠️ In Ablefy ist NICHT gekuendigt (kein order.subscription.canceled in webhook_logs) —
#   sonst verlaengert sich das Jahresabo im Juni 2027 automatisch. Wie Aschenbrenner/Endorphine.
#
# LAUFZEIT-CHECK auf zwischenzeitlichen Neukauf, inkl. PRODUKT-FILTER (nur 517561/517562).
# NICHT nach Zeitstempel filtern: das Kuendigungs-Event traegt selbst access_type=GRANT.
# Hinweis: Fuer diesen Kunden hat Ablefy bisher GAR KEINE payer.access.changed-Events
# geschickt -> der Check steht aktuell strukturell auf 0 (wie bei Aschenbrenner).
set -o pipefail
BOTDIR=/home/botuser/copy-trading-bot
LOG=/home/botuser/scripts/kick_michael_adams.log
ENVF="$BOTDIR/.env"
DB="$BOTDIR/copy_trading.db"
DUID=268
EMAIL="mikeadmore@proton.me"
INVITE="https://telegram.me/+d0jHYq4T17dkYTky"
CUST="b802e0d9-0d44-411f-99fc-a59c3bf0bab6"
VALID_UNTIL="2027-06-30T00:00:00Z"
TOKEN=$(grep -E "^TELEGRAM_BOT_TOKEN=" "$ENVF" | head -1 | cut -d= -f2-)
MAIN=$(grep -E "^SIGNAL_PAID_GROUP_ID=" "$ENVF" | head -1 | cut -d= -f2-)
SCALP=$(grep -E "^SIGNAL_SCALP_GROUP_ID=" "$ENVF" | head -1 | cut -d= -f2-)
ADMIN=$(grep -E "^TELEGRAM_CHAT_ID=" "$ENVF" | head -1 | cut -d= -f2-)
TG_ID=$(sqlite3 "$DB" "SELECT COALESCE(telegram_chat_id,'') FROM dashboard_users WHERE id=${DUID};")
echo "=== $(date -u) kick michael_adams START (tg_id='${TG_ID}') ===" >> "$LOG"

# --- Laufzeit-Check: hat der Kunde nach der Kuendigung neu gekauft? ---
G_SQL="FROM webhook_logs WHERE lower(payload) LIKE '%${EMAIL}%' AND json_extract(payload,'\$.access.access_type')='GRANT' AND CAST(json_extract(payload,'\$.product.id') AS TEXT) IN ('517561','517562') AND COALESCE(json_extract(payload,'\$.access.access_valid_until'),'') > '${VALID_UNTIL}'"
REGRANT=$(sqlite3 "$DB" "SELECT COUNT(*) ${G_SQL};")
G_MAXUNTIL=$(sqlite3 "$DB" "SELECT COALESCE(MAX(json_extract(payload,'\$.access.access_valid_until')),'') ${G_SQL};")
echo "Re-GRANT-Check (valid_until > ${VALID_UNTIL}): ${REGRANT} (max ${G_MAXUNTIL})" >> "$LOG"
if [ "$REGRANT" != "0" ]; then
  echo "ABBRUCH: neuerer GRANT gefunden -> KEIN Ban, nur Admin-Alert" >> "$LOG"
  [ -n "$ADMIN" ] && curl -s "https://api.telegram.org/bot${TOKEN}/sendMessage" -d chat_id="$ADMIN" --data-urlencode text="[KICK ABGEBROCHEN] ${EMAIL} (Michael Adams, id ${DUID}) sollte heute gekickt werden - laut Ablefy hat er aber WIEDER GEZAHLT (Zugang gueltig bis ${G_MAXUNTIL}). Kein Ban ausgefuehrt, Zugang bleibt." >> "$LOG" 2>&1
  echo "=== $(date -u) kick michael_adams ABORTED (re-grant) ===" >> "$LOG"
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
RESP=$(curl -s "https://api.telegram.org/bot${TOKEN}/revokeChatInviteLink" -d chat_id="$MAIN" --data-urlencode "invite_link=${INVITE}")
echo "revokeInviteLink -> $RESP" >> "$LOG"
sqlite3 "$DB" "UPDATE dashboard_users SET payment_status='cancelled' WHERE id=${DUID}; UPDATE customers SET is_active=0, deactivated_at=CURRENT_TIMESTAMP WHERE id='${CUST}';"
echo "DB: payment_status=cancelled, customer is_active=0" >> "$LOG"
if [ "$OKALL" != "1" ] && [ -n "$ADMIN" ]; then
  curl -s "https://api.telegram.org/bot${TOKEN}/sendMessage" -d chat_id="$ADMIN" --data-urlencode text="[KICK] ${EMAIL} / Michael Adams (id ${DUID}) Jahresabo-Laufzeit endet 30.06.2027 - Auto-Kick nicht sicher bestaetigt (keine/ungueltige Telegram-ID). Bitte MANUELL aus Paid-Gruppe/Scalp entfernen." >> "$LOG" 2>&1
  echo "ADMIN-ALERT gesendet" >> "$LOG"
fi
echo "=== $(date -u) kick michael_adams DONE ===" >> "$LOG"
