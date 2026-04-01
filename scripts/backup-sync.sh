#!/usr/bin/env bash
# scripts/backup-sync.sh
# Uploads a backup file to an S3-compatible object store.
#
# Usage: ./scripts/backup-sync.sh <backup-file-path>
#
# Environment (read from .env.production or inherited):
#   BACKUP_CLOUD_URL  — S3-compatible base URL (e.g. https://s3.example.com/bucket)
#                       If unset the script exits 0 silently.
#
# Exit codes:
#   0  — upload succeeded, or BACKUP_CLOUD_URL is unset (graceful no-op)
#   0  — upload failed but degraded gracefully (local backup is primary)

set -uo pipefail

# ── Logging helpers ───────────────────────────────────────────────────────────
log_info()  { echo "[$(date '+%Y-%m-%d %H:%M:%S')] INFO  $*"; }
log_warn()  { echo "[$(date '+%Y-%m-%d %H:%M:%S')] WARN  $*" >&2; }

# ── Load .env.production if not already loaded ────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/../.env.production"

if [[ -f "${ENV_FILE}" ]] && [[ -z "${BACKUP_CLOUD_URL+x}" ]]; then
    # shellcheck source=/dev/null
    set -a
    source "${ENV_FILE}"
    set +a
fi

BACKUP_CLOUD_URL="${BACKUP_CLOUD_URL:-}"

# ── If no cloud URL configured, exit silently ─────────────────────────────────
if [[ -z "${BACKUP_CLOUD_URL}" ]]; then
    exit 0
fi

# ── Validate argument ─────────────────────────────────────────────────────────
if [[ $# -lt 1 ]] || [[ -z "$1" ]]; then
    log_warn "backup-sync.sh called without a file argument. Skipping."
    exit 0
fi

BACKUP_FILE="$1"

if [[ ! -f "${BACKUP_FILE}" ]]; then
    log_warn "File not found: ${BACKUP_FILE}. Skipping cloud sync."
    exit 0
fi

# ── Upload via S3-compatible PUT ──────────────────────────────────────────────
FILENAME="$(basename "${BACKUP_FILE}")"
UPLOAD_URL="${BACKUP_CLOUD_URL%/}/${FILENAME}"

log_info "Uploading ${FILENAME} to cloud storage…"

if curl --silent --fail \
        --max-time 300 \
        --retry 2 \
        --retry-delay 5 \
        -X PUT "${UPLOAD_URL}" \
        -H "Content-Type: application/octet-stream" \
        --data-binary "@${BACKUP_FILE}"; then
    log_info "Cloud sync succeeded: ${FILENAME}"
else
    log_warn "Cloud sync failed for ${FILENAME}. Local backup is still intact. (non-fatal)"
fi

# Always exit 0 — local backup is primary, cloud is best-effort
exit 0
