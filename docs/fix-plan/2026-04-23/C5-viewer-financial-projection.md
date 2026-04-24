# C5 — VIEWER role strips financial fields from Order responses

**Item:** C5 · **Severity:** P0 · **Effort:** M · **Owner:** BE + GDPR
**Source:** `docs/review/2026-04-23/FIX-PLAN.md` Group C, report 04 finding F-04
**Decision locked (2026-04-24):** VIEWER sees NO financial fields.

## Context

CLAUDE.md "Data Privacy Rules":
> **Financial Data:** Pricing, payment info, material costs → visible only to ADMIN and GOLDSMITH roles

Current state:
- `core/permissions.py:175-199` — `UserRole.VIEWER` has `ORDER_VIEW`.
- `models/order.py:294-344` — `OrderRead` Pydantic schema returns `price`, `material_cost_calculated`, `material_cost_override`, `labor_cost`, `hourly_rate`, `profit_margin_percent`, `calculated_price` (lines 313-323) to everyone with `ORDER_VIEW`.
- `api/routers/orders.py:20-30` — GET endpoints use `OrderRead` unconditionally.
- Scanner service already has the right pattern: `scanner_service.py:176 ORDER_FIELDS_BY_ROLE` — a role-keyed field allowlist. The REST API never uses it.

## Goal

VIEWER-role responses to `GET /api/v1/orders/*` contain NO financial fields:
- ❌ `price`
- ❌ `material_cost_calculated`
- ❌ `material_cost_override`
- ❌ `labor_cost`
- ❌ `hourly_rate`
- ❌ `profit_margin_percent`
- ❌ `calculated_price`
- ❌ `cost_breakdown` (if present)
- ❌ any `material.*` field that exposes cost

ADMIN and GOLDSMITH responses unchanged.

Approach: introduce `OrderReadViewer` — a narrower Pydantic schema — and have the router/service pick the right schema based on `current_user.role`. Alternative: use Pydantic's `model_dump(exclude=...)` with a role-derived exclude set.

**Prefer separate `OrderReadViewer` model** — self-documenting via the schema + easier to test.

## Files

- **Modify** `src/goldsmith_erp/models/order.py` — define `OrderReadViewer` as a subset of `OrderRead`. Alternative: `OrderReadFinancial` as the extension, and `OrderReadBase` without. Pick whichever aligns with existing inheritance patterns.
- **Modify** `src/goldsmith_erp/api/routers/orders.py` — for every `response_model=OrderRead` (or `List[OrderRead]`), pick the schema based on the caller's role. Cleanest: the service layer returns the ORM object; the router decides the schema in `response_model`. Options:
  - **Option A — two endpoint variants**: ugly, doubles route surface.
  - **Option B — `response_model_exclude` per-request**: FastAPI supports it. Use `response_model_exclude` set computed from role via a FastAPI dependency. Simple, minimal code change.
  - **Option C — custom Pydantic serializer**: verbose.
  - **Recommend Option B**.
- **Modify** `src/goldsmith_erp/services/order_service.py` — OPTIONALLY add a `project_for_role(order, role) -> dict` helper if the router pattern isn't expressive enough. Prefer not touching the service if router-level projection works.
- **Create** `tests/integration/test_order_viewer_projection.py` — integration tests covering VIEWER/GOLDSMITH/ADMIN for list + detail endpoints.

## Acceptance criteria

- [ ] `GET /api/v1/orders/` authenticated as VIEWER returns orders WITHOUT the 7 listed financial fields (verified by asserting the JSON body).
- [ ] Same request as GOLDSMITH or ADMIN returns orders WITH those fields.
- [ ] `GET /api/v1/orders/{id}` same pattern.
- [ ] Existing order-related tests still pass.
- [ ] OpenAPI schema reflects the differentiation (either `OrderReadViewer` appears, or `response_model_exclude` is documented).
- [ ] Frontend unaffected (VIEWER-role frontend sessions won't see the fields, but no existing frontend code expects to render them as VIEWER, so no frontend work needed — verify by grepping `frontend/src/` for `profit_margin_percent`, `material_cost_calculated` — these should not appear in VIEWER-visible components).

## Test design (TDD)

```python
# tests/integration/test_order_viewer_projection.py
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

FINANCIAL_FIELDS = {
    "price", "material_cost_calculated", "material_cost_override",
    "labor_cost", "hourly_rate", "profit_margin_percent", "calculated_price",
}

class TestOrderRoleProjection:
    async def test_viewer_sees_no_financial_fields_on_list(
        self, authenticated_client_viewer: AsyncClient, test_order,
    ):
        resp = await authenticated_client_viewer.get("/api/v1/orders/")
        assert resp.status_code == 200
        orders = resp.json()
        assert orders, "need at least one order"
        leaked = FINANCIAL_FIELDS & set(orders[0].keys())
        assert not leaked, f"VIEWER leaked financial fields: {leaked}"

    async def test_viewer_sees_no_financial_fields_on_detail(
        self, authenticated_client_viewer, test_order,
    ):
        resp = await authenticated_client_viewer.get(f"/api/v1/orders/{test_order.id}")
        assert resp.status_code == 200
        leaked = FINANCIAL_FIELDS & set(resp.json().keys())
        assert not leaked

    async def test_goldsmith_sees_financial_fields(
        self, authenticated_client_goldsmith, test_order,
    ):
        resp = await authenticated_client_goldsmith.get(f"/api/v1/orders/{test_order.id}")
        body = resp.json()
        # Expect at least `price` and `calculated_price` present for GOLDSMITH
        assert "price" in body
        assert "calculated_price" in body

    async def test_admin_sees_financial_fields(
        self, authenticated_client_admin, test_order,
    ):
        resp = await authenticated_client_admin.get(f"/api/v1/orders/{test_order.id}")
        body = resp.json()
        assert "price" in body
        assert "calculated_price" in body

    async def test_openapi_documents_viewer_projection(self, client):
        resp = await client.get("/api/v1/openapi.json")
        # Either an OrderReadViewer schema exists, OR the orders endpoint
        # documents response_model_exclude in some way. Specifically check
        # that the financial field list isn't advertised as always-present
        # without any role gating hint.
        schema = resp.json()
        # Implementation-specific assertions — adapt to whichever approach lands.
```

## Implementation sketch (Option B)

```python
# api/routers/orders.py

from fastapi import Depends
from goldsmith_erp.core.permissions import has_permission, Permission
from goldsmith_erp.db.models import UserRole, User as UserModel

def _financial_excludes_for_role(user: UserModel) -> set[str]:
    """Return the set of fields to exclude from an Order response based on role."""
    # Only ADMIN + GOLDSMITH see financial fields.
    if user.role in (UserRole.ADMIN, UserRole.GOLDSMITH):
        return set()
    return {
        "price", "material_cost_calculated", "material_cost_override",
        "labor_cost", "hourly_rate", "profit_margin_percent", "calculated_price",
    }

@router.get("/{order_id}", response_model=OrderRead)
@require_permission(Permission.ORDER_VIEW)
async def get_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user),
):
    order = await OrderService.get_order(db, order_id)
    return ORJSONResponse(
        OrderRead.model_validate(order).model_dump(
            exclude=_financial_excludes_for_role(current_user)
        )
    )
```

**Prefer** using FastAPI's built-in `response_model_exclude` via a Depends-computed set if possible. If FastAPI doesn't cleanly support per-request exclude sets in the decorator (this is a known limitation), return a plain `JSONResponse` with `model_dump(exclude=...)` as above.

Apply the same pattern to list endpoint, and any other handler that returns `OrderRead`.

## Parallel-safety

Owns:
- MODIFIED: `src/goldsmith_erp/models/order.py`, `src/goldsmith_erp/api/routers/orders.py`, optionally `services/order_service.py`
- NEW: `tests/integration/test_order_viewer_projection.py`

No conflict with C1/C4/C6 (different files).

## Commit message

```
feat(orders): strip financial fields from VIEWER-role responses (C5)

Fix item C5 — VIEWERs previously saw price, material_cost_*,
labor_cost, hourly_rate, profit_margin, calculated_price on every
GET /orders response, violating CLAUDE.md "Financial data → ADMIN
and GOLDSMITH only." Per-request response_model_exclude driven by
role now strips these 7 fields for VIEWER; ADMIN and GOLDSMITH
unchanged. Scanner service already had the right pattern; the
REST API now matches.

Ref: docs/fix-plan/2026-04-23/C5-viewer-financial-projection.md
Ref: docs/review/2026-04-23/FIX-PLAN.md#group-c

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

## Open questions for the implementing agent

- If the order is embedded inside another response (e.g., `CustomerRead` includes orders), the role projection needs to propagate. Check — and if so, extend projection to those endpoints too. Document in DECISIONS.md if scope expands.
- WebSocket events that broadcast `order_updated` — do they include financial fields? If so, should a VIEWER-connected WebSocket client receive the redacted payload? Probably yes; file as follow-up if the WS broadcast path is not trivial to project.
- Any analytics/reports endpoint that VIEWER can hit and that indirectly exposes financial data (aggregate revenue, etc.)? Grep `api/routers/analytics.py` — may be a follow-up C5.1.
