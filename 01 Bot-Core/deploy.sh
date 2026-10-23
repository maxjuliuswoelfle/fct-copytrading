#!/bin/bash
# (C) deploy.sh — Bot-Code auf den Server deployen
#
# Nutzung:
#   ./deploy.sh <SERVER-IP>
#   ./deploy.sh <SERVER-IP> <SSH-USER>   (Default: root)
#
# Was das Script macht:
# 1. Alle Python-Dateien + Config auf den Server kopieren
# 2. Dependencies installieren
# 3. Service neustarten (falls aktiv)
#
# ACHTUNG: Kopiert NICHT .env oder die Datenbank — die bleiben auf dem Server.

set -e

if [ -z "$1" ]; then
    echo "Nutzung: ./deploy.sh <SERVER-IP> [SSH-USER]"
    echo "Beispiel: ./deploy.sh 49.13.100.42"
    exit 1
fi

SERVER_IP="$1"
SSH_USER="${2:-root}"
BOT_USER="botuser"
REMOTE_DIR="/home/$BOT_USER/copy-trading-bot"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=========================================="
echo "Deploy nach $SSH_USER@$SERVER_IP"
echo "=========================================="

# Dateien die deployed werden
FILES=(
    "auth.py"
    "bot_types.py"
    "config.py"
    "customer_ws.py"
    "database.py"
    "execution.py"
    "listen.py"
    "logger_setup.py"
    "manage.py"
    "parser.py"
    "requirements.txt"
    "rest_client.py"
    "scaling.py"
    "telegram.py"
    "watchdog.sh"
    "websocket_client.py"
    "copy-trading-bot.service"
    "setup.sh"
)

# 1. Verzeichnis erstellen
echo "[1/4] Verzeichnis erstellen..."
ssh "$SSH_USER@$SERVER_IP" "mkdir -p $REMOTE_DIR"

# 2. Dateien kopieren
echo "[2/4] Dateien kopieren..."
for f in "${FILES[@]}"; do
    if [ -f "$SCRIPT_DIR/$f" ]; then
        scp -q "$SCRIPT_DIR/$f" "$SSH_USER@$SERVER_IP:$REMOTE_DIR/$f"
        echo "  ✓ $f"
    else
        echo "  ✗ $f (nicht gefunden, uebersprungen)"
    fi
done

# 3. Dependencies installieren + Rechte setzen
echo "[3/4] Dependencies installieren..."
ssh "$SSH_USER@$SERVER_IP" bash <<EOF
    # venv erstellen falls noetig
    if [ ! -d "$REMOTE_DIR/venv" ]; then
        python3 -m venv "$REMOTE_DIR/venv"
    fi

    # Dependencies installieren
    "$REMOTE_DIR/venv/bin/pip" install -q -r "$REMOTE_DIR/requirements.txt"

    # Rechte setzen
    chown -R $BOT_USER:$BOT_USER "$REMOTE_DIR"
    chmod +x "$REMOTE_DIR/watchdog.sh"
    chmod +x "$REMOTE_DIR/deploy.sh" 2>/dev/null || true

    # Service-Datei aktualisieren
    cp "$REMOTE_DIR/copy-trading-bot.service" /etc/systemd/system/
    systemctl daemon-reload
EOF
echo "  ✓ Dependencies installiert"

# 4. Service neustarten (falls er laeuft)
echo "[4/4] Service pruefen..."
RUNNING=$(ssh "$SSH_USER@$SERVER_IP" "systemctl is-active copy-trading-bot 2>/dev/null || echo 'inactive'")
if [ "$RUNNING" = "active" ]; then
    echo "  Bot laeuft — wird neugestartet..."
    ssh "$SSH_USER@$SERVER_IP" "systemctl restart copy-trading-bot"
    sleep 2
    STATUS=$(ssh "$SSH_USER@$SERVER_IP" "systemctl is-active copy-trading-bot")
    echo "  ✓ Bot neugestartet (Status: $STATUS)"
else
    echo "  Bot ist nicht aktiv — kein Restart"
    echo "  Starten mit: ssh $SSH_USER@$SERVER_IP 'systemctl start copy-trading-bot'"
fi

echo ""
echo "=========================================="
echo "Deploy abgeschlossen!"
echo "=========================================="
echo ""
echo "Server:  $SERVER_IP"
echo "Bot-Dir: $REMOTE_DIR"
echo ""
