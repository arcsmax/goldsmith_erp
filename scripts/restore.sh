#!/usr/bin/env bash
# scripts/restore.sh
# Restores the PostgreSQL database from a compressed dump file.
#
# Usage: ./scripts/restore.sh <backup-file.sql.gz>
#
# Steps:
#   1. Validates the backup file
#   2. Asks for explicit confirmation (German prompt)
#   3. Stops the backend
#   4. Drops and recreates the database
#   5. Restores the dump
#   6. Runs alembic upgrade head
#   7. Restarts all services
#
# Exit codes:
#   0  — restore completed successfully
#   1  — validation error, user abort, or restore failure

set -euo pipefail

# ── Resolve paths ─────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${PROJECT_ROOT}/.env.production"

# ── Load .env.production ──────────────────────────────────────────────────────
if [[ -f "${ENV_FILE}" ]]; then
    # shellcheck source=/dev/null
    set -a
    source "${ENV_FILE}"
    set +a
else
    echo "ERROR: ${ENV_FILE} not found. Run setup.sh first." >&2
    exit 1
fi

POSTGRES_USER="${POSTGRES_USER:-user}"
POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-pass}"
POSTGRES_DB="${POSTGRES_DB:-goldsmith}"

COMPOSE_FILE="${PROJECT_ROOT}/podman-compose.prod.yml"
COMPOSE_CMD="podman-compose -f ${COMPOSE_FILE}"

# ── Logging helpers ───────────────────────────────────────────────────────────
log_info()  { echo "[$(date '+%Y-%m-%d %H:%M:%S')] INFO  $*"; }
log_error() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR $*" >&2; }

# ── Validate argument ─────────────────────────────────────────────────────────
if [[ $# -lt 1 ]] || [[ -z "$1" ]]; then
    echo "Usage: $0 <backup-file.sql.gz>" >&2
    exit 1
fi

BACKUP_FILE="$1"

if [[ ! -f "${BACKUP_FILE}" ]]; then
    log_error "File not found: ${BACKUP_FILE}"
    exit 1
fi

if [[ "${BACKUP_FILE}" != *.sql.gz ]]; then
    log_error "Invalid backup file. Expected a .sql.gz file, got: ${BACKUP_FILE}"
    exit 1
fi

# ── Integrity check before proceeding ─────────────────────────────────────────
log_info "Prüfe Archiv-Integrität: ${BACKUP_FILE}"
if ! gzip -t "${BACKUP_FILE}" 2>/dev/null; then
    log_error "Archiv ist beschädigt (gzip -t failed). Abbruch."
    exit 1
fi

# ── Confirmation prompt ───────────────────────────────────────────────────────
echo ""
echo "══════════════════════════════════════════════════════════════"
echo "  WARNUNG: Datenbankwiederherstellung"
echo "══════════════════════════════════════════════════════════════"
echo ""
echo "  Backup-Datei : $(basename "${BACKUP_FILE}")"
echo "  Datenbank    : ${POSTGRES_DB}"
echo ""
echo "  WARNUNG: Alle aktuellen Daten werden überschrieben."
echo "  Fortfahren? (j/n)"
echo ""
read -r -p "  Eingabe: " CONFIRM

if [[ "${CONFIRM}" != "j" && "${CONFIRM}" != "J" ]]; then
    echo "Abgebrochen."
    exit 1
fi

echo ""
log_info "Wiederherstellung startet…"

# ── Stop backend ──────────────────────────────────────────────────────────────
log_info "Stoppe Backend-Service…"
${COMPOSE_CMD} stop backend

# ── Drop and recreate the database ───────────────────────────────────────────
log_info "Lösche und erstelle Datenbank '${POSTGRES_DB}' neu…"
${COMPOSE_CMD} exec -T db \
    psql -U "${POSTGRES_USER}" -d postgres \
    -c "DROP DATABASE IF EXISTS \"${POSTGRES_DB}\";"

${COMPOSE_CMD} exec -T db \
    psql -U "${POSTGRES_USER}" -d postgres \
    -c "CREATE DATABASE \"${POSTGRES_DB}\" OWNER \"${POSTGRES_USER}\";"

# ── Restore the dump ──────────────────────────────────────────────────────────
log_info "Stelle Daten wieder her aus: $(basename "${BACKUP_FILE}")"
gunzip -c "${BACKUP_FILE}" \
    | ${COMPOSE_CMD} exec -T db \
        psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}"

# ── Run alembic upgrade head ──────────────────────────────────────────────────
log_info "Führe Datenbankmigrationen aus (alembic upgrade head)…"
${COMPOSE_CMD} run --rm backend \
    sh -c "cd /app/src && poetry run alembic upgrade head"

# ── Restart all services ──────────────────────────────────────────────────────
log_info "Starte alle Services neu…"
${COMPOSE_CMD} up -d

echo ""
echo "══════════════════════════════════════════════════════════════"
echo "  Wiederherstellung erfolgreich abgeschlossen."
echo "  Datenbank '${POSTGRES_DB}' wurde aus"
echo "  '$(basename "${BACKUP_FILE}")' wiederhergestellt."
echo "══════════════════════════════════════════════════════════════"
echo ""

exit 0
