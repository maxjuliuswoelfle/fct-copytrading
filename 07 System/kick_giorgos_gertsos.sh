#!/usr/bin/env bash
# One-shot Kick fuer Giorgos Gertsos / gertsos.giorgos@gmail.com, dashboard_users id 327.
# Telegram: "Giogio" (@Gkertso), user-id 8185391400 — per getChatMember verifiziert,
# member in Main UND Scalp (Stand 2026-09-11). ID aus Support-Bot-Header [ID: 8185391400].
# Ablefy: order.subscription.canceled + payer.access.changed am 2026-09-11 11:53,
# access_valid_until 2026-09-18T00:00:00Z. Order 16856235, Produkt 517561,
# Monatsabo 96,45 EUR (Karte), Zahlung 18.08.2026.
# Reiner Signal-Kunde — KEINE API-Keys (Laenge 0), 0 Positions-Mappings, kein Copy-Trading-Risiko.
# Ansage Max: am 18.09.2026 kicken.
#
# LAUFZEIT-CHECK: Neuerer GRANT fuer UNSER Produkt (517561/517562) mit spaeterem
# access_valid_until als dem bekannten Laufzeitende -> KEIN Ban, nur Admin-Alert.
# (Nicht nach Zeitstempel filtern — das Kuendigungs-Event traegt selbst access_type=GRANT.)
# Siehe Projekt-CLAUDE.md (Copy Trading Bot).
set -o pipefail
BOTDIR=/home/botuser/copy-trading-bot
LOG=/home/botuser/scripts/kick_giorgos_gertsos.log
ENVF="$BOTDIR/.env"
DB="$BOTDIR/copy_trading.db"
DUID=327
EMAIL="gertsos.giorgos@gmail.com"
INVITE="https://telegram.me/+s0ZrCYcJjik0ODY6"
CUST="7954931f-9fa7-4d1a-bebf-6d67f71e531b"
VALID_UNTIL="2026-09-18T00:00:00Z"
TOKEN=$(grep -E "^TELEGRAM_BOT_TOKEN=" "$ENVF" | head -1 | cut -d= -f2-)
MAIN=$(grep -E "^SIGNAL_PAID_GROUP_ID=" "$ENVF" | head -1 | cut -d= -f2-)
SCALP=$(grep -E "^SIGNAL_SCALP_GROUP_ID=" "$ENVF" | head -1 | cut -d= -f2-)
ADMIN=$(grep -E "^TELEGRAM_CHAT_ID=" "$ENVF" | head -1 | cut -d= -f2-)
TG_ID=$(sqlite3 "$DB" "SELECT COALESCE(telegram_chat_id,'') FROM dashboard_users WHERE id=${DUID};")
echo "=== $(date -u) kick giorgos_gertsos START (tg_id='${TG_ID}') ===" >> "$LOG"

# --- Laufzeit-Check: hat der Kunde nach der Kuendigung neu gekauft? ---
REGRANT=$(sqlite3 "$DB" "SELECT COUNT(*) FROM webhook_logs WHERE lower(payload) LIKE '%${EMAIL}%' AND json_extract(payload,'\$.access.access_type')='GRANT' AND CAST(json_extract(payload,'\$.product.product_id') AS TEXT) IN ('517561','517562') AND COALESCE(json_extract(payload,'\$.access.access_valid_until'),'') > '${VALID_UNTIL}';")
echo "Re-GRANT-Check (valid_until > ${VALID_UNTIL}): ${REGRANT}" >> "$LOG"
if [ "$REGRANT" != "0" ]; then
  echo "ABBRUCH: neuerer GRANT gefunden -> KEIN Ban, nur Admin-Alert" >> "$LOG"
  [ -n "$ADMIN" ] && curl -s "https://api.telegram.org/bot${TOKEN}/sendMessage" -d chat_id="$ADMIN" -d text="[KICK ABGEBROCHEN] ${EMAIL} (id ${DUID}, Giogio/@Gkertso) sollte heute gekickt werden — es liegt aber ein NEUERER Ablefy-GRANT vor (Neukauf). Kein Ban ausgefuehrt, Zugang bleibt. Bitte pruefen." >> "$LOG" 2>&1
  echo "=== $(date -u) kick giorgos_gertsos ABORTED (re-grant) ===" >> "$LOG"
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
  curl -s "https://api.telegram.org/bot${TOKEN}/sendMessage" -d chat_id="$ADMIN" -d text="[KICK] ${EMAIL} / Giorgos Gertsos (id ${DUID}) Abo abgelaufen 18.09.2026 — Auto-Kick nicht sicher bestaetigt. Bitte MANUELL aus Paid-Gruppe/Scalp entfernen. Telegram: Giogio (@Gkertso, ID 8185391400)." >> "$LOG" 2>&1
  echo "ADMIN-ALERT gesendet" >> "$LOG"
fi
echo "=== $(date -u) kick giorgos_gertsos DONE ===" >> "$LOG"
