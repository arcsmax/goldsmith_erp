# F2 — Alembic upgrade→downgrade→upgrade smoke test in CI

**Item:** F2 · **Severity:** P0 · **Effort:** S · **Owner:** CI
**Source:** `docs/review/2026-04-23/FIX-PLAN.md` Group F, flagged by report 06

## Context

`.github/workflows/ci.yml:98` runs `poetry run alembic upgrade head` against a Postgres 15 service, which is effectively a forward-migration smoke test. There is **no downgrade verification anywhere in CI** — a broken `downgrade()` function or an FK-drop-order bug only surfaces after merge.

Commit `263fd45` (`fix(migrations): 3 real bugs caught by smoke-test against fresh PG`) confirms that this class of bug is real and recent. An `upgrade → downgrade → upgrade` cycle in CI catches it pre-merge for ~30 s of wall time.

## Goal

On every PR, CI runs:
```
alembic upgrade head
alembic downgrade base
alembic upgrade head
```
Any SQL error at any step fails the job.

## Files

- **Modify** `.github/workflows/ci.yml` — add the downgrade+re-upgrade step right after the existing `alembic upgrade head` at line 98 (in the `test-backend` job, or a dedicated `migration-smoke` job — see below).

## Acceptance criteria

- [ ] A new CI step named `Alembic downgrade+re-upgrade smoke test` runs on PR and push.
- [ ] The step runs `alembic upgrade head && alembic downgrade base && alembic upgrade head`.
- [ ] The step runs AGAINST the Postgres service, not SQLite.
- [ ] If run on HEAD today, the step SHOULD PASS (all 6 active migrations are reversible per report 05 — migration-chain health table).
- [ ] Intentionally breaking any migration's `downgrade()` and pushing causes the step to fail.
- [ ] Wall-time: the added step should complete in under 60s on the CI runner.

## Test design (TDD)

The CI step itself is the test. To validate the step catches real regressions:

1. **Before adding the step**: run locally against a fresh PG
   ```bash
   podman-compose up -d db
   poetry run alembic upgrade head   # expect success
   poetry run alembic downgrade base  # expect success
   poetry run alembic upgrade head   # expect success
   ```
   If this passes, the baseline is healthy and the CI step will also pass.

2. **Test the step catches regressions** (temporarily): introduce a bogus `op.drop_column("nonexistent")` inside a recent migration's `downgrade()`, push to a scratch branch, confirm the step fails, revert. (Document in DECISIONS.md if you skip this step for time — the empirical check in step 1 is the minimum bar.)

## Implementation sketch

Two options for where the step lives — pick whichever matches project style:

### Option A — Inline in `test-backend` job (simpler)

Edit `.github/workflows/ci.yml` around line 98:

```yaml
      - name: Run Alembic migrations
        run: poetry run alembic upgrade head
        env:
          DATABASE_URL: postgresql+asyncpg://user:pass@localhost:5432/goldsmith_test

      - name: Alembic downgrade + re-upgrade smoke test
        run: |
          poetry run alembic downgrade base
          poetry run alembic upgrade head
        env:
          DATABASE_URL: postgresql+asyncpg://user:pass@localhost:5432/goldsmith_test
```

### Option B — Dedicated `migration-smoke` job (cleaner, recommended)

Adds a short parallel job that runs only the migration cycle against its own PG service, clean boundaries:

```yaml
  migration-smoke:
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
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    env:
      DATABASE_URL: postgresql+asyncpg://user:pass@localhost:5432/goldsmith_test
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - run: pip install --no-cache-dir poetry
      - run: poetry install --no-interaction --no-ansi
      - name: Alembic upgrade → downgrade → upgrade cycle
        run: |
          poetry run alembic upgrade head
          poetry run alembic downgrade base
          poetry run alembic upgrade head
```

**Recommend Option B** — keeps migration smoke isolated from the broader test suite runtime.

## Parallel-safety

Owns `.github/workflows/ci.yml`. No other Wave-1 item edits this file. Wave-2 items F1 and F3 also touch `ci.yml` but are sequenced AFTER F2 per TRACKER.md.

## Commit message

```
ci: add alembic upgrade→downgrade→re-upgrade smoke test

Fix item F2 — CI only ran forward migrations. A broken downgrade or
FK-drop-order bug only surfaced post-merge (see commit 263fd45 "3 real
bugs caught by smoke-test against fresh PG"). A dedicated job runs
the cycle against the Postgres service on every PR.

Ref: docs/fix-plan/2026-04-23/F2-downgrade-smoke.md
Ref: docs/review/2026-04-23/FIX-PLAN.md#group-f

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

## Open questions for the implementing agent

- Option A vs Option B: pick one. Option B (dedicated job) is recommended; if project style already loads every CI step into `test-backend`, Option A is acceptable.
- Should this step be required to pass for merge (`required` in branch protection)? Out of scope for this fix — the step being green is what matters; enforcing it is a GitHub settings change.
- If you discover during local verification that one of the downgrade paths actually fails on HEAD (contra report 05's "all reversible" claim), STOP and escalate — the fix expands into repair work on that migration, not just CI.
