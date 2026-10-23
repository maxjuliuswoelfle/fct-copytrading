# (C) Commands & Referenz

> **Zuletzt aktualisiert:** 2026-05-15

Schnellreferenz fuer alle Befehle rund um den Copy Trading Bot. Alle Befehle sind copy-pastebar.

**Server:** `178.105.135.197` | **User:** `root` | **Bot-User:** `botuser`
**Bot-Verzeichnis:** `/home/botuser/copy-trading-bot`
**Dashboard-Verzeichnis:** `/home/botuser/dashboard`
**Datenbank:** `/home/botuser/copy-trading-bot/copy_trading.db`


---

## Server-Zugang

```bash
ssh root@178.105.135.197
```


---

## Bot Management

### Bot starten
```bash
ssh root@178.105.135.197 "systemctl start copy-trading-bot"
```

### Bot stoppen
```bash
ssh root@178.105.135.197 "systemctl stop copy-trading-bot"
```

### Bot neustarten
```bash
ssh root@178.105.135.197 "systemctl restart copy-trading-bot"
```

### Bot Status pruefen
```bash
ssh root@178.105.135.197 "systemctl status copy-trading-bot"
```

### Bot Logs (live)
```bash
ssh root@178.105.135.197 "journalctl -u copy-trading-bot -f"
```

### Bot Logs (letzte 100 Zeilen)
```bash
ssh root@178.105.135.197 "journalctl -u copy-trading-bot -n 100"
```

### Bot Logs (letzte 100 Zeilen, kein Pager)
```bash
ssh root@178.105.135.197 "journalctl -u copy-trading-bot -n 100 --no-pager"
```


---

## Dashboard Management

### Dashboard neustarten
```bash
ssh root@178.105.135.197 "systemctl restart copy-trading-dashboard"
```

### Dashboard Status pruefen
```bash
ssh root@178.105.135.197 "systemctl status copy-trading-dashboard"
```

### Dashboard Logs (live)
```bash
ssh root@178.105.135.197 "journalctl -u copy-trading-dashboard -f"
```

### Dashboard Logs (letzte 100 Zeilen)
```bash
ssh root@178.105.135.197 "journalctl -u copy-trading-dashboard -n 100 --no-pager"
```


---

## Deploy

### Bot-Core deployen (automatisch)
```bash
cd "03 Projects/Copy Trading Bot/01 Bot-Core" && ./deploy.sh 178.105.135.197
```
> Kopiert alle Python-Dateien + Config, installiert Dependencies, startet Bot neu falls er laeuft.
> ACHTUNG: `.env` und Datenbank werden NICHT ueberschrieben.

### Dashboard deployen (automatisch)
```bash
cd "03 Projects/Copy Trading Bot/03 Dashboard/MVP 1.0" && ./deploy-dashboard.sh 178.105.135.197
```
> Kopiert App, Templates, Static Files, installiert Dependencies, startet Dashboard neu.

### Bot-Core manuell deployen (einzelne Datei)
```bash
scp "01 Bot-Core/DATEINAME.py" root@178.105.135.197:/home/botuser/copy-trading-bot/DATEINAME.py
ssh root@178.105.135.197 "chown botuser:botuser /home/botuser/copy-trading-bot/DATEINAME.py && systemctl restart copy-trading-bot"
```


---

## Kunden-Verwaltung (manage.py)

Alle `manage.py`-Befehle laufen auf dem Server im Bot-Verzeichnis.

### Alle Kunden anzeigen
```bash
ssh root@178.105.135.197 "cd /home/botuser/copy-trading-bot && /home/botuser/copy-trading-bot/venv/bin/python manage.py list"
```

### Neuen Kunden hinzufuegen (interaktiv)
```bash
ssh -t root@178.105.135.197 "cd /home/botuser/copy-trading-bot && /home/botuser/copy-trading-bot/venv/bin/python manage.py add"
```
> Braucht `-t` fuer interaktive Eingabe. Fragt nach: Name, UID, API Key, API Secret, Read API Key (optional).

### Kunden deaktivieren
```bash
ssh root@178.105.135.197 "cd /home/botuser/copy-trading-bot && /home/botuser/copy-trading-bot/venv/bin/python manage.py remove <KUNDE-ID>"
```

### Dashboard-Einladungslink erstellen
```bash
ssh -t root@178.105.135.197 "cd /home/botuser/copy-trading-bot && /home/botuser/copy-trading-bot/venv/bin/python manage.py invite <KUNDE-ID>"
```
> Erstellt einen Link den der Kunde bekommt um sein Dashboard-Passwort zu setzen.

### Test-Kunde aus .env migrieren
```bash
ssh root@178.105.135.197 "cd /home/botuser/copy-trading-bot && /home/botuser/copy-trading-bot/venv/bin/python manage.py migrate-env"
```


---

## Datenbank (SQLite)

Alle DB-Befehle nutzen `sqlite3` direkt auf dem Server.

### Alle Kunden anzeigen
```bash
ssh root@178.105.135.197 "sqlite3 -header -column /home/botuser/copy-trading-bot/copy_trading.db 'SELECT id, name, uid, is_active, last_known_balance, onboarding_status FROM customers;'"
```

### Kunden-Balance pruefen
```bash
ssh root@178.105.135.197 "sqlite3 -header -column /home/botuser/copy-trading-bot/copy_trading.db 'SELECT id, name, last_known_balance, balance_updated_at FROM customers WHERE is_active = 1;'"
```

### Aktive Position-Mappings anzeigen
```bash
ssh root@178.105.135.197 "sqlite3 -header -column /home/botuser/copy-trading-bot/copy_trading.db 'SELECT customer_id, symbol, side, customer_qty, customer_entry_price, leverage FROM position_mappings WHERE is_active = 1;'"
```

### Trade-Historie anzeigen (letzte 20)
```bash
ssh root@178.105.135.197 "sqlite3 -header -column /home/botuser/copy-trading-bot/copy_trading.db 'SELECT customer_id, symbol, side, action, qty, price, pnl, created_at FROM trade_history ORDER BY created_at DESC LIMIT 20;'"
```

### Master-Trade-Historie anzeigen (letzte 20)
```bash
ssh root@178.105.135.197 "sqlite3 -header -column /home/botuser/copy-trading-bot/copy_trading.db 'SELECT symbol, side, action, qty, price, pnl, created_at FROM master_trade_history ORDER BY created_at DESC LIMIT 20;'"
```

### Kunden freischalten (manuell)
```bash
ssh root@178.105.135.197 "sqlite3 /home/botuser/copy-trading-bot/copy_trading.db \"UPDATE customers SET is_active = 1, onboarding_status = 'active' WHERE id = '<KUNDE-ID>';\""
```

### API Keys eintragen (manuell)
```bash
ssh root@178.105.135.197 "sqlite3 /home/botuser/copy-trading-bot/copy_trading.db \"UPDATE customers SET api_key = '<API-KEY>', api_secret = '<API-SECRET>', uid = '<UID>' WHERE id = '<KUNDE-ID>';\""
```

### Read-Only API Keys eintragen
```bash
ssh root@178.105.135.197 "sqlite3 /home/botuser/copy-trading-bot/copy_trading.db \"UPDATE customers SET read_api_key = '<READ-KEY>', read_api_secret = '<READ-SECRET>' WHERE id = '<KUNDE-ID>';\""
```

### Dashboard-User anzeigen
```bash
ssh root@178.105.135.197 "sqlite3 -header -column /home/botuser/copy-trading-bot/copy_trading.db 'SELECT customer_id, email, is_activated, created_at FROM dashboard_users;'"
```

### Telegram Subscriber anzeigen
```bash
ssh root@178.105.135.197 "sqlite3 -header -column /home/botuser/copy-trading-bot/copy_trading.db 'SELECT chat_id, username, first_name, is_active FROM telegram_subscribers;'"
```

### Alle User loeschen (Komplett-Reset)
```bash
ssh root@178.105.135.197 "sqlite3 /home/botuser/copy-trading-bot/copy_trading.db 'DELETE FROM customers; DELETE FROM dashboard_users; DELETE FROM position_mappings; DELETE FROM trade_history; DELETE FROM master_trade_history; DELETE FROM telegram_subscribers;'"
```
> ACHTUNG: Loescht ALLE Daten unwiderruflich. Nur fuer Test-Resets.

### DB Schema einer Tabelle anzeigen
```bash
ssh root@178.105.135.197 "sqlite3 /home/botuser/copy-trading-bot/copy_trading.db 'PRAGMA table_info(customers);'"
```
> Verfuegbare Tabellen: `customers`, `dashboard_users`, `position_mappings`, `trade_history`, `master_trade_history`, `telegram_subscribers`, `bot_state`

### Bot-State anzeigen
```bash
ssh root@178.105.135.197 "sqlite3 -header -column /home/botuser/copy-trading-bot/copy_trading.db 'SELECT * FROM bot_state;'"
```


---

## Telegram Bot

Der Bot sendet Trade-Alerts an abonnierte Telegram-User.

| Befehl | Beschreibung |
|--------|-------------|
| `/start PASSWORD` | Alerts abonnieren (Passwort noetig) |
| `/stop` | Alerts abbestellen |
| `/status` | Bot-Status anzeigen |


---

## Schnell-Checks

### Laeuft alles?
```bash
ssh root@178.105.135.197 "systemctl is-active copy-trading-bot && systemctl is-active copy-trading-dashboard"
```

### Wieviele aktive Kunden + Positionen?
```bash
ssh root@178.105.135.197 "sqlite3 /home/botuser/copy-trading-bot/copy_trading.db 'SELECT (SELECT COUNT(*) FROM customers WHERE is_active = 1) as aktive_kunden, (SELECT COUNT(*) FROM position_mappings WHERE is_active = 1) as aktive_positionen;'"
```

### Letzte Bot-Aktivitaet (letzter Trade)
```bash
ssh root@178.105.135.197 "sqlite3 -header -column /home/botuser/copy-trading-bot/copy_trading.db 'SELECT symbol, action, created_at FROM master_trade_history ORDER BY created_at DESC LIMIT 1;'"
```
