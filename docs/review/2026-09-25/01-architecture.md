# Review 01: Architecture (UX/ERP audit, 2026-09)

- **Reviewer:** Henrik Lindqvist (technical lead persona), read-only
- **HEAD:** `main` @ `73fff19` (last commit 2026-07-26)
- **Scope:** the big picture: layering, domain model, real-time/async, API design, frontend architecture, deployment/operability, extensibility toward the product goal, and a comparison with current practice. I did not repeat line-level security, correctness, frontend-code, testing/CI or GDPR findings; where one of those matters here I point to the sibling review.
- **Method:** I read the prior reviews first. Then I measured with `wc -l`/`grep -c`, traced the order lifecycle end to end (ORM, service, router, React page), checked the wiring in `main.py`, the compose and systemd files, and the frontend build config, and re-checked every prior finding against the current code.
- **Files examined:** about 70 files directly (backend 44, frontend 14, deploy/compose/config 8, docs 6), plus repo-wide greps over `src/goldsmith_erp/**` (about 39.5k LOC in services/routers/models) and `frontend/src/**` (about 39.8k LOC).

Size snapshot (`wc -l`):

| File | LOC | Note |
|---|---|---|
| `src/goldsmith_erp/db/models.py` | 3245 | 79 top-level classes, 547 `Column(`, 0 `Mapped[` |
| `services/customer_service.py` | 1856 | CRM + GDPR export/erasure + search |
| `services/pdf_service.py` | 1483 | every PDF type in one module |
| `services/scanner_service.py` | 1305 | |
| `services/time_tracking_service.py` | 1116 | |
| `api/routers/customers.py` | 1066 | GDPR endpoints mixed into CRM router |
| `services/file_erasure_service.py` | 1031 | |
| `services/quote_service.py` | 985 | |
| `api/routers/ml.py` | 914 | |
| `frontend/src/types.ts` | 1285 | hand-written API types |
| `frontend/src/pages/QuotesPage.tsx` | 1277 | |

There are 44 service modules, 36 routers and 243 route handlers. The backend has 113 test files and the frontend has 48.

---

## A. Status of prior architecture findings

Sources: **BA** = `docs/review/2026-04-23/01-backend-architecture.md`, **AR** = `docs/review/2026-04-23/08-architectural-reasoning.md`, **PR** = `docs/review/2026-07-26/production-readiness.md`, **OLD** = `docs/technical/architecture/ARCHITECTURE_REVIEW.md` (2025-11).

| Source / id | Finding | Status | Evidence |
|---|---|---|---|
| BA P0-1 | Two parallel RBAC systems | **fixed** | `api/deps.py` (110 LOC) has no `Permission`/`ROLE_PERMISSIONS`; single source at `core/permissions.py:18,166` |
| BA P0-2 | Audit middleware not registered | **fixed** | `main.py:148-150` |
| BA P1 | `require_permission` reads `kwargs['current_user']` | **partial** | the decorator still does this (`core/permissions.py:307-309`); a `require_permission_dep` factory now exists (`core/permissions.py:332`) but most routes use the decorator (179 decorator sites vs 39 `Depends/dependencies=`) |
| BA P1 | `NotificationService.create_notification` commits inside caller transaction + sends SMTP inline | **open** | `services/notification_service.py:100` `await db.commit()`, then customer email at `:107-113` |
| BA P1 | Blocking sync file I/O in async handlers | **open** | `photo_service.py:135`, `repair_photo_service.py:132`, `consultation_photo_service.py:127`, `api/routers/scrap_gold.py:221`, `api/routers/materials.py:370` (`write_bytes`, no `to_thread`) |
| BA P1 / AR-B | `@app.on_event("startup")`, no lifespan, background task never cancelled | **open** | `main.py:356-360`, `main.py:363` |
| BA P1 / AR-B | One Redis pubsub connection per WebSocket | **open** | `main.py:310`, `main.py:339`; `core/pubsub.py:60-75` |
| BA P1 | `system_monitor` tuple of eagerly created coroutines | **open** | `services/system_monitor.py:316-321` |
| BA P1 | `sanitize_text` SQL keyword blocklist rejects legitimate text | **open** | `models/order.py:59-71` |
| BA P1 | `_safe_publish` dead branch (publish never raises) | **open** | `services/time_tracking_service.py:929-947` vs `core/pubsub.py:42-57` |
| BA P1 | `sessionmaker` instead of `async_sessionmaker` | **open** | `db/session.py:3,49` |
| BA P2 | Routers issue SQL directly | **open, grew** | 32 router files import `sqlalchemy`; 60 `db.execute/commit` calls in `api/routers/` |
| BA P2 | Pydantic v1 `.dict()` | **open** | `services/order_service.py:324` |
| BA P2 | Money as `float` | **open** (see backend-correctness review) | `db/models.py:460` `price = Column(Float)`; `:1886-1887` repair costs |
| BA P2 | Health endpoints echo exception text | **open** (see security review) | `api/routers/health.py:83,99,128` |
| AR-C/D | Services raise `HTTPException`; no domain-error mapping | **partial** | down to 42 raises in 5 service files. There is now a per-service `ValueError` hierarchy (`quote_service.py:90-113`, `consultation_service.py:42-65`, `customer_update_service.py:107-162`), but some errors still subclass `HTTPException` (`order_service.py:41`, `time_tracking_service.py:45,69`, `metal_inventory_service.py:85`). There is no global handler: the only one is `main.py:137`, and routers hand-map with 63 `except ValueError/...NotFoundError` blocks |
| AR-E | No feature flags / kill switches | **open** | `core/config.py` has no `FEATURE*` field |
| AR-J / PR 2.6 | In-memory metrics only; no Sentry/OTel/Prometheus | **open** | `middleware/request_metrics.py:30,33`; grep for `sentry|opentelemetry|prometheus` finds nothing |
| AR-H / PR T3 | WebSocket `?token=` query fallback | **open** (see security review) | `main.py:290` |
| AR-F | `db/models.py` monolith | **open, worse** | 2435 LOC/64 classes, now 3245/79 |
| AR-F | Large services (scanner, pdf, customer, time tracking, ml router) | **open, worse** | see size table |
| AR-G | No on-reconnect refetch in `useWebSocket` | **open** | no `onReconnect` in `frontend/src/hooks/useWebSocket.ts` |
| AR-A | No outbox; events lost after 3 retries | **open** | `core/pubsub.py:42-57` |
| AR-I | Single tenant, `User.tenant_id` slot only | **unchanged, by design** | `db/models.py:206` is the only `tenant_id` |
| PR 0.2 | Frontend prod container ran Vite dev server | **fixed** | `frontend/Containerfile.prod`; prod compose builds a static bundle behind nginx |
| PR 1.1 | No TLS / reverse proxy | **fixed** | `deploy/Caddyfile` (`tls internal`, on-demand LAN certs); backend `expose` only (`podman-compose.prod.yml` backend block) |
| PR 1.3 / 2.3 | GDPR cleanup / retention not scheduled | **fixed (wiring)** | `deploy/systemd/goldsmith-{gdpr-cleanup,retention-sweep,health-watchdog}.{service,timer}` + `jobs/*.py`. Whether it is correct is for the GDPR review |
| PR 2.7 | `/docs` public in prod | **fixed** | `main.py:124-130` |
| OLD 2.1 | Tokens in localStorage | **fixed** | HttpOnly cookie auth (PR "verified healthy") |
| OLD 2.2 | "Migrate Context to Zustand" | **obsolete** | the real gap is server-state caching, not a client store (ARCH-06) |
| OLD 1.3-1.5, 4.x, 6.1, 6.3 | Pool leak, N+1, transactions, validation, RBAC, structured logging, health checks | **fixed** | `core/pubsub.py:27-38`, `db/transaction.py`, `core/logging.py`, `api/routers/health.py` |
| OLD (whole doc) | | **obsolete** | stale since 2026-04. It should be archived so agents stop reading it as current (CLAUDE.md still says "READ THIS FIRST") |

Net: the April security P0s and the July deploy blockers are fixed. The structural findings (monolith models, transport-coupled services, per-socket pubsub, missing lifespan, no observability sink, no flags) are all still open, and the two coupling hotspots have grown about 30%.

---

## B. Current architecture as built

```
 Workshop LAN devices (desktop, tablet at bench, phone scanner)
        |  HTTPS (Caddy tls internal, on_demand)
        v
 +-------------+     +-------------------------------+
 | caddy :443  | --> | frontend nginx :3000          |  static SPA (React 18, RR7, 22 lazy routes, PWA/Workbox)
 +-------------+     |  /api /ws /uploads -> backend |
                     +---------------+---------------+
                                     v
 +-----------------------------------------------------------------------------+
 | backend: uvicorn --workers 2   (FastAPI, one process per worker)            |
 |  middleware: SecurityHeaders > CORS > Metrics(in-mem) > Logging > SizeLimit |
 |              > AuthRequired (deny-by-default) > AuditLogging (path table)   |
 |  36 routers (243 handlers) --- @require_permission decorator                |
 |     |  32 routers also run SQL directly                                     |
 |     v                                                                       |
 |  44 "service" modules = classes of @staticmethod (286) taking AsyncSession  |
 |     |  HTTPException / ValueError subclasses; transactional(db) or commit() |
 |     v                                                                       |
 |  db/models.py (79 classes, legacy Column style)   db/repositories/ (UNUSED) |
 |  core/: config, security(jose), encryption(Fernet+HMAC), pubsub, cache,     |
 |         idempotency, token_revocation, permissions                          |
 |  in-process: system_monitor_loop (every 5 min, per worker) -> Notification  |
 |              rows -> customer e-mail (aiosmtplib inline)                    |
 |  WS /ws/orders, /ws/notifications/{id}: 1 Redis SUBSCRIBE per socket        |
 +------+-------------------------+-----------------------+--------------------+
        v                         v                       v
  PostgreSQL 15             Redis 7 (64 MB LRU)      ./uploads (bind mount, local FS)
  (alembic upgrade head     pub/sub, portal tokens,  photos for order/repair/
   + reference_seed at      cache, idempotency,      consultation
   every boot)              jti revocation
        ^
  systemd timers on host: gdpr-cleanup, retention-sweep, health-watchdog (+ alert units)
  scripts/: backup.sh / restore.sh / rotate-secrets.sh (manual or cron)
```

Frontend: `pages/*` components each fetch through `frontend/src/api/*.ts` (axios, cookie auth, refresh interceptor) inside `useEffect`, and keep `isLoading`/`error` in local state (51 files with this pattern). Context is used for Auth, Order *tab state*, Scanner, Theme, TimeTracking and Toast. API types are hand-written in `types.ts`. zod is used only for form validation (`lib/validation/*`). WebSocket consumers are only `TimeTrackingContext.tsx:338` and `NotificationBell.tsx:152`.

Overall it is a layered monolith with correct security primitives. It works as a "layered", not a "modular", monolith: every domain reaches into one ORM module, and business rules are scattered between routers, services and the React pages.

---

## C. Findings

Ordered by impact on the product goal: keeping track of work and clients faster, and giving clients better feedback.

### ARCH-01 (HIGH): The order lifecycle is not modelled. Status is a free-form field, and status history is never written
- **Evidence:**
  - `OrderStatusEnum` (`db/models.py:47-63`) mixes commercial states (`draft`, `confirmed`, `delivered`), production steps (`waiting_for_fitting`, `ready_for_setting`) and a legacy `new`. Its own docstring describes a different pipeline ("Entwurf -> Guss -> Montage -> Fassung -> Oberflaeche -> QK").
  - Orders have no transition table. `OrderService.update_order` (`services/order_service.py:330-398`) applies whatever `status` the PATCH carries, with only two guards (Punzierung, confirmation fields). Repairs and hallmarks do have explicit `_VALID_TRANSITIONS` (`services/repair_service.py:99-113`, `services/hallmark_service.py:35`).
  - The UI offers every status as a button from any status (`frontend/src/pages/OrderDetailPage.tsx:457-468`).
  - `OrderStatusHistory` exists (`db/models.py:2938`), but its only writer is `db/repositories/order.py:593`, which no production code imports (ARCH-03). The order "Verlauf" tab renders two timestamps, `created_at` and `updated_at` (`OrderDetailPage.tsx:495-517`).
  - Status labels are defined three times with different wording: `customer_portal.py:49-60` ("Bereit zur Fassung", "Qualitaetskontrolle"), `OrderDetailPage.tsx:457-468` ("Bereit für Steinbesatz", "Endkontrolle"), and `getStatusLabel`.
- **Why it matters:** client feedback ("your ring moved to stone setting on Tuesday"), a kanban, cycle-time KPIs and the estimator's actuals all need a trustworthy stream of transitions. Today the system cannot answer "when did this order enter QC?" This is the biggest single gap between the architecture and the product goal.
- **Recommendation:**
  - Introduce an explicit order workflow module: a transition table plus guards (the pattern already exists for repairs).
  - Split *lifecycle status* (intake, quoted, approved, in_production, ready, handed_over, invoiced, closed) from *production stage* (an optional, configurable list of workshop stations).
  - Make every transition write an `order_events` row (`order_status_history`, generalized) in the same transaction.
  - Expose `GET /orders/{id}/timeline`.
  - Move labels to one backend source, served in the API or the OpenAPI enum descriptions.
- **Effort:** M. **Confidence:** high.

### ARCH-02 (HIGH): Two parallel "job" aggregates (Order and RepairJob) with no shared spine; repairs cannot be invoiced
- **Evidence:**
  - `RepairJob` (`db/models.py:1828`) has no `order_id`. It has its own number scheme, status machine, photo table and cost floats (`:1886-1887`).
  - `Invoice.order_id` is `nullable=False` (`db/models.py:1326-1330`), and `invoice_service.py` never references repairs.
  - Quotes attach to orders only through a nullable FK (`db/models.py` Quote block, `ondelete="SET NULL"`). Consultations convert to orders through `converted_order_id`.
  - The portal resolves three reference formats separately (`customer_portal.py` header).
- **Why it matters:** repairs are the highest-volume work type in a small workshop. Every cross-cutting feature has to be built twice: customer updates already special-case this (`PhotosNotAllowedForRepairError`, `services/customer_update_service.py:145`), and so will timelines, kanban, invoicing and the feedback digest. The domain review should confirm the business impact; architecturally, this is the main force that doubles the cost of every future feature.
- **Recommendation:** introduce a common "work item/Vorgang" concept. The pragmatic option is a `jobs` supertable, or a `job_id` that both orders and repairs reference, carrying customer, number, lifecycle status, timeline and media. Let invoices, updates, photos and events reference the job. Migrate incrementally: add the table, backfill, then move one feature at a time.
- **Effort:** L. **Confidence:** medium (the exact shape needs the domain review's input).

### ARCH-03 (HIGH): The repository layer is nominal: 1.8k LOC of dead code, while routers and services both hit the ORM
- **Evidence:**
  - `db/repositories/{base,customer,material,order}.py` total 1,834 LOC. Nothing under `src/` imports them (they are only referenced by hygiene tests such as `tests/unit/test_customer_repository_hygiene.py`).
  - Meanwhile 32 routers import SQLAlchemy and make 60 direct `execute/commit` calls (e.g. the whole of `api/routers/customer_portal.py`).
  - Services write SQL inline as `@staticmethod` namespaces (286 staticmethods across 36 classes).
  - `api/routers.py` (75 LOC) is an old module shadowed by the `api/routers/` package and can never be imported.
- **Why it matters:** there is no single place where data-access rules live: soft-delete filtering, PII decryption, audit hooks, eager-loading policy, and later tenant scoping. Dead code that looks authoritative misleads contributors and AI agents; the unused `add_status_history` is exactly why ARCH-01 happened.
- **Recommendation:** decide explicitly on **services own queries**. That is the simpler choice for this team, and repositories would add a layer without a second storage backend. Then:
  - Delete `db/repositories/` and `api/routers.py`.
  - Move router SQL into services.
  - Add an import-linter rule (`import-linter` or a ruff banned-api rule) forbidding `sqlalchemy` in `api/routers/**`.
  - Keep per-aggregate query helpers inside service packages.
- **Effort:** S to delete, M to move router SQL. **Confidence:** high.

### ARCH-04 (HIGH): Background and side-effect work runs in the web process, and `--workers 2` duplicates it
- **Evidence:**
  - Prod runs `uvicorn --workers 2` (`podman-compose.prod.yml` backend `command`). Every worker runs `@app.on_event("startup")` and spawns `system_monitor_loop()` (`main.py:356-360`, `services/system_monitor.py:333-346`).
  - The loop runs deadline, pickup and fitting scans. These dedupe by check-then-insert (`notification_service.py` docstrings at the check methods), and with two concurrent workers that is a race.
  - `create_notification` then emails customers for `ORDER_STATUS/PICKUP_READY/FITTING_REMINDER/REPAIR_*` (`notification_service.py:50-58,107-113`). So a race can send **duplicate customer emails**.
  - Metal-price refresh also runs twice. In-memory metrics (`request_metrics.py:30,33`) and the slowapi limiters (`main.py:69`, `auth.py:30`, `customer_portal.py:43`, no `storage_uri`) are per worker, so metrics are halved and rate limits effectively doubled (see security review).
  - Customer email is sent inline in the request or scan path through `aiosmtplib` (`services/email_service.py:307`), with no retry queue apart from the manual `SEND_FAILED` resend in `customer_update_service.py:605-650`.
  - No `pg_try_advisory_lock` anywhere.
- **Why it matters:** customer-facing communication is the product's differentiator. Duplicate or lost emails damage trust directly. More scheduled customer feedback (digests, reminders) will make this worse.
- **Recommendation:**
  1. Short term: guard `system_monitor_loop` with a Postgres advisory lock (leader election), or move it to a systemd timer like the other jobs.
  2. Medium term: add a small **durable job/outbox table** (`outbox_messages`: kind, payload, status, attempts, next_attempt_at, dedupe_key UNIQUE). Services insert into it in the same transaction as the business change. A single worker process (a separate compose service running `python -m goldsmith_erp.worker`, using `SELECT ... FOR UPDATE SKIP LOCKED`) sends emails, renders PDFs and publishes to Redis.

  This removes the need for Celery or arq (Redis-backed queues would be one more stateful dependency with weaker durability than the PG you already back up).
- **Effort:** S for the lock, M for the outbox and worker. **Confidence:** high.

### ARCH-05 (HIGH): Customer communication is a side effect of internal staff notifications
- **Evidence:** `NotificationService.create_notification` creates a *staff* in-app notification, commits (`notification_service.py:100`), publishes, and then, if the type is in `_CUSTOMER_EMAIL_TYPES`, looks up the customer and emails them (`:107-113`, `:617-660`). A separate, well-designed customer-update pipeline (`customer_update_service.py`, draft, send, PDF, §649 cost-change) sits alongside it.
- **Why it matters:** the product goal is about client feedback, yet there are two unrelated channels. One is implicit (a staff alert implies a customer email) and has no consent, preview or audit trail per customer message. The other is explicit. Adding digests, photo reports or a portal on top of the implicit path would mean coupling to notification types.
- **Recommendation:** make "customer communication" its own module. A `CustomerMessage` record (channel, template, job_id, consent check, rendered snapshot, delivery status) is produced by domain events (ARCH-01 events) or by the goldsmith explicitly, and dispatched by the outbox worker (ARCH-04). Staff notifications stay internal. Fold the current customer-update flow in as the "manual" producer.
- **Effort:** M. **Confidence:** high.

### ARCH-06 (MEDIUM): The frontend has no server-state layer; lists truncate silently at 100 and nothing refreshes
- **Evidence:**
  - 51 page/component files fetch in `useEffect` and hand-roll `isLoading`/`error` (53 `setLoading(true)`-style sites).
  - `OrdersPage` calls `ordersApi.getAll()` with no args (`frontend/src/pages/OrdersPage.tsx:76`). That defaults to `limit=100` (`frontend/src/api/orders.ts:18-27`) and the backend returns the newest 100 (`services/order_service.py:154-158`). The page then searches, filters by status and sorts **client-side** (`OrdersPage.tsx:86-110`). An in-progress order that is older than the newest 100 disappears from "In Bearbeitung" with no indication.
  - `OrderContext` holds UI tab state, not data.
  - WebSocket events reach only timers and the bell. The order list never updates live, and there is no refetch on reconnect.
- **Why it matters:** "faster to keep track of work" dies when lists lie. This will surface in the first busy season (about 100 orders is a few months for a busy workshop).
- **Recommendation:**
  - Adopt **TanStack Query**. It is worth it here: it deletes boilerplate across 51 files and gives cache, dedupe, retry, background refetch, and a single `queryClient.invalidateQueries(['orders'])` hook that the WebSocket handler can call.
  - Move filtering, search and paging to the server with a page envelope (ARCH-08).
  - Do not add Zustand or Redux; local UI state is fine in Context.
- **Effort:** M, incremental page by page. **Confidence:** high.

### ARCH-07 (MEDIUM): API types are hand-maintained on both sides, with no generated contract
- **Evidence:**
  - `frontend/src/types.ts` is 1,285 hand-written lines, imported by 74 files.
  - The v1.3 memory notes record live bugs from drift: `DRAFT` vs `draft` casing at 7 sites, and a missing `order_type` field.
  - OpenAPI is disabled in prod (fine), but it is not exported in CI either, and no `openapi-typescript`, orval or hey-api tooling exists.
  - 55 handlers have no `response_model` (188 of 243 do).
  - Money is `float` end to end.
- **Why it matters:** every new feature changes both sides, and the drift has already cost live-verification rounds.
- **Recommendation:**
  - Add `scripts/export_openapi.py`, then run `openapi-typescript` to produce `frontend/src/api/schema.d.ts` in CI, with a diff check that fails on drift.
  - Migrate `types.ts` gradually by aliasing to the generated types. Use `openapi-fetch` or keep axios; either works.
  - Require `response_model` on every handler (a lint test over `app.routes`).
- **Effort:** S for tooling, M for migration. **Confidence:** high.

### ARCH-08 (MEDIUM): API conventions are inconsistent: pagination, error envelope, prefix ownership, exception mapping
- **Evidence:**
  - Only quotes and invoices return a paged envelope (`models/quote.py:190`, `models/invoice.py:175`). 37 list endpoints return bare arrays, and `limit` has no upper bound (e.g. `api/routers/orders.py:94-95`).
  - The error body is FastAPI's `{"detail": ...}`, with German strings built ad hoc. There is no machine-readable `code` for the frontend to branch on.
  - Only one exception handler is registered (`main.py:137`). Routers translate domain errors by hand in 63 `except` blocks.
  - Some services still raise `HTTPException` subclasses (`order_service.py:41`, `time_tracking_service.py:45,69`, `metal_inventory_service.py:85`).
  - Route prefixes are set half in `main.py` (18 mounts with the bare `API_V1_STR` prefix) and half inside the router (`customers.py:44`, `metal_inventory.py:34`, ...).
  - Of 243 handlers, only 8 use PATCH and 19 use PUT. Many state changes are ad-hoc `POST /x/{id}/action` endpoints, which is fine if it is deliberate.
- **Recommendation:**
  - One `DomainError(code, message, status)` base with `NotFound`, `Conflict`, `InvalidTransition` and `Forbidden` subclasses; a single registered handler that emits `{"detail", "code"}` (or RFC 9457 problem+json).
  - A `Page[T]` generic with a capped `limit` (`Query(le=200)`).
  - A router-registry module that owns prefixes, which also shrinks `main.py`.
- **Effort:** M. **Confidence:** high.

### ARCH-09 (MEDIUM): `db/models.py` and several services are god-modules (3,245 LOC and 79 classes, growing)
- **Evidence:** the size table; legacy `Column()` style with no `Mapped[]` annotations (0 of 547 columns), which is also part of why mypy strict has thousands of errors (see testing/CI review). `customer_service.py` (1,856) mixes CRM and GDPR, `pdf_service.py` (1,483) handles every document type, and `customers.py` (1,066) mixes CRM and GDPR routes.
- **Why it matters:** merge-conflict hotspot (CLAUDE.md already forbids parallelizing edits to `db/models.py`), reviewer load, and slow typing burndown.
- **Recommendation:** convert to **domain packages** (a modular monolith): `goldsmith_erp/domains/{orders,repairs,customers,billing,workshop,inventory,comms,gdpr}/` each with `models.py`, `schemas.py`, `service.py`, `router.py`. Keep `db/models/__init__.py` as a re-export so Alembic autogenerate and the imports keep working. Convert to `Mapped[]` per package as it moves. Enforce allowed dependencies between domains with `import-linter` contracts.
- **Effort:** L, mechanical and incremental. **Confidence:** high.

### ARCH-10 (MEDIUM): Photos and media have three unrelated models and a local filesystem assumption
- **Evidence:**
  - `OrderPhoto` has a UUID string PK (`db/models.py:856-876`), `RepairPhoto` an Integer PK (`:1944`), and `ConsultationPhoto` a UUID PK (`:2084`).
  - There are three services (`photo_service.py`, `repair_photo_service.py`, `consultation_photo_service.py`, 941 LOC together), each with its own `write_bytes` on the event loop.
  - `CustomerUpdate.photo_ids` is an untyped JSON list with no FK integrity (`db/models.py:2707`).
  - The frontend fakes numeric IDs from UUIDs with a `Math.random()` fallback (`OrderDetailPage.tsx:523-528`).
  - Storage is a bind-mounted `./uploads` (prod compose), and `boto3` is declared but unused (`pyproject.toml`).
- **Why it matters:** "photo-centric progress documentation" and "clients get better feedback on their jewelry" are both media features. Today each new surface (timeline, digest, portal gallery, before/after) has to join three tables with different key types.
- **Recommendation:** one `media_assets` table (uuid, owner job_id, kind/phase, stage, captured_at, taken_by, storage_key, sha256, width/height, variants JSON, customer_visible bool, consent flag). Put a `MediaStore` interface in front of the local FS today (S3/MinIO-ready later). Generate thumbnails and email variants in the worker (ARCH-04), not in the request. Migrate the three tables into it with views for compatibility.
- **Effort:** M/L. **Confidence:** high.

### ARCH-11 (MEDIUM): Real-time fan-out is per socket, not tied to a lifecycle, and only partially used
- **Evidence:**
  - Each socket opens its own Redis `SUBSCRIBE` (`main.py:310,339`, `core/pubsub.py:60-75`).
  - There is no server heartbeat, no lifespan shutdown (`main.py:356`), and `publish_event` silently drops events after about 1.5 s of retries (`core/pubsub.py:42-57`).
  - The only consumers are the timer and the bell (section B). `order_updates` is published but no order view listens.
- **Why it matters:** at workshop scale (under 15 sockets) the connection count is not the problem. The problem is that real-time does not deliver the UX it promises (a live board), and dropped events have no recovery path.
- **Recommendation:** treat WebSocket messages as **cache-invalidation hints**, not data: `{type: "order.changed", id}`, and the frontend then invalidates the query (ARCH-06). With a refetch on reconnect, lost events stop mattering, and no outbox is needed for the UI. Use one subscriber per process with an in-memory fan-out map, created and cancelled in `lifespan`, plus a 30 s ping. Skip SSE and extra brokers.
- **Effort:** S/M. **Confidence:** high.

### ARCH-12 (MEDIUM): Observability stops at JSON logs; there is no error tracking or durable metrics
- **Evidence:** `core/logging.py` (JSON + request_id) is good. Metrics are an in-memory deque per worker (`request_metrics.py:30,33`). There is no Sentry, OTel or Prometheus. The health watchdog is a systemd timer that emails (`deploy/systemd/goldsmith-health-watchdog.*`). Logs are json-file capped at 10 MB × 3 per container (prod compose `logging:`), so a busy week of logs rotates away.
- **Why it matters:** a one-person-IT shop learns of failures when Anne phones. The failure modes that hurt (email not sent, PDF crashed, migration stuck) are invisible.
- **Recommendation:** for this team, add the **Sentry SDK** (self-hosted GlitchTip is fine for data residency) on backend and frontend, with PII scrubbing (see GDPR review). Add an admin "Outbox/Jobs" page showing failed deliveries (with ARCH-04). Persist logs with journald (`--log-driver=journald`), which the systemd tooling already uses. Skip OpenTelemetry and Prometheus: there is one box and no SRE to look at them.
- **Effort:** S. **Confidence:** high.

### ARCH-13 (LOW): Configuration and runtime toggles: no feature flags, and settings drift
- **Evidence:** there are no feature flags (AR-E still open), while scanner, ML (`api/routers/ml.py`, 914 LOC; `ml/` 3,157 LOC) and estimator are optional subsystems. `core/config.py` is 451 LOC of typed pydantic-settings (good). `pyproject.toml` declares `boto3`, `pyjwt` and `python-jose`; only `jose` is imported (`core/security.py`, `main.py`, `api/deps.py`, `middleware/auth_required.py`, `api/routers/auth.py`).
- **Recommendation:** `FEATURES__SCANNER=true`-style fields on `Settings`, plus a `require_feature()` dependency and a `/api/v1/features` endpoint the SPA reads to hide menus. No flag service. Remove the unused dependencies (the security review owns the jose-vs-pyjwt choice).
- **Effort:** S. **Confidence:** high.

### ARCH-14 (LOW): Deployment is single-box and boot-coupled, which is fine, but migrations and seeding run on every start
- **Evidence:** the backend `command` runs `alembic upgrade head && python -m goldsmith_erp.db.reference_seed && uvicorn ...` (prod compose). This is acceptable for one box, but a failed migration crash-loops the API under `restart: unless-stopped`, and there is no pre-migration backup hook. The PWA precaches authenticated `/api/v1/orders` responses in Cache Storage (`frontend/vite.config.ts:33-47`), so pricing data sits at rest on shared workshop devices (see security/GDPR review).
- **Recommendation:** a one-shot `migrate` compose service (`depends_on: condition: service_completed_successfully`) that runs `scripts/backup.sh` first. Keep the single box; document it as an explicit decision in an ADR.
- **Effort:** S. **Confidence:** high.

### ARCH-15 (LOW): Audit and authorization are routed by URL shape, not attached to data
- **Evidence:** `AuditLoggingMiddleware` decides by `_RESOURCE_ROUTES[parts[2]]` (`middleware/audit_logging.py:120-137`), so financial data served under `/orders` (price, margins) or embedded in other responses is not audited unless the path matches (PR 2.2 still applies). Permissions are a decorator per handler (179 sites).
- **Why it matters:** every new endpoint that returns sensitive fields (portal, digest, timeline) has to remember to extend a path table. This does not scale with feature count.
- **Recommendation:** move audit emission into the service/query layer for sensitive aggregates (for example, a `@audited_read("financial")` service decorator, or an `after_execute` hook scoped to the models involved). Mark sensitive fields in the Pydantic read models and derive redaction per role. See the security and GDPR reviews for the rules. Architecturally, the point is to put the policy next to the data.
- **Effort:** M. **Confidence:** medium.

### ARCH-16 (LOW): The architecture docs are stale or incomplete
- **Evidence:** the LikeC4 model (`docs/architecture/likec4/src/goldsmith-erp.c4`, 165 lines) shows frontend, backend, Postgres and Redis only. It has no Caddy, nginx, systemd jobs, SMTP, file store or customer email channel. `ARCHITECTURE_REVIEW.md` is from 2025-11 and CLAUDE.md still says "READ THIS FIRST". There are no ADRs for single-box, jose, statistical estimator, or no-portal decisions.
- **Recommendation:** archive the old review. Update the C4 container view with this document's section B. Start `docs/adr/` with the decisions in section E.
- **Effort:** S. **Confidence:** high.

---

## D. State-of-the-art scorecard (for a 2026 single-workshop business app)

| Dimension | Score (1-5) | Justification |
|---|---|---|
| Layering | 2 | Router, service and ORM layers exist, but routers run SQL, services raise HTTP, and repositories are dead code |
| Domain modeling | 2 | Rich entities (79), but the core order lifecycle is an unguarded enum with no history; Order and Repair are duplicated aggregates |
| API design | 3 | Versioned `/api/v1`, Pydantic in/out on 77% of routes, auth deny-by-default; no page envelope, no error codes, unbounded limits |
| Data fetching (frontend) | 2 | Hand-rolled `useEffect` fetching in 51 files, client-side filtering over truncated lists, no cache or invalidation |
| Type safety end-to-end | 2 | Hand-written `types.ts`, legacy untyped ORM columns, mypy baseline gate rather than clean; drift has caused live bugs |
| Real-time | 2 | Works for timers and the bell; per-socket subscribe, no lifespan or heartbeat, not used for the work board |
| Background jobs | 3 | systemd timers for GDPR, retention and watchdog are a good fit; in-process monitor duplicated per worker, inline SMTP, no outbox |
| Observability | 2 | Good JSON logs and health endpoints; no error tracking, metrics or delivery dashboard |
| Deployment | 4 | Rootless Podman, Caddy TLS, non-root, read-only Redis, backups and restore scripts, secret validation; migrate-on-boot is the remaining weak point |
| Testability | 3 | Large suites (113 backend and 48 frontend test files, e2e); SQLite default vs PG-specific features (`tests/conftest.py:43`); static services make DI seams rare (see testing review) |
| Extensibility | 2 | Every product-goal feature (feedback, photos, kanban) hits ARCH-01, 02, 05 and 10 first; multi-tenant readiness is one nullable column |

Mean is about 2.5. The deployment and security primitives are ahead of typical small-business apps. The domain core and the frontend data layer are behind.

### Comparison with specific options (adopt for THIS team?)

| Option | Verdict | Reason |
|---|---|---|
| TanStack Query | **Adopt** | Removes boilerplate across 51 files and fixes staleness; pairs with WS invalidation |
| Generated OpenAPI client/types | **Adopt** (types first) | Drift bugs already happened; CI diff gate is cheap |
| Domain events + transactional outbox (PG table) | **Adopt, minimal** | Needed for reliable customer comms and timeline; no broker |
| Task queue (Celery/arq/Dramatiq) | **Skip** | PG `SKIP LOCKED` worker covers the volume; one less stateful service |
| Explicit state machine (hand-rolled table) | **Adopt** | Repairs already prove the pattern; a library (`transitions`) is unnecessary |
| Feature flags | **Adopt, env-based** | Optional subsystems (scanner, ML, estimator); no flag service |
| Structured logging | **Have it** | Keep; add journald persistence |
| Sentry/GlitchTip | **Adopt** | Highest value per hour of any observability item |
| OpenTelemetry / Prometheus | **Skip for now** | One host, nobody watching dashboards |
| Typed settings | **Have it** | pydantic-settings with prod validators is already good |
| Modular monolith (domain packages + import-linter) | **Adopt incrementally** | Addresses god-modules without microservices |
| Microservices / k8s | **Reject** | Wrong for team size and product |
| Zustand/Redux | **Reject** | Server state is the problem, not client state |

---

## E. Target architecture (6-12 months)

```
SPA (React, TanStack Query, generated API types, WS = invalidation hints)
        |
Caddy -> nginx -> FastAPI "web" (N workers, stateless: no loops, no SMTP)
                     domains/
                       jobs      (Vorgang spine: Order | Repair, lifecycle SM, timeline)
                       customers (CRM)      gdpr (export/erase/retention)
                       billing   (quotes, invoices, cost changes)
                       workshop  (stages, time, capacity/kanban)
                       media     (media_assets + MediaStore)
                       comms     (CustomerMessage, templates, consent)
                       inventory, metals, estimator, scanner
                     shared kernel: auth/RBAC, audit, encryption, errors, pagination
                     write path: service -> tx { state change + job_events + outbox }
        |
FastAPI "worker" (1 process, same image): outbox dispatcher (email, PDF, thumbnails,
        Redis publish), scheduled scans (leader via advisory lock)
        |
PostgreSQL (source of truth + outbox)   Redis (pubsub, cache, tokens)   MediaStore (FS now)
host systemd: gdpr/retention/watchdog/backup timers;  Sentry/GlitchTip
```

Customer feedback builds on this. A job's timeline events plus `customer_visible` media produce a `CustomerMessage`: an email digest with photos, a PDF status report (the existing `pdf_service`), or later a read-only token portal view that reuses the existing `customer_portal` token mechanism. Kanban is a view over `jobs` grouped by `production_stage`, with capacity computed from time estimates (the estimator) and deadlines.

### Phases (each can ship on its own)

| Phase | Content | Ships value | Risk / mitigation |
|---|---|---|---|
| **0. Hygiene (1-2 wk)** | Delete `db/repositories/` and `api/routers.py`; `lifespan` replaces `on_event`; advisory-lock or timer for `system_monitor`; Sentry; unused deps out; archive old review; ADRs | No duplicate customer emails; errors visible | Low. Verify no hidden importers (grep and tests) |
| **1. Contract (2-3 wk)** | `DomainError` + one handler + `code` field; `Page[T]` + capped limits on list endpoints; OpenAPI export + `openapi-typescript` CI gate; TanStack Query on Orders, Repairs and Customers pages with server-side filter and search | Correct lists, less boilerplate | Medium: frontend error handling reads `detail`, so keep `detail` and add `code` |
| **2. Lifecycle (3-4 wk)** | Order transition table + guards; `job_events` written on every transition (backfill from `updated_at` = unknown); `/orders/{id}/timeline`; single label source; separate `production_stage` field | Real history, the basis for feedback and KPIs | Medium: existing orders in odd states need a mapping migration (Alembic data migration, reversible, dry-run on a prod dump) |
| **3. Outbox + comms (3-4 wk)** | `outbox_messages` + worker service in compose; move SMTP, PDF and thumbnail work off the request path; `CustomerMessage` module; staff notifications no longer email customers directly | Reliable, auditable client communication; retry UI | Medium: the email cut-over must be idempotent (dedupe_key); run old and new paths behind a flag for one week |
| **4. Media (3-4 wk)** | `media_assets` + `MediaStore`; migrate the three photo tables; `customer_visible` flag; digest template with photos | Photo-centric progress docs and client digests | Medium: file moves must be atomic with DB rows; keep old paths readable, and backups must include media |
| **5. Job spine (4-6 wk)** | `jobs` supertable referenced by orders and repairs; invoices, updates, media and events attach to `job_id`; repair invoicing | Repairs are first-class for billing and feedback; kanban across both | High: the largest migration. Do it after phases 2-4 so the new tables are born `job_id`-aware |
| **6. Modularize (ongoing)** | Split `db/models.py` into domain packages with `Mapped[]`; import-linter contracts; move router SQL into services | Faster, safer changes; mypy burndown | Low per step. Alembic autogenerate must still see all models (re-export) |
| **Later / optional** | Read-only customer portal page (token link); kanban and capacity UI; multi-workshop | | Multi-tenant: add `workshop_id` to the `jobs` spine and customers first, and scope queries in services (a reason to keep queries centralized). Do not start this before phase 5 |

Explicitly **not** in the target: microservices, Kubernetes, Celery, an event-sourcing store, GraphQL, or a client state library.

---

## F. Things the user might have missed

1. **The order "Verlauf" tab is placeholder UI** (`OrderDetailPage.tsx:495-517`): two timestamps presented as a history. Staff may believe the history is recorded when it is not. Anne should know before relying on it for disputes.
2. **Two workers can double-email customers** for pickup and fitting reminders (ARCH-04). This is the only finding here that can embarrass the workshop in front of clients, and a small change fixes it.
3. **Orders page status filter hides older active orders** once more than 100 orders exist (ARCH-06). It is silent, so staff will think orders are lost.
4. **Status vocabulary disagrees between the customer portal and the staff UI** ("Bereit zur Fassung" vs "Bereit für Steinbesatz"; "Qualitaetskontrolle" vs "Endkontrolle"). Customers and staff would describe the same state in different words on the phone.
5. **The PWA caches order API responses (with prices) on devices** (`vite.config.ts:33-47`). On a shared workshop tablet, financial data persists in the browser after logout. This is a security/GDPR item and I am flagging it here for routing.
6. **The ML subsystem is about 4k LOC** (`ml/` 3,157 plus `api/routers/ml.py` 914) for a workshop with a few staff, with no flag to switch it off. Consider feature-flagging it off by default until the data volume justifies it; the statistical estimator (V1.3) is the part that pays off.
7. **CLAUDE.md prescribes patterns the code no longer follows** (the "Redis via `core.pubsub.get_redis_client`" example matches, but "READ ARCHITECTURE_REVIEW.md first", the Zustand advice and the localStorage note are obsolete). AI agents working on this repo are steered by stale guidance. A CLAUDE.md refresh is cheap and high-leverage.
8. **`db/repositories/` is guarded by hygiene tests** that keep dead code alive (e.g. `tests/unit/test_order_repository_hygiene.py`). Delete those tests together with the code.
9. **No ADR records the choice of single box with migrate-on-boot, or of cookie auth over bearer tokens.** Future contributors (or a SaaS pivot) will re-litigate them.

---

## Verification (2026-09-25)

Verifier: `.orchestrated-fable/ux-erp-audit-2026-09/verify-backend-architecture.md` (adversarial, read-only, HEAD `73fff19`). All five HIGH findings confirmed; none refuted or re-rated.

| ID | Title (short) | Claimed | Verdict | Corrected severity | Verifier note |
|---|---|---|---|---|---|
| ARCH-01 | Order status is free-form; no transition table; history never written | HIGH | CONFIRMED | HIGH | `order_service.py:330-398`, `OrderDetailPage.tsx:457-468`; the enum docstring pipeline differs from its members. Same root cause as BE-06; both reviews converge on identical evidence |
| ARCH-02 | Order and RepairJob duplicated; repairs cannot be invoiced | HIGH | CONFIRMED | HIGH | `RepairJob` has no `order_id`; `Invoice.order_id` is NOT NULL; zero "repair" hits in `invoice_service.py`. A hard structural block: no code path can invoice a repair without a schema change |
| ARCH-03 | Repository layer is 1.8k LOC dead code; routers run SQL | HIGH | CONFIRMED | HIGH | 179+686+198+771 = 1,834 LOC; no importer outside the package; 32 routers import SQLAlchemy |
| ARCH-04 | Background work in-process; `--workers 2` duplicates it; no leader lock | HIGH | CONFIRMED | HIGH | `main.py:356-360` task without stored reference; no `advisory_lock` anywhere. Directly causes BE-09's double emails once email is enabled |
| ARCH-05 | Customer email is a side effect of staff notifications | HIGH | CONFIRMED | HIGH | `notification_service.py:90-113`; confirms the two-channel framing on top of BE-09 |

MEDIUM and LOW findings (ARCH-06 to ARCH-16) were outside the verifier's scope. Tracking: [FINDINGS-REGISTER.md](FINDINGS-REGISTER.md); fixes: [MASTER-FIX-PLAN.md](MASTER-FIX-PLAN.md).
