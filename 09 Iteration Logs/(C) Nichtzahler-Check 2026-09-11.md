# (C) Nichtzahler-Check 2026-09-11
> ↩ [[CLAUDE|Copy Trading Bot]]

**Reiner Check — niemand wurde gekickt, gesperrt oder angeschrieben.** Max entscheidet.
Script: [[07 System/(C) check_nichtzahler|(C) check_nichtzahler.py]] (v3, read-only: DB schreibgeschützt, Telegram nur `getChatMember`). Stand: 11.09.2026, 13:02 UTC.

## Methode (v3 — maßgeblich)
Grundlage ist Ablefys eigenes Feld **„nächste Rate fällig am“** (`payments_schedule_next_rate_date`), das in jeder Zahlung mitkommt (in 1.049 von 1.060 Zahlungen befüllt; bei Einmalzahlung steht dort das Datum ein Jahr später). Das ist verbindlich „bezahlt bis“. Pro Order unseres Produkts (517561):
- laufend → bezahlt bis „nächste Rate fällig“
- gekündigt → Ablefys Enddatum
- pausiert (Zahlung fehlgeschlagen) → Ende am Pausentag; eine spätere Zahlung hebt die Pause auf
- 3 Tage Kulanz; eine laufende SEPA-Zahlung zählt als bezahlt
- **Mehrfach-Bestellungen zählen zusammen** (per E-Mail inkl. gmail/googlemail + Order-ID); zusätzlich Suche nach Vor- und Nachname unter anderer E-Mail

**Warum v3:** v1 (Ablefy-Zugangsdatum) und v2 („letzte Zahlung + 31 Tage“) haben Vorauszahler fälschlich markiert. Von Max geprüft und bestätigt: **Robin Ebner** (2 Raten am 29.07.) und **Manuela Orsag** (Rate am 07.08. vorgezogen) sind beide bis 28.09. bezahlt. **s-duerr** hat 876,95 € Einmalzahlung → bis 01.07.2027.

Von **290** aktiven Kunden mit abgelaufenem Ablefy-Datum sind **240 bezahlt**. **50 sind offen.** Unter anderer E-Mail zahlt keiner davon.

## Kurzfassung
| Gruppe | Anzahl | Bedeutung |
|---|---|---|
| **A** Zahlung fehlgeschlagen, Ablefy hat pausiert | 18 | Ablefy hat den Zugang entzogen und versucht weiter abzubuchen — bei uns passiert nichts |
| **B** Gekündigt + abgelaufen, nie gekickt | 32 | Haben selbst in Ablefy gekündigt; nur von Max gemeldete Kündigungen bekommen einen Kick-Timer |

- **Nicht kicken:** Max' eigener Account (30), Ina (31), Rico (49) — Team
- **Klären:** Felix Roth (77), Norbert Block (201) — lt. Notiz bis 2027, Ablefy bucht aber seit der Kündigung nicht mehr ab
- **Schon raus:** Nikolai Guenther (432)
- **→ 44 echte Nichtzahler** (17 aus A + 27 aus B)

**Telegram:** 47 von 50 haben **keine Telegram-ID** (Beitritt vor dem 28.07.) → der Bot kann sie nicht entfernen und nicht prüfen, ob sie noch drin sind. Nachweislich noch drin: **Noah Schartz Forte (434)**.

## Mehrfach-Bestellungen (Max' Hinweis) — geprüft
9 der 50 haben mehrere Orders. Bei **allen** ist es dasselbe Muster: abgebrochene Kartenversuche am selben Tag (0 Zahlungen, nur Fehler) + **eine** echte Order. Diese echte Order ist pausiert bzw. gekündigt — **keine versteckte laufende Order**.
| Kunde | abgebrochene Versuche | echte Order | Status der echten Order |
|---|---|---|---|
| Delil Dogan | 1 (Einmalzahlung, 4 Fehler) | 16519808 | pausiert 29.07. |
| Albertas Maciukaitis | 2 | 16574390 | pausiert 06.08. |
| Benjamin Vollbehr | 3 | 16575139 | pausiert 06.08., Ablefy versucht weiter (10 Fehlversuche bis 07.09.) |
| Marco Schenk | 1 | 16672815 | pausiert 21.08. |
| Santo Castagnaro | 1 | 16546518 | pausiert 02.09. |
| Kandid Hofstetter | 1 | 16525836 | gekündigt |
| Tula Kittelmann | 1 | 16564610 | gekündigt |
| Christian Kettenburg | 1 | 16519851 | gekündigt |
| Kai Radojewski | 2 | 16704062 | gekündigt |

## A — Zahlung fehlgeschlagen, Ablefy hat pausiert (18)
**Max' Entscheidung (11.09.):** Diese Gruppe ist real — Zugang wird entzogen, **aber nicht sofort, sondern mit Zeitversatz**. Frist noch festzulegen.
| id | Name | E-Mail | Plan | Zahlungen (letzte) | pausiert seit | Tage | Telegram |
|---|---|---|---|---|---|---|---|
| 135 | Delil Dogan | delil.dogan1992@icloud.com | Monatsabo | 1 (28.06.) | 29.07. | 44 | keine ID |
| 153 | Alex Pedevilla | pedevillaalex@gmail.com | Monatsabo | 1 (28.06.) | 29.07. | 44 | keine ID |
| 159 | Karl Gombocz | kago9562@gmail.com | Jahresabo Launch (monatl.) | 1 (28.06.) | 29.07. | 44 | keine ID |
| 225 | Eldin Sultanovic | eldinsultan@gmail.com | Monatsabo | 1 (29.06.) | 30.07. | 43 | keine ID |
| 370 | Albertas Maciukaitis | albertomaciukaitis@gmail.com | Jahresabo monatl. | 1 (05.07.) | 06.08. | 36 | keine ID |
| 371 | Benjamin Vollbehr | benny.vollbehr@bluewin.ch | Jahresabo monatl. | 1 (05.07.) | 06.08. | 36 | keine ID |
| 379 | Sascha Lutz | sascha1302@web.de | Monatsabo | 1 (06.07.) | 07.08. | 35 | keine ID |
| 380 | Josef Knechtges | j_k@live.de | Monatsabo | 1 (06.07.) | 07.08. | 35 | keine ID |
| 420 | Marco Schenk | crypto@trading-invest.ch | Jahresabo monatl. | 1 (20.07.) | 21.08. | 21 | keine ID |
| 75 | Stefan Sandke | sanirostock@gmail.com | Jahresabo Launch (monatl.) | 2 (29.07.) | 29.08. | 13 | keine ID |
| 88 | Malick Eisenblätter | ferrum43global@gmail.com | Jahresabo Launch (monatl.) | 2 (29.07.) | 29.08. | 13 | keine ID |
| 115 | Tom Claß | tomclass2004@web.de | Jahresabo Launch (monatl.) | 2 (30.07.) | 29.08. | 13 | keine ID |
| 165 | Nico Kapferer | nico@nicokapferer.com | Monatsabo | 2 (29.07.) | 29.08. | 13 | keine ID |
| 432 | Nikolai Guenther | nikolai_guenther@yahoo.com | Jahresabo monatl. | 1 (29.07.) | 30.08. | 12 | **schon raus** |
| 434 | Noah Schartz Forte | noahschartzforte@gmail.com | Jahresabo monatl. | 1 (29.07.) | 30.08. | 12 | **noch drin** (Main + Scalp) |
| 329 | Santo Castagnaro | soteria@outlook.de | Monatsabo | 2 (02.08.) | 02.09. | 9 | keine ID |
| 347 | Maritta Weise | h-weise@pm.me | Jahresabo monatl. | 2 (04.08.) | 04.09. | 7 | keine ID |
| 361 | Dirk Schwerdtfeger | dsschneewiesel7@googlemail.com | Monatsabo (SEPA) | 2 (12.08.) | 07.09. | 4 | keine ID |

## B — Gekündigt + abgelaufen, nie gekickt (32)
| id | Name | E-Mail | Plan | gekündigt | Zugang bis | Tage | Hinweis |
|---|---|---|---|---|---|---|---|
| 30 | Max Wölfle | max.woelfle5@gmail.com | Test | 28.06. | 28.07. | 45 | ⛔ **Max' eigener Account** |
| 77 | Felix Roth | felix.roth87@gmail.com | Jahresabo Launch | 09.07. | 28.07. | 45 | ⚠️ **Klären:** lt. Notiz bis 28.07.2027, Ablefy bucht seit Kündigung nicht mehr ab |
| 134 | Luis Ramallo Pallast | cocorapa@proton.me | Jahresabo Launch | 10.07. | 28.07. | 45 | |
| 138 | Jollmas Halimi | jollmas.halimi76@gmail.com | Monatsabo | 21.07. | 28.07. | 45 | |
| 145 | Maksim Elberg | elbergm@yahoo.de | Jahresabo Launch (SEPA) | 09.07. | 28.07. | 45 | |
| 175 | Tamas Mentes | leon1oroszlan+m@gmail.com | Monatsabo | 21.07. | 28.07. | 45 | |
| 200 | Benny Beifus | bennybeifus@gmail.com | Monatsabo | 24.07. | 29.07. | 44 | |
| 201 | Norbert Block | nblock70@googlemail.com | Jahresabo Launch | 10.07. | 29.07. | 44 | ⚠️ **Klären:** lt. Notiz bis 29.07.2027, Ablefy bucht seit Kündigung nicht mehr ab |
| 227 | Kandid Hofstetter | fcct.hbdqk@passmail.com | Monatsabo | 28.07. | 29.07. | 44 | |
| 256 | Helena Perschnick | lumira7@proton.me | Monatsabo | 10.07. | 30.07. | 43 | |
| 263 | Alexander Titz | alextitz@online.de | Monatsabo | 23.07. | 30.07. | 43 | |
| 302 | Christopher Gantzkow | gantzkow@mein.gmx | Monatsabo | 26.07. | 01.08. | 41 | |
| 338 | Ummahan Arslancik | u.arslancik@gmail.com | Monatsabo | 27.07. | 02.08. | 40 | |
| 354 | Tula Kittelmann | kittelmann.tula@web.de | Monatsabo | 28.07. | 04.08. | 38 | |
| 360 | Markus Horch | markushorch89@gmail.com | Monatsabo | 04.07. | 04.08. | 38 | |
| 355 | Martina Funke | funke.potsdam@freenet.de | Monatsabo (SEPA) | 04.08. | 07.08. | 35 | |
| 390 | Andreas Vogel | andreas.vogel122@hotmail.de | Monatsabo | 27.07. | 07.08. | 35 | |
| 363 | Mert Can Ürer | mertue16@gmail.com | Monatsabo (SEPA) | 05.08. | 08.08. | 34 | |
| 377 | Jörg Pongratz | j.pongi@web.de | Monatsabo (SEPA) | 06.08. | 09.08. | 33 | |
| 402 | Rene Placzko | r.placzko@gmx.de | Monatsabo | 10.08. | 13.08. | 29 | |
| 409 | Georg Heinrich | martaheinrich76@gmail.com | Monatsabo | 08.08. | 15.08. | 27 | |
| 408 | Markus Lang | markus.lang83@gmail.com | Monatsabo (SEPA) | 19.08. | 20.08. | 22 | |
| 427 | Kevin Seeger | seeger-kev@hotmail.de | Monatsabo | 19.08. | 25.08. | 17 | |
| 31 | Ina Herrmann | inaherrmann3@gmx.net | Jahresabo Launch (SEPA) | 06.08. | 28.08. | 14 | ⛔ **TEAM / LIFETIME-FREE** — Marker durch Rate am 03.08. überschrieben |
| 49 | Rico Andres | rico.andres@web.de | Jahresabo Launch (SEPA) | 06.08. | 28.08. | 14 | ⛔ **TEAM / LIFETIME-FREE** — Marker durch Rate am 03.08. überschrieben |
| 63 | Samuel Kaufmann | sam.kaufmann@hotmail.com | Jahresabo Launch | 20.08. | 28.08. | 14 | |
| 137 | Christian Kettenburg | keddek@icloud.com | Monatsabo | 14.08. | 28.08. | 14 | |
| 426 | Kai Radojewski | kai.radojewski@gmail.com | Monatsabo (SEPA) | 05.08. | 29.08. | 13 | |
| 250 | Fritz Mader | fritz.mader@web.de | Monatsabo (SEPA) | 28.07. | 01.09. | 10 | |
| 309 | Ivan Mietz | ivanmietz@web.de | Monatsabo | 03.08. | 01.09. | 10 | |
| 341 | Sascha Duffner | sd@werbewind.com | Monatsabo | 26.08. | 02.09. | 9 | |
| 435 | Mike Malz | hansdampf_derechte@outlook.com | Monatsabo (SEPA) | 03.08. | 03.09. | 8 | gespeicherte Telegram-ID ungültig |

## Entscheidungen Max (11.09.2026)
- **Zahlung fehlgeschlagen:** Hinweis an den Kunden, nach **7 Tagen** entfernen (ohne Dauer-Sperre). Stichprobe bestätigt: Noah Schartz Forte + Nikolai Guenther = echte versäumte Zahlungen.
- **Dirk Schwerdtfeger (361) hat gekündigt** → gehört zu B, nicht A (Ablefy meldete die Kündigung als REVOKE `subscription_canceled`).
- **Selbst gekündigt:** erst zum Ende des bezahlten Zeitraums entfernen, nicht bei der Kündigung.
- **Team (inkl. Ina, Rico) bleibt drin** und wird ignoriert. **Felix Roth + Norbert Block** vorerst drin lassen.
- **Ohne Telegram-ID (47 von 50): ignorieren, nur merken.** IDs evtl. später einsammeln (Client-API-Abgleich über die Einladungslinks oder passiv über Auto-Capture/Support-Bot).
- **Mit Telegram-ID bleiben 3:** Noah Schartz Forte (434) — **✅ am 11.09. 13:32 UTC entfernt** (ohne Dauer-Sperre, Link widerrufen, bei Nachzahlung automatisch zurück), Nikolai Guenther (432, schon raus), Mike Malz (435, gespeicherte ID ungültig).

## Ursprünglich offene Punkte (Stand vor Max' Entscheidungen)
1. **A — Frist:** Wie viele Tage nach Ablefys Pause wird entfernt? Vorschlag: Tag 0 Pause → Hinweis an den Kunden („Zahlung fehlgeschlagen, bitte Zahlungsmittel aktualisieren“), **Tag 7 → entfernen ohne Dauer-Sperre** — zahlt er nach, holt ihn die Auto-Reaktivierung automatisch zurück. Für die 18 Altfälle ist die Frist längst abgelaufen.
2. **B:** Direkt entfernen (Kündigung ist ihr eigener Wille, Zugang lt. Ablefy abgelaufen)?
3. **Felix Roth + Norbert Block:** drin lassen (wie notiert bis 2027) oder raus?
4. **Ina + Rico:** LIFETIME-Marker wiederherstellen + im Code verhindern, dass eine Zahlung ihn überschreibt?
5. **Telegram-IDs:** Ohne IDs kann der Bot 47 der 50 nicht entfernen. Empfehlung: einmaliger Abgleich über die Telegram-Client-API mit Max' Admin-Account („wer ist über welchen Einladungslink beigetreten“) → IDs für alle ~450 Kunden, schließt nebenbei die 10 Altfälle aus dem Audit vom 04.09. Alternative: manuell in Telegram.
