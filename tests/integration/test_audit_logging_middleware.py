"""
Integration tests for AuditLoggingMiddleware (fix item A1).

These tests verify two GDPR Art. 30 requirements:

1. An authenticated GET on `/api/v1/customers/{id}` writes a
   CustomerAuditLog row with `user_id` populated (set by
   AuthRequiredMiddleware via `request.state.user_id`), `action` set,
   and `entity_id` matching the target customer.
2. A forced audit-write failure is logged but does NOT fail the user's
   request — the audit middleware is fire-and-forget relative to the
   response path.

The middleware opens its own `AsyncSessionLocal()` (it is a
BaseHTTPMiddleware and cannot use FastAPI's `Depends(get_db)`), so the
tests replace that factory with the integration test's SQLite
`TestSessionLocal` via monkeypatch.  This keeps the middleware's
production code path identical and keeps the test self-contained.

Ref: docs/fix-plan/2026-04-23/A1-audit-middleware.md
"""
import logging

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from goldsmith_erp.db.models import CustomerAuditLog


# ---------------------------------------------------------------------------
# Fixture: point the middleware's AsyncSessionLocal at the test DB factory
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _patch_middleware_session(monkeypatch):
    """
    Redirect the audit middleware's ``AsyncSessionLocal`` to the integration
    test's SQLite-backed ``TestSessionLocal``.  The middleware opens its own
    session (BaseHTTPMiddleware can't take FastAPI dependencies); without
    this patch it would try to reach the production Postgres URL.

    We grab ``TestSessionLocal`` from the ALREADY-LOADED conftest module
    via ``sys.modules`` — a plain ``from tests.integration.conftest import
    TestSessionLocal`` risks loading a *second* copy of the conftest (with
    a fresh ``_DB_FILENAME`` / engine that has no tables) when pytest has
    already registered it under a different module name (``integration.
    conftest`` or simply ``conftest``).  Using the already-loaded instance
    guarantees the middleware writes to the same SQLite file the session
    fixture created tables in.
    """
    import sys
    from goldsmith_erp.middleware import audit_logging

    conftest_module = (
        sys.modules.get("tests.integration.conftest")
        or sys.modules.get("integration.conftest")
        or sys.modules.get("conftest")
    )
    assert conftest_module is not None, (
        "integration conftest must already be loaded by pytest; "
        "currently-loaded conftest-like modules: "
        + repr(sorted(k for k in sys.modules if "conftest" in k))
    )
    TestSessionLocal = conftest_module.TestSessionLocal

    monkeypatch.setattr(
        audit_logging, "AsyncSessionLocal", TestSessionLocal
    )


# ---------------------------------------------------------------------------
# Test 1 — authenticated GET produces an audit row with user_id populated
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_customer_get_produces_audit_row(
    authenticated_client: AsyncClient,
    db_session,
    test_customer,
    admin_user,
):
    # Act
    resp = await authenticated_client.get(
        f"/api/v1/customers/{test_customer.id}"
    )
    assert resp.status_code == 200, (
        f"expected 200 OK, got {resp.status_code}: {resp.text}"
    )

    # Assert — the audit middleware wrote a row for this customer access.
    result = await db_session.execute(
        select(CustomerAuditLog)
        .where(CustomerAuditLog.entity_id == test_customer.id)
        .order_by(CustomerAuditLog.timestamp.desc())
    )
    rows = result.scalars().all()

    assert len(rows) >= 1, (
        "AuditLoggingMiddleware must write a CustomerAuditLog row for every "
        "authenticated customer GET — zero rows found. "
        "Is the middleware registered in main.py?"
    )

    row = rows[0]
    assert row.user_id == admin_user.id, (
        f"audit row must record the authenticated user (expected "
        f"user_id={admin_user.id}, got {row.user_id}). "
        "Is AuthRequiredMiddleware populating request.state.user?"
    )
    assert row.action, "audit row must have an action set"
    assert row.entity == "customer"
    assert row.ip_address, "audit row must record the client ip"


# ---------------------------------------------------------------------------
# Test 2 — audit-write failure does NOT fail the user's request
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_write_failure_does_not_fail_user_request(
    authenticated_client: AsyncClient,
    test_customer,
    monkeypatch,
    caplog,
):
    """
    If the audit-writer raises, the middleware must catch the exception,
    emit an ERROR-level log line, and let the user's response through
    unchanged. Failing the user request would violate security > correctness
    ordering (we don't deny legitimate access because the audit log is down).
    """
    from goldsmith_erp.middleware import audit_logging

    async def broken_write(*args, **kwargs):
        raise RuntimeError("simulated audit DB failure")

    monkeypatch.setattr(
        audit_logging.AuditLoggingMiddleware,
        "_log_to_database",
        broken_write,
    )

    caplog.set_level(logging.ERROR, logger="goldsmith_erp.middleware.audit_logging")

    resp = await authenticated_client.get(
        f"/api/v1/customers/{test_customer.id}"
    )

    assert resp.status_code == 200, (
        "user request must not fail (500) when audit write fails — "
        f"got {resp.status_code}: {resp.text}"
    )
    assert any(
        "audit" in rec.message.lower() for rec in caplog.records
    ), "an ERROR log line mentioning 'audit' must be emitted on failure"


# ---------------------------------------------------------------------------
# Test 3 — R1: bulk list access must be audited (Art. 30 gap fix)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_customers_produces_audit_row(
    authenticated_client: AsyncClient,
    db_session,
    test_customer,
    admin_user,
):
    """
    R1: bulk list access (`GET /api/v1/customers/`) must be audited.

    Bulk list access exposes MORE PII than a single-record GET (every
    customer in the result set). Prior to this fix, `_log_to_database`
    returned early when `customer_id` was None, silently dropping every
    list/search request. That is a P1 GDPR Art. 30 gap.

    The audit row for a list request has:
    - `entity_id` = None (no specific customer)
    - `action` = "list_accessed" (distinct from single-record "accessed")
    - `user_id` populated from the authenticated session
    """
    # test_customer ensures there is at least one row in the DB, so the
    # list endpoint actually returns data.
    _ = test_customer

    resp = await authenticated_client.get("/api/v1/customers/")
    assert resp.status_code == 200, (
        f"expected 200 OK from list endpoint, got {resp.status_code}: {resp.text}"
    )

    result = await db_session.execute(
        select(CustomerAuditLog)
        .where(CustomerAuditLog.entity == "customer")
        .where(CustomerAuditLog.action == "list_accessed")
        .order_by(CustomerAuditLog.timestamp.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()

    assert row is not None, (
        "bulk list access must write an audit row — GDPR Art. 30 requires "
        "records of bulk PII processing activities"
    )
    assert row.user_id == admin_user.id, (
        f"list-audit row must record the authenticated user "
        f"(expected user_id={admin_user.id}, got {row.user_id})"
    )
    assert row.entity_id is None, (
        "list endpoint targets no single customer; entity_id must be None"
    )
    assert row.action == "list_accessed", (
        "list-endpoint audit rows must use 'list_accessed' to distinguish "
        "them from single-record 'accessed' rows"
    )


# ---------------------------------------------------------------------------
# Test 4 — regression: single-record GET still uses "accessed" action
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_single_customer_get_uses_accessed_action(
    authenticated_client: AsyncClient,
    db_session,
    test_customer,
):
    """
    R1 regression: fixing the list-audit path must not break the single-
    record audit path. `GET /api/v1/customers/{id}` must still write a row
    with `action="accessed"` and `entity_id=<customer.id>` (NOT
    "list_accessed").
    """
    resp = await authenticated_client.get(
        f"/api/v1/customers/{test_customer.id}"
    )
    assert resp.status_code == 200

    result = await db_session.execute(
        select(CustomerAuditLog)
        .where(CustomerAuditLog.entity_id == test_customer.id)
        .order_by(CustomerAuditLog.timestamp.desc())
        .limit(1)
    )
    row = result.scalar_one_or_none()

    assert row is not None, (
        "single-record GET must still produce an audit row"
    )
    assert row.action == "accessed", (
        f"single-record GET must use 'accessed' action, got '{row.action}' "
        "— did the R1 fix accidentally reroute single reads to list_accessed?"
    )
    assert row.entity_id == test_customer.id
