# F3 — Run Playwright E2E specs in CI

**Item:** F3 · **Severity:** P0 · **Effort:** M · **Owner:** CI + FE · **Status:** 🛑 BLOCKED on F1 landing first (shared `ci.yml`, avoid merge conflicts).

## Context

Four Playwright E2E specs exist and are committed:
- `frontend/e2e/smoke.spec.ts`
- `frontend/e2e/auth.spec.ts`
- `frontend/e2e/goldsmith-workflow.spec.ts`
- `frontend/e2e/goldsmith-full.spec.ts`

`playwright.config.ts` is correctly shaped (auto-starts Vite webServer, retries twice in CI, screenshots on failure — per report 06). **But no CI workflow runs any of them.** Users think the login / unauthenticated-redirect / happy-path workflows are E2E-tested; they are not.

## Goal

On every PR, at least `smoke.spec.ts` + `auth.spec.ts` run headless against the real backend + frontend. Wall-time ≤ 8 min.

## Files

- **Modify** `.github/workflows/ci.yml` — add `test-e2e` job (services postgres+redis; backend `alembic upgrade head`; `yarn install`; `npx playwright install --with-deps`; `yarn e2e`).

## Acceptance criteria

- [ ] CI has a `test-e2e` job that runs on push + PR.
- [ ] Job brings up backend + frontend + db + redis.
- [ ] At minimum `smoke.spec.ts` + `auth.spec.ts` run.
- [ ] Job fails if any spec fails; screenshots uploaded as artifacts.
- [ ] Total added wall time ≤ 8 min.

## Design options

- **Option A — run on every PR** (slower but catches regressions fast).
- **Option B — nightly-only + manual trigger** (faster PRs, lag on finding regressions).

**Recommended:** Option A for smoke+auth (short, fast) + Option B (nightly) for goldsmith-workflow / goldsmith-full (longer).

## Next step

Unblocked by F1 landing first (both edit `ci.yml`). Then expand into TDD plan.
