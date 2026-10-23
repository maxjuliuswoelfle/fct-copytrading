# (C) Security Audit — Copy Trading Bot

> **Erstellt:** 2026-05-18
> **Status:** 12/14 CRITICAL+HIGH Punkte erledigt. Noch offen: API Key Encryption (#2), lokale .env (#3).


## Übersicht

Vollständiger Security Audit über alle drei Bereiche: Bot-Core, Dashboard, Infrastruktur. Jeder Punkt ist priorisiert und mit konkretem Fix beschrieben.


## CRITICAL — Sofort fixen

### 1. HTTPS/TLS prüfen und sicherstellen
- **Status:** ✅ Erledigt — Nginx + Let's Encrypt war bereits aktiv. UFW Firewall aktiviert (nur 22/80/443). Port 8443 geblockt.
- **Was:** Dashboard muss über HTTPS laufen. Ohne TLS gehen Passwörter, Session-Tokens und API Keys im Klartext über das Internet.
- **Wo:** Server — Nginx Reverse Proxy + Let's Encrypt
- **Fix:**
  1. Prüfen ob Nginx + TLS bereits konfiguriert ist (`nginx -t`, `certbot certificates`)
  2. Falls nicht: Nginx installieren, Let's Encrypt Zertifikat holen
  3. Port 8443 in UFW schließen, nur 80/443 offen
  4. HTTP → HTTPS Redirect einrichten

### 2. API Keys verschlüsselt speichern
- **Status:** ❌ Offen
- **Was:** `api_key`, `api_secret`, `read_api_key`, `read_api_secret` liegen im Klartext in der SQLite DB. Wer die Datei hat, hat alle Kunden-Zugangsdaten.
- **Wo:** `database.py` — Speicher- und Lese-Funktionen
- **Fix:**
  1. `cryptography` Library installieren (Fernet)
  2. Encryption Key als `ENCRYPTION_KEY` in `.env` auf dem Server
  3. Keys vor dem Schreiben verschlüsseln, beim Lesen entschlüsseln
  4. Bestehende Keys einmalig migrieren (Script)

### 3. Lokale .env löschen + Keys rotieren
- **Status:** ❌ Offen
- **Was:** Echte API-Keys liegen lokal im Vault unter `01 Bot-Core/.env`. Wird möglicherweise über iCloud/Obsidian gesynced.
- **Wo:** `01 Bot-Core/.env` (lokal)
- **Fix:**
  1. `01 Bot-Core/.env` lokal löschen
  2. Alle Keys bei Levex rotieren (neue generieren, alte deaktivieren)
  3. Neue Keys nur auf dem Server in `/home/botuser/copy-trading-bot/.env` mit `chmod 600`
  4. `.env.example` behalten (mit Platzhalter-Werten)

### 4. Secure-Flag auf Cookies
- **Status:** ✅ Erledigt — `secure=True` auf allen 4 `set_cookie()` Aufrufen
- **Was:** Session-Cookies werden ohne `secure=True` gesetzt → Browser schickt sie auch über HTTP.
- **Wo:** `auth_routes.py` — alle `set_cookie()` Aufrufe (Zeilen 74-79, 161-166, 265-270, 332-337)
- **Fix:** `secure=True` zu jedem `set_cookie()` hinzufügen. Setzt HTTPS voraus (Punkt 1).


## HIGH — Vor Launch fixen

### 5. Rate Limiting
- **Status:** ✅ Erledigt — In-Memory Rate Limiter in `app.py`. Login 5/min, Register 3/h, PW-Reset 3/15min, Resend-Verify 3/15min.
- **Was:** Kein Limit auf Login, Registrierung, Passwort-Reset. Brute-Force und E-Mail-Bombing möglich.
- **Wo:** `app.py` + `auth_routes.py`
- **Fix:**
  1. `slowapi` installieren
  2. Limits setzen: Login 5/min, Register 3/h, Passwort-Reset 3/15min
  3. Bei Überschreitung: 429 Too Many Requests zurückgeben

### 6. HTTP Security Headers
- **Status:** ✅ Erledigt — Middleware in `app.py`. X-Frame-Options, X-Content-Type-Options, HSTS, Referrer-Policy, Permissions-Policy, CSP.
- **Was:** Keine Security Headers (CSP, X-Frame-Options, HSTS etc.). Clickjacking und MIME-Sniffing möglich.
- **Wo:** `app.py` — Middleware hinzufügen
- **Fix:** Middleware die auf jeder Response setzt:
  - `X-Frame-Options: DENY`
  - `X-Content-Type-Options: nosniff`
  - `Strict-Transport-Security: max-age=31536000; includeSubDomains`
  - `Referrer-Policy: strict-origin-when-cross-origin`
  - `Content-Security-Policy: default-src 'self'; ...`

### 7. SSH härten
- **Status:** ✅ Erledigt — SSH Key-only (ed25519), PermitRootLogin prohibit-password, PasswordAuthentication no, fail2ban aktiv.
- **Was:** Nur Root-Zugang via SSH. Wenn Passwort geknackt → Vollzugriff.
- **Wo:** Server — `/etc/ssh/sshd_config`
- **Fix:**
  1. Admin-User mit sudo erstellen
  2. `PermitRootLogin no`
  3. `PasswordAuthentication no` (nur SSH Keys)
  4. `fail2ban` installieren

### 8. Dashboard systemd Service härten
- **Status:** ✅ Erledigt — NoNewPrivileges, ProtectSystem=strict, ProtectHome=read-only, PrivateTmp, ProtectKernelTunables, ProtectControlGroups.
- **Was:** Dashboard-Prozess hat vollen Dateisystem-Zugriff. Bot-Service ist gehärtet, Dashboard nicht.
- **Wo:** `copy-trading-dashboard.service`
- **Fix:** Gleiche Directives wie Bot-Service:
  ```
  NoNewPrivileges=true
  ProtectSystem=strict
  ProtectHome=read-only
  ReadWritePaths=/home/botuser/copy-trading-bot /home/botuser/dashboard
  PrivateTmp=true
  ```

### 9. Datenbank-Backups
- **Status:** ✅ Erledigt — Täglicher Cron um 3:00 Uhr. SQLite `.backup` nach `/home/botuser/backups/`. Auto-Cleanup nach 30 Tagen.
- **Was:** Kein Backup. Hardware-Ausfall = Totalverlust.
- **Wo:** Server — Cron Job
- **Fix:**
  1. Täglicher Cron: `sqlite3 copy_trading.db ".backup /backup/ct_$(date +%Y%m%d).db"`
  2. Off-Server speichern (S3 oder zweiter Hetzner Volume)
  3. 30 Tage Retention
  4. Restore regelmäßig testen

### 10. Sessions nach Passwort-Reset invalidieren
- **Status:** ✅ Erledigt — `session_token = NULL` nach Passwort-Reset in `auth_routes.py`.
- **Was:** Nach Passwort-Änderung bleiben alte Sessions aktiv.
- **Wo:** `auth_routes.py` — Reset-Password Endpoint (Zeile ~474)
- **Fix:** Nach Update `db.clear_session(customer_id)` aufrufen.

### 11. XSS — innerHTML durch textContent ersetzen
- **Status:** ✅ Erledigt — `esc()` Funktion in app.js, alle externen Daten (symbol, label, side, timestamps) werden escaped.
- **Was:** Trade-Daten werden via `.innerHTML` eingefügt. Manipulierte Daten könnten Script ausführen.
- **Wo:** `static/app.js` — `setLiveHtml()`, `refreshFeed()`, `refreshRecentTrades()`
- **Fix:** `.textContent` statt `.innerHTML` wo möglich. Für HTML-Struktur DOM-Elemente programmatisch erstellen.

### 12. CSRF-Schutz
- **Status:** ✅ Erledigt — Double-Submit Cookie Pattern. CSRF-Token in allen Forms (Login, Register, Forgot-PW, Reset-PW, Verify, Invite, Setup). Server-seitige Validierung mit `secrets.compare_digest()`.
- **Was:** POST-Forms ohne CSRF-Token. Bösartige Website könnte Aktionen im Namen des Users auslösen.
- **Wo:** `app.py` + alle Templates mit Forms
- **Fix:**
  1. `starlette-csrf` installieren
  2. Token in jedes `<form>` als Hidden Field
  3. Server-seitig validieren


## MEDIUM — Sollte gefixt werden

| # | Problem | Wo | Fix | Status |
|---|---------|----|-----|--------|
| 13 | E-Mail-Verifikation umgehbar | `auth_routes.py` | `require_auth()` muss `email_verified` prüfen | ❌ |
| 14 | Keine Server-seitige E-Mail-Validierung | `auth_routes.py` | `email-validator` Library | ❌ |
| 15 | Schwache Passwort-Anforderungen | `auth_routes.py` | Mixed characters oder `zxcvbn` | ❌ |
| 16 | REST API Calls ohne Timeout | `rest_client.py` | `aiohttp.ClientTimeout(total=10)` | ❌ |
| 17 | WebSocket-Nachrichten ohne Validierung | `websocket_client.py` | Schema-Validierung vor Verarbeitung | ❌ |
| 18 | Balance nur via WebSocket (manipulierbar) | `customer_ws.py` | Periodischer REST-API-Gegencheck | ❌ |
| 19 | `/api/history` ohne Limit-Cap | `api_routes.py` | `limit = min(limit, 100)` | ❌ |
| 20 | Sensitive Daten in Logs | `rest_client.py`, diverse | API-Responses nicht loggen, Log-Rotation | ❌ |
| 21 | `*.db` nicht in `.gitignore` | `.gitignore` | Hinzufügen | ❌ |
| 22 | Deploy ohne Integrity-Checks | `deploy.sh` | Checksums, Non-Root Deploy | ❌ |


## LOW — Nice-to-have

| # | Problem | Fix | Status |
|---|---------|-----|--------|
| 23 | `.env.example` enthält echte Master UID | Placeholder-Werte | ❌ |
| 24 | Telegram-Passwort ohne Timing-Safe-Vergleich | `hmac.compare_digest()` | ❌ |
| 25 | `datetime.utcnow()` deprecated | `datetime.now(timezone.utc)` | ❌ |
| 26 | Keine Auto-Security-Updates auf Server | `unattended-upgrades` | ❌ |
| 27 | Hardcodierte Server-IP | `DASHBOARD_URL` aus env | ❌ |


## Reihenfolge der Umsetzung

1. HTTPS/TLS prüfen (möglicherweise schon aktiv)
2. Lokale .env löschen + Keys rotieren
3. Secure-Flag auf Cookies
4. Rate Limiting
5. Security Headers
6. SSH härten
7. DB-Backups einrichten
8. Dashboard-Service härten
9. Sessions nach PW-Reset invalidieren
10. API Keys verschlüsseln (Fernet)
11. CSRF-Schutz
12. XSS fixen (innerHTML)
13. E-Mail-Verifikation in Auth-Check
14. Rest (Medium + Low)
