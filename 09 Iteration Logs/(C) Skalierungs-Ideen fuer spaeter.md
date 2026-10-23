# (C) Skalierungs-Ideen für später

> Erstellt: 2026-05-08
> Zuletzt aktualisiert: 2026-05-15

## ✅ Umgesetzt: Minimum-Qty Fallback

Wenn die skalierte Qty unter dem Exchange-Minimum liegt, wird auf das Minimum aufgerundet — sofern der Kunde genug freie Margin hat. So bekommen auch kleine Kunden Trades mit.

## ✅ Umgesetzt: Customer Balance von API / WebSocket

Kunden-Balance wird in Echtzeit über WebSocket getrackt (`customer_ws.py`). Balance und freie Margin werden bei jedem `perpAccount.update` aktualisiert. Kein Hardcoding mehr.

## 🔲 Noch offen

### 1. Dynamische Mindesteinzahlung beim Onboarding
- Feste Untergrenze: **5% von Max' aktueller Balance**, mindestens aber **500 USDT**
- Wird beim Registrierungsprozess geprüft
- Beispiel: Max = 10K → Mindestens 500 USDT. Max = 50K → Mindestens 2.500 USDT

### 2. Warnsystem bei niedriger Balance
- Wenn ein Kunde zu wenig freie Margin für einen Minimum-Trade hat:
  - Im Dashboard warnen: „Balance zu niedrig — Trades werden übersprungen"
  - Optional: Max benachrichtigen
  - Kunde bleibt aktiv, bekommt nur keine neuen Trades

### 3. Risk-Based Position Sizing
- Statt feste proportionale Skalierung: **X% des Accounts pro Trade** riskieren
- Kunde kann im Dashboard sein Risiko-Level einstellen (z.B. 1%, 2%, 5% pro Trade)
- Position Size wird basierend auf SL-Distanz und gewähltem Risiko berechnet
- Vorteil: Konsistentes Risiko unabhängig von der Trade-Größe des Masters

### 4. Max Concurrent Positions Limit
- Obergrenze für gleichzeitig offene Positionen pro Kunde
- Verhindert Überexposure bei kleinen Accounts
- Wenn Limit erreicht: neue Trades überspringen und Kunde benachrichtigen
- Konfigurierbar pro Kunde (z.B. Standard: 5, Premium: 10)

### 5. Drawdown Protection
- Auto-Pause wenn Kunde einen bestimmten Drawdown überschreitet (z.B. -15% vom Startkapital)
- Kunde bekommt Benachrichtigung: „Copy Trading pausiert — Drawdown-Limit erreicht"
- Reaktivierung nur manuell durch den Kunden (bewusste Entscheidung)
- Schützt Kunden vor Verlusten in schlechten Phasen

### 6. Performance-Based Scaling
- Dynamische Anpassung der Position Size basierend auf aktueller Performance
- Bei Winning Streak: schrittweise hochskalieren (z.B. +10% pro 3 Gewinn-Trades)
- Bei Losing Streak: automatisch runterskalieren (z.B. -20% pro 3 Verlust-Trades)
- Zurück auf Normalwert nach X Trades oder manuell
- Vorsicht: Klar kommunizieren, dass dies experimentell ist
