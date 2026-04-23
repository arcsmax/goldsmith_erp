# A3 — Lock down `/users/register` to ADMIN-invitation-only

**Item:** A3 · **Severity:** P0 · **Effort:** S · **Owner:** BE + SEC
**Status:** ⏳ pending (policy decision landed 2026-04-23)
**Source:** `docs/review/2026-04-23/FIX-PLAN.md` Group A, flagged by reports 01, 03
**Decision:** Option 1 — **ADMIN-invitation-only** (per user AskUserQuestion 2026-04-23). See DECISIONS.md.

## Context

`middleware/auth_required.py:29` whitelists `/api/v1/users/register` as PUBLIC. `api/routers/users.py:19-43` accepts any `(email, password)` with no invitation token, no captcha, no admin approval. 400 "Email already registered" is a free email-enumeration oracle.

A2 (commit `17d1056`) already migrated this router to `core.permissions`, so `require_permission` is available.

## Goal

- `/users/register` is no longer anonymously callable. Unauthenticated POST → 401.
- Admin-authenticated POST → 201 as today.
- Duplicate-email response identical to unknown-email response (no oracle).
- Existing admin flows still work.

## Files

- **Modify** `src/goldsmith_erp/middleware/auth_required.py` — remove `/api/v1/users/register` from `PUBLIC_PATHS`.
- **Modify** `src/goldsmith_erp/api/routers/users.py` — add `@require_permission(Permission.USER_MANAGE)` (or `USER_CREATE` if it exists) above `register_user`. Consider renaming the route to something ADMIN-semantic (e.g. `POST /users`) OR keep `/register` for back-compat with ADMIN gating — simpler.
  - Remove the 400-vs-201 enumeration oracle: return 201 regardless of whether the email existed (treat duplicate as no-op at the API layer; leave a server-side log for ADMIN awareness). Alternative: keep 400 but only to authenticated admins — that's fine since the oracle only matters for unauthenticated callers.
- **Extend** `tests/integration/test_auth_flow.py` or a new `tests/integration/test_user_registration.py` — assert:
  - Unauthenticated POST → 401
  - Authenticated-but-non-admin POST → 403
  - Admin POST with new email → 201
  - Admin POST with duplicate email → either 409 (if we keep the signal for admins) or 201 (if we want identical); DECIDE and DOCUMENT.

## Acceptance criteria

- [ ] `grep -n "/api/v1/users/register" src/goldsmith_erp/middleware/auth_required.py` returns 0 matches (removed from PUBLIC_PATHS).
- [ ] `register_user` handler has `@require_permission(Permission.USER_MANAGE)` (or the equivalent admin-level perm).
- [ ] New integration tests pass (TDD flow: failing test first).
- [ ] All existing auth/user tests pass: `pytest tests/ -k "user or auth" -v`.
- [ ] Admin-creates-user flow still works end-to-end (integration test covers it).
- [ ] No regression in frontend — the admin UI's user-creation page still works if one exists.

## Test design (TDD)

Write first. Must fail against HEAD (endpoint is currently public). Then fix. Confirm pass.

```python
# tests/integration/test_user_registration.py
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

class TestUserRegistrationLockdown:
    async def test_unauthenticated_cannot_register(self, client: AsyncClient):
        resp = await client.post(
            "/api/v1/users/register",
            json={"email": "attacker@evil.com", "password": "S3cr3tp@ss!", "first_name": "X", "last_name": "Y"},
        )
        assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"

    async def test_non_admin_cannot_register(
        self, authenticated_client_goldsmith: AsyncClient,
    ):
        resp = await authenticated_client_goldsmith.post(
            "/api/v1/users/register",
            json={"email": "new@example.com", "password": "S3cr3tp@ss!", "first_name": "X", "last_name": "Y"},
        )
        assert resp.status_code == 403

    async def test_admin_can_register(self, authenticated_client_admin: AsyncClient):
        resp = await authenticated_client_admin.post(
            "/api/v1/users/register",
            json={"email": "new-admin-created@example.com", "password": "S3cr3tp@ss!", "first_name": "X", "last_name": "Y"},
        )
        assert resp.status_code == 201

    async def test_duplicate_email_does_not_leak_existence(
        self, authenticated_client_admin: AsyncClient, existing_user,
    ):
        """Decision: duplicate must match unknown to remove the oracle.
        Either both 201 (silent no-op) or both 409 — pick one and assert it.
        Current implementation returns 409 to admins (acceptable — admin can see)
        but MUST return 401 to unauthenticated callers (no oracle leak)."""
        resp = await authenticated_client_admin.post(
            "/api/v1/users/register",
            json={"email": existing_user.email, "password": "S3cr3tp@ss!", "first_name": "X", "last_name": "Y"},
        )
        assert resp.status_code in (201, 409)  # either is fine for admins

    async def test_unauthenticated_duplicate_email_returns_401_not_400(
        self, client: AsyncClient, existing_user,
    ):
        """The fatal bug: pre-fix this returned 400 'Email already registered',
        leaking existence. Post-fix it's 401 (no oracle)."""
        resp = await client.post(
            "/api/v1/users/register",
            json={"email": existing_user.email, "password": "X", "first_name": "X", "last_name": "Y"},
        )
        assert resp.status_code == 401, "Must not differentiate 401 vs 400 on email existence"
```

## Implementation sketch

1. Read `auth_required.py` — find `PUBLIC_PATHS`, remove the `/api/v1/users/register` line.
2. Read `users.py::register_user` — add `@require_permission(Permission.USER_MANAGE)` above. (If `USER_CREATE` is a separate, narrower permission in the enum, prefer that.)
3. Confirm `require_permission` already imported (post-A2, this router imports from `core.permissions`).
4. Run the new failing tests → pass.
5. Run `pytest tests/ -k "user or auth"` → all pass.
6. Commit.

## Parallel-safety

Touches `auth_required.py` and `users.py`. **No other Wave-2 item touches these.** F2a is DB/migration only, A7 is frontend + possibly different backend files (not users.py), F1 is CI.

## Commit message

```
feat(auth): lock /users/register to ADMIN-invitation-only

Fix item A3 — removed /api/v1/users/register from PUBLIC_PATHS and
gated register_user with @require_permission(Permission.USER_MANAGE).
Unauthenticated POST now returns 401 across all paths (email /
password existence), closing the enumeration oracle. Admins continue
to create users via the same endpoint.

Ref: docs/fix-plan/2026-04-23/A3-register-endpoint.md
Ref: docs/review/2026-04-23/FIX-PLAN.md#group-a

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

## Open questions for the implementing agent

- Is there a `USER_CREATE` permission distinct from `USER_MANAGE`? Pick the narrower one if so.
- If the frontend has a /register route that calls this endpoint, that page should also be removed or re-routed to /login. Check `frontend/src/App.tsx` for the route + `grep -rn "/register\|register_user" frontend/src/`. If yes, DOCUMENT in DECISIONS.md and remove in the same commit.
