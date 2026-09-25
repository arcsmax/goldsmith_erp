"""Quotes (Kostenvoranschlaege) and quote lines."""

import enum
from decimal import Decimal

from sqlalchemy import Column, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import relationship

from goldsmith_erp.core.timeutil import utcnow
from goldsmith_erp.db.models.base import (
    MONEY_NUMERIC,
    PERCENT_NUMERIC,
    WEIGHT_NUMERIC,
    Base,
    SAEnum,
)
from goldsmith_erp.db.types import UtcDateTime

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
