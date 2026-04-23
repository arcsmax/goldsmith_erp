# F1 — Run integration tests against Postgres (not SQLite) in CI

**Item:** F1 · **Severity:** P0 · **Effort:** M · **Owner:** CI
**Status:** ⏳ pending (strategy locked 2026-04-23: Option C — split conftests)
**Source:** `docs/review/2026-04-23/FIX-PLAN.md` Group F, flagged by report 06

## Context

`tests/conftest.py:33` + `tests/integration/conftest.py:42` hard-code `sqlite+aiosqlite://`. CI provisions PG15 + sets `DATABASE_URL=postgresql+asyncpg://...` but the conftest ignores it. Consequence: every test runs SQLite, and `test_concurrent_metal_consumption.py` (FIFO/LIFO money race) `skipif(sqlite)` is silently skipped.

## Decision (locked 2026-04-23)

**Option C — split conftests.** Unit tests keep SQLite for speed. Integration tests honor `TEST_DATABASE_URL` env var, defaulting to PG in CI and SQLite locally.

## Goal

- `tests/integration/conftest.py` reads `TEST_DATABASE_URL` env var (fallback: `sqlite+aiosqlite:///:memory:` for quick local runs).
- A new CI job `test-integration-pg` sets `TEST_DATABASE_URL=postgresql+asyncpg://...` and runs `pytest tests/integration/`.
- Unit tests (`tests/unit/`, `tests/test_*.py`) unchanged, stay on SQLite.
- `test_concurrent_metal_consumption.py` actually runs (no longer silently skipped).
- `make test-integration-pg` local target for developers.

## Files

- **Modify** `tests/integration/conftest.py` — read `TEST_DATABASE_URL` with SQLite fallback. Keep existing fixture structure; just replace the hard-coded URL constant.
- **Modify** `.github/workflows/ci.yml` — add `test-integration-pg` job (services postgres+redis; install; `TEST_DATABASE_URL=...` set in env; `pytest tests/integration/`).
- **Modify** `Makefile` — add `test-integration-pg` target.
- **Extend** `tests/integration/test_concurrent_metal_consumption.py` — keep the existing `skipif(sqlite)` markers (they're correct; with the env var flip to PG, the skip condition becomes False).

## Acceptance criteria

- [ ] `grep -n "TEST_DATABASE_URL\|DATABASE_URL" tests/integration/conftest.py` shows env-var lookup.
- [ ] Running `pytest tests/integration/` with unset env var uses SQLite (and silently skips PG-only tests — intentional).
- [ ] Running `TEST_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/goldsmith_test pytest tests/integration/test_concurrent_metal_consumption.py -v` shows the tests **executing** (not skipping).
- [ ] New `test-integration-pg` CI job appears in `ci.yml` and runs green on HEAD.
- [ ] Existing `test-backend` CI job unchanged — stays fast on SQLite.
- [ ] Wall-time budget: new PG job ≤ 6 min.

## Test design (TDD)

This is a test-infrastructure change. The "failing test" is running the round-trip locally:

```bash
# Before the fix
cd /Users/maxbook/Documents/Github/Anne/goldsmith_erp
TEST_DATABASE_URL=postgresql+asyncpg://... pytest tests/integration/test_concurrent_metal_consumption.py -v
# Expect: test is SKIPPED (SQLite hardcoded, env var ignored)

# After the fix
TEST_DATABASE_URL=postgresql+asyncpg://... pytest tests/integration/test_concurrent_metal_consumption.py -v
# Expect: test RUNS, and passes (or fails for real — either way, it executed)
```

For the CI job — the job itself is the test. Add actionlint validation if available.

## Implementation sketch

### `tests/integration/conftest.py`

Find the line that currently declares the SQLite URL (around line 42 per finding). Replace with:

```python
import os
TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "sqlite+aiosqlite:///:memory:",
)

# ... existing engine/session-factory construction, using TEST_DATABASE_URL
```

Keep all other fixtures unchanged.

### `.github/workflows/ci.yml`

Add a new job (adjacent to `test-backend`):

```yaml
  test-integration-pg:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_USER: user
          POSTGRES_PASSWORD: pass
          POSTGRES_DB: goldsmith_test
        ports: ['5432:5432']
        options: >-
          --health-cmd pg_isready --health-interval 10s
          --health-timeout 5s --health-retries 5
      redis:
        image: redis:7
        ports: ['6379:6379']
    env:
      TEST_DATABASE_URL: postgresql+asyncpg://user:pass@localhost:5432/goldsmith_test
      DATABASE_URL: postgresql+asyncpg://user:pass@localhost:5432/goldsmith_test
      REDIS_URL: redis://localhost:6379/0
      SECRET_KEY: test_secret_not_used_in_prod_at_least_32_chars_long_abc
      ENCRYPTION_KEY: ${{ secrets.TEST_ENCRYPTION_KEY || 'dGVzdGtleTEyMzQ1Njc4OTBhYmNkZWZnaGlqa2w=' }}
      ANONYMIZATION_SALT: testsalt1234567890abcdef
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
          cache: 'poetry'
      - run: pip install --no-cache-dir poetry
      - run: poetry install --no-interaction --no-ansi
      - name: Integration tests against Postgres
        run: poetry run pytest tests/integration/ -v
```

### `Makefile`

```makefile
test-integration-pg:
	@POSTGRES_PASSWORD=pass podman-compose up -d db redis
	@TEST_DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/goldsmith_test \
	  DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/goldsmith_test \
	  poetry run pytest tests/integration/ -v
```

## Parallel-safety

Touches `tests/integration/conftest.py`, `.github/workflows/ci.yml`, `Makefile`.
- No other Wave-2 item touches `conftest.py`.
- `ci.yml` is also touched by F2 (after F2a) and F3 in Wave 2b — sequenced AFTER F1.
- `Makefile` is not touched by any other Wave-2 item.

## Commit message

```
test(ci): honor TEST_DATABASE_URL + add test-integration-pg job

Fix item F1 — integration conftest hardcoded sqlite+aiosqlite, so the
PG service in CI was wasted (only used for `alembic upgrade head`) and
test_concurrent_metal_consumption was silently skipped. Integration
conftest now reads TEST_DATABASE_URL; new CI job runs the integration
suite against real Postgres 15. Unit tests stay on SQLite for speed.

Ref: docs/fix-plan/2026-04-23/F1-pg-test-target.md
Ref: docs/review/2026-04-23/FIX-PLAN.md#group-f

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

## Open questions for the implementing agent

- Are there other tests outside `tests/integration/` that need PG? Probably not (unit/ deliberately uses SQLite). Spot-check.
- Does any existing fixture in `tests/integration/conftest.py` assume SQLite quirks (e.g., `PRAGMA` statements)? Fix if so.
- `ENCRYPTION_KEY` in CI env: use a non-secret test key like `dGVzdGtleTEyMzQ1Njc4OTBhYmNkZWZnaGlqa2w=` (base64 of "testkey1234567890abcdefghijkl"). Not a real secret; avoids needing a GitHub secret for CI.
