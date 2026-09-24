# tests/integration/test_customer_email_once.py
"""
BE-09 / DOM-10 regression: automated customer emails go out exactly once
per event, regardless of how many staff users exist, and are never re-sent
by a later monitor tick.

The scans under test are the functions ``system_monitor._run_one_cycle``
calls (``NotificationService.check_pickup_reminders`` /
``check_fitting_reminders``). SMTP is mocked at the same boundary as the
other Kundeninfo tests (``email_service_module.aiosmtplib.send``).
"""

from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.core.config import settings
from goldsmith_erp.core.security import get_password_hash
from goldsmith_erp.db.models import (
    Customer,
    CustomerUpdate,
    CustomerUpdateKind,
    CustomerUpdateStatus,
    Notification,
    NotificationTypeEnum,
    Order,
    OrderStatusEnum,
    UpdateDeliveryMethod,
    User,
    UserRole,
)
from goldsmith_erp.services import email_service as email_service_module
from goldsmith_erp.services.notification_service import NotificationService

pytestmark = pytest.mark.asyncio

STAFF_COUNT = 3


class _CapturingSend:
    def __init__(self, should_raise: bool = False) -> None:
        self.should_raise = should_raise
        self.calls = 0
        self.sent_messages: list = []

    async def __call__(self, msg, **kwargs):
        self.calls += 1
        if self.should_raise:
            raise ConnectionRefusedError("SMTP unreachable (test double)")
        self.sent_messages.append(msg)
        return None


def _enable_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "EMAIL_NOTIFICATIONS_ENABLED", True)
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test.local")
    monkeypatch.setattr(settings, "SMTP_FROM", "werkstatt@test.local")
    monkeypatch.setattr(settings, "SMTP_USER", None)
    monkeypatch.setattr(settings, "SMTP_PASSWORD", None)


def _install_smtp_double(
    monkeypatch: pytest.MonkeyPatch, should_raise: bool = False
) -> _CapturingSend:
    capture = _CapturingSend(should_raise=should_raise)
    monkeypatch.setattr(email_service_module.aiosmtplib, "send", capture)
    return capture


@pytest_asyncio.fixture
async def staff_users(db_session: AsyncSession) -> list[User]:
    """One ADMIN + two GOLDSMITH users — three staff recipients."""
    roles = [UserRole.ADMIN, UserRole.GOLDSMITH, UserRole.GOLDSMITH]
    users = []
    for i, role in enumerate(roles):
        user = User(
            email=f"staff{i}_{datetime.utcnow().timestamp()}@once.example.com",
            hashed_password=get_password_hash("StaffPass123!"),
            first_name="Staff",
            last_name=str(i),
            role=role,
            is_active=True,
        )
        db_session.add(user)
        users.append(user)
    await db_session.commit()
    for user in users:
        await db_session.refresh(user)
    assert len(users) == STAFF_COUNT
    return users


async def _make_order(
    db_session: AsyncSession, customer: Customer, status: OrderStatusEnum
) -> Order:
    order = Order(
        title="Verlobungsring Test",
        customer_id=customer.id,
        status=status,
        deadline=datetime.utcnow() + timedelta(days=10),
    )
    if status == OrderStatusEnum.COMPLETED:
        order.completed_at = datetime.utcnow() - timedelta(days=4)
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)
    return order


async def _customer_updates(db_session: AsyncSession, order_id: int) -> list:
    result = await db_session.execute(
        select(CustomerUpdate).where(CustomerUpdate.order_id == order_id)
    )
    return list(result.scalars().all())


async def _count_notifications(
    db_session: AsyncSession, order_id: int, ntype: NotificationTypeEnum
) -> int:
    result = await db_session.execute(
        select(func.count(Notification.id)).where(
            Notification.related_order_id == order_id,
            Notification.notification_type == ntype,
        )
    )
    return int(result.scalar_one())


class TestPickupReminderCustomerEmail:
    async def test_three_staff_users_produce_exactly_one_customer_email(
        self, db_session, staff_users, test_customer, monkeypatch
    ):
        # Arrange
        _enable_smtp(monkeypatch)
        capture = _install_smtp_double(monkeypatch)
        order = await _make_order(db_session, test_customer, OrderStatusEnum.COMPLETED)

        # Act
        await NotificationService.check_pickup_reminders(db_session)

        # Assert — one mail to the customer, one CustomerUpdate SENT row,
        # one in-app row per staff user.
        assert capture.calls == 1
        updates = await _customer_updates(db_session, order.id)
        assert len(updates) == 1
        assert updates[0].kind == CustomerUpdateKind.READY_FOR_PICKUP
        assert updates[0].status == CustomerUpdateStatus.SENT
        assert updates[0].delivery_method == UpdateDeliveryMethod.EMAIL
        assert updates[0].sent_at is not None
        assert (
            await _count_notifications(
                db_session, order.id, NotificationTypeEnum.PICKUP_READY
            )
            == STAFF_COUNT
        )

    async def test_second_and_third_monitor_tick_send_nothing(
        self, db_session, staff_users, test_customer, monkeypatch
    ):
        _enable_smtp(monkeypatch)
        capture = _install_smtp_double(monkeypatch)
        order = await _make_order(db_session, test_customer, OrderStatusEnum.COMPLETED)

        await NotificationService.check_pickup_reminders(db_session)
        await NotificationService.check_pickup_reminders(db_session)
        # Staff marking their bell entries read must not re-arm the email
        # (the old dedup keyed on is_read=False).
        for user in staff_users:
            await NotificationService.mark_all_read(db_session, user.id)
        await NotificationService.check_pickup_reminders(db_session)

        assert capture.calls == 1
        assert len(await _customer_updates(db_session, order.id)) == 1
        assert (
            await _count_notifications(
                db_session, order.id, NotificationTypeEnum.PICKUP_READY
            )
            == STAFF_COUNT
        )

    async def test_failed_send_is_recorded_not_marked_notified_and_not_retried_same_day(
        self, db_session, staff_users, test_customer, monkeypatch
    ):
        _enable_smtp(monkeypatch)
        capture = _install_smtp_double(monkeypatch, should_raise=True)
        order = await _make_order(db_session, test_customer, OrderStatusEnum.COMPLETED)

        await NotificationService.check_pickup_reminders(db_session)
        await NotificationService.check_pickup_reminders(db_session)

        assert capture.calls == 1
        updates = await _customer_updates(db_session, order.id)
        assert len(updates) == 1
        assert updates[0].status == CustomerUpdateStatus.SEND_FAILED
        assert updates[0].delivery_method is None

    async def test_smtp_disabled_sends_nothing_and_creates_no_customer_update(
        self, db_session, staff_users, test_customer, monkeypatch
    ):
        monkeypatch.setattr(settings, "EMAIL_NOTIFICATIONS_ENABLED", False)
        capture = _install_smtp_double(monkeypatch)
        order = await _make_order(db_session, test_customer, OrderStatusEnum.COMPLETED)

        await NotificationService.check_pickup_reminders(db_session)

        assert capture.calls == 0
        assert await _customer_updates(db_session, order.id) == []
        assert (
            await _count_notifications(
                db_session, order.id, NotificationTypeEnum.PICKUP_READY
            )
            == STAFF_COUNT
        )


class TestFittingReminderCustomerEmail:
    async def test_fitting_reminder_emails_customer_once_across_ticks(
        self, db_session, staff_users, test_customer, monkeypatch
    ):
        _enable_smtp(monkeypatch)
        capture = _install_smtp_double(monkeypatch)
        order = await _make_order(
            db_session, test_customer, OrderStatusEnum.WAITING_FOR_FITTING
        )

        await NotificationService.check_fitting_reminders(db_session)
        await NotificationService.check_fitting_reminders(db_session)

        assert capture.calls == 1
        updates = await _customer_updates(db_session, order.id)
        assert len(updates) == 1
        assert updates[0].status == CustomerUpdateStatus.SENT
        # The internal staff message must never leak into the customer mail
        # (BE-09: it used to be passed as ``fitting_date``).
        assert "Termin mit Kunden vereinbaren" not in updates[0].subject
        assert "Termin mit Kunden vereinbaren" not in updates[0].body
        assert (
            await _count_notifications(
                db_session, order.id, NotificationTypeEnum.FITTING_REMINDER
            )
            == STAFF_COUNT
        )
