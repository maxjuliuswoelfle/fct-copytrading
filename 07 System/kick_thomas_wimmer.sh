#!/usr/bin/env bash
# One-shot Kick fuer Thomas Wimmer / wimmerthomas04@gmail.com, dashboard_users id 375.
# Gemeldet 2026-09-16 via Support-Bot (Header [ID: 1257192191], Kundennummer selbst genannt und
# korrekt: a61d8f28-8d98-4f78-b49c-38bad7f3397b). Grund: "komme derzeit nicht zum Trading,
# will es spaeter nochmal probieren". Ansage Max: am 09.10.2026 kicken.
#
# Telegram: "Tom" (@Bizepsbrutalo), user-id 1257192191 — per getChatMember verifiziert (2026-09-16):
#    member in Main (-1003888563475), LEFT im Scalp (-1004292274970) -> Scalp-Ban praeventiv.
#    ID war in der DB LEER und wurde am 2026-09-16 nachgetragen (sonst nur Admin-Alert statt Ban).
# Ablefy: order.subscription.canceled + payer.access.changed am 2026-09-16 08:32,
#    access_valid_until 2026-10-09T00:00:00Z (= Max' Datum, kein offener Ablefy-Punkt).
# Order 16581710, Produkt 517561, Monatsabo 96,45 EUR (SEPA), Kauf 06.07.2026,
#    Zahlungen 09.07. / 13.08. / 15.09.2026.
# Reiner Signal-Kunde — KEINE API-Keys (Laenge 0), 0 Positions-Mappings, kein Copy-Trading-Risiko.
#
# LAUFZEIT-CHECK auf zwischenzeitlichen Neukauf (Lehre Lihua/Timo), inkl. PRODUKT-FILTER:
# nur unsere Produkte 517561/517562 zaehlen. NICHT nach Zeitstempel filtern: das Kuendigungs-Event
# traegt selbst access_type=GRANT. Siehe Projekt-CLAUDE.md (Copy Trading Bot).
set -o pipefail
BOTDIR=/home/botuser/copy-trading-bot
LOG=/home/botuser/scripts/kick_thomas_wimmer.log
ENVF="$BOTDIR/.env"
DB="$BOTDIR/copy_trading.db"
DUID=375
EMAIL="wimmerthomas04@gmail.com"
INVITE="https://telegram.me/+cUY5ynAG0_NmMTRi"
CUST="a61d8f28-8d98-4f78-b49c-38bad7f3397b"
VALID_UNTIL="2026-10-09T00:00:00Z"
TOKEN=$(grep -E "^TELEGRAM_BOT_TOKEN=" "$ENVF" | head -1 | cut -d= -f2-)
MAIN=$(grep -E "^SIGNAL_PAID_GROUP_ID=" "$ENVF" | head -1 | cut -d= -f2-)
SCALP=$(grep -E "^SIGNAL_SCALP_GROUP_ID=" "$ENVF" | head -1 | cut -d= -f2-)
ADMIN=$(grep -E "^TELEGRAM_CHAT_ID=" "$ENVF" | head -1 | cut -d= -f2-)
TG_ID=$(sqlite3 "$DB" "SELECT COALESCE(telegram_chat_id,'') FROM dashboard_users WHERE id=${DUID};")
echo "=== $(date -u) kick thomas_wimmer START (tg_id='${TG_ID}') ===" >> "$LOG"

# --- Laufzeit-Check: hat der Kunde nach der Kuendigung neu gekauft? ---
G_SQL="FROM webhook_logs WHERE lower(payload) LIKE '%${EMAIL}%' AND json_extract(payload,'\$.access.access_type')='GRANT' AND CAST(json_extract(payload,'\$.product.product_id') AS TEXT) IN ('517561','517562') AND COALESCE(json_extract(payload,'\$.access.access_valid_until'),'') > '${VALID_UNTIL}'"
REGRANT=$(sqlite3 "$DB" "SELECT COUNT(*) ${G_SQL};")
G_MAXUNTIL=$(sqlite3 "$DB" "SELECT COALESCE(MAX(json_extract(payload,'\$.access.access_valid_until')),'') ${G_SQL};")
echo "Re-GRANT-Check (valid_until > ${VALID_UNTIL}): ${REGRANT} (max ${G_MAXUNTIL})" >> "$LOG"
if [ "$REGRANT" != "0" ]; then
  echo "ABBRUCH: neuerer GRANT gefunden -> KEIN Ban, nur Admin-Alert" >> "$LOG"
  [ -n "$ADMIN" ] && curl -s "https://api.telegram.org/bot${TOKEN}/sendMessage" -d chat_id="$ADMIN" --data-urlencode text="[KICK ABGEBROCHEN] ${EMAIL} (Thomas Wimmer / Tom, id ${DUID}) sollte heute gekickt werden - laut Ablefy hat er aber WIEDER GEZAHLT (Zugang gueltig bis ${G_MAXUNTIL}). Kein Ban ausgefuehrt, Zugang bleibt. Falls er spaeter doch raus soll: neuen Kick-Termin setzen." >> "$LOG" 2>&1
  echo "=== $(date -u) kick thomas_wimmer ABORTED (re-grant) ===" >> "$LOG"
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
  curl -s "https://api.telegram.org/bot${TOKEN}/sendMessage" -d chat_id="$ADMIN" --data-urlencode text="[KICK] ${EMAIL} / Thomas Wimmer (id ${DUID}) Abo abgelaufen 09.10.2026 - Auto-Kick nicht sicher bestaetigt. Bitte MANUELL aus Paid-Gruppe/Scalp entfernen. Telegram: Tom (@Bizepsbrutalo, ID 1257192191)." >> "$LOG" 2>&1
  echo "ADMIN-ALERT gesendet" >> "$LOG"
fi
echo "=== $(date -u) kick thomas_wimmer DONE ===" >> "$LOG"
