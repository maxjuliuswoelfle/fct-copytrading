#!/bin/bash
# (C) setup.sh — Server-Setup fuer den Copy Trading Bot
#
# Ausfuehren als root auf einem frischen Ubuntu 24.04 Server:
#   bash setup.sh
#
# Was das Script macht:
# 1. System-Updates installieren
# 2. Python 3.11+ und Dependencies installieren
# 3. Bot-User erstellen
# 4. Bot-Verzeichnis einrichten + venv
# 5. systemd Service installieren

set -e  # Bei Fehler abbrechen

echo "=========================================="
echo "Copy Trading Bot — Server Setup"
echo "=========================================="

# 1. System updaten
echo "[1/5] System-Updates..."
apt update && apt upgrade -y

# 2. Python + Tools installieren
echo "[2/5] Python + Tools installieren..."
apt install -y python3 python3-pip python3-venv curl nano htop

# Python-Version pruefen
PYTHON_VERSION=$(python3 --version 2>&1)
echo "  Python: $PYTHON_VERSION"

# 3. Bot-User erstellen (falls nicht vorhanden)
echo "[3/5] Bot-User einrichten..."
if ! id "botuser" &>/dev/null; then
    useradd -m -s /bin/bash botuser
    echo "  User 'botuser' erstellt"
else
    echo "  User 'botuser' existiert bereits"
fi

# 4. Bot-Verzeichnis + venv
echo "[4/5] Bot-Verzeichnis einrichten..."
BOT_DIR="/home/botuser/copy-trading-bot"
mkdir -p "$BOT_DIR"

# Virtual Environment erstellen
if [ ! -d "$BOT_DIR/venv" ]; then
    python3 -m venv "$BOT_DIR/venv"
    echo "  venv erstellt"
fi

# Dependencies installieren (falls requirements.txt vorhanden)
if [ -f "$BOT_DIR/requirements.txt" ]; then
    "$BOT_DIR/venv/bin/pip" install -r "$BOT_DIR/requirements.txt"
    echo "  Dependencies installiert"
else
    echo "  [SKIP] requirements.txt nicht gefunden — wird beim Deploy installiert"
fi

# Rechte setzen
chown -R botuser:botuser "$BOT_DIR"

# 5. systemd Service installieren
echo "[5/5] systemd Service einrichten..."
if [ -f "$BOT_DIR/copy-trading-bot.service" ]; then
    cp "$BOT_DIR/copy-trading-bot.service" /etc/systemd/system/
    systemctl daemon-reload
    systemctl enable copy-trading-bot
    echo "  Service installiert und aktiviert"
    echo "  Starten mit: systemctl start copy-trading-bot"
else
    echo "  [SKIP] Service-Datei nicht gefunden — wird beim Deploy installiert"
fi

echo ""
echo "=========================================="
echo "Setup abgeschlossen!"
echo "=========================================="
echo ""
echo "Naechste Schritte:"
echo "  1. Code deployen:  ./deploy.sh <SERVER-IP>"
echo "  2. .env erstellen:  su - botuser && nano ~/copy-trading-bot/.env"
echo "  3. Kunden laden:    python3 manage.py add"
echo "  4. Bot starten:     systemctl start copy-trading-bot"
echo ""
