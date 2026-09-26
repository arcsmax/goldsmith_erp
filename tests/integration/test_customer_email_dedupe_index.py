"""C2.2 (adversarial round on BE-09): DB backstop for the automated-mail dedupe.

``send_customer_mail_once`` checks for an existing SENT (or today's
SEND_FAILED) CustomerUpdate and then creates + sends a new one. Two
concurrent monitor ticks can both pass that check and both email the
customer. The backstop: automated rows carry ``customer_updates.dedupe_key``
and a partial unique index ``uq_customer_updates_dedupe_key``
(``dedupe_key IS NOT NULL AND status <> 'send_failed'``) rejects the second
row before any mail goes out; the sender treats that IntegrityError as
"already sent". Failed attempts stay excluded so tomorrow's retry works, and
staff-written Kundeninfo (no key) is not restricted.
"""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError

from goldsmith_erp.core.config import settings
from goldsmith_erp.core.security import get_password_hash
from goldsmith_erp.db.models import (
    CustomerUpdate,
    CustomerUpdateKind,
    CustomerUpdateStatus,
    NotificationTypeEnum,
    Order,
    OrderStatusEnum,
    User,
    UserRole,
)
from goldsmith_erp.services import automated_customer_email
from goldsmith_erp.services import email_service as email_service_module
from goldsmith_erp.services.automated_customer_email import send_customer_mail_once

pytestmark = pytest.mark.asyncio

_INDEX = "uq_customer_updates_dedupe_key"


class _Smtp:
    def __init__(self, should_raise: bool = False) -> None:
        self.should_raise = should_raise
        self.calls = 0

    async def __call__(self, msg, **kwargs):
        self.calls += 1
        if self.should_raise:
            raise ConnectionRefusedError("SMTP unreachable (test double)")


@pytest.fixture
def smtp(monkeypatch) -> _Smtp:
    monkeypatch.setattr(settings, "EMAIL_NOTIFICATIONS_ENABLED", True)
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test.local")
    monkeypatch.setattr(settings, "SMTP_FROM", "werkstatt@test.local")
    monkeypatch.setattr(settings, "SMTP_USER", None)
    monkeypatch.setattr(settings, "SMTP_PASSWORD", None)
    double = _Smtp()
    monkeypatch.setattr(email_service_module.aiosmtplib, "send", double)
    return double


@pytest.fixture
async def admin(db_session) -> User:
    user = User(
        email=f"c22_{datetime.utcnow().timestamp()}@example.com",
        hashed_password=get_password_hash("AdminPass123!"),
        first_name="Admin",
        last_name="C22",
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def completed_order(db_session, test_customer) -> Order:
    order = Order(
        title="Ring C2.2",
        customer_id=test_customer.id,
        status=OrderStatusEnum.COMPLETED,
        completed_at=datetime.utcnow() - timedelta(days=4),
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)
    return order


def _concurrent_tick(monkeypatch) -> None:
    """The second tick's pre-check ran before the first tick's commit."""

    async def _missed(*args, **kwargs):
        return False

    monkeypatch.setattr(automated_customer_email, "_already_handled", _missed)


async def _rows(db_session, order_id: int) -> list[CustomerUpdate]:
    result = await db_session.execute(
        select(CustomerUpdate).where(CustomerUpdate.order_id == order_id)
    )
    return list(result.scalars().all())


def _row(order_id: int, user_id: int, key, status) -> CustomerUpdate:
    return CustomerUpdate(
        order_id=order_id,
        kind=CustomerUpdateKind.READY_FOR_PICKUP,
        subject="Abholbereit",
        body="Ihr Schmuck ist fertig.",
        status=status,
        sent_by=user_id,
        dedupe_key=key,
    )


async def test_partial_unique_index_exists(db_session) -> None:
    conn = await db_session.connection()
    names = await conn.run_sync(
        lambda c: {i["name"] for i in inspect(c).get_indexes("customer_updates")}
    )
    assert _INDEX in names


async def test_concurrent_tick_does_not_send_twice(
    db_session, smtp, admin, completed_order, monkeypatch
) -> None:
    order_id = completed_order.id
    assert await send_customer_mail_once(
        db_session, completed_order, NotificationTypeEnum.PICKUP_READY
    )
    _concurrent_tick(monkeypatch)

    second = await send_customer_mail_once(
        db_session, completed_order, NotificationTypeEnum.PICKUP_READY
    )

    assert second is False
    assert smtp.calls == 1
    rows = await _rows(db_session, order_id)
    assert len(rows) == 1
    assert rows[0].dedupe_key is not None
    assert rows[0].status == CustomerUpdateStatus.SENT


async def test_retry_after_failed_send_is_still_possible(
    db_session, smtp, admin, completed_order, monkeypatch
) -> None:
    order_id = completed_order.id
    smtp.should_raise = True
    assert not await send_customer_mail_once(
        db_session, completed_order, NotificationTypeEnum.PICKUP_READY
    )
    smtp.should_raise = False
    _concurrent_tick(monkeypatch)  # stands in for "next day"

    assert await send_customer_mail_once(
        db_session, completed_order, NotificationTypeEnum.PICKUP_READY
    )

    statuses = sorted(r.status.value for r in await _rows(db_session, order_id))
    assert statuses == ["send_failed", "sent"]


async def test_index_rejects_duplicate_live_rows_only(
    db_session, admin, completed_order
) -> None:
    order_id, user_id = completed_order.id, admin.id
    key = f"auto:order:{order_id}:pickup_ready"
    db_session.add(_row(order_id, user_id, key, CustomerUpdateStatus.SEND_FAILED))
    db_session.add(_row(order_id, user_id, key, CustomerUpdateStatus.SENT))
    db_session.add(_row(order_id, user_id, None, CustomerUpdateStatus.SENT))
    db_session.add(_row(order_id, user_id, None, CustomerUpdateStatus.SENT))
    await db_session.commit()

    db_session.add(_row(order_id, user_id, key, CustomerUpdateStatus.DRAFT))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
