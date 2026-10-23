# Offene Punkte und TODOs

> Zuletzt aktualisiert: 2026-05-15

## Muss gefixt werden (sobald möglich)

### 0. SEPA-Erstkäufe automatisch freischalten (Webhook) — 2026-07-01
- **Problem:** SEPA-Kunden feuern `payment.pending` / `payment_state=payment_pending` (OHNE `active_subscription`, `access_activated_at` leer). Unser Webhook (`webhook_routes.py`) wertet das NICHT als echte Zahlung → Kunde hängt fest, keine Vormerkung, keine Setup-Mail.
- **Folge:** Jeder SEPA-Erstkäufer muss MANUELL freigeschaltet werden (pending_payments-Eintrag + `send_purchase_setup_email`). Bisher betroffen: Tobias Geuss, Fritz Mader, Julian Ellmaier, Helen P.
- **Fix:** `payment.pending` mit `payment_method=sepa` + gültiger Order (Produkt 517561/517562) als echte Zahlung behandeln (vormerken + Setup-Mail).
- **Abwägung (Entscheidung mit Max):** SEPA kann platzen → Zugang ohne Zahlung. Optionen: (a) sofort freischalten + späterer `payment.error`/Rücklastschrift-Webhook sperrt wieder, oder (b) konservativ erst bei `payment.successful`.
- **Bis dahin:** manuell (Konvention siehe Projekt-CLAUDE.md „Manuelles Freischalten").

### 1. Limit Orders über Copy Trading API
- **Problem:** Der `copy-affiliate-order` Endpoint unterstützt keine Limit Orders (Error 600034 "Order not found"). Alle Varianten getestet — konsistent.
- **Workaround (umgesetzt ✅):** Limit Orders werden als `OPEN_TRADE` erkannt, Bot wartet auf `TRADE_FILLED`, dann wird Market Order beim Kunden gespiegelt. Implementiert in `execution.py`.
- **Lösung:** Bei Levex nachfragen (WhatsApp-Nachricht ist raus). Entweder erweitern sie den Endpoint oder es gibt einen anderen API Key-Typ / Endpoint.
- **Sobald gefixt:** `_handle_open_trade` in `execution.py` anpassen — Limit Orders 1:1 als Limit durchreichen statt auf Fill warten.

### 2. SL/TP nachträglich auf Kunden-Positionen setzen
- **Workaround gelöst ✅:** SL/TP wird über den `trading-stop` Endpoint gesetzt. Implementiert in `execution.py`.
- **Trade Management komplett ✅:** SL setzen/ändern/entfernen, TP setzen/ändern/entfernen, Scale In, Partial Close, Full Close — alles implementiert und funktional.

### ~~3. HTTP 405 bei switch-position-mode~~ ✅
- **Gelöst:** Multi-Trade Modus wird beim Laden der Kunden gesetzt. Implementiert in `listen.py`.

## Erledigt ✅

### Restart/Reconciliation ✅
- Erfolgreich getestet. DB-Mapping bleibt persistent. Trade öffnen → Bot stoppen → Neustarten → Trade schließen funktioniert.
- Reconciliation-Methode in `execution.py` implementiert — gleicht offene Positionen beim Start ab.

### Trade Management ✅
- SL setzen/ändern/entfernen ✅
- TP setzen/ändern/entfernen ✅
- Scale In (Nachkauf) ✅
- Partial Close (z.B. 50% schließen) ✅
- Full Close ✅
- Alles über DB-Mapping mit korrekter `position_id`.

### IP-Whitelist Lösung ✅
- Bot läuft auf VPS mit fester IP. IP einmalig gewhitelistet.

### Onboarding-Flow (Phase 1) ✅
- Landingpage → Registrierung → geführtes Setup → Dashboard mit Performance-Tracking
- Setup Wizard mit Schritt-für-Schritt-Anleitung
- Legal Pages (Terms, Privacy, Imprint)
- Aktuell ohne Zahlungsintegration (kommt mit Stripe)

### Mehrere Kunden ✅
- Multi-Customer Support implementiert mit Auto-Reload alle 60 Sekunden.
- Kunden-Daten in DB gespeichert.

### Dashboard MVP ✅
- Equity Chart (Portfolio Performance)
- P&L Tracking
- Live-Preise via WebSocket
- Balance-Anzeige (inkl. Master Balance mit WebSocket-Fallback)
- Follower-Anzahl
- Recent Trades
- Live Feed

### Telegram Notification Bot ✅
- Trade-Alerts bei: Trade eröffnet, Trade geschlossen (mit P&L), SL/TP geändert
- Befehle: `/start`, `/stop`, `/status`

## Muss noch gebaut werden

### Stripe Zahlungsintegration
- **Was:** Einrichtungsgebühr + monatlicher Retainer automatisch abrechnen
- **Umsetzung:** Stripe Checkout für Setup Fee, Stripe Subscriptions für Retainer
- **Abhängigkeit:** Muss vor öffentlichem Launch stehen

### Admin Panel
- **Was:** Übersicht aller Kunden, deren Performance, System-Health
- **Features:** Kunden aktivieren/deaktivieren, Performance pro Kunde, System-Logs, Error-Monitoring

### ~~E-Mail Notifications~~ ✅
- 4 transaktionale Mails implementiert via Google Workspace SMTP: E-Mail-Verifizierung (Double-Opt-In, Blocking), Setup-Willkommen, Passwort-Reset, Pause/Resume-Bestätigung
- DSGVO Consent-Tracking in DB (Zeitstempel für AGB, Datenschutz, Risikohinweis, Marketing)
- **⚠️ Bei Stripe-Integration zusätzlich:** Zahlung bestätigt + Zahlung fehlgeschlagen / Abo läuft aus — NICHT VERGESSEN

### Responsive & Mobile Optimierung 🔴 LAUNCH-BLOCKER
- **Was:** Alle Seiten müssen auf Mobile einwandfrei funktionieren — Login, Register, Setup Wizard, Dashboard, Support, Einstellungen, Legal Pages, E-Mail-Templates
- **Warum:** Kunden werden zu 70%+ über Mobile zugreifen. Ohne Mobile-Optimierung kein öffentlicher Launch.
- **Umfang:** Breakpoints, Touch-Targets, Sidebar-Collapse, Tabellen-Scroll, Chart-Resize, Cookie-Banner, Modals

### Cookie Consent → Analytics
- **Status:** Cookie-Banner ist implementiert, aber Analytics-Integration (z.B. Google Analytics, Plausible) fehlt noch
- **Umsetzung:** Nach Cookie-Akzeptierung Analytics-Script laden

### Video-Inhalte einpflegen
- **Video Intro Popup:** Platzhalter-URL muss durch echtes Intro-Video ersetzt werden
- **Setup Wizard Videos:** Video-Anleitungen in den Setup-Schritten sind Platzhalter — echte Screencasts aufnehmen und einbinden

### Calendly-Links im Setup verifizieren
- **Was:** Setup-Wizard verlinkt auf Calendly für Onboarding-Termin — Links müssen geprüft und ggf. aktualisiert werden

### Support Bot (Telegram) testen
- **Was:** Telegram Support Bot ist gebaut, muss aber End-to-End getestet werden mit echten Kunden-Anfragen

## Nice-to-have / Später

### Exchange Symbol-Configs dynamisch laden
- Min Order Size, Tick Size, Lot Size pro Symbol aus der Exchange API laden statt hardcoded Defaults.

### Skalierungs-Ideen
- Siehe `09 Iteration Logs/(C) Skalierungs-Ideen fuer spaeter.md`

### Dashboard MVP 2.0
- **Equity Chart historisch:** Braucht `daily_snapshots` Tabelle für historische P&L-Daten pro Tag
- **Master Hero Mini-Chart:** Gleiche Datenquelle wie Equity Chart
- **R-Multiple bei Trades:** Initiales Risiko (SL-Distanz bei Eröffnung) müsste bei Trade-Open gespeichert werden
- **Sync Genauigkeit / Latenz:** Zeitdifferenz zwischen Master-Event und Customer-Execution loggen
- **Stub-Seiten ausbauen:** Positionen (Detail-View), Wallet (Deposit/Withdraw-History), Einstellungen (Profil, Notifications), Support (FAQ + Tickets)

### Signale-Reiter im Dashboard
- Neuer Nav-Punkt "Signale" im Dashboard.
- Führt auf Unterseite wo sich Kunden für Trade-Alerts registrieren können (z.B. Telegram oder Push).
- Quasi der bestehende Telegram-Alert-Bot, aber als Self-Service für Kunden statt nur fürs Team.
