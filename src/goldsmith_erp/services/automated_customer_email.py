# src/goldsmith_erp/services/automated_customer_email.py
"""
Automated customer emails for order events: once per event, never per staff user.

BE-09 / DOM-10: the reminder scans used to email the customer from
``NotificationService.create_notification``, which runs once per staff
recipient, and the dedup keyed on ``Notification.is_read`` re-armed it every
time a staff member read the bell entry. The customer got N mails per tick
(N = staff users) and more mails every day.

Customer mail is now a separate step, called once per order per scan, and it
goes through the regular Kundeninfo path (``CustomerUpdateService.create_draft``
+ ``send``). As a result:

- every automated mail is a ``CustomerUpdate`` row that staff can see in
  Kundeninfo;
- ``status=SENT`` / ``delivery_method=EMAIL`` are set only when SMTP accepted
  the message; a failure is recorded as ``SEND_FAILED`` and the acting user
  gets an in-app notice (existing send-path behaviour);
- the ``CustomerUpdate`` rows are also the dedupe store (no new table or
  column).

Dedupe key: (order_id, kind[, fixed subject]).
- A SENT row for the key means the customer was already informed (by this job
  or by staff by hand), so the job never sends again.
- A SEND_FAILED row created today means the job already tried today, so the
  retry waits for the next day.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, cast

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.core.config import settings
from goldsmith_erp.db.models import (
    Customer,
    CustomerUpdate,
    CustomerUpdateKind,
    CustomerUpdateStatus,
    NotificationTypeEnum,
    Order,
    User,
    UserRole,
)
from goldsmith_erp.models.customer_update import CustomerUpdateCreate

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class _EventMail:
    """How one automated event maps onto a CustomerUpdate."""

    kind: CustomerUpdateKind
    # None means "use CustomerUpdateService's German template for ``kind``"
    # and dedupe on (order, kind) alone.
    subject_template: Optional[str] = None
    body: Optional[str] = None

    def subject_for(self, order_id: int) -> Optional[str]:
        if self.subject_template is None:
            return None
        return self.subject_template.format(order_id=order_id)


_FITTING_BODY = (
    "Ihr Schmuckstueck ist bereit fuer die Anprobe. Bitte melden Sie sich "
    "bei uns, damit wir einen Termin vereinbaren koennen."
)

_EVENT_MAILS: dict[NotificationTypeEnum, _EventMail] = {
    NotificationTypeEnum.PICKUP_READY: _EventMail(
        kind=CustomerUpdateKind.READY_FOR_PICKUP
    ),
    NotificationTypeEnum.FITTING_REMINDER: _EventMail(
        kind=CustomerUpdateKind.CUSTOM,
        subject_template="Anprobe fuer Ihren Auftrag #{order_id}",
        body=_FITTING_BODY,
    ),
}


def _email_delivery_enabled() -> bool:
    """Same gate as CustomerUpdateService.send's ``will_attempt``."""
    return bool(settings.EMAIL_NOTIFICATIONS_ENABLED and settings.SMTP_HOST)


async def _customer_has_email(db: AsyncSession, customer_id: Optional[int]) -> bool:
    if customer_id is None:
        return False
    customer = (
        await db.execute(select(Customer).where(Customer.id == customer_id))
    ).scalar_one_or_none()
    return bool(customer is not None and customer.email)


async def _already_handled(
    db: AsyncSession, order_id: int, mail: _EventMail, day_start: datetime
) -> bool:
    """True if the customer was already informed, or we already tried today."""
    conditions = [
        CustomerUpdate.order_id == order_id,
        CustomerUpdate.kind == mail.kind,
    ]
    subject = mail.subject_for(order_id)
    if subject is not None:
        conditions.append(CustomerUpdate.subject == subject)

    rows = (
        await db.execute(
            select(CustomerUpdate.status, CustomerUpdate.created_at).where(
                and_(*conditions)
            )
        )
    ).all()
    for status, created_at in rows:
        if status == CustomerUpdateStatus.SENT:
            return True
        if status == CustomerUpdateStatus.SEND_FAILED and created_at >= day_start:
            return True
    return False


async def _system_actor_id(db: AsyncSession) -> Optional[int]:
    """User recorded as ``sent_by`` for automated mails.

    The oldest active ADMIN (fallback: GOLDSMITH), who also receives the
    send-failure notice. ``CustomerUpdate.sent_by`` is NOT NULL, and there is
    no system user.
    """
    for role in (UserRole.ADMIN, UserRole.GOLDSMITH):
        user_id = (
            await db.execute(
                select(User.id)
                .where(and_(User.is_active.is_(True), User.role == role))
                .order_by(User.id)
                .limit(1)
            )
        ).scalar_one_or_none()
        if user_id is not None:
            return int(user_id)
    return None


async def send_customer_mail_once(
    db: AsyncSession, order: Order, event: NotificationTypeEnum
) -> bool:
    """Send the customer mail for ``event`` on ``order`` at most once.

    Returns True only if an email was accepted by SMTP in this call. Never
    raises: a failure is logged with IDs only (no PII) and recorded on the
    CustomerUpdate row by the send path.
    """
    mail = _EVENT_MAILS.get(event)
    order_id = int(order.id)
    if mail is None or not _email_delivery_enabled():
        return False
    if not await _customer_has_email(db, cast(Optional[int], order.customer_id)):
        return False

    day_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    if await _already_handled(db, order_id, mail, day_start):
        return False

    actor_id = await _system_actor_id(db)
    if actor_id is None:
        logger.warning(
            "No active ADMIN/GOLDSMITH user to attribute automated customer mail",
            extra={"order_id": order_id, "event": event.value},
        )
        return False

    return await _create_and_send(db, order_id, event, mail, actor_id)


async def _create_and_send(
    db: AsyncSession,
    order_id: int,
    event: NotificationTypeEnum,
    mail: _EventMail,
    actor_id: int,
) -> bool:
    # Late import: customer_update_service lazily imports NotificationService,
    # and notification_service lazily imports this module.
    from goldsmith_erp.services.customer_update_service import (  # noqa: PLC0415
        CustomerUpdateService,
    )

    try:
        draft = await CustomerUpdateService.create_draft(
            db,
            order_id=order_id,
            repair_job_id=None,
            data=CustomerUpdateCreate(
                kind=mail.kind,
                subject=mail.subject_for(order_id),
                body=mail.body,
                photo_ids=None,  # design-IP rule: automated mails attach nothing
            ),
            user_id=actor_id,
        )
        result = await CustomerUpdateService.send(db, int(draft.id), actor_id)
    except Exception as exc:
        logger.error(
            "Automated customer mail failed",
            extra={
                "order_id": order_id,
                "event": event.value,
                "error_type": type(exc).__name__,
            },
            exc_info=True,
        )
        return False

    logger.info(
        "Automated customer mail processed",
        extra={
            "order_id": order_id,
            "event": event.value,
            "update_id": result.update.id,
            "delivered": result.delivered,
        },
    )
    return bool(result.delivered)
