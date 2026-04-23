# A4 — Compose password defaults + bind DB to 127.0.0.1 in dev

**Item:** A4 · **Severity:** P0 · **Effort:** S · **Owner:** OPS
**Source:** `docs/review/2026-04-23/FIX-PLAN.md` Group A, flagged by report 03

## Context

Dev compose files ship with `POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-pass}` and expose the DB on `0.0.0.0:5432`:

```yaml
# docker-compose.yml (lines 8, 12)
POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-pass}
ports:
  - "5432:5432"           # binds to 0.0.0.0 by default
```

```yaml
# podman-compose.yml (lines 13, 17)
POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-pass}
ports:
  - "${DB_PORT:-5432}:5432"
```

`core/config.py` already validates `SECRET_KEY` and fails loudly on the documented insecure default (good). But `POSTGRES_PASSWORD` has no such guard, and `0.0.0.0:5432` means a developer running this on a non-firewalled laptop or shared WiFi exposes their DB to the LAN with `user:pass`. `podman-compose.prod.yml:11` already uses the `:?error` pattern — mirror it to dev.

## Goal

Two behavioural changes in the dev compose files:
1. `POSTGRES_PASSWORD` must be set in the environment (or `.env`) — `podman-compose up` / `docker-compose up` MUST fail if it's unset.
2. DB port binds to `127.0.0.1:5432` by default, not `0.0.0.0:5432`. A developer who wants LAN access can override with an env var.

## Files

- **Modify** `docker-compose.yml` — replace all `POSTGRES_PASSWORD:-pass` with `POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set — copy .env.example to .env`; replace `- "5432:5432"` with `- "127.0.0.1:${DB_PORT:-5432}:5432"`.
- **Modify** `podman-compose.yml` — same two changes (all `${POSTGRES_PASSWORD:-pass}` and the port mapping).
- **Modify** `.env.example` — ensure `POSTGRES_PASSWORD=` is present with a placeholder line and a comment noting the compose files require it.
- Leave `podman-compose.prod.yml` untouched — already correct.

## Acceptance criteria

- [ ] `unset POSTGRES_PASSWORD; podman-compose -f podman-compose.yml config` exits non-zero with an error mentioning `POSTGRES_PASSWORD`.
- [ ] Same check against `docker-compose.yml` fails similarly.
- [ ] With `POSTGRES_PASSWORD=secret`, `podman-compose -f podman-compose.yml config` reports `published: "127.0.0.1:5432"` (not `0.0.0.0:5432`) for the db service port mapping.
- [ ] `docs/review/2026-04-23/` CVE report's P0 A4 line can be struck through (documented in DECISIONS.md if any nuance arose).
- [ ] No change to `podman-compose.prod.yml` (already uses the `:?` pattern).

## Test design (TDD)

This is a config fix — test via a repo-level shell assertion rather than pytest. Add this as a Makefile target and invoke it in CI (piggyback on the lint job).

```bash
# New Makefile target
validate-compose:
	@POSTGRES_PASSWORD=__test__ podman-compose -f podman-compose.yml config > /dev/null && echo "podman-compose.yml: OK"
	@POSTGRES_PASSWORD=__test__ docker-compose -f docker-compose.yml config > /dev/null 2>&1 && echo "docker-compose.yml: OK" || true
	@if unset POSTGRES_PASSWORD; podman-compose -f podman-compose.yml config > /dev/null 2>&1; then \
		echo "FAIL: podman-compose.yml accepted missing POSTGRES_PASSWORD"; exit 1; \
	else \
		echo "podman-compose.yml: correctly fails on missing POSTGRES_PASSWORD"; \
	fi
```

And a small bash test script to run locally:

```bash
# scripts/test-compose-validation.sh
#!/usr/bin/env bash
set -euo pipefail

# Test 1: missing POSTGRES_PASSWORD must fail
unset POSTGRES_PASSWORD
if podman-compose -f podman-compose.yml config > /dev/null 2>&1; then
  echo "FAIL: compose accepted missing POSTGRES_PASSWORD"; exit 1
fi

# Test 2: with password set, port binds to 127.0.0.1
export POSTGRES_PASSWORD=testpass
port_mapping=$(podman-compose -f podman-compose.yml config 2>/dev/null | grep -A1 "published:" | grep -oE '127\.0\.0\.1:[0-9]+' || true)
if [[ -z "$port_mapping" ]]; then
  echo "FAIL: DB port not bound to 127.0.0.1"; exit 1
fi

echo "compose validation tests: PASS"
```

## Implementation sketch

1. **Read** both compose files in full to ensure no related service references need updating.
2. **Write failing test** — add `scripts/test-compose-validation.sh` (make executable); run it; it fails on current code.
3. **Edit `docker-compose.yml`**:
   - Line 8: `POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set — copy .env.example to .env}`
   - Line 44: `- POSTGRES_PASSWORD=${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set}`
   - Line 48: in `DATABASE_URL`, change the `${POSTGRES_PASSWORD:-pass}` to `${POSTGRES_PASSWORD:?}`
   - Line 12-13: change `- "5432:5432"` to `- "127.0.0.1:${DB_PORT:-5432}:5432"`
4. **Edit `podman-compose.yml`** — same four substitutions at the matching lines.
5. **Edit `.env.example`** — confirm `POSTGRES_PASSWORD=changeme` exists with a comment; the file is already in `.gitleaks` allowlist so this is fine.
6. **Run** the test script → passes.
7. **Commit.**

## Parallel-safety

Owns `docker-compose.yml`, `podman-compose.yml`, `.env.example`, `scripts/test-compose-validation.sh`, and a Makefile target. No other Wave-1 item touches these files.

## Commit message

```
chore(compose): require POSTGRES_PASSWORD and bind DB to 127.0.0.1 in dev

Fix item A4 — weak committed default `POSTGRES_PASSWORD=pass` with an
0.0.0.0 bind was flagged as P0 by the security review. Use the same :?
required-var pattern that podman-compose.prod.yml already applies, and
restrict the dev port binding to loopback. Developers who want LAN
access can override DB_HOST_IP (or edit locally).

Ref: docs/fix-plan/2026-04-23/A4-compose-defaults.md
Ref: docs/review/2026-04-23/FIX-PLAN.md#group-a

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

## Open questions for the implementing agent

- Should the port binding offer an opt-in override for LAN access (e.g., `- "${DB_HOST_IP:-127.0.0.1}:${DB_PORT:-5432}:5432"`)? Err toward yes — zero cost, avoids friction for devs on separate machines.
- `.env.example` already contains `CHANGE_THIS_TO_A_SECURE_RANDOM_STRING_AT_LEAST_32_CHARS` for `SECRET_KEY`. Mirror: `POSTGRES_PASSWORD=changeme` with comment `# REQUIRED — compose files will refuse to start without this`.
