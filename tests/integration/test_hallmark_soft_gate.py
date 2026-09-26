"""Hallmark soft-completion gate (W2-09; DOM-22, DOM-23, DOM-44; D-10).

Before this change, completing an alloyed order required a verified
Feingehalt mark from a four-alloy vocabulary — a hard gate. D-10 softens
this: completion now also succeeds with a documented
``"nicht punziert: <Grund>"`` reason, and the vocabulary itself widens to
every alloy the order form offers (585/750/333/375/900/999/Ag800/Ag925/
Pt950), not just the original four.

This file exercises the public HTTP surface (``PATCH /orders/{id}`` then
``PATCH /orders/{id}/status``, matching the frontend's two-step retry) plus
the service layer directly. ``tests/integration/test_punzierung_bypass_
enumeration.py`` remains the enumeration of every status-write path; this
file is the soft-gate contract on top of it.
"""

from __future__ import annotations

import uuid
from typing import Optional

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import Customer, Order, OrderStatusEnum, User
from goldsmith_erp.services.order_service import OrderService, PunzierungRequiredError


async def _refresh(db_session: AsyncSession, order_id: int) -> Order:
    """Re-read the order row — ``OrderRead`` does not serialize
    ``punzierung_verified_marks`` on the HTTP response (same as the
    existing ``test_slice_5_endpoints.py`` convention), so tests that need
    to see the persisted marks go straight to the DB."""
    result = await db_session.execute(select(Order).where(Order.id == order_id))
    return result.scalar_one()


pytestmark = pytest.mark.asyncio


async def _make_order(
    db_session: AsyncSession,
    customer: Customer,
    *,
    alloy: Optional[str] = "333",
    status: OrderStatusEnum = OrderStatusEnum.QUALITY_CHECK,
) -> Order:
    order = Order(
        title=f"Hallmark soft gate {uuid.uuid4().hex[:6]}",
        description="W2-09 soft gate",
        customer_id=customer.id,
        status=status,
        alloy=alloy,
        price=500.0,
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)
    return order


# --------------------------------------------------------------------------- #
# HTTP: complete without marks -> 409 with the new code
# --------------------------------------------------------------------------- #


@pytest_asyncio.fixture
async def gate_order(db_session: AsyncSession, sample_customer: Customer) -> Order:
    return await _make_order(db_session, sample_customer, alloy="333")


class TestCompleteWithoutMarksIsRefused:
    async def test_status_patch_returns_409_hallmark_required(
        self, client: AsyncClient, goldsmith_auth_headers: dict, gate_order: Order
    ):
        resp = await client.patch(
            f"/api/v1/orders/{gate_order.id}/status",
            json={"status": "completed"},
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 409, resp.text
        body = resp.json()
        # Modern dotted slug the frontend branches on (OrderDetailPage).
        assert body["code"] == "order.hallmark_required"
        # Legacy nested code kept for the pre-existing bypass-enumeration
        # suite and any caller written against the hard-gate era.
        assert body["detail"]["code"] == "PUNZIERUNG_REQUIRED"
        assert body["detail"]["alloy"] == "333"
        assert "Fertiggestellt" in body["detail"]["message"]

    async def test_generic_patch_returns_409_hallmark_required(
        self, client: AsyncClient, goldsmith_auth_headers: dict, gate_order: Order
    ):
        resp = await client.patch(
            f"/api/v1/orders/{gate_order.id}",
            json={"status": "completed"},
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "order.hallmark_required"


# --------------------------------------------------------------------------- #
# HTTP: complete with a documented "nicht punziert" reason -> ok
# --------------------------------------------------------------------------- #


class TestCompleteWithNichtPunziertReasonSucceeds:
    async def test_reason_in_the_same_request_completes(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        db_session: AsyncSession,
        gate_order: Order,
    ):
        resp = await client.patch(
            f"/api/v1/orders/{gate_order.id}",
            json={
                "status": "completed",
                "punzierung_verified_marks": ["nicht punziert: Stein zu klein"],
            },
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "completed"

        refreshed = await _refresh(db_session, gate_order.id)
        assert refreshed.punzierung_verified_marks == ["nicht punziert: Stein zu klein"]
        assert refreshed.punzierung_verified_at is not None
        # A2.8 retention promoted on first mark write — the reason path is
        # a mark write too.
        assert refreshed.retention_class == "hallmark_10y"

    async def test_reason_recorded_first_then_status_advanced(
        self, client: AsyncClient, goldsmith_auth_headers: dict, gate_order: Order
    ):
        # Matches the frontend's two-step retry: PATCH the marks first,
        # then PATCH /status (the modal opens on the /status 409, records
        # the reason via PATCH /orders/{id}, then retries the status call).
        record = await client.patch(
            f"/api/v1/orders/{gate_order.id}",
            json={
                "punzierung_verified_marks": [
                    "nicht punziert: Kunde wollte keine Punze"
                ]
            },
            headers=goldsmith_auth_headers,
        )
        assert record.status_code == 200, record.text

        advance = await client.patch(
            f"/api/v1/orders/{gate_order.id}/status",
            json={"status": "completed"},
            headers=goldsmith_auth_headers,
        )
        assert advance.status_code == 200, advance.text
        assert advance.json()["status"] == "completed"


# --------------------------------------------------------------------------- #
# HTTP: complete with a valid Feingehalt mark -> ok, across the widened
# vocabulary (DOM-22: 333/375/900/999/Ag800 were previously unrepresentable)
# --------------------------------------------------------------------------- #


class TestCompleteWithFeingehaltMarkSucceeds:
    @pytest.mark.parametrize(
        ("alloy", "mark"),
        [
            ("333", "feingehalt_333"),
            ("375", "feingehalt_375"),
            ("900", "feingehalt_900"),
            ("999", "feingehalt_999"),
            ("Ag800", "feingehalt_800"),
            ("Ag925", "feingehalt_925"),
            ("Pt950", "feingehalt_950_pt"),
            ("585", "585"),
            ("750", "Au750"),
        ],
    )
    async def test_widened_vocabulary_completes(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        db_session: AsyncSession,
        sample_customer: Customer,
        alloy: str,
        mark: str,
    ):
        order = await _make_order(db_session, sample_customer, alloy=alloy)
        resp = await client.patch(
            f"/api/v1/orders/{order.id}",
            json={"status": "completed", "punzierung_verified_marks": [mark]},
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "completed"


# --------------------------------------------------------------------------- #
# An additional mark alone still does not satisfy the gate
# --------------------------------------------------------------------------- #


class TestAdditionalMarkAloneIsInsufficient:
    async def test_meisterzeichen_alone_still_409s(
        self, client: AsyncClient, goldsmith_auth_headers: dict, gate_order: Order
    ):
        resp = await client.patch(
            f"/api/v1/orders/{gate_order.id}",
            json={
                "status": "completed",
                "punzierung_verified_marks": ["meisterzeichen"],
            },
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["code"] == "order.hallmark_required"


# --------------------------------------------------------------------------- #
# Service layer: the guard function directly
# --------------------------------------------------------------------------- #


class TestServiceLayerSoftGate:
    async def test_advance_status_with_reason_marks_succeeds(
        self, db_session: AsyncSession, sample_customer: Customer, sample_user: User
    ):
        order = await _make_order(db_session, sample_customer, alloy="333")
        updated = await OrderService.advance_status(
            db_session,
            order.id,
            OrderStatusEnum.COMPLETED,
            user_id=sample_user.id,
            punzierung_verified_marks=["nicht punziert: Stein zu klein"],
        )
        assert updated is not None
        assert updated.status == OrderStatusEnum.COMPLETED
        assert updated.punzierung_verified_marks == ["nicht punziert: Stein zu klein"]

    async def test_advance_status_without_marks_raises_hallmark_required(
        self, db_session: AsyncSession, sample_customer: Customer, sample_user: User
    ):
        order = await _make_order(db_session, sample_customer, alloy="900")
        with pytest.raises(PunzierungRequiredError) as excinfo:
            await OrderService.advance_status(
                db_session, order.id, OrderStatusEnum.COMPLETED, user_id=sample_user.id
            )
        assert excinfo.value.code == "order.hallmark_required"
        assert excinfo.value.detail["code"] == "PUNZIERUNG_REQUIRED"

    async def test_orders_without_alloy_are_exempt(
        self, db_session: AsyncSession, sample_customer: Customer, sample_user: User
    ):
        order = await _make_order(db_session, sample_customer, alloy=None)
        updated = await OrderService.advance_status(
            db_session, order.id, OrderStatusEnum.COMPLETED, user_id=sample_user.id
        )
        assert updated is not None
        assert updated.status == OrderStatusEnum.COMPLETED
