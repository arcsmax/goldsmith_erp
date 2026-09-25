"""Models not yet moved to a domain module."""

import enum
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    event,
    text,
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import relationship

from goldsmith_erp.core.timeutil import utcnow
from goldsmith_erp.db.models.base import MONEY_NUMERIC, Base, SAEnum
from goldsmith_erp.db.models.orders import OrderTypeEnum
from goldsmith_erp.db.types import EncryptedString, UtcDateTime, UtcDateTimeNaiveStorage


class CalendarEventType(str, enum.Enum):
    """Event types for the calendar/planning system."""

    ORDER_DEADLINE = "order_deadline"
    WORKSHOP_TASK = "workshop_task"
    APPOINTMENT = "appointment"
    REMINDER = "reminder"


class CalendarEvent(Base):
    """
    Calendar events for workshop planning.

    Covers manual events (appointments, reminders, tasks) as well as
    system-generated entries (order_deadline type is created on-the-fly from
    Order.deadline and is NOT stored here — use CalendarService.get_order_deadlines
    for those).
    """

    __tablename__ = "calendar_events"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    event_type = Column(
        SAEnum(CalendarEventType),
        nullable=False,
        default=CalendarEventType.WORKSHOP_TASK,
        index=True,
    )

    # Time range
    start_datetime = Column(UtcDateTime, nullable=False, index=True)
    end_datetime = Column(UtcDateTime, nullable=True)
    all_day = Column(Boolean, default=False, nullable=False)

    # Optional link to an order
    order_id = Column(
        Integer,
        ForeignKey("orders.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Owner / creator
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Visual styling
    color = Column(String(7), nullable=True)  # Hex color, e.g. "#FF6B6B"

    # Simple recurrence note (free-text, not a full RFC 5545 implementation)
    recurrence = Column(String(100), nullable=True)  # e.g. "weekly", "monthly"

    # Metadata
    created_at = Column(UtcDateTime, default=utcnow, nullable=False)
    updated_at = Column(
        UtcDateTime,
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )

    # Relationships
    order = relationship("Order")
    user = relationship("User")


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


# ============================================================================
# REPAIR TRACKING (REPARATURVERWALTUNG)
# ============================================================================


class RepairJobStatus(str, enum.Enum):
    """
    Lifecycle states for a repair job.

    Follows the physical flow through the workshop:
    Eingang -> Diagnose -> Angebot -> Genehmigt -> Reparatur ->
    Qualitaetskontrolle -> Abholbereit -> Abgeholt | Storniert
    """

    RECEIVED = "received"  # Eingang — Stueck angenommen
    DIAGNOSED = "diagnosed"  # Diagnose — Fehler festgestellt
    QUOTED = "quoted"  # Angebot erstellt, wartet auf Kundenzusage
    APPROVED = "approved"  # Kunde hat Angebot genehmigt
    IN_REPAIR = "in_repair"  # Reparatur laeuft
    QUALITY_CHECK = "quality_check"  # Qualitaetskontrolle
    READY = "ready"  # Abholbereit
    PICKED_UP = "picked_up"  # Abgeholt
    CANCELLED = "cancelled"  # Storniert


class RepairItemType(str, enum.Enum):
    """Type of jewelry item being repaired."""

    RING = "ring"  # Ring
    CHAIN = "chain"  # Kette
    BRACELET = "bracelet"  # Armband
    EARRING = "earring"  # Ohrringe
    WATCH = "watch"  # Uhr
    BROOCH = "brooch"  # Brosche
    OTHER = "other"  # Sonstiges


class RepairPhotoPhase(str, enum.Enum):
    """Phase during which a repair photo was taken."""

    INTAKE = "intake"  # Eingang — Zustand bei Annahme
    DURING_REPAIR = "during_repair"  # Waehrend der Reparatur
    COMPLETED = "completed"  # Fertig — Ergebnis


class RepairJob(Base):
    """
    Reparaturauftrag — repair order for an existing piece of jewelry.

    Repair jobs are distinct from production orders (Order table):
    - They have a physical bag/envelope with a number for physical tracking
    - They go through an estimate → approval workflow before work begins
    - Customer notification events (REPAIR_RECEIVED, REPAIR_READY) are tracked
    - Estimated and actual costs are both recorded for Nachkalkulation
    """

    __tablename__ = "repair_jobs"

    id = Column(Integer, primary_key=True, index=True)

    # Repair number: REP-YYYY-NNNN (unique, auto-generated)
    repair_number = Column(String(20), unique=True, nullable=False, index=True)

    # Physical bag/envelope number for workshop floor tracking
    # (piece sits in a numbered paper tray until pickup)
    bag_number = Column(String(20), nullable=False, index=True)

    # Links
    customer_id = Column(
        Integer,
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    received_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Item details
    item_description = Column(Text, nullable=False)
    item_type = Column(
        SAEnum(RepairItemType), nullable=False, default=RepairItemType.OTHER
    )
    metal_type = Column(
        String(50), nullable=True
    )  # Free text: "585 Gelbgold", "Silber 925"
    estimated_value = Column(
        MONEY_NUMERIC, nullable=True
    )  # Versicherungswert des Stuecks in EUR

    # Status
    status = Column(
        SAEnum(RepairJobStatus),
        nullable=False,
        default=RepairJobStatus.RECEIVED,
        index=True,
    )

    # Diagnosis & cost
    diagnosis_notes = Column(Text, nullable=True)
    estimated_cost = Column(MONEY_NUMERIC, nullable=True)  # Kostenvoranschlag in EUR
    actual_cost = Column(
        MONEY_NUMERIC, nullable=True
    )  # Tatsaechliche Kosten nach Reparatur

    # Dates
    estimated_completion_date = Column(UtcDateTime, nullable=True, index=True)
    actual_completion_date = Column(UtcDateTime, nullable=True)
    customer_notified_at = Column(
        UtcDateTime, nullable=True
    )  # When READY notification was sent
    picked_up_at = Column(UtcDateTime, nullable=True)

    # Soft delete (30-day grace period before hard delete per GDPR Art. 17)
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    deleted_at = Column(UtcDateTime, nullable=True)

    # Audit timestamps
    created_at = Column(UtcDateTime, default=utcnow, nullable=False, index=True)
    updated_at = Column(UtcDateTime, default=utcnow, onupdate=utcnow, nullable=False)

    # V1.1 — Eingangs-Checkliste (repair photo-intake checklist). Seeded from
    # settings.REPAIR_INTAKE_CHECKLIST at creation; item shape documented in
    # models.repair.IntakeChecklistItem (not enforced by the DB), e.g.
    # {"key": str, "label": str, "status": "open"|"photo"|"na",
    #  "photo_id": int|None, "na_reason": str|None}. Mirrors
    # Customer.style_profile's JSON-column pattern.
    intake_checklist = Column(JSON, nullable=True)

    # Relationships
    customer = relationship("Customer")
    received_by_user = relationship("User", foreign_keys=[received_by])
    photos = relationship(
        "RepairPhoto",
        back_populates="repair_job",
        cascade="all, delete-orphan",
        order_by="RepairPhoto.timestamp.asc()",
    )

    def __repr__(self) -> str:
        return (
            f"<RepairJob {self.repair_number} "
            f"status={self.status.value} "
            f"bag={self.bag_number}>"
        )


class RepairPhoto(Base):
    """
    Foto-Dokumentation fuer Reparaturauftraege.

    Photos are grouped by phase (INTAKE / DURING_REPAIR / COMPLETED) so the
    customer can see before/after documentation and the workshop has a visual
    audit trail for each step.
    """

    __tablename__ = "repair_photos"

    id = Column(Integer, primary_key=True, index=True)
    repair_job_id = Column(
        Integer,
        ForeignKey("repair_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    phase = Column(
        SAEnum(RepairPhotoPhase), nullable=False, default=RepairPhotoPhase.INTAKE
    )
    file_path = Column(String(500), nullable=False)
    timestamp = Column(UtcDateTime, default=utcnow, nullable=False, index=True)
    taken_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    notes = Column(Text, nullable=True)

    # Relationships
    repair_job = relationship("RepairJob", back_populates="photos")
    taken_by_user = relationship("User", foreign_keys=[taken_by])

    def __repr__(self) -> str:
        return f"<RepairPhoto repair={self.repair_job_id} " f"phase={self.phase.value}>"


# ---------------------------------------------------------------------------
# V1.1 Consultation & Intake (Beratung & Annahme)
# ---------------------------------------------------------------------------


class ConsultationStatus(str, enum.Enum):
    """Lifecycle of a consultation (Beratungsgespräch)."""

    DRAFT = "draft"  # Laufende/unterbrochene Beratung — auto-save target
    COMPLETED = "completed"  # Beratung abgeschlossen, noch nicht konvertiert
    CONVERTED = "converted"  # In Auftrag oder Kostenvoranschlag überführt
    ARCHIVED = "archived"  # Nicht weiterverfolgt


class ConsultationOccasion(str, enum.Enum):
    """Anlass des Schmuckwunsches."""

    ENGAGEMENT = "engagement"
    WEDDING = "wedding"
    ANNIVERSARY = "anniversary"
    BIRTHDAY = "birthday"
    SELF = "self"  # Selbstkauf
    REDESIGN = "redesign"  # Umarbeitung
    REPAIR_CONSULT = "repair_consult"
    OTHER = "other"


class ConsultationPhotoKind(str, enum.Enum):
    """Art eines Beratungsfotos."""

    SKETCH = "sketch"  # Foto der Papierskizze
    REFERENCE = "reference"  # Referenz-/Inspirationsbild des Kunden
    INSPIRATION = "inspiration"
    EXISTING_PIECE = "existing_piece"  # Mitgebrachtes Stück (z. B. Erbstück)


class NoGoCategory(str, enum.Enum):
    """Kategorie eines Kunden-No-Gos."""

    METAL = "metal"
    STONE = "stone"
    FINISH = "finish"
    DESIGN_ELEMENT = "design_element"
    ALLERGY = "allergy"
    OTHER = "other"


class Consultation(Base):
    """Beratungsgespräch — strukturierte Aufnahme eines Schmuckwunsches.

    Wishes/notes/photos are design IP: GOLDSMITH/ADMIN access only.
    budget_min/budget_max are financial data (ADMIN/GOLDSMITH, audit-logged).
    """

    __tablename__ = "consultations"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(
        Integer,
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    conducted_by = Column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    calendar_event_id = Column(
        Integer, ForeignKey("calendar_events.id", ondelete="SET NULL"), nullable=True
    )
    occasion = Column(
        SAEnum(ConsultationOccasion),
        nullable=False,
        default=ConsultationOccasion.OTHER,
    )
    occasion_date = Column(Date, nullable=True)
    budget_min = Column(
        MONEY_NUMERIC, nullable=True
    )  # Finanzdaten — Sichtbarkeitsregeln!
    budget_max = Column(MONEY_NUMERIC, nullable=True)
    piece_type = Column(SAEnum(OrderTypeEnum), nullable=True)
    wishes = Column(Text, nullable=True)  # Design-IP
    materials_discussed = Column(JSON, nullable=True)  # [{"metal": "gold_585", ...}]
    source_material = Column(Text, nullable=True)  # Altgold/Erbstück des Kunden
    status = Column(
        SAEnum(ConsultationStatus),
        nullable=False,
        default=ConsultationStatus.DRAFT,
        index=True,
    )
    converted_quote_id = Column(
        Integer, ForeignKey("quotes.id", ondelete="SET NULL"), nullable=True
    )
    converted_order_id = Column(
        Integer, ForeignKey("orders.id", ondelete="SET NULL"), nullable=True
    )
    follow_up_at = Column(UtcDateTime, nullable=True)
    notes = Column(Text, nullable=True)  # Design-IP
    created_at = Column(UtcDateTime, default=utcnow, nullable=False, index=True)
    updated_at = Column(UtcDateTime, default=utcnow, onupdate=utcnow, nullable=False)

    customer = relationship("Customer")
    goldsmith = relationship("User", foreign_keys=[conducted_by])
    photos = relationship(
        "ConsultationPhoto",
        back_populates="consultation",
        cascade="all, delete-orphan",
        order_by="ConsultationPhoto.timestamp.asc()",
    )

    def __repr__(self) -> str:
        return f"<Consultation {self.id} customer={self.customer_id} status={self.status.value}>"


class ConsultationPhoto(Base):
    """Skizzen-/Referenzfoto einer Beratung. Cloned from OrderPhoto conventions."""

    __tablename__ = "consultation_photos"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    consultation_id = Column(
        Integer,
        ForeignKey("consultations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Set on conversion so the bench sees the sketch on the order (spec: link, not copy).
    order_id = Column(
        Integer, ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    kind = Column(
        SAEnum(ConsultationPhotoKind),
        nullable=False,
        default=ConsultationPhotoKind.SKETCH,
    )
    file_path = Column(String(500), nullable=False)
    timestamp = Column(UtcDateTime, default=utcnow, index=True)
    taken_by = Column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    notes = Column(Text)

    consultation = relationship("Consultation", back_populates="photos")
    user = relationship("User")


class CustomerNoGo(Base):
    """Persistentes Kunden-No-Go (z. B. 'kein Nickel'). Warn-Quelle für Aufträge.

    ``value``/``note`` are health-adjacent PII (allergies live here — this
    table is the source of truth, the legacy ``Customer.allergies`` mirror
    is a read-compat sync target, see ``no_go_service._sync_legacy_
    allergies``) and are encrypted at rest via ``EncryptedString``, same
    C1 pattern as the ``Customer`` PII columns (``db/types.py``).

    Because Fernet ciphertext is non-deterministic, ``value`` itself can't
    carry the duplicate-detection unique constraint. ``value_hash`` is the
    HMAC-SHA-256 blind-index tag (see
    ``core.encryption.no_go_value_blind_index``) over
    ``"<category>:<value.strip().casefold()>"`` — composite because a
    no-go is only a duplicate when BOTH category and (casefolded) value
    match. This replaces the previous functional index on
    ``(customer_id, category, lower(value))``: that index (a) could never
    have worked once ``value`` became ciphertext (SQL ``lower()`` over a
    Fernet token is meaningless), and (b) used SQL ``lower()``, whose
    normalisation silently diverged from the app-side Python
    ``casefold()`` compare (e.g. 'Straße' vs 'STRASSE' collide app-side,
    NOT at that index) — casefold-everywhere closes both gaps at once.
    """

    __tablename__ = "customer_no_gos"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(
        Integer,
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category = Column(SAEnum(NoGoCategory), nullable=False)
    value = Column(EncryptedString, nullable=False)
    # HMAC-SHA-256 blind-index tag over "<category>:<casefolded value>" —
    # see core.encryption.no_go_value_blind_index and the class docstring.
    # Populated by the before_insert/before_update hooks below whenever the
    # caller (NoGoService.add_no_go) hasn't already set it explicitly —
    # exact mirror of Customer.email_hash's event-hook pattern.
    value_hash = Column(String(64), nullable=False, index=True)
    note = Column(EncryptedString, nullable=True)
    source_consultation_id = Column(
        Integer, ForeignKey("consultations.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(UtcDateTime, default=utcnow, nullable=False)

    # DB-level backstop for the app-side duplicate check in
    # NoGoService.add_no_go (issue #12 — closes the duplicate TOCTOU: that
    # check runs BEFORE the transaction, so two concurrent requests can
    # both pass it). Plain (non-expression) composite unique index — now
    # that duplicate-detection lives entirely in value_hash, this no
    # longer needs to be a functional index over the encrypted column.
    # Named identically to the index created by
    # alembic/versions/20260703_i12_no_go_unique_index.py so that
    # ``Base.metadata.create_all()`` (unit-test DBs) and
    # ``alembic upgrade head`` (real deployments) produce the same
    # constraint shape.
    __table_args__ = (
        Index(
            "uq_customer_no_gos_customer_value_hash",
            customer_id,
            value_hash,
            unique=True,
        ),
    )

    customer = relationship("Customer")


# ── I12-follow-up — auto-populate value_hash on insert / update ────────
# Exact mirror of the Customer.email_hash hooks above: derives value_hash
# from (category, value) whenever the caller hasn't already set it,
# keeping the blind-index in lock-step for any direct-ORM construction
# path (tests, seed scripts) that doesn't go through NoGoService.add_no_go
# (which sets it explicitly — see services/no_go_service.py).


@event.listens_for(CustomerNoGo, "before_insert")
def _customer_no_go_before_insert(_mapper, _connection, target: "CustomerNoGo") -> None:
    """Ensure ``value_hash`` is populated on insert."""
    if target.value and target.category is not None and not target.value_hash:
        from goldsmith_erp.core.encryption import (  # noqa: PLC0415
            no_go_value_blind_index,
        )

        target.value_hash = no_go_value_blind_index(target.category.value, target.value)


@event.listens_for(CustomerNoGo, "before_update")
def _customer_no_go_before_update(_mapper, _connection, target: "CustomerNoGo") -> None:
    """Keep ``value_hash`` in lock-step with (category, value) on update.

    CAUTION (security review, 2026-07): the ``not target.value_hash`` guard
    means a future write path that mutates ``value``/``category`` WITHOUT
    clearing ``value_hash`` would leave a stale hash, silently breaking the
    duplicate-detection unique index for that row. No such path exists today
    (no-gos are immutable: created via NoGoService.add_no_go, only ever
    deleted) — if you add an update endpoint, set ``value_hash = None``
    before changing ``value`` or ``category``.
    """
    if target.value and target.category is not None and not target.value_hash:
        from goldsmith_erp.core.encryption import (  # noqa: PLC0415
            no_go_value_blind_index,
        )

        target.value_hash = no_go_value_blind_index(target.category.value, target.value)


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


# ============================================================================
# QR / BARCODE WORKFLOW MODELS (V1.1 — Slice 1)
# ============================================================================
# The three tables below are created by Alembic migration
# `20260418_qr_core` (Slice 1). The ORM classes exist so the service layer
# and tests can query them via SQLAlchemy, BUT the partitioning of
# `scan_logs` is a PostgreSQL feature that lives at the DDL level and is
# not expressed by SQLAlchemy; the ORM treats it as a plain table.
#
# FK semantics: `scan_logs.user_id`, `barcode_aliases.created_by` and
# `label_templates.created_by` all use `ON DELETE RESTRICT` at the DB
# level. Hard-deleting a user who created any of these rows is blocked;
# anonymisation is required via `UserService.anonymize_user` (registered
# in `ANONYMIZABLE_FK_TARGETS`).


class BarcodeAlias(Base):
    """Lookup from a scanned external code (QR or barcode) to an ERP entity.

    Populated at label-print time and on first-scan of an unknown external
    code (e.g. supplier barcodes). One entry per external code; the same
    ERP entity may have many aliases (order qr + metal-lot barcode + etc).
    """

    __tablename__ = "barcode_aliases"

    id = Column(Integer, primary_key=True, autoincrement=True)
    external_code = Column(String(500), nullable=False, unique=True)
    entity_type = Column(String(50), nullable=False)
    entity_id = Column(Integer, nullable=False)
    label = Column(String(200), nullable=True)
    supplier_lot = Column(String(100), nullable=True)
    supplier_cert = Column(String(200), nullable=True)
    # Forward-compat: `suppliers` table is introduced in V1.2. The FK will
    # be added then; today the column stands alone. See migration docstring.
    supplier_id = Column(Integer, nullable=True)
    created_by = Column(
        Integer,
        ForeignKey(
            "users.id",
            name="fk_barcode_aliases_created_by_users",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    created_at = Column(UtcDateTime, default=utcnow, nullable=False)
    last_scanned_at = Column(UtcDateTime, nullable=True)
    scan_count = Column(Integer, default=0, nullable=False)

    creator = relationship("User", foreign_keys=[created_by])


class ScanLog(Base):
    """Append-only audit / analytics log for every scan event.

    Partitioned by `scanned_at` (monthly) on PostgreSQL. The composite PK
    `(id, scanned_at)` is REQUIRED by RANGE partitioning — the partition
    key must appear in every unique/primary-key constraint on a
    partitioned table. SQLAlchemy uses the ORM-level PK for INSERTs and
    does not emit the PostgreSQL `PARTITION BY` clause; that is handled
    entirely by the migration.
    """

    __tablename__ = "scan_logs"

    # Stored as TEXT (36 chars) on SQLite and as UUID on PostgreSQL. Using
    # String(36) at the ORM level keeps the type portable; the migration
    # upgrades the column to native UUID on PG.
    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        nullable=False,
    )
    # Stays TIMESTAMP WITHOUT TIME ZONE in PostgreSQL: it is the RANGE
    # partition key and a partition key column cannot change type. The
    # type still stores naive UTC and hands back aware UTC (BE-15).
    scanned_at = Column(UtcDateTimeNaiveStorage, primary_key=True, nullable=False)
    user_id = Column(
        Integer,
        ForeignKey(
            "users.id",
            name="fk_scan_logs_user_id_users",
            ondelete="RESTRICT",
        ),
        nullable=False,
        index=True,
    )
    raw_payload = Column(String(500), nullable=False)
    resolved_type = Column(String(50), nullable=True)
    resolved_id = Column(String(100), nullable=True)
    resolution_path = Column(String(20), nullable=True)
    action_taken = Column(String(50), nullable=True)
    context = Column(JSON, nullable=True)
    offline_queued = Column(Boolean, default=False, nullable=False)
    synced_at = Column(UtcDateTime, nullable=True)
    idempotency_key = Column(String(36), nullable=True)
    # A1.2 — client-side FAB tap timestamp for adoption metrics.
    client_tap_at = Column(UtcDateTime, nullable=True)
    # A1.3 — server-side resolution completion, pairs with client_tap_at.
    server_resolved_at = Column(UtcDateTime, nullable=True)
    # A1.4 — camera-denied / manual-fallback tracking.
    fallback_reason = Column(String(40), nullable=True)
    # A1.6 — retention bucket for future retention-engine.
    retention_class = Column(String(32), nullable=False, default="standard_24m")

    user = relationship("User", foreign_keys=[user_id])


class LabelTemplate(Base):
    """Printable label layout definition.

    The `fields` JSON column carries the per-template layout; the 7
    system-default rows are seeded by the Slice 1 migration with
    `is_system_default=TRUE` and may NOT be overwritten by re-running
    the seed. Admin-edited copies have `is_system_default=FALSE` and are
    preserved across re-seeding via `ON CONFLICT (entity_type, name) DO
    NOTHING`.
    """

    __tablename__ = "label_templates"
    __table_args__ = (
        UniqueConstraint("entity_type", "name", name="uq_label_templates_entity_name"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    entity_type = Column(String(50), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    width_mm = Column(Integer, default=89, nullable=False)
    height_mm = Column(Integer, default=36, nullable=False)
    fields = Column(JSON, nullable=False)
    is_default = Column(Boolean, default=False, nullable=False)
    is_system_default = Column(Boolean, default=False, nullable=False)
    created_by = Column(
        Integer,
        ForeignKey(
            "users.id",
            name="fk_label_templates_created_by_users",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    created_at = Column(UtcDateTime, default=utcnow, nullable=False)
    updated_at = Column(
        UtcDateTime,
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )

    creator = relationship("User", foreign_keys=[created_by])


Index("ix_notifications_user_read", Notification.user_id, Notification.is_read)

# Slice 1 — QR / barcode workflow indexes.
# Named identically to the Alembic migration indexes so that CREATE INDEX
# from `Base.metadata.create_all()` (used by the test conftest) produces
# the same DB shape as `alembic upgrade head`.
Index("idx_alias_external_code", BarcodeAlias.external_code)
Index(
    "idx_alias_entity",
    BarcodeAlias.entity_type,
    BarcodeAlias.entity_id,
)
Index("idx_scan_user_date", ScanLog.user_id, ScanLog.scanned_at)
Index("idx_scan_entity", ScanLog.resolved_type, ScanLog.resolved_id)
Index(
    "idx_scan_idem",
    ScanLog.idempotency_key,
    unique=True,
    sqlite_where=ScanLog.idempotency_key.isnot(None),
    postgresql_where=ScanLog.idempotency_key.isnot(None),
)
Index("idx_template_entity_type", LabelTemplate.entity_type)


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
