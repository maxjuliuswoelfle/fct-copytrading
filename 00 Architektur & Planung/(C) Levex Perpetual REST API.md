# (C) Levex Perpetual REST API — Copy Trading Endpoints

> Quelle: Levex IT (Google Doc, Stand 2026-05-08)
> Für den Copy Trading Bot — Trade Execution auf Kunden-Accounts

---

## Authentifizierung

### Environments
- **Testnet:** `https://api-testnet.levex.com`
- **Production:** `https://api.levex.com`

### Headers
| Header | Beschreibung |
|--------|-------------|
| `X-LX-APIKEY` | API Key |
| `X-LX-SIGNATURE` | HMAC-SHA256 Signatur |

### Signatur-Algorithmus
```
Signatur-Input = [Request Path][?Query][Request Body]
```
- HMAC-SHA256 mit `apiSecret` als Key
- Ergebnis als lowercase Hex-String
- GET: Body leer, POST/PUT: Original JSON Body
- `requestExpiry` (Millisekunden-Timestamp) muss in der Zukunft liegen

---

## Endpoints

### 1. Order platzieren (Copy Trading)
`POST /api/service-perpetual/order/copy-affiliate-order`

| Feld | Typ | Required | Beschreibung |
|------|-----|----------|-------------|
| symbol | String | Ja | Trading Pair (z.B. BTCUSDT) |
| posSide | String | Ja | Position Side (Long/Short) |
| side | String | Ja | Buy/Sell |
| orderQty | String | Nein | Menge |
| price | String | Nein | Limit-Preis |
| ordType | String | Nein | Market/Limit/StopMarket/etc. (Default: Market) |
| timeInForce | String | Nein | GoodTillCancel (Default) |
| reduceOnly | Boolean | Nein | Nur Position reduzieren |
| takeProfit | String | Nein | TP-Preis |
| stopLoss | String | Nein | SL-Preis |
| positionID | String | Nein | Bestehende Position (für Nachkauf) |
| positionName | String | Nein | Position-Label |
| leverage | String | Nein | Hebel |
| stopPrice | String | Nein | Stop-Trigger-Preis |
| clOrdID | String | Nein | Client Order ID |
| actionBy | String | Nein | Action Source |
| trigger | String | Nein | Trigger-Typ |
| tpTrigger | String | Nein | TP Trigger Method |
| slTrigger | String | Nein | SL Trigger Method |

**Response:**
```json
{
    "error": null,
    "result": {
        "bizError": 0,
        "orderID": "b159adb4-1280-45fc-9014-870a4aceebb8",
        "symbol": "ETHUSDT",
        "side": "Buy",
        "orderType": "Market",
        "price": "2310.2",
        "posSide": "Long",
        "orderQty": "1.234",
        "ordStatus": "Created",
        "execStatus": "PendingNew"
    }
}
```

---

### 2. Aktive Orders abfragen
`GET /api/perpetual/orders/active-all`

| Parameter | Required | Beschreibung |
|-----------|----------|-------------|
| symbol | Ja | Trading Pair |

---

### 3. Order stornieren
`DELETE /api/perpetual/orders`

| Parameter | Required | Beschreibung |
|-----------|----------|-------------|
| symbol | Ja | Trading Pair |
| posSide | Ja | Long/Short |
| orderID | Nein | Order ID |
| clOrdID | Nein | Client Order ID |
| positionID | Nein | Position ID |

---

### 4. Alle Orders stornieren
`DELETE /api/perpetual/orders/cancel-all`

| Parameter | Required | Beschreibung |
|-----------|----------|-------------|
| symbol | Nein | Trading Pair (leer = alle) |
| untriggered | Nein | Filter triggered/untriggered |
| cancelAllOrdType | Nein | true = alle Typen canceln |

---

### 5. Alle Positionen schließen
`DELETE /api/perpetual/orders/all-positions`

| Parameter | Required | Beschreibung |
|-----------|----------|-------------|
| symbol | Nein | Trading Pair |
| settleCurrency | Nein | Settlement Currency |

---

### 6. Order-Historie
`GET /api/service-perpetual/perp-trading/order`

| Parameter | Required | Beschreibung |
|-----------|----------|-------------|
| symbols | Nein | Trading Pairs |
| orderStatus | Nein | Status-Filter (kommagetrennt) |
| orderTypes | Nein | Typ-Filter |
| start/end | Nein | Zeitraum (ms) |
| pageNumber | Nein | Seite (Default: 1) |
| pageSize | Nein | Pro Seite (Default: 20) |

---

### 7. Trade-Historie
`GET /api/service-perpetual/perp-trading/trade`

| Parameter | Required | Beschreibung |
|-----------|----------|-------------|
| symbols | Nein | Trading Pairs |
| tradeTypes | Nein | Typ-Filter |
| start/end | Nein | Zeitraum (ms) |
| pageNumber | Nein | Seite (Default: 1) |
| pageSize | Nein | Pro Seite (Default: 20) |

---

### 8. Leverage ändern
`POST /api/perpetual/positions/leverage`

| Feld | Typ | Required | Beschreibung |
|------|-----|----------|-------------|
| symbol | String | Ja | Trading Pair |
| marginMode | String | Ja | Isolated/Cross |
| longLeverage | String | Ja | Long-Hebel |
| shortLeverage | String | Ja | Short-Hebel |

**Wichtig:** Leverage kann nur geändert werden wenn Position-Size = 0 ist (Error 2136).

---

### 9. Position umbenennen
`POST /api/perpetual/positions/display-name`

| Feld | Typ | Required | Beschreibung |
|------|-----|----------|-------------|
| positionID | String | Ja | Position UUID |
| symbol | String | Ja | Trading Pair |
| posSide | String | Ja | Long/Short/Merged/Multi |
| displayName | String | Ja | Neuer Name |

---

### 10. Margin anpassen
`POST /api/perpetual/positions/margin`

| Feld | Typ | Required | Beschreibung |
|------|-----|----------|-------------|
| positionID | String | Ja | Position UUID |
| symbol | String | Ja | Trading Pair |
| posSide | String | Ja | Long/Short/Merged/Multi |
| changeAmount | Number | Ja | Margin +/- Betrag |

---

### 11. Position-Modus wechseln
`POST /api/perpetual/positions/switch-pos-mode`

| Feld | Typ | Required | Beschreibung |
|------|-----|----------|-------------|
| symbol | String | Ja | Trading Pair |
| targetPosMode | String | Ja | Hedged/OneWay/Multi |

---

## Enums

### Side
Buy, Sell

### Order Type
Market, Limit, StopMarket, StopLimit, MarketIfTouched, LimitIfTouched, ProtectedMarket, MarketAsLimit, StopAsLimit, MarketIfTouchedAsLimit, Bracket, BoTpLimit, BoSlLimit, BoSlMarket

### Order Status
Created, Untriggered, Deactivated, Triggered, Rejected, New, PartiallyFilled, Filled, Canceled, Inactive

### Margin Mode
Cross, Isolated

### Position Mode
OneWay, Hedged, Multi

### Position Side
Long, Short, Merged, Multi

### Trade Type
Trade, Liq, Adl, Funding, TakeOver, LiqTrade, AdlTrade, Amend, Cancel, Replace, TransferIn, ExchangeIn, ExchangeOut
