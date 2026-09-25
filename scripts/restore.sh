#!/usr/bin/env bash
# scripts/restore.sh
# Restores the PostgreSQL database from a (normally encrypted) dump and then
# re-applies every GDPR erasure the dump does not know about.
#
# Usage:
#   ./scripts/restore.sh <backup-file.sql.gz.age|.sql.gz.gpg|.sql.gz>
#   ./scripts/restore.sh --dry-run <backup-file>   # checks + plan, no changes
#
# Steps:
#   1. Validates the backup file and (for encrypted dumps) the decryption key
#   2. Asks for explicit confirmation (German prompt)
#   3. Saves the erasure ledger from the LIVE database (so erasures made after
#      the last backup.sh run are not lost when the database is dropped)
#   4. Stops the backend and Redis
#   5. Drops and recreates the database, restores the dump
#   6. Runs alembic upgrade head
#   7. GDPR-07: dry-run of the erasure replay, then — after a second
#      confirmation — replays every executed erasure newer than the backup
#      BEFORE the stack goes live again
#   8. Restarts all services
#
# Decryption keys come from .env.production (see scripts/lib/backup-crypto.sh):
#   *.age → BACKUP_AGE_IDENTITY_FILE (bring the offline key for the restore)
#   *.gpg → BACKUP_PASSPHRASE_FILE
#
# Exit codes:
#   0  — restore completed successfully (erasures replayed)
#   1  — validation error, user abort, or restore failure
#   2  — restore done but the erasure replay failed or was declined: the
#        stack is NOT started; fix the problem and replay by hand (see the
#        printed command) before bringing it up

set -euo pipefail
umask 077

# ── Resolve paths ─────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${GOLDSMITH_ENV_FILE:-${PROJECT_ROOT}/.env.production}"

# shellcheck source=scripts/lib/backup-crypto.sh
source "${SCRIPT_DIR}/lib/backup-crypto.sh"

# ── Arguments ─────────────────────────────────────────────────────────────────
DRY_RUN=false
BACKUP_FILE=""
for arg in "$@"; do
    case "${arg}" in
        --dry-run) DRY_RUN=true ;;
        -h|--help) sed -n '2,33p' "${BASH_SOURCE[0]}"; exit 0 ;;
        -*) echo "ERROR: unknown option: ${arg}" >&2; exit 1 ;;
        *)  BACKUP_FILE="${arg}" ;;
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
    exit 1
fi

POSTGRES_USER="${POSTGRES_USER:-user}"
POSTGRES_DB="${POSTGRES_DB:-goldsmith}"
BACKUP_DIR="${BACKUP_DIR:-${HOME}/goldsmith-backups}"
BACKUP_DIR="${BACKUP_DIR/#\~/${HOME}}"
ERASURE_LEDGER_FILE="${ERASURE_LEDGER_FILE:-${BACKUP_DIR}/erasure-ledger/erasure-ledger.jsonl}"
ERASURE_LEDGER_FILE="${ERASURE_LEDGER_FILE/#\~/${HOME}}"

COMPOSE_FILE="${PROJECT_ROOT}/podman-compose.prod.yml"
COMPOSE_CMD="podman-compose -f ${COMPOSE_FILE}"
REPLAY_CMD="python -m goldsmith_erp.cli.gdpr_replay_erasures"

# ── Logging helpers ───────────────────────────────────────────────────────────
log_info()  { echo "[$(date '+%Y-%m-%d %H:%M:%S')] INFO  $*"; }
log_warn()  { echo "[$(date '+%Y-%m-%d %H:%M:%S')] WARN  $*" >&2; }
log_error() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR $*" >&2; }

# ── Validate argument ─────────────────────────────────────────────────────────
if [[ -z "${BACKUP_FILE}" ]]; then
    echo "Usage: $0 [--dry-run] <backup-file.sql.gz.age|.sql.gz.gpg|.sql.gz>" >&2
    exit 1
fi
if [[ ! -f "${BACKUP_FILE}" ]]; then
    log_error "File not found: ${BACKUP_FILE}"
    exit 1
fi

METHOD="$(backup_crypto_method_for_file "${BACKUP_FILE}")"
if [[ "${METHOD}" == "unknown" ]]; then
    log_error "Invalid backup file. Expected .sql.gz.age, .sql.gz.gpg or .sql.gz, got: ${BACKUP_FILE}"
    exit 1
fi
if [[ "${METHOD}" == "none" ]]; then
    log_warn "Unverschlüsseltes Backup (.sql.gz) — nur für Entwicklungsumgebungen vorgesehen."
fi
backup_crypto_check_decrypt "${METHOD}" || exit 1

# Backup time from the file name (local time of the backup host) with the
# current UTC offset; the replay subtracts a 24 h safety margin on top.
BACKUP_STAMP="$(basename "${BACKUP_FILE}" | grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{6}' || true)"
SINCE_ARG=()
if [[ -n "${BACKUP_STAMP}" ]]; then
    SINCE_ISO="${BACKUP_STAMP:0:10}T${BACKUP_STAMP:11:2}:${BACKUP_STAMP:13:2}:${BACKUP_STAMP:15:2}$(date '+%z')"
    SINCE_ARG=(--since "${SINCE_ISO}")
else
    log_warn "Kein Zeitstempel im Dateinamen — es wird das GESAMTE Löschprotokoll erneut angewendet."
fi

# ── Integrity check before proceeding ─────────────────────────────────────────
log_info "Prüfe Archiv-Integrität: ${BACKUP_FILE} (Verschlüsselung: ${METHOD})"
if ! backup_crypto_decrypt "${METHOD}" "${BACKUP_FILE}" | gzip -t 2>/dev/null; then
    log_error "Archiv ist beschädigt oder falscher Schlüssel (Entschlüsselung/gzip -t fehlgeschlagen). Abbruch."
    exit 1
fi

if ${DRY_RUN}; then
    echo "DRY-RUN: Backup ist lesbar. Es wurde nichts verändert."
    echo "  Backup-Datei    : $(basename "${BACKUP_FILE}")"
    echo "  Verschlüsselung : ${METHOD}"
    echo "  Löschprotokoll  : ${ERASURE_LEDGER_FILE}"
    echo "  Replay ab       : ${SINCE_ISO:-gesamtes Protokoll} (minus 24 h Sicherheitsabstand)"
    exit 0
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

# ── Save the erasure ledger from the live database (GDPR-07) ─────────────────
mkdir -p "$(dirname "${ERASURE_LEDGER_FILE}")"
if [[ ! -f "${ERASURE_LEDGER_FILE}" ]]; then
    printf '# Goldsmith ERP erasure ledger (GDPR-07). Append-only. Do not edit.\n' \
        > "${ERASURE_LEDGER_FILE}"
fi
chmod 600 "${ERASURE_LEDGER_FILE}"
LEDGER_NEW="$(mktemp "${ERASURE_LEDGER_FILE}.new.XXXXXX")"
if ${COMPOSE_CMD} exec -T backend ${REPLAY_CMD} export --known - \
        < "${ERASURE_LEDGER_FILE}" > "${LEDGER_NEW}"; then
    cat "${LEDGER_NEW}" >> "${ERASURE_LEDGER_FILE}"
    log_info "Löschprotokoll aus der laufenden Datenbank gesichert."
else
    log_warn "Laufende Datenbank nicht erreichbar — es wird das zuletzt von backup.sh"
    log_warn "gesicherte Löschprotokoll verwendet (Löschungen danach fehlen ggf.)."
fi
rm -f "${LEDGER_NEW}"

# ── Stop backend and Redis ────────────────────────────────────────────────────
log_info "Stoppe Backend- und Redis-Service…"
${COMPOSE_CMD} stop backend redis

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
backup_crypto_decrypt "${METHOD}" "${BACKUP_FILE}" \
    | gunzip -c \
    | ${COMPOSE_CMD} exec -T db \
        psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}"

# ── Run alembic upgrade head ──────────────────────────────────────────────────
log_info "Führe Datenbankmigrationen aus (alembic upgrade head)…"
${COMPOSE_CMD} run --rm backend \
    sh -c "cd /app/src && poetry run alembic upgrade head"

# ── GDPR-07: replay erasures BEFORE the stack goes live ──────────────────────
replay() {
    ${COMPOSE_CMD} run --rm -T backend ${REPLAY_CMD} replay --ledger - \
        ${SINCE_ARG[@]+"${SINCE_ARG[@]}"} "$@" < "${ERASURE_LEDGER_FILE}"
}

MANUAL_REPLAY="${COMPOSE_CMD} run --rm -T backend ${REPLAY_CMD} replay --ledger - ${SINCE_ARG[*]+${SINCE_ARG[*]}} --execute < ${ERASURE_LEDGER_FILE}"

log_info "DSGVO: Probelauf der Löschwiederholung (nichts wird verändert)…"
if ! replay; then
    log_error "Probelauf der Löschwiederholung fehlgeschlagen. Stack wird NICHT gestartet."
    log_error "Nach Behebung manuell ausführen: ${MANUAL_REPLAY}"
    exit 2
fi

echo ""
echo "  DSGVO: Die oben gelisteten Löschungen werden jetzt erneut angewendet,"
echo "  damit keine gelöschte Person durch das Backup zurückkehrt."
echo "  Löschungen erneut anwenden? (j/n)"
read -r -p "  Eingabe: " CONFIRM_REPLAY
if [[ "${CONFIRM_REPLAY}" != "j" && "${CONFIRM_REPLAY}" != "J" ]]; then
    log_error "Löschwiederholung abgelehnt. Stack wird NICHT gestartet (Art. 17 DSGVO)."
    log_error "Manuell ausführen: ${MANUAL_REPLAY}"
    exit 2
fi
if ! replay --execute; then
    log_error "Löschwiederholung fehlgeschlagen. Stack wird NICHT gestartet."
    log_error "Nach Behebung manuell ausführen: ${MANUAL_REPLAY}"
    exit 2
fi
log_info "Löschungen erneut angewendet."

# ── Restart Redis first, then all remaining services ─────────────────────────
log_info "Starte Redis neu…"
${COMPOSE_CMD} up -d redis

log_info "Starte alle Services neu…"
${COMPOSE_CMD} up -d

echo ""
echo "══════════════════════════════════════════════════════════════"
echo "  Wiederherstellung erfolgreich abgeschlossen."
echo "  Datenbank '${POSTGRES_DB}' wurde aus"
echo "  '$(basename "${BACKUP_FILE}")' wiederhergestellt;"
echo "  Löschungen aus dem Löschprotokoll wurden erneut angewendet."
echo "  Details: docs/technical/GDPR_ERASURE_RETENTION.md"
echo "           (Abschnitt \"Backups und Löschung\")"
echo "══════════════════════════════════════════════════════════════"
echo ""

exit 0
