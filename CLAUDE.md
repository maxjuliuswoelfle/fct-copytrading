# FCT Copytrading
> ↩ [[CLAUDE|Life OS]] · [[FCT/CLAUDE|FCT]]

Live-Produkt mit zahlenden Kunden: Max Steinauers Levex-Trades werden als **Signale** in eine bezahlte Telegram-Gruppe gepostet (Phase 1, live seit 28.06.2026) und sollen in Phase 2 **automatisch auf Kundenkonten gespiegelt** werden (Bot-Core fertig, Kundenseite noch nicht freigeschaltet — ❓ Status von Max bestätigen lassen). Dazu ein Kunden-Dashboard (Registrierung, Setup, Support) und die Kündigungs-/Zugangs-Automatik.

**Dieser Ordner ist die Werkbank** — Code, Scripts, Anleitungen, Git-versioniert. Das System läuft auf Server 2 (`178.105.135.197`). Gesamtbild aller FCT-Systeme → `FCT OS/(C) Systemlandkarte FCT.md`.

**Einstieg für jede Session:**
- [[(C) Wissensbasis Copytrading]] — Kündigungs-Termine, Kick-Fälle, API-Fallen, Betriebsfakten (vor jeder Kundenaktion nach dem Namen suchen)
- [[(C) Logbuch Copytrading]] — Session-Protokoll, neueste Einträge oben
- [[COMMANDS]] — Server- und Management-Befehle
- [[(C) Aufräumen — Schutzliste]] — vor jedem Löschen/Verschieben lesen

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


## Aktueller Status

> **Zuletzt aktualisiert:** 2026-10-28 — CLAUDE.md aufgeteilt (Logbuch + Wissensbasis), Kopf auf Betriebsstand gebracht, Aufräumen vom 27.10. committet. Davor 2026-10-23: „Viktor Lachner" manuell entfernt (keinem Account zuordenbar). Details → [[(C) Logbuch Copytrading]].
> **Status:** In Betrieb. Signal-Gruppe (Main + Scalp) läuft, Kunden kaufen über Ablefy (Plan 610907 monatlich / 610909 Jahresabo mit monatlicher Abbuchung). Kündigungen werden im Support-Bot gemeldet, in der Wissensbasis erfasst und vom konsolidierten Ablauf-Job (`revoke-access-daily`, täglich 08:55) zum Laufzeitende ausgeführt — seit 28.09. statt 49 Einzel-Timern. Session-Gate im Dashboard sperrt Gekündigte. AI-Support-Agent: Bausteine 1–3 gebaut (Mitschreiben, Wissensbasis, read-only Tools), Antworten noch nicht automatisiert.
> **Offen:** siehe „Offene Punkte" unten.

## Was läuft

- **Signal-Bot** (`01 Bot-Core/signal_bot.py`) — 10 Nachrichtentypen, Trade-Nummerierung, Debounce, deutsche Formatierung; postet in Paid-Gruppen; profitable Closes + Wochen-/Monats-Summaries in den Marketing-Channel (`-1001252595461`).
- **Bot-Core** — WebSocket-Listener, Parser (14 Actions), Execution Engine mit proportionaler Skalierung, Position-Mapping, Reconciliation, Pause/Resume. Technisch fertig; Kunden-Copytrading noch nicht aktiv (`MIN_DEPOSIT_USDT` vor Phase 2 auf 1000 zurück).
- **Dashboard** (`03 Dashboard/MVP 1.0/`, FastAPI, Port 8443, `dashboard.firstclass-trading.com`) — Payment-First-Onboarding (Ablefy-Checkout → `/welcome` → Telegram-Link), 2 Tiers (Paid Signals = Dashboard Light, Copy Trading = voll), Session-Gate für Gekündigte, Support-Seite, Legal Pages, 5 transaktionale Mails via Google-Workspace-SMTP.
- **Ablefy-Webhook** (`/webhooks/ablefy`) — Payment/Refund/Order-Events, nur Produkte 517561 (Signale) + 517562 (Copy Trading), SEPA-Erstkäufe sofort freischalten (Rücklastschrift sperrt).
- **Zugangs-Automatik** (`07 System/`) — `revoke-access-daily` Timer: Kündigungen zum Laufzeitende, Kick aus Main + Scalp, Dashboard-Sperre. Kick-Regel: Kulanz = ban + sofort unban (Endstatus `left`), Moderationsfall = permanent.
- **Support-Bot** (`@FCT_Copy_Trading_Support_Bot`, `07 System/support_bot.py`) — Kundenanfragen, Mitschreiben für den AI-Support.
- **Levex-Proxy** (`levex-proxy`, nur auf diesem Server, weil bei Levex gewhitelistet) — UID-Prüfung für den FCT-Club (Dienst des FCT-OS-Projekts, Code dort unter `01 Betrieb/levex-proxy/`).
- **Landingpages** (`04 Landingpage/`) — `copytrading.firstclass-trading.com` auf IONOS (statisch) + Event-Landingpage. Zielbild: auf den eigenen Stack ziehen (siehe Systemlandkarte).

## Offene Punkte

- **Phase 2 — automatisches Copy Trading freischalten:** End-to-End-Test mit echtem Trade, `MIN_DEPOSIT_USDT=1000`, API-Keys verschlüsseln (Fernet), Anleitungsvideos statt Platzhalter.
- **AI-Support-Agent Baustein 4** — Antworten automatisieren (Bauplan: [[08 AI Support/(C) AI Support Agent — Bauplan]]).
- **Kündigungs-Erkennung:** Kein Webhook-Event heißt bei Plan 610909 NICHT „nicht gekündigt" — Ablefy-Status aktiv prüfen (Regel in der Wissensbasis). Automatischer Abgleich wäre der nächste Schritt.
- **Nicht zuordenbare Telegram-Accounts** („BND", „Viktor Lachner") — Lücke zwischen Telegram-ID und `dashboard_users`; Idee: Beitritt nur über personalisierten Einmal-Link.
- **Backup der SQLite-DB einrichten:** `07 System/backup-copytrading-db.sh` auf Server 2 installieren (Anleitung im Script-Kopf: Cron 03:30, 30 Tage, `/var/backups/copytrading/`).
- **Landingpages konsolidieren** — IONOS → eigener Stack (Projekt in Notion).
- **Admin-Panel, Analytics, Dashboard MVP 2.0** — nice-to-have, nicht priorisiert.
- **Nice-to-have aus 2026-06:** Trade-Label Swing/Day/Scalp im Signal (Feature-Wunsch Max), Vorteils-Seite vor Upgrade-Checkout, Bumper-Offer.

## Beteiligte Personen

- **Max Steinauer** — der Trader, Master-Account (Levex), Gesicht des Produkts; meldet Kündigungen/Kicks per Zuruf.
- **Max Wölfle** — Betrieb, Systeme, Marketing; `root` auf dem Server.
- **Luis Heidenreich** — Technik (seit 26.10.2026), eigener Server-User `luis`, Git über den FCT-OS-Git-Server.


## Ordnerstruktur

```
FCT Copytrading/
├── CLAUDE.md                  ← Kontext, Regeln, Status, offene Punkte (kurz halten)
├── (C) Wissensbasis Copytrading.md ← Fakten, Kündigungen, Fallen
├── (C) Logbuch Copytrading.md      ← Session-Protokoll
├── (C) Aufräumen — Schutzliste.md
├── COMMANDS.md                ← Server- und Management-Befehle
├── 00 Architektur & Planung/  ← Systemarchitektur, Levex-API-Docs, Onboarding-Flow, Signal-Spezifikation
├── 01 Bot-Core/               ← Python-Quellcode Bot + Signal-Bot (+ systemd, deploy.sh)
├── 03 Dashboard/MVP 1.0/      ← FastAPI-Dashboard (routes/, templates/, static/, deploy-dashboard.sh)
├── 04 Landingpage/            ← Landingpage + Event-Landingpage (statisch, IONOS)
├── 05 Live & Launch/          ← Server-Setup
├── 06 Attachments/            ← Referenzen
├── 07 System/                 ← Support-Bot, Ablauf-Job (revoke-access-daily), Analyse-/Patch-Scripts
├── 08 AI Support/             ← Bauplan + Wissensbasis Support
├── 09 Iteration Logs/         ← Bugs, TODOs, Skalierungs-Ideen
├── 10 Security/               ← Security Audit
└── 11 Performance/            ← Performance-Auswertungen
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


## Regeln für Kontextpflege

- **Live-Update-Regel:** Nach jeder relevanten Änderung (neues Feature deployed, Bug gefixt, Entscheidung getroffen, Architektur geändert) **sofort**: (1) Eintrag oben ins [[(C) Logbuch Copytrading]], (2) „Zuletzt aktualisiert"-Zeile hier anpassen, (3) dauerhafte Erkenntnis → [[(C) Wissensbasis Copytrading]], (4) neuer Dienst/Domain → [[../FCT OS/(C) Systemlandkarte FCT|Systemlandkarte]] im FCT-OS-Projekt. Nicht warten bis die Session endet — der Chat kann jederzeit abbrechen.
- **Was ist "relevant"?** Alles was eine neue Session wissen müsste: Was wurde deployed, was wurde geändert, welche Entscheidungen wurden getroffen, was ist noch offen.
- **Diese Datei bleibt kurz:** Rolle, Stack, Server, Regeln, offene Punkte. Protokolle und Fakten-Sammlungen gehören ins Logbuch bzw. die Wissensbasis.
- **Kontextdatei ist Wahrheit:** Neue Sessions starten mit CLAUDE.md → dort steht alles was die nächste Session wissen muss.


## Verknüpfte Dateien
- [[07 System/backup-copytrading-db.sh|Backup-Script SQLite (täglich 03:30)]]
- [[(C) Wissensbasis Copytrading|(C) Wissensbasis Copytrading]]
- [[(C) Logbuch Copytrading|(C) Logbuch Copytrading]]

- ⚠️ **Vor jedem Aufräumen im Vault:** Schutzliste lesen — sie liegt im FCT-OS-Projekt und ist von hier aus **nicht** per Wikilink erreichbar (eigener Obsidian-Vault). Absoluter Pfad: `~/Life OS/FCT/FCT OS/03 Anleitungen/(C) Vault aufräumen — Schutzliste.md`
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
