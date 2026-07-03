# src/goldsmith_erp/services/customer_update_service.py
"""
CustomerUpdateService — draft/send/PDF lifecycle for Kundeninfo updates
(V1.2 Task 5).

Precedent followed:
    - Typed exceptions (ValueError subclasses) raised OUTSIDE
      ``transactional(db)`` when the message could carry user text,
      mirroring ``repair_service.InvalidChecklistPhotoError`` /
      ``no_go_service.DuplicateNoGoError``: ``transactional()`` logs
      ``str(exc)`` at ERROR on any escaping exception, so a pre-flight
      raise (before entering the block) keeps that logger ID-only.
    - Financial-data structured audit logging mirrors
      ``invoice_service._log_financial_access`` (a per-file structured
      logger helper, "audit": True extra) rather than writing
      ``CustomerAuditLog`` rows directly — see the module docstring on
      ``AuditLoggingMiddleware`` for why: ``/orders/{id}/updates`` keys on
      the FIRST path segment ("orders"), which is not itself an audited
      resource family, so the middleware cannot see these order-scoped
      reads. The ``updates`` family IS added to
      ``middleware.audit_logging._RESOURCE_ROUTES`` (covers
      ``GET /updates/{id}/pdf``), but the three ``/orders/{id}/...`` GETs
      (history, cost-changes list, projected-cost) and every mutation
      need this service-level fallback to satisfy CLAUDE.md's "All
      financial data access MUST be audit-logged" for the read paths the
      middleware structurally cannot key on. See report for the full
      resolution.
    - Photo attachments/embeds are built from the EXPLICIT
      ``photo_ids`` only (design-IP rule — nothing auto-shared), read via
      ``image_validation.resolve_within_root`` (V1.1 security precedent:
      DB path columns are not trustworthy by construction) then
      ``create_email_variant`` (EXIF-stripped, ≤1600px JPEG).
    - order_ref formatting matches the established convention seen across
      handoff_service/notification_service/customer_portal.py:
      ``order.title or f"Auftrag #{order.id}"`` for orders,
      ``f"Reparatur {repair.repair_number}"`` for repairs.

Router-exposed scope note: this service's ``create_draft`` supports BOTH
``order_id`` and ``repair_job_id`` targets (mirrors the ``CustomerUpdate``
model's dual-target invariant and the plan's documented signature), but
Task 5's router only wires up the order-scoped
``POST /orders/{id}/updates`` endpoint — no ``/repairs/{id}/updates``
route exists yet (not in the plan's enumerated endpoint list). A
symmetric repair endpoint can be added later without any service changes.
"""
from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.core.config import settings
from goldsmith_erp.db.models import (
    CostChangeRequest,
    Customer,
    CustomerUpdate,
    CustomerUpdateKind,
    CustomerUpdateStatus,
    NotificationSeverityEnum,
    NotificationTypeEnum,
    Order,
    OrderPhoto,
    RepairJob,
    UpdateDeliveryMethod,
)
from goldsmith_erp.db.transaction import transactional
from goldsmith_erp.models.customer_update import (
    CustomerUpdateCreate,
    CustomerUpdateRead,
    CustomerUpdateSendResult,
)
from goldsmith_erp.services.email_service import EmailService
from goldsmith_erp.services.image_validation import (
    PhotoValidationError,
    create_email_variant,
    resolve_within_root,
)
from goldsmith_erp.services.pdf_service import PDFService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Typed exceptions — see module docstring for the raise-outside-transactional
# rationale. Messages are ID-only / fixed strings, never user free-text
# (CLAUDE.md: customer PII / design-IP text must never reach a log line).
# ---------------------------------------------------------------------------


class CustomerUpdateNotFoundError(ValueError):
    """No CustomerUpdate row with this id — maps to 404."""

    def __init__(self, update_id: int) -> None:
        super().__init__(f"Kundeninfo-Update #{update_id} nicht gefunden")


class InvalidUpdateStateError(ValueError):
    """The update's current status forbids the requested action — maps to 409."""

    def __init__(self, update_id: int, current_status: str) -> None:
        super().__init__(
            f"Kundeninfo-Update #{update_id} hat bereits Status "
            f"'{current_status}' — Aktion nicht erlaubt"
        )


class CustomerUpdateValidationError(ValueError):
    """Base for malformed-input failures on CustomerUpdate creation — maps to 422."""


class InvalidUpdatePhotoError(CustomerUpdateValidationError):
    """
    One or more ``photo_ids`` do not resolve to an OrderPhoto of the target
    order, or photos were supplied for a repair-targeted update (spec ties
    photo sharing to ORDER updates only — repairs have no order-scoped
    photo pool here).

    Message is ID-only, mirroring ``repair_service.InvalidChecklistPhotoError``.
    """

    def __init__(self, invalid_photo_ids: List[str]) -> None:
        super().__init__(
            f"Ungueltige photo_id(s): {invalid_photo_ids} — muss ein Foto "
            "dieses Auftrags sein"
        )


class PhotosNotAllowedForRepairError(CustomerUpdateValidationError):
    """photo_ids were supplied for a repair-targeted update — not permitted."""

    def __init__(self) -> None:
        super().__init__("Fotos nur bei Auftrags-Updates erlaubt")


class MissingCustomerUpdateContentError(CustomerUpdateValidationError):
    """kind=custom has no template to prefill from — subject/body are required."""

    def __init__(self) -> None:
        super().__init__(
            "Fuer kind='custom' muessen subject und body angegeben werden "
            "— kein Template vorhanden"
        )


# ---------------------------------------------------------------------------
# Default subject/body per kind (template prefill) — see report for why this
# is NOT routed through EmailService.render_preview: that method's
# _PREVIEW_CONTEXTS allowlist has no entry for "customer_update"/"cost_change"
# (only the six pre-V1.2 notification templates), and more fundamentally it
# returns fully-rendered HTML (the whole customer_update.html page) — not
# suitable for prefilling the editable CustomerUpdate.subject/body TEXT
# fields, which are the free-text substituted INTO that template, not the
# template's own output. This mirrors the subject-building already
# duplicated per typed sender in email_service.py (send_order_confirmed etc).
# ---------------------------------------------------------------------------


def _default_subject_body(kind: CustomerUpdateKind, order_ref: str) -> tuple[str, str]:
    if kind == CustomerUpdateKind.PROGRESS:
        return (
            f"Update zu Ihrem Auftrag {order_ref}",
            "Ihr Auftrag befindet sich weiterhin in Bearbeitung. Wir halten "
            "Sie ueber den Fortschritt auf dem Laufenden.",
        )
    if kind == CustomerUpdateKind.READY_FOR_PICKUP:
        return (
            f"Ihr Schmuckstueck ist fertig zur Abholung — {order_ref}",
            "Ihr Schmuckstueck ist fertig und kann ab sofort in unserem "
            "Atelier abgeholt werden.",
        )
    # CUSTOM (and COST_CHANGE, which never reaches this path — see
    # CostChangeService, which builds its own CustomerUpdate row directly)
    # has no template — the caller must supply both fields explicitly.
    raise MissingCustomerUpdateContentError()


# ---------------------------------------------------------------------------
# Small formatting helpers (German locale) — duplicated in miniature from
# pdf_service._fmt_eur rather than importing a private helper cross-module.
# ---------------------------------------------------------------------------


def _format_eur(value: float) -> str:
    formatted = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{formatted} €"


def _format_percent(value: float) -> str:
    formatted = f"{value:,.1f}".replace(".", ",")
    return f"{formatted} %"


# ---------------------------------------------------------------------------
# Financial-data structured audit logging — see module docstring.
# ---------------------------------------------------------------------------


def _log_financial_access(
    action: str,
    update_id: Optional[int],
    order_id: Optional[int],
    user_id: int,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
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


# ---------------------------------------------------------------------------
# Target / customer resolution — shared by send() and render_pdf()
# ---------------------------------------------------------------------------


async def _resolve_target(
    db: AsyncSession, update: CustomerUpdate
) -> tuple[str, Optional[Customer]]:
    """Return (order_ref, customer-or-None) for either target kind."""
    if update.order_id is not None:
        order = (
            await db.execute(select(Order).where(Order.id == update.order_id))
        ).scalar_one_or_none()
        if order is None:
            return f"Auftrag #{update.order_id}", None
        # cast(): mypy sees Column[str] at class level for `title` (classic
        # Column() style, no Mapped[] here) — at runtime, on a loaded
        # instance, it is a plain Optional[str] (matches cost_watch_service's
        # established cast() precedent for this exact false-positive class).
        order_ref = cast(Optional[str], order.title) or f"Auftrag #{order.id}"
        customer = None
        if order.customer_id is not None:
            customer = (
                await db.execute(
                    select(Customer).where(Customer.id == order.customer_id)
                )
            ).scalar_one_or_none()
        return order_ref, customer

    repair = (
        await db.execute(select(RepairJob).where(RepairJob.id == update.repair_job_id))
    ).scalar_one_or_none()
    if repair is None:
        return f"Reparatur #{update.repair_job_id}", None
    order_ref = f"Reparatur {repair.repair_number}"
    customer = None
    if repair.customer_id is not None:
        customer = (
            await db.execute(select(Customer).where(Customer.id == repair.customer_id))
        ).scalar_one_or_none()
    return order_ref, customer


async def _load_photo_variant_bytes(
    db: AsyncSession, order_id: Optional[int], photo_ids: List[str]
) -> List[bytes]:
    """
    Load the explicitly-selected OrderPhotos and return EXIF-stripped
    email-variant JPEG bytes for each one that can be read. A photo whose
    path is missing/invalid/escapes the storage root is skipped with a
    logged warning — one bad photo must not block the whole send/PDF
    (mirrors ``pdf_service._embed_photo_grid``'s graceful degradation).
    """
    if not photo_ids or order_id is None:
        return []

    result = await db.execute(
        select(OrderPhoto).where(
            OrderPhoto.id.in_(photo_ids), OrderPhoto.order_id == order_id
        )
    )
    photos = result.scalars().all()
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
            variants.append(create_email_variant(resolved))
        except PhotoValidationError:
            logger.warning(
                "Customer-update photo failed validation",
                extra={"photo_id": photo.id, "order_id": order_id},
                exc_info=True,
            )
    return variants


async def _send_cost_change_email(
    db: AsyncSession,
    update: CustomerUpdate,
    customer: Customer,
    order_ref: str,
    customer_name: str,
) -> bool:
    """Render+send the linked CostChangeRequest via the §649 template."""
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

    # cast(): line_items is a nullable JSON column (Column[Any] at class
    # level); at runtime it's either None or list[dict[str, Any]].
    raw_line_items = cast(Optional[List[Dict[str, Any]]], cost_change.line_items)
    line_items = [
        {
            "label": item["label"],
            "amount": _format_eur(item["amount"]),
            "kind": item["kind"],
        }
        for item in (raw_line_items or [])
    ]

    return await EmailService.send_cost_change(
        to=cast(str, customer.email),
        subject=cast(str, update.subject),
        customer_name=customer_name,
        order_ref=order_ref,
        original_amount=_format_eur(cast(float, cost_change.original_amount)),
        new_amount=_format_eur(cast(float, cost_change.new_amount)),
        delta_percent=_format_percent(cast(float, cost_change.delta_percent)),
        reason=cast(str, cost_change.reason),
        line_items=line_items,
    )


class CustomerUpdateService:
    """Static-method service — all methods accept AsyncSession as first arg."""

    # ------------------------------------------------------------------
    # Draft creation
    # ------------------------------------------------------------------

    @staticmethod
    async def create_draft(
        db: AsyncSession,
        *,
        order_id: Optional[int],
        repair_job_id: Optional[int],
        data: CustomerUpdateCreate,
        user_id: int,
    ) -> CustomerUpdate:
        """
        Create a DRAFT CustomerUpdate for exactly one target.

        Raises:
            ValueError: target (order/repair) does not exist, or exactly-one
                invariant is violated (both/neither id supplied — router bug
                guard, not expected from real callers).
            InvalidUpdatePhotoError / PhotosNotAllowedForRepairError /
                MissingCustomerUpdateContentError: malformed input (422).
        """
        if (order_id is None) == (repair_job_id is None):
            raise ValueError("Exakt eines von order_id/repair_job_id muss gesetzt sein")

        order_ref: str
        if order_id is not None:
            order = (
                await db.execute(select(Order).where(Order.id == order_id))
            ).scalar_one_or_none()
            if order is None:
                raise ValueError(f"Auftrag #{order_id} nicht gefunden")
            order_ref = cast(Optional[str], order.title) or f"Auftrag #{order.id}"

            if data.photo_ids:
                result = await db.execute(
                    select(OrderPhoto.id).where(
                        OrderPhoto.id.in_(data.photo_ids),
                        OrderPhoto.order_id == order_id,
                    )
                )
                valid_ids = set(result.scalars().all())
                invalid_ids = sorted(set(data.photo_ids) - valid_ids)
                if invalid_ids:
                    raise InvalidUpdatePhotoError(invalid_ids)
        else:
            repair = (
                await db.execute(select(RepairJob).where(RepairJob.id == repair_job_id))
            ).scalar_one_or_none()
            if repair is None:
                raise ValueError(f"Reparaturauftrag #{repair_job_id} nicht gefunden")
            order_ref = f"Reparatur {repair.repair_number}"

            if data.photo_ids:
                raise PhotosNotAllowedForRepairError()

        subject = data.subject
        body = data.body
        if subject is None or body is None:
            default_subject, default_body = _default_subject_body(data.kind, order_ref)
            subject = subject or default_subject
            body = body or default_body

        async with transactional(db):
            update = CustomerUpdate(
                order_id=order_id,
                repair_job_id=repair_job_id,
                kind=data.kind,
                subject=subject,
                body=body,
                photo_ids=data.photo_ids or None,
                status=CustomerUpdateStatus.DRAFT,
                sent_by=user_id,
            )
            db.add(update)

        await db.refresh(update)
        _log_financial_access("draft_created", cast(int, update.id), order_id, user_id)
        return update

    # ------------------------------------------------------------------
    # Send
    # ------------------------------------------------------------------

    @staticmethod
    async def send(
        db: AsyncSession, update_id: int, user_id: int
    ) -> CustomerUpdateSendResult:
        """
        Send (or re-attempt) a CustomerUpdate via email.

        Never blocks on delivery failure: SMTP-unset, missing customer
        email, and genuine SMTP failures all return a 200-shaped result
        with ``delivered=False`` — the draft always persists (spec: a
        failed send is a recorded outcome, not a 5xx).

        Raises:
            CustomerUpdateNotFoundError: no such update (404).
            InvalidUpdateStateError: update already SENT — re-sending a
                sent update is rejected (409). DRAFT and SEND_FAILED may
                both (re-)attempt delivery.
        """
        update = (
            await db.execute(
                select(CustomerUpdate).where(CustomerUpdate.id == update_id)
            )
        ).scalar_one_or_none()
        if update is None:
            raise CustomerUpdateNotFoundError(update_id)
        if update.status == CustomerUpdateStatus.SENT:
            raise InvalidUpdateStateError(update_id, update.status.value)

        order_ref, customer = await _resolve_target(db, update)
        photo_variants = await _load_photo_variant_bytes(
            db,
            cast(Optional[int], update.order_id),
            cast(Optional[List[str]], update.photo_ids) or [],
        )
        photo_attachments = [
            (f"foto-{i + 1}.jpg", data) for i, data in enumerate(photo_variants)
        ]

        delivered = False
        attempted = False

        if not settings.EMAIL_NOTIFICATIONS_ENABLED or not settings.SMTP_HOST:
            # PDF-only mode — expected, not a failure. Nothing attempted.
            pass
        elif customer is None or not customer.email:
            # A real per-record data gap the sender needs to act on.
            attempted = True
        else:
            attempted = True
            customer_name = f"{customer.first_name} {customer.last_name}".strip()
            if update.kind == CustomerUpdateKind.COST_CHANGE:
                delivered = await _send_cost_change_email(
                    db, update, customer, order_ref, customer_name
                )
            else:
                delivered = await EmailService.send_customer_update(
                    to=cast(str, customer.email),
                    subject=cast(str, update.subject),
                    customer_name=customer_name,
                    body=cast(str, update.body),
                    order_ref=order_ref,
                    photo_count=len(photo_variants),
                    attachments=photo_attachments or None,
                )

        method: Optional[UpdateDeliveryMethod] = None
        async with transactional(db):
            if delivered:
                update.status = cast(Any, CustomerUpdateStatus.SENT)
                update.sent_at = cast(Any, datetime.utcnow())
                update.delivery_method = cast(Any, UpdateDeliveryMethod.EMAIL)
                method = UpdateDeliveryMethod.EMAIL
            elif attempted:
                update.status = cast(Any, CustomerUpdateStatus.SEND_FAILED)

        if attempted and not delivered:
            await CustomerUpdateService._notify_send_failure(db, update, user_id)

        await db.refresh(update)
        _log_financial_access(
            "send_attempted",
            update_id,
            cast(Optional[int], update.order_id),
            user_id,
            extra={"delivered": delivered},
        )
        return CustomerUpdateSendResult(
            update=CustomerUpdateRead.model_validate(update),
            delivered=delivered,
            method=method,
        )

    @staticmethod
    async def _notify_send_failure(
        db: AsyncSession, update: CustomerUpdate, user_id: int
    ) -> None:
        """Notify the sender of a failed send — never silent (CLAUDE.md)."""
        # Late import — mirrors the CostWatchService._raise_cost_alert
        # convention of deferring cross-service imports to call time.
        from goldsmith_erp.services.notification_service import (  # noqa: PLC0415
            NotificationService,
        )

        try:
            await NotificationService.create_notification(
                db=db,
                user_id=user_id,
                title=f"Versand fehlgeschlagen: Update #{update.id}",
                message=(
                    f"Der Versand des Kundeninfo-Updates #{update.id} ist "
                    "fehlgeschlagen. Bitte pruefen Sie die Kundendaten oder "
                    "senden Sie das Update als PDF."
                ),
                notification_type=NotificationTypeEnum.SYSTEM,
                severity=NotificationSeverityEnum.WARNING,
                related_order_id=cast(Optional[int], update.order_id),
            )
        except Exception:
            logger.error(
                "Failed to notify sender of update send failure",
                extra={"update_id": update.id},
                exc_info=True,
            )

    # ------------------------------------------------------------------
    # PDF fallback (delivery_method=pdf_manual)
    # ------------------------------------------------------------------

    @staticmethod
    async def render_pdf(db: AsyncSession, update_id: int) -> bytes:
        """
        Render the update as PDF bytes — a pure read, no status mutation
        (spec: downloading must not mark the update delivered; see
        ``mark_delivered`` for the explicit confirmation step).
        """
        update = (
            await db.execute(
                select(CustomerUpdate).where(CustomerUpdate.id == update_id)
            )
        ).scalar_one_or_none()
        if update is None:
            raise CustomerUpdateNotFoundError(update_id)

        order_ref, customer = await _resolve_target(db, update)
        customer_name = (
            f"{customer.first_name} {customer.last_name}".strip()
            if customer is not None
            else "Kunde"
        )
        photos = await _load_photo_variant_bytes(
            db,
            cast(Optional[int], update.order_id),
            cast(Optional[List[str]], update.photo_ids) or [],
        )

        return PDFService.render_customer_update_pdf(
            update=update,
            order_ref=order_ref,
            customer_name=customer_name,
            photos=photos,
            workshop_name=settings.WORKSHOP_NAME,
        )

    # ------------------------------------------------------------------
    # Explicit delivery confirmation (PDF handed over manually)
    # ------------------------------------------------------------------

    @staticmethod
    async def mark_delivered(
        db: AsyncSession,
        update_id: int,
        user_id: int,
        method: UpdateDeliveryMethod = UpdateDeliveryMethod.PDF_MANUAL,
    ) -> CustomerUpdate:
        """
        Explicitly confirm an out-of-band delivery (goldsmith handed the
        PDF over herself). Never triggered by ``render_pdf`` — downloading
        must not silently mark an update as delivered.

        Raises:
            CustomerUpdateNotFoundError: no such update (404).
            InvalidUpdateStateError: update already SENT (409).
        """
        update = (
            await db.execute(
                select(CustomerUpdate).where(CustomerUpdate.id == update_id)
            )
        ).scalar_one_or_none()
        if update is None:
            raise CustomerUpdateNotFoundError(update_id)
        if update.status == CustomerUpdateStatus.SENT:
            raise InvalidUpdateStateError(update_id, update.status.value)

        async with transactional(db):
            update.status = cast(Any, CustomerUpdateStatus.SENT)
            update.sent_at = cast(Any, datetime.utcnow())
            update.delivery_method = cast(Any, method)

        await db.refresh(update)
        _log_financial_access(
            "marked_delivered", update_id, cast(Optional[int], update.order_id), user_id
        )
        return update

    # ------------------------------------------------------------------
    # History
    # ------------------------------------------------------------------

    @staticmethod
    async def list_for_order(
        db: AsyncSession, order_id: int, user_id: int
    ) -> List[CustomerUpdate]:
        """
        Update history for an order, newest first. Does not itself check
        order existence (mirrors ``HandoffService.get_order_handoff_history``
        — an order with zero updates yields an empty list either way).
        """
        result = await db.execute(
            select(CustomerUpdate)
            .where(CustomerUpdate.order_id == order_id)
            .order_by(CustomerUpdate.created_at.desc())
        )
        updates = list(result.scalars().all())
        _log_financial_access("list_accessed", None, order_id, user_id)
        return updates
