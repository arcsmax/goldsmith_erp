#!/usr/bin/env bash
# scripts/backup.sh
# Creates a compressed PostgreSQL dump, verifies integrity, applies retention
# policy, optionally syncs to cloud, and notifies the backend admin endpoint.
#
# Usage: ./scripts/backup.sh
# Reads configuration from .env.production at the project root.
#
# Exit codes:
#   0  — backup created and verified successfully
#   1  — backup failed or verification failed

set -euo pipefail

# ── Resolve project root (parent of scripts/) ─────────────────────────────────
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

# ── Apply defaults for optional variables ─────────────────────────────────────
BACKUP_DIR="${BACKUP_DIR:-${HOME}/goldsmith-backups}"
POSTGRES_USER="${POSTGRES_USER:-user}"
POSTGRES_DB="${POSTGRES_DB:-goldsmith}"
BACKUP_CLOUD_URL="${BACKUP_CLOUD_URL:-}"

COMPOSE_FILE="${PROJECT_ROOT}/podman-compose.prod.yml"
COMPOSE_CMD="podman-compose -f ${COMPOSE_FILE}"

# ── Logging helpers ───────────────────────────────────────────────────────────
log_info()  { echo "[$(date '+%Y-%m-%d %H:%M:%S')] INFO  $*"; }
log_warn()  { echo "[$(date '+%Y-%m-%d %H:%M:%S')] WARN  $*" >&2; }
log_error() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR $*" >&2; }

# ── Notify admin endpoint ─────────────────────────────────────────────────────
notify_admin() {
    local status="$1"
    local filename="$2"
    local size="$3"

    curl --silent --max-time 10 --retry 2 \
        -X POST "http://localhost:8000/api/v1/admin/notify-backup" \
        -H "Content-Type: application/json" \
        -d "{\"status\":\"${status}\",\"filename\":\"${filename}\",\"size\":\"${size}\"}" \
        || log_warn "Could not reach admin notify endpoint (non-fatal)"
}

# ── Ensure backup directory exists ────────────────────────────────────────────
BACKUP_DIR="${BACKUP_DIR/#\~/${HOME}}"   # expand leading tilde
mkdir -p "${BACKUP_DIR}"

# ── Build output filename ─────────────────────────────────────────────────────
TIMESTAMP="$(date '+%Y-%m-%d_%H%M%S')"
BACKUP_FILE="${BACKUP_DIR}/goldsmith_erp_${TIMESTAMP}.sql.gz"

log_info "Starting backup → ${BACKUP_FILE}"

# ── Run pg_dump piped through gzip ───────────────────────────────────────────
if ! ${COMPOSE_CMD} exec -T db \
        pg_dump -U "${POSTGRES_USER}" "${POSTGRES_DB}" \
    | gzip > "${BACKUP_FILE}"; then
    log_error "pg_dump failed. Aborting."
    notify_admin "failure" "${BACKUP_FILE}" "0"
    exit 1
fi

# ── Verify archive integrity ──────────────────────────────────────────────────
if ! gzip -t "${BACKUP_FILE}" 2>/dev/null; then
    log_error "Integrity check failed for ${BACKUP_FILE}. Previous backups are NOT deleted."
    notify_admin "corrupted" "${BACKUP_FILE}" "0"
    exit 1
fi

BACKUP_SIZE="$(du -sh "${BACKUP_FILE}" | cut -f1)"
log_info "Backup verified OK. Size: ${BACKUP_SIZE}"

# ── Retention: keep last 7 daily + 4 weekly (Sun) + 3 monthly (1st) ──────────
apply_retention() {
    local dir="$1"
    local pattern="goldsmith_erp_*.sql.gz"

    # Collect all backup files sorted oldest-first
    mapfile -t all_files < <(ls -1t "${dir}/${pattern}" 2>/dev/null | tac)

    declare -a keep=()
    local daily_count=0
    local weekly_count=0
    local monthly_count=0

    for f in "${all_files[@]}"; do
        local basename
        basename="$(basename "${f}")"
        # Extract date portion: goldsmith_erp_YYYY-MM-DD_HHMMSS.sql.gz
        local date_str
        date_str="$(echo "${basename}" | grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}')"
        if [[ -z "${date_str}" ]]; then
            keep+=("${f}")
            continue
        fi

        local day_of_week month_day
        day_of_week="$(date -j -f '%Y-%m-%d' "${date_str}" '+%u' 2>/dev/null \
                     || date -d "${date_str}" '+%u' 2>/dev/null || echo 0)"
        month_day="$(echo "${date_str}" | cut -d'-' -f3)"

        local is_sunday=false
        local is_first=false
        [[ "${day_of_week}" == "7" ]] && is_sunday=true
        [[ "${month_day}" == "01" ]]  && is_first=true

        local marked=false

        # Monthly: first of month, keep last 3
        if ${is_first} && (( monthly_count < 3 )); then
            keep+=("${f}")
            (( monthly_count++ ))
            marked=true
        fi

        # Weekly: Sunday, keep last 4
        if ${is_sunday} && (( weekly_count < 4 )); then
            # avoid double-counting if already in monthly
            if ! ${marked}; then
                keep+=("${f}")
            fi
            (( weekly_count++ ))
            marked=true
        fi

        # Daily: keep last 7
        if (( daily_count < 7 )); then
            if ! ${marked}; then
                keep+=("${f}")
            fi
            (( daily_count++ ))
            marked=true
        fi
    done

    # Delete files not in keep list
    for f in "${all_files[@]}"; do
        local found=false
        for k in "${keep[@]}"; do
            [[ "${f}" == "${k}" ]] && found=true && break
        done
        if ! ${found}; then
            log_info "Removing expired backup: $(basename "${f}")"
            rm -f "${f}"
        fi
    done
}

apply_retention "${BACKUP_DIR}"

# ── Optional cloud sync ───────────────────────────────────────────────────────
if [[ -n "${BACKUP_CLOUD_URL}" ]]; then
    log_info "Syncing backup to cloud storage…"
    "${SCRIPT_DIR}/backup-sync.sh" "${BACKUP_FILE}"
fi

# ── Notify success ────────────────────────────────────────────────────────────
notify_admin "success" "$(basename "${BACKUP_FILE}")" "${BACKUP_SIZE}"
log_info "Backup complete: $(basename "${BACKUP_FILE}")"
exit 0
