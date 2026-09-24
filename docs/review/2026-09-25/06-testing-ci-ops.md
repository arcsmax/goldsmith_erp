# Review 06 — Testing, CI, Tooling, Deployment & Operations

**Date:** 2026-09-24
**Repo:** `/Users/maxbook/Documents/Github/Anne/goldsmith_erp`, branch `main` @ `73fff19` (last push 2026-07-26)
**Reviewer scope:** testing / CI / tooling / deployment / backup / observability only. Security and GDPR
substance are covered by other agents in this pass and are only mentioned here where they surface as a
CI/ops **wiring** gap (a control that exists in code but is not scheduled, gated, or documented).

## Scope & method

Re-verified two prior review documents against the current tree by re-running commands rather than
trusting prior prose:
- `docs/review/2026-04-23/06-testing-ci.md` (static review, HEAD `1feae6d`)
- `docs/review/2026-07-26/production-readiness.md` (5-pass audit, HEAD `8e5556c`, Tiers 0-3)

Also read: `CLAUDE.md` (testing/command sections), `Makefile` (full), `.github/workflows/ci.yml` and
`bundle-size-gate.yml` (full), `.truecourse/config.json`, `.pre-commit-config.yaml`, `pyproject.toml`
(`[tool.pytest.ini_options]`, `[tool.mypy]`), `tests/conftest.py`, `tests/integration/conftest.py`,
`Containerfile`, `frontend/Containerfile` + `Containerfile.prod`, `podman-compose.prod.yml`,
`deploy/Caddyfile`, all 8 files in `deploy/systemd/`, `docs/DEPLOYMENT.md`,
`docs/technical/infrastructure/PRODUCTION_DEPLOYMENT.md`, `.env.example`, `src/goldsmith_erp/core/config.py`.

**Headline context change since the last review:** the repo is not in the state either prior document
describes. The 2026-07-26 audit found the install broken and CI red; a same-day remediation sprint
(21 commits, all dated 2026-07-26, ending in `73fff19`) fixed the Tier-0 blockers, added TLS, closed most
of Tier 1/2, and landed a green CI run across all 7 jobs. **Nothing has been pushed to `main` since.**
The repository has been dormant for exactly 2 months as of today. This review's job is to confirm that
green state still holds locally and catalog what is still open or has drifted since.

### Commands run (every one, with exit code)

```
find docs/review -maxdepth 2 -type d                                          → 0
cat -n Makefile                                                                → 0
ls .github/workflows/ ; cat .truecourse/config.json ; cat .pre-commit-config.yaml → 0
cat -n .github/workflows/ci.yml                                                → 0
cat -n .github/workflows/bundle-size-gate.yml                                  → 0
gh auth status ; gh repo view --json nameWithOwner                             → 0
gh api repos/arcsmax/goldsmith_erp/branches/main/protection                    → 0
gh run list --limit 15                                                        → 0
gh pr list --state open ; gh issue list --state open                          → 0
gh api repos/.../dependabot/alerts --paginate -q '...severity' | sort | uniq -c → 0
gh run view 30218721938  (job-level breakdown of last green run)              → 0
git log --oneline -20 --date=short --format='%h %ad %s' main                  → 0
git worktree list                                                             → 0
find . test_*.py inventory (1st pass, included .claude/worktrees/*)           → 0  (767 files — discarded, see below)
find . test_*.py inventory excluding node_modules + .claude/worktrees         → 0  (113 files)
grep -rc "def test_\|async def test_" (same exclusion)                        → 0  (1695 functions)
find frontend/src -name '*.test.ts*'                                         → 0  (48 files)
grep -rc "^\s*(it|test)(" frontend/src --include=*.test.tsx --include=*.test.ts → 0  (479 calls)
find frontend/e2e -type f                                                     → 0  (6 specs)
poetry env info --path (root and src/ — same venv)                            → 0
cat .env | grep names-only ; grep model_config config.py                      → 0
poetry run python -m pytest tests/ -q --cov=... (1st attempt, empty venv)     → "No module named pytest" (venv had only pip)
poetry run pip list                                                           → 0  (confirmed venv was empty)
timeout 300 poetry install                                                    → 0  (fresh install, ~110 packages, no errors)
timeout 600 poetry run python -m pytest tests/ -q --tb=short --cov=goldsmith_erp --cov-report=term-missing:skip-covered → 0
  RESULT: 1805 passed, 6 skipped, 1 xfailed, 63 warnings in 285.88s; TOTAL coverage 68% (16781 stmts, 5369 miss)
cd src && poetry run mypy goldsmith_erp/ --ignore-missing-imports                → 0  "Success: no issues found in 159 source files"
cd src && poetry run black --check goldsmith_erp/                               → 0  "160 files would be left unchanged"
cd src && poetry run isort --check-only goldsmith_erp/                          → 0
cd src && poetry run bandit -r goldsmith_erp/ -c ../pyproject.toml              → 0  0 high/med/low issues
cd frontend && yarn vitest run --coverage                                       → 1  "MISSING DEPENDENCY '@vitest/coverage-v8'"
cd frontend && yarn vitest run                                                  → 0  "Test Files 48 passed (48), Tests 485 passed (485)"
cd frontend && npx tsc --noEmit                                                → 0  (no output, clean)
ls frontend/.eslintrc* frontend/eslint.config.*                                → 1  (no such file — confirms no ESLint config)
grep pylint ci.yml ; grep ruff ci.yml ; grep pip-audit|npm audit ci.yml       → 0  (all empty — confirms none wired)
grep cache: ci.yml bundle-size-gate.yml                                       → 0  (empty — confirms no actions cache)
grep test-local|lint-local Makefile                                          → 0  (empty — confirms still absent)
find tests -name __init__.py                                                  → 0  (present at all 4 levels — Tier-3 fix confirmed)
grep skipif/pytest.skip test_concurrent_metal_consumption.py                  → 0  (3 skips confirmed under SQLite)
grep xfail tests/ -r                                                          → 0  (1 hit: test_customer_service.py:268)
cat Containerfile, frontend/Containerfile, frontend/Containerfile.prod        → 0
cat podman-compose.prod.yml                                                   → 0
cat deploy/systemd/*.{service,timer} (8 files)                                → 0
grep systemd|timer Makefile setup.sh                                          → 0  (no hits — confirms no auto-install)
grep BACKEND_CORS_ORIGINS|LOCAL_IP|CORS_ORIGINS_JSON setup.sh                 → 0  (fix confirmed present)
grep -oE config fields vs .env.example (ad hoc diff)                          → 0
cat .env.example (full)                                                       → 0
grep -rln setup.sh|podman-compose.prod README.md docs/technical/infrastructure/*.md → 0
du -sh docs/architecture/likec4/node_modules ; git check-ignore -v            → 0  (gitignored, not tracked — non-issue)
sed -n config.py SECRET_KEY validator                                        → 0
grep -rli rollback docs/ Makefile scripts/                                    → 0  (docs/DEPLOYMENT.md only)
ls alembic/versions | wc -l (21) ; ls alembic_backup (1: env.py)             → 0
cd src && poetry show --outdated                                              → 0  (long list; cryptography, alembic, bandit, boto3 all behind)
cd frontend && yarn outdated                                                  → 0  (Usage Error — yarn 4 Berry has no built-in `outdated`)
grep -rc Mock|monkeypatch|patch tests/ (446) ; await .commit() (478) ; assert (3817) → 0
find frontend/src/pages -name '*.test.*'                                     → 0  (6 page-level tests now exist)
sed -n test_websocket_auth.py header ; grep redis conftest.py x2             → 0
find .github -iname '*nightly*' ; grep schedule: .github/workflows/*.yml     → 0  (no nightly workflow exists anywhere)
gh api repos/.../issues/31 -q '.state,.title' ; issues/8                     → 0  (both closed — Tier-3 items resolved)
find src/goldsmith_erp -name '*.py' (160) ; frontend/src *.ts/.tsx (160)     → 0
for svc in accounting_export_service calendar_service comparison_service label_service system_monitor: find tests -iname *svc* → 0 (all 5: NONE)
grep gzip/verify backup.sh ; gunzip restore.sh                                → 0  (both present/correct)
grep backup|cron|timer docs/technical/infrastructure/PRODUCTION_DEPLOYMENT.md → 0  (documents manual cron/timer setup + checklist)
```

---

## A. Status of prior findings

| Prior ID / topic | 2026-04-23 / 2026-07-26 status | Current status (verified 2026-09-24) |
|---|---|---|
| P0 — tests hard-coded to SQLite, PG never exercised | Open (Apr) | **Fixed.** `test-integration-pg` CI job runs `tests/integration/` against real PG 15; passed in 5m51s in the last run. |
| P0 — no Alembic downgrade smoke test | Open (Apr) | **Fixed.** `migration-smoke` job runs upgrade→downgrade→upgrade on fresh PG; passed in 1m4s. |
| P0 — concurrent-consumption tests silently skipped | Open (Apr) | **Mitigated, not eliminated.** Still `skipif` under SQLite (confirmed: 3 skips in local run) but now genuinely exercised by `test-integration-pg` in CI. Local `poetry run pytest` alone still silently skips them — a dev relying on local runs only will never see this test execute. |
| P0 — Playwright E2E never runs in CI | Open (Apr) | **Partially fixed.** `test-e2e` job now runs `smoke.spec.ts` + `auth.spec.ts` on every PR. **`goldsmith-workflow.spec.ts` and `goldsmith-full.spec.ts` (the two specs covering the actual domain flows) still never run anywhere** — the "deferred to nightly" comment in `ci.yml` is aspirational; no nightly workflow file exists. Two newer specs, `consultation-wizard.spec.ts` and `estimator-quote-flow.spec.ts`, are also unwired (open issue #18). |
| P0 — encryption tests permanently skipped | Open (Apr) | **Fixed** — not present in the current skip list; 1805/1812 collected tests pass with only 6 skips (the PG-only concurrency tests) and the documented xfail. |
| Tier 0.1 — `.env.production` CORS crashes boot | BLOCKER (Jul) | **Fixed.** `setup.sh` now builds `CORS_ORIGINS_JSON` via `build_cors_json()` and includes `LOCAL_IP`. |
| Tier 0.2 — prod frontend serves Vite dev server | BLOCKER (Jul) | **Fixed.** `frontend/Containerfile.prod` is a real multi-stage build → non-root nginx; `podman-compose.prod.yml` points at it explicitly. |
| Tier 0.3 — frontend↔backend proxy wired to nothing | HIGH (Jul) | **Fixed** — nginx in `Containerfile.prod` proxies `/api`, `/ws`, `/uploads`; client uses a relative baseURL. |
| Tier 0.4 — CORS rejects workshop LAN devices | HIGH (Jul) | **Fixed**, same `setup.sh` change as 0.1. |
| Tier 1.1 — no TLS anywhere | BLOCKER (Jul) | **Fixed.** `deploy/Caddyfile` + a `caddy` service in `podman-compose.prod.yml` terminate TLS with an internal on-demand CA; `COOKIE_SECURE` hard-fails boot when `DEBUG=false`. Not yet verified live on the actual workshop box (no device-trust step has been exercised) — templates/config only. |
| Tier 1.2 — GDPR FK fix unmerged | BLOCKER (Jul) | Presumed merged — `test-integration-pg` is green, which was the symptom. Not independently re-derived from the model layer in this pass (owned by the GDPR/compliance review). |
| Tier 1.3 — GDPR hard-delete never scheduled | BLOCKER (Jul) | **Half-fixed.** `deploy/systemd/goldsmith-gdpr-cleanup.{service,timer}` + an OnFailure alert unit now exist and are well-documented. **But nothing installs them** — no Makefile target, no `setup.sh` step. Installation is 100% manual (`cp` + `systemctl --user enable`), and `PRODUCTION_DEPLOYMENT.md` lists it as a checklist item, not an automated step. |
| Tier 1.4 — no employee erasure path | BLOCKER (Jul) | Not re-verified here (compliance-review territory); commit `feat(users): ADMIN-only POST /users/{id}/gdpr-erase` is on `main`. |
| Tier 1.5 — VIEWER can read scrap-gold financials | HIGH (Jul) | Not re-verified here (permissions/compliance territory). |
| Tier 1.6 — no clean prod seed path | HIGH (Jul) | **Fixed.** `db/reference_seed.py` + `SEED_REFERENCE_DATA` env var wired into the prod compose boot command (idempotent, no demo data). |
| Tier 1.7 — Dependabot backlog | HIGH (Jul): 1 critical + 34 high + 29 medium + 7 low | **Still open, roughly similar shape**: 1 critical + 20 high + 14 medium (see OPS-06). Net improvement in high/medium count but the critical alert persists and 2 months have passed with zero commits to address it. |
| Tier 1.8 — CI red / no branch protection / unpushed commits | BLOCKER (Jul) | **Fixed.** Branch protection is live on `main` (7 required contexts: `test-backend`, `test-frontend`, `test-integration-pg`, `test-e2e`, `migration-smoke`, `lint-frontend`, `lint`). Last run on `main` is green across all 7 jobs. `enforce_admins` is **off**, so the repo owner can still merge around a red required check — acceptable for a solo maintainer but worth knowing. |
| Tier 2.1-2.15 | Mostly open (Jul) | Several fixed same-day: token revocation (2.1), financial-read audit (2.2), retention sweep job (2.3, ships dry-run — see OPS-07), backup/restore gzip mismatch (2.4, fixed), backup-vs-erasure policy documented (2.5), health watchdog (2.6, see OPS-07), CORS wildcard validator (2.9), camera permissions-policy (2.8), `.env.example` regenerated (2.13), deploy docs rewritten (2.14). Not independently re-verified: 2.7 (docs/redoc gating), 2.10 (rate-limit bucketing), 2.11 (export redaction), 2.12 (plaintext financial columns), 2.15 (Verzeichnis refresh) — these are permissions/compliance-review territory, not CI/ops wiring. |
| Tier 3 — mypy 1,505 errors, unpassable gate | Open (Jul) | **Restructured, not eliminated.** A per-module baseline ledger (`pyproject.toml` `[[tool.mypy.overrides]]`, generated by `scripts/gen_mypy_baseline.py`) suppresses 1,532 errors across 96 modules. `mypy --ignore-missing-imports` now exits 0 in CI and locally. This is an honest debt ledger (new code in a baselined module still fails on new error codes) but it means "lint passes" ≠ "these 96 modules are type-safe" — see OPS-03. |
| Tier 3 — missing `tests/__init__.py` | Open (Jul) | **Fixed** — present at `tests/`, `tests/unit/`, `tests/integration/`, `tests/factories/`. |
| Tier 3 — untracked WIP test/tsc failures | Open (Jul) | **Fixed** — full local run is 0 failures, `tsc --noEmit` is clean. |
| Tier 3 — no frontend ESLint | Open (Jul) | **Still open.** No `.eslintrc*` / `eslint.config.*` anywhere in `frontend/`. Tracked as issue #33 (still open). |
| Tier 3 — flaky `CustomerStep.test.tsx` (#31) | Open (Jul) | **Fixed and closed** (verified via `gh api issues/31` → `state: closed`). |
| Tier 3 — stale e2e for removed /register (#8) | Open (Jul) | **Fixed and closed** (verified via `gh api issues/8` → `state: closed`). |

---

## B. Metrics table

| Metric | Value | Source |
|---|---|---|
| Backend test files (excl. `.claude/worktrees`) | 113 | `find` |
| Backend test functions (grep `def test_`) | 1,695 | `grep -c` |
| Backend tests actually collected/run | 1,812 (1,805 passed + 6 skipped + 1 xfailed) | live pytest run |
| Backend suite wall time | 285.9 s (4:46) | live pytest run |
| Backend suite exit code | 0 | — |
| Backend line coverage | **68%** (16,781 stmts, 5,369 missed) | `--cov-report=term-missing` |
| CI backend coverage floor | `--cov-fail-under=50` | `ci.yml:113` |
| Frontend test files | 48 | `find` |
| Frontend `it`/`test` calls (grep) | 479 | `grep -c` |
| Frontend tests actually run | 485 passed / 485 (48/48 files) | live vitest run |
| Frontend suite wall time | 4.84 s | live vitest run |
| Frontend suite exit code | 0 | — |
| Frontend coverage | **Not measurable** — `@vitest/coverage-v8` is not an installed dependency; `yarn vitest run --coverage` exits 1 | live run |
| E2E spec files | 6 | `find frontend/e2e` |
| E2E specs wired into any CI workflow | 2 of 6 (`smoke.spec.ts`, `auth.spec.ts`) | `ci.yml` `test-e2e` job |
| mypy (CI invocation) | 0 errors under 96-module baseline suppressing 1,532 errors | live run, exit 0 |
| black --check | clean, 160 files | live run, exit 0 |
| isort --check-only | clean | live run, exit 0 |
| bandit -r | 0 high/medium/low | live run, exit 0 |
| tsc --noEmit | clean | live run, exit 0 |
| ESLint config present | No | `ls` |
| Last 15 CI runs on `main` | All from 2026-07-26; final run green across all 7 jobs; preceding 14 runs same-day iterative fixes (red→green), not flakiness | `gh run list` |
| Branch protection on `main` | Enabled, 7 required contexts, `enforce_admins: false` | `gh api .../protection` |
| Open Dependabot alerts | 1 critical, 20 high, 14 medium | `gh api .../dependabot/alerts` |
| Open GitHub issues | 12 (none P0-blocking; mostly V1.1-V1.3 follow-ups) | `gh issue list` |
| Open PRs | 0 | `gh pr list` |
| Alembic migration files | 21 (`alembic/versions/`) | `ls` |
| Git worktrees under `.claude/worktrees/` | 7, all stale (branches already merged to `main` or dated April/July) | `git worktree list` |
| Days since last commit to `main` | ~60 (2026-07-26 → 2026-09-24) | `git log` |

---

## C. Findings

**OPS-01 — SEVERITY: MEDIUM — Two of six E2E specs, and the two that matter most, never run anywhere in CI**
Evidence: `.github/workflows/ci.yml:256-264` comment says `goldsmith-workflow.spec.ts` and
`goldsmith-full.spec.ts` are "deferred to a nightly workflow" to keep PR wall-time down; `find .github
-iname '*nightly*'` and `grep schedule: .github/workflows/*.yml` both return nothing. No such workflow
was ever created. `consultation-wizard.spec.ts` and `estimator-quote-flow.spec.ts` (added later, covering
V1.1/V1.3 features) are likewise unwired — tracked but unaddressed as issue #18.
Impact: the only E2E coverage that actually runs on every PR is unauthenticated routing + login-failure
paths. The flows CLAUDE.md calls "critical" — create order, time tracking, quote accept, scanner,
customer portal — have Playwright specs written for them that **never execute** in CI. A regression in
any of these ships silently.
Fix: either add a `schedule:` trigger (e.g. nightly cron) running the two heavy specs + the two newer
ones against a fresh PG+Redis stack, or fold them into the existing `test-e2e` job if wall-time allows
(it's currently ~2 min for 2 specs; 4 more specs is unlikely to blow an 8-minute budget).
Effort: S. Confidence: high.

**OPS-02 — SEVERITY: MEDIUM — Frontend coverage tooling is not installed; `vitest.config.ts` coverage
config is dead**
Evidence: `frontend/vitest.config.ts:15-16` configures `coverage: { provider: 'v8', ... }`; `yarn vitest
run --coverage` fails with `MISSING DEPENDENCY '@vitest/coverage-v8'` (exit 1); the package is absent from
`package.json`/`yarn.lock` entirely (not just unmounted). CI's `test-frontend` job runs `yarn test --run`
with no `--coverage` flag, so this has never worked, in CI or locally, since the config was added (this
same gap was flagged in the 2026-04-23 review and has not moved).
Impact: no visibility into frontend coverage at all — not even the page-level tests recently added
(`ConsultationsPage.test.tsx`, `QuotesPage.editor.test.tsx`, etc.) can be measured for completeness. There
is no frontend coverage floor comparable to the backend's `--cov-fail-under=50`.
Fix: `yarn add -D @vitest/coverage-v8`, wire `yarn test:coverage --run` into `test-frontend`, add a
`coverage.thresholds` block.
Effort: S. Confidence: high.

**OPS-03 — SEVERITY: MEDIUM — mypy "passing" is a 1,532-error baseline suppression, not a clean bill of
health, and the ledger has no expiry/shrink pressure**
Evidence: `pyproject.toml:74-`… 96 `[[tool.mypy.overrides]]` blocks generated by
`scripts/gen_mypy_baseline.py`, each disabling specific error codes for one module ("96 modules, 1532
suppressed errors as of last run"). `poetry run mypy goldsmith_erp/ --ignore-missing-imports` exits 0
locally and in CI's `lint` job (now a required branch-protection context).
Impact: `lint` is green, and is required for merge, but 96 modules are silently exempted from
`strict = true` for the specific codes they already violate. A new violation of a *different* error code
in a baselined module still fails CI (good), but there is no tracked burndown target/deadline, and no CI
step warns when the suppressed-error count grows (e.g., if someone edits an override block to add more
codes). The ledger can only get bigger by hand-edit, which nobody is prevented from doing casually.
Fix: add a CI check (or a pre-commit hook) that fails if a PR *widens* any override block's
`disable_error_code` list without also reducing another block's count elsewhere; track the running total
in `docs/technical/MYPY_BURNDOWN.md` (referenced in the pyproject comment — verify it exists and is
current).
Effort: M. Confidence: medium (the mechanism is sound engineering; the risk is process discipline, which
is unverifiable from static inspection alone).

**OPS-04 — SEVERITY: LOW/MEDIUM — No CI caching anywhere; every job reinstalls the full dependency tree**
Evidence: `grep cache: .github/workflows/*.yml` returns nothing. `actions/setup-python@v5` and
`actions/setup-node@v4` are used 8 times combined across `ci.yml` and `bundle-size-gate.yml`, none with a
`cache:` parameter. `poetry install` runs fresh in `lint`, `test-backend`, `test-integration-pg`,
`migration-smoke`, and `test-e2e` (5 times per CI run); `yarn install --frozen-lockfile` runs fresh in
`lint-frontend`, `test-frontend`, `test-e2e`, and `bundle-size-gate.yml` (4 times). This was flagged in
the April review and is unchanged.
Impact: CI wall time and GitHub Actions minutes are needlessly high — this compounds every single push
given `on: [push: main, pull_request: main]` triggers on both events. Not correctness-affecting, purely
cost/latency.
Fix: `actions/setup-python@v5` → `cache: 'poetry'`; `actions/setup-node@v4` → `cache: 'yarn'`.
Effort: S. Confidence: high.

**OPS-05 — SEVERITY: MEDIUM — No local-mode `make test`/`make lint`; CLAUDE.md's "Option 2: backend
local" path is undocumented in the Makefile**
Evidence: `Makefile:131-133` (`test:`) and `:154-159` (`lint:`) both invoke `$(COMPOSE) exec backend ...`,
requiring a running podman-compose stack. `grep -n "test-local\|lint-local" Makefile` returns nothing.
CLAUDE.md documents running the backend locally via `poetry run uvicorn ...` (Option 2) as a supported
workflow, but there is no matching `make test`/`make lint` variant for that mode — a developer following
CLAUDE.md's own "faster backend iteration" path has to hand-type the full pytest/mypy/black invocations
(which is exactly what this review did to get the numbers above). This was flagged in the April review
and is unchanged.
Fix: add `test-local: poetry run python -m pytest tests/ -q --cov=goldsmith_erp --cov-fail-under=50` and
`lint-local` mirroring the CI job commands, run from repo root (matching how CI does it, not `cd src`).
Effort: S. Confidence: high.

**OPS-06 — SEVERITY: HIGH — 35 open Dependabot alerts (1 critical, 20 high, 14 medium), untouched for 2
months of dormancy**
Evidence: `gh api repos/arcsmax/goldsmith_erp/dependabot/alerts` → 1 critical / 20 high / 14 medium open.
`poetry show --outdated` independently confirms drift: `cryptography 48.0.1 → 50.0.1` (2 majors behind,
security-relevant package), `alembic 1.17.1 → 1.20.0`, `bandit 1.8.6 → 1.9.4`, `boto3`/`botocore` several
minors behind, `bcrypt 4.3.0 → 5.0.0`, dozens more. `yarn outdated` isn't usable as-is under Yarn 4 Berry
(`Usage Error: Couldn't find a script named "outdated"` — needs a plugin or `yarn npm outdated` /
third-party tool), so frontend drift could not be independently quantified in this pass beyond the
Dependabot alert count, which does cover both ecosystems.
Impact: this is the single largest unaddressed item carried over from the July review (was 1+34+29+7,
now 1+20+14 — net improvement, so *some* bumping happened, but the critical alert and 20 high alerts
persist through 2 months of zero commits). No CI gate would have caught new ones landing, either — see
OPS-11.
Fix: dedicated dependency-bump PR, prioritizing the critical alert and `cryptography` first; re-run full
suite + bandit after.
Effort: M. Confidence: high.

**OPS-07 — SEVERITY: MEDIUM — Compliance-critical systemd timers exist and are well-designed, but nothing
installs them, and one ships intentionally inert**
Evidence: `deploy/systemd/` has 8 files — `goldsmith-gdpr-cleanup.{service,timer}` +
`-alert.service`, `goldsmith-retention-sweep.{service,timer}` + `-alert.service`, and
`goldsmith-health-watchdog.{service,timer}` — each with thorough header docs and OnFailure alert wiring.
`grep -n "systemd\|timer" Makefile setup.sh` returns **zero hits**: there is no `make install-timers` (or
equivalent) and `setup.sh` never copies or enables any of them. `docs/technical/infrastructure/
PRODUCTION_DEPLOYMENT.md:172-191` explicitly tells the operator "no backup timer ships out of the box,
set one up yourself" and gives manual `systemctl --user enable` instructions for the GDPR timer, ending in
a checklist item ("Backup-Zeitplan aktiv... Restore getestet", "DSGVO-Löschtimer installiert") rather than
an automated step. Separately, `goldsmith-retention-sweep.service` ships with `RETENTION_EXECUTE`
commented out by design — dry-run only until an operator manually uncomments it after sign-off.
Impact: for a single-workshop deployment run by a non-technical operator (per CLAUDE.md's own
"Deployment context"), every compliance-critical schedule — backups, GDPR Art. 17 erasure, retention
sweep, and the external health watchdog — depends on a manual `systemctl --user enable --now` sequence
that nothing in the codebase verifies was ever run. There is no `systemctl --user list-timers` check
wired into `make prod-status` or any health endpoint. If the operator skips step 6/7 of the deployment
doc, the system silently runs with no backups and no GDPR erasure, indefinitely, with no alert (the
health watchdog itself is one of the un-installed timers).
Fix: (a) add a `make install-timers` target that copies all `deploy/systemd/*` into
`~/.config/systemd/user/`, does the `daemon-reload`, and enables all three timers in one step; (b) add a
`systemctl --user list-timers 'goldsmith-*'` check to `make prod-status` so an operator (or a future
health-check script) can see at a glance if any expected timer is missing; (c) treat the
`RETENTION_EXECUTE` dry-run flag as a distinct, explicitly-tracked follow-up rather than assuming
Tier 2.3 is "done" once the timer exists.
Effort: S (installer target) / already-flagged-decision (dry-run activation). Confidence: high.

**OPS-08 — SEVERITY: LOW — `docs/DEPLOYMENT.md` is badly stale and could mislead an operator away from
the real production path**
Evidence: `docs/DEPLOYMENT.md` header says "Current Version: 1.0.0 (Phase 1.6 - GDPR Compliance
Complete)" and its migration-rollback section references migration names `001_initial_schema` /
`002_gdpr_compliance` that do not exist in `alembic/versions/` (real files are date-prefixed:
`20260401_v1_initial_schema.py` ... `20260705_v13t5_qli_est_meta.py`, 21 files total). This is a leftover
from a much earlier project phase, sitting at `docs/DEPLOYMENT.md` (top-level, easy to find) alongside
the current, accurate `docs/technical/infrastructure/PRODUCTION_DEPLOYMENT.md`.
Impact: it is the only doc in the repo with a "Rollback" section at all (Alembic downgrade commands) —
the current production doc has none. An operator who finds this doc first (it's shorter and at a more
prominent path) would follow instructions for a schema that no longer exists.
Fix: archive/delete `docs/DEPLOYMENT.md` (or add a banner pointing to the current doc), and port its
Alembic-rollback commands (they're mechanically still correct, `alembic downgrade -1` etc., only the
example migration names are wrong) into `PRODUCTION_DEPLOYMENT.md`, which currently has zero mentions of
"rollback" beyond DB migrations — no documented procedure for rolling back a bad **application** deploy
(e.g., `make update` pulled a broken image).
Effort: S. Confidence: high.

**OPS-09 — SEVERITY: LOW — Redis pub/sub publish→delivery path is still fully mocked; no test proves the
real-time-update contract end-to-end**
Evidence: `tests/integration/test_websocket_auth.py:15` docstring: "subscribe_and_forward is patched to a
no-op coroutine so tests do not require a running Redis instance." `tests/conftest.py:108-143`
(`mock_publish_event`) patches `publish_event` to a no-op for **every** unit test. A `fake_redis` fixture
now exists (`tests/conftest.py:205`, hand-rolled in-memory fake, since `fakeredis` is not a project
dependency) but it is used for `token_revocation` testing, not for the WS broadcast path. This is the same
gap flagged in the April review (finding P1 #7) and it has not moved.
Impact: CLAUDE.md's own "Real-time Updates" architecture section describes `publish_event` → Redis →
`WebSocket Manager` → connected clients as the core contract for order/timer updates. Nothing in the test
suite exercises that whole chain; a break in the actual Redis subscribe/forward wiring (as opposed to the
auth handshake, which *is* tested) would ship with a fully green suite.
Fix: one integration test using the existing `fake_redis`-style in-memory fake (or a real Redis service,
which CI already provisions for `test-backend`/`test-integration-pg`) that publishes an event and asserts
a connected WS client receives the forwarded JSON payload.
Effort: M. Confidence: high.

**OPS-10 — SEVERITY: LOW — A documented "passes on PostgreSQL" test claim is never actually checked**
Evidence: `tests/unit/test_customer_service.py:267-270` — `@pytest.mark.xfail(reason="... not supported by
SQLite ... Passes on PostgreSQL.")` on `test_filter_by_tag`. This test lives in `tests/unit/`, which the
`test-integration-pg` CI job never runs (it only runs `tests/integration/`). The claim "passes on
PostgreSQL" is therefore asserted in a code comment but never verified by any CI job, ever.
Impact: low individually (one test), but it's a pattern worth naming: PG-specific behavior tests that
live under `tests/unit/` are invisible to the one CI job that actually has a PG backend.
Fix: either move `test_filter_by_tag` to `tests/integration/` (where it would run for real against PG and
the `xfail` could be dropped once confirmed), or add `strict=True` to the `xfail` and a comment pointing
at whichever job is supposed to prove the claim.
Effort: S. Confidence: high.

**OPS-11 — SEVERITY: LOW — No dependency-vulnerability scanning in CI despite the tooling being a declared
dependency**
Evidence: `pip-audit` is installed as part of `poetry install` (confirmed in this run's install log:
"Installing pip-audit (2.10.0)"), and is a Poetry dev-group dependency. `grep -n "pip-audit\|npm audit"
.github/workflows/ci.yml` returns nothing — it is never invoked anywhere in CI. There is likewise no
`yarn npm audit` step for the frontend. This exact gap was flagged in the April review and is unchanged.
Impact: the 35 open Dependabot alerts (OPS-06) are caught by GitHub's out-of-band scanning only; nothing
in the PR pipeline itself would flag a newly-introduced vulnerable dependency at merge time.
Fix: add a `security-audit` job (non-blocking/advisory initially, given the current backlog) running
`poetry run pip-audit` and `yarn npm audit --severity high`.
Effort: S. Confidence: high.

**OPS-12 — SEVERITY: LOW — No `ruff` step in CI despite being the fastest, already-adopted linter in
pre-commit**
Evidence: `.pre-commit-config.yaml:26-30` runs `ruff --fix` on every commit (when hooks aren't bypassed);
`grep -n ruff .github/workflows/ci.yml` returns nothing. `pylint` is similarly declared as a dependency and
run via `make lint` but never invoked in CI (`grep pylint ci.yml` — no hits), making it dead CI tooling
in the same way. Both gaps were flagged in April and are unchanged.
Impact: a contributor who bypasses (or never installs) pre-commit hooks gets zero ruff/pylint enforcement
from CI, since `black`/`isort`/`bandit`/`mypy` are the only static-analysis steps actually wired into
`lint`.
Fix: add a `ruff check` step next to the existing black/isort/bandit steps in the `lint` job; either wire
`pylint` in too or drop it from `Makefile`/`pyproject.toml` as dead tooling (matches the April
recommendation, still unresolved either way).
Effort: S. Confidence: high.

**OPS-13 — SEVERITY: LOW — Frontend has no ESLint config; issue #33 open since 2026-07-03, unaddressed
through 2 months of dormancy**
Evidence: `ls frontend/.eslintrc* frontend/eslint.config.*` → no matches. `lint-frontend` in `ci.yml` runs
only `npx tsc --noEmit`. GitHub issue #33 ("Frontend has no ESLint config — react-hooks/jsx-a11y rules
unenforced") is open and unassigned.
Impact: unchanged from the April review — `react-hooks` correctness rules and `jsx-a11y` accessibility
rules are enforced nowhere, not in CI and not in pre-commit (pre-commit is backend-only:
`.pre-commit-config.yaml` has zero JS/TS hooks).
Fix: add `eslint.config.js` (flat config) with `@typescript-eslint`, `eslint-plugin-react-hooks`, and
`eslint-plugin-jsx-a11y`; a `lint` script in `package.json`; wire into `ci.yml`'s `lint-frontend` job.
Effort: M. Confidence: high.

**OPS-14 — SEVERITY: LOW — Dev/git hygiene: 7 stale worktrees under `.claude/worktrees/`, one stray
`alembic_backup/` directory**
Evidence: `git worktree list` shows 7 worktrees under `.claude/worktrees/` (`agent-a40026cc92b9537da`,
`agent-a4d1c2a8558ad6b68`, `agent-a644bd819efe7cdfe`, `agent-ae528d0baea031fbc`,
`agent-ae537fb5221c90457`, `agent-af9d1004`, `v13-p3-wire-order`), checked out at commits `b8d6d44`,
`00e1f80`, `5e1307d`, `4cb99cd`, `591b132`, `17d8f94`, `8de0736` respectively. Cross-referencing against
`git log --oneline`, the commit subjects for several of these branches (`chore/mypy-baseline-gate`,
`feat/token-revocation`, `feat/retention-sweep-alerting`, `feat/financial-read-audit`,
`docs/gdpr-export-policy-batch`) match commits already present on `main` from the 2026-07-26 sprint —
these worktrees are leftover from parallel-agent implementation and were never cleaned up after merge.
Separately, `alembic_backup/` at the repo root contains a single stray `env.py` file — unclear purpose,
not referenced by any Makefile target, alembic config, or doc found in this pass.
Impact: disk usage and directory clutter only; no functional risk. Worth a `git worktree remove` pass and
a decision on `alembic_backup/` (delete, or document why it's kept).
Fix: `git worktree remove` each stale entry (after confirming no uncommitted work); `rm -rf
alembic_backup/` or move its content into a documented location.
Effort: S. Confidence: medium (did not inspect each worktree's working-tree diff for uncommitted changes
before recommending removal — that check should precede any actual `git worktree remove`).

**OPS-15 — SEVERITY: LOW — `AUTH_REVOCATION_FAIL_CLOSED` (a real security/availability toggle) is
undocumented in `.env.example`**
Evidence: `src/goldsmith_erp/core/config.py:48` — `AUTH_REVOCATION_FAIL_CLOSED: bool = False`, with a
comment describing the fail-open-vs-fail-closed tradeoff for the token-revocation check when Redis is
unavailable. `.env.example` (read in full) has no mention of this variable anywhere, commented or
otherwise — unlike every other security-relevant knob (`ENCRYPTION_KEY`, `COOKIE_SECURE`,
`ANONYMIZATION_SALT`, CORS), which all have a documented block. This is the one remaining gap after the
otherwise-thorough `.env.example` regeneration that closed Tier 2.13.
Impact: minor — the default (`False`, fail-open) is probably the right call for a single-workshop
deployment (availability over strict revocation), but an operator has no way to discover or reason about
this toggle from `.env.example` the way they can for every other security setting.
Fix: add a short documented block for `AUTH_REVOCATION_FAIL_CLOSED` mirroring the style of the other
security-toggle sections.
Effort: S. Confidence: high.

---

## D. Test-quality assessment

**Overall shape (backend):** 113 files, 1,812 collected tests, 3,817 `assert` statements (~2.1/test — same
healthy ratio as the April review), 478 `await *.commit()` calls (tests exercise real persistence through
the ORM, not just mocks), 446 `Mock`/`monkeypatch`/`patch` occurrences (targeted, not blanket). This reads
as behavioral testing, not implementation-detail testing — sampled files
(`test_websocket_auth.py`, `test_customer_service.py`, `test_concurrent_metal_consumption.py`) assert on
HTTP status codes, close codes, and computed business values, not on internal call counts.

**DB strategy:** unit tests (`tests/conftest.py`) and the PG integration job (`tests/integration/
conftest.py`) both use the identical isolation pattern — per-test `DELETE FROM` across every table in
reverse dependency order, run in a second session after the primary session rolls back. This is the same
approach flagged as a perf concern in the April review (P1, `tests/conftest.py:82,87-89`); it is still
present, unchanged, now also running against real Postgres in `test-integration-pg` (5m51s wall time for
that job in the last CI run — tolerable at current scale, but it is the kind of thing that degrades
non-linearly as the schema grows, since a full-table-wipe pays a query per table per test regardless of
how much data that test actually touched).

**Redis/SMTP mocking:** Redis publish is uniformly no-op'd (see OPS-09); SMTP was not directly inspected
in this pass but `email_service.py` sits at 63% coverage with the missing lines concentrated in the actual
send path (`182-205`, `304-305`, `349-361`), consistent with SMTP being mocked/skipped rather than
exercised.

**Factories:** `tests/factories/` still has only `order_factory.py` and `user_factory.py` (unchanged from
April) despite `factory-boy` being a declared dependency and dozens of new entities (consultations,
quotes, estimates, hallmarks, repairs, measurements) added since. Most new tests build models by hand.

**xfail/skip hygiene:** exactly one `xfail` in the whole suite (`test_customer_service.py:268`, well-
documented, see OPS-10) and 6 `skip`s (all 3 skip *sites* in `test_concurrent_metal_consumption.py`, hit
once each under SQLite = matches the "6 skipped" summary line). This is a dramatic improvement over the
April review's finding of 7 permanently-skipped encryption/GDPR tests being counted as green — none of
that pattern remains.

**Frontend:** 48 files / 485 tests, including genuine page-level tests now (`ConsultationsPage.test.tsx`,
`QuotesPage.editor.test.tsx`, `InvoicesPage.test.tsx`, `CustomerPortalPage.test.tsx`,
`ConsultationsRoutes.test.tsx`, `ConsultationWizardPage.test.tsx`) — this closes most of the April
review's "0 of 20 pages tested" finding, though it is concentrated on the newest (V1.1/V1.2) features;
older pages (Orders, Materials, Time Tracking dashboards) were not confirmed to have coverage in this
pass. MSW (`frontend/src/test/mocks/handlers.ts` + `server.ts`) remains the mocking backbone, consistent
with the April review's assessment of it being correctly configured.

### Coverage-gap list — critical behaviors with no/thin dedicated test coverage

From the live coverage run, the 20 lowest-covered backend modules (below the 68% average), cross-checked
against "no test file exists at all" for a sample of five:

| Module | Coverage | Dedicated test file? |
|---|---|---|
| `api/routers.py` | 0% | — (router-registration glue, likely exercised only via app startup) |
| `middleware/rate_limiting.py` | 0% | **No dedicated test at all** — the rate-limiting middleware itself is untested; only its *effects* (429s on login) are asserted incidentally elsewhere. |
| `ml/model_registry.py` | 0% | No |
| `models/common.py` | 0% | No (shared base/mixins — likely covered transitively) |
| `models/validators.py` | 0% | No (shared Pydantic validators — same caveat) |
| `services/comparison_service.py` | 10% | **Confirmed: no file matches `*comparison_service*` under `tests/`.** |
| `db/repositories/order.py` | 13% | No |
| `db/repositories/customer.py` | 14% | No |
| `ml/feature_engineering.py` | 17% | No |
| `ml/duration_model.py` | 20% | No |
| `services/label_service.py` | 20% | **Confirmed: no file matches `*label_service*`.** |
| `db/repositories/base.py` | 23% | No |
| `db/repositories/material.py` | 23% | No |
| `services/calendar_service.py` | 26% | **Confirmed: no file matches `*calendar_service*`.** |
| `services/handoff_service.py` | 26% | No |
| `services/metal_price_service.py` | 26% | No |
| `api/routers/measurements.py` | 28% | No |
| `services/system_monitor.py` | 29% | **Confirmed: no file matches `*system_monitor*`.** |
| `api/routers/metal_prices.py` | 30% | No |
| `services/ml_data_service.py` | 31% | No |

This list is a near-exact re-confirmation of the April review's "modules with zero direct tests" list —
`comparison_service`, `calendar_service`, `label_service`, `system_monitor` remain untested by name, 5
months later, despite substantial feature work landing around them in the interim (they were spot-checked
directly with `find tests -iname` and confirmed zero matches). `db/repositories/*` (the repository-pattern
layer CLAUDE.md's own patterns doc calls out) is uniformly the weakest-covered layer in the codebase
(13-23%) — this is architecturally significant, not incidental: it's the layer meant to be the seam for
swapping storage/mocking in tests, and it is the one nobody is testing directly.

**No test exists for:** the rate-limiting middleware in isolation (only observed indirectly through
login-endpoint behavior), the ML model registry, and — per OPS-09 — the actual Redis publish→WebSocket
delivery path.

---

## E. Ops readiness checklist

| Item | Status | Evidence |
|---|---|---|
| TLS | **Present** (Caddy, internal on-demand CA) | `deploy/Caddyfile`, `podman-compose.prod.yml:152-186`. Not live-verified on the actual workshop box in this pass. |
| Backups scheduled | **Not automated** — script correct, no default schedule | `scripts/backup.sh` (verified: has integrity check + gzip); `PRODUCTION_DEPLOYMENT.md:172-177` explicitly tells the operator to set up their own cron/timer; `make install-backup-cron` exists but is a manual, undocumented-in-onboarding step. |
| Restore tested | **Script is correct; no evidence of an actual test-restore having been run** | `make restore` → `scripts/restore.sh` (fixed gzip handling, confirmed via `grep gunzip`); "Restore getestet" is a checklist item in the deployment doc, i.e. an acknowledged manual step, not something CI or automation verifies. |
| Migrations at boot | **Present** | `podman-compose.prod.yml:76-82` — `alembic upgrade head && reference_seed && uvicorn`. |
| Migration rollback tested | **Present, in CI** (upgrade→downgrade→upgrade) | `migration-smoke` job, passed in last run (1m4s). |
| App-level rollback (bad deploy) documented | **Missing** | No mention of rolling back a bad `make update` / container image anywhere; the only "Rollback" section in the repo (`docs/DEPLOYMENT.md`) is stale and covers only Alembic (see OPS-08). |
| Health monitoring | **Present, in-app + external watchdog template** | `api/routers/health.py` (rich health family); `deploy/systemd/goldsmith-health-watchdog.{service,timer}` (external, email-based dead-man's-switch) — but see next row. |
| Health monitoring installed on prod | **Unverified / likely not installed** | No Makefile/setup.sh automation installs any `deploy/systemd/*` timer (OPS-07); nothing in this repo checkout confirms it is running on the actual workshop machine. |
| Alerting | **Email-based, templates exist; no Sentry** | `scripts/health-watchdog.sh` + `jobs/health_alert.py`; `ErrorBoundary.tsx:34-35` still has only a comment placeholder for Sentry, unchanged since July. |
| Log retention | **Present, container-level only** | `podman-compose.prod.yml` — `json-file` driver, `max-size: 10m`, `max-file: 3` on every service. No separate application-log rotation/retention policy found beyond this container-level cap; not verified whether podman (vs Docker) actually honors `logging.driver: json-file` identically (flagged as unverified in the July review too, same caveat still applies to `deploy.resources.limits`). |
| Resource limits | **Present in compose, host-verification unconfirmed** | `podman-compose.prod.yml` — every service has `deploy.resources.limits.{memory,cpus}`; July review flagged that `deploy.resources` may be a no-op under plain `podman-compose` (vs Docker Swarm/Kubernetes) — this was not re-verified in this pass (would require running on the actual target host). |
| Upgrade procedure documented | **Present** | `Makefile:259-264` (`make update`: rebuild → up -d --remove-orphans → migrate); `PRODUCTION_DEPLOYMENT.md`. |
| Rollback procedure documented | **Partial** — DB-only, and only in a stale doc | See OPS-08. |
| Dependency vulnerability scanning in CI | **Absent** | OPS-11; Dependabot (out-of-band, GitHub-native) is the only mechanism. |
| GDPR/retention jobs scheduled | **Templates only, not installed** | OPS-07. |

---

## F. Recommended order of work

1. **OPS-06 (Dependabot backlog, especially the 1 critical + `cryptography`)** — highest severity item in
   this whole review; 2 months of zero attention on a security-relevant dependency. Do this first,
   independent of everything else here.
2. **OPS-07 (wire the systemd timer installers)** — turns "the compliance controls exist in the repo" into
   "the compliance controls run on the actual box." This is the single highest-leverage ops fix: one
   Makefile target closes backups, GDPR erasure, retention sweep, and health monitoring simultaneously for
   any *future* deployment, and gives an existing deployment a checklist-verifiable way to confirm it's
   live (`systemctl --user list-timers`).
3. **OPS-01 (wire the two heavy E2E specs + the two newer ones into CI, even if only nightly)** — closes
   the biggest remaining coverage-of-critical-flows gap; the specs already exist, this is pure wiring.
4. **OPS-02 (frontend coverage tool)** — one `yarn add` + one CI line; currently a completely blind spot.
5. **OPS-04 + OPS-05 (CI caching, local test/lint Makefile targets)** — cheap, compounding quality-of-life
   fixes that reduce friction for whoever resumes work after this 2-month gap.
6. **OPS-11 + OPS-12 (pip-audit/npm audit, ruff in CI)** — cheap additions, directly reduce the chance
   OPS-06 recurs unnoticed.
7. **OPS-13 (frontend ESLint)** — larger effort (M), but the longest-standing open issue (#33, since July
   3rd) and the only item on this list with an existing tracking issue that's gone untouched.
8. **OPS-08, OPS-09, OPS-10, OPS-14, OPS-15, OPS-03** — lower-severity hygiene/documentation items; batch
   these into a single cleanup pass whenever someone is next in this part of the codebase.

---

## G. Things the user might have missed

- **The project looks worse on paper (stale prior review docs) than it is.** If someone reads
  `docs/review/2026-07-26/production-readiness.md` cold, they will conclude the install is broken, CI is
  red, and there's no TLS. All three are now false. Whoever picks this project back up should be told
  explicitly: "the July 26 sprint fixed Tier 0 and most of Tier 1/2 same-day; re-read `git log
  --since=2026-07-26` before trusting that document's verdict." The verdict section of that doc ("Not
  deployable today") is stale and should probably get a one-line update pointing at this review, even
  though this review doesn't touch that file per the read-only constraint.
- **The repo has been completely dormant for exactly 2 months** (last commit 2026-07-26, today is
  2026-09-24). Nothing is technically broken, but resuming work means: (a) re-running `poetry install` /
  `yarn install` fresh (this review's own venv was empty and had to be reinstalled from scratch — same
  will be true for whoever picks this up next), (b) doing the Dependabot pass before anything else, since
  it's the one thing that actively decays with time, and (c) deciding whether the 7 stale worktrees
  represent any unmerged work worth rescuing before deleting them (this review did not diff their working
  trees — that check is a prerequisite for safely running `git worktree remove`).
- **Branch protection exists but `enforce_admins` is off.** For a solo-maintainer repo this is a
  reasonable choice (you'd otherwise lock yourself out during exactly the kind of same-day red→green
  sprint that produced the current state), but it's worth being a deliberate choice rather than a default,
  since it means the 7-required-check gate is advisory for the repo owner specifically.
- **The retention-sweep job shipping in dry-run-only mode is a real design decision, not a bug** — it
  requires an explicit `RETENTION_EXECUTE=1` + "Anna+Henrik sign-off" per its own header comment. Don't
  treat "activate it" as a pure ops task; it's gated on a compliance decision this review isn't scoped to
  make. Flagged here only so it isn't lost track of as "done" once the timer-installer fix (OPS-07) ships.
- **The single most under-tested architectural layer is `db/repositories/*`** (13-23% coverage across the
  board), not any one feature area. Given CLAUDE.md's own coding-review standards call out the Repository
  Pattern by name, this is worth a deliberate look independent of any single feature's test backlog —
  it's the shared seam every service goes through.
- **No one has load-tested or even manually verified `deploy.resources.limits` under actual rootless
  podman-compose** (as opposed to Docker Swarm, where that key has real teeth). This has been flagged as
  an open question across two prior reviews and remains unverified; it would take ten minutes on the
  actual target host (`podman stats` while under load) to settle permanently instead of re-flagging it a
  third time.

---

## Verification (2026-09-25)

Not separately verified; its metrics were produced by executing the suites, exit codes recorded in the header ("Commands run"). No verifier re-rated any OPS finding. OPS-06 (HIGH) stays in Wave 5 of the plan; see decision D-17 in [MASTER-FIX-PLAN.md](MASTER-FIX-PLAN.md) about pulling the single critical bump forward.
