# Goldsmith ERP – Produktions-Deployment

**Vollständige Anleitung** für ein echtes Produktions-Deployment mit
gehärtetem Stack: `setup.sh` → `.env.production` → `podman-compose.prod.yml`
(Backend + DB + Redis + Frontend + **Caddy TLS-Proxy**) → CA-Vertrauen →
Referenz-Seed → Backups → DSGVO-Löschjob.

> ⚠️ **Der Schnellstart in [README](../../../README.md) und
> [INSTALLATION.md](INSTALLATION.md) beschreibt die ENTWICKLUNGS-Umgebung.**
> `setup-podman.sh` installiert Podman und startet den **Dev-Stack**
> (`podman-compose.yml`: Vite-Dev-Server, `.env` aus `.env.example`, `DEBUG`
> aktiv, **kein TLS**). Für einen Produktivbetrieb mit echten Kundendaten
> (PII, Finanzdaten, DSGVO + §147 AO) ist dieser Weg **nicht geeignet** —
> folge stattdessen dieser Anleitung.

---

## Dev-Stack vs. Produktions-Stack

| | Entwicklung | **Produktion** |
|---|---|---|
| Einstieg | `./setup-podman.sh` | **`./setup.sh`** (oder `make setup`) |
| Compose-Datei | `podman-compose.yml` | **`podman-compose.prod.yml`** |
| Umgebungsdatei | `.env` (aus `.env.example`) | **`.env.production`** (von `setup.sh` erzeugt) |
| `DEBUG` | `true` | **`false`** |
| Frontend | Vite-Dev-Server | nginx (gebautes SPA) |
| TLS | keins | **Caddy** (`:443`, `tls internal`) |
| Cookie `Secure` | aus | **`COOKIE_SECURE=true`** (Boot erzwingt es) |
| Seed | Demo-/Beispieldaten möglich | **nur Referenzdaten** + ein Admin |

Der einzige nach außen veröffentlichte Port im Produktions-Stack ist Caddy
(`80`/`443`). `backend` und `frontend` sind `expose`-only und nur im
Compose-Netz erreichbar — es gibt keinen Klartext-HTTP-Endpunkt im
Werkstattnetz. Details: [PRODUCTION_TLS.md](PRODUCTION_TLS.md).

---

## Voraussetzungen

- `podman`, `podman-compose`, `python3`, `poetry`
- Podman rootless eingerichtet (siehe [INSTALLATION.md](INSTALLATION.md) bzw.
  `setup-podman.sh` — nur der **Podman-Installationsteil** ist auch für
  Produktion nützlich; den Dev-Stack, den es startet, danach mit
  `podman-compose -f podman-compose.yml down` wieder stoppen).
- Eine Maschine im Werkstatt-LAN, feste oder per DHCP-Reservierung stabile IP.

---

## Schritt 1 – `setup.sh` (Ersteinrichtung)

```bash
# Im Projektwurzelverzeichnis:
./setup.sh          # oder: make setup
```

`setup.sh` ist **idempotent** (ein vorhandenes `.env.production` wird nicht
überschrieben) und führt der Reihe nach aus:

1. Abhängigkeiten prüfen.
2. **LAN-IP erkennen** — noch bevor `.env.production` geschrieben wird, damit
   die erkannte Adresse in die CORS-Allow-List aufgenommen wird (sonst werden
   die anderen Werkstattgeräte per CORS abgewiesen).
3. Konfiguration abfragen (Werkstattname, Admin-Zugang, Backup-Ordner,
   optionale Cloud-Sync-URL) und **Schlüssel generieren** (`SECRET_KEY`,
   `ENCRYPTION_KEY`, DB-Passwort).
4. `.env.production` schreiben (`chmod 600`, `DEBUG=false`,
   `COOKIE_SECURE=true`, CORS als JSON-Array inkl. LAN-IP).
5. Container über `podman-compose.prod.yml` bauen.
6. DB + Redis starten, auf `healthy` warten, **Migrationen** ausführen
   (`alembic upgrade head`).
7. Admin-Benutzer anlegen (`scripts/create-admin.py`).
8. **Alle Dienste starten** (inkl. Caddy).
9. Optional Firewall- (`ufw`/`firewalld`) und mDNS- (`avahi`) Regeln anbieten.

> ℹ️ **Hinweis zum Abschluss-Banner:** `setup.sh` gibt am Ende
> `http://<IP>:3000` / `:8000` aus. Im Produktions-Stack sind diese Ports
> jedoch **nicht** veröffentlicht (siehe oben) — der tatsächliche Zugang läuft
> über **`https://<IP>`** via Caddy (Schritt 4).

---

## Schritt 2 – `.env.production`

Von `setup.sh` erzeugt, enthält Geheimnisse — **niemals in Git einchecken**
(Berechtigung `600`). Die sicherheitsrelevanten Werte:

| Variable | Wert | Warum |
|---|---|---|
| `DEBUG` | `false` | Aktiviert die Prod-Validatoren in `core/config.py`. |
| `SECRET_KEY` | generiert | JWT-Signatur; Boot lehnt Platzhalter/kurze Keys ab. |
| `ENCRYPTION_KEY` | generierter Fernet-Key | Verschlüsselung der PII/Wertgutachten; ohne ihn **bootet das Backend nicht**. |
| `COOKIE_SECURE` | `true` | Auth-Cookie nur über HTTPS; Boot erzwingt es bei `DEBUG=false`. |
| `BACKEND_CORS_ORIGINS` | **JSON-Array** inkl. LAN-IP | pydantic-settings verlangt JSON; kommaseparierte Strings crashen den Boot. |
| `BACKUP_DIR` | z. B. `~/goldsmith-backups/` | Zielordner für `backup.sh`. |
| `SEED_REFERENCE_DATA` | `true` (Default) | Referenz-Seed beim Boot (siehe Schritt 5). |

Eine vollständige Referenz aller Variablen steht in `.env.example`.

---

## Schritt 3 – Der Produktions-Stack (`podman-compose.prod.yml`)

Fünf Dienste:

| Dienst | Image / Basis | Ports | Rolle |
|---|---|---|---|
| `db` | `postgres:15-alpine` | intern | Datenbank (Volume `pgdata`). |
| `redis` | `redis:7-alpine` | intern | Pub/Sub + Cache. |
| `backend` | FastAPI | `expose 8000` | API, Migrationen + Referenz-Seed beim Boot. |
| `frontend` | nginx (gebautes SPA) | `expose 3000` | SPA + Proxy für `/api`, `/ws`, `/uploads`. |
| `caddy` | `caddy:2-alpine` | **`80`/`443` veröffentlicht** | TLS-Terminierung (`tls internal`, `on_demand`). |

Verwaltung über die `make`-Ziele:

```bash
make prod-start     # alle Dienste starten
make prod-status    # Container + Health-Checks (Backend/DB/Redis)
make prod-logs      # Logs folgen
make prod-restart   # neu starten
make prod-stop      # stoppen
make update         # Images neu bauen, starten, Migrationen anwenden
```

---

## Schritt 4 – TLS + CA-Vertrauen

Caddy signiert das Zertifikat mit seiner **eigenen CA** (`tls internal`), da es
keine öffentliche Domain und kein öffentliches ACME gibt. Jedes Werkstattgerät
muss dieser Root-CA **einmalig vertrauen**, sonst zeigt der Browser eine
Zertifikatswarnung.

- Root-CA aus dem `caddy_data`-Volume exportieren, dann pro Gerät installieren.
- Danach ist die App unter **`https://<werkstatt-ip>`** (oder dem mDNS-Namen)
  ohne Warnung erreichbar.

**Vollständige Schritte (Export + macOS/iOS/Android/Windows/Firefox):**
→ [PRODUCTION_TLS.md](PRODUCTION_TLS.md).

---

## Schritt 5 – Datenbank-Seed (Produktion)

Ein frisches Produktivsystem braucht genau **zwei** Dinge geseedet: **einen
Admin-Benutzer** (legt `setup.sh` an) und die **Referenzdaten** (15
Standardtätigkeiten + Standard-Materialkatalog).

- **Automatisch beim Boot:** Der Backend-Container führt nach den Migrationen
  den idempotenten Referenz-Seed aus (`SEED_REFERENCE_DATA=true`, Default).
- **Manuell:** `make seed-production`
  (`python -m goldsmith_erp.db.reference_seed` im Backend-Container).

> ❌ **Niemals** `make seed-demo` oder `make seed` gegen die Produktionsdatenbank
> — sie erzeugen Fake-Personal mit dem geteilten Demo-Passwort und Fake-Kunden-PII.

Contract, Idempotenz und die vier Seed-Pfade im Detail:
→ [DATABASE_SEEDING.md](DATABASE_SEEDING.md).

---

## Schritt 6 – Backups

`scripts/backup.sh` liest `.env.production`, erstellt einen komprimierten,
integritätsgeprüften `pg_dump` und wendet die **gestaffelte Aufbewahrung** an
(7 täglich / 4 wöchentlich / 3 monatlich), optional Cloud-Sync.

```bash
make backup-now                       # einmalig: scripts/backup.sh
make restore FILE=pfad/backup.sql.gz  # Wiederherstellung: scripts/restore.sh
```

**Zeitplan (empfohlen).** Es wird kein fertiger Backup-Timer ausgeliefert;
richte einen `systemd`-User-Timer (analog zum DSGVO-Timer, siehe Schritt 7) oder
einen Cron-Eintrag ein, z. B. täglich nachts:

```bash
0 2 * * * cd /pfad/zu/goldsmith_erp && bash scripts/backup.sh >> ~/backup.log 2>&1
```

> 🔒 **DSGVO:** Eine Wiederherstellung kann bereits gelöschte Kunden für bis zu
> ~3 Monate zurückbringen. `restore.sh` weist am Ende darauf hin — danach den
> Löschjob erneut ausführen. Siehe
> [GDPR_ERASURE_RETENTION.md, „Backups und Löschung"](../GDPR_ERASURE_RETENTION.md).

---

## Schritt 7 – DSGVO-Löschjob (systemd-Timer)

Die Art.-17-Löschung nach Ablauf der 30-Tage-Frist wird durch nichts
automatisch ausgelöst, solange der Timer nicht installiert ist. Installiere die
User-Units aus `deploy/systemd/` (`goldsmith-gdpr-cleanup.{service,timer}` +
`…-alert.service`) und setze für Produktion `COMPOSE_FILE=podman-compose.prod.yml`.

Vollständige Installations- und Alerting-Anleitung:
→ [GDPR_ERASURE_RETENTION.md](../GDPR_ERASURE_RETENTION.md).

---

## Deployment-Checkliste

- [ ] `./setup.sh` gelaufen, `.env.production` mit `600` vorhanden.
- [ ] `DEBUG=false`, `COOKIE_SECURE=true`, `BACKEND_CORS_ORIGINS` als JSON inkl. LAN-IP.
- [ ] `make prod-status` meldet Backend/DB/Redis + Caddy als gesund.
- [ ] Caddy-Root-CA auf allen Werkstattgeräten vertraut; `https://<IP>` ohne Warnung.
- [ ] Referenzdaten vorhanden (`make seed-production` idempotent), **keine** Demo-Daten.
- [ ] Backup-Zeitplan aktiv (`scripts/backup.sh` per Timer/Cron), Restore getestet.
- [ ] DSGVO-Löschtimer installiert und `list-timers` zeigt ihn.

## Siehe auch

- [INSTALLATION.md](INSTALLATION.md) – Podman-Installation, Dev-Schnellstart.
- [PODMAN_MIGRATION.md](PODMAN_MIGRATION.md) – Podman-Grundlagen, systemd-Integration.
- [PRODUCTION_TLS.md](PRODUCTION_TLS.md) – Caddy TLS-Proxy + CA-Vertrauen.
- [DATABASE_SEEDING.md](DATABASE_SEEDING.md) – Produktions- vs. Demo-Seed.
- [GDPR_ERASURE_RETENTION.md](../GDPR_ERASURE_RETENTION.md) – Löschung, Aufbewahrung, Backups.
