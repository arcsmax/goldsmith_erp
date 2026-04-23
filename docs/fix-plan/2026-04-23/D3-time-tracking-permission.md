# D3 — Add `@require_permission` to `GET /time-tracking/user/{user_id}`

**Item:** D3 · **Severity:** P0 · **Effort:** S · **Owner:** BE + SEC
**Source:** `docs/review/2026-04-23/FIX-PLAN.md` Group D, flagged by report 01

## Context

`src/goldsmith_erp/api/routers/time_tracking.py:115-135` defines `GET /time-tracking/user/{user_id}` with only `Depends(get_current_user)` and a manual `check_ownership_or_permission` check in the body. **It has no `@require_permission` decorator**, in violation of CLAUDE.md's standard *"All new endpoints must have @require_permission decorator"*.

Current state (verified 2026-04-23):

```python
@router.get("/user/{user_id}", response_model=List[TimeEntryRead])
async def get_time_entries_for_user(
    user_id: int,
    start_date: Optional[datetime] = Query(None, ...),
    end_date: Optional[datetime] = Query(None, ...),
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Check if user owns resource or has permission to view all time entries
    if not check_ownership_or_permission(user_id, current_user, Permission.TIME_VIEW_ALL):
        raise HTTPException(status_code=403, detail="Permission denied: ...")

    return await TimeTrackingService.get_time_entries_for_user(...)
```

The next handler (`POST /`) uses `@require_permission(Permission.TIME_TRACK)` — the convention is well-established in this file.

## Goal

`GET /time-tracking/user/{user_id}` is gated by `@require_permission(Permission.TIME_VIEW_OWN)` (the minimum permission every authenticated time-tracking user has), with the in-body ownership/`TIME_VIEW_ALL` ladder preserved. A user with NO `TIME_VIEW_OWN` permission receives `403` without even reaching the handler body.

## Files

- **Modify** `src/goldsmith_erp/api/routers/time_tracking.py` — add decorator above `async def get_time_entries_for_user`.
- **Create or extend** `tests/integration/test_time_tracking_permissions.py` — integration test asserting 403 for unauthenticated/unauthorized users.

## Acceptance criteria

- [ ] The decorator `@require_permission(Permission.TIME_VIEW_OWN)` is present above `get_time_entries_for_user`.
- [ ] The in-body `check_ownership_or_permission(user_id, current_user, Permission.TIME_VIEW_ALL)` check remains — it handles the "can I see OTHER users' entries" case.
- [ ] Integration test: unauthenticated request → 401 (existing behavior from middleware; don't break).
- [ ] Integration test: user with `TIME_VIEW_OWN` requesting OWN user_id → 200.
- [ ] Integration test: user with `TIME_VIEW_OWN` only (no `TIME_VIEW_ALL`) requesting OTHER user_id → 403 with the ownership-message body.
- [ ] Integration test: user with `TIME_VIEW_ALL` requesting any user_id → 200.
- [ ] Integration test: user with NO time permissions at all → 403 from the decorator (not the in-body check), message "Permission denied" or similar.
- [ ] All existing `time_tracking` tests still pass.

## Test design (TDD)

If `tests/integration/test_time_tracking_permissions.py` already exists, add to it. Otherwise create it:

```python
# tests/integration/test_time_tracking_permissions.py
import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
class TestTimeTrackingUserEndpointPermissions:
    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.get("/api/v1/time-tracking/user/1")
        assert resp.status_code == 401

    async def test_user_with_view_own_can_see_own_entries(
        self, authenticated_client_viewer, viewer_user,
    ):
        resp = await authenticated_client_viewer.get(
            f"/api/v1/time-tracking/user/{viewer_user.id}"
        )
        assert resp.status_code == 200

    async def test_user_with_view_own_cannot_see_other_user_entries(
        self, authenticated_client_viewer, other_user,
    ):
        resp = await authenticated_client_viewer.get(
            f"/api/v1/time-tracking/user/{other_user.id}"
        )
        assert resp.status_code == 403

    async def test_user_with_view_all_can_see_any_user_entries(
        self, authenticated_client_admin, other_user,
    ):
        resp = await authenticated_client_admin.get(
            f"/api/v1/time-tracking/user/{other_user.id}"
        )
        assert resp.status_code == 200

    async def test_user_missing_view_own_gets_403_from_decorator(
        self, authenticated_client_no_time_perms, other_user,
    ):
        """The decorator must gate access BEFORE the in-body ownership check runs."""
        resp = await authenticated_client_no_time_perms.get(
            f"/api/v1/time-tracking/user/{other_user.id}"
        )
        assert resp.status_code == 403
        # The decorator's message should be distinguishable from the in-body one.
        # Matching on phrases is brittle; prefer matching on structured error code
        # if one exists — otherwise document the expected phrase in DECISIONS.md.
```

Fixtures `authenticated_client_viewer`, `authenticated_client_admin`, `authenticated_client_no_time_perms`, `viewer_user`, `other_user` either exist in `tests/integration/conftest.py` (report 06 confirmed `viewer_auth_headers` + `goldsmith_auth_headers` + `admin_auth_headers`) or need creating. Read conftest first to reuse.

## Implementation sketch

```python
@router.get("/user/{user_id}", response_model=List[TimeEntryRead])
@require_permission(Permission.TIME_VIEW_OWN)
async def get_time_entries_for_user(
    user_id: int,
    start_date: Optional[datetime] = Query(None, ...),
    end_date: Optional[datetime] = Query(None, ...),
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if not check_ownership_or_permission(user_id, current_user, Permission.TIME_VIEW_ALL):
        raise HTTPException(status_code=403, detail="...")
    ...
```

Preserve the import statement — `Permission` and `require_permission` are both imported at the top of this file (confirmed via the initial grep that `time_tracking.py` uses `core.permissions`). No new imports required.

## Parallel-safety

Owns `src/goldsmith_erp/api/routers/time_tracking.py`. **A2 does NOT touch this file** (verified: A2's 4 target routers are customers/measurements/metal_prices/metal_types). No Wave-1 conflict.

**Ordering note**: D3 can run fully in parallel with A2. Both import `Permission` from `core.permissions` already — A2's work is moving 4 OTHER routers onto `core.permissions`. D3 is adding one decorator to a file already on `core.permissions`.

## Commit message

```
fix(time-tracking): add @require_permission to GET /user/{user_id}

Fix item D3 — the endpoint relied on an in-body ownership check only,
violating CLAUDE.md's "every new endpoint must have @require_permission"
standard. The decorator now gates access BEFORE the ownership/
TIME_VIEW_ALL ladder; ladder is preserved for cross-user lookups.

Ref: docs/fix-plan/2026-04-23/D3-time-tracking-permission.md
Ref: docs/review/2026-04-23/FIX-PLAN.md#group-d

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

## Open questions for the implementing agent

- If `require_permission` is currently a decorator that reads `kwargs.get('current_user')` (per report 01 P1 finding 1.8e), verify it plays correctly with a route that ALSO has `Depends(get_current_user)` injecting the same param. It should — `current_user` is in `kwargs` either way — but a quick sanity `curl` after the change is cheap insurance.
- The decorator-then-ownership-check two-stage pattern is intentional — do not consolidate the 403 paths. The decorator's role is "you have NO time permissions at all"; the in-body check's role is "you have the own-view permission but are asking about someone else."
