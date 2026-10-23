#!/usr/bin/env bash
# One-shot Kick fuer Matthias Kocemba / matthias.kocemba@gmail.com, dashboard_users id 468.
# Telegram: "Maciek" (@skynet_one), user-id 454434454 — per getChatMember verifiziert,
# member in Main UND Scalp (Stand 2026-09-10). Kunde hat seine Kundennummer selbst via
# Support-Bot geschickt ([ID: 454434454]) -> Identitaet eindeutig.
# Ablefy: order.subscription.canceled + payer.access.changed am 2026-09-10 14:09,
# access_valid_until 2026-10-02T00:00:00Z. Order 16937707, Produkt 517561,
# Monatsabo 96,45 EUR, Kauf 29.08.2026 (SEPA), erste Zahlung 02.09.2026.
# Reiner Signal-Kunde — KEINE API-Keys (Laenge 0), 0 Positions-Mappings, kein Copy-Trading-Risiko.
# Ansage Max: am 02.10.2026 kicken.
#
# NEU ggue. frueheren Kick-Scripts: LAUFZEIT-CHECK auf einen zwischenzeitlichen Neukauf.
# Findet sich nach dem Kuendigungs-Event ein neueres payer.access.changed mit
# "access_type": "GRANT", wird NICHT gebannt, sondern nur ein Admin-Alert geschickt.
# (Lehre aus dem Fall Lihua Zoustahr, 2026-09-09: Timer feuerte blind und bannte
# eine Kundin, die 6 Tage nach der Kuendigung neu gekauft hatte.)
# Siehe Projekt-CLAUDE.md (Copy Trading Bot).
set -o pipefail
BOTDIR=/home/botuser/copy-trading-bot
LOG=/home/botuser/scripts/kick_matthias_kocemba.log
ENVF="$BOTDIR/.env"
DB="$BOTDIR/copy_trading.db"
DUID=468
EMAIL="matthias.kocemba@gmail.com"
INVITE="https://telegram.me/+GSYVnZhJR3UwZjEy"
CUST="fead5058-ca43-4e8e-953a-9ecb3b40e104"
VALID_UNTIL="2026-10-02T00:00:00Z"
TOKEN=$(grep -E "^TELEGRAM_BOT_TOKEN=" "$ENVF" | head -1 | cut -d= -f2-)
MAIN=$(grep -E "^SIGNAL_PAID_GROUP_ID=" "$ENVF" | head -1 | cut -d= -f2-)
SCALP=$(grep -E "^SIGNAL_SCALP_GROUP_ID=" "$ENVF" | head -1 | cut -d= -f2-)
ADMIN=$(grep -E "^TELEGRAM_CHAT_ID=" "$ENVF" | head -1 | cut -d= -f2-)
TG_ID=$(sqlite3 "$DB" "SELECT COALESCE(telegram_chat_id,'') FROM dashboard_users WHERE id=${DUID};")
echo "=== $(date -u) kick matthias_kocemba START (tg_id='${TG_ID}') ===" >> "$LOG"

# --- Laufzeit-Check: hat der Kunde nach der Kuendigung neu gekauft? ---
# WICHTIG: Das Kuendigungs-Event selbst traegt ebenfalls access_type=GRANT
# (Zugang laeuft bis Laufzeitende). Deshalb NICHT nach Zeitstempel filtern, sondern
# nach einem SPAETEREN Gueltigkeitsdatum als dem bekannten Laufzeitende.
REGRANT=$(sqlite3 "$DB" "SELECT COUNT(*) FROM webhook_logs WHERE payload LIKE '%${EMAIL}%' AND json_extract(payload,'\$.access.access_type')='GRANT' AND CAST(json_extract(payload,'\$.product.product_id') AS TEXT) IN ('517561','517562') AND COALESCE(json_extract(payload,'\$.access.access_valid_until'),'') > '${VALID_UNTIL}';")
echo "Re-GRANT-Check (valid_until > ${VALID_UNTIL}): ${REGRANT}" >> "$LOG"
if [ "$REGRANT" != "0" ]; then
  echo "ABBRUCH: neuerer GRANT gefunden -> KEIN Ban, nur Admin-Alert" >> "$LOG"
  [ -n "$ADMIN" ] && curl -s "https://api.telegram.org/bot${TOKEN}/sendMessage" -d chat_id="$ADMIN" -d text="[KICK ABGEBROCHEN] ${EMAIL} (id ${DUID}, Maciek/@skynet_one) sollte heute gekickt werden — es liegt aber ein NEUERER Ablefy-GRANT vor (Neukauf). Kein Ban ausgefuehrt, Zugang bleibt. Bitte pruefen." >> "$LOG" 2>&1
  echo "=== $(date -u) kick matthias_kocemba ABORTED (re-grant) ===" >> "$LOG"
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
  curl -s "https://api.telegram.org/bot${TOKEN}/sendMessage" -d chat_id="$ADMIN" -d text="[KICK] ${EMAIL} / Matthias Kocemba (id ${DUID}) Abo abgelaufen 02.10.2026 — Auto-Kick nicht sicher bestaetigt. Bitte MANUELL aus Paid-Gruppe/Scalp entfernen. Telegram: Maciek (@skynet_one, ID 454434454)." >> "$LOG" 2>&1
  echo "ADMIN-ALERT gesendet" >> "$LOG"
fi
echo "=== $(date -u) kick matthias_kocemba DONE ===" >> "$LOG"
