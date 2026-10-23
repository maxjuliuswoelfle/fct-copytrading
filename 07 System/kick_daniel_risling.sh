#!/usr/bin/env bash
# One-shot Kick fuer Daniel Risling / d.risling@live.de, dashboard_users id 477.
# Kuendigung gemeldet 2026-09-04 (Kundennummer fe5eb242-... von Max genannt).
# Kauf 03.09.2026 15:04 (Order 16976341, Produkt 517561, Monatsabo), Ablefy
# access_valid_until 2026-10-03T00:00:00Z. Ansage Max: am 03.10.2026 kicken.
# Reiner Signal-Kunde — KEINE API-Keys (Laenge 0), 0 Positions-Mappings, kein Copy-Trading-Risiko.
# Telegram-user-id 8601828159 war via chat_member-Auto-Capture bereits in der DB und wurde per
# getChatMember verifiziert (loest auf "Daniel Risling" — member in Main UND Scalp).
# ⚠️ OFFEN zum Zeitpunkt des Baus: In webhook_logs lag noch KEIN order.subscription.canceled —
# Max muss die Kuendigung in Ablefy ausloesen, sonst zieht am 03.10. die naechste Rate.
# Das Script liest telegram_chat_id zur LAUFZEIT: vorhanden -> Ban in Main + Scalp,
# leer -> Admin-Alert an Max ("manuell entfernen"). DB-Updates + Invite-Revoke laufen in beiden Faellen.
# Siehe Projekt-CLAUDE.md (Copy Trading Bot).
set -o pipefail
BOTDIR=/home/botuser/copy-trading-bot
LOG=/home/botuser/scripts/kick_daniel_risling.log
ENVF="$BOTDIR/.env"
DB="$BOTDIR/copy_trading.db"
DUID=477
INVITE="https://telegram.me/+ijINmGvjMpcxMWQ6"
CUST="fe5eb242-45b0-4e2d-b7bf-aaed2a95ee4d"
TOKEN=$(grep -E "^TELEGRAM_BOT_TOKEN=" "$ENVF" | head -1 | cut -d= -f2-)
MAIN=$(grep -E "^SIGNAL_PAID_GROUP_ID=" "$ENVF" | head -1 | cut -d= -f2-)
SCALP=$(grep -E "^SIGNAL_SCALP_GROUP_ID=" "$ENVF" | head -1 | cut -d= -f2-)
ADMIN=$(grep -E "^TELEGRAM_CHAT_ID=" "$ENVF" | head -1 | cut -d= -f2-)
TG_ID=$(sqlite3 "$DB" "SELECT COALESCE(telegram_chat_id,'') FROM dashboard_users WHERE id=${DUID};")
echo "=== $(date -u) kick daniel_risling START (tg_id='${TG_ID}') ===" >> "$LOG"

# --- Laufzeit-Check (nachgeruestet 2026-09-11, Lehre Lihua/Timo): hat der Kunde wieder gezahlt? ---
# Liegt fuer unser Produkt ein Ablefy-GRANT mit SPAETEREM access_valid_until als dem
# Laufzeitende vor -> KEIN Ban, nur Admin-Alert.
# NICHT nach Zeitstempel filtern: das Kuendigungs-Event traegt selbst access_type=GRANT.
G_EMAIL="d.risling@live.de"
G_UNTIL="2026-10-03T00:00:00Z"
G_SQL="FROM webhook_logs WHERE lower(payload) LIKE '%${G_EMAIL}%' AND json_extract(payload,'\$.access.access_type')='GRANT' AND CAST(json_extract(payload,'\$.product.product_id') AS TEXT) IN ('517561','517562') AND COALESCE(json_extract(payload,'\$.access.access_valid_until'),'') > '${G_UNTIL}'"
REGRANT=$(sqlite3 "$DB" "SELECT COUNT(*) ${G_SQL};")
G_MAXUNTIL=$(sqlite3 "$DB" "SELECT COALESCE(MAX(json_extract(payload,'\$.access.access_valid_until')),'') ${G_SQL};")
echo "Re-GRANT-Check (valid_until > ${G_UNTIL}): ${REGRANT} (max ${G_MAXUNTIL})" >> "$LOG"
if [ "$REGRANT" != "0" ]; then
  echo "ABBRUCH: neuerer GRANT gefunden -> KEIN Ban, nur Admin-Alert" >> "$LOG"
  [ -n "$ADMIN" ] && curl -s "https://api.telegram.org/bot${TOKEN}/sendMessage" -d chat_id="$ADMIN" --data-urlencode text="[KICK ABGEBROCHEN] ${G_EMAIL} sollte heute gekickt werden - laut Ablefy hat der Kunde aber WIEDER GEZAHLT (Zugang gueltig bis ${G_MAXUNTIL}). Kein Ban ausgefuehrt, Zugang bleibt. Falls er spaeter doch raus soll: neuen Kick-Termin setzen." >> "$LOG" 2>&1
  echo "=== $(date -u) kick_daniel_risling ABORTED (re-grant) ===" >> "$LOG"
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
  curl -s "https://api.telegram.org/bot${TOKEN}/sendMessage" -d chat_id="$ADMIN" -d text="[KICK] d.risling@live.de / Daniel Risling (id 477) Abo abgelaufen 03.10.2026 — Auto-Kick nicht sicher bestaetigt. Bitte MANUELL aus Paid-Gruppe/Scalp entfernen. Telegram: Daniel Risling (ID 8601828159)." >> "$LOG" 2>&1
  echo "ADMIN-ALERT gesendet" >> "$LOG"
fi
echo "=== $(date -u) kick daniel_risling DONE ===" >> "$LOG"
