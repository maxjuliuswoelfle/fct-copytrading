#!/usr/bin/env bash
# One-shot Kick fuer "M." / markus2aschenbrenner@gmail.com, dashboard_users id 301.
# Kuendigung des JAHRESABOS gemeldet 2026-08-21 via Support-Bot. Ansage Max: am 01.07.2027 entfernen.
# Order 16544298, Jahresabo 74,94 EUR/Monat (12 Monate gebunden), Kauf 01.07.2026,
# letzte Zahlung 02.08.2026 -> Laufzeitende 01.07.2027.
# Telegram-ID 7755452504, bei Erfassung member in Main UND Scalp.
# Reiner Signal-Kunde (keine API-Keys, 0 Mappings). Siehe Projekt-CLAUDE.md (Copy Trading Bot).
set -o pipefail
BOTDIR=/home/botuser/copy-trading-bot
LOG=/home/botuser/scripts/kick_markus_aschenbrenner.log
ENVF="$BOTDIR/.env"
DB="$BOTDIR/copy_trading.db"
TG_ID=7755452504
INVITE="https://telegram.me/+S4Uj8nra001kMTgy"
CUST="f16fcbac-3346-4c9a-9a93-330f8e4c1e46"
TOKEN=$(grep -E "^TELEGRAM_BOT_TOKEN=" "$ENVF" | head -1 | cut -d= -f2-)
MAIN=$(grep -E "^SIGNAL_PAID_GROUP_ID=" "$ENVF" | head -1 | cut -d= -f2-)
SCALP=$(grep -E "^SIGNAL_SCALP_GROUP_ID=" "$ENVF" | head -1 | cut -d= -f2-)
ADMIN=$(grep -E "^TELEGRAM_CHAT_ID=" "$ENVF" | head -1 | cut -d= -f2-)
echo "=== $(date -u) kick markus_aschenbrenner START ===" >> "$LOG"

# --- Laufzeit-Check (nachgeruestet 2026-09-11, Lehre Lihua/Timo): hat der Kunde wieder gezahlt? ---
# Liegt fuer unser Produkt ein Ablefy-GRANT mit SPAETEREM access_valid_until als dem
# Laufzeitende vor -> KEIN Ban, nur Admin-Alert.
# NICHT nach Zeitstempel filtern: das Kuendigungs-Event traegt selbst access_type=GRANT.
G_EMAIL="markus2aschenbrenner@gmail.com"
G_UNTIL="2027-07-01T00:00:00Z"
G_SQL="FROM webhook_logs WHERE lower(payload) LIKE '%${G_EMAIL}%' AND json_extract(payload,'\$.access.access_type')='GRANT' AND CAST(json_extract(payload,'\$.product.product_id') AS TEXT) IN ('517561','517562') AND COALESCE(json_extract(payload,'\$.access.access_valid_until'),'') > '${G_UNTIL}'"
REGRANT=$(sqlite3 "$DB" "SELECT COUNT(*) ${G_SQL};")
G_MAXUNTIL=$(sqlite3 "$DB" "SELECT COALESCE(MAX(json_extract(payload,'\$.access.access_valid_until')),'') ${G_SQL};")
echo "Re-GRANT-Check (valid_until > ${G_UNTIL}): ${REGRANT} (max ${G_MAXUNTIL})" >> "$LOG"
if [ "$REGRANT" != "0" ]; then
  echo "ABBRUCH: neuerer GRANT gefunden -> KEIN Ban, nur Admin-Alert" >> "$LOG"
  [ -n "$ADMIN" ] && curl -s "https://api.telegram.org/bot${TOKEN}/sendMessage" -d chat_id="$ADMIN" --data-urlencode text="[KICK ABGEBROCHEN] ${G_EMAIL} sollte heute gekickt werden - laut Ablefy hat der Kunde aber WIEDER GEZAHLT (Zugang gueltig bis ${G_MAXUNTIL}). Kein Ban ausgefuehrt, Zugang bleibt. Falls er spaeter doch raus soll: neuen Kick-Termin setzen." >> "$LOG" 2>&1
  echo "=== $(date -u) kick_markus_aschenbrenner ABORTED (re-grant) ===" >> "$LOG"
  exit 0
fi

OKALL=1
for CHAT in "$MAIN" "$SCALP"; do
  RESP=$(curl -s "https://api.telegram.org/bot${TOKEN}/banChatMember" -d chat_id="$CHAT" -d user_id="$TG_ID")
  echo "banChatMember $CHAT -> $RESP" >> "$LOG"
  echo "$RESP" | grep -q '"ok":true' || OKALL=0
done
RESP=$(curl -s "https://api.telegram.org/bot${TOKEN}/revokeChatInviteLink" -d chat_id="$MAIN" -d invite_link="$INVITE")
echo "revokeInviteLink -> $RESP" >> "$LOG"
sqlite3 "$DB" "UPDATE dashboard_users SET payment_status='cancelled' WHERE id=301; UPDATE customers SET is_active=0, deactivated_at=CURRENT_TIMESTAMP WHERE id='${CUST}';"
echo "DB: payment_status=cancelled, customer is_active=0" >> "$LOG"
if [ "$OKALL" != "1" ] && [ -n "$ADMIN" ]; then
  curl -s "https://api.telegram.org/bot${TOKEN}/sendMessage" -d chat_id="$ADMIN" -d text="[KICK] markus2aschenbrenner@gmail.com / M. (id 301): banChatMember nicht ueberall ok=true -> bitte manuell aus Paid-Gruppe/Scalp entfernen. Siehe kick_markus_aschenbrenner.log" >> "$LOG" 2>&1
  echo "ADMIN-ALERT gesendet (ban nicht ueberall ok)" >> "$LOG"
fi
echo "=== $(date -u) kick markus_aschenbrenner DONE ===" >> "$LOG"
