# Week 1 Fix Tracker — Groups A + B + F
**Source:** `docs/review/2026-04-23/FIX-PLAN.md` · **Branch:** `code-review-fixes-2026-04-23` (off main `a6a5d73`) · **Started:** 2026-04-23

## Conventions

- Each item gets a spec at `docs/fix-plan/2026-04-23/<ID>-<slug>.md`.
- Status machine: `⏳ pending` → `🧭 specced` → `🚧 in-progress` → `🔍 review` → `✅ committed` → `🚢 merged`. `🛑 blocked` is a side state with a reason.
- **TDD discipline**: every item's spec lists the failing test first. No implementation lands without a matching test or a documented exemption in `DECISIONS.md`.
- **Commits**: one commit per item (conventional-commits style). Commit message references the item ID.
- **Parallelism rules** (from CLAUDE.md): never parallelize edits to `main.py`, `db/models.py`, `types.ts`, `package.json`, or any alembic migration. The wave schedule below respects this.

## Item inventory

| ID | Title | Effort | Owner area | Status | Wave | Blocked-by | Spec |
|----|-------|--------|------------|--------|------|------------|------|
| A1 | Register `AuditLoggingMiddleware` + populate `request.state.user` | M | BE + GDPR | ✅ committed `38229c0` | 1 | — | [A1-audit-middleware.md](A1-audit-middleware.md) |
| A2 | Merge duplicate `Permission` / `require_permission` systems | M | BE + SEC | ✅ committed `17d1056` | 1 | — | [A2-permission-merge.md](A2-permission-merge.md) |
| A3 | Lock down `/users/register` | S | BE + SEC | 🛑 blocked | 2 | A2; **product decision needed** | [A3-register-endpoint.md](A3-register-endpoint.md) |
| A4 | Compose password defaults + bind DB to 127.0.0.1 (dev) | S | OPS | ✅ committed `ccf0c73` | 1 | — | [A4-compose-defaults.md](A4-compose-defaults.md) |
| A5 | Add top-level + MainLayout `ErrorBoundary` | S | FE | ✅ committed `38cd45b` | 1 | — | [A5-error-boundary.md](A5-error-boundary.md) |
| A6 | `CustomerPortalPage` raw fetch leaks cookies | S | FE + SEC | ✅ committed `0603982` | 1 | — | [A6-portal-fetch.md](A6-portal-fetch.md) |
| A7 | CSRF token on cookie-auth state-changing requests | S | FE + BE + SEC | 🛑 blocked | 2 | Backend CSRF state verification | [A7-csrf-header.md](A7-csrf-header.md) |
| B1+B2 | Bump axios (CVE-2026-25639) + react-router-dom (CVE-2026-22029 + CVE-2026-21884) | S | DEP + FE | ✅ committed `ac0864b` | 1 | — | [B1-B2-cve-bumps.md](B1-B2-cve-bumps.md) |
| F1 | Run integration tests against Postgres (not SQLite) in CI | M | CI | 🛑 blocked | 2 | Need to confirm conftest strategy | [F1-pg-test-target.md](F1-pg-test-target.md) |
| **F2a** | **Fix broken `downgrade()` in migration `20260420_h9_explicit_ondelete_restrict.py`** | **S** | **DB** | **🛑 blocked on decision** | **1.5** | **NEW — escalation from F2** | **[F2a-h9-downgrade-fix.md](F2a-h9-downgrade-fix.md)** |
| F2 | Alembic upgrade→downgrade→upgrade smoke test in CI | S | CI | 🛑 blocked | 1.5 | F2a must land first — downgrade-smoke would immediately fail CI on HEAD | [F2-downgrade-smoke.md](F2-downgrade-smoke.md) |
| F3 | Run Playwright E2E specs in CI | M | CI + FE | 🛑 blocked | 2 | F1, F2 land first (shared `ci.yml`) | [F3-playwright-ci.md](F3-playwright-ci.md) |
| F4 | Un-skip or delete 7 stale-skipped encryption/GDPR tests | S | CI + GDPR | 🛑 blocked | — | Needs C1–C4 (encryption infra) from Week 2+ | [F4-skipped-tests.md](F4-skipped-tests.md) |
| D3 | Add `@require_permission(Permission.TIME_VIEW_OWN)` to `GET /time-tracking/user/{user_id}` | S | BE + SEC | ✅ committed `a1f72f1` | 1 | — | [D3-time-tracking-permission.md](D3-time-tracking-permission.md) |

D3 is from Group A-adjacent (time_tracking.py missing `@require_permission`, P0, S effort, from report 01) — tiny, included in Wave 1 because `core.permissions` was already canonical for that file.

**Count:** 14 items in scope (after F2a escalation). Wave 1 done = 7 (A1, A2, A4, A5, A6, B1+B2, D3). Wave 1 blocked = 1 (F2 → F2a needed first). Wave 2 = A3, A7, F1, F3. Wave 1.5 (new) = F2a → F2. Deferred = F4.

## Wave 1 outcome snapshot (2026-04-23)

**7 of 8 dispatched items committed** on branch `code-review-fixes-2026-04-23`:

```
38229c0 feat(audit): register AuditLoggingMiddleware and populate request.state.user_id   [A1]
17d1056 refactor(permissions): unify Permission enum and require_permission to core.permissions   [A2]
a1f72f1 fix(time-tracking): add @require_permission to GET /user/{user_id}   [D3]
38cd45b feat(frontend): add ErrorBoundary at app + page level   [A5]
ccf0c73 chore(compose): require POSTGRES_PASSWORD and bind DB to 127.0.0.1 in dev   [A4]
ac0864b chore(deps): bump axios to 1.13.5+ and react-router-dom to 7.12+   [B1+B2]
0603982 fix(portal): stop leaking auth cookie on public /portal/lookup   [A6]
```

**Post-wave sanity checks (all green):**
- `git status --porcelain` has zero tracked-file changes (all agents committed cleanly, no leftover stages)
- Backend imports cleanly: `210 routes, 7 middlewares` (audit middleware now registered, up from 6)
- `grep -rn "class Permission" src/goldsmith_erp/` → 1 match (A2 invariant)
- `grep -rn "from goldsmith_erp.api.deps import.*Permission" src/goldsmith_erp/` → 0 matches (A2 invariant)
- No merge conflicts between the 7 parallel agents

**F2 escalation:** F2 agent ran the `upgrade → downgrade → upgrade` cycle locally against a fresh Postgres 15 **before touching `ci.yml`**. Downgrade step 1 (`20260420_h9_restrict -> 20260419_security_floor`) **failed** with:
```
psycopg2.errors.DuplicateObject: constraint "fk_customers_deleted_by_users" for relation "customers" already exists
```
This contradicts report 05's "all reversible" claim and is itself a P0 migration correctness bug. Per the spec's escalation rule ("If you discover during local verification that one of the downgrade paths actually fails on HEAD, STOP and escalate"), the agent did not commit. New item **F2a** added to fix the H9 downgrade FIRST; F2 blocked on it.

## Dependency DAG

```
                                   (product decision)
                                          │
A2 (Permission merge) ──────────► A3 (register lockdown)
       │
       └────────► D3 (time-tracking decorator, trivial follow-on)

A1 (AuditLoggingMiddleware registration)
       │
       └────────► A7 (CSRF header — depends on backend cookie/csrf infra)

A4 (compose)      independent
A5 (ErrorBoundary) independent
A6 (portal fetch)  independent
B1+B2 (CVE bumps)  independent

F2 (downgrade smoke)  ┐
                      ├── all touch .github/workflows/ci.yml
F1 (PG test target)   ├── sequence: F2 → F1 → F3
F3 (Playwright)       ┘

F4 — deferred (needs encryption infra from Group C)
```

## Wave schedule

### Wave 1 — maximum parallelism, no file conflicts (dispatched 2026-04-23)

Eight agents in one dispatch. File-ownership table below confirms no edit collision.

| Agent | Item | Primary files | Parallel-safe because |
|-------|------|---------------|------------------------|
| 1 | A1 | `src/goldsmith_erp/main.py`, `src/goldsmith_erp/middleware/audit_logging.py`, `src/goldsmith_erp/middleware/auth_required.py` | only Wave-1 item that touches `main.py` |
| 2 | A2 | `src/goldsmith_erp/api/deps.py`, `src/goldsmith_erp/core/permissions.py`, 5 router files (`customers.py`, `measurements.py`, `metal_types.py`, `metal_prices.py`, `metal_inventory.py`) | no overlap with any other Wave-1 agent |
| 3 | A4 | `docker-compose.yml`, `podman-compose.yml`, `.env.example` | isolated — no other agent touches these |
| 4 | A5 | `frontend/src/App.tsx`, `frontend/src/layouts/MainLayout.tsx`, new file `frontend/src/components/ErrorBoundary.tsx`, new test | only frontend agent in Wave 1 that edits `App.tsx` / `MainLayout` |
| 5 | A6 | `frontend/src/pages/CustomerPortalPage.tsx` | isolated to one file |
| 6 | B1+B2 | `frontend/package.json`, `frontend/yarn.lock` | only agent touching package manifest |
| 7 | F2 | `.github/workflows/ci.yml` | only Wave-1 agent touching ci.yml |
| 8 | D3 | `src/goldsmith_erp/api/routers/time_tracking.py` | single-line permission decorator add; A2's router-migration targets don't include `time_tracking.py` |

**Hard rule:** if an agent discovers mid-execution that a fix needs to touch a file already claimed by another agent, it must stop and report to the orchestrator rather than edit.

### Wave 2 (after Wave 1 reviewed + committed)

| Item | Needs first |
|------|-------------|
| A3 | Product decision on registration policy; A2 committed |
| A7 | Backend CSRF state verified (existing cookie attributes + server-side CSRF token emission) |
| F1 | Decide conftest pattern (env-var-switched vs. separate postgres fixture); F2 committed |
| F3 | F1 committed (shared workflow) |

### Deferred to Week 2+

- **F4** — skipped encryption tests should be reconsidered AFTER Group C (PII encryption) lands. Un-skipping them with no encryption plumbing would just fail the suite.

## Current status

- **Baseline commit:** `a6a5d73 refactor(scanner): remove Suspense/lazy wrapper around vendor module` (main HEAD on branch-off)
- **Branch:** `code-review-fixes-2026-04-23` — 9 commits ahead of main
- **Wave 1**: 7/8 done, F2 blocked on F2a (new) — see snapshot above
- **Next up**: decision needed from user on F2a approach (see DECISIONS.md), plus A3 product decision, plus A7 backend CSRF investigation
- **Open decisions:** see `DECISIONS.md`

## Per-item commit convention

Commit message template:
```
<type>(<scope>): <short description>

Fix item <ID> — <one-line rationale>

Ref: docs/fix-plan/2026-04-23/<spec-file>.md
Ref: docs/review/2026-04-23/FIX-PLAN.md#<anchor>

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

Example for A4:
```
chore(compose): require POSTGRES_PASSWORD and bind DB to 127.0.0.1 in dev

Fix item A4 — weak committed default `POSTGRES_PASSWORD=pass` with
0.0.0.0 bind was reported as P0 by the security review. Prod compose
already uses :? pattern; mirror it to dev.

Ref: docs/fix-plan/2026-04-23/A4-compose-defaults.md
Ref: docs/review/2026-04-23/FIX-PLAN.md#group-a
```

## What gets reviewed before commit

Every item must satisfy these before the orchestrator commits:

- [ ] Spec's **acceptance criteria** all check out (orchestrator verifies manually or via command)
- [ ] New test(s) written **before** implementation and now pass
- [ ] Pre-existing tests still pass (`make test` subset or targeted invocation)
- [ ] Changed files + net new files match the spec's "Files" section
- [ ] Commit message follows the template
