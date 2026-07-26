#!/usr/bin/env bash
# ==============================================================================
# health-watchdog.sh — external /health dead-man's-switch (finding 2.6)
#
# In-app health notifications are useless when the backend is down. This script
# runs OUTSIDE the backend (on the host, via a 5-minute systemd timer — see
# deploy/systemd/), curls the /health endpoint with retries, and on failure
# sends an out-of-band email via the import-light CLI
# goldsmith_erp.jobs.health_alert.
#
# Crucially the alert CLI does NOT need the backend process or the DB — it only
# reads the SMTP config from .env — so it still fires when the app is dead.
#
# Configuration (env vars, all optional):
#   HEALTH_URL          health endpoint          (default http://localhost:8000/health)
#   HEALTH_RETRIES      probe attempts           (default 3)
#   HEALTH_RETRY_DELAY  seconds between attempts (default 10)
#   HEALTH_TIMEOUT      per-probe curl timeout   (default 10)
#   ALERT_CMD           how to run the alert CLI (default "poetry run")
#                       Container deploy example:
#                         ALERT_CMD="podman run --rm --env-file .env <backend-image>"
#   HEALTH_ALERT_EMAIL  alert recipient (else falls back to SMTP_FROM); passed
#                       through to the CLI via the environment.
#
# Exit codes:
#   0  → backend healthy.
#   1  → backend unreachable (an out-of-band alert was dispatched, or was a
#        documented no-op if SMTP is unconfigured). Nonzero so `systemctl
#        --user status` surfaces the outage on every timer tick.
# ==============================================================================
set -euo pipefail

HEALTH_URL="${HEALTH_URL:-http://localhost:8000/health}"
RETRIES="${HEALTH_RETRIES:-3}"
RETRY_DELAY="${HEALTH_RETRY_DELAY:-10}"
TIMEOUT="${HEALTH_TIMEOUT:-10}"
ALERT_CMD="${ALERT_CMD:-poetry run}"

log() { echo "[$(date -u '+%Y-%m-%dT%H:%M:%SZ')] health-watchdog: $*"; }

attempt=1
http_code=""
while [ "$attempt" -le "$RETRIES" ]; do
    # --fail is NOT used: a 503 (degraded) still means the process is UP, and
    # we only alert on total unreachability / non-200. We inspect the code.
    if http_code=$(curl --silent --show-error --output /dev/null \
        --max-time "$TIMEOUT" --write-out '%{http_code}' "$HEALTH_URL" 2>/dev/null) \
        && [ "$http_code" = "200" ]; then
        log "OK (HTTP $http_code) on attempt ${attempt}/${RETRIES}"
        exit 0
    fi
    log "check FAILED (HTTP ${http_code:-none}) attempt ${attempt}/${RETRIES}"
    attempt=$((attempt + 1))
    if [ "$attempt" -le "$RETRIES" ]; then
        sleep "$RETRY_DELAY"
    fi
done

reason="Health endpoint unreachable or non-200 after ${RETRIES} attempts (last HTTP ${http_code:-none})."
log "ALL retries failed — dispatching out-of-band alert. ${reason}"

# The alert CLI is import-light, needs NO DB and NO running backend. It reuses
# the backend's SMTP config from .env; if SMTP is unconfigured it logs and
# exits 0 (documented no-op). Do not let a nonzero alert rc abort the script
# before we log it.
set +e
# shellcheck disable=SC2086  # ALERT_CMD is intentionally word-split (e.g. "poetry run")
${ALERT_CMD} python -m goldsmith_erp.jobs.health_alert \
    --reason "$reason" --target "$HEALTH_URL"
alert_rc=$?
set -e

if [ "$alert_rc" -ne 0 ]; then
    log "alert CLI exited nonzero (${alert_rc}) — SMTP configured but the send failed"
else
    log "alert dispatched (or no-op if SMTP unconfigured)"
fi

# The backend is down regardless of the alert outcome: exit nonzero so the
# outage is visible in `systemctl --user status goldsmith-health-watchdog`.
exit 1
