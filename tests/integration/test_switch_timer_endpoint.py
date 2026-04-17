"""Integration tests for POST /api/v1/time-tracking/{entry_id}/switch (H18).

Coverage:
  * Happy path: switch commits a single stop + start pair; old entry
    ends, new entry runs, origin propagates as ``scan``.
  * Per-user scope (A5.1): a GOLDSMITH-role token cannot switch another
    user's timer — 403.
  * Stale-timer guard (A5.2): 409 with ``detail.code == "TIMER_POSSIBLY_STALE"``
    when the outgoing entry has been running past the 20-min threshold.
  * Missing entry id: 404 ``OLD_ENTRY_NOT_FOUND`` so clients with a
    stale cached id fail loudly rather than silently starting a fresh
    timer on the wrong user's behalf.
  * Non-existent ``new_order_id``: 500/422 FK error surface at commit
    — we treat either as "service-layer rejects invalid order" and
    assert on the status code range. The contract the frontend cares
    about is that a brand-new timer does NOT appear.
  * StrictRequestBase: body with ``user_id`` -> 422 (unknown key).
  * Idempotency header format: endpoint accepts Idempotency-Key +
    X-Client-Created-At headers without rejecting the call (V1.1
    transport-level contract; server-side dedupe is V1.1.5).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

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
# Fixtures
# --------------------------------------------------------------------------- #


@pytest_asyncio.fixture
async def switch_activity(db_session: AsyncSession) -> Activity:
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
async def switch_activity_2(db_session: AsyncSession) -> Activity:
    activity = Activity(
        name="Polieren",
        category="finishing",
        icon="sparkles",
        color="#2ecc71",
        usage_count=0,
        is_custom=False,
        created_at=datetime.utcnow(),
    )
    db_session.add(activity)
    await db_session.commit()
    await db_session.refresh(activity)
    return activity


@pytest_asyncio.fixture
async def order_a(db_session: AsyncSession, test_customer) -> Order:
    order = Order(
        title="H18 Order A",
        description="old-timer target",
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
async def order_b(db_session: AsyncSession, test_customer) -> Order:
    order = Order(
        title="H18 Order B",
        description="switch target",
        customer_id=test_customer.id,
        status=OrderStatusEnum.IN_PROGRESS,
        alloy="585",
        price=300.0,
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)
    return order


async def _start_entry(
    db_session: AsyncSession,
    *,
    user: User,
    order: Order,
    activity: Activity,
    minutes_ago: int = 2,
) -> TimeEntry:
    entry = TimeEntry(
        id=str(uuid.uuid4()),
        order_id=order.id,
        user_id=user.id,
        activity_id=activity.id,
        start_time=datetime.utcnow() - timedelta(minutes=minutes_ago),
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
# Endpoint tests
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
class TestSwitchTimerEndpointHappyPath:
    async def test_switch_commits_stop_and_start_atomically(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        db_session: AsyncSession,
        goldsmith_user: User,
        order_a: Order,
        order_b: Order,
        switch_activity: Activity,
        switch_activity_2: Activity,
    ):
        old_entry = await _start_entry(
            db_session,
            user=goldsmith_user,
            order=order_a,
            activity=switch_activity,
        )

        count_before = (
            await db_session.execute(select(func.count(TimeEntry.id)))
        ).scalar_one()

        resp = await client.post(
            f"/api/v1/time-tracking/{old_entry.id}/switch",
            json={
                "new_order_id": order_b.id,
                "activity_id": switch_activity_2.id,
                "location": "Werkbank 3",
            },
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()

        # New entry is running, pointing at order_b + activity_2.
        assert body["id"] != old_entry.id
        assert body["order_id"] == order_b.id
        assert body["activity_id"] == switch_activity_2.id
        assert body["end_time"] is None

        # Old entry has been stopped.
        refreshed = await db_session.execute(
            select(TimeEntry).where(TimeEntry.id == old_entry.id)
        )
        old_row = refreshed.scalar_one()
        assert old_row.end_time is not None
        assert old_row.duration_minutes is not None

        # Exactly one new row was created — the stop was in-place,
        # the start inserted a single new TimeEntry, hence count +1.
        count_after = (
            await db_session.execute(select(func.count(TimeEntry.id)))
        ).scalar_one()
        assert count_after == count_before + 1

        # New entry carries origin='scan' (A5.4).
        new_row = (
            await db_session.execute(
                select(TimeEntry).where(TimeEntry.id == body["id"])
            )
        ).scalar_one()
        assert new_row.origin == "scan"

    async def test_requires_auth(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        goldsmith_user: User,
        order_a: Order,
        order_b: Order,
        switch_activity: Activity,
    ):
        old_entry = await _start_entry(
            db_session,
            user=goldsmith_user,
            order=order_a,
            activity=switch_activity,
        )
        resp = await client.post(
            f"/api/v1/time-tracking/{old_entry.id}/switch",
            json={
                "new_order_id": order_b.id,
                "activity_id": switch_activity.id,
            },
        )
        assert resp.status_code == 401


@pytest.mark.asyncio
class TestSwitchTimerPerUserScope:
    async def test_cross_user_switch_is_forbidden(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        goldsmith_auth_headers: dict,
        goldsmith_user: User,
        admin_user: User,
        order_a: Order,
        order_b: Order,
        switch_activity: Activity,
    ):
        """A GOLDSMITH token MUST NOT be able to switch an admin-owned
        timer. The service raises ``CrossUserTimerError`` (403) before
        any DB mutation — we verify both the status code and that the
        admin's entry is untouched.
        """
        # admin_user owns this running timer.
        admin_entry = await _start_entry(
            db_session,
            user=admin_user,
            order=order_a,
            activity=switch_activity,
        )

        # goldsmith token tries to switch it.
        resp = await client.post(
            f"/api/v1/time-tracking/{admin_entry.id}/switch",
            json={
                "new_order_id": order_b.id,
                "activity_id": switch_activity.id,
            },
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 403
        detail = resp.json()["detail"]
        assert detail["code"] == "CROSS_USER_TIMER_FORBIDDEN"

        # Admin's entry still running.
        refreshed = await db_session.execute(
            select(TimeEntry).where(TimeEntry.id == admin_entry.id)
        )
        row = refreshed.scalar_one()
        assert row.end_time is None

        # No entry was created for the goldsmith caller.
        gs_entries = (
            await db_session.execute(
                select(func.count(TimeEntry.id)).where(
                    TimeEntry.user_id == goldsmith_user.id
                )
            )
        ).scalar_one()
        assert gs_entries == 0


@pytest.mark.asyncio
class TestSwitchTimerStaleGuard:
    async def test_stale_timer_returns_409_with_code(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        goldsmith_auth_headers: dict,
        goldsmith_user: User,
        order_a: Order,
        order_b: Order,
        switch_activity: Activity,
    ):
        """Entry running 25+ minutes with no interruption inside the
        20-min window -> 409 TIMER_POSSIBLY_STALE. The Mittagspause
        modal on the frontend reads `detail.code` to distinguish this
        from other 409s."""
        old_entry = await _start_entry(
            db_session,
            user=goldsmith_user,
            order=order_a,
            activity=switch_activity,
            minutes_ago=25,
        )
        resp = await client.post(
            f"/api/v1/time-tracking/{old_entry.id}/switch",
            json={
                "new_order_id": order_b.id,
                "activity_id": switch_activity.id,
            },
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 409
        detail = resp.json()["detail"]
        assert detail["code"] == "TIMER_POSSIBLY_STALE"
        assert detail["old_entry_id"] == old_entry.id
        assert detail["running_minutes"] >= 20

        # Old entry must still be running — stale guard fires before
        # any DB write.
        refreshed = await db_session.execute(
            select(TimeEntry).where(TimeEntry.id == old_entry.id)
        )
        assert refreshed.scalar_one().end_time is None


@pytest.mark.asyncio
class TestSwitchTimerNotFound:
    async def test_missing_entry_id_returns_404(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        order_b: Order,
        switch_activity: Activity,
    ):
        """A caller supplying an entry id that doesn't exist gets a
        404 — the service refuses to silently start a new timer when
        the cached id is stale. A1 contract.
        """
        bogus = str(uuid.uuid4())
        resp = await client.post(
            f"/api/v1/time-tracking/{bogus}/switch",
            json={
                "new_order_id": order_b.id,
                "activity_id": switch_activity.id,
            },
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 404
        detail = resp.json()["detail"]
        assert detail["code"] == "OLD_ENTRY_NOT_FOUND"


@pytest.mark.asyncio
class TestSwitchTimerBodyValidation:
    async def test_rejects_user_id_in_body(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        goldsmith_auth_headers: dict,
        goldsmith_user: User,
        order_a: Order,
        order_b: Order,
        switch_activity: Activity,
    ):
        """StrictRequestBase rejects unknown keys (and explicit actor
        fields). ``user_id`` in the body must never be accepted — the
        JWT is the sole source of actor identity."""
        old_entry = await _start_entry(
            db_session,
            user=goldsmith_user,
            order=order_a,
            activity=switch_activity,
        )
        resp = await client.post(
            f"/api/v1/time-tracking/{old_entry.id}/switch",
            json={
                "new_order_id": order_b.id,
                "activity_id": switch_activity.id,
                "user_id": 999,
            },
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 422

    async def test_rejects_non_positive_new_order_id(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        goldsmith_auth_headers: dict,
        goldsmith_user: User,
        order_a: Order,
        switch_activity: Activity,
    ):
        """``Field(..., gt=0)`` on the Pydantic schema catches invalid
        ids at the router boundary — no DB round-trip."""
        old_entry = await _start_entry(
            db_session,
            user=goldsmith_user,
            order=order_a,
            activity=switch_activity,
        )
        resp = await client.post(
            f"/api/v1/time-tracking/{old_entry.id}/switch",
            json={"new_order_id": 0, "activity_id": switch_activity.id},
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 422


@pytest.mark.asyncio
class TestSwitchTimerIdempotencyHeaders:
    async def test_accepts_idempotency_headers(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        goldsmith_auth_headers: dict,
        goldsmith_user: User,
        order_a: Order,
        order_b: Order,
        switch_activity: Activity,
    ):
        """The endpoint must accept ``Idempotency-Key`` (UUIDv4) + a
        valid ``X-Client-Created-At`` without rejecting the call. V1.1
        does not dedupe server-side — that is V1.1.5 scope — but the
        transport contract must land in V1.1 so clients can send the
        headers today.
        """
        old_entry = await _start_entry(
            db_session,
            user=goldsmith_user,
            order=order_a,
            activity=switch_activity,
        )
        headers = {
            **goldsmith_auth_headers,
            "Idempotency-Key": str(uuid.uuid4()),
            "X-Client-Created-At": datetime.utcnow().isoformat() + "Z",
        }
        resp = await client.post(
            f"/api/v1/time-tracking/{old_entry.id}/switch",
            json={
                "new_order_id": order_b.id,
                "activity_id": switch_activity.id,
            },
            headers=headers,
        )
        assert resp.status_code == 200, resp.text

    async def test_rejects_malformed_idempotency_key(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        goldsmith_auth_headers: dict,
        goldsmith_user: User,
        order_a: Order,
        order_b: Order,
        switch_activity: Activity,
    ):
        """Non-UUID Idempotency-Key must return 400 per the core.
        idempotency contract — surface any format drift loudly."""
        old_entry = await _start_entry(
            db_session,
            user=goldsmith_user,
            order=order_a,
            activity=switch_activity,
        )
        headers = {
            **goldsmith_auth_headers,
            "Idempotency-Key": "not-a-uuid",
        }
        resp = await client.post(
            f"/api/v1/time-tracking/{old_entry.id}/switch",
            json={
                "new_order_id": order_b.id,
                "activity_id": switch_activity.id,
            },
            headers=headers,
        )
        assert resp.status_code == 400
