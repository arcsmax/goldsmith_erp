#!/usr/bin/env bash
# Compose validation tests for fix A4
# (docs/fix-plan/2026-04-23/A4-compose-defaults.md)
#
# Two guarantees enforced:
#   1. `POSTGRES_PASSWORD` unset -> `compose config` MUST fail.
#   2. With the password set, the DB port MUST bind to 127.0.0.1 (loopback).
#
# Tool selection: prefer podman-compose (matches project runtime); fall back
# to `docker compose` (identical compose-file validator). Note recorded in
# docs/fix-plan/2026-04-23/DECISIONS.md if the fallback is used.
#
# We explicitly bypass the repo-local `.env` file during validation because
# docker compose auto-loads it and would silently supply POSTGRES_PASSWORD,
# defeating Test 1. `--env-file /dev/null` isolates the check to the compose
# file contents only.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Pick the validator. `podman-compose` preferred; `docker compose` is a drop-in
# for the pure-YAML validation we care about here.
ENV_FILE_FLAG=()
if command -v podman-compose >/dev/null 2>&1; then
  COMPOSE=(podman-compose)
elif docker compose version >/dev/null 2>&1; then
  COMPOSE=(docker compose)
  ENV_FILE_FLAG=(--env-file /dev/null)
elif command -v docker-compose >/dev/null 2>&1; then
  COMPOSE=(docker-compose)
  ENV_FILE_FLAG=(--env-file /dev/null)
else
  echo "SKIP: no compose validator available (podman-compose / docker compose / docker-compose all missing)"
  exit 0
fi

echo "Using validator: ${COMPOSE[*]}"
if [[ ${#ENV_FILE_FLAG[@]} -gt 0 ]]; then
  echo "Isolation flag:  ${ENV_FILE_FLAG[*]}"
fi

FAIL_COUNT=0

# ---------------------------------------------------------------------------
# Test 1: missing POSTGRES_PASSWORD -> compose MUST fail on both dev files
# ---------------------------------------------------------------------------
echo
echo "[1] Unset POSTGRES_PASSWORD -> compose config must reject"
for file in podman-compose.yml docker-compose.yml; do
  set +e
  output=$(env -u POSTGRES_PASSWORD "${COMPOSE[@]}" "${ENV_FILE_FLAG[@]}" -f "$file" config 2>&1)
  rc=$?
  set -e
  if [[ $rc -eq 0 ]]; then
    echo "  FAIL: $file accepted missing POSTGRES_PASSWORD (rc=0)"
    FAIL_COUNT=$((FAIL_COUNT + 1))
  else
    if echo "$output" | grep -qi "POSTGRES_PASSWORD"; then
      echo "  PASS: $file correctly rejected (rc=$rc, message mentions POSTGRES_PASSWORD)"
    else
      echo "  PASS: $file rejected (rc=$rc)"
    fi
  fi
done

# ---------------------------------------------------------------------------
# Test 2: with POSTGRES_PASSWORD set -> port MUST bind to 127.0.0.1
# ---------------------------------------------------------------------------
echo
echo "[2] POSTGRES_PASSWORD=testpass -> DB port must bind to 127.0.0.1"
for file in podman-compose.yml docker-compose.yml; do
  set +e
  output=$(POSTGRES_PASSWORD=testpass "${COMPOSE[@]}" "${ENV_FILE_FLAG[@]}" -f "$file" config 2>&1)
  rc=$?
  set -e
  if [[ $rc -ne 0 ]]; then
    echo "  FAIL: $file config failed with POSTGRES_PASSWORD set (rc=$rc)"
    echo "$output" | head -10
    FAIL_COUNT=$((FAIL_COUNT + 1))
    continue
  fi
  # Extract the db service block and look for a 127.0.0.1 host_ip on the 5432
  # target. Accept either short form (127.0.0.1:<port>:5432) or long form
  # (host_ip: 127.0.0.1 with target: 5432 nearby).
  #
  # Use awk to isolate the `db:` service subtree: from `^  db:` until the
  # next top-level service (`^  [a-z]`) — then look for the port binding.
  db_block=$(echo "$output" | awk '
    /^[[:space:]]{2}db:/            { in_db=1; print; next }
    in_db && /^[[:space:]]{2}[a-z]/ { in_db=0 }
    in_db                           { print }
  ')
  if echo "$db_block" | grep -qE '127\.0\.0\.1:[0-9]+:5432'; then
    echo "  PASS: $file binds DB to 127.0.0.1 (short form)"
  elif echo "$db_block" | grep -q 'host_ip: 127.0.0.1' && echo "$db_block" | grep -q 'target: 5432'; then
    echo "  PASS: $file binds DB to 127.0.0.1 (long form)"
  else
    echo "  FAIL: $file does not bind DB to 127.0.0.1"
    echo "----- db service block -----"
    echo "$db_block" | head -40
    echo "----------------------------"
    FAIL_COUNT=$((FAIL_COUNT + 1))
  fi
done

echo
if [[ $FAIL_COUNT -gt 0 ]]; then
  echo "compose validation tests: FAIL ($FAIL_COUNT failure(s))"
  exit 1
fi
echo "compose validation tests: PASS"
