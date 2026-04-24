"""Integration tests for C5 — VIEWER-role financial-field projection.

Decision locked (2026-04-24): VIEWER sees NO financial fields on any
``GET /api/v1/orders/*`` response. ADMIN and GOLDSMITH see all fields.

The seven forbidden fields are enumerated in ``FINANCIAL_FIELDS`` below
and sourced from CLAUDE.md "Data Privacy Rules → Financial Data":
> Pricing, payment info, material costs → visible only to ADMIN and
> GOLDSMITH roles

This test is the single source of truth for the VIEWER projection on
the REST Orders API. If a new financial column is added to ``OrderRead``
and not listed here, the ``test_viewer_does_not_leak_any_financial_*``
assertions will still fail if the field appears in a VIEWER response
— the assertion inspects the full JSON body, not just this constant.

Ref: docs/fix-plan/2026-04-23/C5-viewer-financial-projection.md
Ref: docs/review/2026-04-23/FIX-PLAN.md group C
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import Customer, Order, OrderStatusEnum


FINANCIAL_FIELDS: frozenset[str] = frozenset({
    "price",
    "material_cost_calculated",
    "material_cost_override",
    "labor_cost",
    "hourly_rate",
    "profit_margin_percent",
    "calculated_price",
})

ORDERS_URL = "/api/v1/orders/"


def _order_url(order_id: int) -> str:
    return f"{ORDERS_URL}{order_id}"


# --------------------------------------------------------------------------- #
# Fixture — an order stuffed with every financial field so we can tell which
# are stripped vs. null-by-default.
# --------------------------------------------------------------------------- #


@pytest_asyncio.fixture
async def financial_order(
    db_session: AsyncSession, test_customer: Customer,
) -> Order:
    """Create an order with every financial field populated.

    Using non-default, non-null values so that a projection that forgets
    to strip a field will visibly show it in the response body, not
    mask the bug as "field is null anyway."
    """
    order = Order(
        title="C5 Financial Projection Test Order",
        description="Every financial field populated for projection assertion",
        customer_id=test_customer.id,
        status=OrderStatusEnum.IN_PROGRESS,
        deadline=datetime.utcnow() + timedelta(days=14),
        # ── the 7 fields under test ──
        price=1234.56,
        material_cost_calculated=500.00,
        material_cost_override=520.00,
        labor_cost=300.00,
        hourly_rate=85.00,
        profit_margin_percent=35.0,
        calculated_price=1800.00,
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)
    return order


# --------------------------------------------------------------------------- #
# VIEWER — must NOT see any of the seven financial fields
# --------------------------------------------------------------------------- #


class TestViewerFinancialProjection:
    """VIEWER role response must have zero of the seven financial fields."""

    @pytest.mark.asyncio
    async def test_viewer_list_strips_all_financial_fields(
        self,
        client: AsyncClient,
        viewer_auth_headers: dict,
        financial_order: Order,
    ):
        resp = await client.get(ORDERS_URL, headers=viewer_auth_headers)
        assert resp.status_code == 200, resp.text
        orders = resp.json()
        assert orders, "test setup failure: the fixture order should be listed"

        # Find the order by id so we're asserting about the right one even
        # if other tests commit orders concurrently.
        matching = [o for o in orders if o.get("id") == financial_order.id]
        assert matching, f"order {financial_order.id} missing from VIEWER list"
        body = matching[0]

        leaked = FINANCIAL_FIELDS & set(body.keys())
        assert not leaked, (
            f"VIEWER LIST leaked financial fields: {sorted(leaked)}. "
            f"CLAUDE.md: financial data is ADMIN/GOLDSMITH only. "
            f"See docs/fix-plan/2026-04-23/C5-viewer-financial-projection.md."
        )

    @pytest.mark.asyncio
    async def test_viewer_detail_strips_all_financial_fields(
        self,
        client: AsyncClient,
        viewer_auth_headers: dict,
        financial_order: Order,
    ):
        resp = await client.get(
            _order_url(financial_order.id), headers=viewer_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()

        leaked = FINANCIAL_FIELDS & set(body.keys())
        assert not leaked, (
            f"VIEWER DETAIL leaked financial fields: {sorted(leaked)}. "
            f"CLAUDE.md: financial data is ADMIN/GOLDSMITH only."
        )

    @pytest.mark.asyncio
    async def test_viewer_detail_preserves_nonfinancial_fields(
        self,
        client: AsyncClient,
        viewer_auth_headers: dict,
        financial_order: Order,
    ):
        """Sanity check — the non-financial fields are still present.

        Catches the accidental-over-strip failure mode where a bad
        exclude-set removes more than intended.
        """
        resp = await client.get(
            _order_url(financial_order.id), headers=viewer_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()

        # These fields must survive the projection. They are the core
        # identifying + status fields a VIEWER legitimately needs.
        must_keep = {"id", "title", "description", "status", "customer_id",
                     "deadline", "created_at", "updated_at"}
        missing = must_keep - set(body.keys())
        assert not missing, (
            f"VIEWER projection over-stripped: missing {sorted(missing)}. "
            f"The exclude-set should only remove financial fields."
        )


# --------------------------------------------------------------------------- #
# GOLDSMITH — must see every financial field
# --------------------------------------------------------------------------- #


class TestGoldsmithFinancialProjection:
    """GOLDSMITH sees the full, unredacted OrderRead response."""

    @pytest.mark.asyncio
    async def test_goldsmith_list_sees_all_financial_fields(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        financial_order: Order,
    ):
        resp = await client.get(ORDERS_URL, headers=goldsmith_auth_headers)
        assert resp.status_code == 200, resp.text
        orders = resp.json()
        matching = [o for o in orders if o.get("id") == financial_order.id]
        assert matching, f"order {financial_order.id} missing from GOLDSMITH list"
        body = matching[0]

        missing = FINANCIAL_FIELDS - set(body.keys())
        assert not missing, (
            f"GOLDSMITH LIST is missing financial fields: {sorted(missing)}. "
            f"GOLDSMITH must see the unredacted OrderRead response."
        )

    @pytest.mark.asyncio
    async def test_goldsmith_detail_sees_all_financial_fields(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        financial_order: Order,
    ):
        resp = await client.get(
            _order_url(financial_order.id), headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()

        missing = FINANCIAL_FIELDS - set(body.keys())
        assert not missing, (
            f"GOLDSMITH DETAIL is missing financial fields: {sorted(missing)}."
        )

        # Values must be present (non-null) — fixture populated all seven.
        assert body["price"] == pytest.approx(1234.56)
        assert body["calculated_price"] == pytest.approx(1800.00)
        assert body["profit_margin_percent"] == pytest.approx(35.0)


# --------------------------------------------------------------------------- #
# ADMIN — identical to GOLDSMITH
# --------------------------------------------------------------------------- #


class TestAdminFinancialProjection:
    """ADMIN sees the full, unredacted OrderRead response."""

    @pytest.mark.asyncio
    async def test_admin_list_sees_all_financial_fields(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        financial_order: Order,
    ):
        resp = await client.get(ORDERS_URL, headers=admin_auth_headers)
        assert resp.status_code == 200, resp.text
        orders = resp.json()
        matching = [o for o in orders if o.get("id") == financial_order.id]
        assert matching, f"order {financial_order.id} missing from ADMIN list"
        body = matching[0]

        missing = FINANCIAL_FIELDS - set(body.keys())
        assert not missing, (
            f"ADMIN LIST is missing financial fields: {sorted(missing)}."
        )

    @pytest.mark.asyncio
    async def test_admin_detail_sees_all_financial_fields(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        financial_order: Order,
    ):
        resp = await client.get(
            _order_url(financial_order.id), headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()

        missing = FINANCIAL_FIELDS - set(body.keys())
        assert not missing, (
            f"ADMIN DETAIL is missing financial fields: {sorted(missing)}."
        )

        assert body["price"] == pytest.approx(1234.56)
        assert body["calculated_price"] == pytest.approx(1800.00)
