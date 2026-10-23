#!/usr/bin/env bash
# One-shot Kick fuer Pawel Brendler, dashboard_users id 465.
# Telegram: "Pawel Brendler", user-id 5978389053 — per getChatMember verifiziert,
# member in Main UND Scalp (Stand 2026-09-10). Kuendigung 2026-09-10 via Support-Bot
# ("Hi, ich moechte mein Abo nicht verlaengern. Muss ich etwas machen?", Header [ID: 5978389053]).
# ⚠️ MAIL-ABWEICHUNG: Im Support nannte er brendler.pawel@gmail.com,
# in der DB steht brendler.pawel@googlemail.com (gleiche Google-Mailbox, anderer String).
# Gefunden wurde er ueber telegram_chat_id, NICHT ueber die Mail.
# Ablefy: order.subscription.canceled + payer.access.changed am 2026-09-10 14:22,
# access_valid_until 2026-09-28T00:00:00Z. Order 16928258, Produkt 517561,
# Monatsabo (Plan 610907, 99,95 EUR Listenpreis, gezahlt 96,45 EUR, Karte),
# Kauf + Zahlung 28.08.2026 -> Kuendigung nach 13 Tagen.
# Reiner Signal-Kunde — KEINE API-Keys (Laenge 0), 0 Positions-Mappings, kein Copy-Trading-Risiko.
# Ansage Max: am 28.09.2026 kicken.
#
# LAUFZEIT-CHECK auf zwischenzeitlichen Neukauf (Lehre aus Fall Lihua Zoustahr, 2026-09-09):
# Findet sich ein GRANT mit SPAETEREM access_valid_until als dem bekannten Laufzeitende,
# wird NICHT gebannt, sondern nur ein Admin-Alert geschickt.
# ⚠️ NICHT nach Zeitstempel filtern — das Kuendigungs-Event traegt selbst access_type=GRANT
# (Zugang bis Laufzeitende) und wuerde jeden Kick faelschlich abbrechen.
# Siehe Projekt-CLAUDE.md (Copy Trading Bot).
set -o pipefail
BOTDIR=/home/botuser/copy-trading-bot
LOG=/home/botuser/scripts/kick_pawel_brendler.log
ENVF="$BOTDIR/.env"
DB="$BOTDIR/copy_trading.db"
DUID=465
EMAIL="brendler.pawel@googlemail.com"
INVITE="https://telegram.me/+SBaibhSdx_1mYWZi"
CUST="8b9029ec-9f36-49de-a6c1-c591f29027ed"
VALID_UNTIL="2026-09-28T00:00:00Z"
TOKEN=$(grep -E "^TELEGRAM_BOT_TOKEN=" "$ENVF" | head -1 | cut -d= -f2-)
MAIN=$(grep -E "^SIGNAL_PAID_GROUP_ID=" "$ENVF" | head -1 | cut -d= -f2-)
SCALP=$(grep -E "^SIGNAL_SCALP_GROUP_ID=" "$ENVF" | head -1 | cut -d= -f2-)
ADMIN=$(grep -E "^TELEGRAM_CHAT_ID=" "$ENVF" | head -1 | cut -d= -f2-)
TG_ID=$(sqlite3 "$DB" "SELECT COALESCE(telegram_chat_id,'') FROM dashboard_users WHERE id=${DUID};")
echo "=== $(date -u) kick pawel_brendler START (tg_id='${TG_ID}') ===" >> "$LOG"

# --- Laufzeit-Check: hat der Kunde nach der Kuendigung neu gekauft? ---
REGRANT=$(sqlite3 "$DB" "SELECT COUNT(*) FROM webhook_logs WHERE payload LIKE '%brendler.pawel%' AND json_extract(payload,'\$.access.access_type')='GRANT' AND CAST(json_extract(payload,'\$.product.product_id') AS TEXT) IN ('517561','517562') AND COALESCE(json_extract(payload,'\$.access.access_valid_until'),'') > '${VALID_UNTIL}';")
echo "Re-GRANT-Check (valid_until > ${VALID_UNTIL}): ${REGRANT}" >> "$LOG"
if [ "$REGRANT" != "0" ]; then
  echo "ABBRUCH: neuerer GRANT gefunden -> KEIN Ban, nur Admin-Alert" >> "$LOG"
  [ -n "$ADMIN" ] && curl -s "https://api.telegram.org/bot${TOKEN}/sendMessage" -d chat_id="$ADMIN" -d text="[KICK ABGEBROCHEN] Pawel Brendler (id ${DUID}, ${EMAIL}) sollte heute gekickt werden — es liegt aber ein NEUERER Ablefy-GRANT vor (Neukauf). Kein Ban ausgefuehrt, Zugang bleibt. Bitte pruefen." >> "$LOG" 2>&1
  echo "=== $(date -u) kick pawel_brendler ABORTED (re-grant) ===" >> "$LOG"
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
  curl -s "https://api.telegram.org/bot${TOKEN}/sendMessage" -d chat_id="$ADMIN" -d text="[KICK] ${EMAIL} / Pawel Brendler (id ${DUID}) Abo abgelaufen 28.09.2026 — Auto-Kick nicht sicher bestaetigt. Bitte MANUELL aus Paid-Gruppe/Scalp entfernen. Telegram: Pawel Brendler, ID 5978389053." >> "$LOG" 2>&1
  echo "ADMIN-ALERT gesendet" >> "$LOG"
fi
echo "=== $(date -u) kick pawel_brendler DONE ===" >> "$LOG"
