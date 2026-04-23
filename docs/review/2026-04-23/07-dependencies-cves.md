# Helper — Dependency CVEs & Upstream Advisories  (2026-04-23, HEAD `1feae6d`)

## Scope audited
Full backend (`pyproject.toml` direct + `poetry.lock` transitive) and full frontend (`frontend/package.json` + `frontend/yarn.lock`) dependency graph. Infra: `Containerfile`, `Dockerfile`, `podman-compose.yml`, `docker-compose.yml`, `.python-version` (3.11.5). Ran `poetry run pip-audit` and `yarn npm audit --severity high --recursive` as of 2026-04-23 and cross-referenced findings against GHSA / NVD / osv.dev. Also sampled framework usage style in source (SQLAlchemy, Pydantic, FastAPI) to flag legacy patterns independent of CVE posture.

**Tool runs succeeded on both sides** — this report is backed by concrete audit output, not guesses.

## Backend dependencies (direct)

| Dep                | Pinned (lock)   | Latest 2026-04-23 | CVEs (pinned)                                                       | Advisories / Notes                                                                                                                                             | Severity |
| ------------------ | --------------- | ----------------- | ------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| fastapi            | 0.121.3         | 0.121.x (current) | none direct                                                         | Pinned version is current; no known CVE against 0.121.3.                                                                                                      | OK       |
| starlette          | 0.49.3          | 0.49.x            | **CVE-2025-62727 FIXED** at 0.49.1                                  | Quadratic Range-header ReDoS in `FileResponse`/`StaticFiles`. Pinned 0.49.3 → fix is in. Leaving note for traceability.                                       | OK       |
| pydantic           | 2.12.4          | 2.12.x            | none                                                                | On v2 line (good). Codebase mostly uses v2 idioms, but see "Framework drift" below — two model files still use legacy `class Config:`.                        | OK       |
| pydantic-settings  | 2.11.0          | 2.11.x            | none                                                                | Fine.                                                                                                                                                         | OK       |
| uvicorn            | 0.32.1          | 0.37+             | none                                                                | ~5 minor versions behind; housekeeping.                                                                                                                       | P2       |
| sqlalchemy         | 2.0.44          | 2.0.x / 2.1       | none                                                                | SQLAlchemy **2.0** is installed, but `db/models.py` is written in **legacy 1.x style** (`Column`, `relationship`, no `Mapped[]` / `DeclarativeBase`).         | P2       |
| alembic            | 1.17.1          | 1.17.x            | none                                                                | Fine.                                                                                                                                                         | OK       |
| asyncpg            | 0.30.0          | 0.30.x            | none                                                                | Fine.                                                                                                                                                         | OK       |
| psycopg2-binary    | 2.9.11          | 2.9.x             | none                                                                | Only used for migrations (sync URL). Fine.                                                                                                                    | OK       |
| redis              | 5.3.1           | 6.x               | none                                                                | One major behind (v6 released). Housekeeping.                                                                                                                 | P2       |
| python-jose        | 3.5.0           | 3.5.0             | none affecting 3.5.0                                                | **CVE-2024-33663** (algorithm confusion, CVSS 9.3) was against ≤ 3.3.0; fixed in 3.3.1/3.4.0. 3.5.0 is clean. However, project is **effectively unmaintained** — commit activity is ~nil. Prefer `pyjwt` (already in deps!) and remove `python-jose`. | P1       |
| pyjwt              | 2.10.1          | 2.10.x            | none                                                                | Actively maintained. Keep this; drop python-jose.                                                                                                             | OK       |
| cryptography       | 44.0.3          | 46.0.7            | none against 44.0.3 directly (CVE-2026-39892 affects 45.x–<46.0.7)  | Two major versions behind; misses security-hardening (CVE-2026-26007 deprecation of SECT\* curves, general hardening in 45/46).                               | P2       |
| ecdsa              | 0.19.1          | 0.19.1            | **CVE-2024-23342** (Minerva timing attack, CVSS 5.9) — WON'T FIX    | Maintainer declared side-channel attacks out of scope. Pure-Python ECC. This is only pulled in as transitive of `python-jose[cryptography]` — drop python-jose and ecdsa goes with it. | P1       |
| passlib            | 1.7.4           | 1.7.4             | none CVEs                                                           | **Project effectively abandoned** (last release 2020). Breaks with `bcrypt >= 5.0`; only works because repo pins `bcrypt < 5`. FastAPI docs dropped recommendation. Plan a migration to direct `bcrypt` or `pwdlib`. | P1       |
| bcrypt             | 4.3.0           | 5.x               | none                                                                | Held back by passlib compat. Migrating off passlib frees this.                                                                                                | P2       |
| python-multipart   | 0.0.18          | 0.0.20+           | **CVE-2024-53981 FIXED** at 0.0.18; **CVE-2026-40347** (DoS via preamble/epilogue, Moderate) affects 0.0.18 | 0.0.18 is clean for 2024 DoS but new CVE-2026-40347 affects large-preamble handling. Bump to ≥ 0.0.20.                                                        | P1       |
| boto3 / botocore   | 1.40.69         | 1.40.x            | none                                                                | Fine.                                                                                                                                                         | OK       |
| pillow             | 12.1.1          | 12.2.0            | **CVE-2026-40192** (FITS decompression bomb, Medium)                | CVE-2026-25990 PSD OOB-write is already **fixed in 12.1.1**, but 12.1.1 is still vulnerable to CVE-2026-40192. Fix: bump to 12.2.0. App does handle user image upload → real exposure. | P1       |
| jinja2             | 3.1.6           | 3.1.x             | none                                                                | Fine.                                                                                                                                                         | OK       |
| fpdf2              | 2.8.7           | 2.8.x             | none                                                                | Fine.                                                                                                                                                         | OK       |
| aiosmtplib         | 5.1.0           | 5.1.x             | none                                                                | Fine.                                                                                                                                                         | OK       |
| segno              | 1.6.6           | 1.6.x             | none                                                                | Fine.                                                                                                                                                         | OK       |
| slowapi            | 0.1.9           | 0.1.x             | none                                                                | Fine.                                                                                                                                                         | OK       |
| email-validator    | 2.3.0           | 2.3.x             | none                                                                | Fine.                                                                                                                                                         | OK       |

### Backend transitive spot-check

| Transitive  | Pinned   | CVEs affecting pinned                                             | Severity |
| ----------- | -------- | ----------------------------------------------------------------- | -------- |
| urllib3     | 2.5.0    | **CVE-2025-66418**, **CVE-2025-66471**, **CVE-2026-21441** — DoS via compression bombs / chained encodings. Fix ≥ 2.6.3. | P1       |
| requests    | 2.33.1   | none                                                              | OK       |
| certifi     | 2025.10.5| none                                                              | OK       |
| idna        | 3.11     | none                                                              | OK       |
| anyio       | 4.11.0   | none                                                              | OK       |
| httpx       | 0.28.1   | none                                                              | OK       |

### Backend dev deps (pip-audit hits, non-production)

| Dep         | Pinned  | CVE                            | Severity (non-prod)            |
| ----------- | ------- | ------------------------------ | ------------------------------ |
| black       | 24.10.0 | CVE-2026-32274 (fix 26.3.1)    | P2 (dev-only cache-write flaw) |
| filelock    | 3.20.0  | CVE-2025-68146, CVE-2026-22701 | P2 (dev-only TOCTOU symlink)   |
| virtualenv  | 20.35.4 | CVE-2026-22702                 | P2 (dev-only TOCTOU)           |
| pygments    | 2.19.2  | CVE-2026-4539 (ReDoS, local)   | P2                             |
| pytest      | 8.4.2   | CVE-2025-71176 (/tmp perms)    | P2                             |

## Frontend dependencies

| Dep                | Pinned (lock)   | Latest 2026-04-23 | CVEs (pinned)                                                 | Advisories / Notes                                                                                                                                    | Severity |
| ------------------ | --------------- | ----------------- | ------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | -------- |
| react / react-dom  | 18.3.1          | 18.3.1 (LTS) / 19 | none                                                          | React 19 is GA but 18.3 is still supported; not a CVE issue.                                                                                          | OK       |
| react-router-dom   | 7.9.5           | 7.12.x            | **CVE-2026-22029** (XSS via open redirects, High), **CVE-2026-21884** (SSR XSS in ScrollRestoration, High) — both fix ≥ 7.12.0 | Confirmed by `yarn npm audit`. This app is SPA-only (not SSR), but the open-redirect flaw is still exploitable in SPA data/loader flows.              | **P0**   |
| axios              | 1.13.2          | 1.13.5            | **CVE-2026-25639** / GHSA-43fc-jf86-j433 — DoS via `__proto__` in `mergeConfig` (High) | Fix: 1.13.5. This is an internet-facing client in the frontend; DoS of the SPA from a malicious API response is realistic.                            | **P0**   |
| vite               | 7.3.1 (dev)     | 7.3.2 / 8.0.5     | **GHSA-v2wj-q39q-566r** (server.fs.deny bypass, High), **GHSA-p9ff-h696-f583** / CVE-2026-39363 (Arbitrary File Read via dev-server WebSocket, High) | Dev-server only, so risk is constrained to dev workstations — but still a HIGH arbitrary-file-read. Fix: 7.3.2.                                       | P1 (dev) |
| zod                | 4.3.6           | 4.3.x             | none                                                          | Fine.                                                                                                                                                 | OK       |
| recharts           | 3.4.1           | 3.4.x             | none                                                          | Fine.                                                                                                                                                 | OK       |
| date-fns           | 4.1.0           | 4.1.x             | none                                                          | Fine.                                                                                                                                                 | OK       |
| @yudiel/react-qr-scanner | 2.5.1     | 2.5.x             | none                                                          | Fine.                                                                                                                                                 | OK       |
| react-timer-hook   | 4.0.5           | 4.0.x             | none                                                          | Fine.                                                                                                                                                 | OK       |
| tailwindcss        | 4.2.2           | 4.2.x             | none                                                          | Fine.                                                                                                                                                 | OK       |
| vite-plugin-pwa    | 1.2.0           | 1.2.x             | pulls lodash 4.17.21 transitively → GHSA-r5fr-rjxr-66jc (code injection via `_.template` in workbox-build) | Only invoked at build-time, not runtime. Monitor; not production-exploitable unless build pipeline runs untrusted input.                              | P2       |
| happy-dom          | 20.8.9          | 20.x              | **CVE-2025-61927 FIXED** in v20 (present)                     | Previously CVSS 9.4 VM-escape / RCE affecting ≤ v19. 20.8.9 is clean. Leaving note — test-only but worth tracking.                                    | OK       |
| vitest             | 4.1.2           | 4.1.x             | none                                                          | Fine.                                                                                                                                                 | OK       |
| msw                | 2.12.14         | 2.13.4            | none                                                          | Slightly behind; housekeeping.                                                                                                                        | OK       |
| @playwright/test   | 1.58.2          | 1.58.x            | none                                                          | Fine.                                                                                                                                                 | OK       |

### Frontend transitive HIGH (from `yarn npm audit`)

| Transitive           | Pinned via           | CVE                                         | Severity |
| -------------------- | -------------------- | ------------------------------------------- | -------- |
| serialize-javascript | @rollup/plugin-terser 0.4.4 (build-time) | GHSA-5c6j-r48x-rmvq — RCE via RegExp.flags (≤ 7.0.2). Fix ≥ 7.0.3. | P2 (build-time) |
| lodash 4.17.21       | workbox-build (build-time)               | GHSA-r5fr-rjxr-66jc — code injection via `_.template`. Fix ≥ 4.17.24. | P2 (build-time) |

## Infra / base images

- **Python base image: `python:3.11-slim` (bookworm)**. Python 3.11.5 pinned in `.python-version` — Python 3.11 reaches **security-fixes-only** mode now, **EOL 2027-10-31**. Actionable but not urgent (no immediate CVE). Consider planning a 3.12/3.13 bump. Snyk reports ~3 HIGH vulns in the slim-bookworm layer itself (glibc/OpenSSL/systemd kernel surface) at any given time — rebuild image to pick up latest patches on each deploy.
- **Postgres 15-alpine (`podman-compose.yml`)** — supported until **2027-11-11**. Fine through V1.x, but plan a PG16/17 upgrade for the 2027 window. Alpine base keeps attack surface small; good.
- **Redis 7-alpine** (unpinned minor). `7:latest` currently resolves to 7.4.x. **Redis 7.2 EOL 2026-02-28 (already past)**, **Redis 7.4 EOL 2026-11-30**. Pin an explicit minor (`7.4-alpine`) and plan a Redis 7.6/8.x upgrade before end-of-year.
- **Node**: no explicit pin in Containerfile output, but Yarn 4.9.1 is packageManager-locked. Node 22 LTS is in Maintenance-LTS, EOL **2027-04-30** — fine.
- **Poetry** installed via `pip install poetry` in the Containerfile without a version pin → re-builds can silently pull in Poetry changes. Pin a major, e.g. `pip install "poetry>=2,<3"`.

Duplicate compose files (`docker-compose.yml` legacy vs `podman-compose.yml` canonical) drift — the Dockerfile legacy path runs `curl | python3 -` as root to install Poetry. If that file is still referenced anywhere (docs/CI), it's a supply-chain-over-curl smell. Recommend deleting `Dockerfile` + `docker-compose.yml` if Podman is the single source of truth per CLAUDE.md.

## Framework-pattern notes (drift since pins were chosen)

- **FastAPI startup**: `src/goldsmith_erp/main.py` still uses `@app.on_event("startup")`. This API has been deprecated since Starlette 0.26 and FastAPI docs exclusively recommend `lifespan=` (async context-manager) from ~0.100 onward. Current pin is 0.121 — migration is overdue. Low risk today, will break on FastAPI 1.x.
- **SQLAlchemy 2.0 style**: repo installs SA 2.0.44 but `db/models.py` uses legacy 1.x classmapping (`Column(...)`, `relationship(...)`, `Base = declarative_base()`). Zero `Mapped[]` / `mapped_column` / `DeclarativeBase` usage detected. Works fine in the 2.0 "legacy mode" compatibility layer, but (a) misses typed attribute checking mypy can catch, (b) will need rework before SA 2.1/3.0. Treat as tech-debt, not a CVE.
- **Pydantic v2 style**: mostly migrated — `ConfigDict`, `model_validate`, `model_config`. Two stragglers still use legacy `class Config:`:
  - `src/goldsmith_erp/models/customer.py`
  - `src/goldsmith_erp/models/measurement.py`
  Works because Pydantic v2 still accepts the old form with a deprecation warning (filtered out by `pytest.ini filterwarnings = ignore::DeprecationWarning` — which masks this). Low-risk but easy fix.
- **React 18.3**: no migration pressure yet. React 19 is GA but React 18.3 is the explicit LTS line. Fine to defer.

## Findings (prioritized)

| Severity | Location                                | Issue                                                                 | Fix                                                                                     |
| -------- | --------------------------------------- | --------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| **P0**   | `frontend/package.json` axios `^1.13.2` | CVE-2026-25639 `__proto__` DoS in `mergeConfig` (HIGH)                | Bump to `^1.13.5` and `yarn install`.                                                   |
| **P0**   | `frontend/package.json` react-router-dom `^7.9.5` | CVE-2026-22029 open-redirect XSS + CVE-2026-21884 ScrollRestoration SSR XSS (both HIGH) | Bump to `^7.12.0` and `yarn install`. Retest protected routes + redirect flows. |
| **P1**   | `poetry.lock` urllib3 2.5.0             | CVE-2025-66418 + CVE-2025-66471 + CVE-2026-21441 (compression DoS)    | Bump transitive: `poetry update urllib3` → expect ≥ 2.6.3.                              |
| **P1**   | `pyproject.toml` pillow `^12.1.1`       | CVE-2026-40192 FITS decompression bomb (Medium, but image-upload path is user-reachable) | Bump to `^12.2.0`.                                                                     |
| **P1**   | `pyproject.toml` python-multipart `^0.0.18` | CVE-2026-40347 multipart preamble/epilogue DoS (Moderate)             | Bump to `^0.0.20`. Validate FastAPI 0.121 pairing (should be fine).                     |
| **P1**   | `pyproject.toml` python-jose + ecdsa     | python-jose is unmaintained; ecdsa ships with unfixed CVE-2024-23342 (Minerva) that maintainer has declined to fix | **Remove python-jose** (pyjwt is already a dep and covers JWT needs). ecdsa falls off with it. |
| **P1**   | `pyproject.toml` passlib 1.7.4           | Abandoned upstream, blocks bcrypt 5.x                                 | Plan migration to direct `bcrypt` or `pwdlib`. Track as tech-debt ticket.               |
| **P1**   | `frontend/package.json` vite 7.3.1 (dev) | GHSA-v2wj-q39q-566r + GHSA-p9ff-h696-f583 (dev-server file-read, HIGH) | Bump to `^7.3.2` (or `^8.0.5` if ready). Dev-only but still relevant on shared dev hosts. |
| **P2**   | `src/goldsmith_erp/main.py`              | `@app.on_event("startup")` deprecated in Starlette ≥ 0.26             | Migrate to `lifespan=` async context manager.                                           |
| **P2**   | `src/goldsmith_erp/db/models.py`         | Full codebase in SA 1.x legacy style on SA 2.0.44                     | Plan incremental migration to `Mapped[]` / `DeclarativeBase` before SA 2.1.             |
| **P2**   | `models/customer.py`, `models/measurement.py` | Pydantic v1 `class Config:` still present (v2 warns, pytest suppresses the warning) | Convert to `model_config = ConfigDict(...)`.                                            |
| **P2**   | `poetry.lock` cryptography 44.0.3        | Two major versions behind (current 46.0.7); missing hardening         | `poetry update cryptography`.                                                           |
| **P2**   | `Containerfile` Poetry unpinned          | `pip install --no-cache-dir poetry` → floating version                | Pin: `pip install "poetry>=2,<3"`.                                                      |
| **P2**   | `podman-compose.yml` Redis `7-alpine`    | Unpinned minor; 7.2 already EOL, 7.4 EOL 2026-11-30                   | Pin `7.4-alpine` explicitly; schedule 7.6/8.x bump before Nov 2026.                     |
| **P2**   | `.python-version` 3.11.5                 | Python 3.11 in security-only mode; EOL 2027-10-31                     | Plan 3.12 or 3.13 bump.                                                                 |
| **P2**   | `Dockerfile` + `docker-compose.yml`      | Legacy duplicate of Podman setup; runs `curl | python3 -` as root to install Poetry | Delete if unused; CLAUDE.md already says Podman is canonical.                           |
| **P2**   | Dev deps (pip-audit)                     | black/filelock/virtualenv/pygments/pytest each has a dev-only CVE     | `poetry update --only dev` sweep.                                                       |
| **P2**   | build-time transitive (yarn audit)       | serialize-javascript + lodash via vite-plugin-pwa (workbox-build)     | Try `yarn dedupe` / `yarn up workbox-build`; accept if no non-breaking upgrade path.    |

## Tool outputs (summary)

**`poetry run pip-audit`** (backend, after installing dev deps):
> Found 9 known vulnerabilities in 6 packages: black (1), filelock (2), pygments (1), pytest (1), urllib3 (3), virtualenv (1). **Only `urllib3` ships in the production image** — the other 5 are `poetry group dev` and never get into the container. urllib3 is the only production-path finding from pip-audit.

**`yarn npm audit --severity high --recursive`** (frontend):
> 7 HIGH findings: axios (1.13.2), react-router (×2), vite (×2), lodash (workbox transitive), serialize-javascript (@rollup/plugin-terser transitive). All with available upstream fixes. The two runtime P0s are axios + react-router-dom.

## Open questions

- Is the JWT path using **python-jose or pyjwt**? If both are imported, which one actually signs tokens? If python-jose isn't used by `core/security.py`, it can be dropped immediately with zero surface change (and ecdsa CVE-2024-23342 goes away for free). Worth checking before a reviewer cites it.
- Are `Dockerfile` + `docker-compose.yml` still referenced by any CI job? If yes, fixing the Poetry install-as-root pattern matters; if not, delete them.
- Is `passlib` still depended on for anything beyond `CryptContext` bcrypt? If only bcrypt, the migration to direct `bcrypt` is ~20 LOC. Confirm before scoping the ticket.
- Target Python version for V1.1? Suggest 3.12 — gives ~3 years of runway and pydantic/sqlalchemy are well-tested on it.

## Sources

- [Axios GHSA-43fc-jf86-j433](https://github.com/axios/axios/security/advisories/GHSA-43fc-jf86-j433)
- [React Router GHSA-2w69-qvjg-hvjx (open-redirect XSS)](https://github.com/remix-run/react-router/security/advisories/GHSA-2w69-qvjg-hvjx)
- [React Router GHSA-8v8x-cx79-35w7 (ScrollRestoration XSS)](https://github.com/advisories/GHSA-8v8x-cx79-35w7)
- [Vite GHSA-p9ff-h696-f583 (dev-server file read)](https://github.com/vitejs/vite/security/advisories/GHSA-p9ff-h696-f583)
- [Vite GHSA-v2wj-q39q-566r (fs.deny bypass)](https://github.com/advisories/GHSA-v2wj-q39q-566r)
- [urllib3 CVE-2025-66418](https://github.com/advisories/GHSA-48p4-8xcf-vxj5)
- [urllib3 CVE-2026-21441](https://urllib3.readthedocs.io/en/2.6.3/changelog.html)
- [python-multipart CVE-2026-40347](https://advisories.gitlab.com/pypi/python-multipart/CVE-2026-40347/)
- [python-jose CVE-2024-33663 (algorithm confusion)](https://github.com/advisories/GHSA-6c5p-j8vq-pqhj)
- [python-ecdsa CVE-2024-23342 (Minerva — WON'T FIX)](https://github.com/tlsfuzzer/python-ecdsa/security/advisories/GHSA-wj6h-64fc-37mp)
- [passlib abandoned — FastAPI discussion #11773](https://github.com/fastapi/fastapi/discussions/11773)
- [Pillow 12.1.1 release + CVE-2026-25990 / CVE-2026-40192](https://pillow.readthedocs.io/en/latest/releasenotes/12.1.1.html)
- [Starlette CVE-2025-62727 (FIXED in 0.49.1 — current pin is 0.49.3)](https://github.com/advisories/GHSA-7f5h-v6xp-fcq8)
- [Happy-DOM CVE-2025-61927 (FIXED in v20 — current pin is 20.8.9)](https://security.snyk.io/vuln/SNYK-JS-HAPPYDOM-13535083)
- [Python EOL calendar](https://devguide.python.org/versions/)
- [PostgreSQL versioning policy](https://www.postgresql.org/support/versioning/)
- [Redis EOL tracker](https://endoflife.date/redis)
- [Node.js EOL calendar](https://endoflife.date/nodejs)
