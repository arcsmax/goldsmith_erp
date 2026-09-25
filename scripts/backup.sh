#!/usr/bin/env bash
# scripts/backup.sh
# Creates an ENCRYPTED, compressed PostgreSQL dump plus an encrypted archive
# of the media root (photos, generated PDFs — ARCH phase 4), verifies both,
# applies the retention policy, appends the GDPR erasure ledger, optionally
# syncs to the cloud, and notifies the backend admin endpoint.
#
# Media: MEDIA_DIR (default: <project>/uploads, the host side of the
# backend's /app/uploads mount, which holds PHOTO_STORAGE_PATH and
# FILE_STORAGE_ROOT) is archived to goldsmith_media_<ts>.tar.gz[.gpg|.age].
# Restore: decrypt, then `tar -xzf <file> -C <project>/uploads`.
#
# Usage:
#   ./scripts/backup.sh                 # encrypted backup (production)
#   ./scripts/backup.sh --dry-run       # print the plan, touch nothing
#   ./scripts/backup.sh --unencrypted   # DEV ONLY: plain .sql.gz
#
# Reads configuration from .env.production at the project root (override the
# path with GOLDSMITH_ENV_FILE, used by the tests).
#
# Encryption (GDPR-06, Art. 32 DSGVO) — see scripts/lib/backup-crypto.sh:
#   BACKUP_AGE_RECIPIENTS_FILE  → age (recommended: the private key stays
#                                 offline, the server can encrypt but never
#                                 decrypt)
#   BACKUP_PASSPHRASE_FILE      → gpg --symmetric (AES256), key read from file
# Without either the script refuses to run unless --unencrypted is given.
#
# Erasure ledger (GDPR-07): after each dump every executed Art. 17 erasure is
# appended to ERASURE_LEDGER_FILE (default
# $BACKUP_DIR/erasure-ledger/erasure-ledger.jsonl). The ledger is NOT part of
# the dump rotation: restore.sh replays it so a restore can never bring an
# erased customer back.
#
# Exit codes:
#   0  — backup created and verified successfully (and ledger appended)
#   1  — backup failed, verification failed, the ledger could not be
#        appended, or the media archive failed (the verified dump is kept in
#        the last two cases)
#   2  — usage / configuration error

set -euo pipefail
umask 077

# ── Resolve project root (parent of scripts/) ─────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${GOLDSMITH_ENV_FILE:-${PROJECT_ROOT}/.env.production}"

# shellcheck source=scripts/lib/backup-crypto.sh
source "${SCRIPT_DIR}/lib/backup-crypto.sh"

# ── Arguments ─────────────────────────────────────────────────────────────────
DRY_RUN=false
ALLOW_UNENCRYPTED=false
for arg in "$@"; do
    case "${arg}" in
        --dry-run)     DRY_RUN=true ;;
        --unencrypted) ALLOW_UNENCRYPTED=true ;;
        -h|--help)     sed -n '2,39p' "${BASH_SOURCE[0]}"; exit 0 ;;
        *) echo "ERROR: unknown argument: ${arg}" >&2; exit 2 ;;
    esac
done

# ── Load .env.production ──────────────────────────────────────────────────────
if [[ -f "${ENV_FILE}" ]]; then
    # shellcheck source=/dev/null
    set -a
    source "${ENV_FILE}"
    set +a
else
    echo "ERROR: ${ENV_FILE} not found. Run setup.sh first." >&2
    exit 2
fi

# ── Apply defaults for optional variables ─────────────────────────────────────
BACKUP_DIR="${BACKUP_DIR:-${HOME}/goldsmith-backups}"
BACKUP_DIR="${BACKUP_DIR/#\~/${HOME}}"   # expand leading tilde
POSTGRES_USER="${POSTGRES_USER:-user}"
POSTGRES_DB="${POSTGRES_DB:-goldsmith}"
BACKUP_CLOUD_URL="${BACKUP_CLOUD_URL:-}"
ERASURE_LEDGER_FILE="${ERASURE_LEDGER_FILE:-${BACKUP_DIR}/erasure-ledger/erasure-ledger.jsonl}"
ERASURE_LEDGER_FILE="${ERASURE_LEDGER_FILE/#\~/${HOME}}"
MEDIA_DIR="${MEDIA_DIR:-${PROJECT_ROOT}/uploads}"
MEDIA_DIR="${MEDIA_DIR/#\~/${HOME}}"

COMPOSE_FILE="${PROJECT_ROOT}/podman-compose.prod.yml"
COMPOSE_CMD="podman-compose -f ${COMPOSE_FILE}"

# ── Logging helpers ───────────────────────────────────────────────────────────
log_info()  { echo "[$(date '+%Y-%m-%d %H:%M:%S')] INFO  $*"; }
log_warn()  { echo "[$(date '+%Y-%m-%d %H:%M:%S')] WARN  $*" >&2; }
log_error() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR $*" >&2; }

# ── Encryption mode ───────────────────────────────────────────────────────────
backup_crypto_resolve_method || exit 2
if [[ "${BACKUP_CRYPTO_METHOD}" == "none" ]]; then
    if ! ${ALLOW_UNENCRYPTED}; then
        log_error "No backup encryption configured (BACKUP_AGE_RECIPIENTS_FILE or"
        log_error "BACKUP_PASSPHRASE_FILE in .env.production). Refusing to write an"
        log_error "unencrypted dump. For development only: --unencrypted."
        exit 2
    fi
    log_warn "UNENCRYPTED backup requested (--unencrypted). Never use this in production."
elif ${ALLOW_UNENCRYPTED}; then
    log_warn "--unencrypted ignored: encryption (${BACKUP_CRYPTO_METHOD}) is configured."
fi

# ── Build output filename ─────────────────────────────────────────────────────
TIMESTAMP="$(date '+%Y-%m-%d_%H%M%S')"
BACKUP_FILE="${BACKUP_DIR}/goldsmith_erp_${TIMESTAMP}.sql.gz$(backup_crypto_suffix)"
MEDIA_FILE="${BACKUP_DIR}/goldsmith_media_${TIMESTAMP}.tar.gz$(backup_crypto_suffix)"

if ${DRY_RUN}; then
    echo "DRY-RUN: no dump, no files written, nothing deleted."
    echo "  encryption : ${BACKUP_CRYPTO_METHOD}"
    echo "  backup file: ${BACKUP_FILE}"
    echo "  media dir  : ${MEDIA_DIR}"
    echo "  media file : ${MEDIA_FILE}"
    echo "  ledger file: ${ERASURE_LEDGER_FILE}"
    echo "  cloud sync : ${BACKUP_CLOUD_URL:+enabled}${BACKUP_CLOUD_URL:-disabled}"
    exit 0
fi

backup_crypto_check_encrypt || exit 2

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

mkdir -p "${BACKUP_DIR}"
chmod 700 "${BACKUP_DIR}"

log_info "Starting backup → ${BACKUP_FILE} (encryption: ${BACKUP_CRYPTO_METHOD})"

# ── pg_dump | gzip | encrypt → .partial, renamed only when complete ──────────
PARTIAL_FILE="${BACKUP_FILE}.partial"
MEDIA_PARTIAL="${MEDIA_FILE}.partial"
trap 'rm -f "${PARTIAL_FILE}" "${MEDIA_PARTIAL}"' EXIT

if ! ${COMPOSE_CMD} exec -T db \
        pg_dump -U "${POSTGRES_USER}" "${POSTGRES_DB}" \
    | gzip \
    | backup_crypto_encrypt > "${PARTIAL_FILE}"; then
    log_error "pg_dump / compression / encryption failed. Aborting."
    notify_admin "failure" "$(basename "${BACKUP_FILE}")" "0"
    exit 1
fi
mv "${PARTIAL_FILE}" "${BACKUP_FILE}"
chmod 600 "${BACKUP_FILE}"

# ── Verify archive integrity ──────────────────────────────────────────────────
verify_backup() {
    local file="${1:-${BACKUP_FILE}}"
    case "${BACKUP_CRYPTO_METHOD}" in
        none) gzip -t "${file}" 2>/dev/null ;;
        gpg)  backup_crypto_decrypt gpg "${file}" | gzip -t 2>/dev/null ;;
        age)
            if [[ -n "${BACKUP_AGE_IDENTITY_FILE:-}" && -r "${BACKUP_AGE_IDENTITY_FILE}" ]]; then
                backup_crypto_decrypt age "${file}" | gzip -t 2>/dev/null
            else
                # Private key is (correctly) offline: check the age header and
                # size only. The quarterly restore drill proves decryptability.
                log_warn "age identity not on this host — header check only (restore drill required)."
                [[ -s "${file}" ]] \
                    && head -c 21 "${file}" | grep -q "age-encryption.org/v1"
            fi
            ;;
    esac
}

if ! verify_backup "${BACKUP_FILE}"; then
    log_error "Integrity check failed for ${BACKUP_FILE}. Previous backups are NOT deleted."
    notify_admin "corrupted" "$(basename "${BACKUP_FILE}")" "0"
    exit 1
fi

BACKUP_SIZE="$(du -sh "${BACKUP_FILE}" | cut -f1)"
log_info "Backup verified OK. Size: ${BACKUP_SIZE}"

# ── Media archive: tar | gzip | encrypt → .partial, renamed when complete ─────
# Photos and generated PDFs live on disk, not in the dump; without this a
# restore brings back every media row pointing at a missing file.
MEDIA_OK=true
if [[ -d "${MEDIA_DIR}" ]]; then
    if tar -C "${MEDIA_DIR}" -cf - . \
        | gzip \
        | backup_crypto_encrypt > "${MEDIA_PARTIAL}"; then
        mv "${MEDIA_PARTIAL}" "${MEDIA_FILE}"
        chmod 600 "${MEDIA_FILE}"
        if verify_backup "${MEDIA_FILE}"; then
            log_info "Media archive verified OK. Size: $(du -sh "${MEDIA_FILE}" | cut -f1)"
        else
            MEDIA_OK=false
            log_error "Integrity check failed for ${MEDIA_FILE}."
        fi
    else
        MEDIA_OK=false
        log_error "Media archive (tar / compression / encryption) failed."
    fi
else
    MEDIA_OK=false
    log_error "Media directory ${MEDIA_DIR} not found (set MEDIA_DIR). Photos are NOT backed up."
fi

# ── Retention: keep last 7 daily + 4 weekly (Sun) + 3 monthly (1st) ──────────
apply_retention() {
    local dir="$1"
    local kind="${2:-dump}"

    # Newest first, so the counters keep the MOST RECENT backups. Matches
    # encrypted and plain dumps (or media archives, counted separately);
    # never matches *.partial or the ledger.
    local -a all_files=()
    if [[ "${kind}" == "media" ]]; then
        mapfile -t all_files < <(ls -1t \
            "${dir}"/goldsmith_media_*.tar.gz \
            "${dir}"/goldsmith_media_*.tar.gz.gpg \
            "${dir}"/goldsmith_media_*.tar.gz.age 2>/dev/null || true)
    else
        mapfile -t all_files < <(ls -1t \
            "${dir}"/goldsmith_erp_*.sql.gz \
            "${dir}"/goldsmith_erp_*.sql.gz.gpg \
            "${dir}"/goldsmith_erp_*.sql.gz.age 2>/dev/null || true)
    fi

    local -a keep=()
    local daily_count=0 weekly_count=0 monthly_count=0

    for f in "${all_files[@]}"; do
        local date_str
        date_str="$(basename "${f}" | grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}' || true)"
        if [[ -z "${date_str}" ]]; then
            keep+=("${f}")
            continue
        fi

        local day_of_week month_day
        day_of_week="$(date -d "${date_str}" '+%u' 2>/dev/null \
                     || date -j -f '%Y-%m-%d' "${date_str}" '+%u' 2>/dev/null || echo 0)"
        month_day="$(echo "${date_str}" | cut -d'-' -f3)"

        local marked=false
        if [[ "${month_day}" == "01" ]] && (( monthly_count < 3 )); then
            keep+=("${f}")
            monthly_count=$((monthly_count + 1))
            marked=true
        fi
        if [[ "${day_of_week}" == "7" ]] && (( weekly_count < 4 )); then
            ${marked} || keep+=("${f}")
            weekly_count=$((weekly_count + 1))
            marked=true
        fi
        if (( daily_count < 7 )); then
            ${marked} || keep+=("${f}")
            daily_count=$((daily_count + 1))
        fi
    done

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
apply_retention "${BACKUP_DIR}" media

# ── Erasure ledger (GDPR-07) ──────────────────────────────────────────────────
append_erasure_ledger() {
    local ledger="$1"
    mkdir -p "$(dirname "${ledger}")"
    if [[ ! -f "${ledger}" ]]; then
        printf '# Goldsmith ERP erasure ledger (GDPR-07). Append-only. Do not edit.\n' > "${ledger}"
    fi
    chmod 600 "${ledger}"
    local fresh
    fresh="$(mktemp "${ledger}.new.XXXXXX")"
    if ! ${COMPOSE_CMD} exec -T backend \
            python -m goldsmith_erp.cli.gdpr_replay_erasures export --known - \
            < "${ledger}" > "${fresh}"; then
        rm -f "${fresh}"
        return 1
    fi
    cat "${fresh}" >> "${ledger}"
    log_info "Erasure ledger: $(grep -c . "${fresh}" || true) new entr(y|ies) → ${ledger}"
    rm -f "${fresh}"
}

LEDGER_OK=true
if ! append_erasure_ledger "${ERASURE_LEDGER_FILE}"; then
    LEDGER_OK=false
    log_error "Erasure ledger could not be appended (backend unreachable?)."
    log_error "The dump is kept, but restore.sh can only replay erasures it knows about."
fi

# ── Optional cloud sync ───────────────────────────────────────────────────────
if [[ -n "${BACKUP_CLOUD_URL}" ]]; then
    log_info "Syncing backup to cloud storage…"
    "${SCRIPT_DIR}/backup-sync.sh" "${BACKUP_FILE}"
    if [[ -f "${MEDIA_FILE}" ]]; then
        "${SCRIPT_DIR}/backup-sync.sh" "${MEDIA_FILE}"
    fi
fi

if ! ${LEDGER_OK}; then
    notify_admin "ledger_failed" "$(basename "${BACKUP_FILE}")" "${BACKUP_SIZE}"
    exit 1
fi

if ! ${MEDIA_OK}; then
    notify_admin "media_failed" "$(basename "${BACKUP_FILE}")" "${BACKUP_SIZE}"
    exit 1
fi

# ── Notify success ────────────────────────────────────────────────────────────
notify_admin "success" "$(basename "${BACKUP_FILE}")" "${BACKUP_SIZE}"
log_info "Backup complete: $(basename "${BACKUP_FILE}")"
exit 0
