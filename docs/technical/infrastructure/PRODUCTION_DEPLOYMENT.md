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
| Netzwerk-Exposition | Redis + Backend an `127.0.0.1` gebunden (kein LAN-Zugriff, kein Auth auf Redis) | nur Caddy (`:80`/`:443`) ans LAN; Redis/Backend/Frontend nur `expose:` (kein Host-Port) |

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
integritätsgeprüften `pg_dump` **und** ein verschlüsseltes Archiv von
`MEDIA_DIR` (Standard: `<projekt>/uploads` — Fotos, generierte PDFs, ARCH
Phase 4), schreibt ein sha256-Manifest über beide Dateien, und wendet die
**gestaffelte Aufbewahrung** an (7 täglich / 4 wöchentlich / 3 monatlich,
für Dump, Medien-Archiv und Manifest getrennt gezählt), optional Cloud-Sync.

```bash
make backup-now                       # einmalig: scripts/backup.sh
make restore FILE=pfad/backup.sql.gz  # Wiederherstellung: scripts/restore.sh
```

`make restore` stellt seit diesem Änderungssatz **automatisch auch das
passende Medien-Archiv wieder her** (gleicher Zeitstempel, gleiches
Verzeichnis wie der Dump) — siehe Schritt 8, „Restore-Drill" für den Ablauf
und die Flags (`--dry-run`, `--skip-media`).

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
> Das gilt **nur für die Datenbank** — die GDPR-Löschung scrubt die
> `media_assets`-Zeilen, löscht aber (Stand dieses Änderungssatzes) nicht
> automatisch die zugehörigen Dateien aus einem wiederhergestellten
> Medien-Archiv (kein Orphan-Sweep implementiert). Ein Restore aus einem
> Backup, das älter als eine spätere Löschung ist, kann also die Datei einer
> bereits gelöschten Kundin physisch zurückbringen, auch wenn die
> `media_assets`-Zeile danach vom Löschjob wieder korrekt gescrubbt wird.
> Bis zu einem Orphan-Sweep: nach einem Restore mit Medien-Wiederherstellung
> das Löschprotokoll gegen `MEDIA_DIR` prüfen, statt sich allein auf den
> DB-Zustand zu verlassen. `--skip-media` umgeht das Problem, wenn nur die
> Datenbank wiederhergestellt werden muss.

---

## Schritt 7 – Systemd-Timer installieren (GDPR-Löschjob, Retention-Sweep, Health-Watchdog)

Drei compliance-kritische Aufgaben — die tägliche Art.-17-Löschung, der
wöchentliche `retention_class`-Sweep und der externe `/health`-Watchdog —
liegen als fertige systemd-User-Units unter `deploy/systemd/`, laufen aber
erst, wenn sie installiert, aktiviert und gestartet wurden. **Kein Backup,
keine DSGVO-Löschung, kein Health-Alert läuft, solange dieser Schritt
übersprungen wird.**

```bash
make install-timers     # kopiert + aktiviert + startet alle drei Timer (idempotent)
make timers-status      # zeigt systemctl --user list-timers 'goldsmith-*'
```

`make install-timers` ruft `scripts/install-timers.sh` auf, das:

1. alle `deploy/systemd/goldsmith-*.{service,timer}` nach
   `~/.config/systemd/user/` kopiert und dabei den Platzhalter
   `WorkingDirectory=%h/goldsmith_erp` durch den tatsächlichen
   Projekt-Root-Pfad ersetzt (funktioniert also unabhängig davon, wohin das
   Repo geklont wurde);
2. `systemctl --user daemon-reload` ausführt;
3. nur die drei `.timer`-Units aktiviert und startet (`enable --now`) — die
   zugehörigen `.service`/`-alert.service`-Units werden nur *durch* den Timer
   bzw. über `OnFailure=` ausgelöst und nie direkt aktiviert;
4. `loginctl enable-linger` best-effort setzt, damit die Timer auch laufen,
   wenn kein Benutzer eingeloggt ist;
5. am Ende `systemctl --user list-timers 'goldsmith-*'` ausgibt.

Erneutes Ausführen ist sicher (reines Überschreiben + `enable --now` ist ein
No-op auf bereits aktiven Units).

> ℹ️ **Produktion vs. Entwicklung:** die kopierten `.service`-Units haben
> standardmäßig `COMPOSE_FILE=podman-compose.yml`. Für einen Produktions-
> Host ergänze in der kopierten Unit
> (`~/.config/systemd/user/goldsmith-gdpr-cleanup.service` bzw.
> `-retention-sweep.service`) eine Zeile
> `Environment=COMPOSE_FILE=podman-compose.prod.yml` und lade danach
> `systemctl --user daemon-reload` neu.

> 🔒 **Retention-Sweep ist standardmäßig ein Dry-Run.** Der Sweep zählt und
> loggt nur Kandidatenzeilen, löscht aber nichts, bis ein Operator nach
> Prüfung der Dry-Run-Logs **und** Freigabe durch Anna+Henrik in der
> kopierten Unit `RETENTION_EXECUTE=1` setzt. Das ist eine bewusste,
> separate Entscheidung — `make install-timers` allein aktiviert keine
> Löschungen.

### Verifikations-Checkliste (Schritt 7)

- [ ] `make install-timers` lief ohne Fehler durch.
- [ ] `make timers-status` (bzw. `systemctl --user list-timers 'goldsmith-*'`)
      listet alle drei Timer mit einem Wert unter `NEXT` (nicht leer/`n/a`).
- [ ] `systemctl --user status goldsmith-gdpr-cleanup.timer
      goldsmith-retention-sweep.timer goldsmith-health-watchdog.timer` zeigt
      jeweils `active (waiting)`.
- [ ] `loginctl show-user "$(whoami)" -p Linger` zeigt `Linger=yes` (sonst
      stoppen die Timer beim Ausloggen — siehe Hinweis oben,
      `loginctl enable-linger $(whoami)` manuell nachholen).
- [ ] Für Produktion: `COMPOSE_FILE=podman-compose.prod.yml` wurde in den
      kopierten `-cleanup.service`/`-sweep.service`-Units ergänzt (siehe
      Hinweis oben) und `daemon-reload` danach erneut ausgeführt.
- [ ] `RETENTION_EXECUTE=1` ist eine bewusste, separate Entscheidung nach
      Anna+Henrik-Freigabe — nicht versehentlich beim Kopieren der Unit
      gesetzt.
- [ ] Ein manueller Testlauf je Job bestätigt Erreichbarkeit:
      `systemctl --user start goldsmith-health-watchdog.service` (sollte bei
      laufendem Backend sofort erfolgreich beenden).

Vollständige Installations- und Alerting-Anleitung (inkl. der einzelnen
Unit-Dateien und Policy-Hintergrund):
→ [GDPR_ERASURE_RETENTION.md](../GDPR_ERASURE_RETENTION.md).

---

## Schritt 8 – Upgrade, Rollback und Restore-Drill (OPS-08)

`make update` baut die Container aus dem aktuellen Checkout neu und führt
danach `alembic upgrade head` aus (`Makefile:update`). Es gibt **kein**
Registry-Image, das zurückgerollt werden könnte — "App-Rollback" bedeutet hier:
den vorherigen Codestand auschecken und neu bauen.

### Vor jedem Upgrade: Backup

```bash
make backup-now                       # scripts/backup.sh — komprimiert, geprüft
git rev-parse HEAD > /tmp/goldsmith-pre-update-commit   # für den Rollback-Fall
```

`make update` ruft `scripts/backup.sh` seit diesem Änderungssatz automatisch
vor dem Neubau auf; ein Upgrade ohne aktuelles Backup ist dennoch nicht
empfohlen (ein manuelles `make backup-now` unmittelbar davor kostet Sekunden).

### DB-Rollback (Alembic)

Migrationsdateien liegen unter `alembic/versions/` und sind datumsbasiert
benannt (z. B. `20260401_v1_initial_schema.py` … `20260925_w207_order_events.py`,
25 Dateien Stand dieses Audits) — **nicht** `001_...`/`002_...` wie im
veralteten `docs/DEPLOYMENT.md`. Die Kette ist nicht immer alphabetisch gleich
der Revisions-Reihenfolge; `alembic history` ist die verbindliche Quelle:

```bash
poetry run alembic current                 # aktueller Stand
poetry run alembic history --indicate-current
poetry run alembic downgrade -1            # eine Migration zurück
poetry run alembic downgrade <revision>    # zu einer bestimmten Revision
```

⚠️ Ein `downgrade` kann Spalten/Tabellen löschen, die die neuere Anwendung
geschrieben hat (Datenverlust für diese Migration). Immer zuerst das
Backup aus dem Schritt oben sichern; bei Zweifel stattdessen aus dem Backup
restaurieren (`make restore FILE=...`) statt `downgrade` auf eine
produktive DB mit neueren Daten anzuwenden.

### App-Rollback (fehlgeschlagenes Deployment)

Kein CI/CD-Image-Tag, kein Blue/Green — der Codestand selbst ist die
"Version". Bei einem fehlgeschlagenen `make update`:

```bash
git log --oneline -5                        # letzten guten Commit finden
git checkout <letzter-guter-commit-oder-tag>
poetry run alembic downgrade <passende Revision>   # falls die neue Migration schon lief
make update                                 # baut den alten Stand neu, migriert (No-op falls schon zurück)
```

Ohne Schema-Änderung im fehlgeschlagenen Release genügt `git checkout` +
`make prod-restart` (kein DB-Rollback nötig).

### Restore-Drill

Der DSGVO-Löschjob macht eine Wiederherstellung besonders heikel (ein altes
Backup kann bereits gelöschte Kunden zurückbringen). Ablauf und die
empfohlene **vierteljährliche** Restore-Probe (Backup einspielen, Löschjournal
erneut abspielen) stehen in
[GDPR_ERASURE_RETENTION.md, „Backups und Löschung"](../GDPR_ERASURE_RETENTION.md) —
dieselbe Übung dient auch als Test, dass ein Upgrade-Rollback tatsächlich
funktioniert, nicht nur der DSGVO-Fall.

**Medien-Wiederherstellung (seit diesem Änderungssatz).** `scripts/restore.sh
<dump-datei>` sucht automatisch nach dem zum Dump passenden Medien-Archiv
(`goldsmith_media_<gleicher-zeitstempel>.tar.gz[.gpg|.age]`, im selben
Verzeichnis wie der Dump) und dem sha256-Manifest
(`goldsmith_manifest_<zeitstempel>.sha256`), falls `backup.sh` eines
geschrieben hat:

1. Ist ein Manifest vorhanden, werden Dump und (falls gefunden) Medien-Archiv
   dagegen geprüft — eine Abweichung bricht die Wiederherstellung **vor**
   jeder Änderung ab (Exit-Code 1). Fehlt ein Eintrag oder das Manifest
   selbst (ältere Backups), wird nur gewarnt, nicht abgebrochen.
2. Nach `alembic upgrade head` wird das Medien-Archiv entschlüsselt und in
   ein temporäres Geschwisterverzeichnis von `MEDIA_DIR` entpackt; erst nach
   vollständigem Erfolg wird der bisherige `MEDIA_DIR`-Inhalt (falls
   vorhanden) nach `MEDIA_DIR.pre-restore` verschoben und das neue
   Verzeichnis an seine Stelle umbenannt (atomarer Swap — `MEDIA_DIR` ist nie
   halb beschrieben). `.pre-restore` wird bei jedem Lauf überschrieben, gilt
   also nur für den unmittelbar vorherigen Restore.
3. Fehlt kein passendes Medien-Archiv (z. B. Backup von vor ARCH Phase 4,
   oder das Backup schlug für die Medien fehl), wird das nur protokolliert
   (`WARN`) — die Datenbank-Wiederherstellung läuft normal weiter.
4. `--skip-media` überspringt die Medien-Wiederherstellung vollständig (nur
   Datenbank); `--dry-run` zeigt den vollständigen Plan (Dump, Medien-Archiv,
   Manifest-Status) ohne etwas zu verändern.

```bash
scripts/restore.sh --dry-run ~/goldsmith-backups/goldsmith_erp_<ts>.sql.gz.gpg
scripts/restore.sh ~/goldsmith-backups/goldsmith_erp_<ts>.sql.gz.gpg
scripts/restore.sh --skip-media ~/goldsmith-backups/goldsmith_erp_<ts>.sql.gz.gpg
```

> ⚠️ **Bekannte Lücke:** ein wiederhergestelltes Medien-Archiv kann Dateien
> zurückbringen, die seit dem Backup per Art.-17-Löschung entfernt wurden —
> die Löschung scrubt die `media_assets`-Zeile, aber es existiert (noch)
> kein Orphan-Sweep, der eine physisch wiederhergestellte Datei ohne
> gültige DB-Zeile erkennt und erneut löscht. Bei der vierteljährlichen
> Restore-Probe das Löschprotokoll gegen den wiederhergestellten `MEDIA_DIR`
> prüfen, bis das nachgerüstet ist.

### Log-Rotation

Alle fünf Dienste in `podman-compose.prod.yml` sind bereits mit
`logging: driver: json-file, max-size: 10m, max-file: 3` konfiguriert (max.
~30 MB Logs pro Container, älteste Datei wird automatisch verworfen) — es ist
keine zusätzliche `logrotate`-Einrichtung nötig. Zugriff:

```bash
make prod-logs                       # alle Dienste folgen
podman logs goldsmith-backend-prod --tail 200
```

### Zwei Betriebshinweise (SEC-F8, SEC-F10)

- **Keine weiteren Web-Apps auf derselben IP/Host betreiben.** Das Auth-Cookie
  nutzt `SameSite=Strict` auf einer IP-adressierten Seite; ein anderer Dienst
  auf demselben Host (andere Portnummer) gilt dem Browser als "same site" und
  könnte das Cookie sehen. Der Produktions-Host ist für die ERP allein.
- **Demo-Konten vor Produktivbetrieb rotieren/löschen.** Falls eine mit
  `make seed-demo` befüllte Datenbank jemals zu einer echten werden soll: die
  Demo-Mitarbeiterkonten teilen sich das Passwort `demo2026!`
  (`scripts/seed_demo.py`) — vor dem ersten echten Kundendatensatz löschen oder
  die Passwörter individuell setzen. Siehe
  [DATABASE_SEEDING.md](DATABASE_SEEDING.md).

---

## Deployment-Checkliste

- [ ] `./setup.sh` gelaufen, `.env.production` mit `600` vorhanden.
- [ ] `DEBUG=false`, `COOKIE_SECURE=true`, `BACKEND_CORS_ORIGINS` als JSON inkl. LAN-IP.
- [ ] `make prod-status` meldet Backend/DB/Redis + Caddy als gesund.
- [ ] Caddy-Root-CA auf allen Werkstattgeräten vertraut; `https://<IP>` ohne Warnung.
- [ ] Referenzdaten vorhanden (`make seed-production` idempotent), **keine** Demo-Daten.
- [ ] Backup-Zeitplan aktiv (`scripts/backup.sh` per Timer/Cron), Restore
      getestet (Datenbank **und** Medien-Archiv, siehe Schritt 8
      „Restore-Drill").
- [ ] `make install-timers` gelaufen; `make timers-status` zeigt alle drei
      Timer (GDPR-Löschung, Retention-Sweep, Health-Watchdog) aktiv — siehe
      Verifikations-Checkliste in Schritt 7.

## Siehe auch

- [INSTALLATION.md](INSTALLATION.md) – Podman-Installation, Dev-Schnellstart.
- [PODMAN_MIGRATION.md](PODMAN_MIGRATION.md) – Podman-Grundlagen, systemd-Integration.
- [PRODUCTION_TLS.md](PRODUCTION_TLS.md) – Caddy TLS-Proxy + CA-Vertrauen.
- [DATABASE_SEEDING.md](DATABASE_SEEDING.md) – Produktions- vs. Demo-Seed.
- [GDPR_ERASURE_RETENTION.md](../GDPR_ERASURE_RETENTION.md) – Löschung, Aufbewahrung, Backups.
- [ADR: Single-box deployment, migrate-on-boot](../../architecture/ADR-2026-09-25-single-box-deployment.md) – warum ein Host, kein SaaS.
