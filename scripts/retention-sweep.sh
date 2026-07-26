#!/usr/bin/env bash
# ==============================================================================
# retention-sweep.sh — per-entity retention_class enforcement wrapper
#
# Production-readiness.md 2026-07-26, finding 2.3. Sibling of gdpr-cleanup.sh:
# runs the retention sweep INSIDE the backend container. The sweep enforces the
# statutory retention buckets tagged on scan_logs / time_entries / material_usage
# (see goldsmith_erp.jobs.retention_sweep and GDPR_ERASURE_RETENTION.md §5).
#
#   * DRY-RUN (default): counts + logs candidate rows per table, deletes NOTHING.
#   * EXECUTE: pass --execute OR set RETENTION_EXECUTE=1 to actually delete
#     expired rows. Financial (financial_10y) rows are never touched inside
#     their §147 AO / HGB §257 statutory period.
#
# Exit-Code:
#   0  → sweep completed cleanly (dry-run or execute).
#   1  → at least one table failed OR backend not reachable.
#        (systemd OnFailure= fires the admin notification — see deploy/systemd/.)
#
# Recommended via systemd timer (deploy/systemd/, weekly). Cron alternative:
#   0 3 * * 0 /path/to/goldsmith_erp/scripts/retention-sweep.sh >> /var/log/retention-sweep.log 2>&1
# ==============================================================================
set -euo pipefail

COMPOSE_FILE="${COMPOSE_FILE:-podman-compose.yml}"
COMPOSE_CMD="${COMPOSE_CMD:-podman-compose}"

# DRY-RUN by default. Enable deletion via RETENTION_EXECUTE=1 or the --execute
# argument (either works, so the systemd unit can flip it via an Environment=).
EXECUTE_FLAG=""
if [ "${RETENTION_EXECUTE:-0}" = "1" ] || [ "${1:-}" = "--execute" ]; then
    EXECUTE_FLAG="--execute"
fi

MODE="DRY-RUN"
[ -n "$EXECUTE_FLAG" ] && MODE="EXECUTE"
echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] Retention-Sweep gestartet (Modus: ${MODE})"

# ---------------------------------------------------------------------------
# Ausführung im Backend-Container
# ---------------------------------------------------------------------------
if ! ${COMPOSE_CMD} -f "$COMPOSE_FILE" ps --services 2>/dev/null | grep -q "^backend$"; then
    echo "FEHLER: Backend-Container läuft nicht." >&2
    echo "Bitte zuerst starten: ${COMPOSE_CMD} -f $COMPOSE_FILE up -d backend" >&2
    exit 1
fi

# ``|| EXIT_CODE=$?`` prevents ``set -e`` from aborting before the summary line;
# the module exit code (0/1) is propagated to the caller / systemd.
EXIT_CODE=0
# shellcheck disable=SC2086  # EXECUTE_FLAG is intentionally word-split (empty or --execute)
${COMPOSE_CMD} -f "$COMPOSE_FILE" exec -T backend \
    python -m goldsmith_erp.jobs.retention_sweep ${EXECUTE_FLAG} || EXIT_CODE=$?

echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] Retention-Sweep beendet (Exit-Code: ${EXIT_CODE})"
exit "${EXIT_CODE}"
