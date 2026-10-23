# Onboarding Flow — Bauplan

> Status: Phase 1 implementiert, Phase 2 geplant
> Erstellt: 2026-05-14
> Zuletzt aktualisiert: 2026-05-15


## Ziel

Kunden koennen sich selbststaendig registrieren, bezahlen und ihren Levex-Account verknuepfen — ohne dass wir manuell in die DB greifen muessen. Der Prozess fuehlt sich an wie ein SaaS-Onboarding: Kauf zuerst, dann Guided Setup.


## Preise & Konditionen

| Position | Betrag |
|----------|--------|
| Einrichtungsgebuehr (einmalig) | 499,97 EUR |
| Monatlicher Retainer | 299,97 EUR |
| Mindesteinzahlung auf Levex | 1.000,00 USDT |

**Wichtig:** Die 1.000 USDT muessen eigenes Geld sein. Der Levex-Bonus (Futures Credit) kommt on top, ist aber nicht sofort verfuegbar und zaehlt nicht als Mindesteinzahlung.


## Der Flow aus Kundensicht

```
[Landingpage] → [Registrierung] → [Bezahlung] → [Guided Setup] → [Dashboard]
                  IMPLEMENTIERT      GEPLANT       IMPLEMENTIERT    IMPLEMENTIERT
```

> In Phase 1 wird Bezahlung uebersprungen. Nach Registrierung geht der Kunde direkt ins Setup.

---

### Schritt 1 — Registrierung (`/register`) — IMPLEMENTIERT

Formular mit folgenden Feldern:
- Vorname
- Nachname
- E-Mail
- Passwort (min. 8 Zeichen)
- Passwort bestaetigen

**Rechtliche Checkboxen (unterhalb der Formularfelder):**

| Checkbox | Pflicht? | Text |
|----------|----------|------|
| AGB | Ja | "Ich akzeptiere die AGB." |
| Datenschutz | Ja | "Ich habe die Datenschutzerklaerung zur Kenntnis genommen." |
| Risikohinweis | Ja | "Ich habe den Risikohinweis gelesen und bin mir bewusst, dass beim Trading Verluste bis zum Totalverlust meines eingesetzten Kapitals moeglich sind." |
| Marketing | Nein | "Ich moechte per E-Mail ueber Produkt-Updates und Angebote informiert werden." |

Alle drei Pflicht-Checkboxen muessen akzeptiert werden, sonst Fehlermeldung. Marketing ist optional.

**Danach:** Account wird erstellt (Status: `registered`). Automatischer Login + Weiterleitung zu `/setup` (Phase 1 ohne Checkout).

**Zusaetzlich implementiert:**
- Password-Toggle (Auge-Icon) fuer beide Passwort-Felder
- Cookie-Banner (notwendige / alle akzeptieren)
- Footer mit Links zu Impressum, AGB, Datenschutz, Risikohinweis
- Link zu `/login` fuer bestehende Accounts

---

### Schritt 2 — Bezahlung (`/checkout`) — GEPLANT (Phase 2)

- Einrichtungsgebuehr 499,97 EUR + erster Monat Retainer 299,97 EUR
- Stripe Checkout Session (gehostet bei Stripe — sicherste Variante)
- Nach erfolgreicher Zahlung: Redirect zu `/setup`
- Stripe Webhook setzt Status auf `paid`

**Wichtig:** Kein Zugang zum Dashboard oder Setup ohne Zahlung.

> Stripe wird spaeter integriert. In Phase 1 wird `/checkout` uebersprungen
> und der Kunde geht direkt von Registrierung ins Setup.

---

### Schritt 3 — Guided Setup (`/setup`) — IMPLEMENTIERT

Wizard mit 3 Schritten. Zwei-Spalten-Layout: links Anleitung + Formular, rechts Video-Platzhalter + Support-Links. Progress Bar oben zeigt aktuellen Schritt (1/2/3) mit Haken fuer abgeschlossene Schritte.

Rechte Spalte — immer sichtbar auf jedem Schritt:
- Video-Platzhalter ("Video-Anleitung kommt bald")
- Telegram Support Button (Link zu `https://t.me/FCT_Copy_Trading_Support_Bot`)
- Calendly-Button ("Kostenlosen Einrichtungscall buchen")

Zurueck-Navigation: Ab Schritt 2 gibt es einen "Zurueck"-Link. Man kann nur zu bereits abgeschlossenen Schritten zuruecknavigieren (`?step=N`), nicht vorwaerts springen.


#### Schritt 3a — LeveX Account erstellen (Step 1) — IMPLEMENTIERT

- Ueberschrift: "Schritt 1: LeveX Account erstellen"
- Info-Badge: Hinweis dass nur ueber Affiliate-Link erstellte Accounts freigeschaltet werden koennen
- Zwei Buttons: "Jetzt Account erstellen" (oeffnet Referral-Link) | "Account erstellt" (Selbstbestaetigung, setzt Step auf 2)
- Referral-Link: https://levex.com/r/maxsteinauer
- Reine Selbstbestaetigung — kein technischer Check

**Bonus-Box mit Einzahlungsbonus-Tabelle:**

| Einzahlung | Bonus |
|------------|-------|
| 1.000 USDT | 200 USDT |
| 3.000 USDT | 600 USDT |
| 10.000 USDT | 1.200 USDT |
| 100.000 USDT | 5.000 USDT |

Hinweis: Futures Credit, Gewinne daraus auszahlbar, Credit selbst nicht.

**VIP-5 Gebuehren-Box (30 Tage):**

| Gebuehr | Standard | VIP-5 |
|---------|----------|-------|
| Spot Maker | 0,1000% | 0,0600% |
| Spot Taker | 0,1000% | 0,0800% |
| Futures Maker | 0,0200% | 0,0160% |
| Futures Taker | 0,0600% | 0,0500% |


#### Schritt 3b — Guthaben einzahlen (Step 2) — IMPLEMENTIERT

- Ueberschrift: "Schritt 2: Guthaben einzahlen"
- Info-Badge: Erklaerung warum Mindestkontogroesse noetig (proportionale Skalierung)
- Button: "Mindestguthaben eingezahlt" (Selbstbestaetigung, setzt Step auf 3)
- Bonus-Box: Tipp zu mehr Einzahlung = mehr Bonus
- Reine Selbstbestaetigung in diesem Schritt

> **Hinweis:** Der tatsaechliche Balance-Check passiert erst in Schritt 3c (API Key Validierung).


#### Schritt 3c — API Keys erstellen & verbinden (Step 3) — IMPLEMENTIERT

- Ueberschrift: "Schritt 3: API Keys erstellen & verbinden"
- Sicherheits-Badge: Keys koennen nur Trades spiegeln / lesen, keine Auszahlungen

**Zwei API Key-Paare werden benoetigt:**

1. **Copy Trading API Key** (Berechtigung: Copy Trading)
   - API Key + API Secret
   - Wird gegen Levex API validiert (UID wird automatisch ausgelesen)

2. **Futures Read API Key** (Berechtigung: Futures Read-only)
   - API Key + API Secret
   - Wird fuer Balance-Tracking und Positions-Skalierung genutzt

**Validierung (zweistufig):**
- "Keys pruefen" Button: Validiert beide Keys per AJAX gegen `/api/setup/validate-key`
- Submit-Button ("Verbinden & Starten") ist disabled bis beide Keys als gueltig validiert

**Balance-Check bei Submit (serverseitig):**
- Futures-Balance wird per WebSocket ueber den Read API Key abgefragt (`check_futures_balance()`)
- Minimum: 1.000 USDT
- Bei zu wenig Balance: Fehlermeldung mit aktuellem Betrag ("Dein Futures-Guthaben betraegt aktuell X USDT...")
- Kein Abschluss moeglich unter 1.000 USDT

**Nach erfolgreichem Abschluss:**
- `complete_setup()` speichert: UID, Copy Trading Key+Secret, Read Key+Secret
- Status wird auf `active` gesetzt
- Redirect zu `/dashboard?welcome=1`

---

### Schritt 4 — Dashboard (`/dashboard`) — IMPLEMENTIERT

**Disclaimer-Popup (pro Session):**
- Bei jedem Besuch des Dashboards wird geprueft ob `sessionStorage('fct_disclaimer')` gesetzt ist
- Wenn nicht: Disclaimer-Overlay wird angezeigt (muss mit "Verstanden" bestaetigt werden)
- Wird nur einmal pro Browser-Session angezeigt (sessionStorage)

**Welcome-Video-Popup (einmalig nach Setup):**
- Wird ausgeloest durch `?welcome=1` Query-Parameter (kommt vom Setup-Redirect)
- Zeigt nach dem Disclaimer ein Video-Intro-Popup
- Reihenfolge: Disclaimer zuerst → nach Bestaetigung → Video-Popup
- Wird nur beim allerersten Dashboard-Besuch nach Setup angezeigt


## Technische Architektur

### Implementierte Routes

| Route | Methode | Status | Beschreibung |
|-------|---------|--------|--------------|
| `/register` | GET/POST | IMPLEMENTIERT | Registrierungsformular mit Checkboxen |
| `/login` | GET/POST | IMPLEMENTIERT | Login mit Onboarding-Status-Redirect |
| `/logout` | POST | IMPLEMENTIERT | Logout + Session loeschen |
| `/setup` | GET | IMPLEMENTIERT | Guided Setup Wizard (Step 1-3) |
| `/setup` | POST | IMPLEMENTIERT | Setup-Schritte abschliessen |
| `/api/setup/validate-key` | POST | IMPLEMENTIERT | API Key validieren (AJAX) |
| `/dashboard` | GET | IMPLEMENTIERT | Dashboard mit `?welcome=1` Support |
| `/checkout` | GET | GEPLANT | Stripe Checkout starten (Phase 2) |
| `/checkout/success` | GET | GEPLANT | Rueckkehr nach Zahlung (Phase 2) |
| `/checkout/cancel` | GET | GEPLANT | Abbruch bei Zahlung (Phase 2) |
| `/webhook/stripe` | POST | GEPLANT | Stripe Webhook (Phase 2) |

### Access Control (Status-basierte Redirects) — IMPLEMENTIERT

| Onboarding-Status | Login-Redirect | Dashboard-Zugang |
|--------------------|----------------|------------------|
| `registered` | `/setup` | Nein (Redirect zu `/setup`) |
| `paid` | `/setup` | Nein (Redirect zu `/setup`) |
| `setup_pending` | `/setup` | Nein (Redirect zu `/setup`) |
| `active` | `/dashboard` | Ja |

Implementiert in:
- `auth_routes.py`: `_redirect_by_status()` fuer Login-Redirect
- `dashboard_routes.py`: `_check_onboarding()` wird auf jeder Dashboard-Route gecalled

> **Phase 1 Besonderheit:** Status `registered` redirected direkt zu `/setup` (kein `/checkout` dazwischen).

### Datenbank-Aenderungen

**`customers` Tabelle — neue Spalten:**

```sql
first_name TEXT DEFAULT ''
last_name TEXT DEFAULT ''
onboarding_status TEXT DEFAULT 'registered'
-- Werte: 'registered' → 'paid' → 'setup_pending' → 'active'
onboarding_step INTEGER DEFAULT 0
-- 0=nicht gestartet, 1=Levex Account, 2=Einzahlung, 3=API Key
stripe_customer_id TEXT        -- Phase 2
stripe_subscription_id TEXT    -- Phase 2
paid_at TIMESTAMP              -- Phase 2
setup_completed_at TIMESTAMP
```

**`dashboard_users` Tabelle:**
- `invite_token` ist optional (NULL erlaubt fuer Self-Service-Registrierung)
- Self-Service erstellt direkt mit Email + Password
- Bestehender Invite-Flow (`/invite/{token}`) bleibt als Alternative erhalten

### API Key Validierung — IMPLEMENTIERT

Zwei Validierungsfunktionen in `api_key_validator.py`:

1. `validate_api_key(api_key, api_secret)` — Prueft Copy Trading Key gegen Levex API, gibt `{valid, uid, error}` zurueck
2. `check_futures_balance(read_api_key, read_api_secret)` — Prueft Futures-Balance per WebSocket, gibt `{balance, error}` zurueck

### Bot-Core Integration

Der Bot laedt neue Kunden **ohne Restart** per Polling alle 60 Sekunden:
- Prueft periodisch ob neue Kunden mit `onboarding_status = 'active'` in der DB sind
- Vergleicht mit bereits geladenen Kunden
- Neue Kunden werden automatisch hinzugefuegt


## Umsetzungsreihenfolge

### Phase 1 — Registrierung + Setup (ohne Payment) — DONE

1. ~~DB-Migrationen (neue Spalten in customers, invite_token nullable)~~ Done
2. ~~`/register` Seite + Route bauen (inkl. Checkboxen: AGB, Datenschutz, Risikohinweis, Marketing)~~ Done
3. ~~`/setup` Wizard bauen (3 Schritte mit Platzhalter-Videos, zwei-Spalten-Layout)~~ Done
4. ~~API Key Validierung gegen Levex API (Copy Trading Key + Futures Read Key)~~ Done
5. ~~Balance-Check per WebSocket (Minimum 1.000 USDT)~~ Done
6. ~~Access Control / Status-basierte Redirects~~ Done
7. ~~Welcome-Video-Popup (`?welcome=1`) + Disclaimer pro Session~~ Done

> In Phase 1 wird der Checkout uebersprungen. Nach Registrierung geht der Kunde
> direkt ins Setup. Das reicht fuer die ersten 20 Kunden die wir sowieso
> persoenlich onboarden.

### Phase 2 — Stripe Payment — GEPLANT

7. Stripe Account einrichten + Produkte anlegen
8. `/checkout` Flow mit Stripe Checkout Session
9. Webhook-Endpoint fuer Zahlungsbestaetigung
10. Abo-Verwaltung (kuendigen, pausieren)

### Phase 3 — Polish — GEPLANT

11. E-Mail Benachrichtigungen (Willkommen, Zahlung, Setup-Erinnerung)
12. Password Reset Flow
13. Admin-Uebersicht (Kunden verwalten, Status aendern)


## Referral & Bonus — Zusammenfassung fuer den Setup

**Levex Referral-Link:** https://levex.com/r/maxsteinauer
(Muss spaeter auf einen trackbaren Link geaendert werden)

**Bonus-Programm von Levex (Einzahlungsbonus als Futures Credit):**

| Einzahlung | Bonus (Futures Credit) | Handelsvolumen-Bedingung |
|------------|----------------------|--------------------------|
| 100 USDT | 20 USDT | 5K USDT |
| 500 USDT | 100 USDT | 20K USDT |
| 1.000 USDT | 200 USDT | 100K USDT |
| 3.000 USDT | 600 USDT | 500K USDT |
| 10.000 USDT | 1.200 USDT | 1M USDT |
| 100.000 USDT | 5.000 USDT | 10M USDT |

**Wichtige Regeln:**
- Nur die hoechste Stufe wird vergeben — Boni nicht kombinierbar
- Futures Credit ist kein Echtgeld, kann als Margin genutzt werden
- Gewinne aus dem Credit sind auszahlbar, der Credit selbst nicht
- Credit verfaellt nach 7 Tagen ab Gutschrift
- Nettoeinzahlung muss 3 Tage auf dem Konto bleiben
- VIP-5-Gebuehren fuer 30 Tage (Futures Taker 0,05% statt 0,06%)
- Bonus-Bedingungen koennen von Levex jederzeit geaendert werden

**Unser Incentive-Ansatz:**
Wir nutzen den Bonus um Kunden zu motivieren, mehr als die Mindesteinzahlung (1.000 USDT) einzuzahlen. Fuer uns heisst das: groessere Konten = groessere kopierte Positionen = zufriedenere Kunden weil die absoluten Gewinne hoeher sind.


## Calendly

Platzhalter-Link fuer Einrichtungs-Calls:
https://calendly.com/d/cx8t-rf8-xfg/kostenfreie-trading-beratung

## Support

Telegram Support Bot (in Setup rechte Spalte verlinkt):
https://t.me/FCT_Copy_Trading_Support_Bot
