# (C) Signal-Produkte Architektur

> **Erstellt:** 2026-05-18
> **Status:** Entwurf — Review mit Max


## Überblick

Drei Produkte, ein Master Account, ein System:

| | Free Signals | Paid Signals | Copy Trading |
|--|--|--|--|
| **Preis** | 0€ (Affiliate-Anmeldung) | ~100€/mo | 500€ Setup + 300€/mo |
| **Signale** | 1-2/Woche (gefiltert) | Alle (10-20/mo) | Automatisch ausgeführt |
| **Management** | Nein | Ja (SL/TP Updates) | Ja (automatisch) |
| **Telegram** | ✅ Gruppe Free | ✅ Gruppe Paid | ❌ (optional) |
| **Dashboard** | ❌ | ✅ Light (mit Locks) | ✅ Voll |
| **Onboarding** | Eigener Flow | Eigener Flow | Eigener Flow (besteht) |

Alle drei Flows sind unabhängige Endpoints. Max verknüpft sie mit seinen Landingpages.


## Architektur

```
Levex WebSocket
      │
      ▼
  listen.py → parser.py → execution.py ──→ Kunden-Accounts (Copy Trading)
                  │
                  ▼
           signal_bot.py ──→ Telegram Paid Gruppe (alle Signale + Management)
                  │
                  ▼
                Filter ──→ Telegram Free Gruppe (nur ausgewählte Signale)
```

### Signal-Bot — Neues Modul: `signal_bot.py`

Hängt sich an denselben Event-Stream wie die Execution Engine. Nach jedem geparsten Event wird parallel:
1. Trade auf Kunden-Accounts ausgeführt (bestehend)
2. Signal in Telegram-Gruppen gepostet (neu)

Kein separater Service, kein Delay — gleicher Prozess, gleiche Events.


## Signal-Nachrichten Format

### Trade-Nummerierung

Problem: Mehrere Positionen pro Symbol (z.B. 2× BTC Short). Kunde muss Updates zuordnen können.

Lösung: **Laufende Nummer pro Symbol+Side**

- Erste BTC Short → `BTC Short #1`
- Zweite BTC Short → `BTC Short #2`
- Update → "⚙️ BTC Short #1 — SL angepasst auf $68.200"

Intern: Mapping `position_id → display_name` in DB. Nummerierung resettet wenn alle Positionen eines Symbol+Side geschlossen sind.

### Nachrichtentypen

**🟢 NEUER TRADE (OPEN)**
```
🟢 NEUER TRADE

📊 BTC Short #1
━━━━━━━━━━━━━━━
Entry:     $69.420
Leverage:  20x
Stop Loss: $71.500
Take Profit: $66.000
━━━━━━━━━━━━━━━
⚡ Live Signal · FirstClass Trading
```

**⚙️ UPDATE (SL/TP angepasst, Scale-In/Out)**
```
⚙️ UPDATE — BTC Short #1

🛡️ Stop Loss angepasst
Vorher: $71.500
Jetzt:  $70.200
━━━━━━━━━━━━━━━
⚡ Live Signal · FirstClass Trading
```

```
⚙️ UPDATE — BTC Short #1

📈 Nachkauf (Scale-In)
Menge: +0.05 BTC
Neuer Avg Entry: $69.100
━━━━━━━━━━━━━━━
⚡ Live Signal · FirstClass Trading
```

**🔴 TRADE GESCHLOSSEN (CLOSE)**
```
🔴 TRADE GESCHLOSSEN

📊 BTC Short #1
━━━━━━━━━━━━━━━
Ergebnis:  +4.2%
Entry:     $69.420
Exit:      $66.500
Dauer:     2T 14h
━━━━━━━━━━━━━━━
⚡ Live Signal · FirstClass Trading
```

### Free vs. Paid — Was wird gesendet?

| Event | Paid | Free |
|-------|------|------|
| OPEN | ✅ Alle | ✅ Nur gefiltert (1-2/Woche) |
| SL/TP Update | ✅ | ❌ |
| Scale-In/Out | ✅ | ❌ |
| CLOSE | ✅ Alle | ✅ Nur für Trades die auch geöffnet wurden |
| Leverage Change | ✅ | ❌ |

**Free-Filter-Logik:**
- Maximal 2 Signale pro Woche
- Nur OPEN + zugehöriger CLOSE (kein Management)
- Auswahl: Zufällig oder konfigurierbar (z.B. nur BTC/ETH)
- Config in `.env` auf dem Server: `FREE_SIGNALS_PER_WEEK=2`, `FREE_SIGNAL_SYMBOLS=BTCUSDT,ETHUSDT`


## Datenbank-Änderungen

### Bestehende Tabelle: `dashboard_users` — Neues Feld

```sql
ALTER TABLE dashboard_users ADD COLUMN product_tier TEXT DEFAULT 'free';
-- Werte: 'free', 'paid_signals', 'copy_trading'
```

Das `product_tier` bestimmt:
- Welchen Onboarding-Flow der User durchlaufen hat
- Was im Dashboard sichtbar/gesperrt ist
- Ob der User Copy Trading oder nur Signale nutzt

### Bestehende Tabelle: `customers` — Neue Felder

```sql
ALTER TABLE customers ADD COLUMN telegram_chat_id TEXT;
ALTER TABLE customers ADD COLUMN telegram_username TEXT;
```

Nur relevant für Copy-Trading-Kunden die auch Telegram-Notifications wollen (Phase 2).

### Neue Tabelle: `signal_display_names`

```sql
CREATE TABLE signal_display_names (
    position_id TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,      -- "BTC Short #1"
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    number INTEGER NOT NULL,         -- die laufende Nummer
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);
```

### Neue Tabelle: `signal_log`

```sql
CREATE TABLE signal_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id TEXT NOT NULL,
    signal_type TEXT NOT NULL,        -- 'open', 'update_sl', 'update_tp', 'scale_in', 'scale_out', 'close'
    message_text TEXT,                -- voller Nachrichtentext
    sent_to_paid INTEGER DEFAULT 0,   -- 1 = gesendet
    sent_to_free INTEGER DEFAULT 0,   -- 1 = gesendet
    created_at TEXT DEFAULT (datetime('now'))
);
```

Für Audit-Trail + Debugging. Wissen wir immer was wann wohin gesendet wurde.


## Drei Onboarding-Flows

### Flow 1: Free Signals — `/signup/free`

```
Schritt 1: Registrierung
  → Name, E-Mail, Passwort
  → AGB + Datenschutz + Risikohinweis Checkboxen

Schritt 2: Affiliate-Verifizierung
  → Nachweis dass Levex-Account über Max' Link erstellt wurde
  → (Methode TBD — Screenshot Upload oder Referral-ID)

Schritt 3: Telegram verbinden
  → Einmaliger Invite-Link zur Free-Gruppe
  → Oder: User schickt /start an Bot, Bot verifiziert und addet

Fertig → Kein Dashboard, nur Telegram-Zugang
```

**Endpoint:** `GET/POST /signup/free`
**Nach Abschluss:** Redirect zu "Fertig"-Seite mit Telegram-Link
**product_tier:** `free`

### Flow 2: Paid Signals — `/signup/signals`

```
Schritt 1: Registrierung
  → Name, E-Mail, Passwort
  → AGB + Datenschutz + Risikohinweis Checkboxen

Schritt 2: Affiliate-Verifizierung
  → Gleich wie Free

Schritt 3: Zahlung
  → Stripe Checkout (~100€/mo)

Schritt 4: Telegram verbinden
  → Einmaliger Invite-Link zur Paid-Gruppe

Fertig → Dashboard Light freigeschaltet + Telegram-Zugang
```

**Endpoint:** `GET/POST /signup/signals`
**Nach Abschluss:** Redirect zu Dashboard Light
**product_tier:** `paid_signals`

### Flow 3: Copy Trading — `/register` (besteht)

Bleibt wie er ist. 3-Schritt Setup-Wizard.
**product_tier:** `copy_trading`


## Dashboard Tiers

### Free User — Kein Dashboard
- Nur Telegram-Gruppe
- Bei Login-Versuch: "Du hast die Free Signals. Upgrade auf Paid Signals für dein persönliches Dashboard." + Link

### Paid Signal User — Dashboard Light

**Sichtbar:**
- Sidebar mit Navigation
- Telegram-Gruppe Link (prominent)
- Support-Seite
- Einstellungen
- Upsell-Banner für Copy Trading

**Gesperrt (geblurred + Lock):**
- Performance / Equity Chart
- Trade-Historie
- Live Feed
- Offene Positionen
- Follower Stats

Klick auf gesperrten Bereich → Overlay:
```
🔒 Copy Trading Feature

Dieser Bereich ist nur mit Copy Trading verfügbar.
Lass deine Trades automatisch ausführen — kein manuelles Trading nötig.

[Mehr erfahren →]
```

### Copy Trading User — Volles Dashboard
Wie jetzt. Alles freigeschaltet.


## Upgrade-Pfade (Upsell)

| Von | Nach | Wo | Aktion |
|-----|------|----|--------|
| Free | Paid Signals | Login-Seite / Telegram-Gruppe | Link zu `/signup/signals` (erkennt bestehenden Account) |
| Free | Copy Trading | Login-Seite / Telegram-Gruppe | Link zu `/signup/copy-trading` |
| Paid Signals | Copy Trading | Dashboard Light (Banner + Lock-Overlays) | Link zu Setup-Wizard (ergänzt bestehenden Account) |

**Wichtig:** Beim Upgrade wird kein neuer Account erstellt. Der bestehende `dashboard_users`-Eintrag bekommt ein neues `product_tier`. Bestehende Daten bleiben erhalten.


## Signal-Bot Integration in Bot-Core

### Wo einhängen?

In `listen.py` — nach dem Parser, parallel zur Execution Engine:

```python
# Bestehend:
events = parser.parse_order_update(data)
for event in events:
    await executor.execute(event)           # Copy Trading (bestehend)
    await signal_bot.process_event(event)   # Signal Bot (NEU)
```

### signal_bot.py — Kernlogik

```python
class SignalBot:
    def __init__(self, db, telegram_bot_token, paid_group_id, free_group_id):
        self.db = db
        self.paid_group_id = paid_group_id
        self.free_group_id = free_group_id
        # Telegram Bot API Client

    async def process_event(self, event: ParsedEvent):
        """Haupteinstieg — wird für jedes Event aufgerufen."""
        signal_type = self._classify(event)
        if not signal_type:
            return

        display_name = self._get_or_create_display_name(event)
        message = self._format_message(signal_type, event, display_name)

        # Immer an Paid senden
        await self._send_to_paid(message)

        # An Free nur wenn Filter erlaubt
        if self._should_send_to_free(signal_type, event):
            await self._send_to_free(message)

        # Log speichern
        self._log_signal(event, message, sent_to_paid=True, sent_to_free=...)

    def _classify(self, event) -> str | None:
        """BotAction → Signal-Typ mappen."""
        mapping = {
            BotAction.OPEN_TRADE: 'open',
            BotAction.TRADE_FILLED: 'open',  # nur wenn neuer Trade
            BotAction.CLOSE_TRADE: 'close',
            BotAction.SCALE_IN: 'scale_in',
            BotAction.SCALE_OUT: 'scale_out',
            BotAction.SET_SL: 'update_sl',
            BotAction.SET_TP: 'update_tp',
            BotAction.CANCEL_SL: 'cancel_sl',
            BotAction.CANCEL_TP: 'cancel_tp',
            BotAction.UPDATE_LEVERAGE: 'leverage',
        }
        return mapping.get(event.action)

    def _get_or_create_display_name(self, event) -> str:
        """Erzeugt 'BTC Short #1' oder holt bestehenden Namen."""
        existing = self.db.get_signal_display_name(event.position_id)
        if existing:
            return existing

        # Nächste Nummer für dieses Symbol+Side
        count = self.db.count_active_signal_names(event.symbol, event.side)
        number = count + 1
        name = f"{event.symbol.replace('USDT','')} {'Long' if event.side == 'BUY' else 'Short'} #{number}"

        self.db.save_signal_display_name(event.position_id, name, event.symbol, event.side, number)
        return name

    def _should_send_to_free(self, signal_type, event) -> bool:
        """Free-Filter: max N Signale pro Woche, nur open+close."""
        if signal_type not in ('open', 'close'):
            return False
        if signal_type == 'close':
            # Nur close senden wenn open auch gesendet wurde
            return self.db.was_signal_sent_to_free(event.position_id, 'open')
        # Limit prüfen
        sent_this_week = self.db.count_free_signals_this_week()
        return sent_this_week < FREE_SIGNALS_PER_WEEK
```


## Dateien die neu erstellt / geändert werden

### Neue Dateien
| Datei | Beschreibung |
|-------|-------------|
| `01 Bot-Core/signal_bot.py` | Signal-Bot Kernlogik |
| `03 Dashboard/MVP 1.0/templates/signup_free.html` | Onboarding Free |
| `03 Dashboard/MVP 1.0/templates/signup_signals.html` | Onboarding Paid Signals |
| `03 Dashboard/MVP 1.0/templates/dashboard_light.html` | Dashboard für Paid Signal User |
| `03 Dashboard/MVP 1.0/routes/signup_routes.py` | Neue Signup-Endpoints |

### Geänderte Dateien
| Datei | Änderung |
|-------|---------|
| `01 Bot-Core/listen.py` | Signal-Bot initialisieren + `process_event()` aufrufen |
| `01 Bot-Core/database.py` | Neue Tabellen + Queries (signal_display_names, signal_log, product_tier) |
| `03 Dashboard/MVP 1.0/app.py` | Neue Routes registrieren |
| `03 Dashboard/MVP 1.0/routes/dashboard_routes.py` | product_tier prüfen → Light vs. Voll |
| `03 Dashboard/MVP 1.0/templates/base.html` | Sidebar-Anpassung je nach Tier |
| `03 Dashboard/MVP 1.0/templates/dashboard.html` | Lock-Overlays für gesperrte Bereiche |

### Neue Env-Variablen (Server `.env`)
```
SIGNAL_PAID_GROUP_ID=-100xxxxxxxxxx
SIGNAL_FREE_GROUP_ID=-100xxxxxxxxxx
FREE_SIGNALS_PER_WEEK=2
FREE_SIGNAL_SYMBOLS=BTCUSDT,ETHUSDT
```


## Offene Fragen

1. **Affiliate-Verifizierung:** Wie prüfen wir ob der User über Max' Link registriert ist? (Max klärt)
2. **Stripe Integration:** Wann bauen wir das? Wird für Paid Signals UND Copy Trading gebraucht.
3. **Telegram-Gruppen:** Wer erstellt die Gruppen und den Bot? Max manuell, dann Bot-Token + Group-IDs in `.env`.
4. **Free-Signal-Auswahl:** Zufällig oder bestimmte Symbols? Oder manuell kuratiert?
