from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, text
from sqlalchemy import Enum as _SAEnum
from sqlalchemy import (
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    UniqueConstraint,
    event,
    text,
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

from goldsmith_erp.db.types import EncryptedString


def SAEnum(enum_class, **kwargs):
    """Wrapper that ensures Python enum .value (lowercase) is stored in PostgreSQL."""
    return _SAEnum(enum_class, values_callable=lambda e: [x.value for x in e], **kwargs)


import enum
import uuid


class CalendarEventType(str, enum.Enum):
    """Event types for the calendar/planning system."""

    ORDER_DEADLINE = "order_deadline"
    WORKSHOP_TASK = "workshop_task"
    APPOINTMENT = "appointment"
    REMINDER = "reminder"


Base = declarative_base()


class OrderStatusEnum(str, enum.Enum):
    """Enumerated order statuses for consistency and validation.

    Follows the goldsmith production pipeline:
    Auftrag -> Entwurf -> Guss -> Montage -> Fassung -> Oberflaeche -> QK -> Auslieferung
    """

    DRAFT = "draft"
    CONFIRMED = "confirmed"
    IN_PROGRESS = "in_progress"
    WAITING_FOR_FITTING = "waiting_for_fitting"
    FITTING_DONE = "fitting_done"
    READY_FOR_SETTING = "ready_for_setting"
    QUALITY_CHECK = "quality_check"
    COMPLETED = "completed"
    DELIVERED = "delivered"
    NEW = "new"  # Legacy backward compatibility


class UserRole(str, enum.Enum):
    """User roles for RBAC (Role-Based Access Control)."""

    ADMIN = "admin"  # Full system access
    GOLDSMITH = "goldsmith"  # Production workers (orders, time tracking, materials)
    VIEWER = "viewer"  # View-only access    # Standard user access


class MetalType(str, enum.Enum):
    """Standard metal types used in goldsmith workshop"""

    GOLD_24K = "gold_24k"  # 999.9 Feingold
    GOLD_22K = "gold_22k"  # 916 Gold
    GOLD_18K = "gold_18k"  # 750 Gold
    GOLD_14K = "gold_14k"  # 585 Gold
    GOLD_9K = "gold_9k"  # 375 Gold
    SILVER_999 = "silver_999"  # Feinsilber
    SILVER_925 = "silver_925"  # Sterling Silber
    SILVER_800 = "silver_800"  # Altsilber
    PLATINUM_950 = "platinum_950"
    PLATINUM_900 = "platinum_900"
    PALLADIUM = "palladium"
    WHITE_GOLD_18K = "white_gold_18k"
    WHITE_GOLD_14K = "white_gold_14k"
    ROSE_GOLD_18K = "rose_gold_18k"
    ROSE_GOLD_14K = "rose_gold_14k"


class CostingMethod(str, enum.Enum):
    """Inventory costing method for material consumption"""

    FIFO = "fifo"  # First In, First Out
    LIFO = "lifo"  # Last In, First Out
    AVERAGE = "average"  # Weighted Average Cost
    SPECIFIC = "specific"  # Specific Identification (manual selection)


class ScrapGoldStatus(str, enum.Enum):
    """Status of scrap gold processing."""

    RECEIVED = "received"  # Items documented
    CALCULATED = "calculated"  # Fine content calculated
    SIGNED = "signed"  # Customer signed receipt
    CREDITED = "credited"  # Applied to invoice


class InvoiceStatus(str, enum.Enum):
    """Invoice lifecycle status (Rechnungsstatus)."""

    DRAFT = "draft"  # Entwurf - not yet sent
    SENT = "sent"  # Versendet - sent to customer
    PAID = "paid"  # Bezahlt - payment received
    OVERDUE = "overdue"  # Ueberfaellig - past due date
    CANCELLED = "cancelled"  # Storniert - voided


class InvoiceLineType(str, enum.Enum):
    """Type of invoice line item (Rechnungspositionstyp)."""

    MATERIAL = "material"  # Metal material (e.g. Gold 18K)
    LABOR = "labor"  # Labor/Arbeitszeit
    GEMSTONE = "gemstone"  # Edelstein
    OTHER = "other"  # Sonstiges


class MeasurementType(str, enum.Enum):
    """Types of body measurements stored in the customer Massbibliothek."""

    RING_SIZE = "ring_size"  # Ring inner circumference (EU mm or EU size)
    CHAIN_LENGTH = "chain_length"  # Necklace/chain length in cm
    WRIST_CIRCUMFERENCE = "wrist_circumference"  # Wrist for bracelets
    FINGER_CIRCUMFERENCE = "finger_circumference"  # Exact finger circumference in mm
    NECK_CIRCUMFERENCE = "neck_circumference"  # Neck circumference in cm
    ANKLE_CIRCUMFERENCE = "ankle_circumference"  # Ankle for anklets


class HandSide(str, enum.Enum):
    """Hand side for ring and bracelet measurements."""

    LEFT = "left"
    RIGHT = "right"


class FingerPosition(str, enum.Enum):
    """Finger position for ring measurements (Fingerposition)."""

    THUMB = "thumb"  # Daumen
    INDEX = "index"  # Zeigefinger
    MIDDLE = "middle"  # Mittelfinger
    RING = "ring"  # Ringfinger
    PINKY = "pinky"  # Kleiner Finger


class AlloyType(str, enum.Enum):
    """Standard gold/silver alloy types with fine content ratio."""

    GOLD_999 = "999"  # 99.9% Feingold
    GOLD_900 = "900"  # 90.0%
    GOLD_750 = "750"  # 75.0% (18K)
    GOLD_585 = "585"  # 58.5% (14K)
    GOLD_375 = "375"  # 37.5% (9K)
    GOLD_333 = "333"  # 33.3% (8K)
    SILVER_999 = "ag999"  # 99.9% Feinsilber
    SILVER_925 = "ag925"  # 92.5% Sterling
    SILVER_800 = "ag800"  # 80.0%
    PLATINUM_950 = "pt950"  # 95.0%


# Many-to-Many zwischen Material und Order
order_materials = Table(
    "order_materials",
    Base.metadata,
    Column("order_id", Integer, ForeignKey("orders.id"), primary_key=True),
    Column("material_id", Integer, ForeignKey("materials.id"), primary_key=True),
)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    first_name = Column(String)
    last_name = Column(String)
    role = Column(SAEnum(UserRole), default=UserRole.VIEWER, nullable=False, index=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # ── GDPR Art. 17 anonymisation infrastructure (Slice 0) ─────────────────
    # Populated by services.user_service.anonymize_user(). See
    # docs/superpowers/plans/qr-barcode-workflow/V1.1-ANONYMIZE-USER-CONTRACT.md.
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    deleted_at = Column(DateTime, nullable=True)
    # Short (16-char) HMAC tracking token. Internal correlation aid only —
    # not user-facing, not a re-identification vector on its own.
    anonymization_hash = Column(String(64), nullable=True)
    # Forward-compat slot for V1.2 multi-tenancy (per DECISIONS-2026-04-16
    # SQ1). Nullable in V1.1; V1.2 migration will make it NOT NULL after
    # backfilling a tenant for every user + sentinel row.
    tenant_id = Column(Integer, nullable=True, index=True)

    # A2.1 — excludes fixture / seed accounts from the 30-day scan-adoption
    # metric (Lena §1). Default FALSE so existing users are unaffected.
    is_test_user = Column(
        Boolean,
        nullable=False,
        server_default=text("FALSE"),
        default=False,
    )


class Customer(Base):
    """Customer/Client Model for CRM.

    PII fields (names, company, email, phone, address) are encrypted at
    rest via ``EncryptedString`` — CLAUDE.md "Data Privacy Rules
    (CRITICAL)". The raw DB columns hold Fernet ciphertext; the ORM
    round-trips plaintext transparently. See ``db/types.py`` + fix item
    **C1** for the design.

    Because Fernet is non-deterministic, the ``email`` column cannot
    carry a UNIQUE constraint or be searched by equality. The companion
    ``email_hash`` column holds an HMAC-SHA-256 tag (see
    ``core.encryption.hmac_blind_index``) — unique-indexed, searchable,
    and the new ground truth for duplicate detection.

    Previous plain ``String(...)`` columns had per-column length limits
    (email ``String(255)``, street ``String(200)``, …). Those limits
    enforced input hygiene. Because the ciphertext size now drives the
    column type (TEXT), length validation moves up to the Pydantic
    schemas in ``models/customer.py``.
    """

    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    # Basic Info — PII, encrypted at rest (C1).
    first_name = Column(EncryptedString, nullable=False)
    last_name = Column(EncryptedString, nullable=False)
    company_name = Column(EncryptedString, nullable=True)

    # Contact Info — PII, encrypted at rest (C1).
    # ``email`` is ciphertext (no unique / no index — Fernet is non-
    # deterministic). ``email_hash`` is the HMAC-SHA-256 blind-index tag;
    # it carries the uniqueness constraint and is the column we equality-
    # search on. See ``core.encryption.hmac_blind_index``.
    email = Column(EncryptedString, nullable=False)
    email_hash = Column(String(64), nullable=False, unique=True, index=True)
    phone = Column(EncryptedString, nullable=True)
    mobile = Column(EncryptedString, nullable=True)

    # Address — PII, encrypted at rest (C1).
    street = Column(EncryptedString, nullable=True)
    city = Column(EncryptedString, nullable=True)
    postal_code = Column(EncryptedString, nullable=True)
    country = Column(String(100), default="Deutschland")

    # CRM Fields
    customer_type = Column(String(50), default="private")  # private, business
    source = Column(String(100), nullable=True)  # referral, website, walk-in, etc.
    notes = Column(Text, nullable=True)
    tags = Column(JSON, default=list)  # ["VIP", "Stammkunde", etc.]

    # Measurement Library (Mass-Bibliothek)
    ring_size = Column(Float, nullable=True)  # EU ring size (e.g., 52, 54.5)
    chain_length_cm = Column(Float, nullable=True)  # Preferred chain length in cm
    bracelet_length_cm = Column(Float, nullable=True)  # Preferred bracelet length in cm
    allergies = Column(String(500), nullable=True)  # e.g., "Nickel", "Kupfer"
    preferences = Column(
        JSON, default=dict
    )  # {"bevorzugt": "Platin", "style": "modern"}
    style_profile = Column(
        JSON, nullable=True
    )  # V1.1: {metal_tones, finishes, stone_preferences, style_words}
    birthday = Column(DateTime, nullable=True)  # For marketing/gift vouchers

    # Metadata
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # GDPR Art. 17 — scheduled hard-delete date (set on erasure request).
    # After this date the gdpr-cleanup.sh cron job permanently deletes the record.
    deletion_scheduled_at = Column(DateTime, nullable=True, index=True)

    # Soft delete
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    deleted_at = Column(DateTime, nullable=True)
    deleted_by = Column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    deletion_reason = Column(String(500), nullable=True)

    # Beziehungen
    orders = relationship("Order", back_populates="customer")
    measurements = relationship(
        "CustomerMeasurement",
        back_populates="customer",
        cascade="all, delete-orphan",
        order_by="CustomerMeasurement.measured_at.desc()",
    )


# ── C1 — auto-populate email_hash on insert / update ──────────────────
# The ``email_hash`` column carries the UNIQUE constraint for the customer
# table (because the ``email`` column itself is non-deterministic
# ciphertext — see ``db/types.py`` for the design). Application code in
# ``services.customer_service`` already sets ``email_hash`` explicitly on
# create / update, but tests (and any future direct-ORM-insert path)
# frequently construct ``Customer(email=..., ...)`` without thinking
# about the hash. The event hook below derives ``email_hash`` from the
# current ``email`` whenever it's missing or stale, keeping the blind-
# index in lock-step with the plaintext email without a second code
# path for callers to remember.


@event.listens_for(Customer, "before_insert")
def _customer_before_insert(_mapper, _connection, target: "Customer") -> None:
    """Ensure ``email_hash`` is populated on insert.

    If the service layer already set ``email_hash``, we leave it alone.
    If not (direct-ORM construction in tests / seed scripts), we derive
    it from ``email`` so the INSERT doesn't fail the NOT NULL + UNIQUE
    constraint.
    """
    if target.email and not target.email_hash:
        # Import locally to avoid a cycle (encryption → config → logging → …).
        from goldsmith_erp.core.encryption import hmac_blind_index  # noqa: PLC0415
        target.email_hash = hmac_blind_index(target.email)


@event.listens_for(Customer, "before_update")
def _customer_before_update(_mapper, _connection, target: "Customer") -> None:
    """Keep ``email_hash`` in lock-step with ``email`` on update.

    If the email was changed but the hash wasn't recomputed, derive it
    here. Cheap — one HMAC per update.
    """
    if target.email and not target.email_hash:
        from goldsmith_erp.core.encryption import hmac_blind_index  # noqa: PLC0415
        target.email_hash = hmac_blind_index(target.email)


class CustomerMeasurement(Base):
    """
    Massbibliothek — persistent body measurements per customer.

    Goldsmiths capture measurements once and reuse them across all future
    orders, eliminating repeated re-measurement sessions.  Each row stores
    one measurement (e.g. ring size on the left ring finger) with full
    provenance: who measured, when, and any fitting notes.
    """

    __tablename__ = "customer_measurements"

    id = Column(Integer, primary_key=True, index=True)

    # Links
    customer_id = Column(
        Integer,
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    measured_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # What was measured
    measurement_type = Column(
        SAEnum(MeasurementType),
        nullable=False,
        index=True,
    )

    # The numeric value — interpretation depends on measurement_type + unit
    # Ring sizes (EU): inner circumference in mm, range 38-80
    # Chain / neck / wrist / ankle: centimetres
    # Finger circumference: millimetres (raw tape measurement, basis for EU size)
    value = Column(Float, nullable=False)
    unit = Column(String(20), nullable=False)  # "mm", "cm", "EU", "US"

    # Ring-specific anatomy
    hand = Column(SAEnum(HandSide), nullable=True)  # LEFT / RIGHT
    finger = Column(SAEnum(FingerPosition), nullable=True)  # RING, INDEX, …

    # Goldsmith notes — e.g. "Knöchel etwas breiter, Weitungsring empfohlen"
    notes = Column(Text, nullable=True)

    # When the measurement was physically taken (not necessarily = created_at)
    measured_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    # Audit timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    # Beziehungen
    customer = relationship("Customer", back_populates="measurements")
    goldsmith = relationship("User", foreign_keys=[measured_by])

    def __repr__(self) -> str:
        return (
            f"<CustomerMeasurement customer={self.customer_id} "
            f"{self.measurement_type.value}={self.value}{self.unit}>"
        )


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
    price = Column(Float)  # Final customer price (can be manually set)
    status = Column(
        SAEnum(OrderStatusEnum), default=OrderStatusEnum.NEW, nullable=False
    )
    customer_id = Column(
        Integer,
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    deadline = Column(DateTime, nullable=True, index=True)  # Deadline für Kalender
    current_location = Column(String(50), nullable=True)  # Aktueller Lagerort

    # Weight & Material Calculation
    estimated_weight_g = Column(Float, nullable=True)  # Estimated metal weight in grams
    actual_weight_g = Column(Float, nullable=True)  # Actual weight after completion
    scrap_percentage = Column(
        Float, default=5.0
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
        Float, nullable=True
    )  # Auto-calculated material cost
    material_cost_override = Column(Float, nullable=True)  # Manual override if needed
    labor_hours = Column(Float, nullable=True)  # Estimated or actual work hours
    hourly_rate = Column(Float, default=75.00)  # Labor rate (EUR/hour)
    labor_cost = Column(Float, nullable=True)  # labor_hours × hourly_rate

    # Pricing
    profit_margin_percent = Column(Float, default=40.0)  # Profit margin (%)
    vat_rate = Column(Float, default=19.0)  # VAT rate (%)
    calculated_price = Column(Float, nullable=True)  # Auto-calculated final price

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
        DateTime, nullable=True
    )  # Timestamp when order reached COMPLETED/DELIVERED

    # Goldsmith Intake Fields (Pflichtfelder for order confirmation)
    alloy = Column(String(20), nullable=True, index=True)  # '585', '750', '333', etc.
    ring_size_mm = Column(
        Float, nullable=True
    )  # Per-order ring size (mm inner circumference)
    surface_finish = Column(String(50), nullable=True)  # 'Hochglanz', 'Matt', etc.
    fitting_date = Column(DateTime, nullable=True)  # Anprobe-Datum
    has_scrap_gold = Column(Boolean, default=False)  # Altgold vorhanden?
    special_instructions = Column(Text, nullable=True)  # Sonderwuensche

    # ── Slice 2 — Punzierungs-Check + retention tagging ────────────────
    # A2.5 / A2.8 — audit evidence for Feingehaltsgesetz / DIN 8238.
    # Set by the PunzierungsCheckModal flow; marks list is populated with
    # values from A3.2 (e.g. "feingehalt_585", "meisterzeichen").
    punzierung_verified_at = Column(DateTime(timezone=True), nullable=True)
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
    deleted_at = Column(DateTime, nullable=True)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

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
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Beziehungen
    order = relationship("Order", back_populates="comments")
    user = relationship("User")


class Material(Base):
    __tablename__ = "materials"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(String)
    unit_price = Column(Float)
    stock = Column(Float)
    unit = Column(String)  # g, kg, stück, etc.
    image_url = Column(String(500), nullable=True)
    supplier = Column(String(200), nullable=True)
    webshop_url = Column(String(500), nullable=True)
    min_stock = Column(Float, default=10.0, nullable=False)

    # Beziehungen
    orders = relationship(
        "Order", secondary=order_materials, back_populates="materials"
    )


class Activity(Base):
    """Aktivitäts-Presets für Time-Tracking"""

    __tablename__ = "activities"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    category = Column(
        String(50), nullable=False, index=True
    )  # fabrication, administration, waiting
    icon = Column(String(10))  # Emoji
    color = Column(String(7))  # Hex color #FF6B6B
    usage_count = Column(Integer, default=0, index=True)
    average_duration_minutes = Column(Float)
    last_used = Column(DateTime)
    is_custom = Column(Boolean, default=False)
    is_billable = Column(
        Boolean, nullable=False, server_default=text("true"), default=True
    )  # fabrication billable; administration/waiting non-billable by default
    created_by = Column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    created_at = Column(DateTime, default=datetime.utcnow)

    # Beziehungen
    creator = relationship("User", foreign_keys=[created_by])
    time_entries = relationship("TimeEntry", back_populates="activity")


class TimeEntry(Base):
    """Haupt-Zeiterfassung"""

    __tablename__ = "time_entries"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id = Column(
        Integer,
        ForeignKey("orders.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    activity_id = Column(
        Integer, ForeignKey("activities.id"), nullable=False, index=True
    )
    start_time = Column(DateTime, nullable=False, index=True)
    end_time = Column(DateTime, nullable=True)
    duration_minutes = Column(Integer, nullable=True)
    location = Column(String(50))  # workbench_1, vault, etc.
    complexity_rating = Column(Integer)  # 1-5
    quality_rating = Column(Integer)  # 1-5
    rework_required = Column(Boolean, default=False)
    notes = Column(Text)
    extra_metadata = Column(JSON)  # Flexible für zusätzliche Daten
    created_at = Column(DateTime, default=datetime.utcnow)

    # ── Slice 2 — origin + correction tracking + retention ────────────
    # A2-origin — Lena §1 adoption metric. Values: 'manual' | 'scan' |
    # 'recovery' | 'import'. Back-populated to 'manual' for pre-Slice-2
    # rows by the migration; every new row must set this explicitly.
    origin = Column(
        String(20),
        nullable=False,
        server_default=text("'manual'"),
        default="manual",
    )
    # A2.2 — self-FK to the entry this row corrects (admin payroll fix).
    # ON DELETE SET NULL so that deleting the original entry (rare, only
    # via admin tools) leaves the correction in place as a standalone row.
    correction_of = Column(
        String(36),
        ForeignKey(
            "time_entries.id",
            name="fk_time_entries_correction_of_self",
            ondelete="SET NULL",
        ),
        nullable=True,
    )
    # A2.7 — HGB §257 requires 10-year financial retention.
    retention_class = Column(
        String(32),
        nullable=False,
        server_default=text("'financial_10y'"),
        default="financial_10y",
    )

    # Beziehungen
    order = relationship("Order", back_populates="time_entries")
    user = relationship("User")
    activity = relationship("Activity", back_populates="time_entries")
    interruptions = relationship(
        "Interruption", back_populates="time_entry", cascade="all, delete-orphan"
    )
    photos = relationship("OrderPhoto", back_populates="time_entry")


# --------------------------------------------------------------------------- #
# Defence-in-depth guard for `time_entries.extra_metadata` (O3)
# --------------------------------------------------------------------------- #
#
# Layer A (Pydantic `TimeEntryMetadata` on the API boundary) covers every
# legitimate HTTP write. This listener covers the residual surface:
# service-layer code that constructs a `TimeEntry` ORM instance without
# routing through the Pydantic schema, tests, fixtures, seed data, and
# any future code path that bypasses the router. Both insert and update
# paths are hooked.
#
# Limitations (known and documented):
#   * Only fires on ORM-mediated writes. Raw SQL issued via
#     `AsyncSession.execute(insert(TimeEntryModel.__table__)...)` or
#     directly through a DBAPI cursor will NOT trigger this listener —
#     SQLAlchemy's mapper events are an ORM-level mechanism. Raw-SQL
#     writes must be separately covered by the DB-level constraint or
#     a CI lint; see the audit script at
#     `scripts/audit_time_entry_metadata.py` for the compensating
#     control during rollout.
#   * `AsyncSession.execute(update(TimeEntryModel)...)` likewise
#     bypasses the mapper hook. The existing service code uses that
#     pattern (see `TimeTrackingService.update_time_entry`) — the
#     Pydantic layer catches the payload before it reaches there, so
#     the two layers together cover the update path.
#
# Not swallowed: a `ValidationError` here propagates out of the
# flush/commit and aborts the transaction. That is the desired
# behaviour — fail loudly on schema violation rather than silently
# writing PII.

from goldsmith_erp.models.time_entry_metadata import (  # noqa: E402
    TimeEntryMetadata,
)


@event.listens_for(TimeEntry, "before_insert")
@event.listens_for(TimeEntry, "before_update")
def _validate_time_entry_metadata(mapper, connection, target) -> None:
    """Validate ``target.extra_metadata`` against the whitelist schema.

    Runs on every ORM insert / update of a ``TimeEntry`` row before
    the statement is sent to the database. ``None`` and empty-dict
    payloads are accepted (there is nothing to scrub).
    """
    metadata = target.extra_metadata
    if metadata is None or metadata == {}:
        return
    # Raises ValidationError — do not swallow; we want the transaction
    # to fail so the caller sees the schema violation.
    TimeEntryMetadata.model_validate(metadata)


class Interruption(Base):
    """Unterbrechungen während der Arbeit"""

    __tablename__ = "interruptions"

    id = Column(Integer, primary_key=True, index=True)
    time_entry_id = Column(
        String(36),
        ForeignKey("time_entries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reason = Column(String(100), nullable=False)  # customer_call, material_fetch, etc.
    duration_minutes = Column(Integer, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

    # Beziehungen
    time_entry = relationship("TimeEntry", back_populates="interruptions")


class LocationHistory(Base):
    """Lagerort-Verlauf für Aufträge"""

    __tablename__ = "location_history"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    location = Column(String(50), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    changed_by = Column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    # Beziehungen
    order = relationship("Order")
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
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
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
    carat = Column(Float, nullable=True)  # Weight in carats
    quality = Column(String(20), nullable=True)  # 'VS1', 'VVS2', etc. (clarity)
    color = Column(String(20), nullable=True)  # 'D', 'E', 'F' for diamonds
    cut = Column(String(50), nullable=True)  # 'Excellent', 'Very Good', 'Good'
    shape = Column(String(50), nullable=True)  # 'Round', 'Princess', 'Oval'

    # Cost & Quantity
    cost = Column(Float, nullable=False)  # Purchase/estimated cost per stone
    quantity = Column(Integer, default=1)  # Number of identical stones
    total_cost = Column(Float, nullable=True)  # cost × quantity

    # Setting
    setting_type = Column(
        String(100), nullable=True
    )  # 'Prong', 'Bezel', 'Channel', etc.

    # Optional certificate info
    certificate_number = Column(String(100), nullable=True)
    certificate_authority = Column(String(50), nullable=True)  # 'GIA', 'IGI', 'HRD'

    notes = Column(Text, nullable=True)

    # Beziehungen
    order = relationship("Order", back_populates="gemstones")


# ============================================================================
# METAL INVENTORY MANAGEMENT
# ============================================================================


class MetalPurchase(Base):
    """
    Tracks metal purchases for inventory management.

    Each purchase represents a batch of metal bought at a specific price.
    Remaining weight decreases as metal is used for orders.
    """

    __tablename__ = "metal_purchases"

    id = Column(Integer, primary_key=True, index=True)

    # Purchase Details
    date_purchased = Column(
        DateTime, nullable=False, default=datetime.utcnow, index=True
    )
    metal_type = Column(SAEnum(MetalType), nullable=False, index=True)

    # Weight & Pricing
    weight_g = Column(Float, nullable=False)  # Original purchase weight in grams
    remaining_weight_g = Column(Float, nullable=False)  # Decreases as used
    price_total = Column(Float, nullable=False)  # Total price paid (EUR)
    price_per_gram = Column(Float, nullable=False)  # Calculated: price_total / weight_g

    # Supplier Information
    supplier = Column(String(200), nullable=True)
    invoice_number = Column(String(100), nullable=True)

    # Additional Info
    notes = Column(Text, nullable=True)
    lot_number = Column(String(100), nullable=True)  # For tracking/certification

    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    # Relationships
    usage_records = relationship(
        "MaterialUsage", back_populates="metal_purchase", cascade="all, delete-orphan"
    )

    @property
    def used_weight_g(self) -> float:
        """Calculate how much weight has been used from this purchase"""
        return self.weight_g - self.remaining_weight_g

    @property
    def usage_percentage(self) -> float:
        """Calculate what percentage of this batch has been used"""
        if self.weight_g == 0:
            return 100.0
        return (self.used_weight_g / self.weight_g) * 100.0

    @property
    def is_depleted(self) -> bool:
        """Check if this batch is fully consumed"""
        return self.remaining_weight_g <= 0.01  # Allow 0.01g tolerance

    @property
    def remaining_value(self) -> float:
        """Calculate the value of remaining metal in this batch"""
        return self.remaining_weight_g * self.price_per_gram

    def __repr__(self):
        return f"<MetalPurchase {self.metal_type.value} {self.weight_g}g @ {self.price_per_gram:.2f} EUR/g>"


class MaterialUsage(Base):
    """
    Tracks which metal batches were used for which orders.

    Links orders to specific metal purchases, recording exact weight consumed
    and cost at the time of use (for accurate accounting).
    """

    __tablename__ = "material_usage"

    id = Column(Integer, primary_key=True, index=True)

    # Links
    order_id = Column(
        Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    metal_purchase_id = Column(
        Integer,
        ForeignKey("metal_purchases.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Usage Details
    weight_used_g = Column(Float, nullable=False)  # How much was consumed
    cost_at_time = Column(
        Float, nullable=False
    )  # Cost when used (weight * price_per_gram)
    price_per_gram_at_time = Column(
        Float, nullable=False
    )  # Snapshot of price when used

    # Costing Method Used
    costing_method = Column(
        SAEnum(CostingMethod), nullable=False, default=CostingMethod.FIFO
    )

    # Timestamps
    used_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Notes
    notes = Column(Text, nullable=True)

    # ── Slice 2 — alloy override audit + retention + user FK ──────────
    # A2 / R10 — captured when a goldsmith overrides the alloy mismatch
    # (metal_purchase.alloy != order.alloy). Default FALSE so legacy rows
    # back-populate correctly.
    alloy_override = Column(
        Boolean,
        nullable=False,
        server_default=text("FALSE"),
        default=False,
    )
    # A2.3 — DB-nullable freetext reason. Pydantic enforces 3–200 chars.
    override_reason = Column(Text, nullable=True)
    # A2.4 — enum-like category. Allowed values enforced at Pydantic layer:
    #   charge_abweichung | kleinteil | notfall | sonstiges
    override_reason_category = Column(String(32), nullable=True)
    # A2.7 — HGB §257: 10-year retention for financial audit.
    retention_class = Column(
        String(32),
        nullable=False,
        server_default=text("'financial_10y'"),
        default="financial_10y",
    )
    # NEW in Slice 2 — column wasn't in the ORM previously. Anna B2
    # assumed it existed. Nullable so we can backfill via a later slice
    # if needed; new writes (Slice 5) will set it from current_user.id.
    user_id = Column(
        Integer,
        ForeignKey(
            "users.id",
            name="fk_material_usage_user_id_users",
            ondelete="RESTRICT",
        ),
        nullable=True,
    )

    # Relationships
    order = relationship("Order", back_populates="material_usage_records")
    metal_purchase = relationship("MetalPurchase", back_populates="usage_records")
    user = relationship("User", foreign_keys=[user_id])

    def __repr__(self):
        return f"<MaterialUsage Order#{self.order_id} used {self.weight_used_g}g @ {self.price_per_gram_at_time:.2f} EUR/g>"


class InventoryAdjustment(Base):
    """
    Tracks manual inventory adjustments (loss, theft, reclamation, etc.)

    Maintains audit trail for any changes to metal inventory that aren't
    from normal purchase or order consumption.
    """

    __tablename__ = "inventory_adjustments"

    id = Column(Integer, primary_key=True, index=True)

    # Link to metal purchase
    metal_purchase_id = Column(
        Integer,
        ForeignKey("metal_purchases.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Adjustment Details
    adjustment_type = Column(
        String(50), nullable=False
    )  # 'loss', 'theft', 'reclamation', 'correction', 'return'
    weight_change_g = Column(
        Float, nullable=False
    )  # Positive for additions, negative for reductions

    # Reason & Documentation
    reason = Column(Text, nullable=False)
    adjusted_by_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    # Timestamps
    adjusted_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    metal_purchase = relationship("MetalPurchase")
    adjusted_by = relationship("User")

    def __repr__(self):
        return (
            f"<InventoryAdjustment {self.adjustment_type} {self.weight_change_g:+.2f}g>"
        )


class ScrapGold(Base):
    """Scrap gold (Altgold) intake record linked to an order."""

    __tablename__ = "scrap_gold"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(
        Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    customer_id = Column(
        Integer,
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_by = Column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    status = Column(
        SAEnum(ScrapGoldStatus), default=ScrapGoldStatus.RECEIVED, nullable=False
    )

    # Calculated totals
    total_fine_gold_g = Column(Float, default=0.0)
    total_value_eur = Column(Float, default=0.0)
    gold_price_per_g = Column(Float, nullable=True)  # Rate used for calculation
    price_source = Column(String(50), default="fixed_rate")  # daily_rate or fixed_rate

    # Legal documentation
    signature_data = Column(Text, nullable=True)  # Base64 encoded signature image
    signed_at = Column(DateTime, nullable=True)
    receipt_pdf_path = Column(String(500), nullable=True)

    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    order = relationship("Order")
    customer = relationship("Customer")
    creator = relationship("User")
    items = relationship(
        "ScrapGoldItem", back_populates="scrap_gold", cascade="all, delete-orphan"
    )


class ScrapGoldItem(Base):
    """Individual scrap gold item within a scrap gold intake."""

    __tablename__ = "scrap_gold_items"

    id = Column(Integer, primary_key=True, index=True)
    scrap_gold_id = Column(
        Integer,
        ForeignKey("scrap_gold.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    description = Column(String(200), nullable=False)  # "Alter Ehering", "Kette"
    alloy = Column(SAEnum(AlloyType), nullable=False)
    weight_g = Column(Float, nullable=False)  # Total weight in grams
    fine_content_g = Column(Float, nullable=False)  # Calculated: weight * alloy/1000
    photo_path = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    scrap_gold = relationship("ScrapGold", back_populates="items")


# ============================================================================
# METAL PRICE HISTORY
# ============================================================================


class MetalPriceSource(str, enum.Enum):
    """Source of a recorded metal spot price."""

    API = "api"  # Fetched from an external price API
    MANUAL = "manual"  # Entered manually by an admin
    FALLBACK = "fallback"  # Hardcoded fallback used when all other sources failed


class MetalPriceHistory(Base):
    """
    Persisted record of spot prices fetched for gold, silver, and platinum.

    The table serves two purposes:
    1. Audit trail — every price used in cost calculations is traceable.
    2. Last-known-price fallback — when Redis cache is cold AND the external
       API is unreachable the service queries this table for the most recent
       entry per base metal.

    Only base-metal prices are stored (GOLD_24K, SILVER_999, PLATINUM_950).
    Alloy prices (18K, 14K, ...) are derived from these on the fly.
    """

    __tablename__ = "metal_price_history"

    id = Column(Integer, primary_key=True, index=True)
    metal_type = Column(SAEnum(MetalType), nullable=False, index=True)
    price_per_gram_eur = Column(Float, nullable=False)
    source = Column(
        SAEnum(MetalPriceSource), nullable=False, default=MetalPriceSource.API
    )
    fetched_at = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)

    def __repr__(self) -> str:
        return (
            f"<MetalPriceHistory {self.metal_type.value} "
            f"{self.price_per_gram_eur:.4f} EUR/g @ {self.fetched_at}>"
        )


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
    start_datetime = Column(DateTime, nullable=False, index=True)
    end_datetime = Column(DateTime, nullable=True)
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
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
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

    id = Column(Integer, primary_key=True, index=True)

    # Rechnungsnummer: RE-2026-0001 (unique, generated on creation)
    invoice_number = Column(String(20), unique=True, nullable=False, index=True)

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
    issue_date = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
    due_date = Column(DateTime, nullable=False, index=True)  # Faelligkeitsdatum
    paid_date = Column(DateTime, nullable=True)  # Zahlungsdatum

    # Amounts (Betraege)
    subtotal = Column(Float, nullable=False, default=0.0)  # Zwischensumme (netto)
    tax_rate = Column(Float, nullable=False, default=19.0)  # MwSt-Satz in Prozent
    tax_amount = Column(Float, nullable=False, default=0.0)  # MwSt-Betrag
    total = Column(Float, nullable=False, default=0.0)  # Gesamtbetrag (brutto)

    # Optional fields
    notes = Column(Text, nullable=True)  # Anmerkungen
    payment_method = Column(
        String(50), nullable=True
    )  # Zahlungsart (Ueberweisung, Bar, Karte)

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

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
    quantity = Column(Float, nullable=False, default=1.0)
    unit_price = Column(Float, nullable=False)  # Einzelpreis (netto)
    total = Column(
        Float, nullable=False
    )  # Gesamtpreis dieser Position (quantity * unit_price)

    # Relationships
    invoice = relationship("Invoice", back_populates="line_items")


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
        DateTime, nullable=False, index=True
    )  # Gueltig bis (+14 Tage default)
    approved_at = Column(DateTime, nullable=True)  # Genehmigt am
    rejected_at = Column(DateTime, nullable=True)  # Abgelehnt am
    converted_at = Column(DateTime, nullable=True)  # Umgewandelt am

    # Amounts (Betraege)
    subtotal = Column(Float, nullable=False, default=0.0)  # Zwischensumme (netto)
    tax_rate = Column(Float, nullable=False, default=19.0)  # MwSt-Satz in Prozent
    tax_amount = Column(Float, nullable=False, default=0.0)  # MwSt-Betrag
    total = Column(Float, nullable=False, default=0.0)  # Gesamtbetrag (brutto)

    # Customer signature (base64 PNG -- stored for approved quotes)
    customer_signature_data = Column(Text, nullable=True)

    # Optional fields
    notes = Column(Text, nullable=True)  # Anmerkungen

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

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
    quantity = Column(Float, nullable=False, default=1.0)
    unit_price = Column(Float, nullable=False)  # Einzelpreis (netto)
    total = Column(Float, nullable=False)  # Gesamtpreis (quantity * unit_price)

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
    read_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

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
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    responded_at = Column(DateTime, nullable=True)  # Set when accepted/declined

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
        Float, nullable=True
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
    estimated_cost = Column(Float, nullable=True)  # Kostenvoranschlag in EUR
    actual_cost = Column(Float, nullable=True)  # Tatsaechliche Kosten nach Reparatur

    # Dates
    estimated_completion_date = Column(DateTime, nullable=True, index=True)
    actual_completion_date = Column(DateTime, nullable=True)
    customer_notified_at = Column(
        DateTime, nullable=True
    )  # When READY notification was sent
    picked_up_at = Column(DateTime, nullable=True)

    # Soft delete (30-day grace period before hard delete per GDPR Art. 17)
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    deleted_at = Column(DateTime, nullable=True)

    # Audit timestamps
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

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
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
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
    budget_min = Column(Float, nullable=True)  # Finanzdaten — Sichtbarkeitsregeln!
    budget_max = Column(Float, nullable=True)
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
    follow_up_at = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)  # Design-IP
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

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
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    taken_by = Column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    notes = Column(Text)

    consultation = relationship("Consultation", back_populates="photos")
    user = relationship("User")


class CustomerNoGo(Base):
    """Persistentes Kunden-No-Go (z. B. 'kein Nickel'). Warn-Quelle für Aufträge."""

    __tablename__ = "customer_no_gos"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(
        Integer,
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category = Column(SAEnum(NoGoCategory), nullable=False)
    value = Column(String(200), nullable=False)
    note = Column(Text, nullable=True)
    source_consultation_id = Column(
        Integer, ForeignKey("consultations.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    customer = relationship("Customer")


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
    submitted_at = Column(DateTime, nullable=True)  # Eingereicht am
    approved_at = Column(DateTime, nullable=True)  # Genehmigt am
    stamped_at = Column(DateTime, nullable=True)  # Gestempelt am

    # Free-text notes (e.g. rejection reason or goldsmith observations)
    notes = Column(Text, nullable=True)

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
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
    metal_weight_g = Column(Float, nullable=True)  # Metallgewicht in Gramm
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
    valuation_date = Column(
        DateTime, nullable=False, default=datetime.utcnow, index=True
    )
    valid_until = Column(DateTime, nullable=False, index=True)  # +2 Jahre default

    # Goldsmith credentials shown on certificate
    goldsmith_name = Column(String(200), nullable=False)
    goldsmith_qualification = Column(
        String(200), nullable=True
    )  # "Goldschmiedemeister"

    # Generated PDF path (stored on disk / S3 in production)
    pdf_path = Column(String(500), nullable=True)

    # Audit
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
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


class CustomMetalType(Base):
    """User-defined metal types that extend the built-in MetalType enum.

    Goldsmiths can define workshop-specific alloys (e.g. "Rotgold 333",
    "Palladium 500", a supplier-specific alloy) that are not covered by the
    standard 15-value MetalType enum.  The frontend shows built-in and custom
    types side-by-side in all metal-type dropdowns.
    """

    __tablename__ = "custom_metal_types"

    id = Column(Integer, primary_key=True, index=True)

    # Machine-readable identifier — must be unique across custom types and must
    # not collide with any MetalType enum value (e.g. "gold_18k").
    code = Column(String(50), unique=True, nullable=False, index=True)

    # Human-readable label shown in the UI (e.g. "Roségold 375 (9K)")
    display_name = Column(String(100), nullable=False)

    # Fine-content ratio: 0.0 – 1.0 (e.g. 0.375 for 9K gold)
    fine_content_ratio = Column(Float, nullable=False)

    # Base precious metal category for grouping in dropdowns
    base_metal = Column(
        String(20), nullable=False
    )  # "gold", "silver", "platinum", "palladium"

    # Optional hex colour for UI badge rendering (e.g. "#D4A843")
    color = Column(String(7), nullable=True)

    # Soft-delete flag — deactivated types are hidden from dropdowns but
    # preserved for historical records (e.g. MetalPurchase rows still referencing them).
    is_active = Column(Boolean, default=True, nullable=False, index=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<CustomMetalType code={self.code!r} display_name={self.display_name!r}>"
        )


# ============================================================================
# CUSTOMER AUDIT & GDPR
# ============================================================================


class CustomerAuditLog(Base):
    """Audit trail for customer data access and changes."""

    __tablename__ = "customer_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(
        Integer,
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action = Column(String(50), nullable=False)
    entity = Column(String(50), nullable=True)
    entity_id = Column(Integer, nullable=True)
    field_name = Column(String(100), nullable=True)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    user_email = Column(String(255), nullable=True)
    user_role = Column(String(50), nullable=True)
    user_agent = Column(String(500), nullable=True)
    details = Column(JSON, nullable=True)
    ip_address = Column(String(45), nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class GDPRRequest(Base):
    """Tracks GDPR data export and erasure requests."""

    __tablename__ = "gdpr_requests"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(
        Integer, ForeignKey("customers.id", ondelete="SET NULL"), nullable=True
    )
    request_type = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    requested_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    requested_by = Column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    notes = Column(Text, nullable=True)


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
    unit_price = Column(Float, nullable=True)
    material_id = Column(
        Integer, ForeignKey("materials.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

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
    changed_at = Column(DateTime, default=datetime.utcnow, nullable=False)
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
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_scanned_at = Column(DateTime, nullable=True)
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
    scanned_at = Column(DateTime, primary_key=True, nullable=False)
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
    synced_at = Column(DateTime, nullable=True)
    idempotency_key = Column(String(36), nullable=True)
    # A1.2 — client-side FAB tap timestamp for adoption metrics.
    client_tap_at = Column(DateTime(timezone=True), nullable=True)
    # A1.3 — server-side resolution completion, pairs with client_tap_at.
    server_resolved_at = Column(DateTime(timezone=True), nullable=True)
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
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    creator = relationship("User", foreign_keys=[created_by])


# ============================================================================
# PERFORMANCE INDEXES
# ============================================================================

# Performance indexes for frequent query patterns
Index("ix_time_entries_end_time", TimeEntry.end_time)
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

# Slice 2 — security floor + audit indexes. Names match the Alembic
# migration (20260419_security_floor) so both create_all() and
# `alembic upgrade head` produce identical index shapes.
#
# Composite index for the 30-day scan-adoption metric query (Lena §1).
Index(
    "idx_time_entries_origin_created_at",
    TimeEntry.origin,
    TimeEntry.created_at,
)
# Partial on PG / plain on SQLite — the migration emits the WHERE clause
# conditionally, and create_all honours the kwargs below on PG only.
Index(
    "idx_time_entries_correction_of",
    TimeEntry.correction_of,
    postgresql_where=TimeEntry.correction_of.isnot(None),
)
Index(
    "idx_orders_punzierung_verified_at",
    Order.punzierung_verified_at,
    postgresql_where=Order.punzierung_verified_at.isnot(None),
)
Index(
    "idx_users_is_test_user",
    User.is_test_user,
    postgresql_where=User.is_test_user.is_(True),
)
# retention_class indexes — small, selective buckets for the future
# retention engine.
Index("idx_orders_retention_class", Order.retention_class)
Index("idx_material_usage_retention_class", MaterialUsage.retention_class)
Index("idx_time_entries_retention_class", TimeEntry.retention_class)
