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
      logger helper, "audit": True extra) — kept as-is for every
      mutation and read in this module. See the module docstring on
      ``AuditLoggingMiddleware`` for why that middleware alone cannot
      cover this module's reads: ``/orders/{id}/updates`` keys on the
      FIRST path segment ("orders"), which is not itself an audited
      resource family, so the middleware cannot see these order-scoped
      GETs. The ``updates`` family IS added to
      ``middleware.audit_logging._RESOURCE_ROUTES`` (covers
      ``GET /updates/{id}/pdf``), but the structural blind spot for
      ``GET /orders/{id}/updates`` (and the sibling
      ``/orders/{id}/cost-changes`` list + ``/orders/{id}/projected-cost``
      in ``cost_change_service.py`` / the router) is RESOLVED
      (final-review fix, decision: service-level and scoped — not a
      blanket ``/orders`` middleware family, which would over-audit every
      unrelated order fetch app-wide): each of those three GETs now ALSO
      writes a ``CustomerAuditLog`` row directly, via
      ``write_financial_audit_row`` below, mirroring
      ``AuditLoggingMiddleware._log_to_database``'s action naming
      (``list_accessed_financial`` / ``financial_read``) and ``details``
      JSON shape (endpoint/http_method/legal_basis/purpose), with
      ``customer_id`` derived from the order. See the report for the
      full resolution.
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
from sqlalchemy import update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.core.config import settings
from goldsmith_erp.db.models import (
    CostChangeRequest,
    Customer,
    CustomerAuditLog,
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


class CostChangeKindNotAllowedError(CustomerUpdateValidationError):
    """
    kind=cost_change was submitted to the generic updates endpoint —
    cost-change updates are ONLY created internally by
    ``CostChangeService.send()`` (they must carry a linked
    CostChangeRequest with derived amounts; a hand-rolled one would be a
    §649 notice with no evidence record behind it). Review fix round 1.
    """

    def __init__(self) -> None:
        super().__init__(
            "Kostenänderungen werden über den Kostenänderungs-Workflow erstellt"
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
# DB-backed financial audit rows for the 3 GETs AuditLoggingMiddleware
# structurally cannot see (final-review fix — see module docstring).
#
# Shared by CustomerUpdateService.list_for_order (this module),
# CostChangeService.list_for_order (imports this function — that module
# already depends on this one for CustomerUpdateService.send, so this adds
# no new coupling axis) and the router's projected-cost handler.
# ---------------------------------------------------------------------------


async def write_financial_audit_row(
    db: AsyncSession,
    *,
    action: str,
    entity: str,
    entity_id: Optional[int],
    order_id: Optional[int],
    user_id: int,
    endpoint: str,
) -> None:
    """
    Persist a ``CustomerAuditLog`` row for a financial-data GET that
    ``AuditLoggingMiddleware`` cannot key on (see that middleware's
    ``_RESOURCE_ROUTES`` comment on the ``/orders/{id}/...`` blind spot).

    Mirrors ``AuditLoggingMiddleware._log_to_database``'s row shape:
    same ``action`` naming convention (``list_accessed_financial`` /
    ``financial_read``), same legal-basis / purpose derivation, and the
    same ``details`` JSON keys (``endpoint``, ``http_method``,
    ``legal_basis``, ``purpose``) — minus ``status_code``/``duration_ms``,
    which the middleware measures around the whole request and are not
    available at this call depth; this is only ever invoked once the
    underlying read has already succeeded, so a 200 is implied. Only GET
    reads call this today, so ``http_method`` is hardcoded.

    ``customer_id`` is derived from the order (CLAUDE.md: financial-data
    audit rows must be traceable to the customer), not from the caller —
    a caller supplying the wrong id here would silently mis-attribute the
    row, so this method does its own lookup rather than trusting a
    passed-in value.

    Fire-and-forget, mirroring the middleware's own broad except: a DB
    outage on the audit path must never deny (or 500) the legitimate read
    it is auditing (security > correctness > convenience, but here
    "correctness of the response" outranks "completeness of the audit
    trail" — the exact same tradeoff the middleware documents for its own
    write). Failures are logged loudly instead of swallowed.
    """
    customer_id: Optional[int] = None
    if order_id is not None:
        order = (
            await db.execute(select(Order).where(Order.id == order_id))
        ).scalar_one_or_none()
        if order is not None:
            customer_id = cast(Optional[int], order.customer_id)

    details = {
        "endpoint": endpoint,
        "http_method": "GET",
        "legal_basis": "GDPR Article 6(1)(c) - Legal obligation (§147 AO)",
        "purpose": f"{entity.replace('_', ' ').title()} {action} via API",
    }

    try:
        audit_log = CustomerAuditLog(
            customer_id=customer_id,
            action=action,
            entity=entity,
            entity_id=entity_id,
            user_id=user_id,
            timestamp=datetime.utcnow(),
            details=details,
        )
        db.add(audit_log)
        await db.commit()
    except Exception:
        await db.rollback()
        logger.error(
            "financial audit DB write failed",
            extra={"audit": True, "entity": entity, "entity_id": entity_id},
            exc_info=True,
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
                MissingCustomerUpdateContentError /
                CostChangeKindNotAllowedError: malformed input (422).
        """
        if (order_id is None) == (repair_job_id is None):
            raise ValueError("Exakt eines von order_id/repair_job_id muss gesetzt sein")

        if data.kind == CustomerUpdateKind.COST_CHANGE:
            # cost_change updates are only created internally by
            # CostChangeService.send() — see the exception's docstring.
            raise CostChangeKindNotAllowedError()

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

        Concurrency (review fix — send-path race): two concurrent
        ``send()`` calls for the SAME update must not both dispatch email
        to the customer. The initial status read above is a plain
        SELECT — racy: two callers can both observe DRAFT/SEND_FAILED and
        both proceed. The actual DRAFT/SEND_FAILED -> SENT transition is
        therefore claimed with a conditional
        ``UPDATE ... WHERE id=:id AND status IN ('draft','send_failed')
        ... RETURNING id``, committed BEFORE any SMTP dispatch starts.
        Only the caller whose UPDATE affects a row proceeds; a second,
        truly concurrent caller's UPDATE affects zero rows (the winner's
        commit already flipped the status) and it raises
        ``InvalidUpdateStateError`` (409) — same outcome as if it had
        arrived after the winner's commit, just enforced at the DB level
        instead of trusted from a stale in-process read.

        The CAS optimistically writes ``status=SENT``/``sent_at=now()``
        BEFORE the dispatch outcome is known; on failure a follow-up
        transaction flips the status to SEND_FAILED (``delivery_method``
        stays unset, ``sent_at`` is NOT rolled back — it now records the
        moment delivery was attempted, whether or not it worked).
        Consequence: a process crash between the CAS commit and either
        the dispatch attempt or the SEND_FAILED follow-up leaves the row
        at status=SENT despite no email ever having gone out. Accepted
        risk — claiming the row only AFTER a successful dispatch would
        reopen the exact double-send race this CAS exists to close, and
        the failure window is mitigated (not eliminated) by the
        SEND_FAILED follow-up + sender-notification path, which still
        fires and lets the goldsmith notice and retry or fall back to a
        manual PDF.

        Raises:
            CustomerUpdateNotFoundError: no such update (404).
            InvalidUpdateStateError: update already SENT, or lost the
                concurrent CAS race described above (409). DRAFT and
                SEND_FAILED may both (re-)attempt delivery.
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

        will_attempt = bool(settings.EMAIL_NOTIFICATIONS_ENABLED and settings.SMTP_HOST)

        if not will_attempt:
            # PDF-only mode — expected, not a failure. Nothing is
            # dispatched, so there is no race to close here; status is
            # left untouched (still DRAFT/SEND_FAILED) so a later send()
            # (once SMTP is configured) can still claim it.
            await db.refresh(update)
            _log_financial_access(
                "send_attempted",
                update_id,
                cast(Optional[int], update.order_id),
                user_id,
                extra={"delivered": False},
            )
            return CustomerUpdateSendResult(
                update=CustomerUpdateRead.model_validate(update),
                delivered=False,
                method=None,
            )

        # CAS claim — see docstring. Runs BEFORE any SMTP dispatch.
        async with transactional(db):
            claim_result = await db.execute(
                sa_update(CustomerUpdate)
                .where(
                    CustomerUpdate.id == update_id,
                    CustomerUpdate.status.in_(
                        [
                            CustomerUpdateStatus.DRAFT,
                            CustomerUpdateStatus.SEND_FAILED,
                        ]
                    ),
                )
                .values(status=CustomerUpdateStatus.SENT, sent_at=datetime.utcnow())
                .returning(CustomerUpdate.id)
            )
            claimed_id = claim_result.scalar_one_or_none()

        if claimed_id is None:
            raise InvalidUpdateStateError(update_id, update.status.value)

        await db.refresh(update)

        if customer is None or not customer.email:
            # A real per-record data gap the sender needs to act on.
            delivered = False
        else:
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
        if delivered:
            async with transactional(db):
                update.delivery_method = cast(Any, UpdateDeliveryMethod.EMAIL)
            method = UpdateDeliveryMethod.EMAIL
        else:
            async with transactional(db):
                update.status = cast(Any, CustomerUpdateStatus.SEND_FAILED)
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
        await write_financial_audit_row(
            db,
            action="list_accessed_financial",
            entity="customer_update",
            entity_id=None,
            order_id=order_id,
            user_id=user_id,
            endpoint=f"/api/v1/orders/{order_id}/updates",
        )
        return updates
