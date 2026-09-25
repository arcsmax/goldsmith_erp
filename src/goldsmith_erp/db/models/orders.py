"""Orders, order events/comments/items/photos, gemstones, hallmarks, valuations, handoffs."""

import enum
import uuid
from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Column,
    Date,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
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
    MetalType,
    OrderStatusEnum,
    SAEnum,
)
from goldsmith_erp.db.models.materials import order_materials
from goldsmith_erp.db.types import EncryptedString, UtcDateTime


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


Index("ix_orders_customer_deleted", Order.customer_id, Order.is_deleted)
Index(
    "idx_orders_punzierung_verified_at",
    Order.punzierung_verified_at,
    postgresql_where=Order.punzierung_verified_at.isnot(None),
)
# retention_class indexes — small, selective buckets for the future
# retention engine.
Index("idx_orders_retention_class", Order.retention_class)
