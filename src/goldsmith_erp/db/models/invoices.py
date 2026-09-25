"""Invoices, invoice lines, workshop settings and number sequences."""

from decimal import Decimal

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.orm import relationship

from goldsmith_erp.core.timeutil import utcnow
from goldsmith_erp.db.models.base import (
    MONEY_NUMERIC,
    PERCENT_NUMERIC,
    WEIGHT_NUMERIC,
    Base,
    InvoiceLineType,
    InvoiceStatus,
    SAEnum,
)
from goldsmith_erp.db.types import EncryptedString, UtcDateTime

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
