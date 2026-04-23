# Helper — Architectural Reasoning & Cross-Cutting Concerns  (2026-04-23, HEAD 1feae6d)

## Method
Used `mcp__sequential-thinking__sequentialthinking` to reason through 10 concern areas (A–J) with the broader system in mind. Evidence gathered via targeted Read + Grep + wc -l; did not review line-by-line. Confidence for each finding is HIGH; claims avoid extrapolating beyond what the committed code shows.

Repo entry points scanned: `src/goldsmith_erp/main.py`, `core/pubsub.py`, `core/config.py`, `db/transaction.py`, `db/models.py` (partial), representative services (order, handoff, time_tracking), `middleware/request_metrics.py`, `frontend/src/api/client.ts`, `frontend/src/hooks/useWebSocket.ts`.

---

## Concern-by-concern analysis

### A. Event consistency (Postgres ↔ Redis)
Ordering is correct in the sampled services: `publish_event` is called AFTER the `async with transactional(db):` block exits (`services/order_service.py:210–229`, `:540–549`; `services/handoff_service.py:170–209`; `services/time_tracking_service.py:212–250`). `publish_event` itself retries 3× with exponential back-off and deliberately **never raises** (`core/pubsub.py:40–57`) so a Redis outage can't take the app down. Order creation/update has a **compensation path** (A5.4/A5.5) that writes an in-app `Notification` on publish failure telling the user to reload (`services/order_service.py:429–468`). Other domains (handoff, repair, metal_inventory, time_tracking) just log-and-drop. There is **no outbox table** — if Redis is unavailable for the full ~1.5 s retry window, that single event is lost forever. Acceptable for real-time fan-out (Postgres remains authoritative), but a durable outbox would be the canonical fix if the product ever needs exactly-once delivery semantics.

### B. WebSocket scalability ceiling
Each connected WebSocket spawns its own `subscribe_and_forward` coroutine that opens a **dedicated Redis pubsub connection from the pool** (`main.py:172`, `:199`; `core/pubsub.py:60–75`). At N connected clients that's N Redis subscriber connections; the default `redis-py` pool is ~50. Horizontal scaling works in principle — every replica subscribes to the same channel, Redis fans out to all replicas, each re-broadcasts to its local WS list — but the per-client subscription is expensive. Standard optimisation: one per-process subscriber per channel + in-memory fanout map. Back-pressure is per-connection (a slow client only stalls its own `ws.send_text` loop), which is the right isolation. No server-side heartbeat/ping; dead-half-open connections linger.

### C. Service-router layering
No cycles (services never import routers — verified by `grep "from goldsmith_erp.api" src/goldsmith_erp/services/`). Routers DO import SQLAlchemy models (33 router files) — mostly for `UserModel`/`MaterialModel` type-annotations on `Depends(get_current_user)`; minor leak, not harmful. **The real smell is the reverse direction**: services raise `HTTPException` directly (>70 occurrences; heaviest: `time_tracking_service.py` 13, `metal_inventory_service.py` 12, `handoff_service.py` 10, `quote_service.py` 8, `repair_service.py` 7, `invoice_service.py` 7). That couples the service contract to the HTTP transport and precludes clean reuse from CLI jobs, background workers, Celery tasks, or future gRPC. Detached-entity risk on lazy-load: services consistently re-fetch after commit with `selectinload` (e.g. `order_service.py:208`, `time_tracking_service.py` — 21 selectinload calls), so this particular trap is handled.

### D. Error propagation
Only exception handler registered is `RateLimitExceeded` (`main.py:95`). No global handler for `ValueError`, `SQLAlchemyError`, or a domain exception hierarchy. Because services raise `HTTPException` directly, the existing path happens to work — but any uncaught `ValueError` (there are many in service code, e.g. `time_tracking_service.py:115, :161, :439`) becomes a raw 500 with stacktrace in the logs instead of a 400/409. There is no mapping layer (`DomainError → HTTP status`). The sensible fix is: introduce a small exception hierarchy (`NotFoundError`, `ConflictError`, `ValidationError`, `PermissionError`), have services raise those, and register one `@app.exception_handler` per family.

### E. Feature flags / kill switches
**None.** `core/config.py` exposes boolean toggles that are purely capability gates (`EMAIL_NOTIFICATIONS_ENABLED`, `DEBUG`, `COOKIE_SECURE`, `METAL_PRICE_API_URL`) — no scanner kill-switch, no ML kill-switch, no per-feature rollout flag. Scanner is a V1.1 user-facing feature that went live recently; rolling it back currently means redeploying a previous build. Minimum viable additions: an env-var-driven `FEATURES: dict[str, bool]` in Settings, a `require_feature("scanner")` dependency, and one or two per-feature toggles. DB-backed/per-user flags would be a follow-up.

### F. Coupling hotspots

| File | LOC | Responsibility count | Note |
|------|-----|----------------------|------|
| `src/goldsmith_erp/db/models.py` | **2435** | **64 top-level classes** | Every ORM entity in a single module. Maximum fan-in: imported by essentially every service & router. Any schema-like change (new enum, new base mixin) forces the whole codebase to re-evaluate imports. |
| `services/scanner_service.py` | 1367 | scanner dispatch + state machine + metrics + anomaly | Recent V1.1 slice; expected to grow; refactor window exists now. |
| `services/pdf_service.py` | 1183 | invoice + quote + valuation + label PDFs | Consolidate template rendering separately. |
| `services/customer_service.py` | 1125 | CRM + GDPR export + erasure + search | Split customer CRM from GDPR ops. |
| `services/time_tracking_service.py` | 981 | time entries + interruptions + anomaly alerts + ML | Extract anomaly + ML bits. |
| `api/routers/ml.py` | 843 | ml predictions + monitoring + admin | Split `/ml/predict` from `/ml/admin`. |
| `db/repositories/order.py` | 773 | — | Fine for a repository; watch for growth. |
| `api/routers/customers.py` | 740 | — | GDPR endpoints mixed in. |

`db/models.py` is the single most dangerous coupling hotspot: 64 classes × direct cross-imports from dozens of services means any schema refactor risks producing a large, hard-to-review diff.

### G. Frontend-backend state coherence
`frontend/src/hooks/useWebSocket.ts:96–139` implements reconnect with exponential back-off (1 s → 2 s → 4 s → …, cap 30 s). `ws.onopen` resets `attemptRef` on a successful reconnect — good hygiene. **No on-reconnect refetch hook**: the WS hook only exposes `onMessage`; each context/component has to notice the reconnect and decide to re-hydrate its slice. That's drift-prone — a disconnected tab will show stale orders/time-entries until the user triggers an action that refetches. No ETag / `If-Match` / `updated_at` version tokens are in use (`grep` returned only an unrelated `version: string` in `api/admin.ts`). Backend has `updated_at` columns but no optimistic-concurrency enforcement on writes.

### H. Auth model coherence
Contrary to the CLAUDE.md note, the frontend uses **HttpOnly cookies** (`frontend/src/api/client.ts:15–17` — `withCredentials: true`, no `localStorage` token). Refresh flow is well-implemented: in-flight-refresh guard, queued-request drain, `_retry` sentinel to prevent loops, `auth:session-expired` event on final failure (`client.ts:32–134`). WebSocket auth pulls the JWT from cookie first, then from query-param (`main.py:150–154`). **The query-param fallback is a soft security smell** — URL tokens leak into reverse-proxy access logs and browser history. Since the frontend now uses cookies, the query-param path should either be removed or gated behind an explicit setting.

### I. Multi-tenancy readiness
Explicitly single-tenant in V1.1 — not an accidental omission. `User.tenant_id` is a nullable indexed column (`db/models.py:202`) reserved as a **forward-compat slot for V1.2** per `docs/superpowers/plans/qr-barcode-workflow/DECISIONS-2026-04-16.md` §SQ1. `models/_base.py:30,82` and `models/scanner.py:10` reference the same slot. Not a finding — a known roadmap item.

### J. Observability floor
- **Logging**: structured JSON via `pythonjsonlogger` with a `request_id` ContextVar (`core/logging.py`). Solid floor.
- **Metrics**: `middleware/request_metrics.py` keeps an **in-memory** ring buffer of the last 1 000 requests for p50/p95/p99 and 4xx/5xx counts. Dies on restart. No Prometheus exporter, no `/metrics` endpoint found.
- **Tracing**: no OpenTelemetry imports anywhere (`grep` came up empty).
- **Error tracking**: no Sentry integration (`grep` came up empty).

Sufficient for dev and single-workshop; insufficient for any production ops practice that involves alerting on error rates, latency regressions, or distributed traces.

---

## Findings (consolidated)

| Severity | Location | Concern | Issue | Fix direction |
|----------|----------|---------|-------|---------------|
| **P1** | `services/*_service.py` (70+ call sites; top: `time_tracking_service.py:560, :588, :722, :726, :736, :750, :807, :811, :823, :832`) | C, D | Services raise `HTTPException` directly — transport coupling blocks reuse from CLI/jobs/gRPC and means `ValueError` bypasses the response mapping. | Introduce `DomainError` hierarchy (`NotFound`, `Conflict`, `Validation`, `Forbidden`); replace `HTTPException` raises; register one `@app.exception_handler` per family. |
| **P1** | `core/config.py` (no `FEATURE_*` flags) | E | No feature-flag / kill-switch mechanism. Scanner is live in V1.1 with no runtime toggle — rollback = redeploy. | Add `FEATURES: dict[str, bool]` to `Settings` + `require_feature()` FastAPI dependency; gate `api/routers/scanner.py` + `api/routers/ml.py` behind it. |
| **P1** | `main.py:172, :199` + `core/pubsub.py:60–75` | B | Per-connection Redis pubsub subscription. N clients = N Redis subscribers; saturates the default pool at ~50 concurrent users. | One subscriber per channel per process + local in-memory fanout map; keep pool usage O(channels) not O(clients). |
| **P1** | `middleware/request_metrics.py:30–58` | J | Metrics live only in an in-memory ring buffer — dies on restart, no external sink, no tracing, no error tracking. | Expose a `/metrics` Prometheus endpoint (prometheus_client is trivial); add Sentry DSN for exception tracking; add OpenTelemetry when tracing becomes a need. |
| **P1** | `main.py:152–154` (`_authenticate_websocket` query-param fallback) | H | WebSocket token accepted from query string; leaks into proxy logs and browser history. Frontend now uses HttpOnly cookies, so the fallback is vestigial. | Remove the query-param branch (or gate behind an explicit setting for non-browser clients); rely on cookie-auth exclusively. |
| **P1** | `db/models.py` (2435 LOC, 64 classes) | F | Single monolithic ORM module — high fan-in, any change ripples widely. | Split into `db/models/{user,customer,order,material,time_tracking,scanner,gdpr,hallmark,valuation}.py`; keep `db/models/__init__.py` as a flat re-export for backward compat. |
| **P1** | `frontend/src/hooks/useWebSocket.ts:96–139` | G | Reconnect works but no shared on-reconnect-refetch; each context must self-remember to re-hydrate, creating silent drift. | Add an `onReconnect` callback to the hook and centralise a `refetchAll()` plumbing in `AuthContext` / `OrderContext`. |
| **P2** | `services/handoff_service.py:196–215`, `repair_service.py:192, :248`, `metal_inventory_service.py:608` | A | Silent drop of order-update / handoff / material events after 3 Redis retries. Only `order_service` has the A5.4/A5.5 notification-compensation path. | Either lift `_safe_publish_order_event`-style compensation to a shared helper, or introduce a lightweight `outbox_events` table flushed by a background task. |
| **P2** | `services/scanner_service.py` (1367), `pdf_service.py` (1183), `customer_service.py` (1125), `time_tracking_service.py` (981), `api/routers/ml.py` (843) | F | Large single-file services. Growing bug-surface; reviewer cognitive load; merge-conflict hotspot. | Split by subdomain (scanner: dispatch vs metrics vs anomaly; customer: CRM vs GDPR; ml: predict vs monitor vs admin). |
| **P2** | `main.py:164–184`, `:191–210` | B | WebSocket loop lacks server-side heartbeat/ping; dead half-open connections linger. | Add `await ws.send_text('{"type":"ping"}')` every ~30 s + idle timeout; close on ping failure. |

## Strengths observed

- Commit-then-publish ordering is correctly implemented in every sampled service (`async with transactional(db): …; await publish_event(...)`).
- `core/db/transaction.py` provides a clean, consistent `transactional(db)` context manager used project-wide.
- `publish_event` retry-with-back-off + never-raise is the right call: Redis outage does not take the app down (`core/pubsub.py:40–57`).
- `OrderService._safe_publish_order_event` (`order_service.py:395–468`) demonstrates a thoughtful in-app notification compensation pattern when Redis publish fails — worth generalising.
- Structured JSON logging with a per-request `request_id` ContextVar (`core/logging.py:16–45`).
- Cookie-based auth with refresh-storm-safe interceptor (`frontend/src/api/client.ts:60–148`) — queued requests, `_retry` sentinel, graceful `auth:session-expired` event on final failure.
- Tenancy forward-compat slot is deliberately placed, documented, and referenced from new V1.1 models (`db/models.py:199–202`).
- Fail-fast production config: missing `ENCRYPTION_KEY` / `ANONYMIZATION_SALT` refuses to start when `DEBUG=False` (`core/config.py:139–177`).
- Exponential-back-off reconnect with mount-aware cleanup on the frontend (`frontend/src/hooks/useWebSocket.ts:126–139`).

## Open questions / follow-up

1. **Outbox worth the complexity?** V1.1 is best-effort real-time; decide whether a durable outbox is needed before V1.2 multi-tenancy (where a single pubsub event may fan out to different tenant shards and retry semantics matter more).
2. **Scanner kill-switch** — do we want just a router-mount toggle, or also a per-user override for staged rollout?
3. **On-reconnect refetch** — should it live in the `useWebSocket` hook itself, or in each Context? A hook-level `onReconnect` + a `refreshOrders()` in `OrderContext` is the minimal change.
4. **When to split `db/models.py`** — before the V1.2 multi-tenancy migration (which will touch many models) or after? Doing it first makes the tenancy migration review much easier.
5. **Is `pythonjsonlogger` sink pointed at a log aggregator** in production, or are logs currently only in container stdout? That dictates whether Prometheus/Sentry or a proper log-aggregator is the higher-leverage next step.
