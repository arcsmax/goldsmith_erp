# tests/unit/test_notification_service.py
"""
Unit tests for NotificationService.

Covers:
- create_notification: persists a row and assigns an ID
- get_notifications: returns only the requesting user's notifications
- mark_as_read: cross-user isolation — cannot mark another user's notification
- mark_all_read: only marks the requesting user's notifications, leaves others untouched
- get_unread_count: returns the correct count, excluding already-read ones
- check_deadline_warnings: deduplication — same order on same day produces only one notification

All tests use the in-memory SQLite DB from conftest.py.
Redis publish_event is patched to a no-op by the autouse fixture in conftest.py.
"""
import pytest
from datetime import datetime, timedelta

from goldsmith_erp.db.models import (
    Notification,
    NotificationSeverityEnum,
    NotificationTypeEnum,
    Order,
    OrderStatusEnum,
    User,
    UserRole,
)
from goldsmith_erp.services.notification_service import NotificationService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _make_notification(
    db,
    user_id: int,
    notification_type: NotificationTypeEnum = NotificationTypeEnum.SYSTEM,
    severity: NotificationSeverityEnum = NotificationSeverityEnum.INFO,
    related_order_id: int | None = None,
) -> Notification:
    """Thin wrapper to reduce boilerplate in tests."""
    return await NotificationService.create_notification(
        db=db,
        user_id=user_id,
        title="Test notification",
        message="Test message body",
        notification_type=notification_type,
        severity=severity,
        related_order_id=related_order_id,
    )


# ---------------------------------------------------------------------------
# create_notification
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestCreateNotification:

    async def test_persists_row_with_id(self, db_session, sample_user):
        """create_notification should return a Notification with a DB-assigned id."""
        notification = await _make_notification(db_session, sample_user.id)

        assert notification.id is not None
        assert notification.id > 0

    async def test_correct_user_id(self, db_session, sample_user):
        notification = await _make_notification(db_session, sample_user.id)
        assert notification.user_id == sample_user.id

    async def test_correct_type_and_severity(self, db_session, sample_user):
        notification = await NotificationService.create_notification(
            db=db_session,
            user_id=sample_user.id,
            title="Urgent issue",
            message="Something needs attention",
            notification_type=NotificationTypeEnum.ORDER_STATUS,
            severity=NotificationSeverityEnum.URGENT,
        )

        assert notification.notification_type == NotificationTypeEnum.ORDER_STATUS
        assert notification.severity == NotificationSeverityEnum.URGENT

    async def test_defaults_to_unread(self, db_session, sample_user):
        """Newly created notifications must start as unread."""
        notification = await _make_notification(db_session, sample_user.id)
        assert notification.is_read is False
        assert notification.read_at is None

    async def test_related_order_id_stored(self, db_session, sample_user, sample_order):
        notification = await _make_notification(
            db_session,
            sample_user.id,
            related_order_id=sample_order.id,
        )
        assert notification.related_order_id == sample_order.id


# ---------------------------------------------------------------------------
# get_notifications
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestGetNotifications:

    async def test_returns_own_notifications(self, db_session, sample_user):
        await _make_notification(db_session, sample_user.id)
        await _make_notification(db_session, sample_user.id)

        results = await NotificationService.get_notifications(db_session, sample_user.id)
        assert len(results) == 2

    async def test_does_not_return_other_users_notifications(
        self, db_session, sample_user, admin_user
    ):
        """Notifications belonging to admin_user must not appear in sample_user's list."""
        await _make_notification(db_session, admin_user.id)
        await _make_notification(db_session, sample_user.id)

        results = await NotificationService.get_notifications(db_session, sample_user.id)

        # Only the notification for sample_user should be returned
        assert len(results) == 1
        assert results[0].user_id == sample_user.id

    async def test_ordered_newest_first(self, db_session, sample_user):
        n1 = await _make_notification(db_session, sample_user.id)
        n2 = await _make_notification(db_session, sample_user.id)

        results = await NotificationService.get_notifications(db_session, sample_user.id)
        ids = [n.id for n in results]

        # Newer ID should come first
        assert ids.index(n2.id) < ids.index(n1.id)

    async def test_unread_only_filter(self, db_session, sample_user):
        n1 = await _make_notification(db_session, sample_user.id)
        await NotificationService.mark_as_read(db_session, n1.id, sample_user.id)
        await _make_notification(db_session, sample_user.id)  # unread

        all_results = await NotificationService.get_notifications(db_session, sample_user.id)
        unread_results = await NotificationService.get_notifications(
            db_session, sample_user.id, unread_only=True
        )

        assert len(all_results) == 2
        assert len(unread_results) == 1
        assert unread_results[0].is_read is False

    async def test_empty_list_for_user_with_no_notifications(self, db_session, sample_user):
        results = await NotificationService.get_notifications(db_session, sample_user.id)
        assert results == []


# ---------------------------------------------------------------------------
# mark_as_read (cross-user isolation)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestMarkAsRead:

    async def test_marks_own_notification_as_read(self, db_session, sample_user):
        notification = await _make_notification(db_session, sample_user.id)
        assert notification.is_read is False

        updated = await NotificationService.mark_as_read(
            db_session, notification.id, sample_user.id
        )

        assert updated is not None
        assert updated.is_read is True
        assert updated.read_at is not None

    async def test_cross_user_isolation_returns_none(self, db_session, sample_user, admin_user):
        """
        mark_as_read must return None when the notification belongs to a different user.
        This prevents cross-user data leakage or privilege escalation.
        """
        notification = await _make_notification(db_session, admin_user.id)

        # sample_user tries to mark admin_user's notification as read
        result = await NotificationService.mark_as_read(
            db_session, notification.id, sample_user.id
        )

        assert result is None

    async def test_cross_user_mark_does_not_mutate_db(self, db_session, sample_user, admin_user):
        """After a failed cross-user mark_as_read, the notification must still be unread."""
        notification = await _make_notification(db_session, admin_user.id)

        await NotificationService.mark_as_read(
            db_session, notification.id, sample_user.id
        )

        # Verify the notification is still unread in the DB
        admin_notifications = await NotificationService.get_notifications(
            db_session, admin_user.id
        )
        assert admin_notifications[0].is_read is False

    async def test_idempotent_on_already_read(self, db_session, sample_user):
        """Calling mark_as_read on an already-read notification must succeed without error."""
        notification = await _make_notification(db_session, sample_user.id)
        await NotificationService.mark_as_read(db_session, notification.id, sample_user.id)
        second_result = await NotificationService.mark_as_read(
            db_session, notification.id, sample_user.id
        )
        assert second_result is not None
        assert second_result.is_read is True

    async def test_nonexistent_notification_returns_none(self, db_session, sample_user):
        result = await NotificationService.mark_as_read(
            db_session, notification_id=999999, user_id=sample_user.id
        )
        assert result is None


# ---------------------------------------------------------------------------
# mark_all_read
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestMarkAllRead:

    async def test_marks_all_own_unread_notifications(self, db_session, sample_user):
        await _make_notification(db_session, sample_user.id)
        await _make_notification(db_session, sample_user.id)
        await _make_notification(db_session, sample_user.id)

        count = await NotificationService.mark_all_read(db_session, sample_user.id)
        assert count == 3

        unread = await NotificationService.get_notifications(
            db_session, sample_user.id, unread_only=True
        )
        assert unread == []

    async def test_does_not_touch_other_users_notifications(
        self, db_session, sample_user, admin_user
    ):
        """mark_all_read must not mark notifications belonging to admin_user."""
        await _make_notification(db_session, admin_user.id)
        await _make_notification(db_session, sample_user.id)

        await NotificationService.mark_all_read(db_session, sample_user.id)

        # admin_user's notification must still be unread
        admin_unread = await NotificationService.get_notifications(
            db_session, admin_user.id, unread_only=True
        )
        assert len(admin_unread) == 1

    async def test_returns_zero_when_nothing_to_mark(self, db_session, sample_user):
        count = await NotificationService.mark_all_read(db_session, sample_user.id)
        assert count == 0

    async def test_skips_already_read_notifications(self, db_session, sample_user):
        n = await _make_notification(db_session, sample_user.id)
        await NotificationService.mark_as_read(db_session, n.id, sample_user.id)

        # The already-read notification should not be counted again
        count = await NotificationService.mark_all_read(db_session, sample_user.id)
        assert count == 0


# ---------------------------------------------------------------------------
# get_unread_count
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestGetUnreadCount:

    async def test_returns_correct_count(self, db_session, sample_user):
        await _make_notification(db_session, sample_user.id)
        await _make_notification(db_session, sample_user.id)
        await _make_notification(db_session, sample_user.id)

        count = await NotificationService.get_unread_count(db_session, sample_user.id)
        assert count == 3

    async def test_excludes_read_notifications(self, db_session, sample_user):
        n1 = await _make_notification(db_session, sample_user.id)
        n2 = await _make_notification(db_session, sample_user.id)
        await _make_notification(db_session, sample_user.id)

        await NotificationService.mark_as_read(db_session, n1.id, sample_user.id)
        await NotificationService.mark_as_read(db_session, n2.id, sample_user.id)

        count = await NotificationService.get_unread_count(db_session, sample_user.id)
        assert count == 1

    async def test_excludes_other_users_notifications(
        self, db_session, sample_user, admin_user
    ):
        await _make_notification(db_session, admin_user.id)
        await _make_notification(db_session, admin_user.id)

        count = await NotificationService.get_unread_count(db_session, sample_user.id)
        assert count == 0

    async def test_zero_when_no_notifications(self, db_session, sample_user):
        count = await NotificationService.get_unread_count(db_session, sample_user.id)
        assert count == 0


# ---------------------------------------------------------------------------
# check_deadline_warnings — deduplication
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
class TestCheckDeadlineWarnings:

    async def _create_order_with_deadline(
        self, db, customer_id: int, days_ahead: int, status=OrderStatusEnum.IN_PROGRESS
    ) -> Order:
        """Create an open order whose deadline is `days_ahead` days from now."""
        order = Order(
            title=f"Deadline order +{days_ahead}d",
            description="Test order for deadline warning",
            customer_id=customer_id,
            status=status,
            deadline=datetime.utcnow() + timedelta(days=days_ahead),
        )
        db.add(order)
        await db.commit()
        await db.refresh(order)
        return order

    async def test_creates_notifications_for_approaching_deadlines(
        self, db_session, sample_user, admin_user, sample_customer
    ):
        """
        An order with a deadline within 4 days must trigger a notification
        for each ADMIN/GOLDSMITH user (sample_user is GOLDSMITH, admin_user is ADMIN).
        """
        await self._create_order_with_deadline(db_session, sample_customer.id, days_ahead=2)

        created_count = await NotificationService.check_deadline_warnings(db_session)

        # Two users (GOLDSMITH + ADMIN) → 2 notifications for 1 order
        assert created_count == 2

    async def test_deduplication_does_not_create_duplicate_on_second_run(
        self, db_session, sample_user, admin_user, sample_customer
    ):
        """
        Running check_deadline_warnings twice on the same day must not create
        duplicate DEADLINE_WARNING notifications for the same order.
        """
        await self._create_order_with_deadline(db_session, sample_customer.id, days_ahead=1)

        first_run = await NotificationService.check_deadline_warnings(db_session)
        second_run = await NotificationService.check_deadline_warnings(db_session)

        # Second run must produce zero new notifications (all unread ones already exist)
        assert first_run > 0
        assert second_run == 0

    async def test_deduplication_allows_new_notification_after_reading(
        self, db_session, sample_user, admin_user, sample_customer
    ):
        """
        Once the existing DEADLINE_WARNING for an order is marked as read,
        the next scan may create a new one (the old one is no longer unread).
        """
        await self._create_order_with_deadline(db_session, sample_customer.id, days_ahead=1)

        await NotificationService.check_deadline_warnings(db_session)

        # Mark all notifications as read to clear the deduplication guard
        await NotificationService.mark_all_read(db_session, sample_user.id)
        await NotificationService.mark_all_read(db_session, admin_user.id)

        second_run = await NotificationService.check_deadline_warnings(db_session)
        assert second_run > 0

    async def test_skips_completed_orders(
        self, db_session, sample_user, admin_user, sample_customer
    ):
        """COMPLETED orders must not generate deadline warnings."""
        await self._create_order_with_deadline(
            db_session,
            sample_customer.id,
            days_ahead=1,
            status=OrderStatusEnum.COMPLETED,
        )

        created_count = await NotificationService.check_deadline_warnings(db_session)
        assert created_count == 0

    async def test_skips_delivered_orders(
        self, db_session, sample_user, admin_user, sample_customer
    ):
        """DELIVERED orders must not generate deadline warnings."""
        await self._create_order_with_deadline(
            db_session,
            sample_customer.id,
            days_ahead=2,
            status=OrderStatusEnum.DELIVERED,
        )

        created_count = await NotificationService.check_deadline_warnings(db_session)
        assert created_count == 0

    async def test_skips_orders_beyond_four_days(
        self, db_session, sample_user, admin_user, sample_customer
    ):
        """Orders with deadlines more than 4 days away must not trigger notifications."""
        await self._create_order_with_deadline(db_session, sample_customer.id, days_ahead=10)

        created_count = await NotificationService.check_deadline_warnings(db_session)
        assert created_count == 0

    async def test_urgent_severity_for_one_day_deadline(
        self, db_session, sample_user, admin_user, sample_customer
    ):
        """An order due in 1 day must produce URGENT severity notifications."""
        await self._create_order_with_deadline(db_session, sample_customer.id, days_ahead=1)

        await NotificationService.check_deadline_warnings(db_session)

        user_notifications = await NotificationService.get_notifications(
            db_session, sample_user.id
        )
        assert any(
            n.severity == NotificationSeverityEnum.URGENT for n in user_notifications
        )

    async def test_notification_type_is_deadline_warning(
        self, db_session, sample_user, sample_customer
    ):
        """Notifications from check_deadline_warnings must have type DEADLINE_WARNING."""
        await self._create_order_with_deadline(db_session, sample_customer.id, days_ahead=2)

        await NotificationService.check_deadline_warnings(db_session)

        notifications = await NotificationService.get_notifications(
            db_session, sample_user.id
        )
        assert all(
            n.notification_type == NotificationTypeEnum.DEADLINE_WARNING
            for n in notifications
        )
