"""Notifications, customer updates, cost-change requests and the outbox."""

import enum
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import relationship

from goldsmith_erp.core.timeutil import utcnow
from goldsmith_erp.db.models.base import MONEY_NUMERIC, Base, SAEnum
from goldsmith_erp.db.types import UtcDateTime


class NotificationTypeEnum(str, enum.Enum):
    """Type of notification — drives icon and routing on the frontend."""

    DEADLINE_WARNING = "deadline_warning"  # Auftrag-Deadline naehert sich
    PICKUP_READY = "pickup_ready"  # Auftrag abholbereit
    LOW_STOCK = "low_stock"  # Material unter Mindestbestand
    FITTING_REMINDER = "fitting_reminder"  # Anprobe-Erinnerung
    ORDER_STATUS = "order_status"  # Auftragsstatus geaendert
    SYSTEM = "system"  # Systemnachricht
    HANDOFF = "handoff"  # Uebergabe zwischen Goldschmiede
    COMMENT = "comment"  # Neuer Kommentar an einem Auftrag
    REPAIR_RECEIVED = "repair_received"  # Reparaturauftrag eingegangen
    REPAIR_READY = "repair_ready"  # Reparatur abholbereit
    BIRTHDAY_REMINDER = "birthday_reminder"
    CONSULTATION_FOLLOWUP = "consultation_followup"  # Beratung: Wiedervorlage fällig
    COST_ALERT = "cost_alert"  # Projizierte Kosten überschreiten Kostenvoranschlag


class NotificationSeverityEnum(str, enum.Enum):
    """Severity level — maps to visual styling (colour, urgency) on the frontend."""

    INFO = "info"
    WARNING = "warning"
    URGENT = "urgent"


class Notification(Base):
    """
    Per-user in-app notification.

    Notifications are always scoped to a single recipient (user_id).
    Real-time delivery is handled via Redis pub/sub on channel
    ``notifications:{user_id}``.  Persistence here allows unread counts
    and notification history to survive browser refreshes.
    """

    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    notification_type = Column(
        SAEnum(NotificationTypeEnum),
        nullable=False,
        index=True,
    )
    severity = Column(
        SAEnum(NotificationSeverityEnum),
        nullable=False,
        default=NotificationSeverityEnum.INFO,
    )

    # Optional contextual links (both nullable — not every notification has one)
    related_order_id = Column(
        Integer,
        ForeignKey("orders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    related_customer_id = Column(
        Integer,
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Read state
    is_read = Column(Boolean, default=False, nullable=False, index=True)
    read_at = Column(UtcDateTime, nullable=True)

    created_at = Column(UtcDateTime, default=utcnow, nullable=False, index=True)

    # Relationships
    user = relationship("User")
    related_order = relationship("Order")
    related_customer = relationship("Customer")


class NotificationPreference(Base):
    """
    Per-user preferences that control which notification types are delivered
    and how far in advance deadline warnings are triggered.
    """

    __tablename__ = "notification_preferences"
    __table_args__ = (
        UniqueConstraint("user_id", "notification_type", name="uq_notification_pref"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    notification_type = Column(SAEnum(NotificationTypeEnum), nullable=False)

    # Whether the user wants this notification type at all
    enabled = Column(Boolean, default=True, nullable=False)

    # For DEADLINE_WARNING: how many days before the deadline to notify
    # (default 3 days; checked on every deadline scan)
    advance_days = Column(Integer, default=3, nullable=False)

    # Relationships
    user = relationship("User")


# ---------------------------------------------------------------------------
# V1.2 Customer Updates & §649 BGB Cost Approval (Kundeninfo & Kostenfreigabe)
# ---------------------------------------------------------------------------


class CustomerUpdateKind(str, enum.Enum):
    """What kind of customer-facing update this is — drives which German
    template renders the default subject/body."""

    PROGRESS = "progress"  # Fortschritts-Update
    COST_CHANGE = "cost_change"  # Kostenänderung (linked to a CostChangeRequest)
    READY_FOR_PICKUP = "ready_for_pickup"  # Abholbereit
    CUSTOM = "custom"  # Freitext, kein Template


class CustomerUpdateStatus(str, enum.Enum):
    """Lifecycle of a CustomerUpdate: draft -> sent | send_failed."""

    DRAFT = "draft"  # Entwurf, editierbar, noch nicht verschickt
    SENT = "sent"  # Erfolgreich verschickt (Email oder als PDF markiert)
    SEND_FAILED = "send_failed"  # SMTP-Versand fehlgeschlagen — nie stillschweigend


class UpdateDeliveryMethod(str, enum.Enum):
    """How a CustomerUpdate actually reached the customer."""

    EMAIL = "email"  # Via EmailService (aiosmtplib)
    PDF_MANUAL = "pdf_manual"  # PDF heruntergeladen, Goldschmiedin hat es selbst verschickt (WhatsApp etc.)


class CostChangeStatus(str, enum.Enum):
    """Change-order lifecycle for a CostChangeRequest (§649 BGB Anzeigepflicht).

    draft -> sent -> approved | declined; sent -> superseded when a newer
    request for the same order is created before the customer responds.
    """

    DRAFT = "draft"  # Entwurf, noch nicht an Kundin geschickt
    SENT = "sent"  # Verschickt, wartet auf Antwort der Kundin
    APPROVED = "approved"  # Kundin hat zugestimmt (Nachweis erfasst)
    DECLINED = "declined"  # Kundin hat abgelehnt (Nachweis erfasst)
    SUPERSEDED = "superseded"  # Durch neuere Anfrage für denselben Auftrag ersetzt


class CostChangeResponseMethod(str, enum.Enum):
    """How the customer's approval/decline of a CostChangeRequest was captured.

    This is evidence logging, not click-tracking — the goldsmith records how
    the customer actually responded (research doc §3: change-order pattern).
    """

    EMAIL_REPLY = "email_reply"  # Kundin hat per Email geantwortet
    IN_PERSON = "in_person"  # Mündlich vor Ort zugestimmt/abgelehnt
    PHONE = "phone"  # Telefonisch zugestimmt/abgelehnt


class CustomerUpdate(Base):
    """Kundeninfo — a progress/cost-change/pickup update sent to a customer.

    Attaches to EITHER an Order OR a RepairJob (exactly one of order_id /
    repair_job_id must be set) — enforced at the Pydantic layer
    (``models/customer_update.py``, Task 2), NOT via a DB CheckConstraint:
    ``models.py`` has no existing CheckConstraint precedent to follow (grepped
    for Task 1), so a DB-level constraint would be a first-of-its-kind
    addition. Documented decision: skip it here: the Pydantic validation on
    the create path is the only write path (no direct-ORM construction route
    exists for this table outside tests), so app-layer enforcement is
    sufficient — matching this repo's general "trust the service layer,
    Pydantic validates" convention for FK-choice invariants.

    ``body`` is free customer-facing text (design-IP adjacent, e.g. quoted
    progress notes) — GDPR scrub target via the ``order_id``/``repair_job_id``
    link (Task 6). ``photo_ids`` holds ONLY explicitly-selected OrderPhoto
    UUIDs — design-IP rule: nothing is ever auto-shared.

    ``token`` is a portal-ready opaque handle (unused by V1.2 emails except
    as a reference id) so a future hosted portal can render identical content
    without a data-model change (spec: "Decision context: no live portal").

    FK deletion semantics: ``order_id``/``repair_job_id`` use ``SET NULL``
    (not CASCADE) — sent updates are outbound-correspondence records kept as
    skeleton rows for Art. 30 accountability even when the linked order/
    repair is hard-deleted (spec GDPR section: "skeleton rows kept for
    Art. 30 / financial audit — same pattern as invoice retention"; matches
    ``Quote.order_id``'s nullable-link precedent). GDPR erasure scrubs the
    free-text content (Task 6), it does not delete the rows.
    """

    __tablename__ = "customer_updates"
    # C2.2: DB backstop for the automated customer-mail dedupe
    # (services/automated_customer_email.py). Automated rows carry a
    # ``dedupe_key``; at most one live (draft/sent) row per key, so two
    # concurrent monitor ticks cannot both email the customer. Failed sends
    # are excluded so the next day's retry can insert a new row. Staff-written
    # Kundeninfo has no key and is unrestricted.
    # Migration: 20260925_c22_cu_dedupe.
    __table_args__ = (
        Index(
            "uq_customer_updates_dedupe_key",
            "dedupe_key",
            unique=True,
            postgresql_where=text("dedupe_key IS NOT NULL AND status <> 'send_failed'"),
            sqlite_where=text("dedupe_key IS NOT NULL AND status <> 'send_failed'"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    # Set only by the automated sender, e.g. "auto:order:12:pickup_ready".
    dedupe_key = Column(String(200), nullable=True)

    # Exactly one of these two must be set — Pydantic-layer invariant, see
    # class docstring. SET NULL, not CASCADE — Art. 30 retention, see
    # docstring.
    order_id = Column(
        Integer, ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    repair_job_id = Column(
        Integer,
        ForeignKey("repair_jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    kind = Column(SAEnum(CustomerUpdateKind), nullable=False)
    subject = Column(String(300), nullable=False)
    body = Column(Text, nullable=False)  # scrub target — user free-text

    # Only explicitly selected photos — list[str] of OrderPhoto UUIDs.
    photo_ids = Column(JSON, nullable=True)

    cost_change_request_id = Column(
        Integer,
        ForeignKey("cost_change_requests.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Portal-ready handle — uuid4 hex, unique + indexed.
    token = Column(
        String(64),
        unique=True,
        nullable=False,
        index=True,
        default=lambda: uuid.uuid4().hex,
    )

    status = Column(
        SAEnum(CustomerUpdateStatus),
        nullable=False,
        default=CustomerUpdateStatus.DRAFT,
        index=True,
    )
    sent_at = Column(UtcDateTime, nullable=True)
    # Set at draft-creation time to the acting user (no separate created_by
    # column on this table) — remains the record's owning user even before
    # sent_at is populated.
    sent_by = Column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    delivery_method = Column(SAEnum(UpdateDeliveryMethod), nullable=True)

    created_at = Column(UtcDateTime, default=utcnow, nullable=False, index=True)
    updated_at = Column(UtcDateTime, default=utcnow, onupdate=utcnow, nullable=False)

    # Relationships
    order = relationship("Order")
    repair_job = relationship("RepairJob")
    cost_change_request = relationship(
        "CostChangeRequest", foreign_keys=[cost_change_request_id]
    )
    sent_by_user = relationship("User", foreign_keys=[sent_by])

    def __repr__(self) -> str:
        return (
            f"<CustomerUpdate {self.id} kind={self.kind.value} "
            f"status={self.status.value}>"
        )


class CostChangeRequest(Base):
    """§649 BGB cost-change request — change-order style approval record.

    Approval is evidence logging, not click-tracking: the customer replies
    to the email (or approves in person/by phone) and the goldsmith records
    it via ``record_response`` (Task 5). ``reason``/``response_evidence`` are
    GDPR scrub targets via the ``order_id`` link (Task 6). Financial data —
    ADMIN/GOLDSMITH only, all access audit-logged.

    FK deletion semantics: ``order_id`` uses ``ondelete="RESTRICT"`` — an
    approved/declined cost change is the §649 BGB approval evidence and a
    financial record with Art. 30 retention duties, so it must block a hard
    delete of its order exactly like ``Invoice.order_id`` does (the spec's
    "same pattern as invoice retention"). GDPR erasure scrubs the free-text
    fields (Task 6), it never deletes the rows.
    """

    __tablename__ = "cost_change_requests"

    id = Column(Integer, primary_key=True, index=True)
    # RESTRICT, not CASCADE — financial-retention backstop, see docstring.
    order_id = Column(
        Integer,
        ForeignKey("orders.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    quote_id = Column(
        Integer, ForeignKey("quotes.id", ondelete="SET NULL"), nullable=True, index=True
    )

    original_amount = Column(MONEY_NUMERIC, nullable=False)  # Kostenvoranschlag-Betrag
    new_amount = Column(
        MONEY_NUMERIC, nullable=False
    )  # Neuer, voraussichtlicher Betrag
    delta_percent = Column(MONEY_NUMERIC, nullable=False)  # Computed at creation

    reason = Column(Text, nullable=False)  # scrub target — legally relevant Begründung
    # [{"label": str, "amount": float, "kind": "add"|"remove"|"change"}]
    line_items = Column(JSON, nullable=True)

    status = Column(
        SAEnum(CostChangeStatus),
        nullable=False,
        default=CostChangeStatus.DRAFT,
        index=True,
    )
    response_method = Column(SAEnum(CostChangeResponseMethod), nullable=True)
    response_evidence = Column(Text, nullable=True)  # scrub target
    responded_at = Column(UtcDateTime, nullable=True)
    recorded_by = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    created_at = Column(UtcDateTime, default=utcnow, nullable=False, index=True)
    created_by = Column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    updated_at = Column(UtcDateTime, default=utcnow, onupdate=utcnow, nullable=False)

    # At-most-one-SENT-per-order invariant (security re-review fix): the
    # DB-level partial unique index is the REAL §649 single-live-notice
    # guarantee — the service-level supersede + CAS in
    # ``CostChangeService.send()`` cannot close the cross-row race under
    # READ COMMITTED (two concurrent sends of two DIFFERENT drafts each
    # see no SENT sibling in their snapshot, so neither's FOR UPDATE scan
    # locks anything). 'sent' (lowercase) matches the stored enum VALUE
    # (SAEnum uses values_callable). Named identically to the index
    # created by alembic/versions/20260703_v12a_customer_updates.py so
    # ``Base.metadata.create_all()`` (unit-test DBs) and
    # ``alembic upgrade head`` (real deployments) produce the same shape
    # (uq_customer_no_gos_customer_value_hash precedent).
    __table_args__ = (
        Index(
            "uq_cost_change_one_sent_per_order",
            "order_id",
            unique=True,
            postgresql_where=text("status = 'sent'"),
            sqlite_where=text("status = 'sent'"),
        ),
    )

    # Relationships
    order = relationship("Order")
    quote = relationship("Quote")
    recorded_by_user = relationship("User", foreign_keys=[recorded_by])
    created_by_user = relationship("User", foreign_keys=[created_by])

    def __repr__(self) -> str:
        return (
            f"<CostChangeRequest {self.id} order={self.order_id} "
            f"status={self.status.value}>"
        )


Index("ix_notifications_user_read", Notification.user_id, Notification.is_read)


# ============================================================================
# OUTBOX (ARCH-04 / ARCH-05, ADR-2026-09-25-outbox)
# ============================================================================


class OutboxStatus(str, enum.Enum):
    """Lifecycle of an outbox row: pending -> sent | failed -> ... | dead."""

    PENDING = "pending"  # waiting for its first attempt
    SENT = "sent"  # delivered (SMTP accepted)
    FAILED = "failed"  # last attempt failed, will be retried at next_attempt_at
    DEAD = "dead"  # gave up after OUTBOX_MAX_ATTEMPTS; needs an admin retry


OUTBOX_STATUS_VALUES = tuple(s.value for s in OutboxStatus)


class OutboxMessage(Base):
    """Durable side-effect job written in the same transaction as the change.

    ``payload`` carries ids only (never recipient, subject or body): the
    worker re-loads the business rows when it sends, so PII stays encrypted
    in its own tables and an erasure also empties pending messages.
    """

    __tablename__ = "outbox_messages"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'sent', 'failed', 'dead')",
            name="ck_outbox_messages_status",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    kind = Column(String(50), nullable=False)
    payload = Column(JSON, nullable=False, default=dict)
    dedupe_key = Column(String(200), nullable=True, unique=True)
    status = Column(String(20), nullable=False, default=OutboxStatus.PENDING.value)
    attempts = Column(Integer, nullable=False, default=0)
    next_attempt_at = Column(UtcDateTime, nullable=False, default=utcnow)
    last_error = Column(String(500), nullable=True)
    created_at = Column(UtcDateTime, nullable=False, default=utcnow)
    sent_at = Column(UtcDateTime, nullable=True)


Index(
    "ix_outbox_messages_status_next_attempt",
    OutboxMessage.status,
    OutboxMessage.next_attempt_at,
)
