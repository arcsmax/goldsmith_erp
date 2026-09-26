# Technische und organisatorische Maßnahmen (TOMs, Art. 32 DSGVO)

**Verantwortliche:** `[Name der Goldschmiede]`, Inhaberin Anne `[Nachname]` · **Betrieb:** Max Kull (Auftragsverarbeiter, AVV)
**Stand:** 2026-09-25 · **Grundlage:** Code-Stand `audit/2026-09-fixes` · **Bezug:** Verzeichnis von Verarbeitungstätigkeiten (`docs/superpowers/plans/qr-barcode-workflow/VERZEICHNIS-VERARBEITUNGSTAETIGKEITEN.md`)

Diese Liste beschreibt, was der Code und die mitgelieferten Skripte **tatsächlich** tun (mit Fundstelle), und trennt davon, was organisatorisch geregelt werden muss. Einträge mit **(offen)** sind noch nicht umgesetzt.

> Die Angemessenheit der Maßnahmen (Art. 32 Abs. 1: Stand der Technik, Risiko) ist **vom Datenschutzberater zu bestätigen**. Für eine Werkstatt mit wenigen Mitarbeitenden und LAN-Betrieb wird das Schutzniveau als angemessen eingeschätzt, solange das System nicht aus dem Internet erreichbar ist.

## 1. Vertraulichkeit (Art. 32 Abs. 1 lit. b)

### 1.1 Zutritt und Zugang zum Server

| Maßnahme | Umsetzung |
|---|---|
| Server im abschließbaren Werkstattbereich | organisatorisch **(festlegen)** |
| Nur Caddy veröffentlicht Ports (80 → 443) | `podman-compose.prod.yml`; Test `tests/scripts/test_compose_hardening.py` (Datenbank, Redis, Backend nicht von außen erreichbar) |
| Rootless Podman, Container ohne Root-Daemon | `docs/technical/infrastructure/PODMAN_MIGRATION.md` |
| Nur LAN, kein öffentlicher Zugang | `deploy/Caddyfile` (`tls internal`, ausdrücklich nicht für das Internet) |

### 1.2 Zugriffskontrolle in der Anwendung

| Maßnahme | Umsetzung |
|---|---|
| Rollen ADMIN / GOLDSMITH / VIEWER mit Berechtigungen | `core/permissions.py`, `@require_permission` an Endpunkten |
| Finanz- und Designfelder für VIEWER serverseitig entfernt | `api/role_projection.py` (`FINANCIAL_VIEW`, `DESIGN_VIEW`) |
| Gesundheitsdaten (Allergien) nur GOLDSMITH/ADMIN und nur mit Einwilligung | `services/consent_service.py`, `CUSTOMER_HEALTH_VIEW` |
| Art. 15-Export, Art. 17-Löschung, Wertgutachten-PDF nur ADMIN | `api/routers/customers.py`, `api/routers/valuations.py` |
| Passwörter mit bcrypt gehasht | `core/security.py` (`CryptContext(schemes=["bcrypt"])`) |
| Kurzlebige Tokens (30 min), HttpOnly-Cookie mit `Secure` in Produktion | `core/config.py` (`ACCESS_TOKEN_EXPIRE_MINUTES`, `COOKIE_SECURE`-Pflicht) |
| Logout widerruft Token; Login-Drosselung je Konto | `tests/integration/test_token_revocation_flow.py` |
| Gleichlange Login-Antwort (kein Nutzer-Enumerieren über Zeit) | `core/security.py` (SEC-17), `tests/unit/test_login_timing.py` |
| Rate-Limits: 100/min anonym, 300/min angemeldet, 5 Exporte/Stunde | `middleware/rate_limiting.py`, echte Client-IP hinter dem Proxy (`core/client_ip.py`) |
| Öffentliches Kundenportal standardmäßig aus | `CUSTOMER_PORTAL_ENABLED=false` (`.env.example`) |
| Keine eigenen Konten für Auszubildende **(offen)**: Rolle fehlt | GDPR-Report §H.4 |

### 1.3 Verschlüsselung

| Maßnahme | Umsetzung |
|---|---|
| Kunden-PII in der Datenbank verschlüsselt (Fernet, AES-128-CBC + HMAC) | `core/encryption.py`, Spaltentyp `EncryptedString` (`db/types.py`) |
| Suchbare verschlüsselte Felder über HMAC-Blindindex | z. B. `customer_no_gos.value_hash` |
| Wertgutachten-Betrag verschlüsselt | `valuation_certificates.appraised_value` (`_appraised_value_cipher`) |
| Rechnungs-Schnappschuss und ausgestelltes PDF verschlüsselt | `invoices.snapshot`, `invoices.issued_pdf` |
| TLS zwischen Browser und Server | Caddy `tls internal`; Geräte vertrauen der lokalen CA (`PRODUCTION_TLS.md`) |
| TLS zum Mailserver | STARTTLS (587) bzw. SSL (465) in `services/email_service.py`; **(offen, W5-09)**: auf anderen Ports kein TLS-Zwang |
| Backups verschlüsselt (age oder gpg AES256), Schlüssel aus Datei | `scripts/backup.sh`, `scripts/lib/backup-crypto.sh` |
| `tolerate_plaintext` für Altbestände **(offen, GDPR-18)** | `db/types.py`; nach Prüfung „alle Zeilen verschlüsselt“ abschalten |

### 1.4 Trennung und Datenminimierung

| Maßnahme | Umsetzung |
|---|---|
| Keine PII in Logs (nur IDs); Test prüft jeden `logger.*`-Aufruf | `tests/unit/test_no_pii_in_logs.py` |
| Request-Log ohne Query-String | `middleware/logging.py`, nginx-Log-Format |
| Kundenmails nur aus kundenseitigen Feldern, nie interne Notizen | `services/automated_customer_email.py` (GDPR-13) |
| Fotos in Mails: nur ausgewählte, EXIF entfernt, verkleinert; Originale ohne EXIF gespeichert | `services/image_validation.py`, `photo_service.py` |
| Echtzeit-Nachrichten nur mit IDs und Status | `core/ws_manager.py` |
| Etiketten ohne HTML-Injektion; Name auf Etikett **(offen, GDPR-19)**: nur Initialen | `services/label_service.py` |

## 2. Integrität (Art. 32 Abs. 1 lit. b)

| Maßnahme | Umsetzung |
|---|---|
| Eingaben über Pydantic-Schemas validiert (`extra="forbid"` für Export-Schemas) | `models/*.py` |
| ORM statt SQL-Strings (keine SQL-Injection) | SQLAlchemy |
| Ausgestellte Rechnungen unveränderlich (Schnappschuss, SHA-256, write-once) | `services/invoice_snapshot_service.py` |
| Altgold nach Unterschrift unveränderlich | `tests/unit/test_scrap_gold_immutable_after_signing.py` |
| Statusverlauf je Auftrag | `order_events` |
| Audit-Log für Kunden- und Finanzdaten (wer, wann, was, Zweck) | `middleware/audit_logging.py` → `customer_audit_logs` |
| Sicherheits-Header (CSP, X-Frame-Options DENY, nosniff) | `middleware/security_headers.py`, `frontend/nginx-security-headers.conf` |

## 3. Verfügbarkeit und Belastbarkeit (Art. 32 Abs. 1 lit. b, c)

| Maßnahme | Umsetzung |
|---|---|
| Tägliches, verschlüsseltes, geprüftes Backup, Rotation 7/4/3 | `scripts/backup.sh` (cron/Timer; `make backup-now`) |
| Optionale Off-Site-Kopie | `scripts/backup-sync.sh` **(offen, GDPR-06)**: Upload nur über die URL authentifiziert; EU-Anbieter mit AVV wählen |
| Wiederherstellung mit Prüfung und Löschwiederholung vor dem Start | `scripts/restore.sh` |
| Hochgeladene Dateien (`./uploads`) im Backup **(offen)** | nicht Teil des DB-Dumps |
| Health-Check und Watchdog mit E-Mail-Alarm | `deploy/systemd/goldsmith-health-watchdog.*`, `api/routers/health.py` |
| Neustart-Policy und Healthcheck für jeden Container | `tests/scripts/test_compose_hardening.py` |
| Monitor läuft auf genau einem Worker (Advisory Lock) | `core/leader_lock.py` |

## 4. Verfahren zur regelmäßigen Überprüfung (Art. 32 Abs. 1 lit. d)

| Maßnahme | Umsetzung / Rhythmus |
|---|---|
| Automatische Tests in CI (Backend, Frontend, Skripte) | `.github/workflows/ci.yml` |
| Restore-Probe | vierteljährlich, `restore.sh --dry-run` plus Vollrestore auf Testrechner **(organisatorisch)** |
| Timer installiert und aktiv | `scripts/install-timers.sh --status` monatlich |
| Retention-Sweep: Probelauf-Protokoll prüfen | wöchentlich im Log; scharf erst nach Freigabe D-08 (`RETENTION_SCHEDULE.md`) |
| Abhängigkeits-Schwachstellen | Dependabot / CI-Audit |
| Überprüfung dieses Dokuments | jährlich und bei jedem Release, zusammen mit dem Verzeichnis |

## 5. Löschung und Betroffenenrechte

| Maßnahme | Umsetzung |
|---|---|
| Art. 17: Deaktivieren, Freitext schwärzen, Dateien löschen, Legal Hold für Belege, nach 30 Tagen hart löschen oder anonymisieren | `DELETE /customers/{id}/gdpr-erase`, `jobs/gdpr_cleanup.py` (täglicher Timer) |
| Löschung überlebt einen Restore | Erasure-Ledger + `cli/gdpr_replay_erasures.py` |
| Art. 15: vollständiger Export mit Pflichtangaben | `GET /customers/{id}/export` |
| Einwilligungen mit Nachweis und Widerruf | `customer_consents`, `services/consent_service.py` |
| Mitarbeiter-Anonymisierung | `UserService.anonymize_user` (`deleted_user_<HMAC>`) |
| Aufbewahrungsfristen je Tabelle | `docs/technical/RETENTION_SCHEDULE.md` |

## 6. Organisatorische Maßnahmen

| Maßnahme | Status |
|---|---|
| Schlüsselhinterlegung: `ENCRYPTION_KEY`, `ANONYMIZATION_SALT`, Backup-Schlüssel (age-Privatschlüssel oder gpg-Passphrase) ausgedruckt im Tresor der Inhaberin | **festlegen** |
| `.env.production` nur für den Betreiber lesbar (0600), nie im Git | `setup.sh`; prüfen |
| Auftragsverarbeitungsverträge (Betreiber, Mail-Anbieter, Backup-Speicher) | `docs/legal/AVV-CHECKLIST.md` |
| Datenpannen-Ablauf (72 h) | `docs/technical/security/BREACH-RUNBOOK.md` |
| Kundeninformation nach Art. 13 an der Theke und in Mails | `docs/legal/DATENSCHUTZHINWEISE-KUNDEN.md` |
| Mitarbeiterinformation nach Art. 13 / §26 BDSG | `MITARBEITER-INFORMATION-BDSG26.md` (Konflikt GDPR-14 beachten) |
| Verpflichtung der Mitarbeitenden auf Vertraulichkeit | **festlegen** (schriftlich, bei Einstellung) |
| Konten beim Austritt sofort deaktivieren | ADMIN, `POST /users/{id}/gdpr-erase` |
| Geräte mit Bildschirmsperre, keine gemeinsamen Konten | **festlegen** |
