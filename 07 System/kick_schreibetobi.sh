#!/usr/bin/env bash
# One-shot Kick fuer "T. D." / schreibetobi@gmail.com, dashboard_users id 448.
# Kuendigung per Support-Bot am 2026-08-21 (bat um offizielle Bestaetigung, Kundennummer selbst genannt).
# Max hat in Ablefy gekuendigt. Kauf 17.08.2026 (Order 16851534, Monatsabo 96,45 EUR),
# Ablefy access_valid_until 2026-09-17T00:00:00Z. Ansage Max: am 17.09.2026 kicken.
# Telegram-ID 1508823657 (via Auto-Capture), bei Erfassung member in Main UND Scalp.
# Reiner Signal-Kunde (keine API-Keys). Siehe Projekt-CLAUDE.md (Copy Trading Bot).
set -o pipefail
BOTDIR=/home/botuser/copy-trading-bot
LOG=/home/botuser/scripts/kick_schreibetobi.log
ENVF="$BOTDIR/.env"
DB="$BOTDIR/copy_trading.db"
TG_ID=1508823657
INVITE="https://telegram.me/+7NyxsyovYLc0NGEy"
CUST="75536432-e1f4-46a2-877e-43319e6dc09e"
TOKEN=$(grep -E "^TELEGRAM_BOT_TOKEN=" "$ENVF" | head -1 | cut -d= -f2-)
MAIN=$(grep -E "^SIGNAL_PAID_GROUP_ID=" "$ENVF" | head -1 | cut -d= -f2-)
SCALP=$(grep -E "^SIGNAL_SCALP_GROUP_ID=" "$ENVF" | head -1 | cut -d= -f2-)
ADMIN=$(grep -E "^TELEGRAM_CHAT_ID=" "$ENVF" | head -1 | cut -d= -f2-)
echo "=== $(date -u) kick schreibetobi START ===" >> "$LOG"

# --- Laufzeit-Check (nachgeruestet 2026-09-11, Lehre Lihua/Timo): hat der Kunde wieder gezahlt? ---
# Liegt fuer unser Produkt ein Ablefy-GRANT mit SPAETEREM access_valid_until als dem
# Laufzeitende vor -> KEIN Ban, nur Admin-Alert.
# NICHT nach Zeitstempel filtern: das Kuendigungs-Event traegt selbst access_type=GRANT.
G_EMAIL="schreibetobi@gmail.com"
G_UNTIL="2026-09-17T00:00:00Z"
G_SQL="FROM webhook_logs WHERE lower(payload) LIKE '%${G_EMAIL}%' AND json_extract(payload,'\$.access.access_type')='GRANT' AND CAST(json_extract(payload,'\$.product.product_id') AS TEXT) IN ('517561','517562') AND COALESCE(json_extract(payload,'\$.access.access_valid_until'),'') > '${G_UNTIL}'"
REGRANT=$(sqlite3 "$DB" "SELECT COUNT(*) ${G_SQL};")
G_MAXUNTIL=$(sqlite3 "$DB" "SELECT COALESCE(MAX(json_extract(payload,'\$.access.access_valid_until')),'') ${G_SQL};")
echo "Re-GRANT-Check (valid_until > ${G_UNTIL}): ${REGRANT} (max ${G_MAXUNTIL})" >> "$LOG"
if [ "$REGRANT" != "0" ]; then
  echo "ABBRUCH: neuerer GRANT gefunden -> KEIN Ban, nur Admin-Alert" >> "$LOG"
  [ -n "$ADMIN" ] && curl -s "https://api.telegram.org/bot${TOKEN}/sendMessage" -d chat_id="$ADMIN" --data-urlencode text="[KICK ABGEBROCHEN] ${G_EMAIL} sollte heute gekickt werden - laut Ablefy hat der Kunde aber WIEDER GEZAHLT (Zugang gueltig bis ${G_MAXUNTIL}). Kein Ban ausgefuehrt, Zugang bleibt. Falls er spaeter doch raus soll: neuen Kick-Termin setzen." >> "$LOG" 2>&1
  echo "=== $(date -u) kick_schreibetobi ABORTED (re-grant) ===" >> "$LOG"
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
sqlite3 "$DB" "UPDATE dashboard_users SET payment_status='cancelled' WHERE id=448; UPDATE customers SET is_active=0, deactivated_at=CURRENT_TIMESTAMP WHERE id='${CUST}';"
echo "DB: payment_status=cancelled, customer is_active=0" >> "$LOG"
if [ "$OKALL" != "1" ] && [ -n "$ADMIN" ]; then
  curl -s "https://api.telegram.org/bot${TOKEN}/sendMessage" -d chat_id="$ADMIN" -d text="[KICK] schreibetobi@gmail.com / T. D. (id 448): banChatMember nicht ueberall ok=true -> bitte manuell aus Paid-Gruppe/Scalp entfernen. Siehe kick_schreibetobi.log" >> "$LOG" 2>&1
  echo "ADMIN-ALERT gesendet (ban nicht ueberall ok)" >> "$LOG"
fi
echo "=== $(date -u) kick schreibetobi DONE ===" >> "$LOG"
