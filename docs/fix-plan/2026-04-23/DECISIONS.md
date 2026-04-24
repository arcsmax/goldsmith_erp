# Decisions Log — Week 1 Fix Plan
Running log of product / judgment-call decisions made during fix execution. Every time an implementation question has a non-obvious answer, we record it here so the trail stays auditable.

**Format per decision:**
```
## YYYY-MM-DD — <item ID> — <short title>
**Question:** ...
**Options considered:** ...
**Decision:** ...
**Rationale:** ...
**Decided by:** <user / orchestrator default>
```

---

## 2026-04-23 — (meta) — Scope, branch, testing, decision model

**Question:** How broad is the Week-1 fix effort, where does it land, how are product calls handled, what's the testing bar?

**Decision:**
- **Scope:** Complete Week 1 (Groups A + B + F) from `docs/review/2026-04-23/FIX-PLAN.md`
- **Branch:** `code-review-fixes-2026-04-23` off main `a6a5d73`
- **Product decisions:** stop and ask one-by-one (no batching)
- **Testing:** TDD per fix — failing test before implementation

**Decided by:** user, via AskUserQuestion round on 2026-04-23.

---

## 2026-04-23 — F4 — Defer un-skipping encryption tests

**Question:** Should F4 (un-skip 7 encryption/GDPR tests) be done in Week 1?

**Options considered:**
1. Un-skip now — they'll fail, because encryption infra (EncryptedString TypeDecorator, PII_FIELDS expansion) is a Group-C Week-2 fix
2. Delete as superseded — but we haven't yet verified that any post-Slice-2 encryption tests actually cover the same surface
3. Defer to Week 2, alongside Group C

**Decision:** Option 3 — defer to Week 2. Status `🛑 blocked` on Group C.

**Rationale:** Un-skipping now = red CI with no fix available this week. Deleting blind = risk losing unique coverage. Deferred is the honest state.

**Decided by:** orchestrator default (matches "TDD per fix" — no point testing infra that doesn't exist yet).

---

## 2026-04-23 — A4 — Compose validator substitution + env-file isolation

**Question:** How to run the A4 acceptance tests when `podman-compose` is not
installed in the executing agent's environment, and how to prevent the repo's
own `.env` from masking the "POSTGRES_PASSWORD unset" test?

**Options considered:**
1. Require podman-compose — blocks CI on environments that only have Docker
2. Fall back to `docker compose` (v2) — identical compose-file YAML validator
   for the two guarantees A4 cares about (required-variable `:?` interpolation
   and port-mapping host_ip). Spec explicitly permits this.
3. Skip the tests if podman-compose is missing — defeats the TDD bar

**Decision:** Option 2 — `scripts/test-compose-validation.sh` prefers
`podman-compose`, falls back to `docker compose`, then `docker-compose`
(classic), then SKIP. Additional nuance: `docker compose` auto-loads `.env`,
which supplies a real POSTGRES_PASSWORD and would silently defeat Test 1.
The script passes `--env-file /dev/null` to the docker-family validators
(podman-compose doesn't need it — it doesn't auto-load `.env` the same way)
so the test measures the compose file on its own.

**Rationale:** The two behaviours A4 enforces — required-variable rejection
and loopback port binding — are pure compose-file syntax, validated identically
by either tool. Coupling the test to the presence of podman-compose buys
nothing and costs portability.

**Port override nuance:** Used the optional pattern from the spec's "Open
questions" section — `${DB_HOST_IP:-127.0.0.1}:${DB_PORT:-5432}:5432` — so a
developer on a remote dev box can opt in to LAN access without editing the
compose file.

**Decided by:** orchestrator default, consistent with spec's escalation clause.

---

## 2026-04-23 — A2 — DI factory vs decorator-style for merged `require_permission`

**Question:** The routers using the old `api.deps.require_permission` all use
`Depends(require_permission(X))` (FastAPI DI factory style). The authoritative
`core.permissions.require_permission` is a function decorator that extracts
`current_user` from `kwargs`. How do we converge?

**Options considered:**
1. Add a companion `require_permission_dep(perm)` factory to `core.permissions`
   — preserves existing call-site style; minimal, additive.
2. Convert all ~20 call sites across the affected routers to decorator style
   (`@require_permission(X)` above the route, `current_user: User =
   Depends(get_current_user)` in the signature) — matches the dominant pattern
   in the rest of the codebase; bigger diff; higher collateral-test-breakage risk.

**Decision:** Option 1 — add `require_permission_dep(permission)` to
`core.permissions`, and have the affected routers do
`from goldsmith_erp.core.permissions import require_permission_dep as require_permission`.

**Rationale:** Spec prefers Option 2 long-term but explicitly permits Option 1
("Option 2 is cleaner... unless a router has a reason the decorator can't
carry"). The A2 fix exists to eliminate the duplicate-enum security foot-gun;
Option 1 achieves that with the smallest behavioural delta and zero test
rewrites. A decorator-style unification can be a later stylistic refactor
without blocking the security fix now. All existing auth/permission tests
still pass with zero behavioural change.

**Decided by:** implementing agent (A2), within the Option-1/Option-2 latitude
explicitly granted by the spec.

---

## 2026-04-23 — A2 — Spec file count: 5 routers, not 4

**Question:** Spec says 4 routers imported `Permission` from `api.deps`, verified
by grep. When TDD-running the migration, the backend failed to boot with
`ImportError` from a 5th router.

**Investigation:** The spec's verification grep used
`from goldsmith_erp.api.deps import …` (absolute form).
`src/goldsmith_erp/api/routers/metal_inventory.py:25` uses the relative form
`from ...api.deps import get_current_user, require_permission, Permission`,
which the absolute-only grep missed.

**Decision:** Fix the 5th file as part of A2. Not a scope creep — the real goal
is "backend boots and no router imports Permission from api.deps"; leaving
`metal_inventory.py` behind would fail the existing acceptance criterion
("Backend container boots without ImportError") and silently re-introduce the
split the A2 fix exists to eliminate.

**Rationale:** Spec's "Files" list was enumerative (based on a specific grep),
not exhaustive (intent: every affected router). The broader acceptance criteria
(grep counts, boot success) are the source of truth. Scope-change is minimal
(same one-line import swap).

**Decided by:** implementing agent (A2), after TDD-run revealed the `ImportError`.

---

## 2026-04-23 — A2 — Update `tests/unit/test_auth_permissions.py` imports

**Question:** The existing `tests/unit/test_auth_permissions.py` imported
`has_permission`, `require_permission`, `Permission` from `api.deps`. The spec's
own TDD test asserts these are NO LONGER importable from `api.deps` (including
re-exports). The test file is not in the spec's "Files" section.

**Decision:** Update the test file's imports to pull from `core.permissions`
(with `require_permission_dep as require_permission` aliasing). No behavioural
change — all 22 pre-existing assertions still pass.

**Rationale:** The alternative — keeping an `api.deps` re-export shim for
backwards compatibility — is explicitly ruled out by the spec's TDD assertion
`test_single_permission_enum_defined_in_repo` (any re-export makes the import
succeed, which fails the test). A mechanical import-path update in one test
file is the smallest possible fix that keeps the acceptance criteria
internally consistent.

**Decided by:** implementing agent (A2).

---

## 2026-04-23 — A1 — request.state shape + audit DB session strategy

**Question:** (1) Should `AuthRequiredMiddleware` populate `request.state.user`
(full User object, requires a DB round-trip per request) or just
`request.state.user_id` (int from the JWT claim, no DB hit)? (2) How should
`AuditLoggingMiddleware.dispatch` obtain an `AsyncSession` given that
`BaseHTTPMiddleware` cannot use FastAPI's `Depends(get_db)`?

**Options considered:**

1. Populate `request.state.user` — matches existing dead code in
   `rate_limiting.py` and the old `audit_logging.py` but requires a DB
   select on every authenticated request.
2. Populate `request.state.user_id` only and rewrite `audit_logging.py` to
   drop `user_email`/`user_role` columns (they contain PII and post-
   `anonymize_user` are re-identifying — see F-25 in GDPR review).
3. For DB sessions in audit middleware: (a) call the dependency generator
   `get_db()` directly (bypasses `app.dependency_overrides` — tests can't
   swap the session), (b) open `AsyncSessionLocal()` inline (easy to patch
   in tests), (c) enqueue to Redis for a background writer (new
   infrastructure, out of Week-1 scope).

**Decision:**

- **`request.state.user_id` only** (option 2). Matches the "minimum data
  principle" in CLAUDE.md and avoids a mandatory per-request DB hit. The
  audit row keeps `user_id` as the FK; `user_email`/`user_role` columns on
  `CustomerAuditLog` are left as nullable and unused — a follow-up item
  (F-25 in the GDPR review) will decide whether to drop them, since they
  defeat the `anonymize_user` sentinel rewrite.
- **Audit DB session: `AsyncSessionLocal()` inline** (option 3b). Tests
  patch the factory reference on the middleware module (same pattern the
  `system_monitor` background loop already uses). A Redis-backed async
  writer is the right answer at scale and is tracked separately as
  F-24 in the GDPR review ("middleware DB write is synchronous").
- Also **trimmed the audit DB insert** to only the columns that actually
  exist on `CustomerAuditLog` — the prior code tried to write `endpoint`,
  `http_method`, `legal_basis`, `purpose`, `status_code`, `duration_ms`,
  none of which are columns in `db/models.py:2129`. Those live in
  `details` JSON instead.

**Rationale:** Ships a correctly-audited GET path today without inventing
new infrastructure. Both follow-ups are already tracked in the GDPR review
as distinct P-items, so no coverage is lost.

**Decided by:** implementing agent (A1).

---

## 2026-04-23 — A7 — Escalate: real CSRF exposure, scope is L not S+M

**Question:** Is the backend already running a double-submit CSRF token scheme
or SameSite=Strict on the auth cookie (→ Case A/C, FE-only or no-op), or is
this a genuine CSRF vulnerability requiring both BE middleware and FE
interceptor plumbing (→ Case B)?

**Investigation findings (per A7 spec checklist):**

1. `src/goldsmith_erp/api/routers/auth.py:67-75` — login sets ONE cookie:
   ```python
   response.set_cookie(
       key="access_token",
       value=token,
       httponly=True,
       secure=settings.COOKIE_SECURE,
       samesite="lax",             # CSRF protection
       max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
       path="/",
   )
   ```
   Same pattern at `:170-178` for `/refresh`. No second cookie (no `csrf_token`)
   is emitted. SameSite is **Lax**, not Strict. The inline comment "CSRF
   protection" overstates what Lax actually delivers — Lax still allows
   top-level cross-site POSTs from form submissions to slip through on some
   browser/legacy-stack combinations, and permits cross-site GETs (which can
   be state-changing in misconfigured APIs).
2. `src/goldsmith_erp/middleware/*.py` — contents: `audit_logging.py`,
   `auth_required.py`, `logging.py`, `rate_limiting.py`, `request_metrics.py`,
   `security_headers.py`. **No CSRF middleware exists.** No header-vs-cookie
   match check anywhere in the request path.
3. `src/goldsmith_erp/core/config.py:137` — only `COOKIE_SECURE` exists.
   No `COOKIE_SAMESITE`, no `CSRF_*` settings. The SameSite value is
   hardcoded `"lax"` in the router.
4. `frontend/src/api/client.ts:60-63` — interceptor is a pure pass-through:
   ```ts
   apiClient.interceptors.request.use(
     (config: InternalAxiosRequestConfig) => config,
     (error: AxiosError) => Promise.reject(error)
   );
   ```
   No cookie read, no header injection. `withCredentials: true` is set at
   line 17 — cookies flow cross-origin if CORS permits.

**Case determination: Case B.** SameSite=Lax + no double-submit + FE that
cannot help = real CSRF exposure on state-changing endpoints.

**Scope assessment:** The A7 spec permits the implementing agent to proceed
if Case B scope looks S+M, escalate if L. Realistic scope for a complete
Case B fix:

- New `CSRFMiddleware` (~80-120 LOC) with allow-list for public prefixes,
  GET/HEAD/OPTIONS skip, timing-safe header-vs-cookie comparison.
- Mint `csrf_token` cookie (non-HttpOnly, SameSite=Strict) on login, refresh,
  and ideally on first authenticated GET so SPA has it after reload.
- `main.py` wiring — **same file A1 just modified** (commit `38229c0`).
  Re-reading A1's output, middleware order is load-bearing:
  `AuthRequiredMiddleware` runs outermost, `AuditLoggingMiddleware` next.
  CSRF check must run AFTER auth (so 401 takes precedence over 403) and
  BEFORE audit (so rejected requests don't emit audit rows). That's a
  three-way ordering constraint with A1's pair.
- FE interceptor — trivial on its own, but needs coordinated rollout.
- **Test-fixture blast radius:** `tests/integration/test_auth_flow.py` and
  every integration test that does `await client.post/put/patch/delete(...)`
  currently sends no `X-CSRF-Token` header. Once the middleware lands, ALL
  of them break unless the shared fixture in `tests/conftest.py` is updated
  to read the csrf cookie and inject the header on every mutating request.
  That fixture touches is cross-cutting — outside a single-agent remit in a
  Wave-2 parallel batch.
- Product decision needed: token generation strategy (random per-session
  stored server-side vs stateless HMAC of session id vs signed double-submit).
  Not obvious which is best fit for this codebase.

**Decision:** **Escalate to orchestrator.** A7 remains 🛑 BLOCKED on Case B
scoping. Proposed sub-items for a future wave:

- **A7.1 (BE, M)** — CSRF middleware + csrf_token cookie emission in
  auth router + main.py wiring. Product decision on token strategy first.
- **A7.2 (tests, M)** — update `tests/conftest.py` auth fixture to inject
  `X-CSRF-Token` on mutating requests so integration suite stays green.
- **A7.3 (FE, S)** — interceptor reads `csrf_token` cookie, attaches
  `X-CSRF-Token` header on non-GET/HEAD/OPTIONS. Deploy after A7.1+A7.2.
- **A7.4 (P2, defence-in-depth)** — switch `samesite="lax"` → `"strict"`
  on the auth cookie, gated on UX testing (Strict breaks the "click email
  link → land logged-in" flow, which matters if the app ever sends email
  links; current app does not, so likely safe).

**Options considered before escalating:**

1. Proceed with Case B full implementation in this agent — rejected.
   The test-fixture update alone touches conftest.py, which per
   `CLAUDE.md` "Parallel Safety Rules" is one of the files to serialise
   around. F1 is concurrently refactoring conftests in this same wave.
2. Land only the FE interceptor as a placeholder — rejected. Without
   the cookie being minted BE-side, the header will always be empty,
   which the reviewer flagged as "no-op pass-through" today.
3. Land only the BE middleware + keep FE as-is — rejected. Instantly
   breaks every authenticated POST/PUT/PATCH/DELETE in both prod and the
   test suite.
4. **Escalate with structured sub-items (A7.1/.2/.3/.4)** — chosen.
   Keeps each future agent's remit tight and parallel-safe.

**Rationale:** The A7 brief's own Case B scoping language flags this as
"bigger scope, full work" and grants the implementing agent explicit
discretion to escalate on L-sized findings. The critical blocker is not
the middleware code (that's straightforward) but the cross-cutting test
fixture change + product call on token strategy. Both belong in a
planning pass, not a solo implementation run.

**Follow-up P1/P2:**
- P1 — orchestrator schedules A7.1/.2 as a coordinated pair in a future
  wave (not parallelisable with F1 on conftest).
- P2 — A7.4 (SameSite=Strict upgrade) can land independently of A7.1-.3
  and by itself closes the bulk of real-world CSRF exposure on any
  modern browser. Worth considering as an interim Wave-3 quick win.
- P2 — fix the misleading `"CSRF protection"` comment on `samesite="lax"`
  in auth.py; it overstates what Lax guarantees.

**Decided by:** implementing agent (A7), under the explicit escalation
clause in the A7 brief ("err toward … escalate if it looks L").

---

## 2026-04-23 — A3 — Frontend scope expansion + duplicate-email response for admins

**Question:** (1) The A3 spec lists only backend files, but the frontend ships
a full public `/register` route + `RegisterPage.tsx` + `authApi.register()`
that directly calls the now-locked-down endpoint. How deep should the
frontend clean-up go inside this commit? (2) Once the endpoint is
admin-only, should a duplicate email still return 400 "Email already
registered" to admins, or should the oracle be closed with a silent 201?

**Options considered:**

1. **Frontend scope — full delete.** Remove the `/register` route, delete
   `RegisterPage.tsx`, remove it from `pages/index.ts`, remove
   `authApi.register()` and `AuthContext.register()`. Cleanest, biggest
   diff, highest chance of colliding with `frontend/src/test/ScanFab.test.tsx`.
2. **Frontend scope — surgical.** Remove the `/register` route from
   `App.tsx`, remove the "Noch kein Konto? Registrieren" link from
   `LoginPage.tsx`, leave `RegisterPage.tsx`, its export, `authApi.register`,
   and `AuthContext.register` on disk as dormant code with no UI entry point.
3. **Escalate to Wave 3.** Mark A3 backend-only and file a separate frontend
   item.

*Duplicate-email response:*

4. Silent 201 (no-op) — admins lose the collision signal.
5. Keep 400 "Email already registered" for authenticated admin callers —
   the oracle only matters for unauthenticated callers, which the middleware
   now intercepts with 401 before the handler runs.

**Decision:** Option 2 + Option 5.

- **Frontend:** removed `/register` route + lazy `RegisterPage` import from
  `App.tsx`, dropped the `<Link to="/register">` from `LoginPage.tsx`
  (and its now-unused `Link` import). The catch-all route sends any
  bookmark of `/register` through `*` → `/dashboard` →
  (unauthenticated) → `/login`. `RegisterPage.tsx`, `pages/index.ts`
  export, `authApi.register()`, and `AuthContext.register()` are left on
  disk. A future "admin invitation" flow is the most natural consumer.
- **ScanFab:** `HIDDEN_PATHS` kept `'/register'` as defence-in-depth
  (harmless — the route is gone; the entry is a no-op guard). The
  existing ScanFab test that renders at `/register` still passes (13/13).
- **Duplicate email:** kept 400 for admins. With the middleware now
  returning 401 to unauthenticated callers before the handler runs,
  the oracle is closed at the transport layer. Admins legitimately
  need the collision signal so they can look up the existing account
  rather than silently creating a dead row. The new test
  `test_unauthenticated_duplicate_email_returns_401_not_400` covers the
  oracle-closure guarantee.

**Rationale:** Option 1 would balloon the diff across 5 more files and
complicate parallel-agent safety (other wave-2 agents don't touch these
files, but a bigger diff increases merge risk) for no security gain — dead
code with no entry point is already inert. Option 3 would leave a
public-looking `/register` route in the UI while the backend returns 401,
which is a worse UX than cleanly removing the route + link in the same
commit. Option 5 is the simplest signal-preserving choice; the security
guarantee lives at the middleware layer, not in the handler body.

**Decided by:** implementing agent (A3), under the spec's "document in
DECISIONS.md and fix in the same commit if the change is small" clause.

## 2026-04-23 — F1 — NullPool on Postgres test engine + pre-existing Makefile bug noted

**Question:** (1) When the integration conftest is flipped to Postgres via
`TEST_DATABASE_URL`, the concurrent-metal-consumption tests still fail — but
with a different, non-skip failure mode. Is that in scope to fix? (2) The
Makefile already has a pre-existing syntax error at line 287 (GNU Make can't
parse a bash heredoc inside a target body) which halts every `make` invocation.
Should F1 fix that so `make test-integration-pg` is actually runnable?

**Investigation:**

1. First PG run: failed with asyncpg's "Future attached to a different loop" on
   the default `QueuePool`. Root cause: asyncpg connections are pinned to the
   event loop that opened them; the session-scoped `event_loop` fixture + a
   connection pool that reuses connections across tests produces leaks between
   loops. SQLite/aiosqlite doesn't have this constraint, which is why the
   conftest shipped without `NullPool` for the whole ~4-year life of the file.
2. Switched the async test engine to `poolclass=NullPool` when the URL is not
   SQLite. Keeps SQLite on the default pool (it's fine there). One pool-line
   change inside the conftest I was already editing.
3. After that fix, the three concurrent tests advance further but still fail
   with `sqlalchemy.exc.ArgumentError: AsyncEngine expected, got Engine(...)`
   at `test_concurrent_metal_consumption.py:194` — the test calls
   `db_session.get_bind()` which returns the sync proxy, then passes it to
   `async_sessionmaker`. That's a genuine test-code bug that SQLite masked
   (on SQLite `get_bind()` returned something `async_sessionmaker` happened to
   accept). It is **pre-existing latent bug** in the test, outside the "Files"
   section of the F1 spec.
4. `make test-integration-pg --just-print` fails immediately on every system
   because `Makefile:287` contains `[Unit]` as a bare line inside a target body
   (an unclosed heredoc pattern). Pre-existing since commit `34ecffee`
   (2026-04-01). Fixing it would touch an unrelated `install-service` target.

**Decision:**

- **(1) NullPool for non-SQLite** — applied inside `tests/integration/conftest.py`
  (in scope, one-line `_engine_kwargs["poolclass"] = NullPool` branch). Tests
  now EXECUTE instead of skipping — F1's actual success criterion.
- **(1b) Leave the `get_bind()` latent bug in `test_concurrent_metal_consumption.py`**.
  That test file is NOT in F1's "Files" section and fixing it is a genuine
  scope creep (needs refactoring the factory to capture `test_engine` directly
  from conftest). The PG job will fail with a real, visible error instead of
  silently passing via skips — that's still a net win vs. the status quo
  (silent skips on SQLite). Escalated as follow-up F1.1.
- **(2) Leave `Makefile:287` bug alone**. Out of scope; the `test-integration-pg`
  target I added is correct GNU-Make syntax and would run fine on its own; the
  pre-existing `install-service` heredoc breaks the whole file for everyone
  today regardless of F1. Fixing it would widen the diff into a target that has
  nothing to do with integration-test infrastructure. Escalated as follow-up
  F1.2 (trivial: convert the heredoc into a shell-only subshell or write the
  systemd unit via `scripts/install-service.sh`).

**Follow-ups filed:**

- **F1.1** — Refactor `test_concurrent_metal_consumption.py` to use the
  module-level `test_engine` AsyncEngine directly instead of
  `db_session.get_bind()`. Size: S. Unblocks the new CI job turning green.
- **F1.2** — Convert `install-service` Makefile target's heredoc to an
  external script so `make` parses the Makefile at all. Size: XS. Blocks every
  local `make <anything>` invocation today.

**Rationale:** F1's locked scope (Option C, split conftests) was completed —
integration conftest now honors `TEST_DATABASE_URL`, a new CI job runs the
suite against real Postgres, and a local `make` target exists. The concurrent
tests are revealing real test-code bugs that were hidden by the SQLite
no-op behaviour — that's the intended outcome of the F1 fix, not a regression
caused by it. Keeping F1 tight keeps the Wave-2 parallel-safety envelope clean
(no cross-agent collision on test files or unrelated Makefile targets).

**Decided by:** implementing agent (F1), under the spec's explicit "fix if
small; escalate if large" clause for test-code dialect assumptions.

## 2026-04-24 — Week-1 branch self-review outcomes

**Who reviewed:** 3 parallel review agents (superpowers:code-reviewer, feature-dev:code-reviewer, TDD validator) audited the 15 Week-1 code commits.

**Verdict:** "Ship as-is for Week 1" (integration reviewer) / "Six intended closures substantively achieved" (security reviewer) / "TDD bar was held" (TDD validator). No P0 regressions introduced. 4 adversarial regressions injected into tests all failed → tests are real, not theatre.

**Findings actioned in this branch:**
- **R1 (P1, committed `071d542`)**: bulk `GET /api/v1/customers` was silently unaudited because `_log_to_database` returned early on `customer_id is None`. The comment ("separate list-access audit path — scoped out of A1") was false — no such path existed. R1 fix: removed the guard, added `action="list_accessed"` branch in dispatch, added 2 tests (list-logs-row + single-record-still-works regression). GDPR Art. 30 gap on bulk access closed.
- **R2 (P2, committed `60c4efd`)**: `/api/v1/users/register` was still advertised in the public OpenAPI/Swagger schema even after A3 locked it to ADMIN. Added `include_in_schema=False`. Now absent from `/openapi.json`. New test pins this.

**Findings NOT actioned, deferred to Week 2+ as known tech debt:**

- **P2 — Audit action string mismatch.** `audit_logging.py:241` uses `action="accessed"` but the A1 spec's acceptance criterion referenced `action="read"` (bracketed as "or the middleware's canonical read action"). Any future dashboard/report that filters `WHERE action = 'read'` will under-count. Mitigation: grep `rg "action.*=.*[\"']read[\"']"` across `src/` + `docs/` returned no matches at time of review (no consumer filters on the string today). Decision: stick with `"accessed"` + `"list_accessed"`; revisit if a consumer emerges.
- **P2 — Audit write is synchronous on response path.** `middleware/audit_logging.py:135-156` awaits the DB insert before returning — adds a second DB roundtrip to every audited request. Fine under light load; Week-2 perf sweep can push to `BackgroundTasks` or a buffered queue.
- **P2 — Audit pool contention.** `DB_POOL_SIZE=5 + overflow=10 = 15`. Audit path holds handler session + opens audit session sequentially. Raise pool size OR offload audit writes to a dedicated background writer with its own small pool. Worth sizing before first busy day.
- **P2 — Audit test coverage gaps.** Missing edge-case tests: (a) 404 on nonexistent customer still audits, (b) malformed JWT `sub` → `user_id=None` audit row, (c) POST-create path where `entity_id` backfills from response body. R1 handled the bulk-list gap; these three remain.
- **P2 — Swagger `/docs` is public.** `PUBLIC_PATHS` allows anonymous access to `/docs`/`/openapi.json` advertising the full API surface. R2 handles the specific `/users/register` case; the broader question (gate `/docs` behind ADMIN in production) is in the security review at `docs/review/2026-04-23/03-security-audit.md` P1.

**Decided by:** orchestrator based on 3 parallel reviews. Reviewers cross-confirmed no P0, no P1 regression on the 15-commit delta (only R1 was P1 and it's now committed).

---

<!-- Append new decisions below as they come up. -->

## 2026-04-24 — C6 — Financial-data audit: extension shape & deferred work

**Question:** How should the AuditLoggingMiddleware be extended to cover
invoices / valuations / scrap-gold, and which edge cases are in scope?

**Options considered:**

1. Per-resource action names (`invoice_read`, `valuation_read`, `scrap_gold_read`).
2. Generic `financial_read` action + per-resource `entity` discriminator.

**Decision:** Option 2.  `action="financial_read"` (single) /
`"list_accessed_financial"` (list) applies to all three financial
resources; the `entity` column (`invoice|valuation|scrap_gold`) narrows
when needed.  Matches the C6 spec.

**Rationale:**
- Dashboards answering "show me all financial-data reads by user X"
  become a one-line `WHERE action = 'financial_read'` filter.
- Per-resource drilldown is still trivially available via `entity`.
- Customer audit path is left untouched (action still `accessed` /
  `list_accessed`) — A1/R1 regression tests guarantee that.

**Other design points settled during implementation (not separate
decisions, but worth recording):**

- **Non-GET verbs on financial paths are NOT audited by this
  middleware.**  Only GETs, per spec.  Writes are audit-logged at the
  service layer (F-05 follow-up).  Customers keep per-verb audit (A1
  legacy).
- **`customer_audit_logs.customer_id` is populated ONLY for
  `entity="customer"` rows.**  That column FKs to `customers.id`; writing
  an invoice id there would violate referential integrity.  Non-customer
  rows use the generic `entity_id` column and leave `customer_id` NULL.
- **Legal basis differs for financial vs customer.**  Financial rows
  cite GDPR Art. 6(1)(c) (legal obligation; §147 AO).  Customer rows
  keep Art. 6(1)(b) (contract).  Surfaced in `details.legal_basis`.
- **Path parser is plain string split, not regex.**  Simpler to audit,
  predictable cost on the hot path.

**Deferred, logged here as follow-ups:**

- **C6.1** — `/api/v1/analytics/*` aggregates financial data but has its
  own path prefix.  Low risk (aggregates, not raw rows); not covered by
  the current resource map.  Add to the map in a later pass.
- **C6.2** — Rename table `customer_audit_logs` -> `access_audit_logs`.
  Cosmetic; needs a migration.  Save for a batched schema sweep.
- **C6.3** — `test_customer` conftest fixture currently fails in the
  working tree because C1 (not yet committed) added a NOT NULL
  `customers.email_hash` without updating the fixture.  Not a C6
  regression — C6's suite passes cleanly against `main` HEAD at the
  moment C6 was implemented.  When C1 lands, it must either set
  `email_hash=hmac_blind_index(email)` in the fixture or provide a
  server-side default, or the integration suite breaks for every agent
  that touches customer data.

**Decided by:** C6 implementing agent, constrained by spec + parallel-safety rules.
