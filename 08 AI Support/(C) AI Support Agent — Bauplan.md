# (C) AI Support Agent — Bauplan
> ↩ [[CLAUDE|Copy Trading Bot]]

**Status:** Planung (2026-09-24) — nichts gebaut, nichts deployed.
**Ziel:** Erste Support-Linie übernimmt eine AI, die im Tonfall von Max schreibt, echte Kundendaten lesen kann und die häufigsten Fälle **abschließend** löst — inklusive einfacher Kündigungen mit Retention-Angebot. Nur echte Ausnahmen landen bei einem Menschen.

---

## 1. Architektur — Kernprinzip

Der AI-Teil wird **als eigener HTTP-Service** gebaut (Endpoint `ai/support` in der bestehenden FastAPI-App), nicht in `support_bot.py` hineingeschrieben. Grund: Der Transportweg wechselt später von Telegram-Gruppe auf ManyChat. Wenn der Kern ein Service mit stabilem Vertrag ist, ist dieser Wechsel ein Tausch des Transports — kein Neubau.

```
Transport (wechselt)          Kern (bleibt)
─────────────────────         ──────────────────────────────
Phase A/B: support_bot.py ──▶ POST ai/support
Phase C:   ManyChat       ──▶   ├─ Claude (claude-opus-5) + Tools
                                ├─ Wissensbasis (gecacht)
                                ├─ Conversation-State (DB)
                                └─ Eskalations-Router
```

**Vertrag des Endpoints:**
Rein: `telegram_user_id`, `nachricht`, `kanal`. Raus: `antwort`, `eskalation` (bool), `eskalations_grund`, `intent`, `aktionen[]` (was ausgeführt wurde).

---

## 2. Kündigungs-Logik (die neue Kernanforderung)

### 2.1 Abo-Klassifizierung — NUR über `plan_id`, niemals über den Betrag

Das ist die gefährlichste Stelle. **Zwei Jahresabos werden monatlich abgebucht und sehen deshalb wie Monatsabos aus:**

| Plan-ID | Typ | Abbuchung | Bindung | Kündigung möglich zum |
|---|---|---|---|---|
| `610907` | **Monatsabo** | 96,45 €/Monat | keine | Ende des bezahlten Monats |
| `610909` | **Jahresabo** (Launch) | 74,94 €/Monat | 12 Monate | Laufzeitende |
| `616171` | **Jahresabo** (monatl. Abbuchung) | 77,05 €/Monat | 12 Monate | Laufzeitende |
| Einmalzahlung Jahr | **Jahresabo** | ~876,95 € einmal | 12 Monate | Laufzeitende |

Genau diese Verwechslung war der Fall **Patrick Sigl** (Plan 616171, wirkte monatlich, war 12 Monate gebunden). Wenn die AI einem Jahresabo-Kunden eine Monatskündigung zusagt, ist das eine falsche Zusage mit rechtlicher Angriffsfläche.

→ **Harte Whitelist im Code, kein AI-Ermessen.** Unbekannte oder fehlende `plan_id` → Eskalation, nie raten.

### 2.2 Monatsabo → Retention-Flow

```
Kündigungswunsch erkannt
   ↓
Vorprüfung (Code, nicht AI):
   • schon mal Retention-Rabatt bekommen?         → ja: direkt kündigen, kein Angebot
   • Zahlung pausiert / Chargeback / Nichtzahler? → ja: direkt kündigen, kein Angebot
   • Härtefall-Signal (Gesundheit, Geldnot)?      → MENSCH
   • Leistungs-Kritik / rechtliche Argumentation? → MENSCH
   • nächste Rate in unter 5 Tagen?               → MENSCH (Rabatt zeitlich nicht mehr umsetzbar, s. 6.2)
   ↓
Kündigungseingang wird SOFORT mit dem heutigen Datum protokolliert
   ↓
Nachricht 1: Retention-Angebot — 50 % auf den nächsten Monat
   ↓
Warten max. 48 h (Erinnerung nach 24 h) — entschieden 2026-09-25
   ├─ "ja"          → Rabatt-Pfad
   ├─ "nein"        → Kündigungs-Pfad
   └─ keine Antwort → Kündigungs-Pfad + kurze Info-Nachricht
```

**⚠️ Rechtlich zwingend:** Die Kündigung darf **nicht** davon abhängen, dass der Kunde auf das Angebot antwortet. Eine Kündigungserklärung wirkt ab Zugang. Das Retention-Angebot ist ein Zusatz, keine Bedingung — deshalb wird der Eingangstag festgehalten und das Kündigungsdatum daraus berechnet, nicht aus dem Tag der Antwort. Sonst entsteht genau die Angriffsfläche, die **Micha73** beschrieben hat („andernfalls bitte die Vertragsgrundlage nennen").

**Missbrauchsschutz:** ✅ **Entschieden (2026-09-25): Das Angebot gibt es genau EINMAL pro Kunde, dauerhaft** — Flag in der DB, kein Reset nach 12 Monaten. Wer es schon hatte und wieder kündigen will, wird ohne zweites Angebot gekündigt. Sonst spricht sich „kündigen = 50 % Rabatt" in der Community herum.

### 2.3 Jahresabo → nur zum Laufzeitende

Nachricht: Kündigung ist möglich, greift aber zum **konkret genannten** Laufzeitende; Zugang läuft bis dahin normal weiter.

- Kunde akzeptiert → Kündigung zum Laufzeitende vormerken, fertig.
- Kunde will **früher** raus, fordert Erstattung, oder widerspricht → **sofort MENSCH**, ohne weitere Verhandlung.

Kein Retention-Angebot bei Jahresabos — er zahlt ohnehin bis Laufzeitende weiter.

### 2.4 Was die AI bei der Ausführung darf — und was nicht

**Darf automatisch:**
- `access_end` berechnen — aus `payments_schedule_next_rate_date`, **nie** aus `access_valid_until` allein (bekannte Falle: bei 240 von 289 aktiven Kunden ist dieses Feld veraltet)
- Zugangsentzug in `scheduled_access_revocations` eintragen (siehe 3.)
- Telegram-ID per `getChatMember` verifizieren und nachtragen, falls leer — genau der Schritt, dessen Fehlen im Fall **Tobias Falke** zu 3 Tagen Überhang geführt hat
- Bestätigungsnachricht schreiben, Fall dokumentieren

**Darf NICHT (Stufe 1):**
- Die Kündigung in Ablefy selbst auslösen → erzeugt einen Task für Max, bis die Ablefy-API verifiziert ist (siehe 6.)
- Erstattungen, Teilerstattungen, vorzeitige Beendigung
- Blocklist-Einträge
- Irgendetwas am Trading-Bot

---

## 3. Infrastruktur-Voraussetzung: 25 Einzel-Timer → eine Tabelle + ein Cron

**Das muss vor der AI-Kündigung stehen.** Aktuell gibt es pro Kündigung eine eigene systemd-Unit (`kick_*.sh` + `.timer`, inzwischen 25+). Eine AI kann und darf keine systemd-Units auf einen Produktionsserver schreiben.

Ersatz:
- Tabelle `scheduled_access_revocations` — `customer_id`, `revoke_at`, `grund`, `modus` (`permanent` / `kulanz_ohne_ban`), `status`, `angelegt_von`
- **Ein** täglicher Cron-Job, der die bewährte Logik genau einmal enthält: Laufzeit-GRANT-Check mit Produkt-Filter über beide Payload-Varianten (`$.product.id` **und** `$.product.product_id`), Ban in Main + Scalp, Endstatus-Gegenprüfung per `getChatMember` (Lehre aus dem Micha73-Unban, der beim ersten Versuch nicht griff), Invite-Revoke, DB-Update, Admin-Alert.

**Nebeneffekte, die dabei gratis mitkommen:**
- Der offene „Ablauf-Job statt Einzel-Timer" aus Part 2 ist damit erledigt
- Der Fehlerfall „Timer feuert, aber keine Telegram-ID → nur Admin-DM, Kunde bleibt drin" wird eine nachverfolgbare Tabellenzeile statt einer verlorenen DM
- Nichtzahler-Entzug (Gruppe A, 7-Tage-Regel) nutzt dieselbe Tabelle

---

## 4. Tools (Function Calling)

| Tool | Art | Zweck |
|---|---|---|
| `get_kundenstatus` | read | Tier, verifiziert, aktiv, bezahlt bis, Kündigungsstatus |
| `get_abo_details` | read | `plan_id` → Abo-Typ nach Whitelist, Laufzeitende, Zahlungshistorie |
| `check_gruppen_mitgliedschaft` | read | `getChatMember` Main + Scalp |
| `neuen_invite_link_erstellen` | write | häufigster Einzelfall, harmlos |
| `verifizierungs_mail_erneut_senden` | write | löst das gmx/web.de-Spam-Problem |
| `retention_angebot_protokollieren` | write | Angebot + Frist + Einmal-Flag |
| `kuendigung_vormerken` | write | Zeile in `scheduled_access_revocations` |
| `eskalieren` | write | Fall an Mensch übergeben, mit Grund + Zusammenfassung |

**Prompt-Regel:** Beträge, Daten, Status und Abo-Typ **ausschließlich** aus Tool-Ergebnissen. Nie erinnern, nie schätzen, nie aus dem Betrag ableiten.

---

## 5. Eskalation

**Immer Mensch, ohne Ausnahme:**
Trading-/Anlageberatung und Prognosen · Erstattung / Widerruf / Chargeback · vorzeitige Beendigung eines Jahresabos · Kulanz und Härtefälle · rechtliche Argumentation oder Drohung · Leistungs-Kritik am Produkt · Beschwerde / erkennbarer Ärger · Preis- oder Vertragsänderung über den definierten Rabatt hinaus · Kunde bittet um Mensch · Kunde nicht auffindbar · zwei erfolglose Versuche · unbekannte `plan_id`.

**Team-Zeiten: 08:00–17:00 Uhr deutsche Zeit.** AI läuft 24/7.
⚠️ Der Server läuft auf UTC. Die Zeiten müssen gegen die Zeitzone `Europe/Berlin` gerechnet werden, **nicht** gegen einen festen UTC-Offset — sonst verschiebt sich alles zweimal im Jahr um eine Stunde. Außerhalb der Zeiten: AI nimmt den Fall auf, sagt zu, dass sich das Team ab 8 Uhr meldet — **Kündigungen werden trotzdem sofort mit dem heutigen Datum erfasst**, nie auf den nächsten Werktag geschoben.

---

## 6. Ablefy-API — Befund und offener Punkt

Es existiert eine Ablefy-API unter `api.myablefy.com` mit Swagger unter `api/swagger_doc`. Erste Recherche deutet auf `POST api/orders/{token}/cancel` und `POST api/payments/{id}/refund` hin, aber **keinen** Endpoint für Abo-Preisänderungen.

**Das ist noch nicht verifiziert** (Swagger war nicht sauber lesbar) und muss mit echten Credentials geprüft werden, bevor irgendetwas darauf gebaut wird.

### 6.1 Rabatt-Umsetzung: entweder echte Preisanpassung oder manueller Task

**Teilerstattung ist ausgeschlossen (Entscheidung Max, 2026-09-24):** Bei einer Erstattung bleiben die Transaktions-/Plattformgebühren auf der vollen Rate liegen — der Rabatt würde also zusätzlich Geld kosten. Nur zwei Wege sind erlaubt:

1. **Automatisch** — nur wenn die Ablefy-API eine echte Rate-/Pricing-Plan-Anpassung für eine laufende Order kann. Muss verifiziert werden.
2. **Manuell** — die AI kommuniziert das Angebot und legt einen **Task mit hartem Fälligkeitsdatum** an; ein Mensch setzt die Anpassung in Ablefy um.

### 6.2 Der manuelle Task muss zwangsläufig rechtzeitig erledigt werden

Das ist die kritische Stelle: Wird die Anpassung nicht **vor** der nächsten Abbuchung gemacht, zieht Ablefy den vollen Betrag, obwohl wir 50 % zugesagt haben. Ergebnis wäre ein Vertrauensbruch bei einem Kunden, der gerade kündigen wollte — plus reales Chargeback-Risiko.

- Tabelle `manuelle_aufgaben` — `typ`, `customer_id`, `faellig_bis`, `status`
- **Empfänger: ausschließlich Max** (Entscheidung 2026-09-25) — keine Zuweisung an Team, kein Verteiler
- `faellig_bis` = nächste Rate (`payments_schedule_next_rate_date`) **minus 5 Tage** — SEPA wird von Ablefy mit Vorlauf eingereicht, am Abbuchungstag ist es zu spät
- **Täglicher Reminder, bis `status='done'`** — eine einzelne Admin-DM reicht nachweislich nicht: im Fall **Tobias Falke** kam der Admin-Alert korrekt an, wurde nicht abgearbeitet, und der Kunde saß 3 Tage länger in den Gruppen
- **Vorlauf-Regel:** Ist die nächste Rate **weniger als 5 Tage** entfernt, macht die AI **kein** Rabatt-Angebot, sondern eskaliert direkt an einen Menschen. Sonst verspricht sie etwas, das zeitlich nicht mehr umsetzbar ist.

---

## 7. Tone of Voice — Learning by Doing, kein Datenimport

✅ **Entschieden (2026-09-25): Es wird KEIN Altmaterial importiert.** Der Tonfall entsteht im Betrieb.

- **Start:** grober Stil-Prompt, abgeleitet aus vorhandener Copy im Vault (Landingpage, E-Mail-Templates, Signal-Formate) plus ein paar Vorgaben von Max
- **Verfeinerung:** Jede Korrektur im Shadow Mode (Phase A) wird als Beispiel gespeichert und wandert in den Prompt. Nach 50–100 korrigierten Antworten sitzt der Ton.
- **Voraussetzung:** Der Support-Bot muss **mitschreiben** (neue Tabelle `support_messages`: Kundennachricht, AI-Vorschlag, tatsächlich gesendete Antwort). Ohne das gibt es keine Korrektur-Historie und damit kein Lernen.

**Verworfene Wege (2026-09-25, dokumentiert damit es niemand nochmal versucht):**
- *Telegram-Chat-Export:* möglich, aber nur über den Client „Telegram Lite" — die macOS-Standard-App hat die Funktion nicht. Von Max verworfen.
- *Telegram Client-API (Telethon):* **funktioniert nicht.** Telegram stellt Login-Codes für selbst erstellte `api_id`s vielfach gar nicht mehr zu — Versand wird quittiert, es kommt nie etwas an (belegt: Telethon-Issues #4730, #4687, #4041; Resend scheitert mit `SendCodeUnavailableError`). Telethon ist seit Februar 2026 archiviert. Keine Umgehung möglich.
- **Folge:** Die ~47 fehlenden Telegram-IDs aus dem Nichtzahler-Check bleiben offen — dieser Weg hätte sie mitgeliefert. Braucht eine eigene Lösung.

---

## 8. Rollout

| Phase | Transport | AI-Verhalten | Eskalation |
|---|---|---|---|
| **A — Shadow** (1–2 Wo.) | Telegram-Gruppe | schlägt Antwort **nur vor**, Mensch sendet | wie heute |
| **B — Auto** | Telegram-Gruppe | antwortet selbst, Whitelist-Intents zuerst | Gruppe, mit @Max |
| **C — Switch** | ManyChat | unverändert | Tag `human_needed` + Automation pausiert → ManyChat Inbox |

**Warum in ManyChat nichts ankommt (geklärt):** `python-telegram-bot` löscht beim Start von `run_polling()` implizit den gesetzten Webhook. Unser Bot killt damit bei jedem Neustart ManyChats Webhook — kein ManyChat-Fehler.
→ **Beim Switch auf Phase C muss das Polling dauerhaft aus**, sonst passiert es wieder.
→ **Und:** ManyChat-Subscriber-IDs sind **keine** Telegram-user-ids (bewiesen im Fall Arne / Ray Bartels). Das Kunden-Matching muss über die echte Telegram-user-id laufen, die ManyChat in einem Custom Field halten muss.

---

## 9. Kosten

`claude-opus-5` mit Prompt-Caching auf Systemprompt + Wissensbasis: ~0,05–0,08 $ pro Konversation. Bei 30 Tickets/Tag ≈ **50–70 $/Monat**. Bei dem Volumen ist Modell-Sparen die falsche Optimierung — Urteilsvermögen bei Eskalations-Entscheidungen ist mehr wert als 30 €.

---

## 10. Nebenbefund: Kündigungsbutton (§ 312k BGB)

Micha73 hat beanstandet, dass es im Dashboard keinen Kündigungsbutton gibt. Für Verbraucher in DE/EU ist ein solcher Button bei Dauerschuldverhältnissen im elektronischen Geschäftsverkehr **vorgeschrieben**, und **Ablefy bietet das Feature nativ an**. Das ist rechtlich zu prüfen (kein Rechtsrat von mir), aber wahrscheinlich ein kurzer Fix mit doppeltem Nutzen.

**Und eine Chance:** Wenn Kunden selbst online kündigen, kommt bei uns ein `order.subscription.canceled`-Webhook an. Wenn der Retention-Flow **an diesem Webhook** hängt statt nur am Support-Chat, deckt er **alle** Kündigungen ab — auch die, die nie im Support schreiben (Dominik Rappers, Lihua, Markus Nass haben alle selbst online gekündigt). Das ist der größere Hebel als der Chat-Pfad.

---

## Offene Punkte

1. **Ablefy-API mit echten Credentials verifizieren** — (a) Kündigung auslösen? (b) **Rate / Pricing-Plan einer laufenden Order ändern?** Punkt (b) entscheidet, ob der Rabatt automatisch läuft oder ein Mensch ihn manuell setzen muss. Erstattungen sind kein Weg (s. 6.1).
1b. ~~Wer bekommt die manuellen Tasks?~~ ✅ **Nur Max** (2026-09-25).
2. ~~Support-Gruppe exportieren~~ ✅ **Entfällt — Learning by Doing** (2026-09-25, s. 7.)
3. **Timer-Konsolidierung bauen** — Voraussetzung für AI-Kündigungen
4. ~~Retention-Angebot festlegen~~ ✅ **50 % auf einen Monat, genau einmal pro Kunde, dauerhaft** (2026-09-25)
5. ~~Antwortfrist~~ ✅ **48 h, mit Erinnerung nach 24 h** (2026-09-25)
6. **Kündigungsbutton bei Ablefy** — rechtlich prüfen und aktivieren
7. **Mitschreiben im Support-Bot einbauen** — Voraussetzung fürs Lernen, braucht einen Support-Bot-Neustart (unkritisch)
8. **Telegram-IDs der ~47 Nichtzahler** — eigener Lösungsweg nötig, Client-API ist tot
