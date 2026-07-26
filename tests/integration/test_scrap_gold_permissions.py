"""
Integration tests for scrap-gold (Altgold) RBAC — production-readiness
finding 1.5 (docs/review/2026-07-26/production-readiness.md).

Before this fix the scrap-gold *read* routes were gated by ``ORDER_VIEW``,
a permission the VIEWER role holds.  ``ScrapGoldRead`` exposes
``total_value_eur`` and ``gold_price_per_g`` — financial data that CLAUDE.md
(Data Privacy Rules → Financial Data) says has the "same protections as
pricing": visible to ADMIN and GOLDSMITH only.  The fix introduces a
dedicated ``SCRAP_GOLD_VIEW`` permission (ADMIN + GOLDSMITH), mirroring
``INVOICE_VIEW`` / ``VALUATION_VIEW``.

This file proves:

* every scrap-gold READ route now 403s for a VIEWER token;
* GOLDSMITH and ADMIN retain access (the two cleanly-200 routes are asserted
  == 200; the two whose business logic legitimately 404/500 in a unit-test
  environment — the on-disk photo download and the PDF receipt — are asserted
  to have passed the permission gate, i.e. status != 403);
* ``GET /orders/{id}/scrap-gold`` (the primary financial read, which lives
  under ``/orders/`` and is therefore invisible to AuditLoggingMiddleware)
  now writes a ``CustomerAuditLog`` row directly from the router.

Structure mirrors tests/integration/test_financial_audit.py (fixtures,
middleware-session patch, audit-row helper).
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import (
    AlloyType,
    Customer,
    CustomerAuditLog,
    Order,
    OrderStatusEnum,
    ScrapGold,
    ScrapGoldItem,
    ScrapGoldStatus,
    User,
)


# ---------------------------------------------------------------------------
# Middleware session patch — identical rationale to test_financial_audit.py:
# AuditLoggingMiddleware opens its own AsyncSessionLocal(); bind it to the
# test engine so its writes (for the /scrap-gold/* routes it *does* match)
# land in the DB the test reads, rather than a missing production Postgres.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _patch_middleware_session(monkeypatch, db_session):
    from sqlalchemy.ext.asyncio import AsyncSession as _AsyncSession
    from sqlalchemy.orm import sessionmaker

    from goldsmith_erp.middleware import audit_logging

    factory = sessionmaker(
        bind=db_session.bind, class_=_AsyncSession, expire_on_commit=False
    )
    monkeypatch.setattr(audit_logging, "AsyncSessionLocal", factory)


# ---------------------------------------------------------------------------
# Fixtures — an order with a scrap-gold record + one item (financial values
# populated so a regression that serialized them to a VIEWER is observable).
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def scrap_gold_record(
    db_session: AsyncSession, test_customer: Customer, admin_user: User
) -> ScrapGold:
    order = Order(
        title="Altgold permission test order",
        description="Seed order for scrap-gold RBAC tests",
        customer_id=test_customer.id,
        status=OrderStatusEnum.COMPLETED,
        actual_weight_g=5.0,
        alloy="750",
        is_deleted=False,
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)

    scrap = ScrapGold(
        order_id=order.id,
        customer_id=test_customer.id,
        created_by=admin_user.id,
        status=ScrapGoldStatus.RECEIVED,
        total_fine_gold_g=3.5,
        total_value_eur=220.0,
        gold_price_per_g=62.86,
        price_source="fixed_rate",
    )
    db_session.add(scrap)
    await db_session.commit()
    await db_session.refresh(scrap)

    item = ScrapGoldItem(
        scrap_gold_id=scrap.id,
        description="Alter Ehering",
        alloy=AlloyType.GOLD_750,
        weight_g=4.67,
        fine_content_g=3.5,
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(scrap)
    return scrap


def _read_routes(scrap: ScrapGold, item_id: int) -> list[str]:
    """Every scrap-gold READ route, keyed off the seeded record."""
    return [
        f"/api/v1/orders/{scrap.order_id}/scrap-gold",
        f"/api/v1/scrap-gold/{scrap.id}/receipt.pdf",
        "/api/v1/scrap-gold/alloy-calculator?alloy=750&weight_g=5.0",
        f"/api/v1/scrap-gold/{scrap.id}/items/{item_id}/photo",
    ]


async def _first_item_id(db_session: AsyncSession, scrap_gold_id: int) -> int:
    row = (
        await db_session.execute(
            select(ScrapGoldItem).where(ScrapGoldItem.scrap_gold_id == scrap_gold_id)
        )
    ).scalar_one()
    return row.id


# ===========================================================================
# VIEWER — must be forbidden on EVERY read route
# ===========================================================================


@pytest.mark.asyncio
async def test_viewer_forbidden_on_all_scrap_gold_reads(
    client: AsyncClient,
    db_session: AsyncSession,
    viewer_auth_headers: dict,
    scrap_gold_record: ScrapGold,
):
    """
    A VIEWER token must receive 403 on every scrap-gold read route.

    This is the core regression guard for finding 1.5: pre-fix these routes
    were gated by ORDER_VIEW (which VIEWER holds), leaking total_value_eur /
    gold_price_per_g. Post-fix they require SCRAP_GOLD_VIEW (ADMIN+GOLDSMITH).
    """
    item_id = await _first_item_id(db_session, scrap_gold_record.id)
    for url in _read_routes(scrap_gold_record, item_id):
        resp = await client.get(url, headers=viewer_auth_headers)
        assert resp.status_code == 403, (
            f"VIEWER must be forbidden from {url}; got {resp.status_code} "
            f"({resp.text[:200]})"
        )


# ===========================================================================
# GOLDSMITH / ADMIN — retain access
# ===========================================================================


def _pick_headers(role: str, goldsmith_headers: dict, admin_headers: dict) -> dict:
    """Select an auth-header fixture by role name (both are injected as test
    args so pytest-asyncio resolves them normally — request.getfixturevalue
    on an async fixture would re-enter the running event loop)."""
    return {"goldsmith": goldsmith_headers, "admin": admin_headers}[role]


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["goldsmith", "admin"])
async def test_privileged_roles_can_read_scrap_gold_record(
    client: AsyncClient,
    role: str,
    goldsmith_auth_headers: dict,
    admin_auth_headers: dict,
    scrap_gold_record: ScrapGold,
):
    """
    GET /orders/{id}/scrap-gold returns 200 (with the financial body) for
    both GOLDSMITH and ADMIN.
    """
    headers = _pick_headers(role, goldsmith_auth_headers, admin_auth_headers)
    resp = await client.get(
        f"/api/v1/orders/{scrap_gold_record.order_id}/scrap-gold",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body is not None
    # The financial fields the finding flagged are present for privileged roles.
    assert body["total_value_eur"] == 220.0
    assert body["gold_price_per_g"] == 62.86


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["goldsmith", "admin"])
async def test_privileged_roles_can_use_alloy_calculator(
    client: AsyncClient,
    role: str,
    goldsmith_auth_headers: dict,
    admin_auth_headers: dict,
):
    """GET /scrap-gold/alloy-calculator returns 200 for GOLDSMITH and ADMIN."""
    headers = _pick_headers(role, goldsmith_auth_headers, admin_auth_headers)
    resp = await client.get(
        "/api/v1/scrap-gold/alloy-calculator?alloy=750&weight_g=5.0",
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["fine_content_g"] == pytest.approx(3.75)


@pytest.mark.asyncio
@pytest.mark.parametrize("role", ["goldsmith", "admin"])
async def test_privileged_roles_pass_gate_on_pdf_and_photo(
    client: AsyncClient,
    db_session: AsyncSession,
    role: str,
    goldsmith_auth_headers: dict,
    admin_auth_headers: dict,
    scrap_gold_record: ScrapGold,
):
    """
    The receipt-PDF download and the item-photo download are gated by
    SCRAP_GOLD_VIEW too. Their handlers can legitimately 404 (no photo file
    on disk) or 500 (PDF render glitch in the test env), so the assertion is
    that the permission GATE was passed — i.e. NOT 403/401 — for privileged
    roles.
    """
    headers = _pick_headers(role, goldsmith_auth_headers, admin_auth_headers)
    item_id = await _first_item_id(db_session, scrap_gold_record.id)

    pdf_resp = await client.get(
        f"/api/v1/scrap-gold/{scrap_gold_record.id}/receipt.pdf",
        headers=headers,
    )
    assert pdf_resp.status_code not in (401, 403), pdf_resp.text
    assert pdf_resp.status_code in (200, 404, 500), pdf_resp.text

    photo_resp = await client.get(
        f"/api/v1/scrap-gold/{scrap_gold_record.id}/items/{item_id}/photo",
        headers=headers,
    )
    assert photo_resp.status_code not in (401, 403), photo_resp.text
    # No photo uploaded in this fixture -> 404 is the expected happy-path.
    assert photo_resp.status_code in (200, 404), photo_resp.text


# ===========================================================================
# Audit logging — the /orders/{id}/scrap-gold blind spot is now covered
# ===========================================================================


@pytest.mark.asyncio
async def test_scrap_gold_record_read_writes_audit_row(
    authenticated_client: AsyncClient,  # ADMIN
    db_session: AsyncSession,
    admin_user: User,
    scrap_gold_record: ScrapGold,
):
    """
    GET /api/v1/orders/{id}/scrap-gold must write a CustomerAuditLog row.

    This route lives under ``/orders/`` so AuditLoggingMiddleware (which keys
    on the first path segment) structurally cannot see it — the router now
    writes the row directly via write_financial_audit_row. CLAUDE.md: "All
    financial data access MUST be audit-logged."
    """
    resp = await authenticated_client.get(
        f"/api/v1/orders/{scrap_gold_record.order_id}/scrap-gold"
    )
    assert resp.status_code == 200, resp.text

    row = (
        await db_session.execute(
            select(CustomerAuditLog)
            .where(CustomerAuditLog.entity == "scrap_gold")
            .where(CustomerAuditLog.entity_id == scrap_gold_record.id)
            .order_by(CustomerAuditLog.timestamp.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    assert row is not None, (
        "GET /api/v1/orders/{id}/scrap-gold must write a CustomerAuditLog "
        "row with entity='scrap_gold' — none found"
    )
    assert row.action == "financial_read", (
        f"single-record financial read must use action='financial_read', "
        f"got '{row.action}'"
    )
    assert row.user_id == admin_user.id
    # customer_id is resolved from the order inside write_financial_audit_row.
    assert row.customer_id == scrap_gold_record.customer_id
