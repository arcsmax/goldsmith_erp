# Production Hardening — Design Spec

**Date:** 2026-04-01
**Goal:** Make Goldsmith ERP reliable enough for daily workshop use on a single self-hosted server.

**Deployment model:** One Linux/macOS machine on a local network. The goldsmith is non-technical — initial setup done by a developer, day-to-day management via the web UI. All users are on the same local network.

**Architecture:** 4 independent layers, each deployable and testable separately. They share only `main.py` (router registration) and `podman-compose.prod.yml`.

---

## Layer 1: Infrastructure

### Setup Script (`setup.sh`)

Interactive first-time setup. Idempotent — safe to re-run.

**Prompts:**
- Workshop name (used in UI branding and backup file names)
- Admin email and password
- Backup folder path (default: `~/goldsmith-backups/`)
- Optional: cloud sync URL (S3-compatible endpoint, or empty to skip)

**Actions:**
1. Generate `.env.production` with:
   - `SECRET_KEY` — 64-char random via `python -c "import secrets; print(secrets.token_urlsafe(64))"`
   - `ENCRYPTION_KEY` — 32-byte Fernet key for PII encryption
   - `DATABASE_URL` — `postgresql+asyncpg://goldsmith:$GENERATED_PW@db:5432/goldsmith_erp` (uses container service name `db`, not `localhost`)
   - `REDIS_URL` — `redis://redis:6379/0` (uses container service name `redis`)
   - `BACKUP_DIR`, `WORKSHOP_NAME`, cloud sync settings
   - `DEBUG=false`, `ACCESS_TOKEN_EXPIRE_MINUTES=1440` (24h for workshop use)
2. Create directories: backups, logs, uploads
3. Pull/build container images
4. Run `alembic upgrade head`
5. Create admin user via management command
6. Start services
7. Print: `"Goldsmith ERP läuft auf http://<detected-local-ip>:3000"`

**Error handling:** Each step checks success before proceeding. On failure, prints what went wrong and how to fix it in plain German.

### Production Compose (`podman-compose.prod.yml`)

Separate from development compose. Production-specific settings:

```yaml
services:
  backend:
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 512M
          cpus: "1.0"
    logging:
      driver: json-file
      options:
        max-size: "10m"
        max-file: "3"
    env_file: .env.production
    volumes:
      - pgdata:/var/lib/postgresql/data
      - ./uploads:/app/uploads
    ports:
      - "0.0.0.0:8000:8000"

  frontend:
    restart: unless-stopped
    ports:
      - "0.0.0.0:3000:3000"

  db:
    restart: unless-stopped
    volumes:
      - pgdata:/var/lib/postgresql/data
    deploy:
      resources:
        limits:
          memory: 256M

  redis:
    restart: unless-stopped
    deploy:
      resources:
        limits:
          memory: 128M

volumes:
  pgdata:
    driver: local
```

No reverse proxy — local network doesn't need TLS. Document how to add Caddy later if internet exposure is ever needed.

### Systemd Integration

- `make install-service` generates and installs a systemd unit via `podman generate systemd`
- Auto-start on boot, auto-restart on crash
- `systemctl status goldsmith-erp` for quick health check

### Makefile Additions

| Target | Purpose |
|--------|---------|
| `make setup` | Run setup.sh |
| `make prod-start` | Start production containers |
| `make prod-stop` | Stop production containers |
| `make prod-restart` | Restart all |
| `make prod-logs` | Tail production logs |
| `make prod-status` | Container health + disk usage summary |
| `make update` | Pull latest, run migrations, restart |
| `make backup-now` | Trigger manual backup |
| `make install-service` | Install systemd auto-start |

---

## Layer 2: Data Safety

### Automated Backup System

**Backup script (`scripts/backup.sh`):**
- Runs `pg_dump` against the PostgreSQL container
- Output: `$BACKUP_DIR/goldsmith_erp_YYYY-MM-DD_HHMMSS.sql.gz` (gzipped)
- Retention: keep last 7 daily + last 4 weekly + last 3 monthly (configurable)
- Old backups beyond retention are deleted automatically
- Exit code 0 on success, non-zero on failure (for cron/systemd monitoring)

**Scheduling:**
- Cron job or systemd timer: daily at 02:00 (workshop is closed)
- `make install-backup-cron` target to set it up
- Backup runs inside the Podman network (connects to `db` container directly)

**Optional cloud sync (`scripts/backup-sync.sh`):**
- If `BACKUP_CLOUD_URL` is set in `.env.production`:
  - After successful local backup, sync to S3-compatible storage
  - Uses `rclone` or plain `curl` with S3 presigned URLs (avoid heavy deps)
  - Falls back gracefully if cloud is unreachable — local backup is always the primary
- If not set, script is a no-op

**Restore script (`scripts/restore.sh`):**
- Takes a backup file path as argument
- Confirms with user before overwriting: "WARNUNG: Alle aktuellen Daten werden überschrieben. Fortfahren? (j/n)"
- Stops backend, restores dump, runs migrations (in case backup is from older version), restarts
- `make restore FILE=path/to/backup.sql.gz`

### Migration Verification

**Pre-deploy migration check (`scripts/check-migrations.sh`):**
- Before `make update`, verify migration chain is consistent
- Run `alembic check` to detect pending migrations
- Run `alembic upgrade --sql head` (dry-run) to verify SQL is valid
- Block deployment if migrations would fail

**Migration chain test:**
- CI job that runs full migration chain from scratch: `alembic upgrade head` on empty database
- Verifies all 13+ migrations apply cleanly in sequence

### Connection Pooling

**SQLAlchemy pool configuration** in `db/session.py`:

```python
# Production pool settings (read from config)
pool_size=5          # Base connections (5 goldsmiths max typical)
max_overflow=10      # Burst capacity
pool_timeout=30      # Wait for connection before error
pool_recycle=1800    # Recycle connections every 30 min
pool_pre_ping=True   # Test connection before use (handles DB restarts)
```

No PgBouncer needed for a single-workshop deployment. SQLAlchemy's built-in pool is sufficient for <20 concurrent users.

### Redis Resilience

- Already implemented: `cache.py` has graceful fallback when Redis unavailable
- Add: Redis `maxmemory 64mb` + `maxmemory-policy allkeys-lru` in production compose
- Add: Connection retry with exponential backoff in `pubsub.py` (currently fails immediately)

---

## Layer 3: Observability

### Admin Dashboard Page (`/admin/system`)

A new page in the React frontend, accessible only to ADMIN role. Shows at-a-glance system health.

**Sections:**

1. **System Status Cards:**
   - Backend: running/stopped, uptime, version
   - Database: connected/disconnected, size on disk, connection pool usage
   - Redis: connected/disconnected, memory usage, key count
   - Disk: total/used/free for data volume and backup volume

2. **Backup Status:**
   - Last backup: timestamp, size, success/failed
   - Next scheduled backup
   - Backup history (last 10) with status indicators
   - "Backup jetzt erstellen" button (triggers manual backup)
   - Cloud sync status: last sync time, success/failed

3. **Application Metrics:**
   - Active users (currently logged in via WebSocket)
   - Orders this month (new, completed)
   - API request count today
   - Average response time (last hour)

4. **Alerts:**
   - Any active system warnings (disk >80%, backup failed, Redis down)
   - Uses the existing notification system to push alerts to admin

### Backend Health Endpoints

**Enhanced `/health` endpoint:**
Current: returns `{"status": "healthy"}` always.
New: returns component-level health:

```json
{
  "status": "healthy",
  "components": {
    "database": { "status": "up", "latency_ms": 2 },
    "redis": { "status": "up", "latency_ms": 1 },
    "disk": { "status": "ok", "free_gb": 45.2 }
  },
  "version": "1.0.0",
  "uptime_seconds": 86400
}
```

**New `/api/v1/admin/system-info` endpoint (ADMIN only):**
Returns detailed system metrics for the dashboard:
- Database: size, connection pool stats, table row counts
- Redis: memory, connected clients, keyspace stats
- Backup: last backup info (read from backup log file)
- Disk: volume usage for data, backups, uploads
- Application: active WebSocket connections, request stats (from in-memory counter)

**New `/api/v1/admin/trigger-backup` endpoint (ADMIN only):**
- Triggers `scripts/backup.sh` as a subprocess
- Returns immediately with `{"status": "started"}`
- Backup result published as notification when complete

### System Notifications

Wire system events into the existing notification system:

| Event | Severity | Message |
|-------|----------|---------|
| Backup completed | INFO | "Backup erfolgreich: goldsmith_erp_2026-04-01.sql.gz (45 MB)" |
| Backup failed | URGENT | "Backup fehlgeschlagen! Bitte Administrator kontaktieren." |
| Cloud sync failed | WARNING | "Cloud-Synchronisation fehlgeschlagen. Lokales Backup vorhanden." |
| Disk space <20% | WARNING | "Speicherplatz knapp: nur noch X GB frei." |
| Disk space <5% | URGENT | "KRITISCH: Speicherplatz fast voll! Sofort handeln." |
| Redis disconnected | WARNING | "Redis nicht erreichbar. Caching deaktiviert." |
| Redis reconnected | INFO | "Redis-Verbindung wiederhergestellt." |
| Database connection pool exhausted | URGENT | "Datenbankverbindungen erschöpft. System möglicherweise langsam." |

Notifications are created by the backend health check service which runs on a periodic interval (every 5 minutes).

### Request Metrics (Lightweight)

No Prometheus/Grafana for a single-server workshop — too much complexity. Instead:

**In-memory request counter middleware:**
- Counts requests per endpoint per minute (ring buffer, last 60 minutes)
- Tracks p50/p95/p99 response times per endpoint
- Resets on restart (acceptable for a workshop)
- Exposed via `/api/v1/admin/system-info`

This gives the admin dashboard enough data to show "API is responsive" or "something is slow" without deploying an entire monitoring stack.

---

## Layer 4: Security

### Secret Management

**`.env.production` generation:**
- `setup.sh` generates all secrets automatically — no manual key creation
- `SECRET_KEY`: 64-char URL-safe random
- `ENCRYPTION_KEY`: 32-byte Fernet key (for GDPR PII encryption)
- `DB_PASSWORD`: 24-char random
- File permissions: `chmod 600 .env.production`

**Secret rotation script (`scripts/rotate-secrets.sh`):**
- Generates new `SECRET_KEY` (invalidates all JWTs — users must re-login)
- Optionally rotates `DB_PASSWORD` (updates both .env and PostgreSQL)
- Does NOT rotate `ENCRYPTION_KEY` (would make encrypted PII unreadable)
- `make rotate-secrets`

### Cookie Hardening

The JWT token flow currently has inconsistencies (sometimes localStorage, sometimes HttpOnly cookie). Standardize:

- Login sets `HttpOnly`, `SameSite=Lax`, `Secure=false` (local network, no TLS) cookie
- Frontend reads token from cookie (not localStorage) for API requests
- Keep `access_token` in login response body during transition (frontend refresh interceptor depends on it), but mark it deprecated — cookie is the primary auth mechanism
- `Secure=true` can be enabled later if TLS is added
- CSRF protection: `SameSite=Lax` is sufficient for same-origin requests on a local network
- Migration path: backend sets cookie AND returns token in body. Frontend prefers cookie (Axios `withCredentials: true`). Once verified, a future release removes the body token.

### CSRF Protection

- `SameSite=Lax` cookies prevent cross-site request forgery for state-changing requests
- No CSRF token needed for API calls from the SPA (same-origin policy protects XHR/fetch)
- Document this decision so future developers don't add unnecessary CSRF tokens

### GDPR Operational Workflows

The GDPR models and encryption exist but the operational workflows don't. Add:

**Data export endpoint (`GET /api/v1/customers/{id}/export`):**
- ADMIN only
- Returns all customer data as JSON (decrypted PII, orders, measurements, time entries)
- Per GDPR Article 15 (Right of Access)
- Audit-logged

**Data deletion endpoint (`DELETE /api/v1/customers/{id}/gdpr-erase`):**
- ADMIN only
- Soft-delete with 30-day grace period (per existing CLAUDE.md rules)
- After 30 days: hard-delete customer, anonymize audit logs (`deleted_user_{hash}`)
- Returns confirmation with deletion schedule
- Per GDPR Article 17 (Right to Erasure)
- Audit-logged

**Scheduled GDPR cleanup job:**
- Runs daily (via the same cron/timer as backups)
- Finds customers past 30-day grace period → hard deletes
- Finds audit logs for deleted customers → anonymizes
- Logs what was cleaned up

### Input Validation Hardening

- Already done: Zod on frontend, Pydantic on backend
- Add: Request body size limit (10MB default) in production compose / middleware
- Add: File upload size limit and type validation for order photos
- Add: SQL query timeout (30 seconds) to prevent runaway queries

---

## File Inventory

New files to create:

| File | Layer | Purpose |
|------|-------|---------|
| `setup.sh` | Infrastructure | First-time setup wizard |
| `podman-compose.prod.yml` | Infrastructure | Production container config |
| `goldsmith-erp.service` | Infrastructure | Systemd unit template |
| `scripts/backup.sh` | Data Safety | Automated database backup |
| `scripts/backup-sync.sh` | Data Safety | Optional cloud backup sync |
| `scripts/restore.sh` | Data Safety | Database restore from backup |
| `scripts/check-migrations.sh` | Data Safety | Migration chain verification |
| `scripts/rotate-secrets.sh` | Security | Secret rotation |
| `scripts/gdpr-cleanup.sh` | Security | Scheduled GDPR data cleanup |
| `src/goldsmith_erp/api/routers/admin.py` | Observability | Admin system info endpoints |
| `src/goldsmith_erp/services/system_health_service.py` | Observability | Health checks and metrics |
| `src/goldsmith_erp/middleware/request_metrics.py` | Observability | Lightweight request counter |
| `frontend/src/pages/AdminSystemPage.tsx` | Observability | System status dashboard |
| `frontend/src/api/admin.ts` | Observability | Admin API client |
| `frontend/src/styles/admin.css` | Observability | Dashboard styles |

Files to modify:

| File | Changes |
|------|---------|
| `Makefile` | Add prod-start, backup-now, install-service, etc. |
| `src/goldsmith_erp/main.py` | Register admin router |
| `src/goldsmith_erp/api/routers/auth.py` | Cookie-only JWT, remove token from response body |
| `src/goldsmith_erp/api/routers/customers.py` | Add export and GDPR erase endpoints |
| `src/goldsmith_erp/db/session.py` | Production pool settings |
| `src/goldsmith_erp/core/pubsub.py` | Redis retry with backoff |
| `src/goldsmith_erp/core/config.py` | New settings (BACKUP_DIR, WORKSHOP_NAME, etc.) |
| `src/goldsmith_erp/services/notification_service.py` | System health notifications |
| `frontend/src/App.tsx` | Add /admin/system route |
| `frontend/src/layouts/MainLayout.tsx` | Add "System" nav link (ADMIN only) |

---

## What This Does NOT Include

- **TLS/HTTPS** — Not needed for local network. Document how to add Caddy if needed later.
- **Prometheus/Grafana** — Overkill for single server. Lightweight in-memory metrics instead.
- **Email notifications** — Adds SMTP complexity. In-app notifications are sufficient.
- **Multi-tenancy** — Single workshop only.
- **Load balancing** — Single server, <20 users.
- **Kubernetes** — Podman compose is sufficient.
- **CI/CD deployment** — Manual `make update` is fine for a single server.
