---
created: 2026-05-18
type: architecture
status: current
---

# Onboarding Flow Map

Komplette Übersicht aller User-Flows — von der Landingpage bis zum Dashboard.


## Übersicht: Die 3 Streams

```
                         dashboard.firstclass-trading.com
                                      │
                                      ▼
                                   /login
                                      │
                    ┌─────────────────┼─────────────────┐
                    │                 │                  │
                    ▼                 ▼                  ▼
             /signup/free      /signup/signals       /register
             Free Signale      Premium Signale     Copy Trading
                    │                 │                  │
                    ▼                 ▼                  ▼
              /setup/free       /setup/premium    /setup/copytrading
              (UID Abfrage)     (UID Abfrage)     (3-Schritt Wizard)
                    │                 │                  │
                    ▼                 ▼                  ▼
           /signup/free/done     /dashboard          /dashboard
           (Telegram Link)    (Dashboard Light)   (Volles Dashboard)
```


## Stream 1: Free Signale

**Zielgruppe:** Kostenlose Krypto-Signale (1-2/Woche) via Telegram
**URL-Pfad:** `/signup/free` → `/setup/free` → `/signup/free/done`

```
Neuer User                                    Eingeloggter User
    │                                              │
    ▼                                              ▼
/signup/free (GET)                           /signup/free (GET)
  → Zeigt signup_free.html                     → Onboarding aktiv?
  → Formular: Name, E-Mail,                      Ja → /signup/free/done
     Passwort, Legal-Checkboxen                   Nein → /setup/free
    │
    ▼
/signup/free (POST)
  → Account erstellen (tier: free)
  → onboarding_status: setup_pending
  → Verifizierungsmail senden
  → Auto-Login (Session Cookie)
  → Redirect: /setup/free
    │
    ▼
/verify-pending
  → Zeigt "Prüfe dein Postfach"
  → Resend-Button
    │
    ▼ (Klick auf Link in E-Mail)
/verify-email?token=xxx
  → email_verified = true
  → Redirect: /setup/free  ⚠️ aktuell /setup/copytrading — muss noch gefixt werden
    │
    ▼
/setup/free (GET)
  → Prüft: eingeloggt? E-Mail verifiziert? Onboarding noch offen?
  → Zeigt setup_free.html
  → UID-Feld (auto-fill wenn schon vorhanden)
    │
    ▼
/setup/free (POST)
  → UID speichern
  → TODO: Levex Affiliate API Check
  → onboarding_status: active
  → Redirect: /signup/free/done
    │
    ▼
/signup/free/done
  → Zeigt signup_free_done.html
  → Telegram-Gruppenlink (TODO: personalisierter Einmal-Link)
  → Upsell: Premium Signale / Copy Trading
```

**Dashboard-Zugang:** Kein Dashboard. `/dashboard` zeigt `dashboard_no_access.html` mit Upgrade-Optionen.


## Stream 2: Premium Signale (Paid)

**Zielgruppe:** 10-20 Trading-Signale/Monat inkl. Trade Management via Telegram
**URL-Pfad:** `/signup/signals` → `/setup/premium` → `/dashboard`
**Preis:** ~100€/Monat (TODO: Stripe)

```
Neuer User                                    Eingeloggter Free User
    │                                              │
    ▼                                              ▼
/signup/signals (GET)                        /signup/signals (GET)
  → Zeigt signup_signals.html                  → Tier prüfen:
  → Formular: Name, E-Mail,                      free → Auto-Upgrade auf paid_signals
     Passwort, Legal-Checkboxen                          → /setup/premium
    │                                             paid_signals/copy_trading → /dashboard
    ▼
/signup/signals (POST)
  → Bestehende Free-E-Mail + richtiges PW?
      → Ja: Upgrade auf paid_signals → /dashboard
      → Nein: Neuer Account (tier: paid_signals)
  → onboarding_status: setup_pending
  → Verifizierungsmail senden
  → Auto-Login → /setup/premium
    │
    ▼
/verify-pending → /verify-email
  → (gleich wie Free)
    │
    ▼
/setup/premium (GET)
  → Prüft: eingeloggt? E-Mail verifiziert? Onboarding noch offen?
  → Zeigt setup_signals.html
  → UID-Feld (auto-fill wenn schon vorhanden)
    │
    ▼
/setup/premium (POST)
  → UID speichern
  → TODO: Levex Affiliate API Check
  → TODO: Stripe Checkout (vor oder nach UID?)
  → onboarding_status: active
  → Redirect: /dashboard
    │
    ▼
/dashboard (Dashboard Light)
  → dashboard_signals.html
  → Telegram Premium-Gruppenlink
  → Support, Einstellungen (nur Profil)
  → Gesperrte Bereiche mit Lock-Icon + Upsell zu Copy Trading
```

**Dashboard-Zugang:** Dashboard Light (`dashboard_signals.html`) — Telegram-Link, Support, Einstellungen (nur Profil). Kein Kontostand, keine Performance-Daten, kein Disclaimer.


## Stream 3: Copy Trading

**Zielgruppe:** Trades werden automatisch auf den Kunden-Account gespiegelt
**URL-Pfad:** `/register` → `/setup/copytrading` (3 Schritte) → `/dashboard`
**Preis:** 500€ Setup + 300€/Monat (TODO: Stripe)

```
Neuer User                                    Eingeloggter Free/Paid User
    │                                              │
    ▼                                              ▼
/register (GET)                              /register (GET)
  → Zeigt register.html                        → Tier prüfen:
  → Formular: Name, E-Mail,                      copy_trading → /dashboard
     Passwort, Legal-Checkboxen                   free/paid_signals →
    │                                                Upgrade auf copy_trading
    ▼                                                onboarding: setup_pending, step 1
/register (POST)                                     → /setup/copytrading
  → Account erstellen (tier: copy_trading)
  → DSGVO Consent speichern
  → Verifizierungsmail senden
  → Auto-Login → /verify-pending
    │
    ▼
/verify-pending → /verify-email
  → (gleich wie oben)
    │
    ▼
/setup/copytrading (GET)
  → Prüft: eingeloggt? E-Mail verifiziert?
  → Zeigt setup.html mit aktuellem Schritt
  → Zurück-Navigation möglich (aber nicht über gespeicherten Schritt hinaus)
    │
    ├── Schritt 1: LeveX Account erstellen
    │     → "Account erstellt" Button
    │     → POST action=complete_step_1
    │     → Setzt Step 2
    │
    ├── Schritt 2: Guthaben einzahlen (min. 1.000 USDT)
    │     → "Mindestguthaben eingezahlt" Button
    │     → POST action=complete_step_2
    │     → Setzt Step 3
    │
    └── Schritt 3: API Keys erstellen & verbinden
          → Copy Trading API Key + Secret
          → Futures Read API Key + Secret
          → POST action=complete_step_3
          → REST-Validierung (Copy Trading Key)
          → WebSocket Balance-Check (Read Key, min 1.000 USDT)
          → Keys speichern, onboarding_status: active
          → Willkommensmail senden
          → /dashboard?welcome=1
    │
    ▼
/dashboard (Volles Dashboard)
  → dashboard.html
  → Equity Chart, Positionen, unrealisierter P&L
  → Recent Trades, Bot-Performance
  → Follower Count, Balance
  → Welcome-Video Popup (einmalig bei ?welcome=1)
  → Disclaimer Popup (pro Session)
```

**Dashboard-Zugang:** Volles Dashboard mit allen Features. Zugang zu: `/verlauf`, `/positionen`, `/live-feed`, `/wallet`, `/einstellungen` (komplett), `/support` (mit System-Status).


## Upgrade-Pfade

```
Free ──────────────────► Paid Signals ──────────────► Copy Trading
       /signup/signals          /register
       (Auto-Upgrade,           (Auto-Upgrade,
        kein neues Konto)        kein neues Konto,
                                 neues Onboarding)

Free ─────────────────────────────────────────────► Copy Trading
                        /register
                        (Auto-Upgrade, kein neues Konto,
                         neues Onboarding Step 1-3)
```

| Von | Nach | Auslöser | Was passiert |
|-----|------|----------|-------------|
| Free | Paid Signals | `/signup/signals` (eingeloggt) | Tier-Upgrade, Redirect `/setup/premium` |
| Free | Copy Trading | `/register` (eingeloggt) | Tier-Upgrade, Onboarding reset, Redirect `/setup/copytrading` |
| Paid Signals | Copy Trading | `/register` (eingeloggt) | Tier-Upgrade, Onboarding reset, Redirect `/setup/copytrading` |

**Wichtig:** Eingeloggte User müssen sich nie neu registrieren. Das bestehende Konto wird einfach hochgestuft.


## Gemeinsame Seiten (alle Tiers)

| Route | Beschreibung | Tier-Unterschiede |
|-------|-------------|-------------------|
| `/login` | Login-Seite | — |
| `/logout` | Session beenden → `/login` | — |
| `/forgot-password` | Passwort-Reset anfordern | — |
| `/reset-password` | Neues Passwort setzen | — |
| `/dashboard` | Hauptseite nach Login | Free: Kein Zugang / Paid: Light / CT: Voll |
| `/einstellungen` | Profil + Account | Free/Paid: nur Profil / CT: + API Keys, Pause, Benachrichtigungen |
| `/support` | Hilfe + FAQ | Free/Paid: kein System-Status, anderes FAQ / CT: volles FAQ + Status |
| `/impressum` | Legal | — |
| `/agb` | Legal | — |
| `/datenschutz` | Legal | — |
| `/risikohinweis` | Legal | — |

### Nur Copy Trading

| Route | Beschreibung |
|-------|-------------|
| `/verlauf` | Trade-Historie (paginiert, 50/Seite) |
| `/positionen` | Positionsübersicht (Stub) |
| `/live-feed` | Echtzeit Trade-Events (Stub) |
| `/wallet` | Wallet-Verbindung (Stub) |


## Bekannte Issues / TODOs

### Bugs (vor Launch fixen)

1. **Verifizierungsmail-Redirect ist hardcoded auf `/setup/copytrading`**
   - `/verify-email` und `/verify-pending` leiten immer zu `/setup/copytrading` — auch für Free/Paid User
   - Muss tier-abhängig sein: Free → `/setup/free`, Paid → `/setup/premium`, CT → `/setup/copytrading`

2. **Login-Redirect bei unfertigem Onboarding ist hardcoded**
   - Login POST und `_redirect_by_status()` leiten immer zu `/setup/copytrading`
   - Muss ebenfalls tier-abhängig sein

3. **Stub-Seiten haben kein Tier-Gate**
   - `/positionen`, `/live-feed`, `/wallet` prüfen nur Login + Onboarding, nicht den Tier
   - Sidebar versteckt die Links, aber direkte URL-Eingabe ist nicht blockiert
   - Nur `/verlauf` prüft explizit auf `copy_trading`

### Noch nicht implementiert

4. **Affiliate-Verifizierung (UID)** — Levex API Check fehlt, nur Speicherung implementiert
5. **Stripe Payment** — Paid Signals + Copy Trading
6. **Personalisierte Telegram-Links** — `createChatInviteLink` mit `member_limit=1`
7. **Telegram Auto-Kick** — Nur Paid Gruppe, Cronjob prüft Stripe-Status
8. **Tier-spezifische E-Mails** — Verifizierung, Willkommen, Onboarding-Abschluss mit Telegram-Link
