# src/goldsmith_erp/services/quote_delivery.py
"""
Quote delivery (Kostenvoranschlag versenden) — DOM-11, W2-05.

"Versenden" used to flip the status to SENT and nothing else. It now:

- emails the quote PDF via ``EmailService.send_quote`` when SMTP is
  configured and the customer has an email address;
- otherwise records the quote as handed over manually (``PDF_MANUAL``); the
  frontend then downloads the PDF for staff;
- on an SMTP failure keeps the quote a DRAFT, records ``SEND_FAILED`` and
  raises 502 so the UI shows the error (never silent).

Recording reuses the Kundeninfo outbox (``CustomerUpdate``), like
``automated_customer_email`` does: each delivery attempt is one row with
``delivery_method`` / ``status`` / ``sent_at``. ``Quote`` has no
``sent_at`` column and ``db/models.py`` is out of scope for this fix, so
the row is found again by its fixed subject ``Kostenvoranschlag <number>``
(quote numbers are unique). When the quote is linked to an order the row
carries that ``order_id`` and shows up in the order's Kundeninfo.

Log lines carry IDs only (CLAUDE.md PII rule): no recipient, no subject.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional, cast

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from goldsmith_erp.core.config import settings
from goldsmith_erp.db.models import Customer as CustomerModel
from goldsmith_erp.db.models import (
    CustomerUpdate,
    CustomerUpdateKind,
    CustomerUpdateStatus,
)
from goldsmith_erp.db.models import Quote as QuoteModel
from goldsmith_erp.db.models import QuoteStatus, UpdateDeliveryMethod
from goldsmith_erp.db.transaction import transactional
from goldsmith_erp.services.email_service import EmailService
from goldsmith_erp.services.outbox_service import KIND_QUOTE_EMAIL, OutboxService
from goldsmith_erp.services.pdf_service import PDFService

logger = logging.getLogger(__name__)

SMTP_FAILED_DETAIL = (
    "E-Mail-Versand fehlgeschlagen. Der Kostenvoranschlag bleibt ein Entwurf. "
    "Bitte die E-Mail-Einstellungen prüfen oder das PDF herunterladen und "
    "selbst übergeben."
)

_RECORD_BODY = (
    "Kostenvoranschlag an die Kundin / den Kunden übergeben. "
    "Das PDF ist im Kostenvoranschlag jederzeit abrufbar."
)


class QuoteCustomerAdapter:
    """Uniform ``.name/.address/.city/.email/.phone`` view for the PDF renderer."""

    def __init__(self, c: CustomerModel) -> None:
        self.name = f"{c.first_name} {c.last_name}".strip()
        self.address = str(c.street) if c.street else ""
        city_parts = [str(p) for p in (c.postal_code, c.city) if p]
        self.city = " ".join(city_parts)
        self.email = str(c.email) if c.email else ""
        self.phone = str(c.phone) if c.phone else ""


@dataclass(frozen=True)
class QuoteDelivery:
    """How and when a quote reached the customer (from its SENT record)."""

    delivery_method: UpdateDeliveryMethod
    sent_at: datetime


def record_subject(quote_number: str) -> str:
    return f"Kostenvoranschlag {quote_number}"


def email_delivery_enabled() -> bool:
    """Same gate as ``CustomerUpdateService.send`` / automated mails."""
    return bool(settings.EMAIL_NOTIFICATIONS_ENABLED and settings.SMTP_HOST)


def customer_email(customer: Optional[CustomerModel]) -> Optional[str]:
    if customer is None or not customer.email:
        return None
    return str(customer.email)


def _fmt_eur(value: Any) -> str:
    """German currency string, e.g. ``1.234,56 €`` (template shows it as is)."""
    amount = float(value or 0.0)
    formatted = f"{amount:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{formatted} €"


async def load_customer(db: AsyncSession, customer_id: int) -> CustomerModel:
    customer = (
        await db.execute(select(CustomerModel).where(CustomerModel.id == customer_id))
    ).scalar_one_or_none()
    if customer is None:
        raise HTTPException(
            status_code=404, detail=f"Kunde {customer_id} nicht gefunden"
        )
    return customer


def render_quote_pdf_bytes(quote: QuoteModel, customer: CustomerModel) -> bytes:
    """Render the Kostenvoranschlag PDF (shared by download and email)."""
    return PDFService.render_quote_pdf(
        quote=quote,
        customer=QuoteCustomerAdapter(customer),
        line_items=list(quote.line_items),
        workshop_name=settings.WORKSHOP_NAME,
    )


async def email_quote(
    quote: QuoteModel, customer: CustomerModel, recipient: str
) -> bool:
    """Send the quote PDF by email. Returns True only if SMTP accepted it."""
    try:
        pdf_bytes = render_quote_pdf_bytes(quote, customer)
    except Exception:
        logger.exception(
            "Quote PDF rendering failed before email send",
            extra={"quote_id": quote.id},
        )
        return False
    valid_until = cast(Optional[datetime], quote.valid_until)
    return await EmailService.send_quote(
        to=recipient,
        quote_number=str(quote.quote_number),
        total=_fmt_eur(quote.total),
        valid_until=valid_until.strftime("%d.%m.%Y") if valid_until else "",
        pdf_bytes=pdf_bytes,
    )


def build_record(
    quote: QuoteModel,
    user_id: int,
    status: CustomerUpdateStatus,
    method: Optional[UpdateDeliveryMethod],
    sent_at: Optional[datetime],
) -> CustomerUpdate:
    """One Kundeninfo outbox row for a delivery attempt."""
    return CustomerUpdate(
        order_id=quote.order_id,
        repair_job_id=None,
        kind=CustomerUpdateKind.CUSTOM,
        subject=record_subject(str(quote.quote_number)),
        body=_RECORD_BODY,
        photo_ids=None,
        status=status,
        sent_at=sent_at,
        sent_by=user_id,
        delivery_method=method,
    )


async def get_delivery(db: AsyncSession, quote: QuoteModel) -> Optional[QuoteDelivery]:
    """Latest successful delivery of ``quote``, or None if never sent."""
    row = (
        await db.execute(
            select(CustomerUpdate.delivery_method, CustomerUpdate.sent_at)
            .where(CustomerUpdate.subject == record_subject(str(quote.quote_number)))
            .where(CustomerUpdate.status == CustomerUpdateStatus.SENT)
            .order_by(CustomerUpdate.sent_at.desc())
            .limit(1)
        )
    ).first()
    if row is None or row.delivery_method is None or row.sent_at is None:
        return None
    return QuoteDelivery(delivery_method=row.delivery_method, sent_at=row.sent_at)


# ----------------------------------------------------------------------
# Outbox (OUTBOX_MODE=worker, ADR-2026-09-25-outbox)
# ----------------------------------------------------------------------


async def enqueue_quote_email(
    db: AsyncSession, quote: QuoteModel, user_id: int
) -> CustomerUpdate:
    """Stage the delivery record + outbox job in the caller's transaction.

    The record is SENT with ``delivery_method=NULL`` ("queued") until the
    worker's SMTP send succeeds, so ``get_delivery`` reports nothing yet.
    """
    record = build_record(quote, user_id, CustomerUpdateStatus.SENT, None, None)
    db.add(record)
    await db.flush()
    await OutboxService.enqueue(
        db,
        kind=KIND_QUOTE_EMAIL,
        payload={"quote_id": quote.id, "record_id": record.id, "user_id": user_id},
        dedupe_key=f"quote_email:{quote.id}:{record.id}",
    )
    return record


async def _load_queued(
    db: AsyncSession, payload: dict[str, Any]
) -> tuple[Optional[QuoteModel], Optional[CustomerUpdate]]:
    quote = (
        await db.execute(
            select(QuoteModel)
            .options(selectinload(QuoteModel.line_items))
            .where(QuoteModel.id == int(payload["quote_id"]))
        )
    ).scalar_one_or_none()
    record = (
        await db.execute(
            select(CustomerUpdate).where(CustomerUpdate.id == int(payload["record_id"]))
        )
    ).scalar_one_or_none()
    return quote, record


async def deliver_queued_quote(db: AsyncSession, payload: dict[str, Any]) -> bool:
    """Outbox handler: email the quote PDF. True = done, False = retry."""
    quote, record = await _load_queued(db, payload)
    if quote is None or record is None:
        logger.info("Queued quote email target gone; skipping", extra=payload)
        return True
    if record.delivery_method == UpdateDeliveryMethod.EMAIL:
        return True
    customer = await load_customer(db, int(quote.customer_id))
    recipient = customer_email(customer)
    if recipient is None:
        async with transactional(db):
            record.delivery_method = cast(Any, UpdateDeliveryMethod.PDF_MANUAL)
            record.sent_at = cast(Any, datetime.utcnow())
        logger.info(
            "Queued quote email: no address, recorded PDF_MANUAL", extra=payload
        )
        return True
    if not await email_quote(quote, customer, recipient):
        return False
    async with transactional(db):
        record.delivery_method = cast(Any, UpdateDeliveryMethod.EMAIL)
        record.sent_at = cast(Any, datetime.utcnow())
    logger.info("Queued quote email sent", extra={"quote_id": quote.id})
    return True


async def fail_queued_quote(db: AsyncSession, payload: dict[str, Any]) -> None:
    """Dead-letter hook: same outcome as an inline SMTP failure.

    The record becomes SEND_FAILED and a quote still SENT goes back to DRAFT,
    so staff can send it again or hand the PDF over.
    """
    quote, record = await _load_queued(db, payload)
    if record is None or record.delivery_method == UpdateDeliveryMethod.EMAIL:
        return
    async with transactional(db):
        record.status = cast(Any, CustomerUpdateStatus.SEND_FAILED)
        if quote is not None and quote.status == QuoteStatus.SENT:
            quote.status = cast(Any, QuoteStatus.DRAFT)
    logger.error("Queued quote email dead-lettered; quote back to DRAFT", extra=payload)
