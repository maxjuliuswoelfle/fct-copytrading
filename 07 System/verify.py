import sqlite3
conn = sqlite3.connect("file:copy_trading.db?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
print("== payment_status gesamt ==")
for r in conn.execute("SELECT COALESCE(payment_status,'<NULL>') ps, COUNT(*) n FROM dashboard_users GROUP BY ps ORDER BY n DESC"):
    print(f"  {r['ps']:<14} {r['n']}")

ids = [145,134,138,175,200,227,256,263,302,338,360,354,390,355,363,377,402,409,
       408,427,137,63,426,250,309,341,435,361,388,398,453,452]
q = ",".join("?"*len(ids))
print("\n== Die 32 Ziele: Ist-Zustand ==")
bad = 0
for r in conn.execute(f"""SELECT du.id, du.email, du.payment_status, c.is_active,
    c.deactivated_at IS NOT NULL AS deact FROM dashboard_users du
    JOIN customers c ON c.id=du.customer_id WHERE du.id IN ({q}) ORDER BY du.id""", ids):
    ok = r["payment_status"]=="cancelled" and r["is_active"]==0 and r["deact"]==1
    bad += 0 if ok else 1
    if not ok:
        print(f"  NICHT SAUBER: id {r['id']} {r['email']} ps={r['payment_status']} act={r['is_active']} deact={r['deact']}")
print(f"  {len(ids)-bad}/{len(ids)} korrekt deaktiviert")

print("\n== Kontrolle: Schutzliste unveraendert? ==")
for r in conn.execute("""SELECT du.id, du.email, du.payment_status, c.is_active FROM dashboard_users du
    JOIN customers c ON c.id=du.customer_id WHERE du.email IN
    ('max.woelfle5@gmail.com','felix.roth87@gmail.com','nblock70@googlemail.com',
     'rico.andres@web.de','inaherrmann3@gmx.net','dr.sabai@pm.me',
     'francesco@firstclass-trading.com') ORDER BY du.id"""):
    flag = "OK" if r["payment_status"]=="paid" and r["is_active"]==1 else "<<< PRUEFEN"
    print(f"  id {r['id']:>4} {r['email']:<36} {r['payment_status']:<10} act={r['is_active']}  {flag}")

print("\n== Kontrolle: laufende Timer-Faelle unangetastet? ==")
for r in conn.execute("""SELECT du.id, du.email, du.payment_status, c.is_active FROM dashboard_users du
    JOIN customers c ON c.id=du.customer_id WHERE du.email IN
    ('gunnars.nachrichtenzentrale@gmail.com','emanuel.dujmic@gmail.com','anna.stadl@icloud.com',
     'markus.nass@web.de','dominik-e-mail@web.de','patrick.man@gmx.at','wimmerthomas04@gmail.com',
     'kh.markus@proton.me','matthias.kocemba@gmail.com','brendler.pawel@gmail.com',
     'samuellandert@gmx.ch','d.risling@live.de','lihua.zoustahr@yahoo.com') ORDER BY du.id"""):
    flag = "OK" if r["payment_status"]=="paid" and r["is_active"]==1 else "<<< PRUEFEN"
    print(f"  id {r['id']:>4} {r['email']:<40} {r['payment_status']:<8} act={r['is_active']}  {flag}")

print("\n== Aktive Sessions jetzt ==")
r = conn.execute("""SELECT COUNT(*) n FROM dashboard_users WHERE session_token IS NOT NULL
    AND session_expires_at > CURRENT_TIMESTAMP""").fetchone()
print(f"  {r['n']} offen")
conn.close()
