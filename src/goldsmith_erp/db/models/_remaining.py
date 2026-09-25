"""Models not yet moved to a domain module."""

import enum
import uuid
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    Float,
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
from goldsmith_erp.db.models.base import (
    MONEY_NUMERIC,
    PERCENT_NUMERIC,
    WEIGHT_NUMERIC,
    Base,
    CostingMethod,
    InvoiceLineType,
    InvoiceStatus,
    MetalType,
    OrderStatusEnum,
    SAEnum,
)
from goldsmith_erp.db.models.materials import order_materials
from goldsmith_erp.db.types import EncryptedString, UtcDateTime, UtcDateTimeNaiveStorage


class CalendarEventType(str, enum.Enum):
    """Event types for the calendar/planning system."""

    ORDER_DEADLINE = "order_deadline"
    WORKSHOP_TASK = "workshop_task"
    APPOINTMENT = "appointment"
    REMINDER = "reminder"


class OrderTypeEnum(str, enum.Enum):
    """Type of jewelry piece being made — primary ML feature for duration prediction."""

    RING = "ring"
    CHAIN = "chain"
    PENDANT = "pendant"
    EARRINGS = "earrings"
    BRACELET = "bracelet"
    BROOCH = "brooch"
    REPAIR = "repair"
    CUSTOM = "custom"


class FinishTypeEnum(str, enum.Enum):
    """Surface finish type — correlates with polishing time in ML models."""

    HIGH_POLISH = "high_polish"
    MATTE = "matte"
    BRUSHED = "brushed"
    HAMMERED = "hammered"
    OXIDIZED = "oxidized"
    MIXED = "mixed"


class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    description = Column(String)
    price = Column(MONEY_NUMERIC)  # Final customer price (can be manually set)
    # W2-07: every status write goes through services/order_workflow.transition
    # (transition table + an OrderEvent row in the same transaction).
    # DOM-46: new orders start as DRAFT, never the legacy NEW.
    status = Column(
        SAEnum(OrderStatusEnum), default=OrderStatusEnum.DRAFT, nullable=False
    )
    # W2-07 / DOM-13: set by the workflow on ON_HOLD / CANCELLED; the hold
    # fields are cleared again when the order resumes.
    hold_reason = Column(String(500), nullable=True)
    resume_date = Column(Date, nullable=True)
    cancel_reason = Column(String(500), nullable=True)
    customer_id = Column(
        Integer,
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    deadline = Column(UtcDateTime, nullable=True, index=True)  # Deadline für Kalender
    current_location = Column(String(50), nullable=True)  # Aktueller Lagerort

    # Weight & Material Calculation
    estimated_weight_g = Column(
        WEIGHT_NUMERIC, nullable=True
    )  # Estimated metal weight in grams
    actual_weight_g = Column(
        WEIGHT_NUMERIC, nullable=True
    )  # Actual weight after completion
    scrap_percentage = Column(
        PERCENT_NUMERIC, default=Decimal("5.0")
    )  # Material loss percentage (default 5%)

    # Metal Inventory Integration
    metal_type = Column(
        SAEnum(MetalType), nullable=True, index=True
    )  # Which metal type to use
    costing_method_used = Column(
        SAEnum(CostingMethod), default=CostingMethod.FIFO, nullable=True
    )  # Costing method
    specific_metal_purchase_id = Column(
        Integer, ForeignKey("metal_purchases.id", ondelete="SET NULL"), nullable=True
    )  # For SPECIFIC method

    # Cost Calculation
    material_cost_calculated = Column(
        MONEY_NUMERIC, nullable=True
    )  # Auto-calculated material cost
    material_cost_override = Column(
        MONEY_NUMERIC, nullable=True
    )  # Manual override if needed
    labor_hours = Column(Float, nullable=True)  # Estimated or actual work hours
    hourly_rate = Column(
        MONEY_NUMERIC, default=Decimal("75.00")
    )  # Labor rate (EUR/hour)
    labor_cost = Column(MONEY_NUMERIC, nullable=True)  # labor_hours × hourly_rate

    # Pricing
    profit_margin_percent = Column(
        PERCENT_NUMERIC, default=Decimal("40.0")
    )  # Profit margin (%)
    vat_rate = Column(PERCENT_NUMERIC, default=Decimal("19.0"))  # VAT rate (%)
    calculated_price = Column(
        MONEY_NUMERIC, nullable=True
    )  # Auto-calculated final price

    # ML Feature Fields — required for training duration and complexity models
    order_type = Column(
        String(50), nullable=True, index=True
    )  # ring, chain, pendant, etc.
    finish_type = Column(String(50), nullable=True)  # high_polish, matte, brushed, etc.
    complexity_rating = Column(Integer, nullable=True)  # 1-5 stars (set at intake)
    actual_hours = Column(
        Float, nullable=True
    )  # Auto-calculated from time entries on completion
    completed_at = Column(
        UtcDateTime, nullable=True
    )  # Timestamp when order reached COMPLETED/DELIVERED

    # Goldsmith Intake Fields (Pflichtfelder for order confirmation)
    alloy = Column(String(20), nullable=True, index=True)  # '585', '750', '333', etc.
    ring_size_mm = Column(
        Float, nullable=True
    )  # Per-order ring size (mm inner circumference)
    surface_finish = Column(String(50), nullable=True)  # 'Hochglanz', 'Matt', etc.
    fitting_date = Column(UtcDateTime, nullable=True)  # Anprobe-Datum
    has_scrap_gold = Column(Boolean, default=False)  # Altgold vorhanden?
    special_instructions = Column(Text, nullable=True)  # Sonderwuensche

    # ── Slice 2 — Punzierungs-Check + retention tagging ────────────────
    # A2.5 / A2.8 — audit evidence for Feingehaltsgesetz / DIN 8238.
    # Set by the PunzierungsCheckModal flow; marks list is populated with
    # values from A3.2 (e.g. "feingehalt_585", "meisterzeichen").
    punzierung_verified_at = Column(UtcDateTime, nullable=True)
    punzierung_verified_by = Column(
        Integer,
        ForeignKey(
            "users.id",
            name="fk_orders_punzierung_verified_by_users",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )
    # JSONB on PostgreSQL (via the dialect JSON alias); JSON/TEXT on SQLite.
    # Server-side default is an empty array so readers never see NULL.
    punzierung_verified_marks = Column(
        JSON,
        nullable=False,
        server_default=text("'[]'"),
        default=list,
    )
    # A2.7 — retention bucket. Orders default to indefinite_business;
    # A2.8 promotes this to 'hallmark_10y' the first time a mark is
    # recorded (service-layer write path, Slice 5).
    retention_class = Column(
        String(32),
        nullable=False,
        server_default=text("'indefinite_business'"),
        default="indefinite_business",
    )

    # Soft delete
    is_deleted = Column(Boolean, default=False, index=True)
    deleted_at = Column(UtcDateTime, nullable=True)

    # Metadata
    created_at = Column(UtcDateTime, default=utcnow)
    updated_at = Column(UtcDateTime, default=utcnow, onupdate=utcnow)

    # Beziehungen
    customer = relationship("Customer", back_populates="orders")
    materials = relationship(
        "Material", secondary=order_materials, back_populates="orders"
    )
    gemstones = relationship(
        "Gemstone", back_populates="order", cascade="all, delete-orphan"
    )
    material_usage_records = relationship(
        "MaterialUsage", back_populates="order", cascade="all, delete-orphan"
    )
    specific_metal_purchase = relationship(
        "MetalPurchase"
    )  # For SPECIFIC costing method
    comments = relationship(
        "OrderComment",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderComment.created_at.desc()",
    )
    time_entries = relationship("TimeEntry", back_populates="order")
    handoffs = relationship(
        "OrderHandoff",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderHandoff.created_at.desc()",
    )
    hallmarks = relationship(
        "OrderHallmark",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderHallmark.created_at.desc()",
    )
    valuation_certificates = relationship(
        "ValuationCertificate",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="ValuationCertificate.created_at.desc()",
    )
    order_items = relationship(
        "OrderItem", back_populates="order", cascade="all, delete-orphan"
    )
    status_history = relationship(
        "OrderStatusHistory", back_populates="order", cascade="all, delete-orphan"
    )
    events = relationship(
        "OrderEvent",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderEvent.created_at",
    )


class OrderEvent(Base):
    """One order lifecycle event (W2-07, ARCH-01, BE-06).

    Written by ``services/order_workflow.py`` in the SAME transaction as the
    status change it records (or at creation, ``from_status`` NULL). The
    W2-07 migration backfilled one synthetic row per pre-existing order
    (``reason = 'backfill'``). Statuses are stored as the plain enum value
    strings so a later enum change never rewrites history.

    ``meta`` holds non-financial context only (origin, resume_date,
    quote_id, backfill flags); the timeline endpoint serves it to every
    ORDER_VIEW role.
    """

    __tablename__ = "order_events"
    __table_args__ = (Index("ix_order_events_order_created", "order_id", "created_at"),)

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(
        Integer,
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_status = Column(String(30), nullable=True)
    to_status = Column(String(30), nullable=False)
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reason = Column(String(500), nullable=True)
    created_at = Column(UtcDateTime, default=utcnow, nullable=False)
    meta = Column(JSON, nullable=True)

    order = relationship("Order", back_populates="events")
    user = relationship("User", foreign_keys=[user_id])


class OrderComment(Base):
    """Order-scoped comments (Digitale Post-its) for inter-team communication."""

    __tablename__ = "order_comments"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(
        Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    text = Column(Text, nullable=False)
    created_at = Column(UtcDateTime, default=utcnow, index=True)
    updated_at = Column(UtcDateTime, default=utcnow, onupdate=utcnow)

    # Beziehungen
    order = relationship("Order", back_populates="comments")
    user = relationship("User")


class OrderPhoto(Base):
    """Foto-Dokumentation für Aufträge"""

    __tablename__ = "order_photos"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    time_entry_id = Column(
        String(36), ForeignKey("time_entries.id", ondelete="SET NULL"), nullable=True
    )
    file_path = Column(String(500), nullable=False)
    timestamp = Column(UtcDateTime, default=utcnow, index=True)
    taken_by = Column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    notes = Column(Text)

    # Beziehungen
    order = relationship("Order")
    time_entry = relationship("TimeEntry", back_populates="photos")
    user = relationship("User")


class Gemstone(Base):
    """Edelsteine für Aufträge"""

    __tablename__ = "gemstones"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(
        Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Gemstone Details
    type = Column(
        String(50), nullable=False
    )  # 'diamond', 'ruby', 'sapphire', 'emerald'
    carat = Column(WEIGHT_NUMERIC, nullable=True)  # Weight in carats
    quality = Column(String(20), nullable=True)  # 'VS1', 'VVS2', etc. (clarity)
    color = Column(String(20), nullable=True)  # 'D', 'E', 'F' for diamonds
    cut = Column(String(50), nullable=True)  # 'Excellent', 'Very Good', 'Good'
    shape = Column(String(50), nullable=True)  # 'Round', 'Princess', 'Oval'

    # Cost & Quantity
    cost = Column(MONEY_NUMERIC, nullable=False)  # Purchase/estimated cost per stone
    quantity = Column(Integer, default=1)  # Number of identical stones
    total_cost = Column(MONEY_NUMERIC, nullable=True)  # cost × quantity

    # Setting
    setting_type = Column(
        String(100), nullable=True
    )  # 'Prong', 'Bezel', 'Channel', etc.

    # Optional certificate info
    certificate_number = Column(String(100), nullable=True)
    certificate_authority = Column(String(50), nullable=True)  # 'GIA', 'IGI', 'HRD'

    # W2-06 / DOM-04: Kundenstein (the customer brought the stone). Migration
    # 20260925_w206_gemstone_intake.
    is_customer_stone = Column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )

    notes = Column(Text, nullable=True)

    # Beziehungen
    order = relationship("Order", back_populates="gemstones")


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


# ============================================================================
# INVOICE / BILLING (RECHNUNGSWESEN)
# ============================================================================


class Invoice(Base):
    """
    Rechnung (Invoice) for a completed goldsmith order.

    Invoice numbers follow the German format RE-YYYY-NNNN (sequential per year).
    Tax is 19% MwSt (Mehrwertsteuer) by default.
    All financial access is audit-logged via structured logging.
    """

    __tablename__ = "invoices"
    __table_args__ = (
        # W2-04 (BE-16): at most one live invoice per order. Cancelled
        # originals and Stornorechnungen (cancels_invoice_id set) are
        # excluded, so a corrected invoice can follow a Storno.
        Index(
            "uq_invoices_one_active_per_order",
            "order_id",
            unique=True,
            postgresql_where=text(
                "status <> 'cancelled' AND cancels_invoice_id IS NULL"
            ),
            sqlite_where=text("status <> 'cancelled' AND cancels_invoice_id IS NULL"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    # Rechnungsnummer: RE-2026-0001 (unique). W2-04: drawn from the
    # per-year ``number_sequences`` counter (services/number_sequence_service).
    invoice_number = Column(String(20), unique=True, nullable=False, index=True)

    # W2-04 (DOM-24b): a Stornorechnung points at the invoice it cancels.
    # The original is never edited; it only moves to CANCELLED.
    cancels_invoice_id = Column(
        Integer,
        ForeignKey("invoices.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )

    # Links
    order_id = Column(
        Integer,
        ForeignKey("orders.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    customer_id = Column(
        Integer,
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    created_by = Column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    # Status
    status = Column(
        SAEnum(InvoiceStatus), default=InvoiceStatus.DRAFT, nullable=False, index=True
    )

    # Dates
    issue_date = Column(UtcDateTime, nullable=False, default=utcnow, index=True)
    due_date = Column(UtcDateTime, nullable=False, index=True)  # Faelligkeitsdatum
    paid_date = Column(UtcDateTime, nullable=True)  # Zahlungsdatum
    # W2-04 (DOM-24): Leistungsdatum (§14 Abs. 4 Nr. 6 UStG). Set at
    # creation from the request, else the order's completion date.
    service_date = Column(UtcDateTime, nullable=True)

    # Amounts (Betraege)
    subtotal = Column(
        MONEY_NUMERIC, nullable=False, default=Decimal("0.0")
    )  # Zwischensumme (netto)
    tax_rate = Column(
        PERCENT_NUMERIC, nullable=False, default=Decimal("19.0")
    )  # MwSt-Satz in Prozent
    tax_amount = Column(
        MONEY_NUMERIC, nullable=False, default=Decimal("0.0")
    )  # MwSt-Betrag
    total = Column(
        MONEY_NUMERIC, nullable=False, default=Decimal("0.0")
    )  # Gesamtbetrag (brutto)

    # Optional fields
    notes = Column(Text, nullable=True)  # Anmerkungen
    payment_method = Column(
        String(50), nullable=True
    )  # Zahlungsart (Ueberweisung, Bar, Karte)

    # ── W1-10 (GDPR-01, BE-23): immutable invoice snapshot ─────────────
    # JSON (recipient, seller, order, lines, totals) written at creation;
    # holds recipient name/address, so it is encrypted at rest. The PDF is
    # rendered from it, never from the live customer row. See
    # services/invoice_snapshot_service.py. Migration:
    # 20260925_w110_invoice_snapshot (backfills legacy rows, backfilled=True).
    snapshot = Column(EncryptedString, nullable=True)
    # Frozen at issue (DRAFT -> SENT, or DRAFT -> PAID): base64 PDF bytes
    # (encrypted, contains the recipient) plus SHA-256 of the raw bytes.
    # Write-once; served verbatim for every non-DRAFT invoice.
    issued_at = Column(UtcDateTime, nullable=True)
    issued_pdf = Column(EncryptedString, nullable=True)
    issued_pdf_sha256 = Column(String(64), nullable=True)

    # Metadata
    created_at = Column(UtcDateTime, default=utcnow, nullable=False)
    updated_at = Column(UtcDateTime, default=utcnow, onupdate=utcnow, nullable=False)

    # Relationships
    order = relationship("Order")
    customer = relationship("Customer")
    creator = relationship("User")
    line_items = relationship(
        "InvoiceLineItem",
        back_populates="invoice",
        cascade="all, delete-orphan",
        order_by="InvoiceLineItem.id",
    )


class InvoiceLineItem(Base):
    """
    Rechnungsposition (Invoice Line Item).

    Each line item represents a billable component of the work:
    - Material (Werkstoff, e.g. "Gold 18K, 5.2g")
    - Labor (Arbeitszeit, e.g. "Fertigung Ring, 3.5h")
    - Gemstone (Edelstein, e.g. "Diamant 0.5ct VS1")
    - Other (Sonstiges)
    """

    __tablename__ = "invoice_line_items"

    id = Column(Integer, primary_key=True, index=True)
    invoice_id = Column(
        Integer,
        ForeignKey("invoices.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Line item details
    line_type = Column(
        SAEnum(InvoiceLineType), nullable=False, default=InvoiceLineType.OTHER
    )
    description = Column(String(500), nullable=False)  # Beschreibung der Position
    quantity = Column(WEIGHT_NUMERIC, nullable=False, default=Decimal("1.0"))
    unit_price = Column(MONEY_NUMERIC, nullable=False)  # Einzelpreis (netto)
    total = Column(
        MONEY_NUMERIC, nullable=False
    )  # Gesamtpreis dieser Position (quantity * unit_price)

    # Relationships
    invoice = relationship("Invoice", back_populates="line_items")


# ============================================================================
# W2-04: WORKSHOP SETTINGS (Werkstatt-Stammdaten) AND NUMBER SEQUENCES
# ============================================================================


class WorkshopSettings(Base):
    """Seller master data printed on every Rechnung (§14 Abs. 4 UStG).

    Singleton (``id`` is always 1, enforced by a CHECK constraint). Holds
    only the workshop's own business data, no customer PII. Edited by ADMIN
    via ``GET/PUT /admin/workshop-settings``; every change is audit-logged.
    Invoices copy these fields into their snapshot at creation and at issue,
    so later edits never change an issued invoice.
    """

    __tablename__ = "workshop_settings"
    __table_args__ = (CheckConstraint("id = 1", name="ck_workshop_settings_singleton"),)

    id = Column(Integer, primary_key=True, default=1)
    name = Column(String(200), nullable=False, default="")
    owner_name = Column(String(200), nullable=True)
    street = Column(String(200), nullable=True)
    postal_code = Column(String(20), nullable=True)
    city = Column(String(100), nullable=True)
    country = Column(String(100), nullable=True, default="Deutschland")
    phone = Column(String(50), nullable=True)
    email = Column(String(255), nullable=True)
    tax_number = Column(String(50), nullable=True)  # Steuernummer
    vat_id = Column(String(20), nullable=True)  # USt-IdNr.
    iban = Column(String(34), nullable=True)
    bic = Column(String(11), nullable=True)
    bank_name = Column(String(100), nullable=True)
    is_kleinunternehmer = Column(Boolean, nullable=False, default=False)  # §19 UStG
    default_vat_rate = Column(PERCENT_NUMERIC, nullable=False, default=Decimal("19.0"))
    invoice_footer = Column(Text, nullable=True)
    updated_at = Column(UtcDateTime, default=utcnow, onupdate=utcnow, nullable=False)
    updated_by = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )


class NumberSequence(Base):
    """Gap-free per-year counter for human-facing document numbers.

    One row per (kind, year), e.g. ("RE", 2026). ``last_value`` is bumped
    with a single row-locking ``UPDATE ... RETURNING`` inside the caller's
    transaction, so concurrent creates serialise on the row and a rolled
    back create gives its number back. See
    services/number_sequence_service.py (BE-16, decision D-12).
    """

    __tablename__ = "number_sequences"

    kind = Column(String(10), primary_key=True)
    year = Column(Integer, primary_key=True)
    last_value = Column(Integer, nullable=False, default=0)


# ============================================================================
# QUOTE SYSTEM (Kostenvoranschlag)
# ============================================================================


class QuoteStatus(str, enum.Enum):
    """Lifecycle status of a quote (Kostenvoranschlag-Status)."""

    DRAFT = "draft"  # Entwurf
    SENT = "sent"  # Gesendet
    APPROVED = "approved"  # Genehmigt
    REJECTED = "rejected"  # Abgelehnt
    EXPIRED = "expired"  # Abgelaufen
    CONVERTED = "converted"  # Umgewandelt in Auftrag


class QuoteLineType(str, enum.Enum):
    """Type of quote line item (Angebotspositionstyp)."""

    MATERIAL = "material"
    LABOR = "labor"
    GEMSTONE = "gemstone"
    OTHER = "other"


class Quote(Base):
    """
    Kostenvoranschlag (Quote/Estimate) for a goldsmith job.

    Quote numbers follow the format KV-YYYY-NNNN (sequential per year).
    Valid for 14 days by default. Can be linked to an existing order or
    created standalone with only a customer reference.
    All financial access is audit-logged.
    """

    __tablename__ = "quotes"

    id = Column(Integer, primary_key=True, index=True)

    # KV-Nummer: KV-2026-0001 (unique, generated on creation)
    quote_number = Column(String(20), unique=True, nullable=False, index=True)

    # Links -- order_id is optional (quote can precede an order)
    order_id = Column(
        Integer, ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    customer_id = Column(
        Integer,
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    created_by = Column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    # Status
    status = Column(
        SAEnum(QuoteStatus), default=QuoteStatus.DRAFT, nullable=False, index=True
    )

    # Dates
    valid_until = Column(
        UtcDateTime, nullable=False, index=True
    )  # Gueltig bis (+14 Tage default)
    approved_at = Column(UtcDateTime, nullable=True)  # Genehmigt am
    rejected_at = Column(UtcDateTime, nullable=True)  # Abgelehnt am
    converted_at = Column(UtcDateTime, nullable=True)  # Umgewandelt am

    # Amounts (Betraege)
    subtotal = Column(
        MONEY_NUMERIC, nullable=False, default=Decimal("0.0")
    )  # Zwischensumme (netto)
    tax_rate = Column(
        PERCENT_NUMERIC, nullable=False, default=Decimal("19.0")
    )  # MwSt-Satz in Prozent
    tax_amount = Column(
        MONEY_NUMERIC, nullable=False, default=Decimal("0.0")
    )  # MwSt-Betrag
    total = Column(
        MONEY_NUMERIC, nullable=False, default=Decimal("0.0")
    )  # Gesamtbetrag (brutto)

    # Customer signature (base64 PNG -- stored for approved quotes)
    customer_signature_data = Column(Text, nullable=True)

    # Optional fields
    notes = Column(Text, nullable=True)  # Anmerkungen

    # Metadata
    created_at = Column(UtcDateTime, default=utcnow, nullable=False)
    updated_at = Column(UtcDateTime, default=utcnow, onupdate=utcnow, nullable=False)

    # Relationships
    order = relationship("Order")
    customer = relationship("Customer")
    creator = relationship("User")
    line_items = relationship(
        "QuoteLineItem",
        back_populates="quote",
        cascade="all, delete-orphan",
        order_by="QuoteLineItem.id",
    )


class QuoteLineItem(Base):
    """
    Angebotsposition (Quote Line Item).

    Each line item represents a cost component of the estimate:
    - Material (Werkstoff, e.g. "Gold 18K, 5.2g")
    - Labor (Arbeitszeit, e.g. "Fertigung Ring, 3.5h")
    - Gemstone (Edelstein, e.g. "Diamant 0.5ct VS1")
    - Other (Sonstiges)
    """

    __tablename__ = "quote_line_items"

    id = Column(Integer, primary_key=True, index=True)
    quote_id = Column(
        Integer, ForeignKey("quotes.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Line item details
    line_type = Column(
        SAEnum(QuoteLineType), nullable=False, default=QuoteLineType.OTHER
    )
    description = Column(String(500), nullable=False)  # Beschreibung der Position
    quantity = Column(WEIGHT_NUMERIC, nullable=False, default=Decimal("1.0"))
    unit_price = Column(MONEY_NUMERIC, nullable=False)  # Einzelpreis (netto)
    total = Column(MONEY_NUMERIC, nullable=False)  # Gesamtpreis (quantity * unit_price)

    # Snapshot of estimator inputs/outputs (V1.3 Phase 3).
    # NULL = manual entry; non-null = estimator-sourced (immutable at API layer).
    estimator_metadata = Column(JSON, nullable=True)

    # Relationships
    quote = relationship("Quote", back_populates="line_items")


# ============================================================================
# NOTIFICATION SYSTEM
# ============================================================================


class HandoffTypeEnum(str, enum.Enum):
    """
    Type of order handoff (Uebergabetyp) between goldsmiths.

    PASS_TO_NEXT     — Normale Weitergabe, z.B. "Loeten fertig → Fassung"
    REQUEST_REVIEW   — Qualitaetskontrolle anfordern, z.B. "Fassung pruefen"
    RETURN_FOR_REWORK— Stueck zurueckgeben mit Nacharbeitsauftrag
    MARK_COMPLETE    — Letzter Arbeitsschritt abgeschlossen (Endkontrolle)
    """

    PASS_TO_NEXT = "pass_to_next"
    REQUEST_REVIEW = "request_review"
    RETURN_FOR_REWORK = "return_for_rework"
    MARK_COMPLETE = "mark_complete"


class HandoffStatusEnum(str, enum.Enum):
    """Lifecycle state of an order handoff record."""

    PENDING = "pending"  # Warten auf Bestaetigung durch Empfaenger
    ACCEPTED = "accepted"  # Empfaenger hat uebernommen
    DECLINED = "declined"  # Empfaenger hat abgelehnt (mit Begruendung)


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
# HANDOFF PROTOCOL (STABUEBERGABE)
# ============================================================================


class OrderHandoff(Base):
    """
    Formal handoff record when an order passes between goldsmiths.

    Workflow: Sender creates a PENDING handoff → recipient ACCEPTS or DECLINES.
    On acceptance the order changes hands; on decline the sender is notified
    with the reason so they can resolve the issue before re-attempting.

    Examples:
      "Loeten fertig, bitte Fassung pruefen" (PASS_TO_NEXT)
      "Fassung kontrollieren" (REQUEST_REVIEW)
      "Pavee-Fassung muss nachgearbeitet werden" (RETURN_FOR_REWORK)
      "Endkontrolle abgeschlossen" (MARK_COMPLETE)
    """

    __tablename__ = "order_handoffs"

    id = Column(Integer, primary_key=True, index=True)

    # Order being handed off
    order_id = Column(
        Integer,
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Who is passing the order
    from_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,  # SET NULL so handoff history survives user deletion
        index=True,
    )

    # Who should receive the order
    to_user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Handoff classification
    handoff_type = Column(
        SAEnum(HandoffTypeEnum),
        nullable=False,
        index=True,
    )

    # Lifecycle status
    status = Column(
        SAEnum(HandoffStatusEnum),
        nullable=False,
        default=HandoffStatusEnum.PENDING,
        index=True,
    )

    # Sender's message — e.g. "Loeten fertig, Lot an Stelle 3 pruefen"
    notes = Column(Text, nullable=True)

    # Recipient's response when declining — required on DECLINED
    response_notes = Column(Text, nullable=True)

    # Timestamps
    created_at = Column(UtcDateTime, default=utcnow, nullable=False, index=True)
    responded_at = Column(UtcDateTime, nullable=True)  # Set when accepted/declined

    # Relationships
    order = relationship("Order", back_populates="handoffs")
    from_user = relationship("User", foreign_keys=[from_user_id])
    to_user = relationship("User", foreign_keys=[to_user_id])

    def __repr__(self) -> str:
        return (
            f"<OrderHandoff order={self.order_id} "
            f"{self.handoff_type.value} "
            f"from={self.from_user_id} to={self.to_user_id} "
            f"status={self.status.value}>"
        )


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


# ============================================================================
# HALLMARKING / PUNZIERUNG
# ============================================================================


class HallmarkType(str, enum.Enum):
    """
    Types of hallmarks applied to precious metal pieces.

    German goldsmiths are required to hallmark pieces above threshold weights.
    Each type corresponds to a distinct punch (Punze) applied to the metal.
    """

    FINENESS_MARK = "fineness_mark"  # Feingehaltsstempel (e.g. 585, 750)
    MAKERS_MARK = "makers_mark"  # Herstellermarke / Meisterpunze
    ASSAY_OFFICE = "assay_office"  # Beschauzeichen der Pruefstelle
    COMMON_CONTROL = "common_control"  # Gemeinsames Kontrollzeichen (CCM)
    DATE_LETTER = "date_letter"  # Datumsbuchstabe (used in UK/some EU)


class HallmarkStatus(str, enum.Enum):
    """
    Lifecycle state of a hallmark application.

    A hallmark starts PENDING, is SUBMITTED to the Pruefstelle (assay office),
    and ends as APPROVED (Pruefzeugnis erteilt) then STAMPED (Punze aufgebracht).
    """

    PENDING = "pending"  # Noch nicht eingereicht
    SUBMITTED = "submitted"  # Eingereicht an Pruefstelle
    APPROVED = "approved"  # Genehmigt — Pruefzeugnis erteilt
    REJECTED = "rejected"  # Abgelehnt — Nacharbeit erforderlich
    STAMPED = "stamped"  # Punze physisch aufgebracht


class OrderHallmark(Base):
    """
    Hallmarking record (Punzierung) per order.

    German law (Edelmetallgesetz) requires pieces above certain weights
    to carry a Feingehaltsstempel.  This table tracks one hallmark application
    per row so an order can carry multiple distinct marks (e.g. fineness mark +
    maker's mark in one workflow step, assay office stamp in another).

    All hallmark records are financial/legal data — access is logged and
    restricted to GOLDSMITH and ADMIN roles.
    """

    __tablename__ = "order_hallmarks"

    id = Column(Integer, primary_key=True, index=True)

    # Parent order
    order_id = Column(
        Integer,
        ForeignKey("orders.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Hallmark type and status
    hallmark_type = Column(
        SAEnum(HallmarkType),
        nullable=False,
        index=True,
    )
    status = Column(
        SAEnum(HallmarkStatus),
        nullable=False,
        default=HallmarkStatus.PENDING,
        index=True,
    )

    # Assay office details (Pruefstelle)
    assay_office = Column(
        String(100), nullable=True
    )  # "Pforzheim", "Schwaebisch Gmuend"

    # Certificate issued by assay office — unique per hallmark application
    certificate_number = Column(String(100), unique=True, nullable=True, index=True)

    # Timestamps for lifecycle steps
    submitted_at = Column(UtcDateTime, nullable=True)  # Eingereicht am
    approved_at = Column(UtcDateTime, nullable=True)  # Genehmigt am
    stamped_at = Column(UtcDateTime, nullable=True)  # Gestempelt am

    # Free-text notes (e.g. rejection reason or goldsmith observations)
    notes = Column(Text, nullable=True)

    # Audit
    created_at = Column(UtcDateTime, default=utcnow, nullable=False, index=True)
    created_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Relationships
    order = relationship("Order", back_populates="hallmarks")
    creator = relationship("User", foreign_keys=[created_by])

    def __repr__(self) -> str:
        return (
            f"<OrderHallmark order={self.order_id} "
            f"type={self.hallmark_type.value} "
            f"status={self.status.value}>"
        )


# ============================================================================
# INSURANCE VALUATION CERTIFICATES (WERTGUTACHTEN)
# ============================================================================


class ValuationCertificate(Base):
    """
    Wertgutachten — official insurance valuation certificate.

    German goldsmiths issue these for customers who need to insure their
    jewelry.  The certificate documents the piece in full (metal, gemstones,
    workmanship) and states an appraised market replacement value in EUR.

    Certificate numbers follow the format WG-YYYY-NNNN (sequential per year).
    Certificates are valid for 2 years (typical insurance requirement).

    SECURITY: valuation data (appraised_value) is financial data AND must be
    encrypted at rest per CLAUDE.md "Data Privacy Rules (CRITICAL) — Insurance
    Valuations." The ``appraised_value`` column uses :class:`EncryptedString`
    and stores the amount as a fixed-2-decimal string (Fernet ciphertext on
    disk). A companion ``appraised_value_hmac`` column carries the HMAC
    blind-index so equality lookups ("find the certificate worth €12500") are
    still answerable without decrypting every row — matches the C1 pattern
    on ``Customer.email`` / ``Customer.email_hash``.

    Python callers continue to use ``cert.appraised_value`` as a numeric:
    the ``@property`` below returns a ``Decimal`` on read and accepts any
    number-like (``Decimal`` / ``float`` / ``int`` / ``str``) on write,
    round-tripping through the fixed-2-decimal normalised string. The
    ``.appraised_value_hmac`` hash is auto-populated by the ``before_insert``
    / ``before_update`` event hooks below so tests and seed scripts that
    construct ``ValuationCertificate(appraised_value=X)`` directly don't
    have to remember the hash column.
    """

    __tablename__ = "valuation_certificates"

    id = Column(Integer, primary_key=True, index=True)

    # Certificate number: WG-2026-0001
    certificate_number = Column(String(20), unique=True, nullable=False, index=True)

    # Links
    order_id = Column(
        Integer,
        ForeignKey("orders.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    customer_id = Column(
        Integer,
        ForeignKey("customers.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    created_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Item description — detailed enough for insurance purposes
    item_description = Column(Text, nullable=False)

    # Metal details
    metal_type = Column(String(100), nullable=True)  # "Gelbgold 750 (18K)"
    metal_weight_g = Column(WEIGHT_NUMERIC, nullable=True)  # Metallgewicht in Gramm
    metal_purity = Column(String(20), nullable=True)  # "750", "585", "950"

    # Gemstone summary (free-text list — mirrors what is in Gemstone rows)
    gemstones_description = Column(Text, nullable=True)

    # Appraised value (Schätzwert / Gutachtenwert) — financial data, ENCRYPTED
    # at rest (C3). The SQL column name stays ``appraised_value`` for
    # schema/migration continuity; the Python ORM attribute is
    # ``_appraised_value_cipher`` so we can expose the decrypted numeric via
    # a proper ``@property`` below. ``nullable=False`` — every certificate
    # has a value.
    _appraised_value_cipher = Column(
        "appraised_value",
        EncryptedString,
        nullable=False,
        key="_appraised_value_cipher",
    )
    # HMAC blind-index over the 2-decimal-normalised string. Indexed so
    # equality lookups don't scan every row. Not unique — two certificates
    # can legitimately share the same appraised value.
    appraised_value_hmac = Column(String(64), nullable=False, index=True)

    # Validity
    valuation_date = Column(UtcDateTime, nullable=False, default=utcnow, index=True)
    valid_until = Column(UtcDateTime, nullable=False, index=True)  # +2 Jahre default

    # Goldsmith credentials shown on certificate
    goldsmith_name = Column(String(200), nullable=False)
    goldsmith_qualification = Column(
        String(200), nullable=True
    )  # "Goldschmiedemeister"

    # Generated PDF path (stored on disk / S3 in production)
    pdf_path = Column(String(500), nullable=True)

    # Audit
    created_at = Column(UtcDateTime, default=utcnow, nullable=False, index=True)
    updated_at = Column(
        UtcDateTime,
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )

    # Relationships
    order = relationship("Order", back_populates="valuation_certificates")
    customer = relationship("Customer")
    creator = relationship("User", foreign_keys=[created_by])

    # ── Numeric interface over the encrypted string column ─────────────
    # Callers historically use ``cert.appraised_value`` as a number; keep
    # that contract. The getter returns a ``Decimal`` (financial data —
    # avoids float drift on formatting). The setter accepts any
    # ``Decimal``/``float``/``int``/``str`` and normalises to a fixed
    # 2-decimal string before handing off to the ``EncryptedString``
    # column. The setter ALSO updates ``appraised_value_hmac`` in lock-
    # step so equality search stays consistent even when callers assign
    # via ``cert.appraised_value = X`` on an already-persisted row.
    @property
    def appraised_value(self):
        """Decrypted numeric appraised value (EUR) as ``Decimal``."""
        from decimal import Decimal  # local import — avoid top-of-file churn

        cipher = self._appraised_value_cipher
        if cipher is None:
            return None
        return Decimal(cipher)

    @appraised_value.setter
    def appraised_value(self, value) -> None:
        from decimal import Decimal  # local import

        if value is None:
            self._appraised_value_cipher = None
            # Hash column is NOT NULL; we only null the cipher if the caller
            # is explicitly clearing (e.g. in-test fixture reset). The
            # before_insert / before_update guard below will raise on flush
            # if someone tries to persist a NULL value without setting the
            # hash — matching the NOT NULL constraint on both columns.
            return
        # 2-decimal normalisation — money-like. Use Decimal to avoid the
        # float repr surprises (e.g. 0.1 + 0.2 → 0.30000000000000004).
        normalised = f"{Decimal(str(value)):.2f}"
        self._appraised_value_cipher = normalised
        # Local import — matches the C1 pattern on Customer.email_hash and
        # avoids a module-level cycle (encryption → config → logging → …).
        from goldsmith_erp.core.encryption import hmac_blind_index  # noqa: PLC0415

        self.appraised_value_hmac = hmac_blind_index(normalised)

    def __repr__(self) -> str:
        return (
            f"<ValuationCertificate {self.certificate_number} "
            f"order={self.order_id} "
            f"value={self.appraised_value:.2f} EUR>"
        )


# ── C3 — auto-populate appraised_value_hmac on insert / update ────────
# Parallel to the C1 event hooks on ``Customer.email_hash``. The property
# setter above populates the hash on every ``cert.appraised_value = X``
# assignment, but direct-ORM construction via SQLAlchemy internals (e.g.
# ``session.merge`` paths, or tests using bulk_save_objects) might write
# to ``_appraised_value_cipher`` without going through the setter. The
# hooks below derive the hash from the current cipher as a safety net,
# mirroring the consistency guarantee on Customer.
#
# Why ``_appraised_value_cipher`` and not ``appraised_value``: by the
# time the before_insert hook fires, the cipher column holds the
# normalised 2-decimal string (SQLAlchemy has not yet run the
# ``EncryptedString.process_bind_param`` encrypt step — that happens at
# the dialect-bind layer, below the ORM event bus). We hash against the
# same normalised plaintext the setter uses, so a round-trip like
# ``cert.appraised_value = 12500`` → DB → ``cert.appraised_value``
# never breaks the hash invariant.


@event.listens_for(ValuationCertificate, "before_insert")
def _valuation_before_insert(
    _mapper, _connection, target: "ValuationCertificate"
) -> None:
    """Ensure ``appraised_value_hmac`` is populated on insert."""
    cipher = target._appraised_value_cipher
    if cipher and not target.appraised_value_hmac:
        from goldsmith_erp.core.encryption import hmac_blind_index  # noqa: PLC0415

        target.appraised_value_hmac = hmac_blind_index(cipher)


@event.listens_for(ValuationCertificate, "before_update")
def _valuation_before_update(
    _mapper, _connection, target: "ValuationCertificate"
) -> None:
    """Keep ``appraised_value_hmac`` in lock-step with the cipher column.

    If the cipher changed but the hash wasn't recomputed (unusual — the
    property setter handles that for every direct assignment — but
    possible via low-level ORM paths), derive it here. Cheap: one HMAC.
    """
    cipher = target._appraised_value_cipher
    if cipher and not target.appraised_value_hmac:
        from goldsmith_erp.core.encryption import hmac_blind_index  # noqa: PLC0415

        target.appraised_value_hmac = hmac_blind_index(cipher)


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
# ORDER LINE ITEMS & STATUS HISTORY
# ============================================================================


class OrderItem(Base):
    """Individual line items within an order."""

    __tablename__ = "order_items"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(
        Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    description = Column(String(500), nullable=False)
    quantity = Column(Integer, default=1, nullable=False)
    unit_price = Column(MONEY_NUMERIC, nullable=True)
    material_id = Column(
        Integer, ForeignKey("materials.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(UtcDateTime, default=utcnow, nullable=False)

    order = relationship("Order", back_populates="order_items")


class OrderStatusHistory(Base):
    """Tracks order status transitions."""

    __tablename__ = "order_status_history"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(
        Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    from_status = Column(String(50), nullable=True)
    to_status = Column(String(50), nullable=False)
    changed_by = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    changed_at = Column(UtcDateTime, default=utcnow, nullable=False)
    notes = Column(String(500), nullable=True)

    order = relationship("Order", back_populates="status_history")
    user = relationship("User", foreign_keys=[changed_by])


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
Index("ix_orders_customer_deleted", Order.customer_id, Order.is_deleted)

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
Index(
    "idx_orders_punzierung_verified_at",
    Order.punzierung_verified_at,
    postgresql_where=Order.punzierung_verified_at.isnot(None),
)
# retention_class indexes — small, selective buckets for the future
# retention engine.
Index("idx_orders_retention_class", Order.retention_class)


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
