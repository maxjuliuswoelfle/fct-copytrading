# (C) Systemarchitektur — Copy Trading Bot

> Zuletzt aktualisiert: 2026-05-15


## Überblick

Der Copy Trading Bot spiegelt die Perpetual/Futures Trades von Max' Master-Account in Echtzeit auf die Accounts zahlender Kunden. Positionsgrößen werden **proportional zur Account-Größe** umgerechnet. Das Dashboard gibt Kunden Echtzeit-Einblick in ihre Trades, Performance und Account-Status.

```
┌─────────────────────┐
│  Max' Master Account│
│  (Levex Perpetual)  │
└────────┬────────────┘
         │ WebSocket (perpAccount.subscribe)
         ▼
┌───────────────────────────────────────────────────┐
│                 COPY TRADING BOT                  │
│                                                   │
│  ┌───────────┐  ┌──────────┐  ┌────────────────┐ │
│  │ listen.py │→│parser.py │→│ execution.py   │ │
│  │(WebSocket)│  │(14 Acts) │  │(REST pro Kunde)│ │
│  └───────────┘  └──────────┘  └───────┬────────┘ │
│        │                              │           │
│  ┌─────▼──────┐                ┌──────▼────────┐ │
│  │customer_ws │                │  scaling.py   │ │
│  │(Balance WS)│                │(Proportional) │ │
│  └────────────┘                └───────────────┘ │
│                                                   │
│  ┌─────────────────────────────────────────────┐ │
│  │           database.py (SQLite WAL)          │ │
│  └──────────────────────┬──────────────────────┘ │
│                         │                         │
│  ┌──────────────────────▼──────────────────────┐ │
│  │         Dashboard (FastAPI + Jinja2)        │ │
│  │         Port 8443 — Kunden-Portal           │ │
│  └─────────────────────────────────────────────┘ │
│                                                   │
│  ┌─────────────┐  ┌─────────────┐                │
│  │ telegram.py │  │  manage.py  │                │
│  │  (Alerts)   │  │   (CLI)     │                │
│  └─────────────┘  └─────────────┘                │
└───────────────────────────────────────────────────┘
         │ REST API (copy-affiliate-order)
         ▼
┌─────────────────────┐
│  Kunden-Accounts    │
│  (Levex Perpetual)  │
└─────────────────────┘
```


## Tech Stack

| Komponente | Technologie | Grund |
|-----------|-------------|-------|
| Runtime | Python 3.11+ (asyncio) | Async-native, schnelles Prototyping, robustes Ecosystem |
| Datenbank | SQLite (WAL Mode) | Leichtgewichtig, kein separater DB-Server nötig, shared zwischen Bot und Dashboard |
| Dashboard | FastAPI + Jinja2 | Async-kompatibel, schnell, modernes Python-Webframework |
| REST Client | aiohttp | Async HTTP-Requests an Levex REST API |
| WebSocket | websockets | Async WebSocket-Verbindungen (Master + Kunden) |
| Frontend Charts | Chart.js | Equity-Kurven und Performance-Visualisierung |
| Deployment | Systemd auf Ubuntu VPS (Hetzner) | Stabil, Auto-Restart, kein Overhead durch Container |
| Alerting | Telegram Bot API | Echtzeit-Benachrichtigungen + interaktive Befehle |


## Datenfluss

```
Levex WebSocket → listen.py → parser.py → execution.py → REST API → Kunden-Accounts
                                                 ↓
                                           database.py (SQLite WAL)
                                                 ↓
                                       Dashboard (FastAPI) → Browser
```

1. **listen.py** empfängt Trade-Events über den Master-WebSocket
2. **parser.py** klassifiziert das Event in eine von 14 BotActions
3. **execution.py** berechnet via **scaling.py** die Positionsgröße und führt den Trade per REST auf allen aktiven Kunden-Accounts aus
4. Alles wird in **SQLite** persistiert
5. Das **Dashboard** liest aus derselben Datenbank und zeigt Kunden ihre Daten


## Komponenten im Detail


### 1. listen.py — WebSocket Listener (Haupteinstieg)

Verbindet sich mit dem Levex WebSocket und hört Max' Perpetual Account in Echtzeit mit.

**Subscription:**
```json
{
  "method": "perpAccount.subscribe",
  "params": {
    "account": true,
    "position": true,
    "order": true,
    "positionInfo": true,
    "historyLimit": 0,
    "allPositions": true
  }
}
```

**Empfängt:**
- `perpOrder.update` — Order-Events (New, Filled, Canceled, Amended)
- `perpPosition.update` — Position-Changes (Size, Margin, Leverage, Liquidation)
- `perpAccount.update` — Account Balance Changes

**Weitere Aufgaben:**
- Lädt Kundenliste automatisch alle 60 Sekunden neu (neue Kunden werden sofort aktiv)
- Startet pro Kunde eine eigene WebSocket-Verbindung für Live-Balance-Tracking (`customer_ws.py`)


### 2. parser.py — Event Parser

Parsed WebSocket-Events in 14 Bot-Actions:

| BotAction | Beschreibung |
|-----------|-------------|
| `OPEN_TRADE` | Max eröffnet neuen Trade |
| `TRADE_FILLED` | Order wurde ausgeführt |
| `AMEND_TRADE` | Max ändert Order-Parameter (Preis/Qty) |
| `CANCEL_TRADE` | Max cancelt offene Order |
| `SET_SL` | Stop Loss gesetzt |
| `SET_TP` | Take Profit gesetzt |
| `CANCEL_SL` | Stop Loss entfernt |
| `CANCEL_TP` | Take Profit entfernt |
| `SCALE_IN` | Max skaliert nach (Nachkauf) |
| `SCALE_OUT` | Max reduziert Position teilweise |
| `CLOSE_TRADE` | Max schließt Position komplett |
| `UPDATE_LEVERAGE` | Hebel angepasst |
| `UPDATE_MARGIN` | Margin hinzugefügt/entfernt |
| `RENAME_POSITION` | Position umbenannt |


### 3. execution.py — Order Executor

Führt geparste Events auf **allen aktiven Kunden-Accounts** aus.

- Nutzt pro Kunde einen eigenen REST-Client (`rest_client.py`)
- Verwaltet Position-Mappings (Master-Position → Kunden-Position)
- Führt bei Bot-Restart eine Reconciliation durch (siehe unten)
- Per-Symbol-Locks verhindern Race Conditions


### 4. scaling.py — Skalierungslogik

Berechnet die proportionale Positionsgröße für jeden Kunden.

**Formel:**
```
customer_qty = master_qty × (customer_balance / master_balance)
→ Abrunden auf lot_size
→ Wenn < min_order_size UND Margin verfügbar → Aufrunden auf Minimum
```

**Beispiel:**
- Max: 10.000 USDT Balance, handelt 1 BTC
- Kunde A: 1.000 USDT Balance → 0.1 BTC
- Kunde B: 5.000 USDT Balance → 0.5 BTC
- Kunde C: 250 USDT Balance → 0.025 BTC

**Regeln:**
- Gleicher Hebel und gleiche Richtung (Long/Short) wie Max
- SL/TP preisbasiert (Preis ist universal, Qty wird skaliert)
- Rounding auf erlaubte Lot-Size/Tick-Size der Exchange
- Minimum-Fallback: Wenn berechnet < Minimum aber Margin reicht → auf Minimum aufrunden


### 5. websocket_client.py — Master WebSocket

Stabile WebSocket-Verbindung zum Master-Account:

- **Heartbeat:** Alle 5 Sekunden `server.ping`
- **Stale Detection:** Wenn >30 Sekunden keine Antwort → Reconnect
- **Auto-Reconnect:** Exponential Backoff (1s → 2s → 4s → ... → max 30s)


### 6. customer_ws.py — Kunden WebSocket

Pro Kunde eine eigene WebSocket-Verbindung für Live-Balance-Tracking:

- Nutzt Futures **Read** API Keys (nur Lesen, kein Handel)
- Aktualisiert `customer_balance` in Echtzeit für die Skalierungsberechnung


### 7. rest_client.py — REST Client

Levex REST Client für Trade-Ausführung:

- Nutzt den `copy-affiliate-order` Endpoint
- Authentifizierung via **HMAC-SHA256** Signatur (`auth.py`)
- Async via aiohttp


### 8. database.py — Datenbank

SQLite mit WAL-Modus (Write-Ahead Logging) — shared zwischen Bot und Dashboard.

**Tabellen:**

| Tabelle | Zweck |
|---------|-------|
| `customers` | Kundendaten, API Keys, Status, Balance |
| `position_mappings` | Master-Position → Kunden-Position Zuordnung |
| `trade_history` | Abgeschlossene Kunden-Trades |
| `master_trade_history` | Abgeschlossene Master-Trades |
| `dashboard_users` | Login-Daten für das Kunden-Dashboard |
| `telegram_subscribers` | Telegram-Benachrichtigungs-Empfänger |
| `bot_state` | Persistierter Bot-Zustand |


### 9. bot_types.py — Datentypen

Dataclasses die exakt die Levex API abbilden:

| Dataclass | Felder |
|-----------|--------|
| `PerpOrder` | 38 Felder |
| `PerpFill` | 27 Felder |
| `PerpPosition` | 35 Felder |
| `PerpAccount` | 14 Felder |
| `BotAction` | Enum mit 14 Actions |


### 10. telegram.py — Telegram Alerts

Echtzeit-Benachrichtigungen und interaktive Steuerung:

**Alerts:** Trade geöffnet/geschlossen, Fehler, Reconnects, Status-Updates

**Interaktive Befehle:**
- `/start` — Bot starten
- `/stop` — Bot stoppen
- `/status` — Aktueller Bot-Status


### 11. manage.py — CLI Tool

Command-Line-Interface für Kunden-Management (Kunden hinzufügen, deaktivieren, etc.)


### 12. Weitere Module

| Modul | Zweck |
|-------|-------|
| `auth.py` | HMAC-SHA256 Signatur-Generierung für WebSocket und REST |
| `config.py` | Environment-Konfiguration aus `.env` (API Keys, Master UID, Environment) |
| `logger_setup.py` | Farbiges Console-Logging |


## Dashboard (Kunden-Portal)

FastAPI-App mit Jinja2-Templates — das Frontend für zahlende Kunden.

### Seiten

| Seite | Funktion |
|-------|----------|
| Login | Kunden-Anmeldung |
| Register | Registrierung mit rechtlichen Checkboxen |
| Setup Wizard | 3-Schritt-Einrichtung (API Keys verknüpfen, etc.) |
| Dashboard | Hauptansicht: Balance, P&L, aktive Trades, Equity-Kurve |
| Support | Kontakt/Hilfe |
| Settings | Konto-Einstellungen |
| Legal Pages | Impressum, AGB, Datenschutz, Risikohinweis |

### API Endpoints

| Endpoint | Daten |
|----------|-------|
| `/api/live` | Balance, offene Positionen, P&L (wird alle 10s gepollt) |
| `/api/stats` | Performance-Statistiken |
| `/api/positions` | Aktive Positionen |
| `/api/history` | Trade-Historie |
| `/api/equity` | Equity-Kurve (Chart.js) |
| `/api/feed` | Activity Feed |
| `/api/recent-trades` | Letzte Trades |
| `/api/toggle-pause` | Copy Trading pausieren/fortsetzen |

### Frontend

- Polling alle 10 Sekunden auf `/api/live` für Echtzeit-Daten
- Chart.js für Equity-Kurven
- Cookie-Banner + vollständige Legal Compliance (Impressum, AGB, Datenschutz, Risikohinweis)


## Trade Management — Alle implementierten Features

| Feature | Status |
|---------|--------|
| Open/Close Trades (Market + Limit Workaround) | Implementiert |
| Scale-In / Scale-Out | Implementiert |
| SL setzen + entfernen | Implementiert |
| TP setzen + entfernen | Implementiert |
| Leverage ändern | Implementiert |
| Margin anpassen | Implementiert |
| Position umbenennen | Implementiert |
| Order ändern (Amend) | Implementiert |
| Order canceln | Implementiert |


## Reconciliation bei Restart

Wenn der Bot neu startet, werden offene Positionen abgeglichen:

| Situation | Aktion |
|-----------|--------|
| Master offen + Mapping aktiv | OK — nichts zu tun |
| Master geschlossen + Mapping aktiv | Kunden-Position schließen (verwaist) |
| Master offen + kein Mapping | Loggen als "missed" — **kein** automatisches Nachholen |


## Sicherheit

| Risiko | Maßnahme |
|--------|----------|
| API Keys im Code | Ausschließlich in `.env` — nie im Code oder in Dateien |
| Authentifizierung | HMAC-SHA256 Signaturen auf allen Requests |
| Missbrauch von Kunden-Keys | Copy-Trading Keys können **nur handeln, nicht abheben** |
| Balance-Einsicht | Read Keys nur für Balance-Tracking, keine Handelsrechte |
| Fehler bei einem Kunden | Per-Customer Error Isolation — ein Fehler stoppt nicht die anderen |
| Race Conditions | Per-Symbol-Locks verhindern parallele Konflikte |
| Bot-Crash während Trade | SQLite persistiert State → Reconciliation nach Restart |


## Deployment

| Parameter | Wert |
|-----------|------|
| Server | Hetzner VPS (CX22) |
| Specs | 2 vCPU, 4 GB RAM |
| Kosten | ~4,35€/Monat |
| OS | Ubuntu |
| Bot-User | `botuser` |
| Bot-Service | `copy-trading-bot` (systemd) |
| Dashboard-Service | `copy-trading-dashboard` (systemd) |
| Dashboard-Port | 8443 |
| Deploy-Script | `deploy-dashboard.sh` (SCP + systemctl restart) |

Beide Services laufen als systemd-Units mit Auto-Restart.


## Bekannte Limitierungen & Workarounds

### 1. Limit Orders
**Problem:** Die Levex Copy-Trading API unterstützt keine Limit Orders.
**Workaround:** `OPEN_TRADE` erkennen → auf `TRADE_FILLED` warten → dann Market Order beim Kunden platzieren.

### 2. SL/TP bei Limit Orders
**Problem:** SL/TP können bei Limit Orders nicht direkt mitgegeben werden.
**Workaround:** SL/TP wird über einen separaten `trading-stop` Endpoint gesetzt, nachdem die Position eröffnet wurde.

### 3. Multi-Trade Mode
**Verhalten:** Der Bot setzt Kunden explizit in den Multi-Trade-Modus. Positionen werden per `positionID` getrackt, nicht per Symbol — damit sind mehrere Positionen im selben Markt möglich.


## Umgebungsvariablen

Konfiguriert über `.env`:

| Variable | Zweck |
|----------|-------|
| `LEVEX_API_KEY` | Master API Key |
| `LEVEX_API_SECRET` | Master API Secret |
| `LEVEX_MASTER_UID` | Master Account UID |
| `LEVEX_ENV` | Environment (testnet/mainnet) |
