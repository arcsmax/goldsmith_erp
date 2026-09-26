"""Scrap gold (Altgold) intake."""

from decimal import Decimal

from sqlalchemy import Column, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from goldsmith_erp.core.timeutil import utcnow
from goldsmith_erp.db.models.base import (
    MONEY_NUMERIC,
    PRICE_PER_GRAM_NUMERIC,
    WEIGHT_NUMERIC,
    AlloyType,
    Base,
    SAEnum,
    ScrapGoldStatus,
)
from goldsmith_erp.db.types import EncryptedString, UtcDateTime


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
    total_fine_gold_g = Column(WEIGHT_NUMERIC, default=Decimal("0.0"))
    total_value_eur = Column(MONEY_NUMERIC, default=Decimal("0.0"))
    gold_price_per_g = Column(
        PRICE_PER_GRAM_NUMERIC, nullable=True
    )  # Rate used for calculation
    price_source = Column(String(50), default="fixed_rate")  # daily_rate or fixed_rate

    # Legal documentation
    signature_data = Column(Text, nullable=True)  # Base64 encoded signature image
    signed_at = Column(UtcDateTime, nullable=True)
    receipt_pdf_path = Column(String(500), nullable=True)

    notes = Column(Text, nullable=True)
    created_at = Column(UtcDateTime, default=utcnow)
    updated_at = Column(UtcDateTime, default=utcnow, onupdate=utcnow)

    # W2-16 / DOM-21 (decision D-16): Ankaufsbuch identification. Optional,
    # required before SIGNED above SCRAP_GOLD_ID_THRESHOLD_EUR. Number and
    # issuing authority are PII -> EncryptedString. Migration
    # 20260925_w216_altgold_id.
    id_document_type = Column(String(30), nullable=True)
    id_document_number = Column(EncryptedString, nullable=True)
    id_issuing_authority = Column(EncryptedString, nullable=True)
    id_checked_by = Column(
        Integer,
        ForeignKey(
            "users.id", name="fk_scrap_gold_id_checked_by_users", ondelete="SET NULL"
        ),
        nullable=True,
    )
    id_checked_at = Column(UtcDateTime, nullable=True)

    # Relationships
    order = relationship("Order")
    customer = relationship("Customer")
    creator = relationship("User", foreign_keys=[created_by])
    id_checker = relationship("User", foreign_keys=[id_checked_by])
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
    weight_g = Column(WEIGHT_NUMERIC, nullable=False)  # Total weight in grams
    fine_content_g = Column(
        WEIGHT_NUMERIC, nullable=False
    )  # Calculated: weight * alloy/1000
    photo_path = Column(String(500), nullable=True)
    created_at = Column(UtcDateTime, default=utcnow)

    # Relationships
    scrap_gold = relationship("ScrapGold", back_populates="items")
