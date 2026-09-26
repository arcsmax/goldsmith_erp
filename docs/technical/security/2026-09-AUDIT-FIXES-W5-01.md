# Security fixes, audit 2026-09-25 (wave 5: dependency backlog, OPS-06 / W5-01)

Source: `docs/review/2026-09-25/06-testing-ci-ops.md` (OPS-06), `docs/review/2026-09-25/MASTER-FIX-PLAN.md`
(W5-01). Alert counts pulled from `gh api repos/arcsmax/goldsmith_erp/dependabot/alerts` on 2026-09-25.

## Backend (Poetry)

| Package | Severity | From → To | Status |
|---|---|---|---|
| anyio | critical | 4.11.0 → 4.14.2 | Fixed — not a direct dependency (pulled in by `starlette`/`httpx`); pinned directly in `[tool.poetry.dependencies]` to force the resolver past the vulnerable range. |
| cryptography | high | 48.0.1 → 50.0.1 | Fixed — direct dependency, bumped `^48.0.1` → `^50.0.0`. |
| pytest | medium | 8.4.2 → 9.1.1 | Fixed — dev dependency; `pytest-asyncio` bumped alongside (`^0.23.0` → `^1.0.0`, which requires `pytest<10,>=8.4`) since 0.23.x caps at `pytest<9`. |
| pip | medium | 26.1.2 → 26.2.1 | Fixed — not a project dependency; appears in the lockfile only because `pip-audit`'s `pip-api` dependency requires `pip = "*"`. Pinned `pip = ">=26.2.0"` in the dev group to force the newer lock entry (does not change the venv's bootstrap `pip` binary). |
| click | high (PYSEC-2026-2132, found by `pip-audit`, not yet a GitHub Dependabot alert at scan time) | 8.3.0 → 8.5.0 | Fixed — not a project dependency; transitive via `black`/`uvicorn`. Pinned `click = ">=8.3.3"`. |
| ecdsa | high | 0.19.2 (unchanged) | **Blocked, not bumped.** No patched version exists (`first_patched_version` is empty in the Dependabot record; `pip-audit` confirms PYSEC-2026-1325 has no fix). `ecdsa` is a transitive, unavoidable dependency of `python-jose[cryptography]`, itself a direct dependency used by `core/security.py` for JWT handling alongside `pyjwt` (already present). The only real fix is dropping `python-jose` in favor of the `pyjwt`-only code path already partially in place — that is an application-code change to `src/goldsmith_erp/core/security.py` (and likely other call sites), which is out of scope for this dependency-only pass. Tracked as a follow-up; see `docs/review/2026-09-25/MASTER-FIX-PLAN.md` row W5-01 ("replace python-jose with pyjwt").

Full backend suite: 3391 passed, 6 skipped, 1 xfailed (both before and after — no regressions).

### Follow-up resolved: `python-jose` → `pyjwt` (ecdsa now gone entirely)

The `ecdsa` blocker above is resolved. `core/security.py`, `api/deps.py`,
`middleware/auth_required.py`, `main.py` and `api/routers/auth.py` were migrated from
`from jose import JWTError, jwt` to `import jwt` (PyJWT, already a dependency at 2.13.0 but
previously unused), mapping `JWTError` to `jwt.InvalidTokenError` (PyJWT's
`ExpiredSignatureError`/`DecodeError`/`InvalidSignatureError` are all subclasses, so every
`except`/`raise` site keeps its exact behaviour, including the `jti` revocation logic and the
refresh grace window). `python-jose` and the direct `ecdsa` pin were removed from
`pyproject.toml`; `poetry lock` drops `python-jose`, `ecdsa`, `pyasn1`, and `rsa` from the lock
file entirely. A new test (`tests/unit/test_security.py::TestJWTTokens::test_token_signed_with_different_algorithm_is_rejected`)
asserts a token signed with a non-pinned algorithm (HS384 instead of HS256) is rejected via
`jwt.InvalidAlgorithmError`. Full backend suite after the migration: 3684 passed, 6 skipped, 1
xfailed. `pip-audit` in a fresh worktree venv: **no known vulnerabilities found.**

## Frontend (Yarn)

Several of the npm alerts Dependabot reports are **not** against `frontend/` at all — they resolve to
`docs/architecture/likec4/package-lock.json` (a separate, unrelated Node project for architecture
diagrams), which pins `vite@6.4.2`, `browserslist@4.28.2`, `nanoid@3.3.12`, `postcss@8.5.15`,
`playwright@1.54.2` and `baseline-browser-mapping@2.10.32` — all inside the vulnerable ranges. That
lockfile is outside this pass's scope (`docs/architecture/likec4/**` was not in scope); per the
Master Fix Plan's own recommendation, it should be deleted or regenerated separately.

`frontend/` itself was independently vulnerable on a different, overlapping set of packages (checked
via `yarn why` against each alert's vulnerable range):

| Package | Severity | From → To | Status |
|---|---|---|---|
| react-router (via `react-router-dom`) | high | 7.15.1 → 7.18.4 | Fixed — bumped the direct dependency `react-router-dom` `^7.15.1` → `^7.18.4`. |
| vitest / @vitest/mocker | medium | 4.1.2 → 4.1.11 | Fixed — bumped the direct devDependency `vitest` `^4.0.10` → `^4.1.11` (also required for `@vitest/coverage-v8`, see OPS-02 below). |
| fast-uri | high | 3.1.4 → 3.1.8 | Fixed — transitive via `ajv`; existing `resolutions` entry bumped `^3.1.2` → `^3.1.6`. |
| nanoid | high | 3.3.12 → 3.3.19 | Fixed — transitive via `postcss`; added a `resolutions` entry `^3.3.18`. |
| postcss | high + medium | 8.5.15 → 8.5.28 | Fixed — transitive via `vite`; existing `resolutions` entry bumped `^8.5.15` → `^8.5.23`. |
| browserslist | high | 4.27.0/4.28.2 → 4.29.1 | Fixed — transitive via `@babel/*`/`core-js-compat`; added a `resolutions` entry `^4.28.7`. |
| baseline-browser-mapping | medium | 2.8.25/2.10.13 → 2.11.26 | Fixed — transitive via `browserslist`; added a `resolutions` entry `^2.11.0`. |
| lodash | high + medium | 4.17.23 → **4.18.1** | Fixed, with a detour — bumping the `resolutions` pin to the first available fix, `4.18.0`, broke `yarn vite build` (`Error: Unable to generate service worker from template. 'assignWith is not defined'`, thrown by `workbox-build`'s use of `require('lodash/template')`): the 4.18.0 patch release had a modular-build packaging regression. `4.18.1` (published shortly after) fixes it; build, `tsc`, and the full vitest suite are all green on `4.18.1`. |
| vite | high | already 7.3.6 / 8.1.5 | Not vulnerable in `frontend/` — the alert's vulnerable range is `<= 6.4.2`; `frontend/`'s resolved versions are already two majors past the fix. Only the `likec4` lockfile above is actually affected. |
| playwright | high | already 1.58.2 | Not vulnerable in `frontend/` — already past the fix version (1.55.1); `@playwright/test` devDependency was already `^1.58.2`. |

Full frontend suites after every bump: `tsc --noEmit` exit 0, `vitest run` 69/69 files, 591/591 tests
passed, `vite build` exit 0 (including the PWA/service-worker generation step, which is what caught
the lodash 4.18.0 regression above).

## Frontend coverage tooling (OPS-02)

Added `@vitest/coverage-v8@^4.1.11` (matching the bumped `vitest@^4.1.11` major/minor — `4.1.11` is
also the latest `4.x` release of `@vitest/coverage-v8`, so no unrelated major bump was pulled in).
`frontend/vitest.config.ts` already had a `coverage` block (added ahead of the dependency actually
being installed); its `reporter` was narrowed to `['text', 'lcov']` (previously
`['text', 'json', 'html']`) — `text` for local/CI terminal output, `lcov` for CI/editor tooling — and
no `coverage.thresholds` were added, per instructions (record a baseline first).

`yarn test:coverage` (`vitest --coverage`, already wired in `package.json` from an earlier pass) run
2026-09-25: **54.35% statements / 46.33% branches / 48.57% functions / 56.13% lines** across 69 test
files / 591 tests. `frontend/coverage/` (the `lcov-report/` HTML and `lcov.info`) is gitignored
(`frontend/coverage/` added to the root `.gitignore`) and was never committed.
