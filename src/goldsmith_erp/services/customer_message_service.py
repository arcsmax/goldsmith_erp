# src/goldsmith_erp/services/customer_message_service.py
"""
CustomerMessageService: the single way a customer-facing message leaves the
system (W6-01, ARCH-05, decision D-03: email/PDF first, no portal).

Every Kundeninfo mail goes through here: the staff composer
(``POST /orders/{id}/updates`` + ``/updates/{id}/send``), the repair
one-tap send (``RepairService.send_customer_update``), the automated
pickup/fitting mails (``automated_customer_email``) and the §649 cost-change
notice (``CostChangeService.send``, via ``CustomerUpdateService.send``).
Each message is a ``CustomerUpdate`` row (draft -> sent | send_failed),
deduplicated by ``customer_updates.dedupe_key`` where the caller sets one.

Legal basis per message kind (GDPR review 07, section E; DATENSCHUTZHINWEISE-
KUNDEN.md section 2)
---------------------------------------------------------------------------

=============  =================  ===============  ============
kind           legal basis        consent needed   prices
=============  =================  ===============  ============
status_update  Art. 6(1)(b)       none             no
question       Art. 6(1)(b)       none             no
pickup_ready   Art. 6(1)(b)       none             no
appointment    Art. 6(1)(b)       none             no
quote_sent     Art. 6(1)(b)       none             yes
cost_change    Art. 6(1)(b)       none             yes (§649 BGB)
photo_update   Art. 6(1)(a)       PHOTO_USE        no
=============  =================  ===============  ============

- Art. 6(1)(b) (performance of the contract): information the customer needs
  to receive the ordered work (status, pickup, appointment, quote, the §649
  cost notice) needs no consent. It is announced in the Art. 13 notice.
- Art. 6(1)(a) (consent): photos of the customer's piece are only sent with a
  recorded ``PHOTO_USE`` consent. This applies to ANY message that carries
  photos, whatever kind the caller picked; text-only stays allowed.
  Promotional mail (reviews, birthdays) would also be 6(1)(a) + §7 UWG and is
  deliberately not a kind here.
- Art. 21 objection ("Keine E-Mail-Updates"): stored as an ``EMAIL_CONTACT``
  consent row that is revoked with no active one left (see
  ``is_opted_out``). It blocks email for every kind; the message falls back
  to ``PDF_MANUAL`` (the goldsmith hands the PDF over herself).

Other rules enforced here:
- no prices (a currency amount in subject or body) unless the kind may carry
  them (E6 data minimisation);
- photo attachments are the explicitly selected OrderPhotos only, re-encoded
  to JPEG with the longest side at most ``PHOTO_MAX_PX`` and without EXIF
  (``image_validation.create_email_variant``);
- the shared email footer (``templates/email/base.html``) carries the Art. 13
  line and the reply-by-email / unsubscribe instruction (E2, E4);
- every message that reaches the customer (email accepted by SMTP, or a PDF
  confirmed as handed over) writes one ``CustomerAuditLog`` row
  ``customer_message_sent`` with ids, kind, method, legal basis and photo
  count, never the body (E16).

Logs carry ids only, never names, addresses, subjects or bodies.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List, Optional, cast

from sqlalchemy import select
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.core.config import settings
from goldsmith_erp.db.models import (
    CostChangeRequest,
    Customer,
    CustomerAuditLog,
    CustomerConsent,
    CustomerUpdate,
    CustomerUpdateKind,
    CustomerUpdateStatus,
    Order,
    OrderPhoto,
    RepairJob,
    UpdateDeliveryMethod,
)
from goldsmith_erp.db.transaction import transactional
from goldsmith_erp.models.consent import ConsentMethod, ConsentPurpose
from goldsmith_erp.models.customer_update import (
    CustomerMessageContext,
    CustomerMessagePreview,
    CustomerUpdateCreate,
    CustomerUpdateRead,
    CustomerUpdateSendResult,
    NotSentReason,
)
from goldsmith_erp.services.consent_service import ConsentService
from goldsmith_erp.services.email_service import EmailService, _html_to_plain_text
from goldsmith_erp.services.image_validation import (
    PhotoValidationError,
    create_email_variant,
    resolve_within_root,
)
from goldsmith_erp.services.pdf_service import PDFService

logger = logging.getLogger(__name__)

# Longest side of a photo attached to a customer message.
PHOTO_MAX_PX = 1200

AUDIT_ACTION_SENT = "customer_message_sent"
_OPT_OUT_NOTE = "Widerspruch nach Art. 21 DSGVO: keine E-Mail-Updates"
_OPT_OUT_LIFTED_NOTE = "Widerspruch aufgehoben: E-Mail-Updates wieder erlaubt"

# A currency amount: "450,00 €", "1.200 EUR", "€ 99", "80 Euro".
_PRICE_RE = re.compile(
    r"(?:€|\bEUR\b|\bEuros?\b)\s*\d" r"|\d(?:[\d.,\s]*\d)?\s*(?:€|\bEUR\b|\bEuros?\b)",
    re.IGNORECASE,
)


class LegalBasis(str, Enum):
    """Art. 6 DSGVO basis a message kind is sent on."""

    CONTRACT = "Art. 6(1)(b) DSGVO (Vertragserfüllung)"
    CONSENT = "Art. 6(1)(a) DSGVO (Einwilligung)"


class MessageKind(str, Enum):
    """What a customer-facing message is about."""

    STATUS_UPDATE = "status_update"
    PHOTO_UPDATE = "photo_update"
    QUESTION = "question"
    PICKUP_READY = "pickup_ready"
    QUOTE_SENT = "quote_sent"
    COST_CHANGE = "cost_change"
    APPOINTMENT = "appointment"


@dataclass(frozen=True)
class MessagePolicy:
    """Legal basis and content rules of one message kind."""

    legal_basis: LegalBasis
    required_consent: Optional[ConsentPurpose]
    may_contain_prices: bool
    update_kind: CustomerUpdateKind


MESSAGE_POLICIES: Dict[MessageKind, MessagePolicy] = {
    MessageKind.STATUS_UPDATE: MessagePolicy(
        LegalBasis.CONTRACT, None, False, CustomerUpdateKind.PROGRESS
    ),
    MessageKind.QUESTION: MessagePolicy(
        LegalBasis.CONTRACT, None, False, CustomerUpdateKind.CUSTOM
    ),
    MessageKind.PICKUP_READY: MessagePolicy(
        LegalBasis.CONTRACT, None, False, CustomerUpdateKind.READY_FOR_PICKUP
    ),
    MessageKind.APPOINTMENT: MessagePolicy(
        LegalBasis.CONTRACT, None, False, CustomerUpdateKind.CUSTOM
    ),
    MessageKind.QUOTE_SENT: MessagePolicy(
        LegalBasis.CONTRACT, None, True, CustomerUpdateKind.CUSTOM
    ),
    MessageKind.COST_CHANGE: MessagePolicy(
        LegalBasis.CONTRACT, None, True, CustomerUpdateKind.COST_CHANGE
    ),
    MessageKind.PHOTO_UPDATE: MessagePolicy(
        LegalBasis.CONSENT,
        ConsentPurpose.PHOTO_USE,
        False,
        CustomerUpdateKind.PROGRESS,
    ),
}


# ---------------------------------------------------------------------------
# Errors: fixed German messages, never user text (they are logged by
# transactional() if they ever escape one). Router maps them to 422.
# ---------------------------------------------------------------------------


class CustomerMessageError(ValueError):
    """A message violates a customer-communication rule (422)."""


class PhotoConsentRequiredError(CustomerMessageError):
    """Photos selected but the customer has no active PHOTO_USE consent."""

    def __init__(self) -> None:
        super().__init__(
            "Fotos dürfen nur mit Einwilligung der Kundin/des Kunden "
            "('Fotonutzung') verschickt werden. Bitte zuerst die Einwilligung "
            "erfassen oder die Fotos entfernen – ein Text-Update ist möglich."
        )


class PriceNotAllowedError(CustomerMessageError):
    """A currency amount in a message kind that must not carry prices."""

    def __init__(self) -> None:
        super().__init__(
            "Preise dürfen nur in Kostenvoranschlag, Rechnung oder "
            "Kostenänderung verschickt werden. Bitte den Betrag aus Betreff "
            "und Nachricht entfernen."
        )


@dataclass(frozen=True)
class Recipient:
    """Resolved target of a message."""

    order_ref: str
    customer: Optional[Customer]

    @property
    def customer_id(self) -> Optional[int]:
        return None if self.customer is None else cast(int, self.customer.id)

    @property
    def display_name(self) -> str:
        if self.customer is None:
            return "Kunde"
        return f"{self.customer.first_name} {self.customer.last_name}".strip()


def message_kind_for(update_kind: CustomerUpdateKind, has_photos: bool) -> MessageKind:
    """Map a stored CustomerUpdate kind onto the message kind it represents."""
    if update_kind == CustomerUpdateKind.COST_CHANGE:
        return MessageKind.COST_CHANGE
    if update_kind == CustomerUpdateKind.READY_FOR_PICKUP:
        return MessageKind.PICKUP_READY
    if has_photos:
        return MessageKind.PHOTO_UPDATE
    if update_kind == CustomerUpdateKind.PROGRESS:
        return MessageKind.STATUS_UPDATE
    return MessageKind.QUESTION


def contains_price(*texts: Optional[str]) -> bool:
    """True when any text contains a currency amount."""
    return any(text and _PRICE_RE.search(text) for text in texts)


# ---------------------------------------------------------------------------
# Recipient / photos
# ---------------------------------------------------------------------------


async def _load_customer(
    db: AsyncSession, customer_id: Optional[int]
) -> Optional[Customer]:
    if customer_id is None:
        return None
    return (
        await db.execute(select(Customer).where(Customer.id == customer_id))
    ).scalar_one_or_none()


async def resolve_recipient(
    db: AsyncSession, *, order_id: Optional[int], repair_job_id: Optional[int]
) -> Recipient:
    """Return the reference text and customer for an order or a repair."""
    if order_id is not None:
        order = (
            await db.execute(select(Order).where(Order.id == order_id))
        ).scalar_one_or_none()
        if order is None:
            return Recipient(f"Auftrag #{order_id}", None)
        order_ref = cast(Optional[str], order.title) or f"Auftrag #{order.id}"
        customer = await _load_customer(db, cast(Optional[int], order.customer_id))
        return Recipient(order_ref, customer)

    repair = (
        await db.execute(select(RepairJob).where(RepairJob.id == repair_job_id))
    ).scalar_one_or_none()
    if repair is None:
        return Recipient(f"Reparatur #{repair_job_id}", None)
    customer = await _load_customer(db, cast(Optional[int], repair.customer_id))
    return Recipient(f"Reparatur {repair.repair_number}", customer)


async def load_photo_attachments(
    db: AsyncSession, order_id: Optional[int], photo_ids: List[str]
) -> List[bytes]:
    """
    EXIF-free JPEG variants (longest side <= ``PHOTO_MAX_PX``) of the
    explicitly selected OrderPhotos of ``order_id``, in ``photo_ids`` order.

    A photo whose stored path is missing, invalid or outside the storage root
    is skipped with a warning (ids only): one bad photo must not block the
    whole message.
    """
    if not photo_ids or order_id is None:
        return []

    result = await db.execute(
        select(OrderPhoto).where(
            OrderPhoto.id.in_(photo_ids), OrderPhoto.order_id == order_id
        )
    )
    photos_by_id = {cast(str, photo.id): photo for photo in result.scalars().all()}
    photos = [photos_by_id[pid] for pid in photo_ids if pid in photos_by_id]
    storage_root = Path(settings.PHOTO_STORAGE_PATH).resolve()

    variants: List[bytes] = []
    for photo in photos:
        resolved = resolve_within_root(cast(str, photo.file_path), storage_root)
        if resolved is None or not resolved.is_file():
            logger.warning(
                "Customer-update photo path invalid or missing",
                extra={"photo_id": photo.id, "order_id": order_id},
            )
            continue
        try:
            # CPU-bound Pillow work, off the event loop.
            variants.append(
                await asyncio.to_thread(create_email_variant, resolved, PHOTO_MAX_PX)
            )
        except (PhotoValidationError, OSError):
            # PIL.UnidentifiedImageError is an OSError subclass.
            logger.warning(
                "Customer-update photo failed validation",
                extra={"photo_id": photo.id, "order_id": order_id},
                exc_info=True,
            )
    return variants


# ---------------------------------------------------------------------------
# Cost-change rendering (§649 notice) — moved from customer_update_service
# ---------------------------------------------------------------------------


def _format_eur(value: float) -> str:
    formatted = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{formatted} €"


def _format_percent(value: float) -> str:
    formatted = f"{value:,.1f}".replace(".", ",")
    return f"{formatted} %"


async def _send_cost_change_email(
    db: AsyncSession, update: CustomerUpdate, recipient: Recipient
) -> bool:
    """Render and send the linked CostChangeRequest via the §649 template."""
    if update.cost_change_request_id is None:
        logger.error(
            "cost_change CustomerUpdate missing cost_change_request_id",
            extra={"update_id": update.id},
        )
        return False

    cost_change = (
        await db.execute(
            select(CostChangeRequest).where(
                CostChangeRequest.id == update.cost_change_request_id
            )
        )
    ).scalar_one_or_none()
    if cost_change is None:
        logger.error(
            "Linked CostChangeRequest not found for cost_change update",
            extra={
                "update_id": update.id,
                "cost_change_request_id": update.cost_change_request_id,
            },
        )
        return False

    raw_line_items = cast(Optional[List[Dict[str, Any]]], cost_change.line_items)
    line_items = [
        {
            "label": item["label"],
            "amount": _format_eur(item["amount"]),
            "kind": item["kind"],
        }
        for item in (raw_line_items or [])
    ]
    customer = cast(Customer, recipient.customer)
    return await EmailService.send_cost_change(
        to=cast(str, customer.email),
        subject=cast(str, update.subject),
        customer_name=recipient.display_name,
        order_ref=recipient.order_ref,
        original_amount=_format_eur(cast(float, cost_change.original_amount)),
        new_amount=_format_eur(cast(float, cost_change.new_amount)),
        delta_percent=_format_percent(cast(float, cost_change.delta_percent)),
        reason=cast(str, cost_change.reason),
        line_items=line_items,
    )


def _log_message_event(
    action: str,
    update_id: Optional[int],
    order_id: Optional[int],
    user_id: int,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    """Structured audit log line (financial-data access, ids only)."""
    logger.info(
        "Financial data access",
        extra={
            "audit": True,
            "action": action,
            "entity": "customer_update",
            "entity_id": update_id,
            "order_id": order_id,
            "user_id": user_id,
            "timestamp": datetime.utcnow().isoformat(),
            **(extra or {}),
        },
    )


class CustomerMessageService:
    """Static-method service; every method takes the AsyncSession first."""

    # ------------------------------------------------------------------
    # Consent / opt-out
    # ------------------------------------------------------------------

    @staticmethod
    async def is_opted_out(db: AsyncSession, customer_id: Optional[int]) -> bool:
        """True when the customer objected to email updates (Art. 21).

        Stored as EMAIL_CONTACT consent rows: at least one exists and none
        is active (the latest was revoked). A customer with no EMAIL_CONTACT
        row at all is not opted out: status mails are contractual.
        """
        if customer_id is None:
            return False
        rows = (
            await db.execute(
                select(CustomerConsent.revoked_at).where(
                    CustomerConsent.customer_id == customer_id,
                    CustomerConsent.purpose == ConsentPurpose.EMAIL_CONTACT.value,
                )
            )
        ).all()
        return bool(rows) and all(revoked_at is not None for (revoked_at,) in rows)

    @staticmethod
    async def set_email_opt_out(
        db: AsyncSession,
        customer_id: int,
        *,
        opted_out: bool,
        user_id: int,
        method: ConsentMethod = ConsentMethod.IN_PERSON,
    ) -> bool:
        """Record or lift the "Keine E-Mail-Updates" objection; returns it.

        Raises ``ConsentCustomerNotFoundError`` for an unknown/erased
        customer. Each change writes the consent audit row of
        ``ConsentService``.
        """
        async with transactional(db):
            active = await ConsentService.get_active(
                db, customer_id, ConsentPurpose.EMAIL_CONTACT
            )
            if opted_out:
                if active is None:
                    if await CustomerMessageService.is_opted_out(db, customer_id):
                        return True
                    # No row yet: record the objection as a grant that is
                    # immediately withdrawn, so time, method and user are kept.
                    await ConsentService.grant(
                        db,
                        customer_id,
                        purpose=ConsentPurpose.EMAIL_CONTACT,
                        method=method,
                        recorded_by_user_id=user_id,
                        note=_OPT_OUT_NOTE,
                    )
                await ConsentService.revoke(
                    db,
                    customer_id,
                    ConsentPurpose.EMAIL_CONTACT,
                    revoked_by_user_id=user_id,
                )
            elif active is None and await CustomerMessageService.is_opted_out(
                db, customer_id
            ):
                await ConsentService.grant(
                    db,
                    customer_id,
                    purpose=ConsentPurpose.EMAIL_CONTACT,
                    method=method,
                    recorded_by_user_id=user_id,
                    note=_OPT_OUT_LIFTED_NOTE,
                )
        logger.info(
            "Customer email opt-out changed",
            extra={
                "customer_id": customer_id,
                "user_id": user_id,
                "opted_out": opted_out,
            },
        )
        return opted_out

    @staticmethod
    async def check_content(
        db: AsyncSession,
        *,
        kind: MessageKind,
        customer_id: Optional[int],
        subject: Optional[str],
        body: Optional[str],
        photo_ids: Optional[List[str]],
    ) -> None:
        """Raise when the message breaks the price or consent rules."""
        policy = MESSAGE_POLICIES[kind]
        if not policy.may_contain_prices and contains_price(subject, body):
            raise PriceNotAllowedError()
        needs_photo_consent = bool(photo_ids) or (
            policy.required_consent is ConsentPurpose.PHOTO_USE
        )
        if needs_photo_consent and not await CustomerMessageService._has_photo_consent(
            db, customer_id
        ):
            raise PhotoConsentRequiredError()

    @staticmethod
    async def _has_photo_consent(db: AsyncSession, customer_id: Optional[int]) -> bool:
        if customer_id is None:
            return False
        return await ConsentService.has_consent(
            db, customer_id, ConsentPurpose.PHOTO_USE
        )

    # ------------------------------------------------------------------
    # Compose + send (the high-level entry point)
    # ------------------------------------------------------------------

    @staticmethod
    async def send_message(
        db: AsyncSession,
        *,
        kind: MessageKind,
        user_id: int,
        order_id: Optional[int] = None,
        repair_job_id: Optional[int] = None,
        subject: Optional[str] = None,
        body: Optional[str] = None,
        photo_ids: Optional[List[str]] = None,
        dedupe_key: Optional[str] = None,
    ) -> CustomerUpdateSendResult:
        """Record a CustomerUpdate for ``kind`` and deliver it.

        Content rules are checked before anything is stored. Raises
        ``CustomerMessageError`` (422), ``DuplicateDedupeKeyError`` when
        ``dedupe_key`` is already claimed by a live row, and whatever
        ``CustomerUpdateService.create_draft`` raises for a bad target.
        """
        from goldsmith_erp.services.customer_update_service import (  # noqa: PLC0415
            CustomerUpdateService,
        )

        policy = MESSAGE_POLICIES[kind]
        recipient = await resolve_recipient(
            db, order_id=order_id, repair_job_id=repair_job_id
        )
        await CustomerMessageService.check_content(
            db,
            kind=kind,
            customer_id=recipient.customer_id,
            subject=subject,
            body=body,
            photo_ids=photo_ids,
        )
        draft = await CustomerUpdateService.create_draft(
            db,
            order_id=order_id,
            repair_job_id=repair_job_id,
            data=CustomerUpdateCreate(
                kind=policy.update_kind,
                subject=subject,
                body=body,
                photo_ids=photo_ids,
            ),
            user_id=user_id,
            dedupe_key=dedupe_key,
            message_kind=kind,
        )
        return await CustomerMessageService.send_update(
            db, cast(int, draft.id), user_id, message_kind=kind
        )

    @staticmethod
    async def send_update(
        db: AsyncSession,
        update_id: int,
        user_id: int,
        *,
        message_kind: Optional[MessageKind] = None,
    ) -> CustomerUpdateSendResult:
        """
        Deliver (or re-attempt) an existing CustomerUpdate by email.

        Order of checks: content rules (422, nothing changes), SMTP disabled
        (delivered=False, draft untouched), no email address or Art. 21
        opt-out (``method=PDF_MANUAL``, draft stays open for the PDF
        hand-over), then the CAS claim DRAFT/SEND_FAILED -> SENT committed
        before any SMTP dispatch, so two concurrent calls cannot both email
        the customer (the loser gets ``InvalidUpdateStateError``, 409). On
        failure a follow-up transaction flips the row to SEND_FAILED and the
        sender gets an in-app notice. A crash between claim and dispatch
        leaves SENT without a mail: accepted, see the V1.2 review.
        """
        from goldsmith_erp.services.customer_update_service import (  # noqa: PLC0415
            CustomerUpdateNotFoundError,
            CustomerUpdateService,
            InvalidUpdateStateError,
        )

        update = (
            await db.execute(
                select(CustomerUpdate).where(CustomerUpdate.id == update_id)
            )
        ).scalar_one_or_none()
        if update is None:
            raise CustomerUpdateNotFoundError(update_id)
        if update.status == CustomerUpdateStatus.SENT:
            raise InvalidUpdateStateError(update_id, update.status.value)

        order_id = cast(Optional[int], update.order_id)
        photo_ids = cast(Optional[List[str]], update.photo_ids) or []
        kind = message_kind or message_kind_for(
            cast(CustomerUpdateKind, update.kind), bool(photo_ids)
        )
        recipient = await resolve_recipient(
            db,
            order_id=order_id,
            repair_job_id=cast(Optional[int], update.repair_job_id),
        )
        await CustomerMessageService.check_content(
            db,
            kind=kind,
            customer_id=recipient.customer_id,
            subject=cast(str, update.subject),
            body=cast(str, update.body),
            photo_ids=photo_ids,
        )
        photo_variants = await load_photo_attachments(db, order_id, photo_ids)

        early = await CustomerMessageService._pre_dispatch_result(
            db, update, recipient, user_id
        )
        if early is not None:
            return early

        async with transactional(db):
            claim_result = await db.execute(
                sa_update(CustomerUpdate)
                .where(
                    CustomerUpdate.id == update_id,
                    CustomerUpdate.status.in_(
                        [CustomerUpdateStatus.DRAFT, CustomerUpdateStatus.SEND_FAILED]
                    ),
                )
                .values(status=CustomerUpdateStatus.SENT, sent_at=datetime.utcnow())
                .returning(CustomerUpdate.id)
            )
            claimed_id = claim_result.scalar_one_or_none()
        if claimed_id is None:
            raise InvalidUpdateStateError(update_id, update.status.value)
        await db.refresh(update)

        delivered = await CustomerMessageService._dispatch_email(
            db, update, recipient, photo_variants
        )

        method: Optional[UpdateDeliveryMethod] = None
        if delivered:
            async with transactional(db):
                update.delivery_method = cast(Any, UpdateDeliveryMethod.EMAIL)
                CustomerMessageService._add_audit_row(
                    db,
                    update=update,
                    customer_id=recipient.customer_id,
                    user_id=user_id,
                    kind=kind,
                    method=UpdateDeliveryMethod.EMAIL,
                    photo_count=len(photo_variants),
                )
            method = UpdateDeliveryMethod.EMAIL
        else:
            async with transactional(db):
                update.status = cast(Any, CustomerUpdateStatus.SEND_FAILED)
            await CustomerUpdateService._notify_send_failure(db, update, user_id)

        await db.refresh(update)
        _log_message_event(
            "send_attempted",
            update_id,
            order_id,
            user_id,
            extra={"delivered": delivered, "message_kind": kind.value},
        )
        return CustomerUpdateSendResult(
            update=CustomerUpdateRead.model_validate(update),
            delivered=delivered,
            method=method,
        )

    @staticmethod
    async def _pre_dispatch_result(
        db: AsyncSession, update: CustomerUpdate, recipient: Recipient, user_id: int
    ) -> Optional[CustomerUpdateSendResult]:
        """Result for the cases that dispatch nothing, else None."""
        method: Optional[UpdateDeliveryMethod]
        reason: NotSentReason
        if not (settings.EMAIL_NOTIFICATIONS_ENABLED and settings.SMTP_HOST):
            # PDF-only mode: expected, the draft stays claimable.
            method, reason = None, "smtp_disabled"
        elif recipient.customer is not None and not recipient.customer.email:
            method, reason = UpdateDeliveryMethod.PDF_MANUAL, "no_email"
        elif await CustomerMessageService.is_opted_out(db, recipient.customer_id):
            method, reason = UpdateDeliveryMethod.PDF_MANUAL, "opted_out"
        else:
            return None

        await db.refresh(update)
        extra: Dict[str, Any] = {"delivered": False, "reason": reason}
        if method is not None:
            extra["fallback"] = method.value
        _log_message_event(
            "send_attempted",
            cast(int, update.id),
            cast(Optional[int], update.order_id),
            user_id,
            extra=extra,
        )
        return CustomerUpdateSendResult(
            update=CustomerUpdateRead.model_validate(update),
            delivered=False,
            method=method,
            reason=reason,
        )

    @staticmethod
    async def _dispatch_email(
        db: AsyncSession,
        update: CustomerUpdate,
        recipient: Recipient,
        photo_variants: List[bytes],
    ) -> bool:
        if recipient.customer is None or not recipient.customer.email:
            return False  # a data gap the sender must act on
        if update.kind == CustomerUpdateKind.COST_CHANGE:
            return await _send_cost_change_email(db, update, recipient)
        attachments = [
            (f"foto-{i + 1}.jpg", data) for i, data in enumerate(photo_variants)
        ]
        return await EmailService.send_customer_update(
            to=cast(str, recipient.customer.email),
            subject=cast(str, update.subject),
            customer_name=recipient.display_name,
            body=cast(str, update.body),
            order_ref=recipient.order_ref,
            photo_count=len(photo_variants),
            attachments=attachments or None,
        )

    # ------------------------------------------------------------------
    # Audit (E16)
    # ------------------------------------------------------------------

    @staticmethod
    def _add_audit_row(
        db: AsyncSession,
        *,
        update: CustomerUpdate,
        customer_id: Optional[int],
        user_id: int,
        kind: MessageKind,
        method: UpdateDeliveryMethod,
        photo_count: int,
    ) -> None:
        """Stage the per-message audit row (caller commits). No body/subject."""
        db.add(
            CustomerAuditLog(
                customer_id=customer_id,
                user_id=user_id,
                action=AUDIT_ACTION_SENT,
                entity="customer_update",
                entity_id=update.id,
                timestamp=datetime.utcnow(),
                details={
                    "message_kind": kind.value,
                    "delivery_method": method.value,
                    "photo_count": photo_count,
                    "photo_ids": list(
                        cast(Optional[List[str]], update.photo_ids) or []
                    ),
                    "order_id": update.order_id,
                    "repair_job_id": update.repair_job_id,
                    "legal_basis": MESSAGE_POLICIES[kind].legal_basis.value,
                },
            )
        )

    @staticmethod
    async def record_manual_delivery(
        db: AsyncSession, update: CustomerUpdate, user_id: int
    ) -> None:
        """Stage the audit row for a PDF handed over by the goldsmith."""
        recipient = await resolve_recipient(
            db,
            order_id=cast(Optional[int], update.order_id),
            repair_job_id=cast(Optional[int], update.repair_job_id),
        )
        photo_ids = cast(Optional[List[str]], update.photo_ids) or []
        CustomerMessageService._add_audit_row(
            db,
            update=update,
            customer_id=recipient.customer_id,
            user_id=user_id,
            kind=message_kind_for(
                cast(CustomerUpdateKind, update.kind), bool(photo_ids)
            ),
            method=UpdateDeliveryMethod.PDF_MANUAL,
            photo_count=len(photo_ids),
        )

    # ------------------------------------------------------------------
    # Composer support: context, preview, PDF preview
    # ------------------------------------------------------------------

    @staticmethod
    async def message_context(
        db: AsyncSession,
        *,
        order_id: Optional[int] = None,
        repair_job_id: Optional[int] = None,
    ) -> CustomerMessageContext:
        """What the composer needs to show consent / delivery hints."""
        recipient = await resolve_recipient(
            db, order_id=order_id, repair_job_id=repair_job_id
        )
        customer_id = recipient.customer_id
        return CustomerMessageContext(
            customer_id=customer_id,
            has_email=bool(recipient.customer is not None and recipient.customer.email),
            photo_consent=await CustomerMessageService._has_photo_consent(
                db, customer_id
            ),
            email_opt_out=await CustomerMessageService.is_opted_out(db, customer_id),
        )

    @staticmethod
    async def _resolved_content(
        kind: CustomerUpdateKind,
        order_ref: str,
        subject: Optional[str],
        body: Optional[str],
    ) -> tuple[str, str]:
        from goldsmith_erp.services.customer_update_service import (  # noqa: PLC0415
            _default_subject_body,
        )

        if subject is not None and body is not None:
            return subject, body
        default_subject, default_body = _default_subject_body(kind, order_ref)
        return subject or default_subject, body or default_body

    @staticmethod
    async def preview(
        db: AsyncSession,
        *,
        kind: CustomerUpdateKind,
        subject: Optional[str],
        body: Optional[str],
        photo_ids: Optional[List[str]],
        order_id: Optional[int] = None,
        repair_job_id: Optional[int] = None,
    ) -> CustomerMessagePreview:
        """Render the email text the customer would get; never raises on
        rule violations but reports them in ``blocked_reason``."""
        from goldsmith_erp.services.customer_update_service import (  # noqa: PLC0415
            MissingCustomerUpdateContentError,
        )

        recipient = await resolve_recipient(
            db, order_id=order_id, repair_job_id=repair_job_id
        )
        context = await CustomerMessageService.message_context(
            db, order_id=order_id, repair_job_id=repair_job_id
        )
        blocked_reason: Optional[str] = None
        try:
            final_subject, final_body = await CustomerMessageService._resolved_content(
                kind, recipient.order_ref, subject, body
            )
        except MissingCustomerUpdateContentError as exc:
            final_subject, final_body = subject or "", body or ""
            blocked_reason = str(exc)

        message_kind = message_kind_for(kind, bool(photo_ids))
        if blocked_reason is None:
            try:
                await CustomerMessageService.check_content(
                    db,
                    kind=message_kind,
                    customer_id=recipient.customer_id,
                    subject=final_subject,
                    body=final_body,
                    photo_ids=photo_ids,
                )
            except CustomerMessageError as exc:
                blocked_reason = str(exc)

        photo_count = len(photo_ids or [])
        html = EmailService._render_template(
            "customer_update.html",
            {
                "customer_name": recipient.display_name,
                "body": final_body,
                "order_ref": recipient.order_ref,
                "photo_count": photo_count,
            },
        )
        use_email = context.has_email and not context.email_opt_out
        return CustomerMessagePreview(
            subject=final_subject,
            text=_html_to_plain_text(html),
            delivery_method=(
                UpdateDeliveryMethod.EMAIL
                if use_email
                else UpdateDeliveryMethod.PDF_MANUAL
            ),
            photo_count=photo_count,
            photo_consent=context.photo_consent,
            email_opt_out=context.email_opt_out,
            has_email=context.has_email,
            legal_basis=MESSAGE_POLICIES[message_kind].legal_basis.value,
            blocked_reason=blocked_reason,
        )

    @staticmethod
    async def render_preview_pdf(
        db: AsyncSession,
        *,
        kind: CustomerUpdateKind,
        subject: Optional[str],
        body: Optional[str],
        photo_ids: Optional[List[str]],
        order_id: Optional[int] = None,
        repair_job_id: Optional[int] = None,
    ) -> bytes:
        """The composer's content as PDF, without storing anything.

        Same rules as sending (raises ``CustomerMessageError``); the PDF is
        what a customer without email receives.
        """
        recipient = await resolve_recipient(
            db, order_id=order_id, repair_job_id=repair_job_id
        )
        final_subject, final_body = await CustomerMessageService._resolved_content(
            kind, recipient.order_ref, subject, body
        )
        await CustomerMessageService.check_content(
            db,
            kind=message_kind_for(kind, bool(photo_ids)),
            customer_id=recipient.customer_id,
            subject=final_subject,
            body=final_body,
            photo_ids=photo_ids,
        )
        photos = await load_photo_attachments(db, order_id, photo_ids or [])
        transient = SimpleNamespace(
            id=None,
            order_id=order_id,
            repair_job_id=repair_job_id,
            subject=final_subject,
            body=final_body,
        )
        return await asyncio.to_thread(
            PDFService.render_customer_update_pdf,
            update=transient,
            order_ref=recipient.order_ref,
            customer_name=recipient.display_name,
            photos=photos,
            workshop_name=settings.WORKSHOP_NAME,
        )
