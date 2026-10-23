import json, sqlite3, collections
conn = sqlite3.connect("file:copy_trading.db?mode=ro", uri=True)
c = collections.Counter()
for (pl,) in conn.execute("SELECT payload FROM webhook_logs WHERE payload LIKE '%payer.access.changed%'"):
    p = json.loads(pl)
    if p.get("event") != "payer.access.changed":
        continue
    prod = (p.get("product") or {})
    pid = prod.get("id") or prod.get("product_id")
    try: pid = int(pid)
    except: pid = None
    if pid not in (517561, 517562):
        continue
    acc = p.get("access") or {}
    c[(acc.get("access_type"), p.get("payment_state"))] += 1
print("(access_type, payment_state) -> Anzahl, nur unsere Produkte:")
for k, v in c.most_common():
    print(f"   {str(k):<55} {v}")
