#!/usr/bin/env bash
# One-shot Kick fuer Markus Nass / markus.nass@web.de, dashboard_users id 474.
# Gemeldet 2026-09-21 via Support-Bot (Header [ID: 7961858897], "Gern dann bitte kuendigen").
# Ansage Max: zum 02.10.2026 kicken.
#
# ⚠️ DREI "Markus" im System — NICHT verwechseln:
#      Markus NASS      (dieser hier, Kick 02.10.2026)
#      Markus MAYER     (kh.markus@proton.me, Kick 07.10.2026)
#      Markus ASCHENBRENNER (Kick 01.07.2027)
# Hinweis: Am 02.10. feuert zusaetzlich kick-matthias-kocemba.timer — separate Timer, kein Konflikt.
#
# Telegram: "Markus Nass", user-id 7961858897 — per getChatMember verifiziert (2026-09-21):
#    LEFT in BEIDEN Kanaelen, er ist also bereits selbst ausgetreten. Der Ban wirkt hier als
#    Rueckkehr-Sperre; der eigentliche Effekt sind Invite-Revoke + DB-Aufraeumen.
#    ID war via Auto-Capture bereits in der DB.
# Ablefy: order.subscription.canceled + payer.access.changed am 2026-09-21 13:40,
#    access_valid_until 2026-10-02T00:00:00Z (= Max' Datum, kein offener Ablefy-Punkt).
# Order 16968907, Produkt 517561, Monatsabo 96,45 EUR (Karte), Kauf + einzige Zahlung 02.09.2026
#    -> Kuendigung nach 19 Tagen.
# Reiner Signal-Kunde — KEINE API-Keys (Laenge 0), 0 Positions-Mappings, kein Copy-Trading-Risiko.
#
# LAUFZEIT-CHECK auf zwischenzeitlichen Neukauf (Lehre Lihua/Timo), inkl. PRODUKT-FILTER:
# nur unsere Produkte 517561/517562 zaehlen. NICHT nach Zeitstempel filtern: das Kuendigungs-Event
# traegt selbst access_type=GRANT. Siehe Projekt-CLAUDE.md (Copy Trading Bot).
set -o pipefail
BOTDIR=/home/botuser/copy-trading-bot
LOG=/home/botuser/scripts/kick_markus_nass.log
ENVF="$BOTDIR/.env"
DB="$BOTDIR/copy_trading.db"
DUID=474
EMAIL="markus.nass@web.de"
INVITE="https://telegram.me/+N0aTyMbJzCEzZTBi"
CUST="94150d80-3b56-420a-acd3-4f806579eb5a"
VALID_UNTIL="2026-10-02T00:00:00Z"
TOKEN=$(grep -E "^TELEGRAM_BOT_TOKEN=" "$ENVF" | head -1 | cut -d= -f2-)
MAIN=$(grep -E "^SIGNAL_PAID_GROUP_ID=" "$ENVF" | head -1 | cut -d= -f2-)
SCALP=$(grep -E "^SIGNAL_SCALP_GROUP_ID=" "$ENVF" | head -1 | cut -d= -f2-)
ADMIN=$(grep -E "^TELEGRAM_CHAT_ID=" "$ENVF" | head -1 | cut -d= -f2-)
TG_ID=$(sqlite3 "$DB" "SELECT COALESCE(telegram_chat_id,'') FROM dashboard_users WHERE id=${DUID};")
echo "=== $(date -u) kick markus_nass START (tg_id='${TG_ID}') ===" >> "$LOG"

# --- Laufzeit-Check: hat der Kunde nach der Kuendigung neu gekauft? ---
G_SQL="FROM webhook_logs WHERE lower(payload) LIKE '%${EMAIL}%' AND json_extract(payload,'\$.access.access_type')='GRANT' AND CAST(json_extract(payload,'\$.product.product_id') AS TEXT) IN ('517561','517562') AND COALESCE(json_extract(payload,'\$.access.access_valid_until'),'') > '${VALID_UNTIL}'"
REGRANT=$(sqlite3 "$DB" "SELECT COUNT(*) ${G_SQL};")
G_MAXUNTIL=$(sqlite3 "$DB" "SELECT COALESCE(MAX(json_extract(payload,'\$.access.access_valid_until')),'') ${G_SQL};")
echo "Re-GRANT-Check (valid_until > ${VALID_UNTIL}): ${REGRANT} (max ${G_MAXUNTIL})" >> "$LOG"
if [ "$REGRANT" != "0" ]; then
  echo "ABBRUCH: neuerer GRANT gefunden -> KEIN Ban, nur Admin-Alert" >> "$LOG"
  [ -n "$ADMIN" ] && curl -s "https://api.telegram.org/bot${TOKEN}/sendMessage" -d chat_id="$ADMIN" --data-urlencode text="[KICK ABGEBROCHEN] ${EMAIL} (Markus Nass, id ${DUID}) sollte heute gekickt werden - laut Ablefy hat er aber WIEDER GEZAHLT (Zugang gueltig bis ${G_MAXUNTIL}). Kein Ban ausgefuehrt, Zugang bleibt. Falls er spaeter doch raus soll: neuen Kick-Termin setzen." >> "$LOG" 2>&1
  echo "=== $(date -u) kick markus_nass ABORTED (re-grant) ===" >> "$LOG"
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
  curl -s "https://api.telegram.org/bot${TOKEN}/sendMessage" -d chat_id="$ADMIN" --data-urlencode text="[KICK] ${EMAIL} / Markus Nass (id ${DUID}) Abo abgelaufen 02.10.2026 - Auto-Kick nicht sicher bestaetigt. Bitte MANUELL pruefen. Telegram-ID 7961858897 (war am 21.09. bereits 'left' in beiden Kanaelen)." >> "$LOG" 2>&1
  echo "ADMIN-ALERT gesendet" >> "$LOG"
fi
echo "=== $(date -u) kick markus_nass DONE ===" >> "$LOG"
