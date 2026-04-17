"""Pubsub-failure handling across service boundaries (Slice 6 / A5.5).

Slice 5 introduced ``_safe_publish`` patterns on three services:

  * TimeTrackingService — ``switch_timer`` / ``patch_activity`` / ``log_interruption``
  * MetalInventoryService — ``consume_material`` via ``_safe_publish_material_event``
  * OrderService — ``update_order`` / ``advance_status`` via ``_safe_publish_order_event``

The A5.5 contract is uniform across all three:

  1. The DB mutation commits successfully.
  2. Pubsub ``publish_event`` raises ``ConnectionError`` / generic ``Exception``.
  3. A ``Notification`` row is written for the user with a clear
     German-language message instructing them to reload.
  4. The ORIGINAL exception is NEVER re-raised to the router — the
     caller sees the successful response.

This test file exercises that contract for each of the three services
so a regression in any one's failure handling fails loudly.

An existing test in ``tests/unit/test_slice_5_service_behaviour.py::
TestSwitchTimerPubsubFailure`` covers switch_timer. This file extends
the coverage to:

  * TimeTrackingService.patch_activity
  * TimeTrackingService.log_interruption
  * MetalInventoryService.consume_material
  * OrderService.update_order
  * OrderService.advance_status
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Optional
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import (
    Activity,
    Customer,
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
from goldsmith_erp.models.metal_inventory import CostingMethod, MaterialUsageCreate
from goldsmith_erp.models.order import OrderUpdate
from goldsmith_erp.services.metal_inventory_service import MetalInventoryService
from goldsmith_erp.services.order_service import OrderService
from goldsmith_erp.services.time_tracking_service import TimeTrackingService


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


async def _user(db: AsyncSession, role: UserRole = UserRole.GOLDSMITH) -> User:
    user = User(
        email=f"pubsub_{uuid.uuid4().hex[:8]}@test.example",
        hashed_password="x" * 40,
        first_name="Pubsub",
        last_name="Tester",
        role=role,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _activity(db: AsyncSession, name: str = "Feilen") -> Activity:
    act = Activity(
        name=name,
        category="fabrication",
        icon="wrench",
        color="#aabbcc",
        usage_count=0,
        is_custom=False,
        created_at=datetime.utcnow(),
    )
    db.add(act)
    await db.commit()
    await db.refresh(act)
    return act


async def _order(
    db: AsyncSession,
    customer_id: int,
    *,
    alloy: Optional[str] = None,
    status: OrderStatusEnum = OrderStatusEnum.IN_PROGRESS,
) -> Order:
    order = Order(
        title=f"Pubsub Order {uuid.uuid4().hex[:4]}",
        description="pubsub failure test",
        customer_id=customer_id,
        status=status,
        alloy=alloy,
        price=100.0,
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)
    return order


async def _running_entry(
    db: AsyncSession, user: User, order: Order, activity: Activity
) -> TimeEntry:
    entry = TimeEntry(
        id=str(uuid.uuid4()),
        order_id=order.id,
        user_id=user.id,
        activity_id=activity.id,
        start_time=datetime.utcnow() - timedelta(minutes=2),
        end_time=None,
        origin="manual",
        extra_metadata={},
        created_at=datetime.utcnow(),
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


async def _metal_purchase(db: AsyncSession, weight_g: float = 100.0) -> MetalPurchase:
    purchase = MetalPurchase(
        date_purchased=datetime.utcnow(),
        metal_type=MetalType.GOLD_18K,
        weight_g=weight_g,
        remaining_weight_g=weight_g,
        price_total=weight_g * 45.0,
        price_per_gram=45.0,
        supplier="Pubsub Supplier",
        invoice_number=f"PUBSUB-{uuid.uuid4().hex[:6]}",
    )
    db.add(purchase)
    await db.commit()
    await db.refresh(purchase)
    return purchase


async def _user_notifications(db: AsyncSession, user_id: int):
    result = await db.execute(
        select(Notification).where(Notification.user_id == user_id)
    )
    return list(result.scalars().all())


# --------------------------------------------------------------------------- #
# TimeTrackingService.patch_activity — pubsub failure
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
class TestPatchActivityPubsubFailure:
    async def test_patch_activity_commits_despite_pubsub_connection_error(
        self, db_session, sample_customer
    ):
        user = await _user(db_session)
        act_1 = await _activity(db_session, "Feilen")
        act_2 = await _activity(db_session, "Loeten")
        order = await _order(db_session, sample_customer.id)
        entry = await _running_entry(db_session, user, order, act_1)
        entry_id = entry.id

        with patch(
            "goldsmith_erp.core.pubsub.publish_event",
            new=AsyncMock(side_effect=ConnectionError("redis unreachable")),
        ):
            updated = await TimeTrackingService.patch_activity(
                db=db_session,
                entry_id=entry_id,
                activity_id=act_2.id,
                user=user,
                origin="scan",
            )

        # Mutation committed.
        assert updated is not None
        assert updated.activity_id == act_2.id

        # Re-read from DB to confirm.
        result = await db_session.execute(
            select(TimeEntry).where(TimeEntry.id == entry_id)
        )
        reloaded = result.scalar_one()
        assert reloaded.activity_id == act_2.id

        # Notification written for the user.
        notifications = await _user_notifications(db_session, user.id)
        assert len(notifications) >= 1
        system_notifs = [
            n for n in notifications
            if n.notification_type == NotificationTypeEnum.SYSTEM
        ]
        assert len(system_notifs) >= 1


# --------------------------------------------------------------------------- #
# TimeTrackingService.log_interruption — pubsub failure
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
class TestLogInterruptionPubsubFailure:
    async def test_log_interruption_commits_despite_pubsub_error(
        self, db_session, sample_customer
    ):
        user = await _user(db_session)
        act = await _activity(db_session)
        order = await _order(db_session, sample_customer.id)
        entry = await _running_entry(db_session, user, order, act)
        entry_id = entry.id

        with patch(
            "goldsmith_erp.core.pubsub.publish_event",
            new=AsyncMock(side_effect=ConnectionError("redis down")),
        ):
            interruption = await TimeTrackingService.log_interruption(
                db=db_session,
                entry_id=entry_id,
                interrupt_code="kundenanruf",
                user=user,
                notes="30s call",
                origin="scan",
            )

        # Interruption row committed.
        assert interruption is not None
        result = await db_session.execute(
            select(Interruption).where(Interruption.time_entry_id == entry_id)
        )
        stored = result.scalars().all()
        assert len(stored) == 1

        # Notification written.
        notifications = await _user_notifications(db_session, user.id)
        assert any(
            n.notification_type == NotificationTypeEnum.SYSTEM
            for n in notifications
        )


# --------------------------------------------------------------------------- #
# MetalInventoryService.consume_material — pubsub failure
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
class TestConsumeMaterialPubsubFailure:
    async def test_consume_commits_despite_pubsub_error(
        self, db_session, sample_customer
    ):
        user = await _user(db_session)
        order = await _order(db_session, sample_customer.id, alloy="750")
        purchase = await _metal_purchase(db_session, weight_g=100.0)
        purchase_id = purchase.id

        with patch(
            "goldsmith_erp.core.pubsub.publish_event",
            new=AsyncMock(side_effect=ConnectionError("redis timeout")),
        ):
            usage = await MetalInventoryService.consume_material(
                db_session,
                MaterialUsageCreate(
                    order_id=order.id,
                    weight_used_g=5.0,
                    costing_method=CostingMethod.SPECIFIC,
                    metal_purchase_id=purchase_id,
                ),
                MetalType.GOLD_18K,
                user_id=user.id,
                origin="scan",
            )

        # Usage row committed; stock decremented.
        assert usage is not None
        result = await db_session.execute(
            select(MetalPurchase).where(MetalPurchase.id == purchase_id)
        )
        reloaded = result.scalar_one()
        assert reloaded.remaining_weight_g == pytest.approx(95.0, abs=0.01)

        # Notification written for the user.
        notifications = await _user_notifications(db_session, user.id)
        system_notifs = [
            n for n in notifications
            if n.notification_type == NotificationTypeEnum.SYSTEM
        ]
        assert len(system_notifs) >= 1
        # Message scope: material-specific.
        assert any("Material" in n.title for n in system_notifs)

    async def test_consume_without_user_id_does_not_raise(
        self, db_session, sample_customer
    ):
        """user_id=None skips the notification write (no user to attribute
        to) but must still commit the mutation and never raise."""
        order = await _order(db_session, sample_customer.id, alloy="750")
        purchase = await _metal_purchase(db_session, weight_g=100.0)

        with patch(
            "goldsmith_erp.core.pubsub.publish_event",
            new=AsyncMock(side_effect=ConnectionError("boom")),
        ):
            usage = await MetalInventoryService.consume_material(
                db_session,
                MaterialUsageCreate(
                    order_id=order.id,
                    weight_used_g=3.0,
                    costing_method=CostingMethod.SPECIFIC,
                    metal_purchase_id=purchase.id,
                ),
                MetalType.GOLD_18K,
                user_id=None,
                origin="manual",
            )
        assert usage is not None


# --------------------------------------------------------------------------- #
# OrderService.update_order — pubsub failure
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
class TestUpdateOrderPubsubFailure:
    async def test_update_order_commits_despite_pubsub_error(
        self, db_session, sample_customer
    ):
        user = await _user(db_session)
        # Alloy=None so the Punzierungs guard is a no-op for this test.
        order = await _order(db_session, sample_customer.id, alloy=None)

        with patch(
            "goldsmith_erp.services.order_service.publish_event",
            new=AsyncMock(side_effect=ConnectionError("redis reset")),
        ):
            updated = await OrderService.update_order(
                db_session,
                order.id,
                OrderUpdate(status=OrderStatusEnum.COMPLETED),
                verified_by_user_id=user.id,
                origin="manual",
            )

        # Mutation committed.
        assert updated is not None
        assert updated.status == OrderStatusEnum.COMPLETED

        # Notification row written.
        notifications = await _user_notifications(db_session, user.id)
        system_notifs = [
            n for n in notifications
            if n.notification_type == NotificationTypeEnum.SYSTEM
        ]
        assert len(system_notifs) >= 1
        assert any(
            "Auftragsaenderung" in n.title for n in system_notifs
        )

    async def test_update_order_user_id_none_does_not_raise(
        self, db_session, sample_customer
    ):
        """``verified_by_user_id=None`` is the anonymous path — we cannot
        write a user-scoped notification, but the mutation must still
        commit and the pubsub error must not escape."""
        order = await _order(db_session, sample_customer.id, alloy=None)

        with patch(
            "goldsmith_erp.services.order_service.publish_event",
            new=AsyncMock(side_effect=ConnectionError("down")),
        ):
            updated = await OrderService.update_order(
                db_session,
                order.id,
                OrderUpdate(status=OrderStatusEnum.COMPLETED),
                verified_by_user_id=None,
                origin="manual",
            )
        assert updated is not None


# --------------------------------------------------------------------------- #
# OrderService.advance_status — pubsub failure
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
class TestAdvanceStatusPubsubFailure:
    async def test_advance_status_commits_despite_pubsub_error(
        self, db_session, sample_customer
    ):
        """advance_status delegates to update_order — verify the A5.5
        contract survives the wrapper call."""
        user = await _user(db_session)
        order = await _order(db_session, sample_customer.id, alloy=None)

        with patch(
            "goldsmith_erp.services.order_service.publish_event",
            new=AsyncMock(side_effect=ConnectionError("nope")),
        ):
            updated = await OrderService.advance_status(
                db_session,
                order.id,
                OrderStatusEnum.COMPLETED,
                user_id=user.id,
            )

        assert updated is not None
        assert updated.status == OrderStatusEnum.COMPLETED

        notifications = await _user_notifications(db_session, user.id)
        assert any(
            n.notification_type == NotificationTypeEnum.SYSTEM
            for n in notifications
        )


# --------------------------------------------------------------------------- #
# Contract: A5.5 pubsub failure never re-raises to the caller
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
class TestPubsubFailureNeverReraises:
    """Cross-service invariant: no pubsub error ever propagates to the
    caller. The caller should see the successful response and find a
    notification in the user's inbox on next poll.

    Any future service that publishes events MUST honour this
    contract — the mutation is the user's intent; a pubsub outage is
    infrastructure noise, not a domain error."""

    async def test_generic_exception_swallowed_on_patch_activity(
        self, db_session, sample_customer
    ):
        """Test with a non-ConnectionError exception to prove the
        ``except Exception`` branch is broad enough."""
        user = await _user(db_session)
        act_1 = await _activity(db_session, "Feilen")
        act_2 = await _activity(db_session, "Loeten")
        order = await _order(db_session, sample_customer.id)
        entry = await _running_entry(db_session, user, order, act_1)

        with patch(
            "goldsmith_erp.core.pubsub.publish_event",
            new=AsyncMock(side_effect=RuntimeError("unexpected shape")),
        ):
            # Must not raise.
            updated = await TimeTrackingService.patch_activity(
                db=db_session,
                entry_id=entry.id,
                activity_id=act_2.id,
                user=user,
                origin="scan",
            )
        assert updated.activity_id == act_2.id
