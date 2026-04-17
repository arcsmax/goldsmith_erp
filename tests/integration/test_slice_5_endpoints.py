"""Integration tests for Slice 5 endpoints.

Endpoint coverage:
  * PATCH /api/v1/time-tracking/{entry_id}/activity  — in-place activity switch
  * POST  /api/v1/time-tracking/{entry_id}/interruption  — log INTERRUPT event
  * PATCH /api/v1/orders/{order_id}  — punzierung mark + timestamp write

Matrix:
  * PATCH /activity: success; returns updated TimeEntryRead; no new row created
  * PATCH /activity: user_id in body → 422 (StrictRequestBase)
  * POST /interruption: success returns 201
  * POST /interruption: timer keeps running after the call
  * PATCH /orders/{id}: marks + timestamp write succeed
  * PATCH /orders/{id}: PUT admin path WITHOUT marks → 409 PUNZIERUNG_REQUIRED
  * PATCH /orders/{id}: invalid mark → 422
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import (
    Activity,
    Order,
    OrderStatusEnum,
    TimeEntry,
    User,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


@pytest_asyncio.fixture
async def slice5_activity(db_session: AsyncSession) -> Activity:
    activity = Activity(
        name="Loeten",
        category="fabrication",
        icon="flame",
        color="#ff6633",
        usage_count=0,
        is_custom=False,
        created_at=datetime.utcnow(),
    )
    db_session.add(activity)
    await db_session.commit()
    await db_session.refresh(activity)
    return activity


@pytest_asyncio.fixture
async def slice5_activity_2(db_session: AsyncSession) -> Activity:
    activity = Activity(
        name="Feilen",
        category="fabrication",
        icon="wrench",
        color="#336699",
        usage_count=0,
        is_custom=False,
        created_at=datetime.utcnow(),
    )
    db_session.add(activity)
    await db_session.commit()
    await db_session.refresh(activity)
    return activity


@pytest_asyncio.fixture
async def slice5_order(db_session: AsyncSession, test_customer) -> Order:
    order = Order(
        title="Slice 5 Order",
        description="integration",
        customer_id=test_customer.id,
        status=OrderStatusEnum.IN_PROGRESS,
        alloy="750",
        price=500.0,
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)
    return order


@pytest_asyncio.fixture
async def slice5_running_entry(
    db_session: AsyncSession,
    slice5_order: Order,
    slice5_activity: Activity,
    goldsmith_user: User,
) -> TimeEntry:
    entry = TimeEntry(
        id=str(uuid.uuid4()),
        order_id=slice5_order.id,
        user_id=goldsmith_user.id,
        activity_id=slice5_activity.id,
        start_time=datetime.utcnow() - timedelta(minutes=2),
        end_time=None,
        origin="manual",
        extra_metadata={},
        created_at=datetime.utcnow(),
    )
    db_session.add(entry)
    await db_session.commit()
    await db_session.refresh(entry)
    return entry


# --------------------------------------------------------------------------- #
# PATCH /time-tracking/{entry_id}/activity
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
class TestPatchActivityEndpoint:
    async def test_patch_activity_success_in_place(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        db_session: AsyncSession,
        slice5_running_entry: TimeEntry,
        slice5_activity_2: Activity,
    ):
        entry_id = slice5_running_entry.id
        new_activity_id = slice5_activity_2.id

        count_before = (
            await db_session.execute(select(func.count(TimeEntry.id)))
        ).scalar_one()

        resp = await client.patch(
            f"/api/v1/time-tracking/{entry_id}/activity",
            json={"activity_id": new_activity_id},
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["id"] == entry_id
        assert body["activity_id"] == new_activity_id

        count_after = (
            await db_session.execute(select(func.count(TimeEntry.id)))
        ).scalar_one()
        # Critical: in-place mutation, no new row.
        assert count_after == count_before

    async def test_patch_activity_rejects_user_id_in_body(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        slice5_running_entry: TimeEntry,
        slice5_activity_2: Activity,
    ):
        entry_id = slice5_running_entry.id
        resp = await client.patch(
            f"/api/v1/time-tracking/{entry_id}/activity",
            json={
                "activity_id": slice5_activity_2.id,
                "user_id": 999,  # StrictRequestBase rejection
            },
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 422

    async def test_patch_activity_requires_auth(
        self,
        client: AsyncClient,
        slice5_running_entry: TimeEntry,
        slice5_activity_2: Activity,
    ):
        resp = await client.patch(
            f"/api/v1/time-tracking/{slice5_running_entry.id}/activity",
            json={"activity_id": slice5_activity_2.id},
        )
        assert resp.status_code == 401


# --------------------------------------------------------------------------- #
# POST /time-tracking/{entry_id}/interruption
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
class TestLogInterruptionEndpoint:
    async def test_log_interruption_returns_201(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        db_session: AsyncSession,
        slice5_running_entry: TimeEntry,
    ):
        entry_id = slice5_running_entry.id
        resp = await client.post(
            f"/api/v1/time-tracking/{entry_id}/interruption",
            json={"interrupt_code": "kundenanruf", "notes": "30s call"},
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["time_entry_id"] == entry_id
        assert "kundenanruf" in body["reason"]

        # Timer must still be running.
        result = await db_session.execute(
            select(TimeEntry).where(TimeEntry.id == entry_id)
        )
        entry = result.scalar_one()
        assert entry.end_time is None

    async def test_log_interruption_rejects_user_id_in_body(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        slice5_running_entry: TimeEntry,
    ):
        resp = await client.post(
            f"/api/v1/time-tracking/{slice5_running_entry.id}/interruption",
            json={"interrupt_code": "test", "user_id": 42},
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 422


# --------------------------------------------------------------------------- #
# PATCH /orders/{order_id}  — Punzierung fields
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
class TestPatchOrderPunzierung:
    async def test_patch_writes_marks_and_timestamp(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        db_session: AsyncSession,
        slice5_order: Order,
    ):
        order_id = slice5_order.id
        resp = await client.patch(
            f"/api/v1/orders/{order_id}",
            json={
                "punzierung_verified_marks": ["feingehalt_750", "meisterzeichen"],
            },
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 200, resp.text

        # Verify the DB row — marks and timestamp recorded.
        result = await db_session.execute(
            select(Order).where(Order.id == order_id)
        )
        refreshed = result.scalar_one()
        assert refreshed.punzierung_verified_at is not None
        assert "feingehalt_750" in refreshed.punzierung_verified_marks
        assert "meisterzeichen" in refreshed.punzierung_verified_marks
        # A2.8 retention promoted.
        assert refreshed.retention_class == "hallmark_10y"

    async def test_advance_to_completed_without_marks_raises_409(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        slice5_order: Order,
    ):
        order_id = slice5_order.id
        resp = await client.patch(
            f"/api/v1/orders/{order_id}",
            json={"status": "completed"},
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 409, resp.text
        detail = resp.json()["detail"]
        assert detail["code"] == "PUNZIERUNG_REQUIRED"

    async def test_unknown_mark_value_rejected_422(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        slice5_order: Order,
    ):
        resp = await client.patch(
            f"/api/v1/orders/{slice5_order.id}",
            json={"punzierung_verified_marks": ["feingehalt_666"]},
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 422

    async def test_put_admin_path_same_guard_fires(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        slice5_order: Order,
    ):
        """PUT /orders/{id} hitting the same update_order path must also
        be guarded — scan is not the only route to COMPLETED."""
        resp = await client.put(
            f"/api/v1/orders/{slice5_order.id}",
            json={"status": "completed"},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "PUNZIERUNG_REQUIRED"
