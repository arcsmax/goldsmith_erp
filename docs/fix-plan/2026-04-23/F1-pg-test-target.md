# F1 — Run integration tests against Postgres (not SQLite) in CI

**Item:** F1 · **Severity:** P0 · **Effort:** M · **Owner:** CI · **Status:** 🛑 BLOCKED on F2 (shared `ci.yml`), to land in Wave 2.

## Context

`tests/conftest.py:33` + `tests/integration/conftest.py:42` hard-code `sqlite+aiosqlite://`. CI sets `DATABASE_URL=postgresql+asyncpg://...` and provisions a PG15 service — but the conftest ignores it. So the PG service in `ci.yml:64-77` is used ONLY for `alembic upgrade`. The test suite itself runs against SQLite.

Consequences (per report 06):
- `tests/integration/test_concurrent_metal_consumption.py` is `skipif(sqlite)` → silently skipped in CI.
- No PG dialect behaviour exercised (JSONB operators, partition insert, `ON DELETE RESTRICT` enforcement, real deadlocks).
- Production is Postgres 15.

## Goal

At least the `tests/integration/` suite runs against Postgres in CI. Unit tests (`tests/unit/`, `tests/`) can stay on SQLite for speed.

## Design options (pick before writing code)

- **Option A — env-var-switched conftest**: read `TEST_DATABASE_URL` from environment; fall back to SQLite. CI sets it to the PG service.
- **Option B — separate postgres-integration job**: clone the conftest, point at PG, run only `tests/integration/`.
- **Option C — split conftests**: unit conftest uses SQLite; integration conftest uses the env var (defaults to PG in CI, SQLite locally).

**Recommended:** Option C. Cleanest separation; local iteration on unit tests stays fast; integration tests can opt into PG via `make test-integration-pg`.

## Files (likely)

- **Modify** `tests/integration/conftest.py` — honor `TEST_DATABASE_URL` env var.
- **Modify** `.github/workflows/ci.yml` — add env var to the test-backend job (or a new `test-integration-pg` job).
- **Modify** `Makefile` — add `test-integration-pg` target for local use.

## Acceptance criteria

- [ ] CI has a step or job that runs `pytest tests/integration/` against Postgres.
- [ ] `tests/integration/test_concurrent_metal_consumption.py` actually executes (not silently skipped).
- [ ] Unit tests (`tests/unit/`) still use SQLite for speed.
- [ ] Test output in CI includes a line confirming PG is in use (e.g., explicit print or log).
- [ ] Local `make test` unchanged (SQLite-based, fast).

## Next step

Unblocked by F2 landing first. Then orchestrator spawns an agent with this spec to choose Option A/B/C and implement with TDD (the test IS the CI cycle).
