# C6 — Audit-log financial data reads (invoices, valuations, scrap_gold)

**Item:** C6 · **Severity:** P0 · **Effort:** M · **Owner:** BE + GDPR
**Source:** `docs/review/2026-04-23/FIX-PLAN.md` Group C, report 04 finding F-05

## Context

CLAUDE.md "Data Privacy Rules":
> **Financial Data:** All financial data access MUST be audit-logged

Current state (report 04):
- `api/routers/invoices.py`, `api/routers/valuations.py`, `api/routers/scrap_gold.py` — GET handlers enforce `*_VIEW` permissions but NO `CustomerAuditLog` row is written when an invoice / valuation / scrap-gold record is fetched.
- `AuditLoggingMiddleware` (A1, commit `38229c0`) currently logs `/api/v1/customers/*` accesses. It does NOT cover `/invoices`, `/valuations`, `/scrap-gold`.
- R1 (commit `071d542`) extended the middleware to also log bulk customer list accesses. Same approach applies here.

## Goal

Every GET on `/api/v1/invoices/*`, `/api/v1/valuations/*`, `/api/v1/scrap-gold/*` produces a `CustomerAuditLog` row with `action="financial_read"`, `entity_type` set to the resource kind (`"invoice"`, `"valuation"`, `"scrap_gold"`), `user_id` from JWT, `timestamp`, `ip_address`. Failures of the audit write are logged but do NOT fail the user request.

## Files

- **Modify** `src/goldsmith_erp/middleware/audit_logging.py` — extend path-parsing logic to recognize invoices/valuations/scrap_gold paths and emit the right `entity_type` + `action`.
  - Currently `_extract_customer_id` handles only `/customers/...`. Add similar extractors (or generalize) for the 3 financial resource paths.
  - The `entity_type` column on `CustomerAuditLog` is generic — use it with values `"invoice"`, `"valuation"`, `"scrap_gold"` (not just `"customer"`).
  - The action for financial reads: `"financial_read"` (new, distinct from `"accessed"`/`"list_accessed"` used for customer reads) — easier for downstream reporting to filter "show me all financial reads by user X".
- **Modify** `src/goldsmith_erp/db/models.py` — if `CustomerAuditLog.entity_type` is not already nullable string, no change needed. Verify.
- **Possibly create** `src/goldsmith_erp/api/deps.py` helper — a FastAPI `audit_access(entity, entity_id)` dependency for explicit per-handler audit calls (alternative to middleware approach). **Prefer middleware** — it's closer to the A1/R1 approach and requires no handler changes.
- **Create** `tests/integration/test_financial_audit.py` — tests for each of the 3 resource kinds:
  - GET single record → audit row with correct `action`, `entity_type`, `entity_id`, `user_id`
  - GET list → audit row with `entity_id=None`, same entity_type
  - Unauthenticated → 401, no audit row (auth fails first)
  - Audit DB failure → request still succeeds

## Acceptance criteria

- [ ] `GET /api/v1/invoices/` (list) → 1 audit row with `entity_type="invoice"`, `action="list_accessed_financial"` (or the naming your impl uses; be consistent).
- [ ] `GET /api/v1/invoices/{id}` → 1 audit row with `entity_type="invoice"`, `entity_id="<id>"`, `action="financial_read"`.
- [ ] Same pattern for `/valuations/` and `/scrap-gold/`.
- [ ] All existing A1 + R1 tests still pass (customer auditing unchanged).
- [ ] Backend boots, routes are unchanged.

## Test design (TDD)

```python
# tests/integration/test_financial_audit.py
import pytest
from sqlalchemy import select
from goldsmith_erp.db.models import CustomerAuditLog

pytestmark = pytest.mark.asyncio

class TestFinancialAudit:
    async def test_invoice_get_writes_audit_row(
        self, authenticated_client_admin, db_session, test_invoice,
    ):
        resp = await authenticated_client_admin.get(f"/api/v1/invoices/{test_invoice.id}")
        assert resp.status_code == 200

        result = await db_session.execute(
            select(CustomerAuditLog)
            .where(CustomerAuditLog.entity_type == "invoice")
            .where(CustomerAuditLog.entity_id == str(test_invoice.id))
            .order_by(CustomerAuditLog.timestamp.desc())
            .limit(1)
        )
        row = result.scalar_one_or_none()
        assert row is not None
        assert row.action == "financial_read"
        assert row.user_id is not None

    async def test_invoice_list_writes_audit_row(
        self, authenticated_client_admin, db_session,
    ):
        resp = await authenticated_client_admin.get("/api/v1/invoices/")
        assert resp.status_code == 200
        result = await db_session.execute(
            select(CustomerAuditLog)
            .where(CustomerAuditLog.entity_type == "invoice")
            .where(CustomerAuditLog.entity_id.is_(None))
            .order_by(CustomerAuditLog.timestamp.desc())
            .limit(1)
        )
        assert result.scalar_one_or_none() is not None

    # Same pattern for valuations, scrap_gold
    @pytest.mark.parametrize("resource,factory_fixture", [
        ("valuations", "test_valuation"),
        ("scrap-gold", "test_scrap_gold"),
    ])
    async def test_other_financial_resources_audit(
        self, resource, factory_fixture, request,
        authenticated_client_admin, db_session,
    ):
        fixture = request.getfixturevalue(factory_fixture)
        resp = await authenticated_client_admin.get(f"/api/v1/{resource}/{fixture.id}")
        assert resp.status_code == 200
        # entity_type uses underscore form
        entity_type = resource.replace("-", "_")
        result = await db_session.execute(
            select(CustomerAuditLog)
            .where(CustomerAuditLog.entity_type == entity_type)
            .where(CustomerAuditLog.entity_id == str(fixture.id))
            .limit(1)
        )
        assert result.scalar_one_or_none() is not None
```

## Implementation sketch

Extend `_extract_customer_id` (or generalize to `_extract_entity_from_path`):

```python
# middleware/audit_logging.py — pseudocode
RESOURCE_ROUTES = {
    "customers": ("customer", "accessed", "list_accessed"),
    "invoices": ("invoice", "financial_read", "list_accessed_financial"),
    "valuations": ("valuation", "financial_read", "list_accessed_financial"),
    "scrap-gold": ("scrap_gold", "financial_read", "list_accessed_financial"),
}

def _extract_audit_context(path: str) -> tuple[str, str, Optional[str]] | None:
    """Return (entity_type, action, entity_id) for audited paths, else None."""
    # Path format: /api/v1/{resource}[/{id}][/...]
    parts = path.strip("/").split("/")
    if len(parts) < 3 or parts[0] != "api" or parts[1] != "v1":
        return None
    resource = parts[2]
    config = RESOURCE_ROUTES.get(resource)
    if not config:
        return None
    entity_type, action_single, action_list = config
    if len(parts) >= 4 and parts[3].isdigit():
        return entity_type, action_single, parts[3]
    return entity_type, action_list, None
```

Then `_log_to_database` uses the returned tuple instead of the hardcoded `customer_id` + `"accessed"`.

**Key consideration:** the R1 commit made the middleware log list endpoints. C6 is a superset — it adds 3 more resource kinds. Merge carefully.

## Parallel-safety

Owns:
- MODIFIED: `src/goldsmith_erp/middleware/audit_logging.py`
- NEW: `tests/integration/test_financial_audit.py`

**HEAVY WARNING**: `middleware/audit_logging.py` was committed by A1 (`38229c0`) and R1 (`071d542`). C6 is the third edit. Read the current state carefully. The `_extract_customer_id` and `_log_to_database` functions will look different than in the original A1 codebase.

Other Wave-3a agents: C1 (db/models.py + types.py + customer_service + encryption), C4 (encryption + main.py), C5 (order.py + routers/orders.py). **None touches `audit_logging.py`**. C6 owns it alone.

## Commit message

```
feat(audit): log financial-data access on invoices/valuations/scrap_gold (C6)

Fix item C6 — AuditLoggingMiddleware now recognizes the 3 financial
resource paths in addition to /customers. Each GET produces a
CustomerAuditLog row with action="financial_read" (single) or
"list_accessed_financial" (list), entity_type set per resource.

CLAUDE.md "All financial data access MUST be audit-logged" is now
enforced on the REST read path.

Ref: docs/fix-plan/2026-04-23/C6-financial-audit.md
Ref: docs/review/2026-04-23/FIX-PLAN.md#group-c

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

## Open questions for the implementing agent

- Should non-GET methods (POST/PATCH/DELETE) also log a financial_read-like action? Strictly, CLAUDE.md says "access" — reads are access; writes are a separate concern and likely already handled by other audit paths (service-layer audit). For C6: only GETs.
- What about `/api/v1/analytics/*` endpoints that aggregate financial data? Out of scope for C6 — log in DECISIONS.md as follow-up C6.1.
- The `CustomerAuditLog` table is named for customer audit — renaming to `AccessAuditLog` might be cleaner but is a DB migration we don't need to do now. Document in DECISIONS.md as cosmetic follow-up.
