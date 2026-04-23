# A2 — Merge duplicate `Permission` / `require_permission` systems

**Item:** A2 · **Severity:** P0 · **Effort:** M · **Owner:** BE + SEC
**Source:** `docs/review/2026-04-23/FIX-PLAN.md` Group A, flagged by reports 01, 03

## Context

Two independent `Permission` enums + `require_permission` implementations coexist:
- `src/goldsmith_erp/api/deps.py:108-217` — the **smaller** (~17 permissions) enum with `require_permission` as a FastAPI `Depends` factory.
- `src/goldsmith_erp/core/permissions.py:16-423` — the **authoritative** (~50+ permissions) enum with `require_permission` as a function decorator + `has_permission` helper.

**4 routers** currently import `Permission` from `api.deps` (verified 2026-04-23): `customers.py`, `measurements.py`, `metal_prices.py`, `metal_types.py`. The other 15+ routers use `core.permissions`. The smaller enum **omits** many permissions the larger one defines (INVOICE_*, QUOTE_*, VALUATION_*, HANDOFF_*, HALLMARK_*, REPAIR_*, SCAN_*, ML_*, NOTIFICATION_*, USER_CREATE/EDIT/DELETE). Role-to-permission maps also diverge, so role behaviour silently differs between the two halves of the codebase.

Latent privilege-escalation / silent-403 foot-gun.

## Goal

Single source of truth: `core.permissions` owns `Permission`, `ROLE_PERMISSIONS`, `has_permission`, `require_permission`. `api.deps` keeps only the auth-DI functions (`get_current_user`, `get_current_admin_user`, `get_token_from_cookie_or_header`, `get_db`). All routers import `Permission` + `require_permission` from `core.permissions`.

## Files

- **Modify** `src/goldsmith_erp/api/deps.py` — delete `class Permission`, `ROLE_PERMISSIONS`, `has_permission`, `require_permission` (lines ~108–217). Keep everything else untouched.
- **Modify** the 4 affected routers' imports:
  - `src/goldsmith_erp/api/routers/customers.py:13`
  - `src/goldsmith_erp/api/routers/measurements.py:21`
  - `src/goldsmith_erp/api/routers/metal_prices.py:27`
  - `src/goldsmith_erp/api/routers/metal_types.py:23`
- **Possibly modify** `src/goldsmith_erp/core/permissions.py` — if the existing `require_permission` is decorator-style only, add a companion FastAPI `Depends` factory (e.g. `has_permission_dep(perm)`) so migrated routers can preserve their current DI style. If all 4 routers only use it decorator-style (no `Depends(require_permission(...))`), skip this.
- **Create** `tests/unit/test_permission_registry.py` — fail-fast test that asserts every `Permission` enum value appears in `ROLE_PERMISSIONS`, and no role has undefined permission strings.

## Acceptance criteria

- [ ] `grep -rn "class Permission" src/goldsmith_erp/` returns exactly one match: `src/goldsmith_erp/core/permissions.py:16`.
- [ ] `grep -rn "def require_permission" src/goldsmith_erp/` returns exactly one match in `core/permissions.py`.
- [ ] `grep -rn "from goldsmith_erp.api.deps import.*Permission" src/goldsmith_erp/` returns zero matches.
- [ ] `pytest tests/unit/test_permission_registry.py -v` passes.
- [ ] All existing auth + routers tests pass unchanged (`pytest tests/ -k "permission or auth" -v`).
- [ ] Backend container boots without `ImportError` (spot-check via `make shell-backend` + `python -c "from goldsmith_erp.main import app"`, or via CI).

## Test design (TDD)

```python
# tests/unit/test_permission_registry.py
"""Registry invariants — protects against the A2 regression (duplicate enums)."""
import importlib
import pytest
from goldsmith_erp.core.permissions import Permission, ROLE_PERMISSIONS
from goldsmith_erp.db.models import UserRole

def test_every_permission_appears_in_at_least_one_role():
    all_granted = set().union(*ROLE_PERMISSIONS.values())
    missing = [p for p in Permission if p not in all_granted]
    assert not missing, f"Permissions defined but never granted to any role: {missing}"

def test_role_permissions_contain_only_defined_permissions():
    valid = set(Permission)
    for role, perms in ROLE_PERMISSIONS.items():
        extra = [p for p in perms if p not in valid]
        assert not extra, f"Role {role} references undefined permissions: {extra}"

def test_single_permission_enum_defined_in_repo():
    # Fail loud if someone re-introduces a duplicate in api/deps.py or elsewhere.
    try:
        from goldsmith_erp.api.deps import Permission as DepsPermission  # noqa
        pytest.fail("Duplicate Permission enum detected in api.deps — should be removed (A2 regression).")
    except ImportError:
        pass  # expected

def test_admin_has_all_permissions():
    assert set(ROLE_PERMISSIONS[UserRole.ADMIN]) == set(Permission)

@pytest.mark.parametrize("role", [UserRole.VIEWER, UserRole.GOLDSMITH, UserRole.ADMIN])
def test_every_role_has_at_least_one_permission(role):
    assert len(ROLE_PERMISSIONS[role]) > 0
```

Write this test first. Expected failure: `test_single_permission_enum_defined_in_repo` fails because the deps.py duplicate currently exists.

## Implementation sketch

1. **Read** `core/permissions.py:220-280` to know the exact `require_permission` signature.
2. **Check** how the 4 affected routers USE `require_permission` — if they use `Depends(require_permission(X))` (DI style), and `core.permissions.require_permission` is decorator-style, we need a `has_permission_dep` factory in `core.permissions`. If all usages are `@require_permission(X)` decorator-style, straight swap.
3. **Write failing test** (above).
4. **Delete** `class Permission`, `ROLE_PERMISSIONS`, `has_permission`, `require_permission` from `api/deps.py`.
5. **Change imports** in the 4 routers to `from goldsmith_erp.core.permissions import Permission, require_permission` (merging with any existing `core.permissions` imports the routers already have).
6. **Run** the new test + the full router suite: `pytest tests/ -v --maxfail=5`.
7. **Verify backend boots**: `poetry run python -c "from goldsmith_erp.main import app; print('OK')"` or via `make start`.

## Parallel-safety

Owns `api/deps.py`, `core/permissions.py`, and the 4 router files (`customers.py`, `measurements.py`, `metal_prices.py`, `metal_types.py`). **No other Wave-1 item touches these.** Note: D3 (time_tracking decorator) imports `Permission` — it already imports from `core.permissions` (verified 2026-04-23 grep), so no conflict. A3 (register) in Wave 2 touches `users.py` (already on `core.permissions`).

## Commit message

```
refactor(permissions): unify Permission enum and require_permission to core.permissions

Fix item A2 — a duplicate, smaller Permission enum in api.deps with a
divergent ROLE_PERMISSIONS map was used by 4 routers (customers,
measurements, metal_prices, metal_types). Future divergence would have
silently mis-gated endpoints. api.deps now keeps only the auth-DI
helpers. A registry-invariant test guards against re-introduction.

Ref: docs/fix-plan/2026-04-23/A2-permission-merge.md
Ref: docs/review/2026-04-23/FIX-PLAN.md#group-a

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

## Open questions for the implementing agent

- If the 4 routers use `Depends(require_permission(X))` (factory style, per api.deps) and `core.permissions.require_permission` is decorator-style only, you have two options:
  1. Add a `has_permission_dep(perm)` factory to `core.permissions` and migrate the 4 routers to call `Depends(has_permission_dep(X))`.
  2. Convert the 4 routers' usage to decorator style (`@require_permission(X)`), matching the rest of the codebase.
  Option 2 is the cleaner outcome long-term. Use it unless a router has a reason the decorator can't carry (e.g., dynamic permission lookup from path parameter).
- If `core.permissions.require_permission` uses `kwargs.get('current_user')` (see report 01 P1 finding), that's a **separate** item (1.8e) — do not touch it here.
