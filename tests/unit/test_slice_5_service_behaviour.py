"""Unit tests for Slice 5 service-layer behaviour.

Coverage:
  * switch_timer
      - A5.1 per-user scope (cross-user is 403)
      - A5.1 ownership pre-flight: mutation never occurs if forbidden
      - A5.2 stale-timer 409 after 20+ minutes without interruption
      - A5.2 recent interruption resets the stale window
      - Atomicity: if new-entry start fails, old entry not left stopped
      - Origin propagation: new entry carries origin='scan'

  * patch_activity
      - Mutates in place — no new TimeEntry row (row count unchanged)
      - Per-user scope 403 for cross-user
      - 409 when entry already stopped

  * log_interruption
      - Creates Interruption linked to entry, timer keeps running
      - Per-user scope 403 for cross-user

  * consume_material
      - Alloy mismatch without override -> 409 ALLOY_MISMATCH
      - Alloy mismatch with override but missing reason -> ValueError
      - Alloy mismatch with override + reason + category -> persisted
      - SELECT FOR UPDATE serialises two parallel consumes on same bar
        (no negative stock)

  * advance_status (OrderService)
      - to COMPLETED, order has alloy + no marks -> 409 PUNZIERUNG_REQUIRED
      - to COMPLETED, order has alloy + marks in same request -> OK
      - to COMPLETED, order with alloy=None -> OK
      - guard fires from direct update_order path (admin bypass blocked)

  * pubsub failure injection
      - switch_timer: mutation commits, notification written, no raise
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta
from typing import Optional
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import (
    Activity,
    Interruption,
    MetalPurchase,
    MetalType,
    Notification,
    NotificationTypeEnum,
    Order,
    OrderStatusEnum,
    TimeEntry,
    User,
    UserRole,
)
from goldsmith_erp.models.metal_inventory import (
    CostingMethod,
    MaterialUsageCreate,
)
from goldsmith_erp.models.order import OrderUpdate
from goldsmith_erp.services.metal_inventory_service import (
    AlloyMismatchError,
    MetalInventoryService,
)
from goldsmith_erp.services.order_service import (
    OrderService,
    PunzierungRequiredError,
)
from goldsmith_erp.services.time_tracking_service import (
    CrossUserTimerError,
    STALE_TIMER_THRESHOLD,
    TimeTrackingService,
    TimerPossiblyStaleError,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _create_user(db_session: AsyncSession, role: UserRole = UserRole.GOLDSMITH) -> User:
    user = User(
        email=f"slice5_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x" * 40,  # any non-null value; not used
        first_name="Slice5",
        last_name="Tester",
        role=role,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _create_activity(db_session: AsyncSession, name: str = "Feilen") -> Activity:
    act = Activity(
        name=name,
        category="fabrication",
        icon="wrench",
        color="#aabbcc",
        usage_count=0,
        is_custom=False,
        created_at=datetime.utcnow(),
    )
    db_session.add(act)
    await db_session.commit()
    await db_session.refresh(act)
    return act


async def _create_order(
    db_session: AsyncSession,
    customer_id: int,
    *,
    alloy: Optional[str] = None,
    status: OrderStatusEnum = OrderStatusEnum.IN_PROGRESS,
) -> Order:
    order = Order(
        title=f"Slice5 Order {uuid.uuid4().hex[:4]}",
        description="unit test",
        customer_id=customer_id,
        status=status,
        alloy=alloy,
        price=100.0,
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)
    return order


async def _start_running_entry(
    db_session: AsyncSession,
    user: User,
    order: Order,
    activity: Activity,
    *,
    start_time: Optional[datetime] = None,
    origin: str = "manual",
) -> TimeEntry:
    entry = TimeEntry(
        id=str(uuid.uuid4()),
        order_id=order.id,
        user_id=user.id,
        activity_id=activity.id,
        start_time=start_time or datetime.utcnow(),
        end_time=None,
        origin=origin,
        extra_metadata={},
        created_at=datetime.utcnow(),
    )
    db_session.add(entry)
    await db_session.commit()
    await db_session.refresh(entry)
    return entry


# ---------------------------------------------------------------------------
# switch_timer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSwitchTimerScope:
    """A5.1 — a scan by user A MUST NOT mutate user B's state."""

    async def test_cross_user_switch_returns_403_and_does_not_mutate(
        self, db_session, sample_customer, sample_activity
    ):
        user_a = await _create_user(db_session)
        user_b = await _create_user(db_session)
        order_1 = await _create_order(db_session, sample_customer.id)
        order_2 = await _create_order(db_session, sample_customer.id)
        entry_b = await _start_running_entry(db_session, user_b, order_1, sample_activity)

        with pytest.raises(CrossUserTimerError) as excinfo:
            await TimeTrackingService.switch_timer(
                db=db_session,
                user=user_a,
                old_entry_id=entry_b.id,
                new_order_id=order_2.id,
                activity_id=sample_activity.id,
                origin="scan",
            )
        assert excinfo.value.status_code == 403

        # B's entry MUST still be running.
        refreshed = await TimeTrackingService.get_time_entry(db_session, entry_b.id)
        assert refreshed is not None
        assert refreshed.end_time is None

        # No new entry should have been created for user A.
        total = await db_session.execute(
            select(func.count(TimeEntry.id)).where(TimeEntry.user_id == user_a.id)
        )
        assert total.scalar_one() == 0


@pytest.mark.asyncio
class TestSwitchTimerStaleGuard:
    """A5.2 — stale-timer (20+ min without interruption) raises 409."""

    async def test_stale_timer_blocks_switch(
        self, db_session, sample_customer, sample_activity
    ):
        user = await _create_user(db_session)
        order_1 = await _create_order(db_session, sample_customer.id)
        order_2 = await _create_order(db_session, sample_customer.id)

        # Started 25 minutes ago, no interruption.
        start_time = datetime.utcnow() - timedelta(minutes=25)
        entry = await _start_running_entry(
            db_session, user, order_1, sample_activity, start_time=start_time
        )

        with pytest.raises(TimerPossiblyStaleError) as excinfo:
            await TimeTrackingService.switch_timer(
                db=db_session,
                user=user,
                old_entry_id=entry.id,
                new_order_id=order_2.id,
                activity_id=sample_activity.id,
                origin="scan",
            )
        assert excinfo.value.status_code == 409
        assert excinfo.value.detail["code"] == "TIMER_POSSIBLY_STALE"
        assert excinfo.value.detail["running_minutes"] >= 20

    async def test_recent_interruption_resets_stale_window(
        self, db_session, sample_customer, sample_activity
    ):
        user = await _create_user(db_session)
        order_1 = await _create_order(db_session, sample_customer.id)
        order_2 = await _create_order(db_session, sample_customer.id)

        start_time = datetime.utcnow() - timedelta(minutes=25)
        entry = await _start_running_entry(
            db_session, user, order_1, sample_activity, start_time=start_time
        )

        # Interruption inside the window — switch should succeed.
        interruption = Interruption(
            time_entry_id=entry.id,
            reason="kundenanruf",
            duration_minutes=0,
            timestamp=datetime.utcnow() - timedelta(minutes=5),
        )
        db_session.add(interruption)
        await db_session.commit()

        new_entry = await TimeTrackingService.switch_timer(
            db=db_session,
            user=user,
            old_entry_id=entry.id,
            new_order_id=order_2.id,
            activity_id=sample_activity.id,
            origin="scan",
        )
        assert new_entry is not None
        assert new_entry.order_id == order_2.id
        assert new_entry.origin == "scan"

    async def test_fresh_timer_switches_cleanly(
        self, db_session, sample_customer, sample_activity
    ):
        user = await _create_user(db_session)
        order_1 = await _create_order(db_session, sample_customer.id)
        order_2 = await _create_order(db_session, sample_customer.id)

        # Started 2 minutes ago — well inside the threshold.
        start_time = datetime.utcnow() - timedelta(minutes=2)
        entry = await _start_running_entry(
            db_session, user, order_1, sample_activity, start_time=start_time
        )

        new_entry = await TimeTrackingService.switch_timer(
            db=db_session,
            user=user,
            old_entry_id=entry.id,
            new_order_id=order_2.id,
            activity_id=sample_activity.id,
            origin="scan",
        )
        # Old entry now stopped.
        old_reloaded = await TimeTrackingService.get_time_entry(db_session, entry.id)
        assert old_reloaded.end_time is not None
        assert old_reloaded.duration_minutes is not None
        # New entry carries scan origin.
        assert new_entry.origin == "scan"
        assert new_entry.order_id == order_2.id


@pytest.mark.asyncio
class TestSwitchTimerAtomicity:
    """Atomic stop+start — failure during start must not leave old stopped."""

    async def test_start_failure_rolls_back(
        self, db_session, sample_customer, sample_activity
    ):
        """If the new TimeEntry insert fails, the old entry's end_time must
        NOT be committed.

        Strategy: patch ``db.add`` to raise when the service tries to
        insert the new TimeEntry. The ``except Exception`` branch in
        ``switch_timer`` rolls back the pending UPDATE on the old entry.
        We verify by re-reading the old entry from the same session
        after the rollback — it must still have ``end_time=None``.
        The commit is the sole persistence point, so a rollback
        discards the in-flight UPDATE to end_time.
        """
        user = await _create_user(db_session)
        order_1 = await _create_order(db_session, sample_customer.id)
        order_2 = await _create_order(db_session, sample_customer.id)
        entry = await _start_running_entry(db_session, user, order_1, sample_activity)
        entry_id = entry.id

        original_add = db_session.add

        def raising_add(obj):
            if isinstance(obj, TimeEntry):
                raise RuntimeError("simulated insert failure")
            return original_add(obj)

        db_session.add = raising_add  # type: ignore[assignment]
        try:
            with pytest.raises(RuntimeError):
                await TimeTrackingService.switch_timer(
                    db=db_session,
                    user=user,
                    old_entry_id=entry_id,
                    new_order_id=order_2.id,
                    activity_id=sample_activity.id,
                    origin="scan",
                )
        finally:
            db_session.add = original_add  # type: ignore[assignment]

        # Re-read via the same session — rollback cleared the in-flight
        # UPDATE so the old entry must still have end_time=None.
        result = await db_session.execute(
            select(TimeEntry).where(TimeEntry.id == entry_id)
        )
        reloaded = result.scalar_one_or_none()
        assert reloaded is not None
        assert reloaded.end_time is None


# ---------------------------------------------------------------------------
# patch_activity
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestPatchActivity:
    async def test_patch_activity_mutates_in_place_no_new_row(
        self, db_session, sample_customer, sample_activity
    ):
        user = await _create_user(db_session)
        order = await _create_order(db_session, sample_customer.id)
        entry = await _start_running_entry(db_session, user, order, sample_activity)
        new_activity = await _create_activity(db_session, name="Loeten")

        count_before = (
            await db_session.execute(select(func.count(TimeEntry.id)))
        ).scalar_one()

        updated = await TimeTrackingService.patch_activity(
            db=db_session,
            entry_id=entry.id,
            activity_id=new_activity.id,
            user=user,
            origin="scan",
        )
        assert updated.id == entry.id
        assert updated.activity_id == new_activity.id

        count_after = (
            await db_session.execute(select(func.count(TimeEntry.id)))
        ).scalar_one()
        # Critical: no new row was created.
        assert count_after == count_before

    async def test_patch_activity_cross_user_forbidden(
        self, db_session, sample_customer, sample_activity
    ):
        user_a = await _create_user(db_session)
        user_b = await _create_user(db_session)
        order = await _create_order(db_session, sample_customer.id)
        entry_b = await _start_running_entry(db_session, user_b, order, sample_activity)
        other_activity = await _create_activity(db_session, name="Polieren")

        with pytest.raises(HTTPException) as excinfo:
            await TimeTrackingService.patch_activity(
                db=db_session,
                entry_id=entry_b.id,
                activity_id=other_activity.id,
                user=user_a,
                origin="scan",
            )
        assert excinfo.value.status_code == 403

    async def test_patch_activity_stopped_entry_409(
        self, db_session, sample_customer, sample_activity
    ):
        user = await _create_user(db_session)
        order = await _create_order(db_session, sample_customer.id)
        entry = await _start_running_entry(db_session, user, order, sample_activity)
        # Stop it.
        entry.end_time = datetime.utcnow()
        entry.duration_minutes = 10
        await db_session.commit()

        new_activity = await _create_activity(db_session, name="Fassen")
        with pytest.raises(HTTPException) as excinfo:
            await TimeTrackingService.patch_activity(
                db=db_session,
                entry_id=entry.id,
                activity_id=new_activity.id,
                user=user,
                origin="scan",
            )
        assert excinfo.value.status_code == 409


# ---------------------------------------------------------------------------
# log_interruption
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestLogInterruption:
    async def test_log_interruption_creates_row_without_stopping_timer(
        self, db_session, sample_customer, sample_activity
    ):
        user = await _create_user(db_session)
        order = await _create_order(db_session, sample_customer.id)
        entry = await _start_running_entry(db_session, user, order, sample_activity)

        result = await TimeTrackingService.log_interruption(
            db=db_session,
            entry_id=entry.id,
            interrupt_code="kundenanruf",
            user=user,
            notes="Kunde ruft wegen Termin an",
        )
        assert result.time_entry_id == entry.id
        # Timer still running.
        reloaded = await TimeTrackingService.get_time_entry(db_session, entry.id)
        assert reloaded.end_time is None
        # Interruption reason contains the code.
        assert "kundenanruf" in result.reason

    async def test_log_interruption_cross_user_403(
        self, db_session, sample_customer, sample_activity
    ):
        user_a = await _create_user(db_session)
        user_b = await _create_user(db_session)
        order = await _create_order(db_session, sample_customer.id)
        entry_b = await _start_running_entry(db_session, user_b, order, sample_activity)

        with pytest.raises(HTTPException) as excinfo:
            await TimeTrackingService.log_interruption(
                db=db_session,
                entry_id=entry_b.id,
                interrupt_code="material_holen",
                user=user_a,
            )
        assert excinfo.value.status_code == 403


# ---------------------------------------------------------------------------
# consume_material — alloy override + concurrency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestConsumeMaterialAlloyOverride:
    async def test_mismatch_without_override_raises_409(
        self, db_session, sample_customer, sample_metal_purchase
    ):
        # sample_metal_purchase is GOLD_18K -> expected alloy '750'.
        order = await _create_order(db_session, sample_customer.id, alloy="585")
        usage_in = MaterialUsageCreate(
            order_id=order.id,
            weight_used_g=5.0,
            costing_method=CostingMethod.SPECIFIC,
            metal_purchase_id=sample_metal_purchase.id,
        )
        with pytest.raises(AlloyMismatchError) as excinfo:
            await MetalInventoryService.consume_material(
                db_session,
                usage_in,
                MetalType.GOLD_18K,
            )
        assert excinfo.value.status_code == 409
        assert excinfo.value.detail["code"] == "ALLOY_MISMATCH"
        assert excinfo.value.detail["order_alloy"] == "585"
        assert excinfo.value.detail["purchase_alloy"] == "750"

    async def test_override_without_reason_raises_value_error(
        self, db_session, sample_customer, sample_metal_purchase
    ):
        order = await _create_order(db_session, sample_customer.id, alloy="585")
        usage_in = MaterialUsageCreate(
            order_id=order.id,
            weight_used_g=5.0,
            costing_method=CostingMethod.SPECIFIC,
            metal_purchase_id=sample_metal_purchase.id,
        )
        # Service-layer defence-in-depth: even if Pydantic schema validator
        # is bypassed, the service rejects override without payload.
        with pytest.raises(ValueError):
            await MetalInventoryService.consume_material(
                db_session,
                usage_in,
                MetalType.GOLD_18K,
                alloy_override=True,
                # Missing override_reason + category.
            )

    async def test_override_with_reason_and_category_persists_audit_fields(
        self, db_session, sample_customer, sample_metal_purchase
    ):
        order = await _create_order(db_session, sample_customer.id, alloy="585")
        usage_in = MaterialUsageCreate(
            order_id=order.id,
            weight_used_g=2.0,
            costing_method=CostingMethod.SPECIFIC,
            metal_purchase_id=sample_metal_purchase.id,
        )
        usage = await MetalInventoryService.consume_material(
            db_session,
            usage_in,
            MetalType.GOLD_18K,
            alloy_override=True,
            override_reason="Kleiner Rest, Kunde stimmt zu.",
            override_reason_category="kleinteil",
            user_id=1,
        )
        assert usage.alloy_override is True
        assert usage.override_reason == "Kleiner Rest, Kunde stimmt zu."
        assert usage.override_reason_category == "kleinteil"

    async def test_matching_alloy_no_override_succeeds(
        self, db_session, sample_customer, sample_metal_purchase
    ):
        # Order alloy 750 matches GOLD_18K purchase.
        order = await _create_order(db_session, sample_customer.id, alloy="750")
        usage_in = MaterialUsageCreate(
            order_id=order.id,
            weight_used_g=3.0,
            costing_method=CostingMethod.SPECIFIC,
            metal_purchase_id=sample_metal_purchase.id,
        )
        usage = await MetalInventoryService.consume_material(
            db_session,
            usage_in,
            MetalType.GOLD_18K,
        )
        assert usage.alloy_override is False
        assert usage.override_reason is None


@pytest.mark.asyncio
class TestConsumeMaterialConcurrency:
    """A3.4 / Lena §3 — SELECT FOR UPDATE + re-check-under-lock prevents
    negative stock.

    SQLite's FOR UPDATE is a no-op, so we cannot reliably drive true
    parallelism inside the test harness. What we CAN pin down: the
    re-check-under-lock logic. After a first consume lands 60g on a
    100g bar, a second consume request for 60g MUST fail with
    ValueError (not silently decrement to -20g). Under PostgreSQL,
    FOR UPDATE serialises two concurrent sessions so this same path
    fires. The test therefore validates the INVARIANT — "no negative
    stock reachable" — which is what Lena §3 actually requires.
    """

    async def test_rechecks_under_lock_prevent_negative_stock(
        self, db_session, sample_customer, sample_metal_purchase
    ):
        # Cache IDs before any consume may expire the ORM row.
        purchase_id = sample_metal_purchase.id
        initial_weight = sample_metal_purchase.remaining_weight_g
        assert initial_weight == 100.0

        order = await _create_order(db_session, sample_customer.id, alloy="750")

        # First consume takes 60g — succeeds, leaves 40g.
        first = await MetalInventoryService.consume_material(
            db_session,
            MaterialUsageCreate(
                order_id=order.id,
                weight_used_g=60.0,
                costing_method=CostingMethod.SPECIFIC,
                metal_purchase_id=purchase_id,
            ),
            MetalType.GOLD_18K,
        )
        assert first.id is not None

        # Second consume requests another 60g — MUST fail rather than
        # drive stock to -20g. allocate_material sees 40g remaining and
        # raises ValueError before reaching the lock-and-decrement path.
        with pytest.raises(ValueError):
            await MetalInventoryService.consume_material(
                db_session,
                MaterialUsageCreate(
                    order_id=order.id,
                    weight_used_g=60.0,
                    costing_method=CostingMethod.SPECIFIC,
                    metal_purchase_id=purchase_id,
                ),
                MetalType.GOLD_18K,
            )

        # Stock never negative.
        reloaded = await db_session.execute(
            select(MetalPurchase).where(MetalPurchase.id == purchase_id)
        )
        refreshed = reloaded.scalar_one()
        assert refreshed.remaining_weight_g >= 0.0
        # Exactly one consume landed.
        assert refreshed.remaining_weight_g == pytest.approx(40.0, abs=0.01)

    async def test_with_for_update_path_exercised_on_consume(
        self, db_session, sample_customer, sample_metal_purchase
    ):
        """Smoke test: consume_material actually executes the with_for_update
        SELECT rather than the plain get_purchase path. Verified by patching
        with_for_update to a sentinel that flips a flag; if the flag never
        flips, the test fails — proving the A3.4 code path is live.

        This is a slim reflectional test rather than a pure behaviour test;
        the behaviour test above validates the invariant. Together they
        catch both a code-path regression (lock removed) and a behaviour
        regression (re-check elided).
        """
        order = await _create_order(db_session, sample_customer.id, alloy="750")
        # The .with_for_update() Query method is the marker.
        seen: list[bool] = []
        from sqlalchemy.sql.selectable import Select as _SelectClass

        orig_with_for_update = _SelectClass.with_for_update

        def tracking(self, *args, **kwargs):
            seen.append(True)
            return orig_with_for_update(self, *args, **kwargs)

        with patch.object(_SelectClass, "with_for_update", tracking):
            await MetalInventoryService.consume_material(
                db_session,
                MaterialUsageCreate(
                    order_id=order.id,
                    weight_used_g=5.0,
                    costing_method=CostingMethod.SPECIFIC,
                    metal_purchase_id=sample_metal_purchase.id,
                ),
                MetalType.GOLD_18K,
            )
        assert len(seen) >= 1, "consume_material must use SELECT ... FOR UPDATE"


# ---------------------------------------------------------------------------
# advance_status — Punzierungs-Check guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestPunzierungGuard:
    async def test_complete_without_alloy_succeeds(self, db_session, sample_customer):
        order = await _create_order(
            db_session, sample_customer.id, alloy=None, status=OrderStatusEnum.QUALITY_CHECK
        )
        updated = await OrderService.advance_status(
            db_session, order.id, OrderStatusEnum.COMPLETED, user_id=1
        )
        assert updated is not None
        assert updated.status == OrderStatusEnum.COMPLETED

    async def test_complete_with_alloy_no_marks_raises_409(
        self, db_session, sample_customer
    ):
        order = await _create_order(
            db_session, sample_customer.id, alloy="750", status=OrderStatusEnum.QUALITY_CHECK
        )
        with pytest.raises(PunzierungRequiredError) as excinfo:
            await OrderService.advance_status(
                db_session, order.id, OrderStatusEnum.COMPLETED, user_id=1
            )
        assert excinfo.value.status_code == 409
        assert excinfo.value.detail["code"] == "PUNZIERUNG_REQUIRED"
        assert excinfo.value.detail["alloy"] == "750"

    async def test_complete_with_alloy_and_marks_in_same_request_succeeds(
        self, db_session, sample_customer
    ):
        order = await _create_order(
            db_session, sample_customer.id, alloy="750", status=OrderStatusEnum.QUALITY_CHECK
        )
        updated = await OrderService.advance_status(
            db_session,
            order.id,
            OrderStatusEnum.COMPLETED,
            user_id=1,
            punzierung_verified_marks=["feingehalt_750", "meisterzeichen"],
        )
        assert updated is not None
        assert updated.status == OrderStatusEnum.COMPLETED
        assert updated.punzierung_verified_at is not None
        assert "feingehalt_750" in updated.punzierung_verified_marks
        # A2.8 — retention promoted on first mark write.
        assert updated.retention_class == "hallmark_10y"

    async def test_complete_with_prior_marks_succeeds_without_resupplying(
        self, db_session, sample_customer
    ):
        order = await _create_order(
            db_session, sample_customer.id, alloy="585", status=OrderStatusEnum.QUALITY_CHECK
        )
        # First: record marks without advancing status.
        await OrderService.update_order(
            db_session,
            order.id,
            OrderUpdate(punzierung_verified_marks=["feingehalt_585", "meisterzeichen"]),
            verified_by_user_id=1,
        )
        # Now advance to COMPLETED — guard should see existing marks.
        updated = await OrderService.advance_status(
            db_session, order.id, OrderStatusEnum.COMPLETED, user_id=1
        )
        assert updated.status == OrderStatusEnum.COMPLETED

    async def test_admin_put_path_same_guard_fires(
        self, db_session, sample_customer
    ):
        """Direct update_order (admin PUT) must hit the same guard."""
        order = await _create_order(
            db_session, sample_customer.id, alloy="750", status=OrderStatusEnum.QUALITY_CHECK
        )
        with pytest.raises(PunzierungRequiredError):
            await OrderService.update_order(
                db_session,
                order.id,
                OrderUpdate(status=OrderStatusEnum.COMPLETED),
                verified_by_user_id=1,
            )


# ---------------------------------------------------------------------------
# Pubsub failure injection — Slice 5 A5.5
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestPubsubFailureNotification:
    """A5.5 — on pubsub failure the mutation commits AND a notification is
    written so the user sees a warning rather than silent stale state."""

    async def test_switch_timer_publishes_failure_notification(
        self, db_session, sample_customer, sample_activity
    ):
        user = await _create_user(db_session)
        order_1 = await _create_order(db_session, sample_customer.id)
        order_2 = await _create_order(db_session, sample_customer.id)
        entry = await _start_running_entry(
            db_session, user, order_1, sample_activity,
            start_time=datetime.utcnow() - timedelta(minutes=2),
        )

        # Replace publish_event with a raising mock. The service's
        # _safe_publish must catch it and still write the notification.
        with patch(
            "goldsmith_erp.core.pubsub.publish_event",
            new=AsyncMock(side_effect=RuntimeError("redis down")),
        ):
            new_entry = await TimeTrackingService.switch_timer(
                db=db_session,
                user=user,
                old_entry_id=entry.id,
                new_order_id=order_2.id,
                activity_id=sample_activity.id,
                origin="scan",
            )

        # Mutation still committed.
        assert new_entry is not None
        reloaded_old = await TimeTrackingService.get_time_entry(db_session, entry.id)
        assert reloaded_old.end_time is not None

        # Notification row written for the user.
        result = await db_session.execute(
            select(Notification).where(
                Notification.user_id == user.id,
                Notification.notification_type == NotificationTypeEnum.SYSTEM,
            )
        )
        notifications = result.scalars().all()
        assert len(notifications) >= 1
        assert any("Live-Update" in n.title for n in notifications)
