import json, sqlite3, collections
conn = sqlite3.connect("file:copy_trading.db?mode=ro", uri=True)
n_prod = collections.Counter()
beispiel = None
for (pl,) in conn.execute("SELECT payload FROM webhook_logs WHERE payload LIKE '%payer.access.changed%'"):
    p = json.loads(pl)
    if p.get("event") != "payer.access.changed":
        continue
    prod = p.get("product")
    n_prod[type(prod).__name__ if prod is not None else "FEHLT"] += 1
    if beispiel is None:
        beispiel = p
print("product-Feld in payer.access.changed:", dict(n_prod))
print("Top-Level-Keys:", sorted(beispiel.keys()))
print("access-Keys:", sorted((beispiel.get("access") or {}).keys()))
print("product:", json.dumps(beispiel.get("product"))[:300])
