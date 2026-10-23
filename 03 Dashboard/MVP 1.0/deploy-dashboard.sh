#!/bin/bash
# (C) deploy-dashboard.sh — Dashboard auf den Server deployen
#
# Nutzung:
#   ./deploy-dashboard.sh <SERVER-IP>
#   ./deploy-dashboard.sh <SERVER-IP> <SSH-USER>   (Default: root)

set -e

if [ -z "$1" ]; then
    echo "Nutzung: ./deploy-dashboard.sh <SERVER-IP> [SSH-USER]"
    exit 1
fi

SERVER_IP="$1"
SSH_USER="${2:-root}"
BOT_USER="botuser"
REMOTE_DIR="/home/$BOT_USER/dashboard"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "=========================================="
echo "Dashboard Deploy nach $SSH_USER@$SERVER_IP"
echo "=========================================="

# 1. Verzeichnisse erstellen
echo "[1/5] Verzeichnisse erstellen..."
ssh "$SSH_USER@$SERVER_IP" "mkdir -p $REMOTE_DIR/{routes,templates,static/logos}"

# 2. Dateien kopieren
echo "[2/5] Dateien kopieren..."

# Hauptdateien
for f in app.py db.py dash_auth.py exchange_client.py api_key_validator.py email_service.py requirements.txt; do
    scp -q "$SCRIPT_DIR/$f" "$SSH_USER@$SERVER_IP:$REMOTE_DIR/$f"
    echo "  ✓ $f"
done

# Routes
for f in "$SCRIPT_DIR"/routes/*.py; do
    fname=$(basename "$f")
    scp -q "$f" "$SSH_USER@$SERVER_IP:$REMOTE_DIR/routes/$fname"
    echo "  ✓ routes/$fname"
done

# __init__.py fuer routes Package
ssh "$SSH_USER@$SERVER_IP" "touch $REMOTE_DIR/routes/__init__.py"

# Templates
for f in "$SCRIPT_DIR"/templates/*.html; do
    fname=$(basename "$f")
    scp -q "$f" "$SSH_USER@$SERVER_IP:$REMOTE_DIR/templates/$fname"
    echo "  ✓ templates/$fname"
done

# Static (CSS, JS)
for f in "$SCRIPT_DIR"/static/*.css "$SCRIPT_DIR"/static/*.js; do
    [ -f "$f" ] || continue
    fname=$(basename "$f")
    scp -q "$f" "$SSH_USER@$SERVER_IP:$REMOTE_DIR/static/$fname"
    echo "  ✓ static/$fname"
done

# Static Logos
for f in "$SCRIPT_DIR"/static/logos/*.png; do
    [ -f "$f" ] || continue
    fname=$(basename "$f")
    scp -q "$f" "$SSH_USER@$SERVER_IP:$REMOTE_DIR/static/logos/$fname"
    echo "  ✓ static/logos/$fname"
done

# 3. Dependencies installieren
echo "[3/5] Dependencies installieren..."
ssh "$SSH_USER@$SERVER_IP" bash <<EOF
    BOT_VENV="/home/$BOT_USER/copy-trading-bot/venv"
    "\$BOT_VENV/bin/pip" install -q -r "$REMOTE_DIR/requirements.txt"
    chown -R $BOT_USER:$BOT_USER "$REMOTE_DIR"
EOF
echo "  ✓ Dependencies installiert (nutzt Bot-venv)"

# 4. Service installieren
echo "[4/5] Service installieren..."
scp -q "$SCRIPT_DIR/copy-trading-dashboard.service" "$SSH_USER@$SERVER_IP:/etc/systemd/system/"
ssh "$SSH_USER@$SERVER_IP" "systemctl daemon-reload"
echo "  ✓ Service installiert"

# 5. Service starten
echo "[5/5] Service starten..."
ssh "$SSH_USER@$SERVER_IP" "systemctl enable copy-trading-dashboard && systemctl restart copy-trading-dashboard"
sleep 2
STATUS=$(ssh "$SSH_USER@$SERVER_IP" "systemctl is-active copy-trading-dashboard")
echo "  ✓ Dashboard Status: $STATUS"

echo ""
echo "=========================================="
echo "Dashboard Deploy abgeschlossen!"
echo "=========================================="
echo ""
echo "Server:    $SERVER_IP"
echo "Dashboard: http://$SERVER_IP:8443"
echo "Remote:    $REMOTE_DIR"
echo ""
echo "WICHTIG: Firewall-Port oeffnen:"
echo "  ssh $SSH_USER@$SERVER_IP 'ufw allow 8443/tcp'"
echo ""
