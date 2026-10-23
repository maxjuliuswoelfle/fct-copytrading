import sqlite3
conn = sqlite3.connect("file:copy_trading.db?mode=ro", uri=True)
conn.row_factory = sqlite3.Row
NEG = ('cancelled','refunded','chargebacked','suspended')

print("== payment_status x is_active ==")
for r in conn.execute("""SELECT COALESCE(du.payment_status,'<NULL>') ps, c.is_active,
                         COUNT(*) n FROM dashboard_users du
                         JOIN customers c ON c.id=du.customer_id
                         GROUP BY ps, c.is_active ORDER BY n DESC"""):
    print(f"  {r['ps']:<14} is_active={r['is_active']}  -> {r['n']}")

print("\n== PAUSIERER (zahlend, aber is_active=0) — duerfen NICHT gesperrt werden ==")
for r in conn.execute("""SELECT du.id, du.email FROM dashboard_users du
                         JOIN customers c ON c.id=du.customer_id
                         WHERE c.is_active=0 AND du.payment_status='paid'"""):
    print(f"  id {r['id']:>4}  {r['email']}")

print("\n== is_activated-Verteilung (steckt bereits im Session-Check) ==")
for r in conn.execute("""SELECT is_activated, COUNT(*) n FROM dashboard_users
                         GROUP BY is_activated"""):
    print(f"  is_activated={r['is_activated']} -> {r['n']}")

q = f"""SELECT COUNT(*) n FROM dashboard_users
        WHERE session_token IS NOT NULL
          AND session_expires_at > CURRENT_TIMESTAMP
          AND is_activated=1
          AND COALESCE(payment_status,'') IN {NEG}"""
print(f"\n== Offene Sessions, die das Gate SOFORT beenden wuerde: {conn.execute(q).fetchone()['n']}")
q2 = """SELECT COUNT(*) n FROM dashboard_users
        WHERE session_token IS NOT NULL AND session_expires_at > CURRENT_TIMESTAMP
          AND is_activated=1"""
print(f"   (aktive Sessions gesamt: {conn.execute(q2).fetchone()['n']})")

print("\n== Betroffene offene Sessions im Detail ==")
for r in conn.execute(f"""SELECT id, email, payment_status FROM dashboard_users
        WHERE session_token IS NOT NULL AND session_expires_at > CURRENT_TIMESTAMP
          AND is_activated=1 AND COALESCE(payment_status,'') IN {NEG}"""):
    print(f"  id {r['id']:>4}  {r['payment_status']:<13} {r['email']}")
