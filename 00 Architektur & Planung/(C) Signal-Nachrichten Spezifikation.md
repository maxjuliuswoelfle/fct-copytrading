# (C) Signal-Nachrichten Spezifikation
> ↩ [[CLAUDE|Copy Trading Bot]]

Alle 16 Nachrichten-Typen fuer die Paid Signal Telegram-Gruppe.
Basierend auf dem Whiteboard-Workshop vom 02.06.2026.

---

## Risikobewertung (fuer alle Open-Signale)

| Level | Anzeige | Label |
|-------|---------|-------|
| 1/5 | 🟩⬜️⬜️⬜️⬜️ | solide |
| 2/5 | 🟩🟩⬜️⬜️⬜️ | moderat |
| 3/5 | 🟨🟨🟨⬜️⬜️ | ausgewogen |
| 4/5 | 🟨🟨🟨🟨⬜️ | aggressiv |
| 5/5 | 🟥🟥🟥🟥🟥 | spekulativ |

**Berechnung:** Basiert auf Hebel × Position-Groesse relativ zum Account.
- 1-5x Hebel → solide
- 6-15x Hebel → moderat
- 16-25x Hebel → ausgewogen
- 26-50x Hebel → aggressiv
- 51x+ Hebel → spekulativ

> Muss ggf. verfeinert werden — erstmal Hebel als Hauptindikator.

---

## Berechnete Werte

**CRV (Chance-Risiko-Verhaeltnis):**
```
CRV = |TP - Entry| / |SL - Entry|
```

**TP/SL Prozent vom Entry:**
```
Long:  TP% = (TP - Entry) / Entry × 100
       SL% = (Entry - SL) / Entry × 100

Short: TP% = (Entry - TP) / Entry × 100
       SL% = (SL - Entry) / Entry × 100
```

**Wie geschlossen (Close-Type):**
- **TP getroffen** — Exit-Preis ≈ TP-Preis (±0.1%)
- **SL getroffen** — Exit-Preis ≈ SL-Preis (±0.1%) UND SL war nicht im Gewinn
- **SL im Gewinn getroffen** — Exit-Preis ≈ SL-Preis UND SL lag im Gewinn (Long: SL > Entry, Short: SL < Entry)
- **Manuell geschlossen** — keiner der obigen Faelle

**Trade-Dauer:**
```
Dauer = Close-Timestamp - Open-Timestamp
Format: "X Tage Xh" oder "Xh Xmin" (wenn < 24h)
```

---

## 1. Neue Position (Market Order)

> Trigger: `TRADE_FILLED` mit `closedPnL == 0` UND `ordType == "Market"`

```
🟢 Neue Position — BTC Short #1

Entry:       69.556$
TP:          65.000$ (+6,5%)
SL:          70.200$ (-0,9%)
Type:        Market Order
Hebel:       10x
CRV:         7,1
Risiko:      🟩🟩⬜️⬜️⬜️ moderat

⚡ FirstClass Trading · Premium Signal
```

**Felder:**
- Display-Name (BTC Short #1)
- Entry-Preis
- TP + Prozent-Distanz (falls gesetzt)
- SL + Prozent-Distanz (falls gesetzt)
- Type: "Market Order"
- Hebel
- CRV (falls SL + TP gesetzt)
- Risikobewertung

---

## 2. Neue Limit Order (neue Position)

> Trigger: `OPEN_TRADE` mit `ordType == "Limit"` UND keine bestehende Position fuer dieses Symbol+Side

```
🟡 Neue Limit Order — ETH Long #1

Entry:       2.450,00$
TP:          2.680,00$ (+9,4%)
SL:          2.380,00$ (-2,9%)
Hebel:       10x
CRV:         3,3
Risiko:      🟩🟩⬜️⬜️⬜️ moderat

⏳ Wartet auf Ausfuehrung

⚡ FirstClass Trading · Premium Signal
```

**Felder:**
- Display-Name
- Limit Entry-Preis
- TP + Prozent-Distanz (falls im selben Batch gesetzt)
- SL + Prozent-Distanz (falls im selben Batch gesetzt)
- Hebel
- CRV (falls SL + TP vorhanden)
- Risikobewertung

---

## 3. Limit Order hinzugefuegt (fuer bestehende Position)

> Trigger: `OPEN_TRADE` mit `ordType == "Limit"` UND bestehende Position fuer dieses Symbol+Side existiert

```
🟡 Limit Order hinzugefuegt

Fuer BTC Short #1
Limit Preis: 69.203$

⏳ Wartet auf Ausfuehrung

⚡ FirstClass Trading · Premium Signal
```

**Felder:**
- Referenz auf bestehenden Trade (Display-Name)
- Limit-Preis

---

## 4. Limit Order ausgefuehrt (neue Position)

> Trigger: `TRADE_FILLED` mit `closedPnL == 0` UND `ordType == "Limit"` UND war vorher als Limit Order getracked

```
🟢 Limit Order ausgefuehrt

BTC Short #1
Entry: 72.300$

⚡ FirstClass Trading · Premium Signal
```

**Felder:**
- Display-Name
- Ausgefuehrter Preis

---

## 5. Limit Order ausgefuehrt (Nachkauf)

> Trigger: `TRADE_FILLED` mit `closedPnL == 0` UND Limit Order war als Nachkauf getracked (bestehende Position)

```
✅ Limit Order ausgefuehrt — Nachkauf

BTC Short #1
Nachkauf @   71.500$
Avg Entry:   71.800$

⚡ FirstClass Trading · Premium Signal
```

**Felder:**
- Display-Name
- Ausgefuehrter Preis
- Neuer Durchschnitts-Entry

---

## 6. Limit Order storniert

> Trigger: `CANCEL_TRADE` UND die gecancelte Order war eine Limit Order

```
⚪ Limit Order storniert

BTC Short #1
Limit war: 72.100$

⚡ FirstClass Trading · Premium Signal
```

**Felder:**
- Display-Name
- Urspruenglicher Limit-Preis

---

## 7. Position geschlossen

> Trigger: `CLOSE_TRADE` (Size geht auf 0)

```
🔴 Position geschlossen — BTC Short #1

✅ Gewinn: +45,00%
Entry:       72.100$
Exit:        69.200$
Dauer:       2 Tage 4h
Geschlossen: Take Profit getroffen

⚡ FirstClass Trading · Premium Signal
```

Variante bei Verlust:
```
🔴 Position geschlossen — BTC Short #1

❌ Verlust: -12,00%
Entry:       72.100$
Exit:        73.200$
Dauer:       4h 23min
Geschlossen: Stop Loss getroffen

⚡ FirstClass Trading · Premium Signal
```

**Felder:**
- Display-Name
- P&L in Prozent (Kursaenderung × Hebel) mit Gewinn/Verlust-Emoji
- Entry-Preis
- Exit-Preis
- Trade-Dauer
- Close-Type: "Take Profit getroffen" / "Stop Loss getroffen" / "SL im Gewinn getroffen" / "Manuell geschlossen"

---

## 8. Teilschliessung (Scale-Out)

> Trigger: `SCALE_OUT` (Size wird kleiner, aber > 0)

```
📉 Trade Update — BTC Short #1

Ich habe soeben 35% der Profite genommen.
Exit:        72.300$
Verbleibend: 65%

⚡ FirstClass Trading · Premium Signal
```

**Felder:**
- Display-Name
- Prozentsatz der geschlossenen Position
- Exit-Preis
- Verbleibender Anteil

---

## 9. Nachkauf / Scale-In (Market Order)

> Trigger: `SCALE_IN` (Size wird groesser) — bei Market Order (nicht Limit-Fill)

```
📈 Position Skalierung — BTC Short #1

Scale-In / Nachkauf
Nachkauf @   71.500$
Avg Entry:   71.800$

⚡ FirstClass Trading · Premium Signal
```

**Felder:**
- Display-Name
- Nachkauf-Preis
- Neuer Durchschnitts-Entry

---

## 10. SL Anpassung

> Trigger: `SET_SL` (neuer SL oder SL verschoben)

Variante — SL in den Gewinn:
```
⚙️ Trade Management — BTC Short #1

🛡️ Stop Loss angepasst — im Gewinn ✅
SL: 72.200$ → 71.150$

⚡ FirstClass Trading · Premium Signal
```

Variante — SL auf Break-Even:
```
⚙️ Trade Management — BTC Short #1

🛡️ Stop Loss angepasst — Break-Even
SL: 73.200$ → 72.100$

⚡ FirstClass Trading · Premium Signal
```

Variante — normaler SL Move:
```
⚙️ Trade Management — BTC Short #1

🛡️ Stop Loss angepasst
SL: 73.200$ → 72.800$

⚡ FirstClass Trading · Premium Signal
```

**Felder:**
- Display-Name
- Alter SL → Neuer SL
- Kontext: "im Gewinn" (SL im Profit), "Break-Even" (SL ≈ Entry ±0.2%), oder nichts

---

## 11. TP Anpassung

> Trigger: `SET_TP` (neuer TP oder TP verschoben)

```
⚙️ Trade Management — BTC Short #1

🎯 Take Profit angepasst
TP: 69.200$ → 68.500$

⚡ FirstClass Trading · Premium Signal
```

**Felder:**
- Display-Name
- Alter TP → Neuer TP

---

## 12. SL entfernt

> Trigger: `CANCEL_SL`

```
⚙️ Trade Management — BTC Short #1

🛡️ Stop Loss entfernt

⚡ FirstClass Trading · Premium Signal
```

---

## 13. TP entfernt

> Trigger: `CANCEL_TP`

```
⚙️ Trade Management — BTC Short #1

🎯 Take Profit entfernt

⚡ FirstClass Trading · Premium Signal
```

---

## 14. Hebel Anpassung

> Trigger: `UPDATE_LEVERAGE`

```
⚙️ Trade Management — BTC Short #1

⚖️ Hebel angepasst
Hebel: 10x → 100x

⚡ FirstClass Trading · Premium Signal
```

**Felder:**
- Display-Name
- Alter Hebel → Neuer Hebel

---

## 15. Margin Anpassung

> Trigger: `UPDATE_MARGIN`

Variante — Margin hinzugefuegt:
```
⚙️ Trade Management — BTC Short #1

💰 Zusaetzliche Margin hinzugefuegt
Liquidierungspreis liegt jetzt bei 72.465$

⚡ FirstClass Trading · Premium Signal
```

Variante — Margin reduziert:
```
⚙️ Trade Management — BTC Short #1

💰 Margin reduziert

⚡ FirstClass Trading · Premium Signal
```

**Felder:**
- Display-Name
- Richtung (Increase / Decrease)
- Liquidierungspreis (falls verfuegbar aus Position-Daten)

---

## 16. Offene Positionen (Taegliche Uebersicht)

> Trigger: Geplant — jeden Tag um 21:00 deutscher Zeit (19:00 UTC)

```
📋 Offene Positionen

Aktive Trades:
📊 BTC Short #1    →  +2,10%  (10x)
📊 ETH Long #1     →  -0,80%  (15x)
📊 SOL Short #2    →  +12,40% (20x)

Offene Limit Orders:
⏳ DOGE Long       →  Limit @ 0,1450$
⏳ BTC Short #1    →  Nachkauf @ 68.500$

⚡ FirstClass Trading · Premium Signal
```

Variante — keine Positionen:
```
📋 Offene Positionen

Aktuell keine aktiven Trades oder Limit Orders.

⚡ FirstClass Trading · Premium Signal
```

**Felder:**
- Alle aktiven Positionen mit Display-Name, aktuellem P&L (%), Hebel
- Alle offenen Limit Orders mit Display-Name, Limit-Preis, ggf. "Nachkauf" Label

---

## Zusammenfassung

| # | Typ | Trigger | Emoji |
|---|-----|---------|-------|
| 1 | Neue Position | TRADE_FILLED (Market) | 🟢 |
| 2 | Neue Limit Order | OPEN_TRADE (Limit, neue Pos.) | 🟡 |
| 3 | Limit hinzugefuegt | OPEN_TRADE (Limit, bestehende Pos.) | 🟡 |
| 4 | Limit ausgefuehrt (neu) | TRADE_FILLED (Limit, neue Pos.) | 🟢 |
| 5 | Limit ausgefuehrt (Nachkauf) | TRADE_FILLED (Limit, bestehende Pos.) | ✅ |
| 6 | Limit storniert | CANCEL_TRADE (Limit) | ⚪ |
| 7 | Position geschlossen | CLOSE_TRADE | 🔴 |
| 8 | Teilschliessung | SCALE_OUT | 📉 |
| 9 | Nachkauf (Market) | SCALE_IN | 📈 |
| 10 | SL Anpassung | SET_SL | ⚙️ |
| 11 | TP Anpassung | SET_TP | ⚙️ |
| 12 | SL entfernt | CANCEL_SL | ⚙️ |
| 13 | TP entfernt | CANCEL_TP | ⚙️ |
| 14 | Hebel Anpassung | UPDATE_LEVERAGE | ⚙️ |
| 15 | Margin Anpassung | UPDATE_MARGIN | ⚙️ |
| 16 | Offene Positionen | Taeglich 21:00 DE | 📋 |

---

## Offene Fragen

1. **Risikobewertung** — Aktuell rein auf Hebel basiert. Soll Position-Groesse relativ zum Account auch einfliessen?
2. **Liquidierungspreis bei Margin** — Kommt der zuverlaessig aus der Levex API? (Feld `liquidationPrice` in PerpPosition existiert)
3. **TP/SL bei Limit Orders** — Werden TP/SL schon gesetzt bevor die Limit Order gefuellt wird, oder erst danach?
4. **Offene Positionen Timing** — 21:00 deutscher Zeit = 19:00 UTC (Sommer) / 20:00 UTC (Winter). Sommer/Winter automatisch handeln?
