#!/usr/bin/env python3
"""Einmal-Script: Offene Orders + Positionen von Levex API holen."""
import sys, os, asyncio, json
sys.path.insert(0, os.path.expanduser("~botuser/copy-trading-bot"))
from rest_client import LevexRESTClient

async def main():
    c = LevexRESTClient(
        base_url="https://api.levex.com",
        api_key=os.environ.get("LEVEX_API_KEY", ""),
        api_secret=os.environ.get("LEVEX_API_SECRET", ""),
    )
    for sym in ["BTCUSDT", "TRXUSDT"]:
        data = await c.get_active_orders(sym)
        print(f"=== {sym} ORDERS ===")
        if data and "result" in data:
            result = data["result"]
            items = result.get("list", result) if isinstance(result, dict) else result
            if isinstance(items, list):
                for o in items:
                    print(json.dumps(o, indent=2))
            else:
                print(json.dumps(result, indent=2))
        else:
            print(json.dumps(data, indent=2))
    await c.close()

asyncio.run(main())
