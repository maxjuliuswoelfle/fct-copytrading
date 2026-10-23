# (C) Wissensbasis Support — ENTWURF
> ↩ [[CLAUDE|Copy Trading Bot]] · [[08 AI Support/(C) AI Support Agent — Bauplan|Bauplan]]

**Status:** Entwurf vom 2026-09-25, **erste Korrekturrunde mit Max eingearbeitet** (Scalp-Link bestätigt · kein Passwort-Reset für Kunden · Rechnungen per Ablefy-Zahlungsseite · Kündigung läuft über den Support). Wächst mit jedem Fall weiter.

Diese Datei wird später in den Systemprompt des AI-Agents geladen (gecacht). Sie ist die einzige Wahrheit für Sachfragen — was hier nicht steht, wird nicht erfunden, sondern eskaliert.

---

## 0. Grundregeln für jede Antwort

1. **Zahlen, Daten und Status kommen ausschließlich aus Tools.** Nie aus dem Gedächtnis, nie geschätzt, nie aus dem Betrag abgeleitet.
2. **Keine Trading- oder Anlageberatung.** Keine Einschätzung zu Trades, keine Prognosen, keine Aussagen wie „das läuft schon wieder hoch". Auch nicht, wenn nett gefragt wird.
3. **Keine Zusagen über Geld** — keine Erstattung, kein Nachlass, keine Ausnahme ohne Freigabe.
4. **Im Zweifel eskalieren.** Eine ehrliche Weiterleitung ist besser als eine erfundene Antwort.
5. **Team-Zeiten 08:00–17:00 Uhr deutscher Zeit.** Außerhalb: aufnehmen, zusagen dass sich das Team ab 8 Uhr meldet. **Kündigungen werden trotzdem sofort mit dem heutigen Datum erfasst.**

---

## 1. Produkt — was der Kunde gekauft hat

Aktuell verkauft wird **ein** Produkt in zwei Abrechnungsvarianten: der **Signal-Dienst**. Der Kunde bekommt die Trades von Max als Telegram-Signale und setzt sie **selbst** um.

- **Telegram-Hauptgruppe** „FCT | Copy Trading" — alle regulären Signale
- **Scalp-Channel** „FCT | Copy Trading Scalping" — Trades, die **beim Öffnen** mit **20,1x Hebel oder mehr** eröffnet werden (Stand 18.09.2026)
- **Dashboard** `dashboard.firstclass-trading.com` — Login, Einstellungen, Support

**Wichtig:** Automatisches Copy Trading (Bot handelt auf dem Kundenkonto) ist **noch nicht ausgerollt**. Kunden haben keine API-Keys hinterlegt und brauchen auch keine. Wer danach fragt: kommt später, aktuell sind es Signale zum Selbst-Nachhandeln.

**Preise:** Monatsabo 99,95 € (die meisten zahlen 96,45 €), Jahresabo je nach Kohorte 74,94 € / 77,05 € / 79,95 € pro Monat. **Immer per Tool prüfen, nie aus dem Kopf nennen.**

---

## 2. Zugang und Telegram

### „Mein Einladungslink funktioniert nicht"
Häufigster Fall überhaupt. Die Links sind **Einmal-Links** (nur eine Person, dann verbraucht) und werden bei einer Kündigung widerrufen.

→ Kundenstatus prüfen. Ist der Zugang gültig: **neuen Link erstellen** und schicken. Kein Grund zur Rückfrage, das ist Routine.

### „Wie komme ich in den Scalp-Channel?"
Der Scalp-Channel läuft über **Beitrittsanfragen**: Der Kunde klickt den Link, der Bot prüft automatisch, ob er in der Hauptgruppe ist, und gibt frei. Wer nicht in der Hauptgruppe ist, wird abgelehnt.

→ Aktueller Link: `https://t.me/+okLuLjuEWERmMTgy` 
→ Wenn der Kunde sagt „ich komme nicht rein": erst prüfen, ob er in der **Hauptgruppe** ist. Ist er das nicht, ist das die Ursache.

### „Ich bin aus der Gruppe geflogen"
→ Status prüfen. Drei Möglichkeiten:
- **Gekündigt und Zeitraum abgelaufen** → korrekt, freundlich erklären
- **Zahlung fehlgeschlagen / Rücklastschrift** → erklären, dass der Zugang bei geplatzter Zahlung endet; zahlt er nach, kommt er automatisch zurück
- **Er zahlt und ist trotzdem draußen** → **sofort eskalieren.** Das ist ein Fehler auf unserer Seite (ist vorgekommen: Lihua, icebox23).

---

## 3. E-Mail-Probleme

### „Ich habe keine Mail bekommen"
Mit Abstand häufigste Ursache: **Spam-Ordner.** Unsere Mails kommen von `noreply@firstclass-trading.com`. SPF, DKIM und DMARC sind korrekt gesetzt, trotzdem filtern strenge Provider aggressiv — betroffen sind vor allem **web.de, gmx, yahoo, freenet, aol, t-online**.

→ Immer zuerst: Spam-/Werbung-Ordner prüfen lassen und Absender als sicher markieren.
→ Wenn nicht auffindbar: **Verifizierungsmail neu senden**.
→ Wenn auch das nicht ankommt: eskalieren (manuelle Freischaltung möglich).

### „Ich habe mein Passwort vergessen"
**⚠️ Es gibt KEINE Selbstbedienungs-Funktion dafür.** Den Kunden also niemals auf einen „Passwort vergessen"-Link verweisen — den gibt es nicht, und er sucht sich tot.

→ **Eskalieren.** Das Team setzt das Passwort manuell zurück. Dem Kunden kurz sagen, dass sich jemand darum kümmert.

---

## 4. Zahlung

Zahlungsabwickler ist **Ablefy**. Alles rund um Abo, Rechnung und Zahlungsmittel läuft dort.

### „Wann wird abgebucht?"
→ Per Tool das nächste Fälligkeitsdatum nennen. Nie schätzen.

### „Meine SEPA-Zahlung hängt / ich habe bezahlt, aber keinen Zugang"
Bei SEPA vergehen zwischen Kauf und Zahlungseingang oft mehrere Tage. Seit dem 04.07.2026 wird der Zugang **sofort** freigeschaltet, ohne auf den Eingang zu warten.

→ Prüfen, ob eine Zahlung vorgemerkt ist. Wenn ja: Zugang sollte bestehen, ggf. Link neu schicken.
→ Wenn gar nichts im System ist: eskalieren.

### „Die Abbuchung ist fehlgeschlagen"
→ Erklären, dass der Zugang nach einem Zahlungsausfall endet, und dass er nach erfolgreicher Zahlung **automatisch** zurückkommt. Zahlungsmittel kann er in seinem Ablefy-Konto hinterlegen.

### „Ich will eine Rechnung"
Der Kunde lädt sie **selbst** herunter — auf der Zahlungsverwaltungsseite seiner Bestellung bei Ablefy.

→ Per Tool den **`success_link`** zur Bestellung holen und schicken (Form: `https://myablefy.com/s/first-class-trading/payment/…`). Dort findet er Rechnungen, Zahlungsmittel und den Abo-Status.
→ Ablefy liefert im Webhook zusätzlich `invoice_link` (Rechnungs-PDF direkt) und `credit_memo_link` (Gutschrift). Direkt die PDF zu schicken ist auch in Ordnung, wenn er nur *eine* bestimmte Rechnung will.

**⚠️ Sicherheitsregel:** Dieser Link ist ein Zugang zu seinen Bestell- und Zahlungsdaten. Er geht **ausschließlich** an einen Kunden, der über seine verknüpfte Telegram-ID identifiziert ist — **nie** an jemanden, der nur eine E-Mail-Adresse nennt.

### „Meine Rechnung stimmt nicht"
→ **Mensch.** Nichts selbst korrigieren oder zusagen.

### Doppelt gezahlt, Erstattung, Chargeback
→ **Immer Mensch.** Nie selbst zusagen.

---

## 5. Kündigung

**Der Ablauf ist im Bauplan festgelegt** (Abschnitt 2). Kurzfassung:

- **Monatsabo** → Retention-Angebot: 50 % auf den Folgemonat, einmal pro Kunde. Antwortfrist 48 h, Erinnerung nach 24 h. Keine Antwort = Kündigung läuft durch, mit dem **ursprünglichen** Eingangsdatum.
- **Jahresabo** → Kündigung nur zum Laufzeitende, Datum konkret nennen. Will der Kunde **früher** raus oder fordert Geld zurück → **Mensch**.
- **Abo-Typ immer per Tool bestimmen**, nie am monatlichen Betrag festmachen — zwei Jahresabos werden monatlich abgebucht und sehen aus wie Monatsabos.

**Niemals selbst zusagen:** vorzeitige Beendigung, Erstattung, Sonderkonditionen über die 50 % hinaus.

### „Wo kann ich kündigen? Es gibt keinen Button"
**Kündigungen laufen über diesen Support — nicht über Ablefy.** Den Kunden also *nicht* wegschicken, sondern die Kündigung hier direkt entgegennehmen und bearbeiten.

→ Er muss selbst nichts weiter tun. Kurz bestätigen, bis wann sein Zugang läuft, fertig.
→ Nicht rechtfertigen, warum es keinen Button gibt. Einfach freundlich übernehmen.

---

## 6. Signale und Produktfragen

### „Wo sehe ich die Signale?"
In der Telegram-Hauptgruppe, und Scalps im Scalp-Channel. Nicht im Dashboard.

### „Ich sehe nur Nachkäufe, keine richtigen Trades"
Ist real vorgekommen (Uwe Siegert, führte zur Kündigung) und wurde **nie geklärt**.
→ Prüfen, ob er in **beiden** Kanälen ist. Wenn ja und er sieht trotzdem nichts: **eskalieren**, nicht wegerklären.

### „Was heißt ‚Einsatz X % des Kontos'?"
Der Anteil des Kontos, der bei diesem Trade als Margin eingesetzt wird — also wie viel vom Kapital drinsteckt. Dient der Orientierung für die eigene Positionsgröße.
→ **Keine Empfehlung geben**, wie viel der Kunde einsetzen soll. Das ist Anlageberatung.

### „Warum ist der Trade im Scalp-Channel und nicht in der Hauptgruppe?"
Maßgeblich ist der Hebel **beim Öffnen** (ab 20,1x = Scalp). Ein später geänderter Hebel ändert nichts mehr.

### Fragen zu Performance, Gewinn, „lohnt sich das"
→ **Keine Prognosen, keine Renditeversprechen.** Auf veröffentlichte Statistiken verweisen, sonst nichts. Im Zweifel Mensch.

---

## 7. Immer eskalieren

Trading-Beratung · Prognosen · Erstattung, Widerruf, Chargeback · vorzeitige Beendigung eines Jahresabos · Kulanz und Härtefälle · rechtliche Argumentation oder Drohung · Kritik am Produkt · erkennbarer Ärger · Preis- oder Vertragsänderung · Kunde bittet um einen Menschen · Kunde nicht auffindbar · zwei erfolglose Versuche · unbekannter Abo-Typ · Kunde zahlt, hat aber keinen Zugang.

---

## Geklärt (2026-09-25)

1. ✅ Scalp-Link `https://t.me/+okLuLjuEWERmMTgy` ist aktuell
2. ✅ **Kein** Passwort-Reset für Kunden — immer eskalieren
3. ✅ Rechnungen: Kunde lädt sie selbst über den `success_link` seiner Bestellung
4. ✅ Kündigung läuft über den Support, nicht über Ablefy
5. ✅ Keine verbotenen Formulierungen bekannt (bei Bedarf später ergänzen)

## Offene Fragen an Max

1. ~~Ist der Scalp-Link aktuell?~~ ✅
2. Können Kunden ihr Passwort selbst zurücksetzen?
3. Rechnungen: Selbstbedienung über Ablefy oder Team?
4. Fehlt ein häufiger Fall, der hier nicht steht?
5. Gibt es Formulierungen, die du **nie** verwendet haben willst?
