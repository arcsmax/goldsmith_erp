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

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, cast

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.core.config import settings
from goldsmith_erp.db.models import (
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
    CustomerUpdateSendResult,
)
from goldsmith_erp.services.customer_message_service import (
    CustomerMessageService,
    MessageKind,
    load_photo_attachments,
    message_kind_for,
    resolve_recipient,
)
from goldsmith_erp.services.job_service import JobService
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


class DuplicateDedupeKeyError(ValueError):
    """
    A LIVE ``customer_updates`` row already carries this ``dedupe_key``
    (C2.2 partial unique index) — a concurrent automated-sender run
    already claimed (or already sent) this exact occurrence.

    Raised from INSIDE a SAVEPOINT (``db.begin_nested()``) rather than
    letting the underlying ``IntegrityError`` reach ``transactional()``'s
    catch-all: ``Session.rollback()`` (what that generic handler calls)
    always rolls back to the ROOT transaction and expires every object in
    the session (SQLAlchemy invariant — see ``Session.rollback()``'s
    ``_to_root=True``), which would leave the caller (e.g.
    ``automated_customer_email._create_and_send``, which still holds the
    ``Order`` it was passed) with expired attributes that raise
    ``MissingGreenlet`` on the next plain (non-awaited) attribute access.
    A SAVEPOINT-scoped rollback only reverts this insert.
    """

    def __init__(self, dedupe_key: str) -> None:
        super().__init__(f"dedupe_key {dedupe_key!r} already claimed by a live row")
        self.dedupe_key = dedupe_key


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
            "timestamp": datetime.now(timezone.utc).isoformat(),
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
    http_method: str = "GET",
    repair_job_id: Optional[int] = None,
) -> None:
    """
    Persist a ``CustomerAuditLog`` row for a financial-data access that
    ``AuditLoggingMiddleware`` cannot (fully) key on — either because it
    is a GET under a first-path-segment the middleware doesn't recognize
    (see that middleware's ``_RESOURCE_ROUTES`` comment on the
    ``/orders/{id}/...`` blind spot), or because it is a non-GET under a
    financial family, which the middleware's ``is_financial`` GET-only
    gate structurally skips (e.g. ``POST /estimates/labor`` — see
    ``api/routers/estimator.py``).

    Mirrors ``AuditLoggingMiddleware._log_to_database``'s row shape:
    same ``action`` naming convention (``list_accessed_financial`` /
    ``financial_read``), same legal-basis / purpose derivation, and the
    same ``details`` JSON keys (``endpoint``, ``http_method``,
    ``legal_basis``, ``purpose``) — minus ``status_code``/``duration_ms``,
    which the middleware measures around the whole request and are not
    available at this call depth; this is only ever invoked once the
    underlying operation has already succeeded, so a 200/201 is implied.
    ``http_method`` defaults to ``"GET"`` (every call site before V1.3
    Task 5 was a GET); pass ``http_method="POST"`` explicitly for a
    non-GET call site so the audit row's ``details`` reflect the real
    verb instead of a stale hardcoded one.

    ``customer_id`` is derived from the order or, when ``order_id`` is
    unset, from ``repair_job_id`` (W2-02: repair-scoped Kundeninfo access,
    e.g. ``CustomerUpdateService.list_for_repair``) — never from the
    caller (CLAUDE.md: financial-data audit rows must be traceable to the
    customer; a caller supplying the wrong id here would silently
    mis-attribute the row, so this method does its own lookup rather than
    trusting a passed-in value). Both unset (e.g. a prospective labor
    estimate with no associated order yet) is a valid input —
    ``customer_id`` simply stays ``None``.

    Fire-and-forget, mirroring the middleware's own broad except: a DB
    outage on the audit path must never deny (or 500) the legitimate
    operation it is auditing (security > correctness > convenience, but
    here "correctness of the response" outranks "completeness of the
    audit trail" — the exact same tradeoff the middleware documents for
    its own write). Failures are logged loudly instead of swallowed.
    """
    customer_id: Optional[int] = None
    if order_id is not None:
        order = (
            await db.execute(select(Order).where(Order.id == order_id))
        ).scalar_one_or_none()
        if order is not None:
            customer_id = cast(Optional[int], order.customer_id)
    elif repair_job_id is not None:
        repair = (
            await db.execute(select(RepairJob).where(RepairJob.id == repair_job_id))
        ).scalar_one_or_none()
        if repair is not None:
            customer_id = cast(Optional[int], repair.customer_id)

    details = {
        "endpoint": endpoint,
        "http_method": http_method,
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
            timestamp=datetime.now(timezone.utc),
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


# Target resolution, photo loading and the actual dispatch live in
# ``customer_message_service`` (W6-01): it is the single way a customer
# message leaves the system. This module keeps the draft lifecycle.


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
        dedupe_key: Optional[str] = None,
        message_kind: Optional[MessageKind] = None,
    ) -> CustomerUpdate:
        """
        Create a DRAFT CustomerUpdate for exactly one target.

        W6: the content rules of ``CustomerMessageService.check_content``
        run before the insert (photos need PHOTO_USE consent, no prices
        outside quote/cost-change). ``message_kind`` overrides the kind
        derived from ``data.kind`` + photos (e.g. ``QUOTE_SENT``).

        ``dedupe_key`` is set only by the automated sender (C2.2); a second
        LIVE row with the same key raises ``DuplicateDedupeKeyError`` (the
        partial unique index ``uq_customer_updates_dedupe_key`` rejects the
        insert; see that exception's docstring for why it is raised from
        inside a SAVEPOINT instead of a bare ``IntegrityError``).

        Raises:
            ValueError: target (order/repair) does not exist, or exactly-one
                invariant is violated (both/neither id supplied — router bug
                guard, not expected from real callers).
            InvalidUpdatePhotoError / PhotosNotAllowedForRepairError /
                MissingCustomerUpdateContentError /
                CostChangeKindNotAllowedError: malformed input (422).
            CustomerMessageError: consent / price rule violated (422).
            DuplicateDedupeKeyError: ``dedupe_key`` collided with a live row
                (automated-sender path only).
        """
        if (order_id is None) == (repair_job_id is None):
            raise ValueError("Exakt eines von order_id/repair_job_id muss gesetzt sein")

        if data.kind == CustomerUpdateKind.COST_CHANGE:
            # cost_change updates are only created internally by
            # CostChangeService.send() — see the exception's docstring.
            raise CostChangeKindNotAllowedError()

        order_ref: str
        customer_id: Optional[int]
        if order_id is not None:
            order = (
                await db.execute(select(Order).where(Order.id == order_id))
            ).scalar_one_or_none()
            if order is None:
                raise ValueError(f"Auftrag #{order_id} nicht gefunden")
            order_ref = cast(Optional[str], order.title) or f"Auftrag #{order.id}"
            customer_id = cast(Optional[int], order.customer_id)

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
            customer_id = cast(Optional[int], repair.customer_id)

            if data.photo_ids:
                raise PhotosNotAllowedForRepairError()

        subject = data.subject
        body = data.body
        if subject is None or body is None:
            default_subject, default_body = _default_subject_body(data.kind, order_ref)
            subject = subject or default_subject
            body = body or default_body

        await CustomerMessageService.check_content(
            db,
            kind=message_kind or message_kind_for(data.kind, bool(data.photo_ids)),
            customer_id=customer_id,
            subject=subject,
            body=body,
            photo_ids=data.photo_ids,
        )

        # ARCH phase 5: the update also names its job.
        job_id = await JobService.job_id_for(
            db, order_id=order_id, repair_job_id=repair_job_id
        )
        update = CustomerUpdate(
            order_id=order_id,
            repair_job_id=repair_job_id,
            job_id=job_id,
            kind=data.kind,
            subject=subject,
            body=body,
            photo_ids=data.photo_ids or None,
            status=CustomerUpdateStatus.DRAFT,
            sent_by=user_id,
            dedupe_key=dedupe_key,
        )

        if dedupe_key is not None:
            # Automated-sender path (C2.2) — see DuplicateDedupeKeyError's
            # docstring for why this insert is scoped to its OWN SAVEPOINT
            # instead of going through transactional(): a collision here is
            # an expected, routine outcome (a concurrent tick), not the
            # unexpected-error case transactional()'s broad except/rollback
            # is designed for, and that broad rollback would expire every
            # object in the caller's session.
            try:
                async with db.begin_nested():
                    db.add(update)
                    await db.flush()
                await db.commit()
            except IntegrityError as exc:
                # The nested block above already rolled back to the
                # SAVEPOINT (session + all other objects are untouched);
                # nothing further to undo here.
                raise DuplicateDedupeKeyError(dedupe_key) from exc
        else:
            async with transactional(db):
                db.add(update)

        await db.refresh(update)
        _log_financial_access("draft_created", cast(int, update.id), order_id, user_id)
        return update

    # ------------------------------------------------------------------
    # Send
    # ------------------------------------------------------------------

    @staticmethod
    async def send(
        db: AsyncSession,
        update_id: int,
        user_id: int,
        *,
        attach_status_report: bool = False,
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
            CustomerMessageError: photos without PHOTO_USE consent or a
                price in a kind that must not carry one (422).
        """
        # W6-01: the dispatch (content rules, opt-out, CAS claim, SMTP,
        # audit row) lives in CustomerMessageService, the single outbound
        # path for customer messages.
        return await CustomerMessageService.send_update(
            db, update_id, user_id, attach_status_report=attach_status_report
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

        recipient = await resolve_recipient(
            db,
            order_id=cast(Optional[int], update.order_id),
            repair_job_id=cast(Optional[int], update.repair_job_id),
        )
        photo_ids = cast(Optional[List[str]], update.photo_ids) or []
        # The PDF reaches the customer too: same consent / price rules.
        await CustomerMessageService.check_content(
            db,
            kind=message_kind_for(
                cast(CustomerUpdateKind, update.kind), bool(photo_ids)
            ),
            customer_id=recipient.customer_id,
            subject=cast(str, update.subject),
            body=cast(str, update.body),
            photo_ids=photo_ids,
        )
        photos = await load_photo_attachments(
            db, cast(Optional[int], update.order_id), photo_ids
        )

        # CPU-bound (fpdf2 font subsetting + drawing) — offloaded to a
        # thread so a PDF render never blocks the event loop on this
        # request path (review fix, ml.py asyncio.to_thread precedent).
        return await asyncio.to_thread(
            PDFService.render_customer_update_pdf,
            update=update,
            order_ref=recipient.order_ref,
            customer_name=recipient.display_name,
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
            update.sent_at = cast(Any, datetime.now(timezone.utc))
            update.delivery_method = cast(Any, method)
            # E16: the PDF reached the customer; one audit row per message.
            await CustomerMessageService.record_manual_delivery(db, update, user_id)

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

    @staticmethod
    async def list_for_repair(
        db: AsyncSession, repair_job_id: int, user_id: int
    ) -> List[CustomerUpdate]:
        """
        Update history for a repair job, newest first (W2-02) — mirrors
        ``list_for_order``. In practice this is usually a single row (the
        pickup-ready draft created by ``RepairService.complete_repair``),
        since a repair's status machine only reaches READY once.
        """
        result = await db.execute(
            select(CustomerUpdate)
            .where(CustomerUpdate.repair_job_id == repair_job_id)
            .order_by(CustomerUpdate.created_at.desc())
        )
        updates = list(result.scalars().all())
        _log_financial_access("list_accessed", None, None, user_id)
        await write_financial_audit_row(
            db,
            action="list_accessed_financial",
            entity="customer_update",
            entity_id=None,
            order_id=None,
            repair_job_id=repair_job_id,
            user_id=user_id,
            endpoint=f"/api/v1/repairs/{repair_job_id}/customer-updates",
        )
        return updates
