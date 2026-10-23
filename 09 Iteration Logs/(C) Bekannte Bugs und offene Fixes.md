# (C) Bekannte Bugs und offene Fixes
> ↩ [[CLAUDE|Copy Trading Bot]] · [[CLAUDE|Life OS]]

Ergebnis des kompletten Bot-Audits vom **2026-06-30**. Fokus: Zustände, die angelegt aber nicht sauber aufgeräumt/aktualisiert werden (gleiche Bug-Klasse wie der Limit-Storno-Bug), plus generelle Logikfehler.

**Legende:** 🔴 kritisch · 🟡 mittel · 🔵 niedrig · ✅ erledigt

---

## ✅ Bereits gefixt (2026-06-30)

- **Stornierte Limit-Order blieb in DB aktiv** → `signal_bot.py` `_send_single_event`: bei `limit_cancelled` wird der Display-Name jetzt deaktiviert (nur wenn keine echte Live-Position existiert). Deployed.
- **#1 Wartende Limit-Order erschien als „offener Trade" in der 21:00-Übersicht** → `_send_daily_overview` zeigt jetzt nur noch Einträge mit echter Live-Position (Parser-State) als „Aktive Trades"; wartende Limits erscheinen nur unter „Offene Limit Orders". Deployed.
- **#2 Hebel in der Übersicht abgeschnitten** (7,5x → 7x) → nutzt jetzt `_fmt_leverage()`. Deployed.
- **#5 Kein Retry beim Senden** → `_send_to_group` versucht jetzt bis zu 3× zu senden: 429 = warten wie Telegram via `retry_after` vorgibt (gedeckelt), 5xx/Netzfehler = Backoff (1s, 2s), 4xx = kein Retry. Deployed.
- **#6 Scale-In-Doppelung über Batch-Grenzen** → statt `_limit_filled_positions` (pro Batch geleert) jetzt `_recent_limit_fills` (positionID → Zeitpunkt, 8s-Fenster, überlebt Batch-Grenzen, unterdrückt genau EIN Scale-In). Deployed.
- **#7 Ein fehlerhaftes Event stoppt den Rest des Batches** → jedes Event in `_process_debounced_batch` jetzt einzeln in `try/except`; ein Fehler überspringt nur dieses Event, die übrigen werden gesendet. Deployed.

### Limit-Order-Editieren (2026-07-04)
- **Amend gab kein Signal** → `_classify` behandelte `BotAction.AMEND_TRADE` gar nicht. Neuer Zweig + Formatter „🔄 Limit Order angepasst — Einstieg X → Y" (nur `ordType==Limit`); Parser-Event um `positionID`/`side`/`posSide`/`ordType` angereichert. Deployed.
- **Revert labelte Re-Placement als „Nachkauf"** → Cancel+Replace (neue OrderID) erzeugte ein OPEN-Limit, das als `limit_added` gepostet wurde, obwohl keine offene Position existiert. Jetzt: `limit_added` nur bei echter Live-Position (`_has_live_position`), sonst `new_limit`. Deployed.
- **Wartende Limit fehlte in der 21:00-Übersicht nach Neustart** → Übersicht las Limits nur aus dem flüchtigen In-Memory-Dict `_pending_limits`, das bei Snapshot/Reconnect nicht neu befüllt wird. Jetzt aus neuer Parser-Methode `get_pending_limit_orders()` (aus `_active_orders`, überlebt Reconnect). Deployed. (Ersetzt faktisch den Rest-Edgecase hinter #3/#4 für die Übersicht.)

---

## 🟡 Signal-Bot — noch offen (live, Phase 1)

- **#3/#4 Rest-Edgecase (kosmetisch):** Neustart genau im Fenster zwischen Limit-Einstellen und Ausführen → der spätere Fill wird als „Nachkauf" statt „neue Position" gelabelt (Ursache: `get_signal_display_name` ignoriert `is_active`). Übersicht ist durch #1-Fix korrekt; nur das Nachrichten-Label im seltenen Timing falsch. Niedrige Prio.

- **#8 Zeitzonen-Fehler Übersicht** (`signal_bot.py:1414`): im Winter feuert die 21:00-Übersicht eine Stunde zu früh (20:00 lokal). Kosmetisch.

- **Cancel+Replace = zwei Nachrichten statt einer** (2026-07-04): Wenn Levex ein Limit-Editieren als Cancel+Replace (neue OrderID) statt als in-place-Amend sendet, kommen zwei (korrekte) Nachrichten: „Limit storniert" + „Neue Limit Order". Zum Zusammenfassen zu EINER „angepasst"-Nachricht müsste ein echtes Cancel+Replace-Event gecaptured werden (Levex `action`-Feld = „Replace" verifizieren), dann Batch-Korrelation über `positionID`. Niedrige Prio — beide Nachrichten sind inhaltlich richtig.

## 🔵 Parser — noch offen (beide Phasen)

- **#9 Speicher-Leck** (`parser.py:210, 27`): `_positions` und `_last_sl_tp` werden für geschlossene Positionen nie entfernt → wächst langsam + Fallback-Schleifen iterieren veraltete Einträge. → Fix: geschlossene Positionen nach Close entfernen.

---

## 🔴 Execution-Engine — VOR dem Copy-Trading-Launch fixen (Phase 2, aktuell keine Copy-Trading-Kunden)

- **#10 🔴 `_handle_cancel_trade` deaktiviert das Mapping nicht** (`execution.py:450`)
  Strukturell identisch zum Signal-Bug: Order wird beim Kunden storniert, aber `position_mappings` bleibt `is_active=1`. Das verwaiste Mapping blockiert via `_has_mapping_for_symbol` einen späteren echten Trade auf demselben Symbol → wird nicht gespiegelt.

- **#11 🔴 `_handle_amend_trade`: Cancel+Replace ohne Ergebnis-Prüfung** (`execution.py:463-497`)
  Alte Order gecancelt, neue platziert — Ergebnis nicht geprüft, `customer_position_id` nicht aktualisiert. Schlägt das Replace fehl, zeigt das Mapping auf eine gecancelte Order → alle folgenden SL/TP/Close laufen ins Leere.

- **#12 🟡 Reconciliation-Asymmetrie** (`execution.py:907-940`)
  (a) Kunde inaktiv → Mapping in DB geschlossen, aber echte Kunden-Position bleibt offen & ungemanagt. (b) Close-Fehler → Mapping bleibt aktiv, aber ohne Retry/Telegram-Alert (leicht zu übersehen).

- **#13 🟡 `_has_mapping_for_symbol` zu grob für Multi-Trade** (`execution.py:270/370`)
  Prüft nur „existiert irgendein Mapping für Symbol+Kunde". Bei mehreren Positionen pro Symbol (Master fährt aktuell 2 BTC-Shorts) wird die zweite legitime Position als Duplikat übersprungen.

- **#14 🔵 Deaktivierte Kunden-WS-Tasks laufen endlos weiter** (`listen.py` / `customer_ws.py`)
  Wird ein Kunde im Dashboard deaktiviert, wird seine WebSocket-Task nicht gecancelt und nicht aus `customer_ws_connections` / `engine._customers` entfernt → reconnectet ewig, schreibt weiter Balance.

- **#15 🔵 `_open_locks` wächst monoton** (`execution.py:97`): kleiner Dauer-Leak pro Symbol×Kunde.

- **#16 🔵 Operator-Präzedenz-Smell** (`execution.py:891`): `float(pos.size) if pos.size else 0.0 > 0` vergleicht nicht wirklich gegen `> 0`, wenn `size` gesetzt ist. Bei positiven Größen harmlos, aber falsch geschrieben.

---

## Sauber (kein Handlungsbedarf)
- DB-Mapping-CRUD (Upsert/Close, korrekt auf `is_active=1` gefiltert)
- Snapshot-Guard (`is_snapshot` → kein Senden, keine Execution)
- Reconciliation der Signal-Namen beim Snapshot (nur bei vollständigem Snapshot)
- Heartbeat-Task-Cleanup in `customer_ws.py`
