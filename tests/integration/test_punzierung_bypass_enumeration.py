"""Punzierungs-Check bypass enumeration (Slice 6 / M4 / R8 / A5.3).

Purpose
-------
Enumerate EVERY code path that writes ``Order.status`` and assert that
the Punzierungs-Check guard fires uniformly when the target status is
``COMPLETED`` and the order has a declared ``alloy`` without verified
marks. This is the M4/R8 gap: the guard is worthless if even one
status-write path bypasses it.

Status-write paths under test
-----------------------------
Path 1 — Router:  ``PUT   /api/v1/orders/{id}``        (status=completed)
Path 2 — Router:  ``PATCH /api/v1/orders/{id}``        (status=completed)
Path 3 — Service: ``OrderService.update_order(...)``   (direct service call)
Path 4 — Service: ``OrderService.advance_status(...)`` (scan-flow wrapper)

Status-write paths explicitly audited and confirmed SAFE
--------------------------------------------------------
Path 5 — ``OrderRepository.change_order_status`` — DELETED in Slice 6
         (H14). Guarded by ``tests/unit/test_order_repository_hygiene.py``.
Path 6 — ``OrderRepository.update_order`` — repository is unused
         (zero callers anywhere). Hygiene test keeps status-write
         methods off the class. Not exercised here because the
         repository is not reachable from any router.
Path 7 — ``QuoteService.convert_quote_to_order`` — CREATES a NEW
         order with status=CONFIRMED (never COMPLETED). The guard
         intentionally does not fire on non-COMPLETED transitions.
Path 8 — ``OrderService.change_location`` — does NOT write ``status``.
Path 9 — ``OrderService.create_order`` — creates new orders; the
         first-write-to-status-COMPLETED case is still guarded via
         ``update_order``. Order creation with status=COMPLETED is
         not currently supported by the API surface.

Control cases
-------------
* ``alloy IS NULL`` — guard must NOT fire on any path.
* ``punzierung_verified_marks`` populated — guard must NOT fire.
* Guard must NOT fire on transitions to non-COMPLETED statuses.

This test file is the living contract for R8 mitigation. If a new
status-write path is introduced, add it here.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import Customer, Order, OrderStatusEnum, User
from goldsmith_erp.models.order import OrderUpdate
from goldsmith_erp.services.order_service import (
    OrderService,
    PunzierungRequiredError,
)


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #


async def _make_order(
    db_session: AsyncSession,
    customer: Customer,
    *,
    alloy: Optional[str] = "750",
    marks: Optional[list] = None,
    status: OrderStatusEnum = OrderStatusEnum.IN_PROGRESS,
) -> Order:
    order = Order(
        title=f"Punz enum {uuid.uuid4().hex[:6]}",
        description="Slice 6 bypass enumeration",
        customer_id=customer.id,
        status=status,
        alloy=alloy,
        punzierung_verified_marks=marks,
        price=500.0,
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)
    return order


# --------------------------------------------------------------------------- #
# Path 1 — PUT /api/v1/orders/{id}
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
class TestPutRouterStatusWrite:
    async def test_put_to_completed_without_marks_raises_409(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        db_session: AsyncSession,
        test_customer: Customer,
    ):
        order = await _make_order(db_session, test_customer, alloy="750")
        resp = await client.put(
            f"/api/v1/orders/{order.id}",
            json={"status": "completed"},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 409, resp.text
        assert resp.json()["detail"]["code"] == "PUNZIERUNG_REQUIRED"

    async def test_put_to_completed_with_alloy_none_succeeds(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        db_session: AsyncSession,
        test_customer: Customer,
    ):
        order = await _make_order(db_session, test_customer, alloy=None)
        resp = await client.put(
            f"/api/v1/orders/{order.id}",
            json={"status": "completed"},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text

    async def test_put_to_completed_with_marks_succeeds(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        db_session: AsyncSession,
        test_customer: Customer,
    ):
        order = await _make_order(
            db_session,
            test_customer,
            alloy="750",
            marks=["feingehalt_750", "meisterzeichen"],
        )
        resp = await client.put(
            f"/api/v1/orders/{order.id}",
            json={"status": "completed"},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text

    async def test_put_to_non_completed_bypasses_guard(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        db_session: AsyncSession,
        test_customer: Customer,
    ):
        """Transitions to IN_PROGRESS / QUALITY_CHECK are not guarded."""
        order = await _make_order(
            db_session,
            test_customer,
            alloy="750",
            status=OrderStatusEnum.NEW,
        )
        resp = await client.put(
            f"/api/v1/orders/{order.id}",
            json={"status": "quality_check"},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text


# --------------------------------------------------------------------------- #
# Path 2 — PATCH /api/v1/orders/{id}
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
class TestPatchRouterStatusWrite:
    async def test_patch_to_completed_without_marks_raises_409(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        db_session: AsyncSession,
        test_customer: Customer,
    ):
        order = await _make_order(db_session, test_customer, alloy="585")
        resp = await client.patch(
            f"/api/v1/orders/{order.id}",
            json={"status": "completed"},
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 409, resp.text
        detail = resp.json()["detail"]
        assert detail["code"] == "PUNZIERUNG_REQUIRED"
        assert detail["alloy"] == "585"
        assert detail["order_id"] == order.id

    async def test_patch_to_completed_with_marks_in_same_request_succeeds(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        db_session: AsyncSession,
        test_customer: Customer,
    ):
        """Scan-flow path — complete + verify in one round-trip."""
        order = await _make_order(db_session, test_customer, alloy="585")
        resp = await client.patch(
            f"/api/v1/orders/{order.id}",
            json={
                "status": "completed",
                "punzierung_verified_marks": ["feingehalt_585", "meisterzeichen"],
            },
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 200, resp.text

    async def test_patch_alloy_none_bypasses_guard(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        db_session: AsyncSession,
        test_customer: Customer,
    ):
        order = await _make_order(db_session, test_customer, alloy=None)
        resp = await client.patch(
            f"/api/v1/orders/{order.id}",
            json={"status": "completed"},
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 200, resp.text


# --------------------------------------------------------------------------- #
# Path 3 — OrderService.update_order (service-layer call)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
class TestUpdateOrderService:
    async def test_service_update_order_fires_guard(
        self,
        db_session: AsyncSession,
        test_customer: Customer,
    ):
        order = await _make_order(db_session, test_customer, alloy="750")
        with pytest.raises(PunzierungRequiredError) as excinfo:
            await OrderService.update_order(
                db_session,
                order.id,
                OrderUpdate(status=OrderStatusEnum.COMPLETED),
                verified_by_user_id=None,
                origin="manual",
            )
        assert excinfo.value.status_code == 409
        assert excinfo.value.detail["code"] == "PUNZIERUNG_REQUIRED"

    async def test_service_update_order_with_alloy_none_succeeds(
        self,
        db_session: AsyncSession,
        test_customer: Customer,
    ):
        order = await _make_order(db_session, test_customer, alloy=None)
        updated = await OrderService.update_order(
            db_session,
            order.id,
            OrderUpdate(status=OrderStatusEnum.COMPLETED),
            verified_by_user_id=None,
            origin="manual",
        )
        assert updated is not None
        assert updated.status == OrderStatusEnum.COMPLETED

    async def test_service_update_order_with_pre_verified_marks_succeeds(
        self,
        db_session: AsyncSession,
        test_customer: Customer,
    ):
        order = await _make_order(
            db_session,
            test_customer,
            alloy="750",
            marks=["feingehalt_750"],
        )
        updated = await OrderService.update_order(
            db_session,
            order.id,
            OrderUpdate(status=OrderStatusEnum.COMPLETED),
            verified_by_user_id=None,
            origin="manual",
        )
        assert updated is not None
        assert updated.status == OrderStatusEnum.COMPLETED


# --------------------------------------------------------------------------- #
# Path 4 — OrderService.advance_status (scan-flow wrapper)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
class TestAdvanceStatusService:
    async def test_advance_status_fires_guard(
        self,
        db_session: AsyncSession,
        test_customer: Customer,
    ):
        order = await _make_order(db_session, test_customer, alloy="585")
        with pytest.raises(PunzierungRequiredError) as excinfo:
            await OrderService.advance_status(
                db_session,
                order.id,
                OrderStatusEnum.COMPLETED,
                user_id=1,
            )
        assert excinfo.value.status_code == 409
        assert excinfo.value.detail["code"] == "PUNZIERUNG_REQUIRED"
        assert excinfo.value.detail["alloy"] == "585"

    async def test_advance_status_complete_and_verify_single_call(
        self,
        db_session: AsyncSession,
        test_customer: Customer,
        goldsmith_user: User,
    ):
        """The scan flow passes marks + target status in one call."""
        order = await _make_order(db_session, test_customer, alloy="585")
        updated = await OrderService.advance_status(
            db_session,
            order.id,
            OrderStatusEnum.COMPLETED,
            user_id=goldsmith_user.id,
            punzierung_verified_marks=["feingehalt_585"],
        )
        assert updated is not None
        assert updated.status == OrderStatusEnum.COMPLETED
        assert updated.punzierung_verified_at is not None
        assert updated.punzierung_verified_by == goldsmith_user.id

    async def test_advance_status_alloy_none_is_exempt(
        self,
        db_session: AsyncSession,
        test_customer: Customer,
    ):
        order = await _make_order(db_session, test_customer, alloy=None)
        updated = await OrderService.advance_status(
            db_session,
            order.id,
            OrderStatusEnum.COMPLETED,
            user_id=1,
        )
        assert updated is not None
        assert updated.status == OrderStatusEnum.COMPLETED


# --------------------------------------------------------------------------- #
# Cross-path parity: All known paths must agree on the same outcome
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
class TestAllPathsAgree:
    """Each path produces the same 409 PUNZIERUNG_REQUIRED response
    for the same failing precondition. Proof: behavioural parity
    means the guard is not bypassed by any one path."""

    async def test_all_paths_reject_unverified_completion(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        db_session: AsyncSession,
        test_customer: Customer,
    ):
        # Build 4 equivalent orders.
        orders = []
        for _ in range(4):
            orders.append(await _make_order(db_session, test_customer, alloy="750"))

        # Path 1: PUT router
        resp = await client.put(
            f"/api/v1/orders/{orders[0].id}",
            json={"status": "completed"},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "PUNZIERUNG_REQUIRED"

        # Path 2: PATCH router
        resp = await client.patch(
            f"/api/v1/orders/{orders[1].id}",
            json={"status": "completed"},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "PUNZIERUNG_REQUIRED"

        # Path 3: OrderService.update_order
        with pytest.raises(PunzierungRequiredError):
            await OrderService.update_order(
                db_session,
                orders[2].id,
                OrderUpdate(status=OrderStatusEnum.COMPLETED),
                verified_by_user_id=None,
            )

        # Path 4: OrderService.advance_status
        with pytest.raises(PunzierungRequiredError):
            await OrderService.advance_status(
                db_session,
                orders[3].id,
                OrderStatusEnum.COMPLETED,
                user_id=1,
            )


# --------------------------------------------------------------------------- #
# Dead-path audit — these services DO NOT write Order.status
# --------------------------------------------------------------------------- #


class TestAuditedNonStatusPaths:
    """Documented invariant: the following services do not write
    ``Order.status``. If any of these gains a status-write in future,
    the enumeration above MUST be extended."""

    def test_change_location_does_not_touch_status(self):
        """Inspect the source to confirm ``change_location`` updates
        ``current_location`` only. This is a static check — the
        module-level string guards against regression by grep."""
        import inspect

        from goldsmith_erp.services.order_service import OrderService

        src = inspect.getsource(OrderService.change_location)
        # The function builds ``update(OrderModel)...values(current_location=...)``
        # and must not touch ``status``.
        assert "status" not in src or ".values(current_location=" in src
        # Explicit check: no ``status=`` inside the values() call.
        assert "status=" not in src, (
            "OrderService.change_location now writes status? That path "
            "must go through OrderService.update_order for the guard."
        )

    def test_quote_convert_creates_with_confirmed_not_completed(self):
        """``QuoteService.convert_quote`` creates an Order with
        ``status=CONFIRMED``. The Punzierung guard fires only on
        COMPLETED, so quote conversion is intentionally exempt."""
        import inspect

        from goldsmith_erp.services.quote_service import QuoteService

        src = inspect.getsource(QuoteService.convert_quote)
        assert "OrderStatusEnum.CONFIRMED" in src
        assert "OrderStatusEnum.COMPLETED" not in src, (
            "Quote conversion now creates COMPLETED orders? That path "
            "must be routed through OrderService.update_order or the "
            "guard call must be added inline."
        )
