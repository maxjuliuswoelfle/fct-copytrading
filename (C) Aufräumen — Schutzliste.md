# (C) Aufräumen — Schutzliste FCT Copytrading
> ↩ [[CLAUDE|FCT Copytrading]] · [[CLAUDE|Life OS]]

> **Zweck:** Bevor in diesem Projektordner irgendetwas gelöscht, umbenannt oder verschoben wird — **erst diese Datei lesen.** Hier steht, was produktiv läuft, was nur Doku ist und was tatsächlich Ballast ist.
>
> **Stand:** 2026-10-27

> ⚠️ **Geltungsbereich:** Diese Datei deckt **nur** `FCT/Copytrading/` ab. Für den restlichen Vault gilt die übergeordnete Liste → [[FCT/FCT OS/03 Anleitungen/(C) Vault aufräumen — Schutzliste|(C) Vault aufräumen — Schutzliste]].

---

## Die eine Regel, die alles erklärt

Dieses Projekt ist **kein Notizordner — es ist ein laufendes Produktivsystem mit echten zahlenden Kunden.** Ein Teil der Dateien hier sind **Spiegelungen von Code, der gerade auf dem Server läuft** und echtes Geld anderer Leute bewegt.

**Daraus folgt:**
- Das Löschen einer Vault-Datei bricht **nichts** auf dem Server (der Server hat seine eigenen Kopien).
- **Aber:** Wer eine Code-Datei hier löscht, verliert die lokale Referenz, gegen die jeder Fix gebaut und jeder Diff geprüft wird. Beim nächsten Patch wird dann blind am Live-System gearbeitet.
- **Und:** Die Doku-Dateien sind keine hübschen Notizen, sondern die **einzige Quelle für Kundenfälle, Entscheidungen und Fehlerursachen**. Ohne sie fängt jede Session bei null an.

---

## 🔴 TABU — niemals löschen, umbenennen oder verschieben

### Die zwei Anker-Dateien im Projekt-Root
| Datei | Warum |
|---|---|
| `CLAUDE.md` | **Die wichtigste Datei des ganzen Projekts.** Enthält den kompletten laufenden Kontext: jeden Kündigungsfall, jede Entscheidung, jede gefundene Bug-Ursache, alle Zugangsdaten-Hinweise. Ein Verlust = kompletter Gedächtnisverlust über ~5 Monate Betrieb. **Nicht kürzen, nicht ausmisten, nicht „aufräumen".** |
| `COMMANDS.md` | Alle Server- und Management-Befehle, copy-paste-ready. Wird im Störfall gebraucht. |

### Live-Code — Spiegelung des Produktivsystems
| Ordner | Warum |
|---|---|
| `01 Bot-Core/` | **Der laufende Trading-Bot.** 15+ Python-Dateien (`listen.py`, `parser.py`, `execution.py`, `signal_bot.py`, `telegram.py`, `database.py` …). Spiegelt `/home/botuser/copy-trading-bot/` auf dem Server. Jeder Fix wird gegen diese Dateien gediffed. |
| `03 Dashboard/MVP 1.0/` | **Das laufende Kunden-Dashboard** (FastAPI, Login, Onboarding, Webhooks). Inklusive `routes/`, `templates/`, `static/`. Spiegelt `/home/botuser/dashboard/`. Enthält u. a. die Ablefy-Webhook-Logik — die Stelle, an der Zahlungen verarbeitet werden. |
| `04 Landingpage/` | Die **live ausgelieferten** HTML-Dateien der Verkaufsseite (IONOS Webspace) inkl. Rechtsseiten (Impressum, AGB, Datenschutz, Risikohinweis). Die Rechtsseiten sind die rechtsverbindlich veröffentlichten Texte. |

> **Merker zu `04 Landingpage/`:** Es gibt zwei Unterordner — `Landingapge/` (normale Seite, Tippfehler im Namen ist historisch, **nicht umbenennen** ohne Deploy-Abgleich) und `Event Landingpage/` (Launch-Version). In der Event-Version steckt ein **auskommentierter Testimonial-Block**, der später wieder rein soll.

### Doku, die durch nichts zu ersetzen ist
| Datei | Warum |
|---|---|
| `10 Security/(C) Security Audit.md` | Vollständiger Sicherheits-Audit inkl. der **noch offenen Punkte**. |
| `00 Architektur & Planung/(C) Systemarchitektur.md` | Wie das System funktioniert. |
| `00 Architektur & Planung/(C) Levex API Reference.md`<br>`(C) Levex Perpetual REST API.md` | **Die Exchange-Doku existiert nirgendwo sonst in dieser Form.** Mehrere Bugs wurden nur mit diesen Dateien gefunden. |
| `00 Architektur & Planung/(C) Onboarding Flow — Bauplan.md` | Der komplette Kaufprozess inkl. Ablefy-Payload-Semantik. |
| `00 Architektur & Planung/(C) Signal-Nachrichten Spezifikation.md` | Wie jedes Signal in der Telegram-Gruppe aussehen muss. |
| `09 Iteration Logs/(C) Bekannte Bugs und offene Fixes.md` | 16 dokumentierte Befunde, mehrere davon **noch offen und kritisch** vor dem Copy-Trading-Launch. |
| `08 AI Support/(C) AI Support Agent — Bauplan.md`<br>`(C) Wissensbasis Support.md` | Aktives Projekt, wird gerade gebaut. |

### Aktiv laufende Automatisierung
| Datei | Warum |
|---|---|
| `07 System/(C) revoke_access_daily.py` | **Läuft täglich scharf auf dem Server** und entzieht gekündigten Kunden den Zugang. Ersetzt die 49 alten Einzel-Timer. |
| `07 System/(C) support_tools.py` | Read-only Tools für den AI-Support-Agent (in Arbeit). |
| `07 System/support_bot.py` | Der Support-Bot, über den Kunden schreiben. |
| `07 System/(C) migrate_kick_timers.py` | Migrations-Script der Timer-Konsolidierung — Beleg, wie die aktuelle Tabelle entstanden ist. |

---

## 🟡 VORSICHT — nur nach Rückfrage anfassen

| Was | Einschätzung |
|---|---|
| `07 System/kick-*.service` + `kick-*.timer` + `kick_*.sh` (**~145 Dateien**) | Das sind Kopien der **49 Einzel-Timer, die am 28.09.2026 abgeschaltet wurden** (ersetzt durch den konsolidierten Tagesjob). Sie laufen nicht mehr → technisch Ballast. **ABER:** Auf dem Server sind sie nur *deaktiviert*, nicht gelöscht — sie sind der dokumentierte Rollback-Weg. Außerdem sind sie Belege zu konkreten Kundenfällen. **→ Empfehlung: in einen Unterordner `07 System/_Archiv Kick-Timer/` verschieben statt löschen.** Die Wiki-Links in `CLAUDE.md` müssen dabei mitgezogen werden. |
| `07 System/(C) patch_*.py` | Einmal-Patches, die bereits deployed sind. Sie dokumentieren **wie** eine Live-Änderung entstanden ist (inkl. Backup-Namen auf dem Server). Behalten, solange der jeweilige Code live ist. |
| `07 System/(C) check_*.py` / `(C) probe_*.py` / `(C) test_*.py` | Diagnose-Scripts aus konkreten Fehlersuchen. Mehrere davon wurden mehrfach wiederverwendet. Niedriges Risiko, aber kein Platzgewinn. |
| `09 Iteration Logs/(C) Nichtzahler-Check 2026-09-11.md` | Momentaufnahme mit 50 offenen Fällen — Teile davon sind **noch nicht abgearbeitet**. Erst löschen, wenn alle Entscheidungen umgesetzt sind. |
| `11 Performance/` | Auswertung + CSV vom 30.09. Wird für Marketing-Zahlen auf der Landingpage herangezogen. Bei neuer Auswertung die alte ersetzen, nicht sammeln. |
| `.claude/` | Projekt-Konfiguration (Agents, Commands, Skills). Nicht „mal eben" löschen. |
| `.obsidian/` | Obsidian-Konfiguration. |

---

## 🟢 BALLAST — kann weg, hier liegt der eigentliche Gewinn

**Der Ordner ist 882 MB groß. Davon sind 602 MB ein einziger Attachments-Ordner.**

| Was | Größe | Einschätzung |
|---|---|---|
| `06 Attachments/DankeVideoReady.mp4` | **542 MB** | **Der mit Abstand größte Brocken im ganzen Projekt — 61 % des Gesamtvolumens.** Das Danke-Video wird live über **Wistia** ausgeliefert, nicht aus dem Vault. Die Datei hier ist nur das Rohmaterial. **→ Raus aus dem Vault** (Google Drive / externe Platte). Ein Vault ist kein Videoarchiv — das bremst Sync und Suche spürbar. |
| `06 Attachments/Signal Nachrichten/` (9 Dateien) | **60 MB** | Screenshots/Referenzbilder der Signal-Formate. Die Formate sind inzwischen in `(C) Signal-Nachrichten Spezifikation.md` **in Textform dokumentiert**. → Auf 1–2 Referenzbilder eindampfen. |
| `01 Bot-Core/__pycache__/` | 280 KB | Kompilierte Python-Caches. **Pure Wegwerfdateien**, werden automatisch neu erzeugt. Löschen. |
| `03 Dashboard/MVP 1.0/__pycache__/` | 36 KB | Dito. Löschen. |
| `01 Bot-Core/_patch_limit_added.py` | — | Einmal-Patch mit Unterstrich-Prefix (= Arbeitsdatei), liegt im **Code-Ordner statt in `07 System/`**. → Nach `07 System/` verschieben oder löschen. |
| `04 Landingpage/Landingapge/index_OLD_backup.html` | — | Explizit als Backup benannte Altversion der Landingpage. Die aktuelle Version ist live. → Löschen. |
| `06 Attachments/perpclosedpnl_2026-06-28.csv` | 44 KB | Export vom Launch-Tag. Die Performance-Auswertung liegt aktueller in `11 Performance/`. → Löschen, wenn nicht mehr gebraucht. |
| `07 System/check_ids.py`, `get_orders.py`, `verify.py`, `verify_tg.py`, `probe_*.py` | — | Namenlose Wegwerf-Scripts **ohne `(C)`-Prefix** = alte Ad-hoc-Hilfen. Niedriger Wert. |

**Realistischer Gewinn: ~600 MB, also rund zwei Drittel des Projektordners — und zwar fast vollständig aus EINER Videodatei und EINEM Bilderordner.** Das ganze Herumschieben von Scripts bringt dagegen kaum Platz. Wer schlank werden will, fängt bei den Medien an, nicht beim Code.

---

## Regeln für den Aufräum-Chat

1. **Nichts löschen, was im `CLAUDE.md` verlinkt ist**, ohne den Wiki-Link gleich mitzuziehen — sonst entstehen tote Links und die Graph-Ansicht bricht.
2. **Verschieben schlägt Löschen.** Bei allem Gelben: Unterordner `_Archiv/` anlegen.
3. **Keine Datei ohne `(C)`-Prefix bearbeiten, ohne vorher zu fragen** (Projektregel).
4. **Der Server wird dabei nicht angefasst.** Kein `ssh`, kein Service-Neustart, nichts. Aufräumen passiert ausschließlich lokal im Vault.
5. **Große Dateien zuerst.** Nach `du -sh *` sortieren, oben anfangen — das spart die 90 % Arbeit, die nichts bringt.
6. **Nach dem Aufräumen:** Abschnitt „Verknüpfte Dateien" in `CLAUDE.md` gegen den tatsächlichen Ordnerinhalt prüfen.

---

## Was in diesem Projekt NICHT zur Debatte steht

- Der Ordner selbst wird **nicht** nach `Done/` verschoben. Das Produkt ist **live und zahlend**.
- Die Ordnernummerierung (`00`–`11`) bleibt. Sie ist in dutzenden Wiki-Links und in Server-Scripts referenziert. Eine Umbenennung von `07 System/` zu „Scripts" o. Ä. zerschießt die halbe Doku.
- Die Lücke bei `02` und der Tippfehler `Landingapge` sind **historisch gewachsen und harmlos** — kosmetische Korrekturen hier kosten mehr als sie bringen.
