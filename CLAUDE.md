# FCT Copytrading
> ↩ [[CLAUDE|Life OS]] · [[FCT/CLAUDE|FCT]]

**Einstieg:** [[(C) Wissensbasis Copytrading]] (Fakten, Fallen, Kündigungen) · [[(C) Logbuch Copytrading]] (Protokoll) · Gesamtsystem → `FCT OS/(C) Systemlandkarte FCT.md`

> 🧹 **Vor jedem Aufräumen/Löschen/Umbenennen in diesem Projektordner:** [[(C) Aufräumen — Schutzliste]] lesen. Hier liegt Live-Code eines produktiven Systems mit zahlenden Kunden — dort steht, was Tabu ist und wo der echte Ballast liegt.

Ein Bot der die Trades von Max (Trader/Personalbrand) in Echtzeit auf die Accounts zahlender Nutzer spiegelt — inklusive komplettem Trade Management (SL, TP, Nachskalierung, Schließung). Die Positionsgrößen werden automatisch auf die jeweilige Account-Größe des Nutzers umgerechnet. Wird als Produkt der Firma verkauft (Einrichtungsgebühr + monatlicher Retainer).


## Claudes Rolle

Claude ist Co-Entwickler für den gesamten Copy Trading Bot. Konkret:

- Architektur planen (Trade-Mirroring, Account-Verknüpfung, Skalierungslogik)
- Bot-Core entwickeln (Trades kopieren, Echtzeit Trade Management, proportionale Skalierung)
- User-System bauen (Registrierung, Affiliate-Link, Account-Verknüpfung)
- Dashboard entwickeln (Profit-Tracking, Trade-Übersicht für Nutzer)
- Testing und Launch begleiten
- Sicherstellen, dass das System zuverlässig und sicher ist — hier geht es um echtes Geld anderer Leute

Wenn eine Session abdriftet ohne sich Richtung fertigem Produkt zu bewegen, mich zurückschubsen: "Was ist der nächste konkrete Schritt damit der Copy Trading Bot live geht?"


## Tech-Stack

| Komponente | Technologie |
|-----------|------------|
| Sprache | Python 3.11+ (asyncio) |
| Datenbank | SQLite (WAL Mode, shared zwischen Bot + Dashboard) |
| Dashboard | FastAPI + Jinja2 Templates |
| HTTP Client | aiohttp (REST API) |
| WebSocket | websockets (Levex Stream) |
| Frontend | Vanilla JS + Chart.js |
| Hosting | Hetzner VPS (CX22, Ubuntu) |
| Services | 2× systemd (copy-trading-bot + copy-trading-dashboard) |
| Alerts | Telegram Bot API |
| Exchange | Levex (Copy Trading API) |


## Architektur-Überblick

```
Levex WebSocket ──→ listen.py ──→ parser.py ──→ execution.py ──→ REST API ──→ Kunden-Accounts
                                       │                ↓
                                       │           database.py (SQLite)
                                       │                ↓
                                       │      Dashboard (FastAPI) ──→ Browser
                                       │
                                       └──→ signal_bot.py ──→ Telegram Paid Gruppe (alle Signale)
                                                    └──→ Telegram Free Gruppe (gefiltert)
```

**Bot-Core** (`01 Bot-Core/`): WebSocket Listener → Event Parser (14 Actions) → Execution Engine → REST Orders auf Kunden-Accounts. Pro Kunde eine separate WebSocket-Verbindung für Live-Balance-Tracking.

**Dashboard** (`03 Dashboard/MVP 1.0/`): FastAPI-App mit Login, Registrierung, 3-Schritt Setup-Wizard, Live-Dashboard (Equity Chart, Positionen, P&L), Support, Einstellungen, Legal Pages. Frontend pollt `/api/live` alle 10 Sekunden. Zwei Product-Tiers: Paid Signals (Dashboard Light), Copy Trading (volles Dashboard).

**Signal Bot** (`01 Bot-Core/signal_bot.py`): Hängt sich an den Parser-Event-Stream, formatiert Signale und postet sie in Telegram-Gruppen (Paid: alle Events inkl. Management). Zusätzlich Marketing-Channel: profitable Trades (>8%) + wöchentliche/monatliche Summaries in Max' allgemeine Community.


## Was ist implementiert

### Bot-Core ✅
- [x] WebSocket Listener mit Auto-Reconnect (Exponential Backoff 1s→30s)
- [x] Event Parser (14 BotActions: Open, Close, Scale-In/Out, SL/TP, Leverage, Margin, Amend, Cancel, Rename)
- [x] Execution Engine mit paralleler Ausführung auf allen Kunden
- [x] Proportionale Skalierung (customer_qty = master_qty × customer_balance / master_balance)
- [x] Lot/Tick-Rounding + Minimum-Qty-Fallback
- [x] Position Mapping (Master → Kunde, persistent in DB)
- [x] Reconciliation bei Bot-Neustart (orphaned Positions schließen)
- [x] Per-Kunde WebSocket für Live-Balance-Tracking
- [x] Auto-Reload neuer Kunden alle 60 Sekunden
- [x] Telegram Alerts (Trade Open/Close, Errors, Reconnects, /status)
- [x] Signal Bot für Telegram-Gruppen (Paid: alle Signale + Management)
- [x] Marketing Channel (profitable Closes >8%, Wochen-/Monats-Summaries, CTA zur Paid-Gruppe)
- [x] Trade-Nummerierung für Signale ("BTC Short #1", "BTC Short #2")
- [x] Multi-Trade Mode (mehrere Positionen pro Symbol)
- [x] Pause/Resume pro Kunde (nur Opens blockiert, Closes/SL weiter aktiv)

### Dashboard ✅
- [x] Login / Registrierung (mit Passwort-Toggle)
- [x] Rechtliche Checkboxen (AGB, Datenschutz, Risikohinweis = Pflicht; Marketing = optional)
- [x] 3-Schritt Setup-Wizard (LeveX Account → Einzahlung → API Keys)
- [x] API Key Validierung (REST-Check)
- [x] Balance-Check via WebSocket (Min. 1.000 USDT Futures-Guthaben)
- [x] Live Dashboard (Equity Chart, Positionen, unrealisierter P&L, Balance)
- [x] Trade-Historie + Recent Trades
- [x] Live Feed (Trade-Events)
- [x] Follower Count + Sync Stats
- [x] Master Performance (Return %, YTD, Max Drawdown)
- [x] Copy Trading Pause/Resume mit Bestätigungs-Modal
- [x] Support-Seite (Telegram Bot + Calendly + E-Mail)
- [x] Einstellungen-Seite
- [x] Disclaimer-Popup (pro Session)
- [x] Video-Intro-Popup (einmalig nach Setup via `?welcome=1`)
- [x] Cookie-Banner (localStorage, "Nur notwendige" / "Alle akzeptieren")
- [x] Legal Pages (Impressum, AGB, Datenschutz, Risikohinweis)
- [x] Legal Footer auf allen Seiten
- [x] Deploy-Script (deploy-dashboard.sh)

### Signal-Produkte ✅
- [x] 2 Produkt-Tiers: Paid Signals, Copy Trading (Free Tier entfernt — 2026-05-29)
- [x] Eigene Onboarding-Flows pro Tier (`/signup/signals`, `/signup/copytrading`)
- [x] Dashboard Light für Paid Signal User (Telegram-Link, Support, Upsell, gesperrte Bereiche mit Lock)
- [x] Sidebar passt sich an product_tier an (weniger Items für Signal-User)
- [x] Upgrade-Pfad: Paid Signals → Copy Trading (ein Account)
- [x] Signal Bot (`signal_bot.py`) — postet Events als formatierte Signale in Paid Telegram-Gruppe
- [x] Marketing Channel — profitable Closes (>8%) + Wochen-/Monats-Summaries in Max' Community Channel
- [x] 10 Nachrichtentypen: Open, Close, SL/TP Update, SL/TP Cancel, Scale-In, Scale-Out, Leverage, Margin
- [x] Debounce-Batching (500ms) — SL/TP werden in Open-Nachricht integriert, CANCEL bei Close unterdrückt
- [x] Deutsche Zahlenformatierung (76.840,7) + Position-P&L (Kursänderung × Hebel)
- [x] Scheduled Summaries: Sonntags Wochen-Performance, Monatsende Monats-Performance

### Was noch fehlt
- [ ] **Security Hardening** — 12/14 CRITICAL+HIGH erledigt. Noch offen: API Key Encryption (#2), lokale .env (#3). Audit: → [[10 Security/(C) Security Audit]]
- [ ] **Stripe Payment** — Für Paid Signals (~100€/mo) UND Copy Trading (500€ Setup + 300€/mo). Bei Integration auch Mails: Zahlung bestätigt + Zahlung fehlgeschlagen
- [x] **Telegram-Gruppen erstellt** — Bot-Token + Group-IDs für Paid Signal-Gruppe + Marketing Channel in `.env` konfiguriert
- [x] **Affiliate-Verifizierung (UID)** — Live. `affiliate_service.py` prüft UID gegen Levex Affiliate API (paginiert, 5min Cache). Keys: `AFFILIATE_API_KEY`, `AFFILIATE_API_SECRET` auf Server konfiguriert.
- [ ] **Admin Panel** — Kunden verwalten, Performance überwachen
- [x] **E-Mail Notifications** — 5 transaktionale Mails (Verifizierung, Willkommen, Passwort-Reset, Pause, Resume) via Google Workspace SMTP. Double-Opt-In, DSGVO Consent-Tracking in DB.
- [x] **Responsive & Mobile** — Alle Seiten mobil-optimiert (Hamburger → Fullscreen-Overlay-Menü, iOS Safari Fixes, 768px/480px Breakpoints). E-Mail-Templates responsive.
- [ ] **Video-Inhalte** — Intro-Video + Anleitungsvideos für Setup-Schritte (aktuell Platzhalter)
- [ ] **Analytics Integration** — Cookie-Banner steht, Analytics-Script noch nicht eingebunden
- [ ] **Dashboard MVP 2.0** — Weitere Optimierungen (R-Multiple Anzeige, Latenz-Tracking im UI)


## Prozess

1. ~~**Architektur planen**~~ ✅
2. ~~**Bot-Core entwickeln**~~ ✅
3. **User-System bauen** — Phase 1 (Registrierung + Setup) ✅ | Phase 2 (Stripe) ausstehend
4. ~~**Dashboard bauen**~~ ✅ (MVP 1.0)
5. **Testen** — Intern läuft, Beta-User als nächstes
6. **Live-Launch** — Nach Stripe + Video-Inhalte + Beta-Test


## Beteiligte Personen

- **Max (Steinauer)** — Der Trader. Seine Trades werden kopiert. Er ist die Personalbrand und das Gesicht des Produkts.


## Ordnerstruktur

```
Copy Trading Bot/
├── CLAUDE.md                  ← Du bist hier
├── COMMANDS.md                ← Alle Server- und Management-Befehle (copy-paste ready)
├── 00 Architektur & Planung/  ← Systemarchitektur, API-Docs, Onboarding-Flow
│   ├── (C) Systemarchitektur.md
│   ├── (C) Onboarding Flow — Bauplan.md
│   ├── (C) Levex API Reference.md
│   └── (C) Levex Perpetual REST API.md
├── 01 Bot-Core/               ← Python Source Code (listen.py, parser.py, execution.py, ...)
├── 03 Dashboard/              ← FastAPI Dashboard (MVP 1.0)
│   └── MVP 1.0/
│       ├── app.py             ← Entry Point
│       ├── routes/            ← auth, dashboard, api, legal
│       ├── templates/         ← Jinja2 HTML
│       ├── static/            ← CSS, JS, Logos
│       └── deploy-dashboard.sh
├── 04 Landingpage/            ← Verkaufsseite (statisches HTML, gehostet auf IONOS Webspace)
│   └── Landingapge/           ← Production-ready Ordner (direkt auf Webspace deployen)
│       ├── index.html         ← Hauptseite
│       ├── theme.css          ← Shared Styles
│       ├── agb/datenschutz/impressum/risikohinweis.html
│       └── Assets/            ← Bilder + Logos
├── 05 Live & Launch/          ← Server Setup, Deployment-Anleitung
├── 06 Attachments/            ← Screenshots, Referenzbilder (Signal-Nachrichten etc.)
├── 07 System/                 ← Support Bot, Scripts
├── 09 Iteration Logs/         ← TODOs, Skalierungs-Ideen, Offene Punkte
├── 10 Security/               ← Security Audit, Hardening-Dokumentation
```


## Server & Deployment

| | Details |
|--|--------|
| Server | Hetzner VPS — 178.105.135.197 |
| SSH | `ssh root@178.105.135.197` |
| Bot-Service | `copy-trading-bot` (systemd) |
| Dashboard-Service | `copy-trading-dashboard` (Port 8443) |
| Dashboard-URL | `https://dashboard.firstclass-trading.com` |
| Landingpage-URL | `https://copytrading.firstclass-trading.com` (IONOS Webspace) |
| DB | `/home/botuser/copy-trading-bot/copy_trading.db` |
| Bot-Pfad | `/home/botuser/copy-trading-bot/` |
| Dashboard-Pfad | `/home/botuser/dashboard/` |

> ### 🔑 Anmeldung — wer bist du?
>
> | Wer arbeitet | Befehl | Rechte |
> |---|---|---|
> | **Max** | `ssh root@<server-ip>` | direkt root |
> | **Mitarbeiter** (Luis u. a.) | `ssh luis@<server-ip>` | eigener Benutzer, root-Rechte über **`sudo`** davor |
>
> **Überall in dieser Datei steht `root@…` — das ist Max' Weg.** Arbeitest du auf dem
> Rechner eines Mitarbeiters, setze stattdessen dessen Benutzernamen ein und stelle
> Befehlen, die root brauchen, `sudo` voran. Beispiel:
> `sudo -u postgres psql -d fct_os` statt `sudo -u postgres psql` als root.
>
> **Diagnose:** Kommt bei `ssh root@…` ein **`Permission denied (publickey)`**, bist du
> auf einem Mitarbeiter-Rechner → mit `luis@` erneut versuchen. Der Zugang ist dann
> nicht kaputt, es ist nur der falsche Benutzername.
>
> 🔴 **NIEMALS einen Schlüssel in `/root/.ssh/authorized_keys` eintragen**, auch nicht
> anfügend. Max hat dort genau einen Schlüssel; geht der verloren, ist der Server nur
> noch über die Hetzner-Konsole erreichbar. Mitarbeiter-Zugänge sind immer **additiv**
> (eigener Benutzer + eigene `authorized_keys` + eigene Datei unter `/etc/sudoers.d/`).


**Domain-Setup:**
- `copytrading.firstclass-trading.com` → IONOS Webspace (217.160.0.194) — Landingpage (statisches HTML)
- `dashboard.firstclass-trading.com` → Hetzner VPS (178.105.135.197) — Dashboard (FastAPI)
- Nginx auf VPS bedient nur noch `dashboard.firstclass-trading.com`
- SSL: IONOS Wildcard (Sectigo) für Landingpage, Let's Encrypt (Certbot) für Dashboard

**Quick-Deploy Dashboard:**
```bash
cd "03 Dashboard/MVP 1.0" && ./deploy-dashboard.sh 178.105.135.197
```

Vollständige Befehls-Referenz: → [[COMMANDS]]


## Regeln & Konventionen

- **`(C)` Prefix** — Von Claude erstellte Dateien werden mit `(C)` gekennzeichnet, damit klar ist, dass sie KI-generiert sind.
- **Bearbeitungsregel** — Bevor eine Datei ohne `(C)` Prefix bearbeitet wird, erst um Erlaubnis fragen.
- **Skills** — Alle wiederverwendbaren Scripts/Automationen werden als Markdown-Dateien im Skills-Ordner gespeichert, NICHT als Claude Code Skills.
- **Graph-Verlinkung** — Wenn eine neue Datei in diesem Projekt erstellt wird, IMMER einen Wiki-Link im "Verknüpfte Dateien" Abschnitt am Ende dieses CLAUDE.md eintragen.
- **Sicherheit** — Keine API-Keys, Secrets oder Zugangsdaten in Dateien speichern. Immer Umgebungsvariablen nutzen. Hier geht es um echtes Geld anderer Leute — Sicherheit ist nicht optional.
- **Security Hardening** — Vollständiger Audit durchgeführt (2026-05-18). Alle Änderungen und offenen Punkte dokumentiert in → [[10 Security/(C) Security Audit]]. Bei Code-Änderungen immer beachten:
  - Cookies immer mit `secure=True, httponly=True, samesite="strict"`
  - Kein `.innerHTML` mit User-/API-Daten → `textContent` oder DOM-Elemente
  - Alle POST-Endpoints brauchen CSRF-Token
  - Sensitive Felder (API Keys/Secrets) verschlüsselt speichern (Fernet)
  - Keine sensitive Daten in Logs (API Responses, Keys, Tokens)
  - Rate Limiting auf alle Auth-Endpoints
  - `require_auth()` muss `email_verified` prüfen
  - Passwort-Reset muss alle Sessions invalidieren


## Aktueller Status

> **Zuletzt aktualisiert:** 2026-07-06 (Weekly Review — Umsatz-Meilenstein)
> **Status:** 🚀 **LIVE seit 28.06. — ~250K Umsatz in Woche 1.** Größter Erfolg bisher. Firmenumsatz 30T dadurch auf 284.997,27€ (Cash Collected 83.307,51€). Signal-Gruppe live, echte Kunden kaufen (Tier `paid_signals`). Server auf CPX32 hochgestuft, burst-fest. SEPA-Freischaltung gefixt & live (04.07.). Phase 2 (automatisches Copy Trading) folgt später. Details siehe "Laufender Kontext" unten.

### Was live ist ✅
- Bot-Core mit Copy Trading + Signal Bot (15 Python-Dateien)
- Dashboard mit 2 Tier-Levels (Paid Signals → Dashboard Light, Copy Trading → volles Dashboard)
- **Landingpage live** (2026-06-12) — `copytrading.firstclass-trading.com` (IONOS Webspace)
  - Ablefy Checkout-Links mit `plan_id` für monatlich (610907, 99,95€) und jährlich (610909, 79,95€)
  - Login-Button → `dashboard.firstclass-trading.com/login`
- **Dashboard live** (2026-06-12) — `dashboard.firstclass-trading.com` (Hetzner VPS, Nginx + Certbot SSL)
- **Payment-First Onboarding** (2026-06-10) — Vereinfachter Flow:
  - Landingpage → Ablefy Checkout → `/welcome?payer_email={email}` (Passwort + UID) → `/welcome/done` (Telegram-Link + Dashboard)
  - Alte Signup-Routes (`/signup/signals`, `/payment`, `/setup/premium`) redirecten auf neuen Flow
  - Webhook-Endpoint `/webhooks/ablefy` empfängt Payment/Refund/Order-State Events
  - Produkt-Filtering: Nur unsere 2 Produkte (517561=Signale, 517562=Copy Trading) werden verarbeitet
  - Pending Payments: Zahlung vor Account-Erstellung wird vorgemerkt + Name aus Webhook extrahiert
  - Post-Purchase Setup-Mail falls User Browser schließt bevor Account erstellt
  - Ablefy "Parameter übergeben" leitet `payer_email` automatisch weiter
- Telegram Paid Signal-Gruppe konfiguriert (FCT | Krypto Signale PREMIUM)
- Marketing Channel (`-1001252595461`): Profitable Closes >8% + Wochen-/Monats-Summaries + CTA zur Paid-Gruppe
- Signal Bot: 10 Nachrichtentypen (Open, Close, SL/TP Update/Cancel, Scale-In/Out, Leverage, Margin)
- Signal-Formate: Deutsche Zahlenformatierung, Position-P&L (Kurs × Hebel), Debounce-Batching (500ms)
- Mobile/Responsive ✅, E-Mails ✅, Security Audit (12/14 CRITICAL+HIGH erledigt)

### Was vor Launch noch fehlt
1. **E-Mails pro Onboarding-Funnel anpassen** — Aktuell bekommt jeder Tier die gleiche Willkommens-/Verifizierungs-Mail. Muss pro Tier (Paid Signals, Copy Trading) individuell angepasst werden: anderer Betreff, anderer Inhalt, andere CTAs. Wichtig: (a) Nach Onboarding-Abschluss muss eine Mail mit dem personalisierten Telegram-Invite-Link kommen. (b) Die Verifizierungs-Mail muss tier-abhängig sein (Paid Signals → `/setup/premium`, Copy Trading → `/setup/copytrading`).
2. **Affiliate-Verifizierung (UID)** — LAUNCH-BLOCKER. UID-Feld ist in `/setup/premium` eingebaut (wird gespeichert, auto-fill wenn schon vorhanden). API-Check fehlt noch. Levex API-Doku erhalten (Google Doc). Endpoint: `GET /api/service-affiliate/affiliate/client/summary` (paginiert, `pageSize` max 500, `pageNumber` ab 1). Response enthält `clientId` pro referriertem User — das ist die UID die der Kunde eingibt. Auth: HMAC-SHA256 Signing (gleiche Logik wie Bot-Core). **WICHTIG: Affiliate-Account ist ein ANDERER Account als der Master-Trading-Account.** Braucht eigene API Keys (`AFFILIATE_API_KEY`, `AFFILIATE_API_SECRET` in `.env`). Max muss diese Keys bei Levex für den Affiliate-Account erstellen. Nur für Paid Signals — Copy Trading braucht keine UID (API Keys reichen als Verknüpfung). Zweiter Endpoint verfügbar: `GET /api/service-affiliate/commission/history` (Commission Records, max 90 Tage Range).
3. **Telegram Invite Links** — Nicht einfach statische Links, sondern **personalisierte Einmal-Links** via `createChatInviteLink` (member_limit=1). Werden nach Onboarding generiert, in DB gespeichert, auf Done-Seite angezeigt UND per Mail verschickt. Aktuell noch Platzhalter `href="#"` in `dashboard_signals.html`.
4. **Telegram Auto-Kick (nur Paid Gruppe)** — Cronjob der regelmäßig prüft ob Paid-Mitglieder noch aktives Abo haben. Wenn Stripe-Abo cancelled/expired → `banChatMember` + `unbanChatMember` (Kick ohne permanenten Ban). Optional vorher DM mit Hinweis. Braucht: `telegram_user_id` in DB (Spalte existiert), Bot als Admin in Gruppe, Stripe Webhook für Abo-Status.
5. ~~**🔧 FIX NÖTIG: SEPA-Erstkäufe automatisch freischalten.**~~ ✅ **GEFIXT & LIVE (2026-07-04).** Entscheidung Max = **Option A** (sofort freischalten, Rücklastschrift sperrt). In `webhook_routes.py` deployed: (1) `payment.pending`/`order.subscription.pending` mit `payment_state=payment_pending` + `payment_method=sepa` + unser Produkt (517561/517562) → wird als echte Zahlung behandelt (Vormerkung + Setup-Mail). (2) Neuer `_handle_payment_failed`: `payment_state=payment_chargebacked` bzw. `chargeback.*`-Events → offene Vormerkung löschen + registrierten User deaktivieren + Telegram-Kick. `payment.error`/`payment_not_completed` bleiben bewusst ignoriert (transiente Kartenablehnungen — kein Kollateralschaden). Payload-Struktur vorab an echten `webhook_logs` verifiziert. 11 historisch festhängende SEPA-Kunden per Backfill nachgezogen (Vormerkung + Setup-Mail). **Offen/Merker:** SEPA-Bounce-Sperrpfad in Prod noch nicht durch echtes Chargeback-Event getriggert gesehen — beim nächsten echten Chargeback kurz prüfen (Log `[WEBHOOK] chargeback: User gesperrt`).
6. **Signal Bot + Marketing Channel testen** — Erster echter Trade → prüfen ob Signale in Paid-Gruppe ankommen UND profitable Closes im Marketing Channel landen
7. **Marketing Channel deployen** — `MARKETING_CHANNEL_ID=-1001252595461` in `.env` auf Server setzen, Bot als Admin im Channel hinzufügen, Bot-Core redeployen
8. ~~**Stripe Payment**~~ → Ersetzt durch **Ablefy** ✅ — Integration live, Webhooks funktionieren. **Max muss noch:** Ablefy-Produkte fertig konfigurieren (Preise, Bezahlseite, Beschreibungen, Bilder)
9. ~~**Lokale .env löschen**~~ ✅ (2026-06-15) — API Keys rotieren noch offen (Max manuell bei Levex)
10. **API Keys verschlüsseln (Fernet)** — Nach neuen Keys
11. ~~Richtigen Master Account verknüpfen~~ ✅
12. **End-to-End Check** — Ein echter Trade durch das ganze System
13. **Video-Inhalte** — Intro-Video + Anleitungsvideos (aktuell Platzhalter)
14. **Analytics Integration** — Cookie-Banner steht, Script noch nicht eingebunden

### Improvements (nach Launch)
- **Vorteils-Seite vor Stripe Checkout** — Wenn eingeloggter User upgradet (Paid→Copy Trading), nicht direkt in den Checkout schicken, sondern erst eine kurze Seite mit den Vorteilen des neuen Tiers zeigen (Social Proof, Features, Preis). Dann CTA zum Checkout. Reduziert Checkout-Abbrüche.
- **Bumper Offer für Launch-Event** — Zwischenseite nach dem Klick auf "Launch-Angebot sichern" (vor dem Ablefy-Checkout). Einmaliges Zusatzangebot (z.B. 1:1 Setup-Call, exklusive Inhalte, verlängerte Testphase o.Ä.) das nur beim Launch verfügbar ist. Erhöht den durchschnittlichen Warenkorbwert. → Muss als eigene HTML-Seite gebaut werden, leitet nach Annahme/Ablehnung zum Checkout weiter.


## Regeln für Kontextpflege

- **Live-Update-Regel:** Nach jeder relevanten Änderung (neues Feature deployed, Bug gefixt, Entscheidung getroffen, Architektur geändert) **sofort**: (1) Eintrag oben ins [[(C) Logbuch Copytrading]], (2) „Zuletzt aktualisiert"-Zeile hier anpassen, (3) dauerhafte Erkenntnis → [[(C) Wissensbasis Copytrading]], (4) neuer Dienst/Domain → [[../FCT OS/(C) Systemlandkarte FCT|Systemlandkarte]] im FCT-OS-Projekt. Nicht warten bis die Session endet — der Chat kann jederzeit abbrechen.
- **Was ist "relevant"?** Alles was eine neue Session wissen müsste: Was wurde deployed, was wurde geändert, welche Entscheidungen wurden getroffen, was ist noch offen.
- **Diese Datei bleibt kurz:** Rolle, Stack, Server, Regeln, offene Punkte. Protokolle und Fakten-Sammlungen gehören ins Logbuch bzw. die Wissensbasis.
- **Kontextdatei ist Wahrheit:** Neue Sessions starten mit CLAUDE.md → dort steht alles was die nächste Session wissen muss.


## Laufender Kontext

> **Zuletzt aktualisiert:** 2026-10-23 („Viktor Lachner" von Max manuell entfernt — **keinem Account zuordenbar, zweiter Fall nach BND**) · *zuvor 2026-10-22 (Kündigung Matthias Rößler erfasst — Entzug 02.11.2026, Zeile id 23) · *zuvor 2026-10-21 (Hans-Peter Walter sofort entfernt · Thomas Brunzel **+ 2 Familien-Zugänge** und Semir Hodzic für 28.06.2027 erfasst · **✅ KORREKTUR: fehlendes Ablefy-Event ist bei Plan 610909 mit Laufzeitende NORMAL — meine Warnung war ein Fehlalarm**) · *zuvor 2026-10-20 (Kündigung Martin Nimsky erfasst — Entzug 28.06.2027 im Ablauf-Job, **Jahresabo Einmalzahlung 876,95 € → bewusst kein Sofort-Kick**) · *zuvor 2026-10-15 (Sofort-Kicks „Mike" + „Captainperalta" — beide ohne Sperre · **⚠️ Captainperalta: SEPA-Rate vor 3 Tagen gezahlt, 22 Tage Restlaufzeit → erhöhtes Rücklastschrift-Risiko**) · *zuvor „Mike"/@Mikefit — ohne Sperre, Ablefy war bereits gekündigt) · *zuvor 2026-10-13 (Sofort-Kick „Oma Gurke"/Björn Weber — Kulanz ohne Sperre, Ablefy war bereits gekündigt) · *zuvor 2026-10-06 (Sofort-Kick „Endorphine"/Volker Gedan — Kulanz ohne Sperre · **⚠️ MAX MUSS BIS 29.10. IN ABLEFY KÜNDIGEN, sonst holt die Auto-Reaktivierung ihn zurück**) · *zuvor 2026-10-05 (Sofort-Kick „Lothar"/Christina Liebing — ohne Dauersperre, **⚠️ 23 Tage Restlaufzeit bezahlt** · zuvor Sofort-Ban „BND" — Moderationsfall, permanent in Main + Scalp · **⚠️ OFFEN: E-Mail fehlt → Abo läuft weiter, keine Blocklist möglich**) · *zuvor 2026-09-30 (Kündigung Siegfried Honold erfasst — Zugangsentzug 01.10., **erster Fall über den konsolidierten Ablauf-Job statt eigenem Timer**) · *zuvor 2026-09-28 (Sofort-Kick Lea Giesen erledigt, ohne Dauer-Sperre · **⚠️ HEUTE: Vergleich Dry-Run vs. alte Timer für Brendler + Landert — Entscheidung über Umstellung auf den konsolidierten Ablauf-Job**) · *zuvor 2026-09-11 (Kündigung Giorgos Gertsos → Kick 18.09. gescheduled · Auto-Reaktivierung zahlender Rückkehrer LIVE ✅, alle Kick-Timer mit Zahlungs-Check. Offen: Part 2 REVOKE/Ablauf-Job, Webhook-Absicherung, Luca-Entscheidung bis ~29.09., LeveX 600034)*

### Aktuelle Situation
- **🚀 SIGNAL-GRUPPE IST LIVE GEGANGEN (2026-06-28)** — echte zahlende Kunden kaufen über Ablefy, kommen in die Paid-Telegram-Gruppe "FCT | Copy Trading" (`-1003888563475`). Bot postet Signale live, ist Admin in der Gruppe.
- **Launch-Angebot:** 77,77 €/Mo (Jahresabo) statt 99,95 €. Endet **01.07.2026 22:00 UTC** (= 02.07. 02:00 Dubai). Timer-Enddatum in der Event-Landingpage (`EVENT_END`).
- **Phase 1 = Signale** (alle Kunden Tier `paid_signals`, 0 Copy-Trading-Kunden, 0 mit API-Keys). Phase 2 (automatisches Copy Trading) kommt später.
- **Server auf CPX32 hochgestuft** (4 vCPU / 8 GB) für den Launch-Burst — reversibel ("nur CPU+RAM", Disk blieb 80 GB). Nach dem Launch-WE wieder auf CPX22 möglich.
- **Master-Account hat aktuell 2 offene BTC-Shorts** (#1 "The Big Short" Entry 78.034 / 300x, + #2). Beide vom Bot getrackt mit SL/TP (POS-CHECK-Log beim Start).
- Marketing Channel: weiterhin NICHT AKTIV (nicht in `.env`).

### Heute deployed (2026-06-28) — alle live & verifiziert
- **Burst-Festigkeit:** 3 Uvicorn-Worker · non-blocking Mail (`send_async` → Threadpool) · SQLite `busy_timeout=5000` · Telegram-Invite lazy (im verify-email-Schritt + /welcome/done, nicht mehr im POST)
- **Dashboard + Bot teilen eine `.env`** via `EnvironmentFile=/home/botuser/copy-trading-bot/.env` (eine Quelle der Wahrheit — Deploys überschreiben Secrets nicht mehr)
- **UID-/Affiliate-Prüfung ENTFERNT** aus dem Signal-Funnel (welcome) — Kunden zahlen, bekommen direkt Zugang
- **Telefonnummer = Pflichtfeld** im Onboarding (Spalte `dashboard_users.phone`) + interner Endpoint `GET /api/internal/phone?email=` (Header `X-Internal-Token`, in `.env`)
- **Danke-Video (Wistia)** in `/welcome/done` + CSP um Wistia-Domains erweitert (sonst geblockt)
- **Signal-Bot Fixes:** (a) Scale-In-Doppelnachricht (Market-Nachkauf wurde als neuer Trade + Skalierung gepostet), (b) SL/TP-Close-Detection via `_last_sl_tp` im Parser (getroffener SL/TP wurde als "manuell" angezeigt, weil die Order beim Trigger entfernt wird), (c) **Phantom-Reconciliation** der `signal_display_names` beim Snapshot (verwaiste aktive Namen werden gegen echte Positionen deaktiviert)
- **"Einsatz: X % des Kontos"-Zeile** in Open/Limit/Scale-In-Signalen (Margin/Account = wie viel % Follower reingehen können)
- **Master-UID korrigiert** in `.env`: `LEVEX_MASTER_UID` 1158206 → **1080129** (war veraltet, nur geloggt)
- **Webhook SEPA-Fix (wichtig!):** (a) `_extract_product_id`-Bug gefixt (lieferte bei verschachteltem `product:{product_id}` den String der Dict statt der ID → Produkt unbekannt → Kunde fiel durchs Raster), (b) SEPA-Logik: `payment.pending`+`active_subscription` triggert jetzt Onboarding (SEPA feuert kein `payment.successful` sofort), (c) `payment_not_completed`/`payment.error` werden ignoriert, (d) Idempotenz (Mail nur einmal trotz mehrerer Events/Kauf)
- **E-Mail Button-Fix:** Plain-Text behält URLs, Button mit solidem `bgcolor` (web.de/gmx strippen Gradients), sichtbarer Fallback-Link in Setup-Mail
- **Event-Landingpage Stats** auf echte Zahlen umgestellt: **Win-Rate 76,8 % als Hero** (Rendite raus), Profit-Faktor 3,08, 152 Trades, −17,2 % Drawdown, +36.538 USDT (6 Mo). → **Max muss die `index.html` aus dem Event-Landingpage-Ordner neu auf IONOS hochladen.**

> **⏳ TESTIMONIALS WIEDER EINBLENDEN (MERKER):** Der Kundenbewertungs-Block (Zitate "Was unsere Mitglieder sagen") in der Event-Landingpage `index.html` wurde am 2026-06-28 **temporär auskommentiert** (Section `class="testi"`, zwischen TESTIMONIALS- und PRICING-Kommentar). **Muss später wieder rein** — einfach den `<!-- ... -->` um den Block entfernen. Grund: von Max gewünscht.

### Offene Punkte / Max muss noch
1. **Event-Landingpage neu auf IONOS hochladen** (Stats-Update + 140+-Zahl + ausgeblendete Testimonials stecken nur lokal in der Datei)
2. **Erste Bestellung von Bernd Sikmann (Order 16516563) bei Ablefy stornieren** (Doppelkauf — die zweite 16516884 bleibt)
3. **Mail-Zustellbarkeit:** läuft über Google Workspace SMTP (`noreply@firstclass-trading.com`). SPF/DKIM/DMARC alle korrekt gesetzt — ABER strenge Provider (web.de, yahoo, gmx, aol) filtern in **Spam** (neue Domain + Launch-Burst). Kunden auf Spam-Ordner hinweisen. **Künftiger Fix: dedizierter Dienst (Brevo/Postmark).**
4. **Verifizierungs-Mail landet bei strengen Providern im Spam** → steckengebliebene Kunden ggf. manuell verifizieren (email_verified=1 setzen + Telegram-Link generieren). Schon manuell freigeschaltet/gefixt: Yuk Lin Sutter Lau, Bernd, Luca, d.born1.
5. **Mail-Logging fixen** — `email_service`-Logger schreibt nicht nach journald (`[EMAIL] Gesendet/Fehler` unsichtbar). Versand klappt trotzdem, aber wir sind blind. Niedrige Prio.
6. **MIN_DEPOSIT_USDT=0** auf Server — irrelevant für Signal-Phase (keine API-Keys), aber VOR Copy-Trading-Phase auf 1000 zurück.
7. Telegram Auto-Kick bei abgelaufenem Abo (Cronjob) — nach Launch.
8. API Keys verschlüsseln (Fernet) — niedrige Prio.
9. **⏰ ERINNERUNG (Max, 2026-06-28):** **Rico Andres, Erik Mustermann und Ina** müssen noch auf **Lifetime Free** umgestellt werden. Beim nächsten Mal dran erinnern. — **Christoph Klein** (`christoph.kln@gmx.de`) ist am 2026-06-29 als Lifetime Free angelegt (siehe Konvention unter "Wichtige Fakten"). — **Elena Ceylan** (`elena.ceylan@mail.de`, Tel. +49 176 41138851) am 2026-06-30 als Lifetime Free angelegt (Teammitglied). Telefon noch nicht in DB (keine Phone-Spalte in `pending_payments`; trägt sie bei der `/welcome`-Registrierung selbst ein). — **Francesco Buontempo** (`francesco@firstclass-trading.com`) am 2026-07-07 als Lifetime Free markiert (Teammitglied). **Hatte bereits seit 09.06. einen voll eingerichteten Account** (`dashboard_users` id 13, `paid_signals`, verifiziert, aktiviert, Telegram-Link `https://t.me/+fsjGXLHAyvcxZDcy`) — nur nachträglich `ablefy_order_id='LIFETIME-FREE'`/`paid_amount='0'` gesetzt + Zugangsmail (`send_welcome_email_signals`) geschickt. Keine Telefonnummer (bewusst).
9. **⏳ FEATURE-WUNSCH (Max, 2026-06-28):** Bot soll erkennen/labeln, ob ein Trade **Swing / Day-Trade / Scalp** ist, und das ins Signal schreiben. Haben wir NOCH NICHT. Optionen: (a) auto via Haltedauer (Scalp < ~1h, Day < 24h, Swing > 1 Tag/über Nacht) — aber erst beim Close sicher bekannt; (b) Max benennt die Position (z.B. "BTC Scalp") → Bot liest den Namen; (c) Heuristik aus SL-Abstand/Hebel. Entscheidung mit Max nötig, wie er's getaggt haben will.

### Wichtige Fakten + Letzte Interaktion

Seit 2026-10-28 ausgelagert — Inhalt unverändert:
- [[(C) Wissensbasis Copytrading]] — Fehlerursachen, API-Fallen, Kündigungs-Termine, Betriebsfakten
- [[(C) Logbuch Copytrading]] — Session-Protokoll, neueste Einträge oben


## Verknüpfte Dateien
- [[(C) Wissensbasis Copytrading|(C) Wissensbasis Copytrading]]
- [[(C) Logbuch Copytrading|(C) Logbuch Copytrading]]

- ⚠️ **Vor jedem Aufräumen im Vault:** Schutzliste lesen — sie liegt im FCT-OS-Projekt und ist von hier aus **nicht** per Wikilink erreichbar (eigener Obsidian-Vault). Absoluter Pfad: `~/Life OS/FCT/FCT OS/05 System/(C) Vault aufräumen — Schutzliste.md`
- [[COMMANDS]]
- [[(C) Aufräumen — Schutzliste|(C) Aufräumen — Schutzliste (was NICHT angefasst werden darf)]]
- [[00 Architektur & Planung/(C) Systemarchitektur|(C) Systemarchitektur]]
- [[00 Architektur & Planung/(C) Onboarding Flow — Bauplan|(C) Onboarding Flow — Bauplan]]
- [[00 Architektur & Planung/(C) Onboarding Flow Map|(C) Onboarding Flow Map]]
- [[00 Architektur & Planung/(C) Signal-Produkte Architektur|(C) Signal-Produkte Architektur]]
- [[00 Architektur & Planung/(C) Levex API Reference|(C) Levex API Reference]]
- [[00 Architektur & Planung/(C) Levex Perpetual REST API|(C) Levex Perpetual REST API]]
- [[05 Live & Launch/(C) Server Setup|(C) Server Setup]]
- [[09 Iteration Logs/(C) Offene Punkte und TODOs|(C) Offene Punkte und TODOs]]
- [[09 Iteration Logs/(C) Bekannte Bugs und offene Fixes|(C) Bekannte Bugs und offene Fixes]]
- [[09 Iteration Logs/(C) Skalierungs-Ideen fuer spaeter|(C) Skalierungs-Ideen für später]]
- [[10 Security/(C) Security Audit|(C) Security Audit]]
- [[07 System/(C) patch_session_gate|(C) patch_session_gate.py — Dashboard-Sperre für Gekündigte (2026-09-25)]]
- [[07 System/(C) test_session_gate|(C) test_session_gate.py — Trockentest Session-Gate (11/11 PASS)]]
- [[07 System/(C) analyse_gekuendigt_abgelaufen|(C) analyse_gekuendigt_abgelaufen.py — read-only Analyse gekündigt + abgelaufen]]
- [[07 System/(C) kick_gekuendigt_abgelaufen|(C) kick_gekuendigt_abgelaufen.py — rückwirkender Entzug (Dry-Run-Default)]]
- [[07 System/(C) check_api_key|(C) check_api_key.py — Key-Prüfung (read-only)]]
- [[07 System/(C) check_pos_mode|(C) check_pos_mode.py — Position-Modus prüfen (405-Bug)]]
- [[07 System/(C) probe_balance_endpoint|(C) probe_balance_endpoint.py — Endpoint-Sondierung]]
- [[07 System/(C) show_account_state|(C) show_account_state.py — Balance + offene Positionen]]
- [[07 System/(C) show_master_positions|(C) show_master_positions.py — Master-Positionen inkl. positionID]]
- [[07 System/(C) audit_gekuendigte_mitglieder|(C) audit_gekuendigte_mitglieder.sh — Read-only Audit Gekündigte vs. Gruppen]]
- [[07 System/(C) send_setup_mail_silvio|(C) send_setup_mail_silvio.py — Setup-Mail-Versand (Vorlage: .env relativ laden)]]
- [[07 System/(C) check_affiliate_uids|(C) check_affiliate_uids.py — UID gegen Affiliate-Liste prüfen (read-only)]]
- [[07 System/(C) check_possides_francesco|(C) check_possides_francesco.py — posSide + Account-Modus auslesen (read-only)]]
- [[07 System/(C) check_order_raw|(C) check_order_raw.py — Order-Historie mit allen Feldern (read-only)]]
- [[07 System/(C) compare_affiliate_records|(C) compare_affiliate_records.py — Affiliate-Records vergleichen (read-only)]]
- [[07 System/(C) test_order_endpoints|(C) test_order_endpoints.py — Copy- vs. normaler Order-Endpoint (Limit, nicht füllbar)]]
- [[07 System/(C) probe_key_permissions|(C) probe_key_permissions.py — Key-Berechtigungen sondieren (read-only)]]
- [[07 System/(C) test_posside_varianten|(C) test_posside_varianten.py — 5 Varianten am Copy-Endpoint (alle 600034)]]
- [[07 System/(C) check_balance_drop|(C) check_balance_drop.py — Balance-Einbruch aufklären (read-only)]]
- [[07 System/(C) patch_reactivation|(C) patch_reactivation.py — Auto-Reaktivierung zahlender Rückkehrer (Webhook, 2026-09-11)]]
- [[07 System/(C) test_reactivation|(C) test_reactivation.py — Trockentest auf DB-Kopie (26/26 PASS)]]
- [[07 System/(C) patch_kick_guards|(C) patch_kick_guards.py — Zahlungs-Check in 7 Kick-Timer nachgerüstet]]
- [[07 System/(C) patch_old_guards_product|(C) patch_old_guards_product.py — Produkt-Filter für Brendler/Kocemba]]
- [[07 System/(C) backfill_access_valid_until|(C) backfill_access_valid_until.py — Ablefy-Ablaufdatum nachtragen]]
- [[07 System/(C) reactivate_paying_locked|(C) reactivate_paying_locked.py — Altfall: gesperrten, weiter zahlenden Kunden zurückholen]]
- [[07 System/(C) check_nichtzahler|(C) check_nichtzahler.py — Nichtzahler-Check read-only (bezahlte Zeiträume pro Order)]]
- [[09 Iteration Logs/(C) Nichtzahler-Check 2026-09-11|(C) Nichtzahler-Check 2026-09-11 — 51 offene Fälle + Entscheidungen]]
- [[00 Architektur & Planung/(C) Signal-Nachrichten Spezifikation|(C) Signal-Nachrichten Spezifikation]]
- [[04 Landingpage/Landingapge/index.html|Landingpage (normal, 79,95 €-Jahresabo)]]
- [[04 Landingpage/Event Landingpage/index.html|Event Landingpage (Launch-Angebot)]]
- [[08 AI Support/(C) AI Support Agent — Bauplan|(C) AI Support Agent — Bauplan (Planung, 2026-09-24)]]
- [[07 System/(C) patch_support_logging|(C) patch_support_logging.py — Mitschreiben im Support-Bot (live 2026-09-25)]]
- [[07 System/(C) migrate_kick_timers|(C) migrate_kick_timers.py — Einzel-Timer in Tabelle migrieren]]
- [[07 System/(C) revoke_access_daily|(C) revoke_access_daily.py — täglicher Zugangsentzug (ersetzt 49 Timer)]]
- [[08 AI Support/(C) Wissensbasis Support|(C) Wissensbasis Support — Faktenbasis für den AI-Agent (Entwurf)]]
- [[11 Performance/(C) Performance-Auswertung Copy Trading 2026-09-30|(C) Performance-Auswertung Copy Trading — 207 Trades, Stand 30.09.2026]]
- [[11 Performance/(C) Trades Copy Trading 2026-09-30.csv|(C) Trade-Liste als CSV (207 Positionen)]]
- [[07 System/(C) fetch_master_trades|(C) fetch_master_trades.py — LeveX Trade-Historie abrufen (read-only)]]
- [[07 System/(C) analyse_master_performance|(C) analyse_master_performance.py — Fills zu Positionen aggregieren]]
- [[07 System/(C) build_performance_note|(C) build_performance_note.py — Markdown-Auswertung generieren]]
- [[07 System/(C) get_master_balance|(C) get_master_balance.py — Master-Balance abfragen (read-only)]]
- [[07 System/(C) support_tools|(C) support_tools.py — read-only Tools für den AI-Agent (Abo-Whitelist verifiziert)]]
