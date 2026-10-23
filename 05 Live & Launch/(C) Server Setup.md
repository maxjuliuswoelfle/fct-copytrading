# (C) Server Setup — Copy Trading Bot Deployment

> **Zuletzt aktualisiert:** 2026-05-15
> Komplette Referenz für alles rund um den Server: Einrichtung, Deployment, Services, Datenbank, Troubleshooting.

---

## Server-Übersicht

| Was | Details |
|---|---|
| **Provider** | Hetzner Cloud |
| **Server-Typ** | CX22 (2 vCPU, 4 GB RAM, 40 GB SSD) — €4,35/Monat |
| **OS** | Ubuntu |
| **IP** | `178.105.135.197` |
| **SSH** | `root@178.105.135.197` |
| **Bot-User** | `botuser` |

---

## Verzeichnisstruktur auf dem Server

```
/home/botuser/
├── copy-trading-bot/       ← Bot-Core (Trade-Mirroring, Listener, etc.)
│   ├── venv/               ← Python Virtual Environment (wird von Bot + Dashboard geteilt)
│   ├── copy_trading.db     ← SQLite-Datenbank (WAL-Modus, geteilt zwischen Bot + Dashboard)
│   ├── .env                ← Umgebungsvariablen
│   ├── listen.py           ← Haupt-Listener
│   ├── manage.py           ← Kunden verwalten
│   └── copy-trading-bot.service  ← systemd Service-Datei
└── dashboard/              ← Dashboard (Flask-App auf Port 8443)
    ├── app.py              ← Flask-Hauptapp
    ├── db.py               ← DB-Zugriff
    ├── dash_auth.py        ← Authentifizierung
    ├── exchange_client.py  ← Exchange API Client
    ├── api_key_validator.py
    ├── requirements.txt
    ├── routes/             ← Flask Routes
    ├── templates/          ← HTML Templates
    └── static/             ← CSS, JS, Logos
```

---

## Umgebungsvariablen (.env)

Datei: `/home/botuser/copy-trading-bot/.env`

```env
# Levex API
LEVEX_API_KEY=xxx           # Master Read API Key
LEVEX_API_SECRET=xxx        # Master Read API Secret
LEVEX_MASTER_UID=xxx        # Master Account UID
LEVEX_ENV=production        # "production" oder "testnet"
LEVEX_WS_URL=wss://stream.levex.com  # WebSocket URL (production)

# Logging
LOG_LEVEL=info              # info / debug

# Telegram Notifications
TELEGRAM_BOT_TOKEN=xxx      # Telegram Bot Token
TELEGRAM_CHAT_ID=xxx        # Admin Chat ID
TELEGRAM_TEAM_PASSWORD=xxx  # Passwort für Team-Subscription
```

> **Sicherheit:** Niemals .env Dateien committen oder in Dokumente kopieren. Immer nur direkt auf dem Server bearbeiten.

---

## Services (systemd)

### Bot-Service: `copy-trading-bot`

- **Service-Datei:** `/etc/systemd/system/copy-trading-bot.service`
- **Läuft als:** `botuser`
- **Pfad:** `/home/botuser/copy-trading-bot/`

### Dashboard-Service: `copy-trading-dashboard`

- **Service-Datei:** `/etc/systemd/system/copy-trading-dashboard.service`
- **Läuft als:** `botuser`
- **Pfad:** `/home/botuser/dashboard/`
- **Port:** `8443`
- **Nutzt:** Bot-venv (`/home/botuser/copy-trading-bot/venv/`)

---

## Deployment

### Dashboard deployen

Vom lokalen Rechner aus:

```bash
cd "03 Dashboard/MVP 1.0" && ./deploy-dashboard.sh 178.105.135.197
```

Das Script macht automatisch:
1. Verzeichnisse auf dem Server erstellen
2. Alle Dateien kopieren (App, Routes, Templates, Static)
3. Dependencies im Bot-venv installieren
4. Service installieren + neustarten
5. Status prüfen

**Nach Deploy:** Firewall-Port öffnen falls noch nicht geschehen:
```bash
ssh root@178.105.135.197 'ufw allow 8443/tcp'
```

### Bot-Core deployen

Manuell per `scp` — Dateien hochladen, Rechte setzen, Service neustarten:

```bash
# Dateien hochladen
scp <DATEIEN> root@178.105.135.197:/home/botuser/copy-trading-bot/

# Rechte setzen + neustarten
ssh root@178.105.135.197 "chown -R botuser:botuser /home/botuser/copy-trading-bot/ && systemctl restart copy-trading-bot"
```

---

## Nützliche Befehle

### Services verwalten

```bash
# Bot
systemctl status copy-trading-bot
systemctl restart copy-trading-bot
systemctl stop copy-trading-bot

# Dashboard
systemctl status copy-trading-dashboard
systemctl restart copy-trading-dashboard
systemctl stop copy-trading-dashboard
```

### Logs ansehen

```bash
# Bot Live-Logs
journalctl -u copy-trading-bot -f

# Dashboard Live-Logs
journalctl -u copy-trading-dashboard -f

# Letzte 100 Zeilen
journalctl -u copy-trading-bot -n 100
journalctl -u copy-trading-dashboard -n 100
```

### Datenbank

Die SQLite-Datenbank liegt unter `/home/botuser/copy-trading-bot/copy_trading.db` und wird im WAL-Modus betrieben, damit Bot und Dashboard gleichzeitig zugreifen können.

```bash
# DB abfragen (auf dem Server)
cd /home/botuser/copy-trading-bot && venv/bin/python -c "
import sqlite3
db = sqlite3.connect('copy_trading.db')
# Beispiel: Alle Kunden anzeigen
for row in db.execute('SELECT * FROM customers'):
    print(row)
"

# Alle User + Kunden löschen (Vorsicht!)
cd /home/botuser/copy-trading-bot && venv/bin/python -c "
import sqlite3
db = sqlite3.connect('copy_trading.db')
db.execute('DELETE FROM dashboard_users')
db.execute('DELETE FROM customers')
db.commit()
print('Alle Users und Customers gelöscht.')
"
```

### Kunden verwalten

```bash
ssh root@178.105.135.197
su - botuser
cd ~/copy-trading-bot

python3 manage.py list    # Alle Kunden anzeigen
python3 manage.py add     # Neuen Kunden hinzufügen
```

---

## Ersteinrichtung (nur einmal nötig)

Falls der Server komplett neu aufgesetzt wird:

```bash
# 1. Per SSH verbinden
ssh root@178.105.135.197

# 2. System aktualisieren + Dependencies
apt update && apt upgrade -y
apt install -y python3 python3-pip python3-venv git

# 3. Bot-User erstellen
useradd -m -s /bin/bash botuser

# 4. Bot-Verzeichnis + venv erstellen
su - botuser
mkdir -p ~/copy-trading-bot
cd ~/copy-trading-bot
python3 -m venv venv
exit

# 5. Code deployen (siehe Deployment oben)

# 6. .env Datei erstellen
su - botuser
cd ~/copy-trading-bot
nano .env
# → Alle Umgebungsvariablen eintragen (siehe oben)
exit

# 7. Services einrichten
cp /home/botuser/copy-trading-bot/copy-trading-bot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable copy-trading-bot
systemctl start copy-trading-bot

# 8. IP bei Levex whitelisten
# Die feste IPv4 (178.105.135.197) in der Levex API-Key Konfiguration eintragen

# 9. Firewall
ufw allow 22/tcp      # SSH
ufw allow 8443/tcp    # Dashboard
ufw enable
```

---

## Troubleshooting

| Problem | Lösung |
|---|---|
| Bot startet nicht | `journalctl -u copy-trading-bot -n 50` — Logs prüfen |
| Dashboard nicht erreichbar | `ufw allow 8443/tcp` + `systemctl status copy-trading-dashboard` |
| DB locked | WAL-Modus prüfen — normalerweise kein Problem, ggf. Bot + Dashboard neustarten |
| Permission denied | `chown -R botuser:botuser /home/botuser/copy-trading-bot/` |
| Python-Packages fehlen | `venv/bin/pip install -r requirements.txt` (im jeweiligen Verzeichnis) |
| Service nach Reboot nicht gestartet | `systemctl enable copy-trading-bot` + `systemctl enable copy-trading-dashboard` |
