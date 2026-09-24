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

Dedupe key: (order_id, kind, subject).
- A SENT row for the key means the customer was already informed (by this job
  or by staff by hand), so the job never sends again.
- A SEND_FAILED row created today means the job already tried today, so the
  retry waits for the next day.

Adversarial fix (C1.2, 2026-09-25): the key used to be (order_id, kind[, a
FIXED subject]) with no bound on WHICH occurrence of the event it covers. An
order/repair whose lifecycle can revisit the triggering status more than once
(e.g. reopened for a warranty fix and completed a SECOND time) would never be
re-mailed — a SENT row from the FIRST completion blocked every later one
forever. ``_EventMail.occurrence_marker`` folds a per-occurrence value (e.g.
``Order.completed_at``, at full precision — see its docstring for why it is
NOT rounded) into the stored ``subject``, so a genuinely new occurrence gets
its own subject and is never shadowed by a stale SENT row from a previous one,
while the SAME occurrence (unchanged completed_at across retries/ticks) still
dedupes exactly as before. A DB-level unique backstop for concurrent double
sends of the SAME occurrence (C2.2) is tracked separately (schema change,
out of this module's scope).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, cast

from sqlalchemy import and_, select
from sqlalchemy.exc import IntegrityError
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
    subject_template: str
    body: str
    # Attribute name on ``Order`` holding this event's per-occurrence
    # timestamp (e.g. "completed_at") — C1.2, see module docstring. ``None``
    # means this event has no natural per-occurrence timestamp on ``Order``
    # today, so its dedupe stays order-scoped (unchanged pre-fix behaviour).
    occurrence_field: Optional[str] = None

    def occurrence_marker(self, order: Order) -> Optional[str]:
        """
        Per-occurrence value for THIS event on ``order``, or ``None`` if the
        event has no such marker.

        Full microsecond precision (``datetime.isoformat()``, not rounded to
        seconds/minutes) is deliberate: two genuinely different occurrences
        (e.g. an automated re-open-and-recomplete test, or a same-day
        reopen+refix in production) can be only milliseconds apart, and
        rounding would let them collide onto the identical marker —
        silently re-introducing the exact bug this fixes.
        """
        if self.occurrence_field is None:
            return None
        value = cast(Optional[datetime], getattr(order, self.occurrence_field, None))
        if value is None:
            return None
        return value.isoformat(sep=" ")

    def subject_for(self, order_id: int, occurrence: Optional[str]) -> str:
        subject = self.subject_template.format(order_id=order_id)
        if occurrence is not None:
            subject = f"{subject} (Bearbeitung vom {occurrence} UTC)"
        return subject


_PICKUP_READY_SUBJECT = (
    "Ihr Schmuckstueck ist fertig zur Abholung — Auftrag #{order_id}"
)
# Duplicated from CustomerUpdateService._default_subject_body's
# READY_FOR_PICKUP text rather than imported: this module needs a template it
# can pass an occurrence marker through (see subject_for), and
# _default_subject_body only fills in when subject/body are omitted entirely.
_PICKUP_READY_BODY = (
    "Ihr Schmuckstueck ist fertig und kann ab sofort in unserem "
    "Atelier abgeholt werden."
)

_FITTING_BODY = (
    "Ihr Schmuckstueck ist bereit fuer die Anprobe. Bitte melden Sie sich "
    "bei uns, damit wir einen Termin vereinbaren koennen."
)

_EVENT_MAILS: dict[NotificationTypeEnum, _EventMail] = {
    NotificationTypeEnum.PICKUP_READY: _EventMail(
        kind=CustomerUpdateKind.READY_FOR_PICKUP,
        subject_template=_PICKUP_READY_SUBJECT,
        body=_PICKUP_READY_BODY,
        occurrence_field="completed_at",
    ),
    NotificationTypeEnum.FITTING_REMINDER: _EventMail(
        kind=CustomerUpdateKind.CUSTOM,
        subject_template="Anprobe fuer Ihren Auftrag #{order_id}",
        body=_FITTING_BODY,
        # No timestamp column tracks "entered WAITING_FOR_FITTING at" on
        # Order today (adding one is a migration, out of this fix's scope)
        # — dedupe stays order-scoped, matching pre-fix behaviour.
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
    db: AsyncSession,
    order_id: int,
    mail: _EventMail,
    day_start: datetime,
    occurrence: Optional[str],
) -> bool:
    """True if the customer was already informed, or we already tried today.

    ``occurrence`` (C1.2) scopes the check to THIS occurrence of the event —
    see ``_EventMail.occurrence_marker``. Folded into the ``subject`` equality
    condition (the same column FITTING_REMINDER already used to key its
    dedupe on), not a separate condition, so a stale row from a PRIOR
    occurrence (different subject) is structurally invisible here rather than
    filtered out after the fact.
    """
    conditions = [
        CustomerUpdate.order_id == order_id,
        CustomerUpdate.kind == mail.kind,
        CustomerUpdate.subject == mail.subject_for(order_id, occurrence),
    ]

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


def _dedupe_key(order_id: int, event: NotificationTypeEnum) -> str:
    """Value for ``customer_updates.dedupe_key`` (C2.2 DB backstop)."""
    return f"auto:order:{order_id}:{event.value}"


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

    occurrence = mail.occurrence_marker(order)
    day_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    if await _already_handled(db, order_id, mail, day_start, occurrence):
        return False

    actor_id = await _system_actor_id(db)
    if actor_id is None:
        logger.warning(
            "No active ADMIN/GOLDSMITH user to attribute automated customer mail",
            extra={"order_id": order_id, "event": event.value},
        )
        return False

    return await _create_and_send(db, order_id, event, mail, actor_id, occurrence)


async def _create_and_send(
    db: AsyncSession,
    order_id: int,
    event: NotificationTypeEnum,
    mail: _EventMail,
    actor_id: int,
    occurrence: Optional[str],
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
                subject=mail.subject_for(order_id, occurrence),
                body=mail.body,
                photo_ids=None,  # design-IP rule: automated mails attach nothing
            ),
            user_id=actor_id,
            dedupe_key=_dedupe_key(order_id, event),
        )
    except IntegrityError:
        # C2.2: a concurrent tick created the live row for this key between
        # our _already_handled check and this insert, so that tick sends
        # (or already sent) the mail. Nothing was sent here.
        logger.info(
            "Automated customer mail already handled by a concurrent run",
            extra={"order_id": order_id, "event": event.value},
        )
        return False
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

    try:
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
