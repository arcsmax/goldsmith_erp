# A7 — CSRF token on cookie-auth state-changing requests

**Item:** A7 · **Severity:** P0 · **Effort:** L (escalated) · **Owner:** FE + BE + SEC · **Status:** 🛑 BLOCKED — ESCALATED 2026-04-23
**Blocked-by:** Product decision on token strategy + coordinated fixture refactor (see DECISIONS.md).

## 2026-04-23 — Investigation outcome (Wave 2 agent)

**Case B confirmed.** Backend uses `samesite="lax"` (auth.py:72, :175), no CSRF
middleware exists in `src/goldsmith_erp/middleware/`, no `csrf_token` cookie is
minted, and the FE interceptor at `frontend/src/api/client.ts:60-63` is a pure
pass-through. Real CSRF exposure on all cookie-authed state-changing endpoints.

Scope for a complete fix is **L**, not S+M as originally estimated, because:
- Integration test fixture in `tests/conftest.py` needs to inject `X-CSRF-Token`
  on every mutating request or the entire suite breaks — cross-cutting change
  that conflicts with concurrent F1 conftest work.
- Product decision needed on token strategy (random per-session vs stateless
  HMAC vs signed double-submit).
- Middleware ordering in `main.py` must integrate with A1's recent addition
  (AuditLogging + AuthRequired) — three-way constraint.

See `DECISIONS.md` → "2026-04-23 — A7 — Escalate" for the full analysis.

## Proposed sub-items for future waves

- **A7.1 (BE, M)** — `CSRFMiddleware` + `csrf_token` cookie emission in
  auth router + `main.py` wiring. Blocked-by: product call on token
  strategy.
- **A7.2 (tests, M)** — update `tests/conftest.py` authed-client fixture
  to inject `X-CSRF-Token` header on mutating requests. Must serialise
  after F1 (concurrent conftest refactor).
- **A7.3 (FE, S)** — interceptor reads `csrf_token` cookie, attaches
  `X-CSRF-Token` header on non-GET/HEAD/OPTIONS. Deploys after A7.1+A7.2.
- **A7.4 (P2)** — flip `samesite="lax"` → `"strict"` on the auth cookie
  (defence-in-depth; standalone; quick win). UX check: no email-link-based
  "land logged in" flows exist, so Strict is safe.


## Context

`frontend/src/api/client.ts:12-21` sets `withCredentials: true` (cookie-auth). The request interceptor at `:60-63` is a no-op — no CSRF token attached on `POST/PUT/PATCH/DELETE`. Cookie-authenticated endpoints are vulnerable to CSRF unless either (a) `SameSite=Strict` on the auth cookie AND browser-honored, or (b) a double-submit CSRF token pattern.

## Investigation needed (first step once unblocked)

1. Read `src/goldsmith_erp/api/routers/auth.py` (login handler) to confirm:
   - Does `response.set_cookie` currently use `samesite="strict"`, `samesite="lax"`, or default?
   - Is a `csrf_token` cookie emitted alongside the auth cookie?
2. If SameSite=Strict + no subresource CSRF risk → frontend still benefits from double-submit for defence-in-depth but P0 status can downgrade to P1.
3. If SameSite=Lax (default) or missing → **backend + frontend both need work**. Fix scope expands to:
   - Backend: add CSRF middleware that emits a `csrf_token` cookie (not HttpOnly) on login and on GET of any authenticated page; verifies `X-CSRF-Token` header matches cookie on state-changing requests.
   - Frontend: interceptor reads the cookie, attaches header for non-GET/HEAD/OPTIONS.

## Goal (once unblocked)

Every state-changing authenticated request carries a CSRF token that the backend verifies. CSRF attacks mitigated at a standard double-submit level.

## Next step

When Wave 2 begins, orchestrator will:
1. Spawn a small BE-focused exploration agent to confirm current SameSite + CSRF posture.
2. Based on the finding, either (a) promote this item to full BE+FE work or (b) downgrade scope to FE-only interceptor plumbing for a pre-existing `csrf_token` cookie.
3. Update this spec with the TDD plan.
