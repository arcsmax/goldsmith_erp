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

<!-- Append new decisions below as they come up. -->
