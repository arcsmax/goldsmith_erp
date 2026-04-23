# A7 — CSRF token on cookie-auth state-changing requests

**Item:** A7 · **Severity:** P0 · **Effort:** S (FE) + M (BE, if infra missing) · **Owner:** FE + BE + SEC · **Status:** 🛑 BLOCKED
**Blocked-by:** Need to verify current backend CSRF state before scoping.

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
