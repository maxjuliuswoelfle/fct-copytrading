#!/usr/bin/env bash
# One-shot Kick fuer Dominik Rappers / dominik-e-mail@web.de, dashboard_users id 401.
# Gemeldet 2026-09-22 via Support-Bot (Header [ID: 241330065], Telegram-Name "Domi .").
# Ansage Max: am 16.10.2026 kicken.
#
# ⚠️ FUENF "Dominik" im System — unserer ist id 401 (Rappers). Nicht verwechseln mit
#    id 58 Ochsendorf (icebox23@hotmail.de, 11.09. reaktiviert), id 100 Krupitza,
#    id 156 Hoerschlaeger, id 332 dominik.blum89@yahoo.de.
#
# Telegram: "Domi ." user-id 241330065 — per getChatMember verifiziert (2026-09-22):
#    member in Main UND Scalp. ID war in der DB LEER und wurde am 2026-09-22 nachgetragen
#    (sonst haette der Timer nur einen Admin-Alert statt eines Bans ausgeloest).
# Ablefy: order.subscription.canceled + payer.access.changed am 2026-09-22 13:18,
#    access_valid_until 2026-10-16T00:00:00Z (= Max' Datum, kein offener Ablefy-Punkt).
# Order 16623926, Produkt 517561, Monatsabo 96,45 EUR (SEPA), Kauf 13.07.2026,
#    Zahlungen 16.07. / 20.08. / 22.09.2026 — die letzte Rate kam am Kuendigungstag selbst
#    (10:08 bezahlt, 13:18 gekuendigt) -> Zugang laeuft noch bis 16.10.
# Reiner Signal-Kunde — KEINE API-Keys (Laenge 0), 0 Positions-Mappings, kein Copy-Trading-Risiko.
#
# LAUFZEIT-CHECK auf zwischenzeitlichen Neukauf (Lehre Lihua/Timo), inkl. PRODUKT-FILTER:
# nur unsere Produkte 517561/517562 zaehlen. NICHT nach Zeitstempel filtern: das Kuendigungs-Event
# traegt selbst access_type=GRANT. Siehe Projekt-CLAUDE.md (Copy Trading Bot).
set -o pipefail
BOTDIR=/home/botuser/copy-trading-bot
LOG=/home/botuser/scripts/kick_dominik_rappers.log
ENVF="$BOTDIR/.env"
DB="$BOTDIR/copy_trading.db"
DUID=401
EMAIL="dominik-e-mail@web.de"
INVITE="https://telegram.me/+CLeh4RtgJl9iNmRi"
CUST="21ac9d3f-5280-4253-8cea-210495db2188"
VALID_UNTIL="2026-10-16T00:00:00Z"
TOKEN=$(grep -E "^TELEGRAM_BOT_TOKEN=" "$ENVF" | head -1 | cut -d= -f2-)
MAIN=$(grep -E "^SIGNAL_PAID_GROUP_ID=" "$ENVF" | head -1 | cut -d= -f2-)
SCALP=$(grep -E "^SIGNAL_SCALP_GROUP_ID=" "$ENVF" | head -1 | cut -d= -f2-)
ADMIN=$(grep -E "^TELEGRAM_CHAT_ID=" "$ENVF" | head -1 | cut -d= -f2-)
TG_ID=$(sqlite3 "$DB" "SELECT COALESCE(telegram_chat_id,'') FROM dashboard_users WHERE id=${DUID};")
echo "=== $(date -u) kick dominik_rappers START (tg_id='${TG_ID}') ===" >> "$LOG"

# --- Laufzeit-Check: hat der Kunde nach der Kuendigung neu gekauft? ---
G_SQL="FROM webhook_logs WHERE lower(payload) LIKE '%${EMAIL}%' AND json_extract(payload,'\$.access.access_type')='GRANT' AND CAST(json_extract(payload,'\$.product.product_id') AS TEXT) IN ('517561','517562') AND COALESCE(json_extract(payload,'\$.access.access_valid_until'),'') > '${VALID_UNTIL}'"
REGRANT=$(sqlite3 "$DB" "SELECT COUNT(*) ${G_SQL};")
G_MAXUNTIL=$(sqlite3 "$DB" "SELECT COALESCE(MAX(json_extract(payload,'\$.access.access_valid_until')),'') ${G_SQL};")
echo "Re-GRANT-Check (valid_until > ${VALID_UNTIL}): ${REGRANT} (max ${G_MAXUNTIL})" >> "$LOG"
if [ "$REGRANT" != "0" ]; then
  echo "ABBRUCH: neuerer GRANT gefunden -> KEIN Ban, nur Admin-Alert" >> "$LOG"
  [ -n "$ADMIN" ] && curl -s "https://api.telegram.org/bot${TOKEN}/sendMessage" -d chat_id="$ADMIN" --data-urlencode text="[KICK ABGEBROCHEN] ${EMAIL} (Dominik Rappers / 'Domi .', id ${DUID}) sollte heute gekickt werden - laut Ablefy hat er aber WIEDER GEZAHLT (Zugang gueltig bis ${G_MAXUNTIL}). Kein Ban ausgefuehrt, Zugang bleibt. Falls er spaeter doch raus soll: neuen Kick-Termin setzen." >> "$LOG" 2>&1
  echo "=== $(date -u) kick dominik_rappers ABORTED (re-grant) ===" >> "$LOG"
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
  curl -s "https://api.telegram.org/bot${TOKEN}/sendMessage" -d chat_id="$ADMIN" --data-urlencode text="[KICK] ${EMAIL} / Dominik Rappers (id ${DUID}) Abo abgelaufen 16.10.2026 - Auto-Kick nicht sicher bestaetigt. Bitte MANUELL aus Paid-Gruppe/Scalp entfernen. Telegram: 'Domi .' (ID 241330065)." >> "$LOG" 2>&1
  echo "ADMIN-ALERT gesendet" >> "$LOG"
fi
echo "=== $(date -u) kick dominik_rappers DONE ===" >> "$LOG"
