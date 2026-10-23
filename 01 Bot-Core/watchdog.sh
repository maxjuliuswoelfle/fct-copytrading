#!/bin/bash
# (C) watchdog.sh — Startet den Copy Trading Bot und restartet bei Crash
#
# Nutzung: ./watchdog.sh
# Beenden: Ctrl+C (stoppt Watchdog + Bot)

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
BOT_SCRIPT="$SCRIPT_DIR/listen.py"
LOG_FILE="$SCRIPT_DIR/bot_output.log"
WATCHDOG_LOG="$SCRIPT_DIR/watchdog.log"
MIN_RESTART_DELAY=5     # Mindestens 5 Sekunden zwischen Restarts
MAX_RESTART_DELAY=60    # Maximal 60 Sekunden Backoff
RESTART_DELAY=$MIN_RESTART_DELAY
CRASH_COUNT=0

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$WATCHDOG_LOG"
}

cleanup() {
    log "Watchdog gestoppt — Bot wird beendet"
    if [ -n "$BOT_PID" ] && kill -0 "$BOT_PID" 2>/dev/null; then
        kill "$BOT_PID"
        wait "$BOT_PID" 2>/dev/null
    fi
    exit 0
}

trap cleanup SIGINT SIGTERM

log "=========================================="
log "WATCHDOG GESTARTET"
log "=========================================="

while true; do
    log "Starte Bot (PID wird gleich zugewiesen)..."
    python3 "$BOT_SCRIPT" >> "$LOG_FILE" 2>&1 &
    BOT_PID=$!
    log "Bot gestartet (PID: $BOT_PID)"

    # Warten bis Bot beendet wird
    wait "$BOT_PID"
    EXIT_CODE=$?

    CRASH_COUNT=$((CRASH_COUNT + 1))
    log "Bot beendet (Exit Code: $EXIT_CODE, Crash #$CRASH_COUNT)"

    # Exit Code 0 = sauberes Beenden (kein Restart)
    if [ $EXIT_CODE -eq 0 ]; then
        log "Sauberes Beenden — kein Restart"
        break
    fi

    # Exponentieller Backoff
    log "Restart in ${RESTART_DELAY}s..."
    sleep "$RESTART_DELAY"

    # Backoff erhoehen (max 60s)
    RESTART_DELAY=$((RESTART_DELAY * 2))
    if [ $RESTART_DELAY -gt $MAX_RESTART_DELAY ]; then
        RESTART_DELAY=$MAX_RESTART_DELAY
    fi

    # Nach 5 erfolgreichen Minuten Backoff zuruecksetzen
    # (wird beim naechsten Crash wieder erhoeht)
done

log "Watchdog beendet"
