#!/usr/bin/env bash
# One-shot Kick fuer Gunnar Still / gunnars.nachrichtenzentrale@gmail.com, dashboard_users id 469.
# Telegram "Gunnar" / @GUNNAR_Trinkwasserbotschafter, ID 869123332.
# Gemeldet 2026-09-24 via Support-Bot (Header [ID: 869123332]). Ansage Max: am 30.09.2026 kicken.
#
# Kuendigungsgrund (O-Ton): "hat sich nicht gelohnt" — er folge Max ohnehin im Stream und habe
#    KEINEN EINZIGEN Trade aus dem Copy Trading gemacht. Bittet um Kuendigungsbestaetigung.
#    => Produktsignal (zweiter Fall nach Michael Grossmann am selben Tag: bezahlter Kanal
#       liefert aus Kundensicht zu wenig Mehrwert gegenueber dem oeffentlichen Content).
#
# Ablefy: order.subscription.canceled + payer.access.changed GRANT (subscription_canceled)
#    am 2026-09-24 09:59 UTC, access_valid_until 2026-09-30T00:00:00Z (= Max' Datum,
#    kein offener Ablefy-Punkt).
# Order 16950016, Produkt 517561, Monatsabo 96,45 EUR (Karte), Kauf + einzige Zahlung
#    31.08.2026 -> Kuendigung nach 24 Tagen.
# Reiner Signal-Kunde — KEINE API-Keys (Laenge 0), 0 Positions-Mappings, nicht auf der Blocklist.
# Telegram-ID war via Auto-Capture in der DB und per getChatMember verifiziert:
#    member in BEIDEN (Main + Scalp).
#
# LAUFZEIT-CHECK auf zwischenzeitlichen Neukauf, inkl. PRODUKT-FILTER (nur 517561/517562).
# Produkt-ID wird aus BEIDEN Payload-Varianten gelesen ($.product.id und $.product.product_id).
# NICHT nach Zeitstempel filtern: das Kuendigungs-Event traegt selbst access_type=GRANT.
set -o pipefail
BOTDIR=/home/botuser/copy-trading-bot
LOG=/home/botuser/scripts/kick_gunnar_still.log
ENVF="$BOTDIR/.env"
DB="$BOTDIR/copy_trading.db"
DUID=469
EMAIL="gunnars.nachrichtenzentrale@gmail.com"
INVITE="https://telegram.me/+KBslWtYv99c0M2I6"
CUST="1082567d-84ed-474f-9ba4-7af284142ccf"
VALID_UNTIL="2026-09-30T00:00:00Z"
TOKEN=$(grep -E "^TELEGRAM_BOT_TOKEN=" "$ENVF" | head -1 | cut -d= -f2-)
MAIN=$(grep -E "^SIGNAL_PAID_GROUP_ID=" "$ENVF" | head -1 | cut -d= -f2-)
SCALP=$(grep -E "^SIGNAL_SCALP_GROUP_ID=" "$ENVF" | head -1 | cut -d= -f2-)
ADMIN=$(grep -E "^TELEGRAM_CHAT_ID=" "$ENVF" | head -1 | cut -d= -f2-)
TG_ID=$(sqlite3 "$DB" "SELECT COALESCE(telegram_chat_id,'') FROM dashboard_users WHERE id=${DUID};")
echo "=== $(date -u) kick gunnar_still START (tg_id='${TG_ID}') ===" >> "$LOG"

# --- Laufzeit-Check: hat der Kunde nach der Kuendigung neu gekauft? ---
G_SQL="FROM webhook_logs WHERE lower(payload) LIKE '%${EMAIL}%' AND json_extract(payload,'\$.access.access_type')='GRANT' AND COALESCE(CAST(json_extract(payload,'\$.product.id') AS TEXT), CAST(json_extract(payload,'\$.product.product_id') AS TEXT),'') IN ('517561','517562') AND COALESCE(json_extract(payload,'\$.access.access_valid_until'),'') > '${VALID_UNTIL}'"
REGRANT=$(sqlite3 "$DB" "SELECT COUNT(*) ${G_SQL};")
G_MAXUNTIL=$(sqlite3 "$DB" "SELECT COALESCE(MAX(json_extract(payload,'\$.access.access_valid_until')),'') ${G_SQL};")
echo "Re-GRANT-Check (valid_until > ${VALID_UNTIL}): ${REGRANT} (max ${G_MAXUNTIL})" >> "$LOG"
if [ "$REGRANT" != "0" ]; then
  echo "ABBRUCH: neuerer GRANT gefunden -> KEIN Ban, nur Admin-Alert" >> "$LOG"
  [ -n "$ADMIN" ] && curl -s "https://api.telegram.org/bot${TOKEN}/sendMessage" -d chat_id="$ADMIN" --data-urlencode text="[KICK ABGEBROCHEN] ${EMAIL} (Gunnar Still, id ${DUID}) sollte heute gekickt werden - laut Ablefy hat er aber WIEDER GEZAHLT (Zugang gueltig bis ${G_MAXUNTIL}). Kein Ban ausgefuehrt, Zugang bleibt." >> "$LOG" 2>&1
  echo "=== $(date -u) kick gunnar_still ABORTED (re-grant) ===" >> "$LOG"
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
  curl -s "https://api.telegram.org/bot${TOKEN}/sendMessage" -d chat_id="$ADMIN" --data-urlencode text="[KICK] ${EMAIL} / Gunnar Still (id ${DUID}) Abo abgelaufen 30.09.2026 - Auto-Kick nicht sicher bestaetigt. Bitte MANUELL aus Paid-Gruppe/Scalp entfernen. Telegram: Gunnar (@GUNNAR_Trinkwasserbotschafter, ID 869123332)." >> "$LOG" 2>&1
  echo "ADMIN-ALERT gesendet" >> "$LOG"
fi
echo "=== $(date -u) kick gunnar_still DONE ===" >> "$LOG"
