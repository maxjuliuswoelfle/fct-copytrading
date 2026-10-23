"""
(C) manage.py — CLI Tool fuer Kunden-Verwaltung

Nutzung:
    python manage.py list                     — Alle Kunden anzeigen
    python manage.py add                      — Neuen Kunden hinzufuegen (interaktiv)
    python manage.py remove <id>              — Kunden deaktivieren
    python manage.py invite <id>              — Dashboard-Einladungslink erstellen
    python manage.py migrate-env              — Test-Kunde aus .env in DB migrieren
"""

import sys
import uuid
import os
from dotenv import load_dotenv
from database import Database

load_dotenv()
db = Database()
db.connect()


def list_customers() -> None:
    """Alle Kunden anzeigen."""
    customers = db.get_all_customers()
    if not customers:
        print("\nKeine Kunden in Datenbank.\n")
        print("Nutze 'python manage.py add' um einen Kunden hinzuzufuegen.")
        print("Oder 'python manage.py migrate-env' um den Test-Kunden aus .env zu migrieren.")
        return

    print(f"\n{'='*70}")
    print(f"{'ID':<20} {'Name':<20} {'UID':<12} {'Status':<10} {'Read-WS'}")
    print(f"{'='*70}")
    for c in customers:
        status = "✅ Aktiv" if c["is_active"] else "❌ Inaktiv"
        has_read = "✅" if c.get("read_api_key") else "❌"
        print(f"{c['id']:<20} {c['name']:<20} {c['uid']:<12} {status:<10} {has_read}")
    print()

    # Aktive Mappings pro Kunde
    for c in customers:
        if c["is_active"]:
            mappings = db.get_mappings_for_customer(c["id"])
            if mappings:
                print(f"  {c['name']}: {len(mappings)} aktive Position(en)")
                for m in mappings:
                    print(f"    - {m['symbol']} | Master: {m['master_position_id'][:12]}... | Side: {m.get('side', '?')}")


def add_customer() -> None:
    """Neuen Kunden interaktiv hinzufuegen."""
    print("\n=== Neuen Kunden hinzufuegen ===\n")

    name = input("Name (z.B. 'Max Mustermann'): ").strip()
    if not name:
        print("Abgebrochen — Name ist Pflicht.")
        return

    uid = input("Levex UID: ").strip()
    if not uid:
        print("Abgebrochen — UID ist Pflicht.")
        return

    api_key = input("Copy Trading API Key: ").strip()
    if not api_key:
        print("Abgebrochen — API Key ist Pflicht.")
        return

    api_secret = input("Copy Trading API Secret: ").strip()
    if not api_secret:
        print("Abgebrochen — API Secret ist Pflicht.")
        return

    read_api_key = input("Futures Read API Key (optional, Enter zum Ueberspringen): ").strip()
    read_api_secret = ""
    if read_api_key:
        read_api_secret = input("Futures Read API Secret: ").strip()

    # ID generieren
    customer_id = f"kunde-{uuid.uuid4().hex[:8]}"

    print(f"\n--- Zusammenfassung ---")
    print(f"ID:     {customer_id}")
    print(f"Name:   {name}")
    print(f"UID:    {uid}")
    print(f"API:    {api_key[:8]}...{api_key[-4:]}")
    print(f"Read:   {'Ja' if read_api_key else 'Nein'}")

    confirm = input("\nSpeichern? (j/n): ").strip().lower()
    if confirm != "j":
        print("Abgebrochen.")
        return

    db.add_customer(
        customer_id=customer_id,
        name=name,
        uid=uid,
        api_key=api_key,
        api_secret=api_secret,
        read_api_key=read_api_key,
        read_api_secret=read_api_secret,
    )
    print(f"\n✅ Kunde '{name}' hinzugefuegt (ID: {customer_id})")
    print("Bot muss neugestartet werden damit der Kunde aktiv wird.")


def remove_customer(customer_id: str) -> None:
    """Kunden deaktivieren."""
    customer = db.get_customer(customer_id)
    if not customer:
        print(f"\nKunde '{customer_id}' nicht gefunden.")
        return

    if not customer["is_active"]:
        print(f"\nKunde '{customer['name']}' ist bereits deaktiviert.")
        return

    # Aktive Mappings pruefen
    mappings = db.get_mappings_for_customer(customer_id)
    if mappings:
        print(f"\n⚠️  Kunde '{customer['name']}' hat {len(mappings)} aktive Position(en)!")
        print("Diese werden NICHT automatisch geschlossen.")
        confirm = input("Trotzdem deaktivieren? (j/n): ").strip().lower()
        if confirm != "j":
            print("Abgebrochen.")
            return

    db.deactivate_customer(customer_id)
    print(f"\n✅ Kunde '{customer['name']}' deaktiviert.")
    print("Bot muss neugestartet werden damit die Aenderung wirkt.")


def invite_customer(customer_id: str) -> None:
    """Dashboard-Einladungslink fuer einen Kunden erstellen."""
    customer = db.get_customer(customer_id)
    if not customer:
        print(f"\nKunde '{customer_id}' nicht gefunden.")
        print("Verfuegbare Kunden:")
        for c in db.get_all_customers():
            print(f"  {c['id']}  —  {c['name']}")
        return

    # Token generieren
    invite_token = uuid.uuid4().hex

    # Pruefen ob schon ein Dashboard-User existiert
    existing = db.get_dashboard_user_by_customer(customer_id)
    if existing:
        print(f"\nKunde '{customer['name']}' hat bereits einen Dashboard-Zugang.")
        confirm = input("Neuen Einladungslink erstellen? (j/n): ").strip().lower()
        if confirm != "j":
            print("Abgebrochen.")
            return

    db.create_invite(customer_id, invite_token)

    # Server-IP aus Umgebung oder Default
    server = os.getenv("DASHBOARD_URL", "https://178.105.135.197:8443")
    invite_url = f"{server}/invite/{invite_token}"

    print(f"\n✅ Einladungslink erstellt fuer '{customer['name']}':")
    print(f"\n   {invite_url}")
    print(f"\nDiesen Link dem Kunden schicken — er kann damit sein Passwort setzen.")


def migrate_env() -> None:
    """Test-Kunden aus .env in DB migrieren."""
    customer_key = os.getenv("CUSTOMER_API_KEY", "")
    customer_secret = os.getenv("CUSTOMER_API_SECRET", "")
    customer_uid = os.getenv("CUSTOMER_UID", "")
    customer_read_key = os.getenv("CUSTOMER_READ_API_KEY", "")
    customer_read_secret = os.getenv("CUSTOMER_READ_API_SECRET", "")

    if not customer_key or not customer_secret or not customer_uid:
        print("\nKeine Kunden-Daten in .env gefunden.")
        print("Benoetigte Variablen: CUSTOMER_API_KEY, CUSTOMER_API_SECRET, CUSTOMER_UID")
        return

    # Pruefen ob schon migriert
    existing = db.get_customer("test-kunde-001")
    if existing:
        print("\nTest-Kunde ist bereits in der Datenbank.")
        return

    db.add_customer(
        customer_id="test-kunde-001",
        name="Test-Kunde",
        uid=customer_uid,
        api_key=customer_key,
        api_secret=customer_secret,
        read_api_key=customer_read_key,
        read_api_secret=customer_read_secret,
    )
    print("\n✅ Test-Kunde aus .env in Datenbank migriert.")
    print("Der Bot laedt Kunden jetzt aus der DB — .env Keys werden nicht mehr benoetigt.")


def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        return

    command = sys.argv[1].lower()

    match command:
        case "list":
            list_customers()
        case "add":
            add_customer()
        case "remove" | "deactivate":
            if len(sys.argv) < 3:
                print("Nutzung: python manage.py remove <kunde-id>")
                return
            remove_customer(sys.argv[2])
        case "invite":
            if len(sys.argv) < 3:
                print("Nutzung: python manage.py invite <kunde-id>")
                print("\nVerfuegbare Kunden:")
                for c in db.get_all_customers():
                    print(f"  {c['id']}  —  {c['name']}")
                return
            invite_customer(sys.argv[2])
        case "migrate-env":
            migrate_env()
        case _:
            print(f"Unbekannter Befehl: {command}")
            print(__doc__)


if __name__ == "__main__":
    main()
