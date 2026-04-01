#!/usr/bin/env bash
# scripts/check-migrations.sh
# Verifies that all Alembic migrations are consistent and can be applied.
#
# Checks performed:
#   1. `alembic check`         — confirms the DB is at the head revision
#   2. `alembic upgrade --sql head` — dry-run to verify SQL generation
#
# Usage: ./scripts/check-migrations.sh
#
# Exit codes:
#   0  — all checks passed
#   1  — one or more checks failed

set -uo pipefail

# ── Resolve paths ─────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
SRC_DIR="${PROJECT_ROOT}/src"

# ── Logging helpers ───────────────────────────────────────────────────────────
log_info()  { echo "[$(date '+%Y-%m-%d %H:%M:%S')] INFO  $*"; }
log_error() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] ERROR $*" >&2; }

FAILED=0

# ── Check 1: alembic check ────────────────────────────────────────────────────
log_info "Check 1/2: alembic check (head revision verification)"
if (cd "${SRC_DIR}" && poetry run alembic check); then
    log_info "Check 1 PASSED"
else
    log_error "Check 1 FAILED: Database is not at alembic head revision."
    log_error "  Run: make migrate  (or: alembic upgrade head)"
    FAILED=1
fi

# ── Check 2: alembic upgrade --sql head (dry-run) ─────────────────────────────
log_info "Check 2/2: alembic upgrade --sql head (dry-run SQL generation)"
if (cd "${SRC_DIR}" && poetry run alembic upgrade --sql head > /dev/null 2>&1); then
    log_info "Check 2 PASSED"
else
    log_error "Check 2 FAILED: Migration SQL generation error."
    log_error "  Inspect migration files in alembic/versions/ for conflicts."
    FAILED=1
fi

# ── Summary ───────────────────────────────────────────────────────────────────
if [[ "${FAILED}" -eq 0 ]]; then
    log_info "All migration checks passed."
    exit 0
else
    log_error "One or more migration checks failed."
    exit 1
fi
