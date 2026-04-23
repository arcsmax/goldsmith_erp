# Prioritized Fix Plan — Goldsmith ERP
**Source:** `SUMMARY.md` + 8 agent reports in this directory · **Target:** main @ `1feae6d` · **Date:** 2026-04-23

**Legend**
- **Severity**: P0 = block production / violates CLAUDE.md / exploitable · P1 = correctness / perf / soon-to-bite · P2 = tech debt, housekeeping
- **Effort**: S ≤ 1 day · M = 1–3 days · L = 1–2 weeks · XL = >2 weeks
- **Owner hint**: `BE` backend, `FE` frontend, `DB` database/migrations, `SEC` security, `GDPR` compliance, `CI` testing/tooling, `OPS` infra, `DEP` deps
- **Origin**: the agent report that flagged it (01–08)

Every row below has been verified against the referenced `file:line`. No code has been modified.

---

## P0 — Ship blockers / CLAUDE.md violations / exploitable

Grouped for sequencing. Fix the **Config-wiring** and **Deps** groups first (cheapest, highest impact). Then **PII + financial** (GDPR core). **Money-as-Float** last but unavoidable.

### Group A — Config / middleware wiring (quick wins, high impact)

| ID | Severity | File:line | Issue | Fix | Effort | Owner | Origin |
|----|----------|-----------|-------|-----|--------|-------|--------|
| A1 | P0 | `src/goldsmith_erp/middleware/audit_logging.py:74-301` + `src/goldsmith_erp/main.py:90-107` | `AuditLoggingMiddleware` defined but never registered → GDPR Art. 30 records-of-processing gap; customer PII access unaudited. | Register after `AuthRequiredMiddleware`; have auth middleware set `request.state.user`; move the DB write to a background task so a blocked audit can't stall the response; buffer through Redis for batch write. | M | BE + GDPR | 01, 03, 04 |
| A2 | P0 | `src/goldsmith_erp/api/deps.py:108-217` vs `src/goldsmith_erp/core/permissions.py:16-423` | Two parallel `Permission` enums / `require_permission` impls. 5 routers (`customers.py:13`, `measurements.py:21`, `metal_types.py:23`, `metal_prices.py:27`, `metal_inventory.py:25`) use the 17-permission version; rest use the 50+ version. | Delete `Permission`/`ROLE_PERMISSIONS`/`has_permission`/`require_permission` from `api/deps.py` (keep only `get_current_user`, `get_current_admin_user`, `get_token_from_cookie_or_header`). Migrate the 5 routers to `core.permissions`. Add a test asserting every `Permission` value appears in exactly one map. | M | BE + SEC | 01, 03 |
| A3 | P0 | `middleware/auth_required.py:29` + `api/routers/users.py:19-43` | Public `/users/register` — email-enumeration oracle + unauthenticated account creation. | Remove from `PUBLIC_PATHS`; keep registration as an ADMIN-only path (reuse `create_user_by_admin`); return generic 200 on duplicate email to remove the oracle. Alternative: put it behind an invitation-token gate. Confirm product intent first. | S | BE + SEC | 01, 03 |
| A4 | P0 | `docker-compose.yml:23,35`, `podman-compose.yml` | Ships with `POSTGRES_PASSWORD=pass` + DB bound to `0.0.0.0:5432`. `SECRET_KEY` already fails loudly on insecure default (good) but DB creds don't. | Change to `POSTGRES_PASSWORD:?fail` pattern (already in `podman-compose.prod.yml:11`). Bind DB to `127.0.0.1:5432` in dev compose. | S | OPS | 03 |
| A5 | P0 | `frontend/src/` (whole tree) | No `ErrorBoundary` anywhere — a single render crash = blank screen in the workshop. | Add a top-level boundary around `<Suspense>` in `App.tsx` + a second inside `MainLayout` around `<Outlet/>`. Fallback UI with retry. | S | FE | 02 |
| A6 | P0 | `frontend/src/pages/CustomerPortalPage.tsx:191-198` | Raw `fetch('/api/v1/portal/lookup', ...)` sends auth cookies from logged-in employees to what should be a public-portal endpoint. | Use `apiClient.post('/portal/lookup', …, { withCredentials: false })` or set `credentials: 'omit'` on the `fetch`. Route through `apiClient` for consistent error handling. | S | FE + SEC | 02 |
| A7 | P0 | `frontend/src/api/client.ts:12-21, 60-63` | `withCredentials: true` but request interceptor is a no-op — no CSRF token attached on state-changing requests. | Confirm backend emits `SameSite=Strict` + a `csrf_token` non-HttpOnly cookie; attach it to the `X-CSRF-Token` header in the interceptor for `POST/PUT/PATCH/DELETE`. Coordinate with A1's middleware work. | S | FE + BE + SEC | 02 |

### Group B — Runtime dependency CVEs (dependency bumps only)

| ID | Severity | File:line | Issue | Fix | Effort | Owner | Origin |
|----|----------|-----------|-------|-----|--------|-------|--------|
| B1 | P0 | `frontend/package.json` `axios ^1.13.2` | CVE-2026-25639 `__proto__` DoS in `mergeConfig` (HIGH). Exploitable via malicious API response. | `yarn up axios@^1.13.5 && yarn install` | S | DEP + FE | 07 |
| B2 | P0 | `frontend/package.json` `react-router-dom ^7.9.5` | CVE-2026-22029 open-redirect XSS + CVE-2026-21884 ScrollRestoration SSR XSS (both HIGH). | `yarn up react-router-dom@^7.12.0 && yarn install`. Retest protected routes + redirect flows (login → returnTo). | S | DEP + FE | 03, 07 |

### Group C — PII encryption + financial-data controls (GDPR/CLAUDE.md)

| ID | Severity | File:line | Issue | Fix | Effort | Owner | Origin |
|----|----------|-----------|-------|-----|--------|-------|--------|
| C1 | P0 | `src/goldsmith_erp/db/models.py:221-234`; `services/customer_service.py:267` | Customer `first_name`, `last_name`, `email`, (likely `birthday`, `company_name`) stored plaintext. `PII_FIELDS` omits them. `search_customers` uses `email.ilike(...)` → implies plaintext in production. | Introduce `EncryptedString` TypeDecorator in `db/types.py` wrapping Fernet. Apply to all 6+ PII columns. For email (searchable, unique), replace the unique index with an HMAC-SHA256 `email_hash` column + index. Write backfill migration. Replace `.ilike` with HMAC lookup. | L | DB + GDPR | 04, 05 |
| C2 | P0 | `db/models.py:226` | `Customer.email` is `unique=True, index=True` — incompatible with non-deterministic Fernet. | Part of C1: drop unique index on ciphertext; make `email_hash` unique instead. | S | DB | 05 |
| C3 | P0 | `db/models.py:2039`, `api/routers/valuations.py` | Insurance `appraised_value` stored as plain `Float`. CLAUDE.md mandates encryption. | Add `appraised_value_encrypted` String + `appraised_value_hmac` for searches (if needed). Route writes/reads through `core/encryption.py`. Deprecate plaintext column in a follow-up migration. | M | DB + GDPR | 04 |
| C4 | P0 | `src/goldsmith_erp/services/customer_service.py:279-315` | `_encrypt_pii` / `_decrypt_pii` catch `Exception` and silently keep plaintext. Violates CLAUDE.md "fail loudly". Misconfigured `ENCRYPTION_KEY` ⇒ plaintext persisted. | Raise `EncryptionError` on encrypt failure when encryption is required. Add a startup health check: if `ENCRYPTION_KEY` unset AND any non-deleted customer row exists, log CRITICAL + refuse to serve customer endpoints (503). | S | GDPR | 04 |
| C5 | P0 | `core/permissions.py:175-199`; `models/order.py:294-344`; `api/routers/orders.py:20-30` | VIEWERs see all financial fields on orders (`price`, `material_cost_*`, `labor_cost`, `hourly_rate`, `profit_margin_percent`, `calculated_price`). CLAUDE.md: "Financial data → visible only to ADMIN and GOLDSMITH". | Mirror `scanner_service.py:176 ORDER_FIELDS_BY_ROLE` pattern. Introduce `OrderReadViewer` Pydantic model stripped of financial fields, or project fields in the service layer based on `current_user.role`. | M | BE + GDPR | 04 |
| C6 | P0 | `api/routers/invoices.py`, `api/routers/valuations.py`, `api/routers/scrap_gold.py` — all GET handlers | Financial-data reads NOT audit-logged. CLAUDE.md: "All financial data access MUST be audit-logged". | Add an `audit_access(entity, entity_id)` FastAPI dependency wired into every financial-read endpoint. Row: `action="financial_read"`, `user_id`, `entity`, `entity_id`, `ip`, `timestamp`. Consider a service-layer decorator so future endpoints can't forget. | M | BE + GDPR | 04 |

### Group D — GDPR lifecycle correctness

| ID | Severity | File:line | Issue | Fix | Effort | Owner | Origin |
|----|----------|-----------|-------|-----|--------|-------|--------|
| D1 | P0 | `src/goldsmith_erp/db/repositories/customer.py:464-535` | `update_consent` writes `consent_marketing`, `email_communication_consent`, … — **none of these columns exist** on `Customer` (db/models.py:214-276). Runtime `AttributeError` for any call. No working consent storage → marketing/reminder features have no legal basis. | EITHER (a) add a migration for the consent columns (also referenced in `docs/GDPR_COMPLIANCE.md §3.1`) + a `customer_consents` audit table, OR (b) delete the dead code and surface a 501 "consent not implemented". (a) is the only GDPR-compliant path if any opt-in feature ships. | L | DB + GDPR | 04 |
| D2 | P0 | `scripts/gdpr-cleanup.sh:66-85` | 30-day hard-delete cron calls `db.delete(customer)` only — no re-run of `FileErasureService`, no audit row written, no `gdpr_requests` status update. If files failed at initial erasure, they're orphaned forever. Post-delete FK is gone so no trace left. | Rewrite: (1) re-run `FileErasureService.erase_customer_files` before delete, (2) block hard-delete if files still fail, (3) write `CustomerAuditLog` row (`action='gdpr_hard_delete'`) BEFORE the delete, (4) update matching `gdpr_requests` row to terminal status. | M | GDPR | 04 |
| D3 | P0 | `src/goldsmith_erp/api/routers/time_tracking.py:115-135` | `GET /time-tracking/user/{user_id}` has an ownership check but no `@require_permission`. Violates CLAUDE.md "All new endpoints must have @require_permission". | Add `@require_permission(Permission.TIME_VIEW_OWN)` above the decorator stack; ownership/`TIME_VIEW_ALL` fallback stays inside the handler. | S | BE + SEC | 01 |

### Group E — Money precision (the big one)

| ID | Severity | File:line | Issue | Fix | Effort | Owner | Origin |
|----|----------|-----------|-------|-----|--------|-------|--------|
| E1 | P0 | `db/models.py:381,413,416,418,419,422-424,433,566,813,815,858-859,933,1266,1268-1269,1322,1325,1401,1403-1404,1454-1455,2039,2194` (28 columns) + `alembic/versions/20260406_add_audit_gdpr_order_items_status_history.py:161` | Money as `Float` across Order / Invoice / Quote / Valuation / MetalPurchase / OrderItem / Gemstone. Rounding drift on every multiply; blocks HGB §257 audit reconciliation. | Migrate all EUR columns to `Numeric(12, 2)`, weights to `Numeric(10, 3)`, percentages to `Numeric(5, 2)`. One batch migration with `ALTER TABLE ... ALTER COLUMN ... TYPE numeric USING CAST(col AS numeric)`. Update Pydantic models to `Decimal` with `Field(max_digits=..., decimal_places=2)`. Coordinate with frontend: parse as string to avoid float round-trip. Add invoice reconciliation sanity check on existing rows. | L | DB + BE + FE | 01, 05 |

### Group F — CI / test integrity

| ID | Severity | File:line | Issue | Fix | Effort | Owner | Origin |
|----|----------|-----------|-------|-----|--------|-------|--------|
| F1 | P0 | `tests/conftest.py:33` + `tests/integration/conftest.py:42`; `.github/workflows/ci.yml` | Test suite hard-codes `sqlite+aiosqlite`. CI's PG service is used only for `alembic upgrade`. `test_concurrent_metal_consumption.py` FIFO/LIFO race test is `skipif(sqlite)` → silently skipped. | Honor `TEST_DATABASE_URL` env var in both conftests. Add a `postgres-integration` CI job that sets `TEST_DATABASE_URL=postgresql+asyncpg://...` and runs the integration suite against real PG. Keep SQLite for fast unit tests. | M | CI | 06 |
| F2 | P0 | `.github/workflows/ci.yml` (absent step) | No Alembic upgrade→downgrade→upgrade smoke test. Commit `263fd45` notes "3 real bugs caught by smoke-test against fresh PG" that would have been caught pre-merge by this. | Add CI step: `alembic upgrade head && alembic downgrade base && alembic upgrade head` against the PG service. Fail on any error. | S | CI | 06 |
| F3 | P0 | `.github/workflows/ci.yml` (absent step) | 4 Playwright E2E specs committed (`smoke`, `auth`, `goldsmith-workflow`, `goldsmith-full`), **0 run in CI**. `playwright.config.ts` is configured. | Add `test-e2e` job: services postgres+redis; install + `alembic upgrade head`; start backend+frontend; `yarn install && npx playwright install --with-deps && yarn e2e`. Consider nightly-only if wall-time is an issue. | M | CI + FE | 06 |
| F4 | P0 | `tests/test_basic_setup.py:52,62,95,109,132` + `tests/test_customer_repository.py:25` + `tests/test_customer_gdpr.py:23` | 7 encryption/GDPR tests permanently skipped with reason "pending GDPR schema migration" — schema shipped weeks ago. `test_encryption_key_configured`, `test_encryption_decrypt` hide whether encryption is wired at runtime. | Un-skip and fix imports, or delete if truly superseded. Align with C1–C4. | S | CI + GDPR | 06 |

---

## P1 — Correctness / perf / soon-to-bite

Grouped by theme, each block ≈ 1–3 days of focused work.

### P1.1 — Transaction & event integrity

| ID | File:line | Issue | Fix | Effort | Origin |
|----|-----------|-------|-----|--------|--------|
| 1.1a | `services/time_tracking_service.py:99-139, 141-191, 363-390, 417-429, 431-456, 700-779, 781-868` | 7 mutating methods use bare `db.commit()` without `async with transactional(db)` — inconsistent with `OrderService`. Auxiliary updates (`increment_usage`) can fail after primary commit. | Wrap all multi-step writes in `async with transactional(db)` (helper exists at `db/transaction.py`). | M | 01 |
| 1.1b | `services/notification_service.py:86-120` + order/time_tracking callers | `create_notification` calls `db.commit()` unconditionally, then blocks on synchronous SMTP. When called from inside another service's `transactional()`, the inner commit terminates the outer transaction early. | Add `commit: bool = True` flag (or prefer `flush`-only + caller-owned commit). Move SMTP to `BackgroundTasks` / asyncio task. | M | 01 |
| 1.1c | `services/time_tracking_service.py:889-913` | Structurally dead branch: `publish_event` never raises, so A5.5 compensation code on lines 920-954 can never execute. Docstring lies. | Make `publish_event` return `bool`; consume it, OR remove the dead branch and update the docstring. | S | 01 |
| 1.1d | `services/handoff_service.py:196-215`, `repair_service.py:192, 248`, `metal_inventory_service.py:608` | Silent drop of events after 3 Redis retries. Only `order_service` has the A5.4/A5.5 compensation path. | Lift `_safe_publish_order_event` to a shared helper; or add an `outbox_events` table flushed by a background task. | M | 08 |

### P1.2 — Async-correctness / blocking I/O

| ID | File:line | Issue | Fix | Effort | Origin |
|----|-----------|-------|-----|--------|--------|
| 1.2a | `api/routers/materials.py:359`, `api/routers/scrap_gold.py:175`, `services/photo_service.py:175, 188` | Blocking sync I/O in async handlers: `Path.write_bytes()` for multi-MB uploads + PIL thumbnailing on the event loop. Stalls every other coroutine (incl. WebSocket sender). | Wrap filesystem writes in `anyio.to_thread.run_sync(...)`; move PIL to `run_in_executor`. Or use `aiofiles.open('wb')`. | M | 01 |
| 1.2b | `main.py:213-217` | Deprecated `@app.on_event("startup")` + no matching shutdown → `system_monitor_loop` never cancelled → traceback on shutdown + leaked DB/Redis handles. Deprecated since Starlette 0.26 / FastAPI 0.93. | Migrate to `lifespan` `@asynccontextmanager` that spawns + `asyncio.wait_for`-cancels the task on exit. | S | 01, 07 |
| 1.2c | `services/system_monitor.py:316-329` | Tuple of eager coroutines — if one iteration raises `CancelledError`, remaining coroutines never awaited → `RuntimeWarning` + leaked queries. | Replace tuple-of-coroutines with tuple-of-callables; call each inside the loop. | S | 01 |
| 1.2d | `db/session.py:3, 32-38` | `sessionmaker` (sync) imported instead of `async_sessionmaker` from SQLAlchemy 2.0. Works, but mypy strict can't verify `await session.execute`. | `from sqlalchemy.ext.asyncio import async_sessionmaker` + `AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)`. | S | 01 |

### P1.3 — WebSocket scaling & drift

| ID | File:line | Issue | Fix | Effort | Origin |
|----|-----------|-------|-----|--------|--------|
| 1.3a | `main.py:164-210` + `core/pubsub.py:60-75` | One Redis pubsub connection per connected WebSocket client. N clients → N subscribers → saturates default pool at ~50 concurrent users. | Single process-level `ConnectionManager` with one Redis subscriber per channel; `{channel: set[WebSocket]}` in-memory fanout. Cap concurrent connections per user (e.g. 5). Close all sockets on graceful shutdown. | L | 01, 08 |
| 1.3b | `main.py:152-154` | WebSocket auth accepts `?token=<jwt>` query-param fallback. Leaks into proxy logs + browser history. Frontend is cookie-based now; fallback is vestigial. | Drop the query-param branch. Cookie auth on WS upgrade already works. Non-browser clients can use `Sec-WebSocket-Protocol: bearer, <token>` per RFC 6455. | S | 03, 08 |
| 1.3c | `frontend/src/contexts/TimeTrackingContext.tsx:338-341` + `frontend/src/components/NotificationBell.tsx:152-155` | TWO concurrent WebSockets per user to same URL. | Hoist a single `WebSocketProvider`; each consumer registers `onMessage`; socket is a shared per-user singleton. | M | 02 |
| 1.3d | `frontend/src/hooks/useWebSocket.ts` + contexts | No on-reconnect refetch hook. After disconnect+reconnect, each context shows stale data until a user action refetches. | Add `onReconnect` callback to the hook; `AuthContext` / `OrderContext` call `refetch*()` on reconnect. | S | 08 |

### P1.4 — Auth & rate-limiting

| ID | File:line | Issue | Fix | Effort | Origin |
|----|-----------|-------|-----|--------|--------|
| 1.4a | `core/config.py` + `api/routers/auth.py` | 7–8 day access-token lifetime, no server-side blocklist on logout, no password-change invalidation, no MFA. Stolen JWT valid for a week. | Shorten access-token to ~30 min; implement real refresh-token rotation (current code treats access ≈ refresh); `jti` + Redis blocklist consulted by `AuthRequiredMiddleware`. Bump all active tokens on password change. | L | 03 |
| 1.4b | `api/routers/customer_portal.py:360-380` | Public `/portal/lookup` rate-limited 10/min/IP but order references are numeric auto-increment — LAN-pool brute-force is feasible. | Replace numeric IDs with random opaque tokens (e.g. `ORD-` + 12 urlsafe chars) in a new column. Tighten to 3/min/IP + 10/hour per reference. Add per-reference failure counter w/ exp backoff. | M | 03 |
| 1.4c | `api/routers/orders.py:24`, `users.py:133`, `materials.py:52`, `time_tracking.py:96, 121`, `comments.py:21`, `activities.py:22` | 7+ list endpoints have unbounded `limit: int = 100` → cheap DoS via `?limit=99999999`. | Add `Query(default=100, ge=1, le=200)` (pattern already at `invoices.py:79`). | S | 03 |
| 1.4d | `api/routers/auth.py:26, 91`, `customer_portal.py:365` | Rate limits only per-IP → workshop router NAT locks out whole office. | Switch `slowapi` key_func to `(ip, username)` on login, `(ip, reference_number)` on portal. | S | 03 |
| 1.4e | `middleware/security_headers.py:26` | `Permissions-Policy: camera=()` will break V1.1 scanner once SPA is served from the same origin. | Change to `Permissions-Policy: camera=(self), microphone=(), geolocation=()`. | S | 03 |
| 1.4f | `main.py:86-88` | `/docs`, `/redoc`, `/openapi.json` public in production → leaks full API surface + permission taxonomy. | Gate with `if settings.DEBUG` or `openapi_url=None` in prod; serve from an admin-LAN-only port if needed. | S | 03 |

### P1.5 — Database correctness & performance

| ID | File:line | Issue | Fix | Effort | Origin |
|----|-----------|-------|-----|--------|--------|
| 1.5a | `services/notification_service.py:268-315, 454-502, 551-566` | N+1 in deadline/pickup/stock scanners (orders × target_users inner `SELECT` per pair). 250 round-trips per scan cycle at 50 orders × 5 users, every 5 minutes. | Batch: one `SELECT` returning all relevant pairs, `set[(order_id, user_id)]` for local lookup. | M | 05 |
| 1.5b | `db/models.py:174-176, 625, 757, 775` | FKs without explicit `ondelete` on `order_materials`, `TimeEntry.activity_id`, `LocationHistory.order_id`, `OrderPhoto.order_id` — missed by the H9 migration. | Decide per-table: CASCADE for association rows, RESTRICT for audit rows. Follow-up migration mirroring H9 for non-user FKs. | M | 05 |
| 1.5c | `services/notification_service.py:336, 346, 428` | `result.scalars().all()` with no `.limit()` on completed-orders / low-stock scans → loads everything into memory per 5-min tick. | Add `.limit(500)` safety cap or `.yield_per(100)` for streaming. | S | 05 |
| 1.5d | `db/models.py:2183-2221, 2129-2175, 2159-2175` | `OrderItem`, `OrderStatusHistory`, `CustomerAuditLog`, `GDPRRequest` use naive `DateTime` (no `timezone=True`). Slice 2 tables use tz-aware. Mixing breaks comparisons. | Migrate audit-column timestamps to `DateTime(timezone=True)`; normalize existing data to UTC. | M | 05 |
| 1.5e | `db/models.py:183-186, 379-380, 564-568` | Unbounded `Column(String)` → PostgreSQL TEXT (no length cap). Attacker can POST 100 MB strings that slip past Pydantic if raw ORM add is ever used. | Bound: `String(254)` email (RFC 5321), `String(255)` names, deliberate `Text` for descriptions. | S | 05 |
| 1.5f | `db/models.py:2294-2298, 611` | `ScanLog.id` and `TimeEntry.id` are `String(36)` at ORM level but PG migration creates them as native `UUID`. Equality against `uuid.UUID` silently fails. | Use `sa.dialects.postgresql.UUID(as_uuid=True)` at ORM level. | S | 05 |
| 1.5g | `db/models.py:381-487` | No index on `Order.status` despite being the primary filter for dashboards + scanners. | Add `Index("ix_orders_status", Order.status)` + composite `(status, is_deleted)`. | S | 05 |

### P1.6 — GDPR completeness

| ID | File:line | Issue | Fix | Effort | Origin |
|----|-----------|-------|-----|--------|--------|
| 1.6a | `docs/GDPR_COMPLIANCE.md §3.4` + `db/models.py:474, 661, 966, 2325` | `retention_class` tagged on rows but no enforcement engine anywhere. Storage Limitation (Art. 5(1)(e)) not demonstrable. | Implement `services/retention_engine.py` with one method per bucket (`purge_standard_24m`, `purge_hallmark_10y`, `purge_indefinite_business` → no-op). Makefile target. Cron next to `gdpr-cleanup.sh`. Every run writes one summary `CustomerAuditLog` row. | L | 04 |
| 1.6b | `api/routers/customers.py:243-351` | GDPR export emits `order.description` (design IP) unconditionally. CLAUDE.md forbids without explicit consent. | Add `include_design_ip: bool = False` query param + consent gate. Default: redact `description`, `special_instructions`, `preferences`, photo refs. | S | 04 |
| 1.6c | `api/routers/photos.py:101-128`; `core/permissions.py:175-199` | VIEWERs can list/download order photos. CLAUDE.md: design IP = GOLDSMITH/ADMIN only. | Introduce `PHOTO_VIEW` permission granted only to GOLDSMITH+ADMIN; wire the 3 photo endpoints. Same for `RepairPhoto`. | S | 04 |
| 1.6d | `api/routers/scrap_gold.py:51, 118, 197` | Altgold gated by `ORDER_VIEW`/`ORDER_EDIT`. CLAUDE.md: scrap gold = same protection as pricing. | Add `SCRAP_GOLD_VIEW/CREATE/EDIT`; grant only to ADMIN+GOLDSMITH. Audit-log every read (same work as C6). | S | 04 |
| 1.6e | `db/models.py:1070, 1407`; `services/scrap_gold_service.py:141-148` | Customer signatures (base64 PNG) stored plaintext. Biometric-adjacent personal data. | Route through encryption service (extend PII encryption list to include `signature_data`, `customer_signature_data`), or move to file-backed store referenced by `FileErasureService`-compatible path. | M | 04 |
| 1.6f | — (absent entirely) | No data-breach-notification infrastructure (GDPR Art. 33/34). `docs/GDPR_COMPLIANCE.md §6.4` proposed a `DataBreach` model that was never created. DPO cannot hit the 72-hour deadline without one. | Add `DataBreach` table + `/admin/breaches` endpoint + email template for supervisory-authority notification + runbook entry. | M | 04 |
| 1.6g | `api/routers/customers.py:460-707` | Erasure request requires `CUSTOMER_DELETE` (admin only). Art. 17 does not require admin mediation. | Add `POST /portal/gdpr-request` (rate-limited, verification-token) that files a `GDPRRequest` row + notifies ADMIN role. | M | 04 |

### P1.7 — Frontend quality & UX

| ID | File:line | Issue | Fix | Effort | Origin |
|----|-----------|-------|-----|--------|--------|
| 1.7a | `frontend/src/api/client.ts:76-134` | Refresh-on-401 → `window.location.href = '/login'` loses all unsaved form state. | After refresh failure, set React state flag + use `Navigate replace`. Add `beforeunload` guard for dirty forms. Session-expired modal preserves draft in memory. | M | 02 |
| 1.7b | `frontend/src/contexts/TimeTrackingContext.tsx:242-249` | 5-second polling on top of WebSocket push → re-render bomb across 5 consumer trees (MainLayout, TimerWidget, ActiveTimerWidget, ScanFab, every page). | Drop polling (trust WS + reconnect); or raise to 30s; or shallow-compare and skip `setRunningEntry` when unchanged. | S | 02 |
| 1.7c | `frontend/src/components/TimerWidget.tsx:131-147`, `ActiveTimerWidget.tsx:173-176, 227-229`, `TimerWidget.tsx:198-199` | 40+ `catch (err: any)` + German-copy string matching (`'bereits gestoppt'`, `'bereits eine laufende'`). Backend text change breaks client. | Backend emits structured error codes (`TIMER_ALREADY_STOPPED`, `TIMER_ALREADY_RUNNING`) — pattern already exists at `TimeTrackingContext.tsx:218-228` (`TIMER_POSSIBLY_STALE`). Match on `code`, promote `extractErrorInfo` (`ActionHandlers.ts:134-172`) to `api/errors.ts`, replace all `err: any`. | M | 02 |
| 1.7d | `frontend/src/components/CustomerFormModal.tsx:263` + 11 other modals | Modals lack `role="dialog"`, focus trap, Esc handler. Outside-click dismiss with no unsaved-state guard. A11y violation + data loss. | Promote to shared `<Modal>` primitive (pattern from `QuickActionModalV2.tsx:287-317`): `aria-modal="true"`, focus trap, Esc, restore focus, dirty-form prompt. | M | 02 |
| 1.7e | `frontend/src/components/OrderList.tsx:37-40` | Status rendering hard-codes 4 of 10 `OrderStatus` enum values; 6 render as empty badge. | `STATUS_LABEL: Record<OrderStatus, string>` lookup (pattern at `QuickActionModalV2.tsx:176-188`). TS enforces exhaustiveness. | S | 02 |
| 1.7f | `frontend/src/components/scanner/QrCameraScanner.tsx:305-322` + `vite.config.ts:17` | `playAudio` silently swallows `el.play()` rejection. `mp3` NOT in PWA precache globs → sounds unavailable offline. Workshop users get no feedback. | Log on first rejected play; degrade to `navigator.vibrate` + visual flash as primary feedback; add `mp3` to `globPatterns`. | S | 02 |

### P1.8 — Architectural hygiene

| ID | File:line | Issue | Fix | Effort | Origin |
|----|-----------|-------|-----|--------|--------|
| 1.8a | `services/*_service.py` (70+ call sites) | Services raise `HTTPException` directly. Couples to HTTP; `ValueError` becomes raw 500. | Introduce `DomainError` hierarchy (`NotFoundError`, `ConflictError`, `ValidationError`, `PermissionError`). Services raise those. One `@app.exception_handler` per family. | M | 08 |
| 1.8b | `core/config.py` (no `FEATURE_*`) | No feature flags / kill switches. Scanner in V1.1 live with no runtime toggle — rollback = redeploy. | Add `FEATURES: dict[str, bool]` to `Settings`; `require_feature()` FastAPI dependency; gate `api/routers/scanner.py` + `ml.py`. | S | 08 |
| 1.8c | `middleware/request_metrics.py:30-58` | Metrics live only in memory → die on restart. No `/metrics` endpoint, no Sentry, no OpenTelemetry. | Expose `/metrics` Prometheus endpoint (`prometheus_client` trivial); add Sentry DSN; OpenTelemetry if tracing becomes a need. | M | 08 |
| 1.8d | `db/models.py` (2,435 LOC, 64 classes) | Monolithic ORM module, maximum fan-in. V1.2 multi-tenancy migration will be painful without a split. | Split into `db/models/{user,customer,order,material,time_tracking,scanner,gdpr,hallmark,valuation}.py` + flat re-export in `__init__.py` for back-compat. | M | 08 |
| 1.8e | `core/permissions.py:239-262, 284-307, 329-355, 377-397` | `@require_permission` extracts `current_user` via `kwargs.get('current_user')` — silently degrades to None if a dev ever passes positionally or renames. | Convert to FastAPI dependency factory (like the one in `api/deps.py`); keep decorator form as a thin shim for non-route callers. | S | 01 |
| 1.8f | `api/deps.py:15`, `api/routers/auth.py:26`, `main.py:148-160` | JWT extraction duplicated in 3 places with subtly different rules. | Extract one `extract_bearer_token(request_or_websocket)` in `core/security.py`; call from all three. Test same input → same extraction. | S | 01 |

### P1.9 — Dependency bumps (non-runtime-blocking CVEs)

| ID | Dep | From → To | CVE | Effort | Origin |
|----|-----|-----------|------|--------|--------|
| 1.9a | `urllib3` (transitive) | 2.5.0 → ≥ 2.6.3 | CVE-2025-66418, CVE-2025-66471, CVE-2026-21441 (compression-bomb DoS) | S | 07 |
| 1.9b | `pillow` | 12.1.1 → 12.2.0 | CVE-2026-40192 FITS decompression bomb (image upload is user-reachable) | S | 07 |
| 1.9c | `python-multipart` | 0.0.18 → 0.0.20 | CVE-2026-40347 preamble/epilogue DoS | S | 07 |
| 1.9d | `python-jose` + `ecdsa` | remove | ecdsa CVE-2024-23342 (Minerva, WON'T FIX upstream); python-jose effectively unmaintained. **pyjwt already a direct dep.** | S | 07 |
| 1.9e | `vite` | 7.3.1 → 7.3.2 (or 8.0.5) | GHSA-v2wj-q39q-566r (`fs.deny` bypass) + GHSA-p9ff-h696-f583 (dev-server arbitrary file read) — dev-only but HIGH | S | 07 |
| 1.9f | `passlib` | 1.7.4 → migrate off | Abandoned upstream (last release 2020); blocks bcrypt 5.x. Move to direct `bcrypt` or `pwdlib`. | M | 07 |
| 1.9g | `cryptography` | 44.0.3 → 46.0.7 | Two major versions behind; missing hardening | S | 07 |

### P1.10 — Testing gaps

| ID | File:line | Issue | Fix | Effort | Origin |
|----|-----------|-------|-----|--------|--------|
| 1.10a | `tests/integration/` | No integration tests for `time_tracking` lifecycle (only `/switch` covered), `users`, `invoices`, `notifications`, `materials`, `photos`, `scrap_gold`, `comments`, `calendar`, `handoffs`. 10 routers, 0 integration coverage. | Prioritize time_tracking full lifecycle, users (role, password), invoices (PDF + permission), notifications. | L | 06 |
| 1.10b | `tests/integration/test_websocket_auth.py:36-38` + `tests/integration/conftest.py:130-132` | WS tests mock `subscribe_and_forward`; no test of publish→forward→WS-client delivery path. | Add fakeredis-backed integration test asserting a published event reaches a WS client. | M | 06 |
| 1.10c | `.github/workflows/ci.yml` (absent) | No `pip-audit` / `yarn npm audit` / Dependabot in CI. `pip-audit` is a dev dep already. | Add `security-audit` job: `poetry run pip-audit` + `yarn npm audit --severity high`. | S | 06 |
| 1.10d | `.github/workflows/ci.yml:30-41` + `pyproject.toml:74-76` | `mypy --ignore-missing-imports` in CI neuters `strict = true` from pyproject. | Drop the flag; add missing type stubs to dev deps. | S | 06 |
| 1.10e | `Makefile:125-128` | `make test` skips `--cov-fail-under=50`; local run ≠ CI coverage gate. | Make `test-cov` mirror CI invocation. | S | 06 |
| 1.10f | `frontend/` (absent) | No ESLint / Prettier. Pre-commit has no frontend hook. | Add `eslint.config.js` (flat) with `@typescript-eslint`, `eslint-plugin-react-hooks`; wire into CI + pre-commit. | S | 06 |

---

## P2 — Housekeeping, code smells, doc drift

Too many to enumerate per-line here (60+ items across agent reports). Grouped by theme for tracking:

- **Pydantic v2 drift**: `.dict()` → `.model_dump()` in `services/order_service.py:180, 297`; legacy `class Config:` in `models/customer.py`, `models/measurement.py` — 07.
- **Money → Decimal in Pydantic**: `models/order.py:37-41, 158-162, 323`, `models/invoice.py:42, 65` (frontend must parse as string) — 01. Complements E1.
- **Error leakage**: `api/routers/health.py:81, 97, 127, 136, 162, 169` — verbose DB connection errors to response body; `api/routers/metal_inventory.py` — broad `except Exception` → info disclosure — 01, 03.
- **CSP / security headers**: tighten `connect-src 'self'`, add `base-uri 'self'`, `form-action 'self'`, `HSTS`, `COOP`, `CORP` — 03.
- **Legacy compose / Dockerfile duplicates**: `Dockerfile` + `docker-compose.yml` still in repo after Podman became canonical; runs `curl|python3 -` as root — 03, 07. Delete if unused.
- **Tooling pins**: `Containerfile` Poetry unpinned (add `poetry>=2,<3`); `Redis 7-alpine` unpinned (pin `7.4-alpine`); `.python-version` 3.11.5 — plan 3.12/3.13 bump before EOL 2027-10-31 — 07.
- **SQLAlchemy 2.0 legacy style**: `db/models.py` entirely on `Column` / `relationship` / `declarative_base()`. No `Mapped[]` / `DeclarativeBase`. Plan before SA 2.1/3.0 — 07.
- **`db/seed_data.py` not DEBUG-guarded**: risk of running in prod — 05.
- **Large single-file services**: `scanner_service.py` 1367, `pdf_service.py` 1183, `customer_service.py` 1125, `time_tracking_service.py` 981, `api/routers/ml.py` 843 — split by subdomain — 08.
- **`CustomerAuditLog` gaps**: no retention class of its own; `user_id` lacks index; `user_email` re-identifies after anonymisation — 04.
- **GDPR doc drift**: `docs/GDPR_COMPLIANCE.md` (2025-11-06) lists models + columns that don't exist; contradicts current code — 04.
- **Router → SQLAlchemy direct imports**: 12 routers (`materials.py:98-143`, `metal_types.py:243-350`, etc.) bypass the service layer — 01.
- **Type-duplication between FE and BE**: `frontend/src/types.ts` (1069 LOC, hand-maintained) drifts from Pydantic schemas; adopt `openapi-typescript` / `orval` — 02.
- **`ActiveTimerWidget` appears orphaned** (0 imports) — 460 LOC dead code — 02.
- **CI performance**: no `actions/setup-*` cache for Poetry/Yarn; `python-version` / `node-version` not matrixed — 06.
- **Ruff in pre-commit but not in CI** — 06.
- **`.gitleaks.toml` allowlist too broad** (entire `tests/`, `.github/workflows/`) — 06.
- **Legacy `alembic_backup/env.py`** references non-existent `settings.database_url` — delete — 05.
- **`v1_initial` migration uses `Base.metadata.create_all()` with hardcoded blocklist** of post-V1.1 tables — fragile against future table additions — 05.

Full P2 detail lives in the per-agent reports — each row in this list maps back to a concrete `file:line` there.

---

## Suggested sequencing

1. **Week 1** — Groups A, B, F (config wiring, CVE bumps, CI PG + downgrade smoke). All short, high-value, largely independent.
2. **Week 2** — Group C (PII encryption foundation + financial role projection + audit-log dependency). Unblocks multiple GDPR P0s.
3. **Week 2–3** — Group D (GDPR lifecycle) + P1.6 consent/retention/breach scaffold. Can parallelize with Group C once the encryption plumbing lands.
4. **Weeks 3–5** — Group E (Money→Numeric). Biggest single change; needs frontend coordination.
5. **Weeks 3–6** — P1.1–P1.10 in parallel streams owned per-sub-team.
6. **Backlog** — P2 tech-debt; fit into feature weeks, no dedicated sprint.

Most P0s are S or M effort; the two L items (C1 PII encryption, E1 Money→Numeric) dominate the timeline.

**No code has been modified in this review.** The next action is your call on sequencing and ownership.
