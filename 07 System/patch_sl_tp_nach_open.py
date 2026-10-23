#!/usr/bin/env python3
"""
Patch (2026-09-07): SL/TP NICHT mehr im Open-Body mitschicken.

PROBLEM
-------
Beim ersten echten Copy-Trade (07.09., Francesco Buontempo) lehnte LeveX die
Order ab mit:  HTTP 400 / code 600034 "Order not found"

Body war:
  {"symbol":"BTCUSDT","side":"Sell","posSide":"Multi","orderQty":"0.007",
   "ordType":"Market","timeInForce":"GoodTillCancel","reduceOnly":false,
   "stopLoss":"79777.7","takeProfit":"78777.7"}

Alle 22 jemals ERFOLGREICHEN Orders (11.05., Test-Kunde) hatten KEIN
stopLoss/takeProfit im Body. Alle Versuche MIT SL/TP (19.05.) scheiterten schon
vorher am 401 (kein API-Key) — der Pfad war also nie unter Realbedingungen
getestet. Der 07.09. war der erste echte Kontakt und schlug sofort fehl.

FIX
---
Position erst NACKT oeffnen (ohne stopLoss/takeProfit), danach SL/TP separat
via /api/service-perpetual/positions/trading-stop setzen. Diesen Weg nutzt der
Bot fuer SET_SL/SET_TP ohnehin schon (_handle_set_sl_tp).

SICHERHEIT
----------
- Aendert AUSSCHLIESSLICH execution.py. signal_bot.py / parser.py unberuehrt.
- Der Signal-Bot laeuft in listen.py als eigener asyncio.create_task und feuert
  VOR engine.execute(); engine.execute() ist zusaetzlich in try/except gekapselt.
  => Signale koennen durch diesen Patch nicht beeinflusst werden.
- Alle Anker haben Count-Asserts: bricht ab, wenn nicht exakt 1 Treffer.
"""

import shutil
import sys
from datetime import datetime

TARGET = "execution.py"

# ---------------------------------------------------------------- Block 1
# Neue Methode _apply_sl_tp_after_open direkt vor _handle_set_sl_tp einfuegen.
ANCHOR_1 = (
    "    async def _handle_set_sl_tp(self, event: ParsedEvent, "
    "customer: Customer, is_sl: bool) -> None:"
)

NEW_METHOD = '''    async def _apply_sl_tp_after_open(
        self,
        customer: Customer,
        symbol: str,
        pos_side: str,
        position_id: str,
        sl_tp: dict,
    ) -> None:
        """
        SL/TP NACH dem Oeffnen separat setzen.

        Grund (2026-09-07): LeveX lehnt copy-affiliate-order ab, wenn
        stopLoss/takeProfit direkt im Open-Body stehen
        (HTTP 400, code 600034 "Order not found"). Die Position wird deshalb
        erst nackt geoeffnet und SL/TP direkt danach via trading-stop gesetzt.
        """
        if not sl_tp or not position_id or not customer.client:
            return

        sl = sl_tp.get("stopLoss")
        tp = sl_tp.get("takeProfit")
        if not sl and not tp:
            return

        last_err = None
        for attempt in range(1, 4):
            if attempt > 1:
                # Position braucht nach dem Market-Fill kurz, bis sie existiert
                await asyncio.sleep(0.5)

            result = await customer.client.set_trading_stop(
                position_id=position_id,
                symbol=symbol,
                pos_side=pos_side,
                stop_loss=str(sl) if sl else None,
                take_profit=str(tp) if tp else None,
            )

            if not result.get("error"):
                logger.info(
                    f"[EXEC] {customer.name}: SL/TP nach Oeffnung gesetzt "
                    f"(SL={sl}, TP={tp}, Versuch {attempt}) OK"
                )
                return

            last_err = result.get("error") or {}
            logger.warning(
                f"[EXEC] {customer.name}: SL/TP-Setzen Versuch {attempt}/3 "
                f"fehlgeschlagen ({last_err.get('code')}: {last_err.get('message')})"
            )

        logger.error(
            f"[EXEC] {customer.name}: SL/TP konnte NICHT gesetzt werden — "
            f"Position laeuft OHNE Absicherung! (SL={sl}, TP={tp}, "
            f"PosID={position_id})"
        )
        if self._telegram:
            try:
                await self._telegram.trade_error(
                    customer.name,
                    symbol,
                    "SET_SL_TP_AFTER_OPEN",
                    f"Position offen OHNE SL/TP (SL={sl}, TP={tp}). "
                    f"Bitte manuell pruefen!",
                )
            except Exception:
                pass

'''

# ---------------------------------------------------------------- Block 2
# TRADE_FILLED: SL/TP aus dem Open-Body entfernen.
ANCHOR_2 = '''                ord_type="Market",
                stop_loss=sl_tp.get("stopLoss"),
                take_profit=sl_tp.get("takeProfit"),
            )
            if sl_tp:
                logger.info(f"[EXEC] {customer.name}: SL/TP bei Eroeffnung mitgeschickt: {sl_tp}")
'''

REPLACE_2 = '''                ord_type="Market",
            )
            # SL/TP bewusst NICHT im Open-Body (LeveX 600034) —
            # wird nach dem Mapping via _apply_sl_tp_after_open gesetzt.
'''

# ---------------------------------------------------------------- Block 3
# OPEN_TRADE: SL/TP aus dem Open-Body entfernen.
ANCHOR_3 = '''                position_id=customer_pos_id,
                stop_loss=sl_tp.get("stopLoss"),
                take_profit=sl_tp.get("takeProfit"),
            )
            if sl_tp:
                logger.info(f"[EXEC] {customer.name}: SL/TP bei Eroeffnung mitgeschickt: {sl_tp}")
'''

REPLACE_3 = '''                position_id=customer_pos_id,
            )
            # SL/TP bewusst NICHT im Open-Body (LeveX 600034) —
            # wird nach dem Mapping via _apply_sl_tp_after_open gesetzt.
'''

# ---------------------------------------------------------------- Block 4
# TRADE_FILLED: nach dem Mapping SL/TP setzen.
ANCHOR_4 = '''                logger.info(
                    f"[EXEC] Mapping (Market Fill): Master {order_id[:8]}... -> "
                    f"Kunde {customer.name} ({customer_order_id[:8] if customer_order_id else 'no-id'}...)"
                )
'''

REPLACE_4 = ANCHOR_4 + '''
                await self._apply_sl_tp_after_open(
                    customer=customer,
                    symbol=event.symbol,
                    pos_side=side,
                    position_id=customer_order_id,
                    sl_tp=sl_tp,
                )
'''

# ---------------------------------------------------------------- Block 5
# OPEN_TRADE: nach dem Mapping SL/TP setzen.
ANCHOR_5 = '''                    logger.info(
                        f"[EXEC] Mapping: Master {master_pos_id[:8]}... -> "
                        f"Kunde {customer.name} {new_customer_pos_id[:8]}..."
                    )
'''

REPLACE_5 = ANCHOR_5 + '''
                    await self._apply_sl_tp_after_open(
                        customer=customer,
                        symbol=event.symbol,
                        pos_side=side,
                        position_id=new_customer_pos_id,
                        sl_tp=sl_tp,
                    )
'''


def check(src: str, anchor: str, label: str) -> None:
    n = src.count(anchor)
    if n != 1:
        print(f"ABBRUCH: Anker '{label}' {n}x gefunden (erwartet: genau 1).")
        sys.exit(1)
    print(f"  OK  Anker '{label}': 1 Treffer")


def main() -> None:
    with open(TARGET, "r", encoding="utf-8") as f:
        src = f.read()

    if "_apply_sl_tp_after_open" in src:
        print("ABBRUCH: Patch scheint bereits angewendet (Methode existiert).")
        sys.exit(1)

    print("Anker pruefen:")
    check(src, ANCHOR_1, "1 neue Methode")
    check(src, ANCHOR_2, "2 TRADE_FILLED Open-Body")
    check(src, ANCHOR_3, "3 OPEN_TRADE Open-Body")
    check(src, ANCHOR_4, "4 TRADE_FILLED Mapping-Log")
    check(src, ANCHOR_5, "5 OPEN_TRADE Mapping-Log")

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = f"{TARGET}.bak_sltp_{ts}"
    shutil.copy2(TARGET, backup)
    print(f"\nBackup: {backup}")

    src = src.replace(ANCHOR_1, NEW_METHOD + ANCHOR_1, 1)
    src = src.replace(ANCHOR_2, REPLACE_2, 1)
    src = src.replace(ANCHOR_3, REPLACE_3, 1)
    src = src.replace(ANCHOR_4, REPLACE_4, 1)
    src = src.replace(ANCHOR_5, REPLACE_5, 1)

    with open(TARGET, "w", encoding="utf-8") as f:
        f.write(src)

    print("Alle 5 Bloecke angewendet.")


if __name__ == "__main__":
    main()
