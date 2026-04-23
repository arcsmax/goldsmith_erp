# Code Review Summary — Goldsmith ERP
**Date:** 2026-04-23 · **Target:** main @ `1feae6d` · **Method:** 8 parallel specialist agents + 2 helpers

## Reports in this bundle

| # | Focus | File | Findings |
|---|---|---|---|
| 01 | Backend architecture & API design | `01-backend-architecture.md` | 21 (3 P0, 12 P1, 6 P2) |
| 02 | Frontend React quality | `02-frontend-react.md` | 33 (3 P0, 18 P1, 12 P2) |
| 03 | Security audit | `03-security-audit.md` | 26 (3 P0, 10 P1, 13 P2) |
| 04 | GDPR / privacy / data protection | `04-gdpr-privacy.md` | 23 (8 P0, 9 P1, 6 P2) |
| 05 | Database, migrations & performance | `05-database-migrations.md` | 25+ (5 P0, 10 P1, 10 P2) |
| 06 | Testing, CI & tooling | `06-testing-ci.md` | 30 (5 P0, 11 P1, 14 P2) |
| 07 | Dependency CVEs & advisories (helper) | `07-dependencies-cves.md` | 18 (2 P0, 6 P1, 10 P2) |
| 08 | Architectural reasoning (helper) | `08-architectural-reasoning.md` | 10 (0 P0, 7 P1, 3 P2) |
|   | **TOTAL** |   | **≈187 findings, ≈29 P0** |

## Health snapshot

**Verdict:** The codebase is in broadly good shape — much better than the March-2026 dormant state described in memory. V1.0 + V1.1 work has produced genuinely high-quality subsystems (scanner pipeline, GDPR erasure + file scrub, Alembic migration chain, pub/sub retry semantics, auth refresh flow, bundle-size gate). Test depth is real (990 backend pytest functions, 2,112 assertions, 258 real DB commits — the "348 tests" memory note is stale).

However, **a cluster of load-bearing configuration and governance issues** blocks a production-grade posture: a dead audit middleware, duplicate RBAC systems, money-as-float, plaintext customer PII, two runtime dependency CVEs, and a CI test suite that never actually runs against PostgreSQL. Most are *configuration or plumbing* gaps — the underlying code is mostly sound. Fixable in 1–2 focused sprints.

## The 10 most load-bearing issues (cross-cutting)

These either (a) appeared in ≥2 agents' reports, indicating robust signal, or (b) are singular findings severe enough to block production.

| # | Issue | Where | Agents | Why it matters |
|---|---|---|---|---|
| 1 | **`AuditLoggingMiddleware` defined but never registered** in `main.py` | `src/goldsmith_erp/middleware/audit_logging.py` vs `main.py:90-107` | 01, 03, 04 | GDPR Art. 30 records-of-processing gap. CLAUDE.md rule violated. Every customer PII access is unaudited despite code implying otherwise. |
| 2 | **Two parallel `Permission` / `require_permission` systems** | `src/goldsmith_erp/api/deps.py:108-217` vs `src/goldsmith_erp/core/permissions.py:16-423` | 01, 03 | 4–5 routers import the smaller 17-permission enum (`customers`, `measurements`, `metal_types`, `metal_prices`, `metal_inventory`); the rest import the 50+ version. Latent privilege escalation / silent-403 foot-gun. |
| 3 | **Money stored as `Float` in 28+ columns** (Order, Invoice, Quote, Valuation, MetalPurchase, OrderItem, Gemstone) | `src/goldsmith_erp/db/models.py:381,413-424,566,813-859,933,1266-1325,1401-1455,2039,2194` | 01, 05 | Round-off drift on every multiply/add. Blocks HGB §257 audit reconciliation. Visible as invoice totals like `4500.01` instead of `4500.00`. |
| 4 | **Customer PII stored plaintext** (`first_name`, `last_name`, `email`, `birthday`, address parts); **insurance `appraised_value` plaintext** | `db/models.py:221-234` (customer), `db/models.py:2039` (valuation); `services/customer_service.py:267` (`PII_FIELDS` incomplete) | 04, 05 | Direct CLAUDE.md rule violation. Email `.ilike()` in `search_customers` is incompatible with non-deterministic Fernet, implying data is plaintext at rest today. Unique-email index additionally incompatible with encryption. |
| 5 | **Financial data (price, costs, margin) visible to VIEWERs**, and financial reads **not audit-logged** | `models/order.py:294-344` + `api/routers/orders.py:24`; `api/routers/invoices.py`, `valuations.py`, `scrap_gold.py` GET handlers | 04 | Both halves of CLAUDE.md "Financial Data" rule violated. Scanner service already has role-based field projection (`scanner_service.py:176` `ORDER_FIELDS_BY_ROLE`) — the REST API doesn't use it. |
| 6 | **Consent management code references columns that don't exist** on `Customer` | `src/goldsmith_erp/db/repositories/customer.py:464-535` | 04 | `update_consent` writes `consent_marketing`, `email_communication_consent`, etc. — none exist in `db/models.py:214-276`. Runtime `AttributeError` for any call. Means there is no working consent storage; any marketing / reminder / birthday feature has no legal basis. |
| 7 | **Test suite runs SQLite, not Postgres** — CI's PG service is used only for `alembic upgrade` | `tests/conftest.py:33`, `tests/integration/conftest.py:42`; `.github/workflows/ci.yml` | 06 | Every test runs against SQLite. `test_concurrent_metal_consumption.py` (FIFO/LIFO money-calc race) is `skipif(sqlite)` → silently skipped in CI. No PG dialect behaviour is exercised. Production is PG 15. |
| 8 | **Runtime dependency CVEs**: axios `1.13.2` (CVE-2026-25639 `__proto__` DoS), react-router-dom `7.9.5` (CVE-2026-22029 open-redirect XSS + CVE-2026-21884 SSR-style XSS) | `frontend/package.json` | 03, 07 | Both HIGH-severity, both have available fixes (axios ≥ 1.13.5, react-router-dom ≥ 7.12.0). |
| 9 | **Public `/users/register` + 7-8 day JWT + no token blocklist + no MFA + weak compose defaults** | `middleware/auth_required.py:29` + `api/routers/users.py:19`; `core/config.py` token lifetime; `docker-compose.yml:23,35`; `podman-compose.yml` | 01, 03 | Email-enumeration oracle (`register` 400/201 split). Stolen JWT valid for a week regardless of logout / password change. Dev compose ships `POSTGRES_PASSWORD=pass` and binds DB to `0.0.0.0`. |
| 10 | **`gdpr-cleanup.sh` 30-day cron performs `db.delete(customer)` only** — no re-run of file erasure, no audit row written, no `gdpr_requests` status update | `scripts/gdpr-cleanup.sh:66-85` | 04 | If files failed during the initial erasure (`PARTIAL_FILE_ERASURE`), they are orphaned forever. The cron also loses its trace once the FK is CASCADE-nulled post-delete. |

## Thematic observations

### What's working (preserve and extend)

- **Scanner pipeline (V1.1).** Both backend (`scanner_service.py` + `routers/scanner.py`) and frontend (`QrCameraScanner.tsx` + `QuickActionModalV2.tsx`) are singled out by 3 different reviewers as exemplary: strict Pydantic (`StrictRequestBase` with `extra="forbid"`), explicit `user_id` rejection from body, focus trap, Esc-to-close, camera-stream lifecycle, deliberate code-splitting under a 250 KB bundle gate.
- **Migration chain.** 6 linear migrations `v1_initial → 20260420_h9_restrict`, all reversible, all idempotent via `migration_helpers.py`. FK `ondelete` policy is explicitly documented and applied.
- **Auth refresh flow.** `frontend/src/api/client.ts:32-134` handles refresh storms with a queue, `_retry` sentinel, and graceful `auth:session-expired` event — a cleaner pattern than most projects of this size have.
- **GDPR engineering bones.** `services/file_erasure_service.py` (path-traversal guard, NOT-NULL sentinel, per-file audit), `UserService.anonymize_user` (HMAC tracking token), `services/customer_service.scrub_customer_pii` declarative registry, and `GDPRRequest` lifecycle are all well-designed — the gaps are scope (what's covered) rather than quality.
- **`transactional(db)` + retry-and-never-raise `publish_event`** = correct event ordering across every sampled service.
- **CI-level bundle-size gate** (`.github/workflows/bundle-size-gate.yml`) enforcing 250 KB scanner ceiling is above-median tooling.
- **Test quality** where tests exist: 2.1 assertions/test avg, real JWT issuance in fixtures, rate-limiter reset between tests, migration upgrade+downgrade tests (`test_migration_qr_core.py`, `test_migration_slice_2.py`) — these are behavioural tests, not mock theatre.

### Systemic gaps

1. **Config drift between what's implemented and what's active.** `AuditLoggingMiddleware`, `MFA` URL prefix, consent-management code, 4 Playwright E2E specs, `pylint`, `pip-audit`, frontend ESLint — all exist in the repo, none is *wired into execution*. This is a shared pattern: capability present, plumbing missing.
2. **Typing / validation discipline not enforced.** `mypy --ignore-missing-imports` in CI neutralises the `strict=true` in `pyproject.toml`. `tsconfig.json` has `strict:true` but 40+ `catch (err: any)` and pervasive `as any` casts. The bar is declared but not held.
3. **No feature-flag / kill-switch mechanism.** Rolling back a misbehaving scanner or ML feature currently means redeploying. `core/config.py` has capability booleans, not feature flags.
4. **Observability floor is in-memory only.** `middleware/request_metrics.py` ring buffer dies on restart. No `/metrics`, no Sentry, no OpenTelemetry. Structured JSON logging is strong (`core/logging.py`); everything above it is missing.
5. **`db/models.py` at 2,435 LOC / 64 classes is the coupling hotspot** — every schema change risks a big, hard-to-review diff. A V1.2 multi-tenancy migration would be painful without a split first.
6. **Services raise `HTTPException` directly** (70+ sites). Couples service layer to HTTP transport; blocks reuse from CLI/jobs; means `ValueError`s become raw 500s. No global exception handler except `RateLimitExceeded`.

### Contradictions & corrections to the initial brief

- **Test count.** Brief said "60 backend + 18 frontend tests". Reality: 990 backend test functions across 53 files + 423 frontend `it()`/`test()` across 22 files (18 Vitest + 4 Playwright). The "348 tests" memory was counting something different; the stale figure should be updated.
- **JWT in localStorage.** CLAUDE.md flags this as a security concern to address; migration to HttpOnly cookies has already shipped (`frontend/src/api/client.ts:15` `withCredentials: true`, no `localStorage` token read). Update CLAUDE.md to reflect current state.
- **Module coverage for V1.0.** Memory says "V1.0 complete: 348 tests, 124 routes, PWA". Route count is broadly right (32 router files). Test coverage at the integration-router level is actually **less comprehensive** than memory implies: `users`, `invoices`, `notifications`, `time_tracking` (start/stop/manual), `materials`, `photos`, `scrap_gold`, `comments`, `calendar`, `handoffs` have zero integration tests.

## How the findings group by effort

Rough effort mapping — detail in `FIX-PLAN.md`:

- **Dependency bumps** (axios, react-router-dom, urllib3, pillow, python-multipart, vite, cryptography, python-jose removal): **~2 days** total, ordered work.
- **Config / middleware wiring** (register `AuditLoggingMiddleware`, tighten compose defaults, add CSP/HSTS, pin `camera=(self)` in Permissions-Policy, remove `/users/register` from `PUBLIC_PATHS`, drop query-param JWT on WS, shorten token lifetime + blocklist): **3-5 days** with careful testing.
- **Duplicate-RBAC merge** + permission-matrix test: **2 days**.
- **Money → Numeric migration** (28 columns + data backfill + frontend coordination): **1–2 weeks** — the single biggest fix.
- **PII encryption rollout** (`EncryptedString` TypeDecorator + HMAC search columns + one-time backfill): **1–2 weeks**.
- **Financial-data role projection + audit-logging**: **1 week**.
- **CI: PG test target + Playwright job + downgrade smoke + pip-audit + yarn audit + ESLint**: **3–5 days**.
- **Consent columns + retention engine + breach-notification infra**: **1–2 weeks** (GDPR completeness).
- **Feature-flag mechanism**: **1–2 days**.
- **Services raise domain errors, not HTTPException** + global exception handler: **3–5 days** (large surface area but mechanical).
- **`db/models.py` split**: **2–3 days**, ideally before V1.2 tenancy work.
- **Observability**: `/metrics` endpoint + Sentry integration = **2 days**; OpenTelemetry = larger.

## Next step

See `FIX-PLAN.md` for the prioritized P0/P1/P2 ranking with file:line, recommended fix approach, and effort sizing. No code changes have been made in this review pass — all files here are new artifacts under `docs/review/2026-04-23/`.
