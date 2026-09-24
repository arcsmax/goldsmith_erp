"""
C1 — Adversarial tests for automated_customer_email.send_customer_mail_once
(audit 2026-09-25, BE-09/DOM-10: exactly one customer email per order event).

tests/integration/test_customer_email_once.py already covers the headline
claim (N staff users -> 1 customer email, no resend on a later tick for the
SAME occurrence). These tests probe the dedupe KEY itself: it is
(order_id, kind[, subject]) with no time bound and no occurrence counter, so
it blocks a SENT mail forever — including for a legitimately NEW occurrence
of the same event on the same order (a repair re-opened and completed a
second time). It also confirms the documented no-crash behaviour for a
customer without an email.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.core.security import get_password_hash
from goldsmith_erp.db.models import (
    Customer,
    CustomerUpdate,
    Order,
    OrderStatusEnum,
    User,
    UserRole,
)
from goldsmith_erp.core.config import settings
from goldsmith_erp.services import email_service as email_service_module
from goldsmith_erp.services.notification_service import NotificationService

pytestmark = pytest.mark.asyncio


class _CapturingSend:
    """Mirrors tests/integration/test_customer_email_once.py's SMTP double."""

    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, msg, **kwargs):
        self.calls += 1
        return None


@pytest_asyncio.fixture(autouse=True)
def _enable_email(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_NOTIFICATIONS_ENABLED", True)
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test.local")
    monkeypatch.setattr(settings, "SMTP_FROM", "werkstatt@test.local")
    monkeypatch.setattr(settings, "SMTP_USER", None)
    monkeypatch.setattr(settings, "SMTP_PASSWORD", None)
    monkeypatch.setattr(email_service_module.aiosmtplib, "send", _CapturingSend())


async def _make_admin(db_session: AsyncSession) -> User:
    user = User(
        email=f"email_once_admin_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash("pw"),
        first_name="Admin",
        last_name="EmailOnce",
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _make_customer(db_session: AsyncSession, with_email: bool = True) -> Customer:
    # Customer.email is NOT NULL at the DB level (nullable=False) — a
    # customer literally without an email is not a representable state.
    # An empty string is the closest real-world analogue (falsy, so
    # _customer_has_email's `bool(customer.email)` check still triggers)
    # and is not rejected by the column constraint.
    customer = Customer(
        first_name="Anna",
        last_name="Kundin",
        email=(
            f"email_once_cust_{uuid.uuid4().hex[:8]}@example.com"
            if with_email
            else ""
        ),
        customer_type="private",
        is_active=True,
    )
    db_session.add(customer)
    await db_session.commit()
    await db_session.refresh(customer)
    return customer


async def _make_order(db_session: AsyncSession, customer: Customer, status) -> Order:
    # check_pickup_reminders only fires for orders completed > 3 days ago
    # (or with a deadline inside the next 2 days) — see
    # NotificationService.check_pickup_reminders's overdue_threshold.
    order = Order(
        title="Email Dedup Test Auftrag",
        description="adversarial",
        customer_id=customer.id,
        status=status,
        completed_at=datetime.utcnow() - timedelta(days=4),
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)
    return order


async def _customer_update_count(db_session: AsyncSession, order_id: int) -> int:
    rows = (
        await db_session.execute(
            select(CustomerUpdate).where(CustomerUpdate.order_id == order_id)
        )
    ).scalars().all()
    return len(rows)


class TestNoCrashWithoutCustomerEmail:
    async def test_customer_id_none_skips_mail_without_crashing(
        self, db_session: AsyncSession
    ):
        """Customer.email is NOT NULL at the DB level (nullable=False,
        db/models.py) — a real customer row without an email is not a
        representable state (confirmed: even an empty string is coerced to
        NULL by the encryption layer and rejected by the same constraint).
        The reachable "no address to mail" case is an order whose
        customer_id is None/unset; exercise send_customer_mail_once's guard
        for that directly."""
        from goldsmith_erp.db.models import NotificationTypeEnum
        from goldsmith_erp.services.automated_customer_email import (
            send_customer_mail_once,
        )

        order = Order(
            title="No Customer Order",
            description="adversarial",
            customer_id=None,
            status=OrderStatusEnum.COMPLETED,
        )
        db_session.add(order)
        await db_session.commit()
        await db_session.refresh(order)

        sent = await send_customer_mail_once(
            db_session, order, NotificationTypeEnum.PICKUP_READY
        )

        assert sent is False
        assert await _customer_update_count(db_session, order.id) == 0


class TestReCompletionAfterReopen:
    async def test_second_completion_after_reopen_does_not_notify_customer_again(
        self, db_session: AsyncSession
    ):
        """A pickup-ready mail is sent once (SENT row created). The order is
        then reopened (e.g. the piece needed a warranty adjustment after the
        customer flagged an issue at pickup) and goes through IN_PROGRESS
        back to COMPLETED a second time — a genuinely new "ready for
        pickup" event. _already_handled's dedupe key is (order_id, kind)
        with a permanent SENT check and no per-occurrence marker, so the
        customer is never told about the SECOND completion. Documents a
        real gap: 'once per order event' has silently become 'once per
        order, ever', for any order whose lifecycle can revisit
        COMPLETED (OrderUpdate.status accepts any OrderStatusEnum value —
        there is no backend transition guard preventing this)."""
        await _make_admin(db_session)
        customer = await _make_customer(db_session, with_email=True)
        order = await _make_order(db_session, customer, OrderStatusEnum.COMPLETED)

        first_count = await NotificationService.check_pickup_reminders(db_session)
        assert await _customer_update_count(db_session, order.id) == 1

        # Simulate a warranty re-open then a second, genuine completion.
        order.status = OrderStatusEnum.IN_PROGRESS
        db_session.add(order)
        await db_session.commit()

        order.status = OrderStatusEnum.COMPLETED
        order.completed_at = datetime.utcnow() - timedelta(days=4)
        db_session.add(order)
        await db_session.commit()

        await NotificationService.check_pickup_reminders(db_session)

        update_count = await _customer_update_count(db_session, order.id)
        assert update_count == 2, (
            f"expected a second customer notification for the second "
            f"completion of order {order.id}, found {update_count} "
            "CustomerUpdate row(s) total — send_customer_mail_once's dedupe "
            "key (order_id, kind) has no per-occurrence bound "
            "(services/automated_customer_email.py _already_handled), so a "
            "re-opened-and-recompleted order is silently never notified "
            "again."
        )
