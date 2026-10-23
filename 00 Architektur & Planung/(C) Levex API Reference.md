# (C) Levex API Reference

> Zusammenfassung der Levex API-Dokumentation für den Copy Trading Bot.
> Quellen: [Trade API](https://docs.google.com/document/d/1DNk_2M2OMmCXoILdjRsXieTkV1ZRLBFF45h-ghFy0EE) | [Data API](https://docs.google.com/document/d/1q9Mi1-bZQK5_E6Eilckg499IOiHZFn7MpWJDvJ9F_CA)


## Environments

| Environment | REST API | WebSocket |
|------------|----------|-----------|
| **Testnet** | `https://api-testnet.levex.com` | `wss://stream-testnet.levex.com` |
| **Production** | `https://api.levex.com` | `wss://stream.levex.com` |


## Authentication

**Required Headers (REST):**
- `X-LX-APIKEY`: API Key
- `X-LX-SIGNATURE`: HMAC-SHA256 Signature

**Signature Construction:**
- SignContent = `[Path][?Query][Body]`
- GET: Body ist leer
- POST/PUT: Raw JSON als Body
- Algorithmus: HMAC-SHA256 mit apiSecret als Key
- Server versucht erst raw Key, dann base64-decoded Key
- Optional: `requestExpiry` (ms) für zeitliche Gültigkeit

**WebSocket Auth:**
```json
{
  "id": 0,
  "method": "user.auth",
  "params": {
    "apiKey": "<API_KEY>",
    "signature": "<HMAC-SHA256 von /tokens/self?requestExpiry=<epoch_ms>>",
    "expiry": <epoch_ms>
  }
}
```


## Rate Limits

- **Global:** 1000 Requests/min pro IP
- **Spot Orders:** 500/min (Weight 1)
- **Cancel All:** 500/min (Weight 5)
- **Public Pairs:** 200/min (Weight 1)

Response Headers: `X-REMAINING`, `X-CAPACITY`, `X-Retry-After`, `X-GROUP`


---


## REST API — Spot Orders

### Place Order
`POST /api/spot/orders`

| Feld | Typ | Required | Beschreibung |
|------|-----|----------|-------------|
| symbol | string | Ja | z.B. `sBTCUSDT` |
| side | string | Ja | `Buy` / `Sell` |
| ordType | string | Nein | `Limit` / `Market` / `StopMarket` / `StopLimit` etc. |
| price | string | Nein | Order-Preis |
| baseQty | string | Nein | Base Quantity |
| quoteQty | string | Nein | Quote Quantity |
| qtyType | string | Nein | `ByBase` / `ByQuote` |
| stopPrice | string | Nein | Trigger-Preis |
| trigger | string | Nein | Trigger-Typ |
| timeInForce | string | Nein | `GoodTillCancel` (default) |
| clOrdID | string | Nein | Client Order ID |
| execInst | string | Nein | Execution Instruction |

**Response:**
```json
{
  "result": {
    "orderID": "123456",
    "symbol": "BTCUSDT",
    "side": "Buy",
    "ordStatus": "New",
    "price": "100.01",
    "baseQty": "0.01",
    "ordType": "Limit",
    "avgPrice": "100.01",
    "cumFee": "0.0001",
    "cumBaseQty": "0.01",
    "cumQuoteQty": "1.0001"
  }
}
```

### Amend Order
`PUT /api/spot/orders` — Gleiche Parameter, `symbol` + `orderID` required

### Cancel Order
`DELETE /api/spot/orders` — `symbol` required + `orderID` oder `clOrdID`

### List Active Orders
`GET /api/spot/orders` — Optional: `symbol`, `orderID`, `clOrdID`

### Single Order Query
`GET /api/spot/orders/active` — `symbol` required + `orderID` oder `clOrdID`

### Order History
`GET /api/service-spot/order` — Max 3 Monate Zeitfenster, mit Pagination

### Cancel All
`DELETE /api/spot/orders/cancel-all` — Optional: `symbol`


---


## REST API — Spot Wallet

### Query Wallet
`GET /api/spot/wallet`

| Feld | Typ | Required | Beschreibung |
|------|-----|----------|-------------|
| currency | string | Nein | Leer = alle Währungen |

**Response:**
```json
{
  "result": {
    "rows": [{
      "currency": "USDT",
      "balance": "100.00",
      "lockedTradingBalance": "10.00",
      "lockedWithdraw": "0.00"
    }]
  }
}
```


---


## REST API — Public

### Trading Pairs & Config
`GET /api/public/pairs`

Returns: `spotPairs`, `perpPairs`, `currencies`, `riskLimits`, `leverages`, `defaultFeeRate`


---


## REST API — Affiliate

### Commission History
`GET /api/service-affiliate/commission/history` — Max 90-Tage Range

### Client Summary
`GET /api/service-affiliate/affiliate/client/summary` — Pagination, optional clientId


---


## WebSocket API

### Connection
- Testnet: `wss://stream-testnet.levex.com`
- Production: `wss://stream.levex.com`

### Heartbeat (alle 5 Sekunden empfohlen)
```json
{"id": 0, "method": "server.ping", "params": {}}
// Response: {"result": "pong"}
```

Reconnect nach 3 fehlgeschlagenen Heartbeats (90 Sekunden max).


### Spot User Data (AUTH REQUIRED) ⭐ KRITISCH FÜR BOT
```json
{
  "id": 0,
  "method": "spotUser.subscribe",
  "params": {"wallet": true, "order": true}
}
```

**Order Updates (`spotOrder.update`):**
- `orderKeys`: userID, symbol, side, action, ordStatus, ordType, orderID, clOrdID, price, avgPrice, qtyType, baseQty, quoteQty, leavesBaseQty, leavesQuoteQty, cumBaseQty, cumQuoteQty, cumFee, trigger, stopPrice, createdTimeNs, transactTimeNs, ...
- `fillKeys`: userID, symbol, side, execStatus, ordType, orderID, execID, price, avgPrice, execBaseQty, execQuoteQty, execFee, ...
- Arrays: `open` (aktive Orders), `closed` (geschlossene Orders), `fills` (Fills)

**Wallet Updates (`spotWallet.update`):**
- Keys: userID, currency, balance, lockedTradingBalance, lockedWithdrawBalance


### Perpetual User Data (AUTH REQUIRED) ⭐ KRITISCH FÜR BOT
```json
{
  "id": 0,
  "method": "perpAccount.subscribe",
  "params": {
    "account": true,
    "position": true,
    "order": true,
    "positionInfo": true,
    "historyLimit": 0,
    "allPositions": true
  }
}
```

**Account Updates (`perpAccount.update`):**
- Keys: userID, currency, accountBalance, usedBalance, bonusBalance

**Position Updates (`perpPosition.update`):**
- Keys: userID, symbol, currency, side, posStatus, leverage, riskLimit, size, initMarginRate, maintMarginRate, avgEntryPrice, posCost, posBalance, posMargin, bankruptPrice, liquidationPrice, markPrice, unrealisedPnL, realisedPnL, ...

**Order Updates (`perpOrder.update`):**
- `orderKeys`: userID, symbol, currency, side, action, ordType, orderID, clOrdID, price, orderQty, ordStatus, leavesQty, cumQty, cumValue, trigger, stopPrice, takeProfitPrice, stopLossPrice, ...
- `fillKeys`: userID, symbol, currency, side, ordType, orderID, execPrice, execQty, execValue, execFee, closedSize, closedPnL, ...
- Arrays: `open`, `closed`, `fills`


### Market Data (PUBLIC — kein Auth)
- `orderbook.subscribe` / `orderbook.update`
- `trade.subscribe` / `trade.update`
- `kline.subscribe` / `kline.update`
- `spot24HTicker.subscribe` / `spot24HTicker.update`
- `perp24HTicker.subscribe` / `perp24HTicker.update`


---


## Error Codes

| Code | Message | Beschreibung |
|------|---------|-------------|
| 429 | Too many requests | Rate Limit |
| 1001 | side is not supported | Ungültige Seite |
| 1002 | qtyType is invalid | Ungültiger Qty-Typ |
| 1003 | timeInForce is not supported | Ungültige TIF |
| 1004 | trigger is not supported | Ungültiger Trigger |
| 1005 | SYMBOL_NOT_SUPPORTED | Symbol nicht unterstützt |
| 1006 | Error in query spot wallet | Wallet-Fehler |
| 2001 | CLIENT_ACCESS_DENIED | Keine Trading-Permission |
| 2002 | ORDER_TYPE_NOT_SUPPORTED | Order-Typ nicht unterstützt |
| 2003 | ORDER_QTY_CHECK_FAILED | Mengen-Validierung fehlgeschlagen |
| 2004 | ORDER_VALUE_CHECK_FAILED | Wert-Check fehlgeschlagen |
| 2005 | ORDER_PRICE_TICKSIZE_FAILED | Preis-Precision fehlgeschlagen |
| 3011 | invalid login token | WebSocket Auth fehlgeschlagen |


## Order Types (Enums)

**Side:** Buy, Sell

**OrdType:** Market, Limit, StopMarket, StopLimit, MarketIfTouched, LimitIfTouched, ProtectedMarket, MarketAsLimit, StopAsLimit, MarketIfTouchedAsLimit, Bracket, BoTpLimit, BoSlLimit, BoSlMarket

**OrdStatus:** Created, Untriggered, Deactivated, Triggered, Rejected, New, PartiallyFilled, Filled, Canceled, Inactive

**QtyType:** ByBase, ByQuote

**TimeInForce:** GoodTillCancel (+ weitere)


---


## Perpetual REST API (Copy Trading)

> ✅ **Erhalten am 2026-05-08 von Levex IT.** Vollständige Dokumentation in separater Datei:
> → [[00 Architektur & Planung/(C) Levex Perpetual REST API]]

Wichtigste Endpoints:
- `POST /api/service-perpetual/order/copy-affiliate-order` — Order platzieren (Copy Trading)
- `DELETE /api/perpetual/orders` — Order canceln
- `DELETE /api/perpetual/orders/cancel-all` — Alle Orders canceln
- `POST /api/perpetual/positions/close-all` — Alle Positionen schließen
- `POST /api/perpetual/positions/trading-stop` — SL/TP setzen
- `POST /api/perpetual/positions/change-leverage` — Leverage ändern
- `POST /api/perpetual/positions/change-margin` — Margin anpassen
- `PUT /api/perpetual/positions/rename` — Position umbenennen

**Bekannte Einschränkungen:**
- Kein REST-Endpoint für Futures Balance — nur via WebSocket (`perpAccount.subscribe`)
- Copy-Trading API unterstützt keine Limit Orders direkt — Workaround im Bot: auf Fill warten, dann Market Order
- SL/TP können bei Limit Orders nicht beim Platzieren mitgegeben werden — separater `trading-stop` Endpoint nötig
