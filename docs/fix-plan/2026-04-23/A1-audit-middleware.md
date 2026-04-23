# A1 — Register `AuditLoggingMiddleware` + populate `request.state.user`

**Item:** A1 · **Severity:** P0 · **Effort:** M · **Owner:** BE + GDPR
**Source:** `docs/review/2026-04-23/FIX-PLAN.md` Group A, flagged by reports 01, 03, 04

## Context

`src/goldsmith_erp/middleware/audit_logging.py` defines `AuditLoggingMiddleware` which writes a `CustomerAuditLog` row for every customer-endpoint access (GDPR Art. 30 records of processing activities). **The class is defined but never registered** in `main.py` (confirmed: the only `app.add_middleware(AuditLoggingMiddleware)` reference in the repo is inside the class's own docstring). Separately, `AuditLoggingMiddleware.dispatch` reads `request.state.user` — which `AuthRequiredMiddleware` never populates (confirmed via grep of `request.state` in `auth_required.py` — zero hits). So even if registered today, every audit row would have `user_id=None`.

CLAUDE.md: *"All new models must be registered with audit logging"* — currently not enforced. This is a GDPR-critical correctness gap.

## Goal

Every authenticated request to `/api/v1/customers/*` produces a `CustomerAuditLog` row with the correct `user_id`, `action`, `endpoint`, `method`, `ip`, and `timestamp`. Failures of the audit write are logged but do NOT fail the user's request.

## Files

- **Modify** `src/goldsmith_erp/middleware/auth_required.py` — set `request.state.user = User(...)` (or `request.state.user_id = sub`, whichever the audit middleware expects) on successful JWT validation.
- **Modify** `src/goldsmith_erp/main.py` — register `AuditLoggingMiddleware` AFTER `AuthRequiredMiddleware` in the middleware stack (so auth runs first).
- **Modify** `src/goldsmith_erp/middleware/audit_logging.py` — if the DB write is currently synchronous inline, wrap in a `try/except` with structured-log fallback so an audit-write failure does not fail the user request. If it's not already, make the write fire-and-forget via `BackgroundTasks` or a buffered queue.
- **Create** `tests/integration/test_audit_logging_middleware.py` — integration test proving the middleware writes the expected row.

## Acceptance criteria

- [ ] A successful `GET /api/v1/customers/{existing_id}` authenticated as any role produces exactly one new row in `customer_audit_logs` with `action="read"` (or the middleware's canonical read action), `user_id=<authenticated user>`, `entity_type="customer"`, `entity_id=<the id>`, and `timestamp` within ±2s of the request.
- [ ] A `GET /api/v1/customers/99999999` (nonexistent) still produces an audit row (access ATTEMPTS are auditable even on 404, unless the middleware explicitly scopes to 2xx — decide and document in the spec below).
- [ ] A forced audit-write failure (mock the DB insert to raise) does NOT cause the user's request to 500 — the response is whatever the handler returned, and an ERROR-level log line records the audit failure with `audit=true` tag.
- [ ] Existing auth + customers tests still pass (`pytest tests/integration/test_customers*.py -v`).

## Test design (TDD)

Write these tests first. They must FAIL against HEAD (middleware unregistered) and PASS after the fix.

```python
# tests/integration/test_audit_logging_middleware.py
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from goldsmith_erp.db.models import CustomerAuditLog, Customer

@pytest.mark.asyncio
async def test_customer_get_produces_audit_row(
    authenticated_client: AsyncClient,
    db_session,
    test_customer,  # fixture that creates a customer
):
    # Act
    resp = await authenticated_client.get(f"/api/v1/customers/{test_customer.id}")
    assert resp.status_code == 200

    # Assert audit row exists
    result = await db_session.execute(
        select(CustomerAuditLog)
        .where(CustomerAuditLog.entity_id == str(test_customer.id))
        .order_by(CustomerAuditLog.timestamp.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()
    assert row is not None, "no audit row written for authenticated customer GET"
    assert row.action == "read"
    assert row.user_id is not None, "audit row must record the authenticated user"
    assert row.entity_type == "customer"

@pytest.mark.asyncio
async def test_audit_write_failure_does_not_fail_request(
    authenticated_client,
    test_customer,
    monkeypatch,
    caplog,
):
    # Arrange: force the audit-writer to raise on insert
    from goldsmith_erp.middleware import audit_logging
    async def broken_write(*args, **kwargs):
        raise RuntimeError("simulated DB failure")
    monkeypatch.setattr(audit_logging, "_write_audit_row", broken_write)  # exact name per impl

    # Act
    resp = await authenticated_client.get(f"/api/v1/customers/{test_customer.id}")

    # Assert
    assert resp.status_code == 200, "user request must not fail on audit write failure"
    assert any("audit" in rec.message.lower() for rec in caplog.records)
```

## Implementation sketch

1. **Read** `middleware/audit_logging.py` in full to know the expected `request.state` key + the exact insert call shape.
2. **Add** in `AuthRequiredMiddleware.dispatch` (after successful token decode, before `await call_next`):
   ```python
   request.state.user_id = int(payload["sub"])  # or populate a full user object if the audit middleware reads `.user.id`
   ```
   Keep the existing state minimal — don't fetch the user from DB here unless audit really needs the whole row (adds latency). Prefer `user_id` only.
3. **Register** `AuditLoggingMiddleware` in `main.py` AFTER `app.add_middleware(AuthRequiredMiddleware, ...)`. Starlette runs middleware in LIFO order of add, so *add audit before auth* so that auth runs first.
4. **Harden** the audit middleware's DB write if it's currently `await db.commit()` inline — wrap in `try/except SQLAlchemyError` with `logger.exception("audit write failed", extra={"audit": True})` so audit failures don't propagate.
5. **Run new tests**; they should pass.
6. **Run** `pytest tests/integration/ -k customer -v` to confirm no regression.

## Parallel-safety

This item owns `main.py`, `middleware/auth_required.py`, and `middleware/audit_logging.py`. No other Wave-1 item touches these files. Cleared to run in parallel with all other Wave-1 items.

## Commit message

```
feat(audit): register AuditLoggingMiddleware and populate request.state.user_id

Fix item A1 — the middleware class was defined but never added to the
stack, and AuthRequiredMiddleware never set request.state. Every customer
PII access was therefore unaudited, violating GDPR Art. 30 records of
processing. Audit-write failures are now caught and logged without failing
the user request.

Ref: docs/fix-plan/2026-04-23/A1-audit-middleware.md
Ref: docs/review/2026-04-23/FIX-PLAN.md#group-a

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

## Open questions for the implementing agent

- Does `audit_logging.py` read `request.state.user` (needing a full `User` object) or `request.state.user_id` (needing just an int)? Read the file first; match the populate-in-auth side accordingly.
- Should access ATTEMPTS on 404 be audited? CLAUDE.md suggests yes (attempts are processing activities); confirm by reading the middleware's current status-code filter, if any.
- If the middleware is not yet async-aware of DB sessions (`BaseHTTPMiddleware` cannot easily inject a FastAPI `Depends(get_db)`), decide whether it opens its own `AsyncSessionLocal()` or enqueues to Redis for a background writer. Simplest for now: open a scoped session inside the middleware.
