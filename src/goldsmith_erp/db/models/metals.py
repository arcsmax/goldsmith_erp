"""Metal purchases, metal price history and custom metal types."""

import enum
from decimal import Decimal

from sqlalchemy import Boolean, Column, Float, Integer, String, Text
from sqlalchemy.orm import relationship

from goldsmith_erp.core.timeutil import utcnow
from goldsmith_erp.db.models.base import (
    MONEY_NUMERIC,
    PRICE_PER_GRAM_NUMERIC,
    WEIGHT_NUMERIC,
    Base,
    MetalType,
    SAEnum,
)
from goldsmith_erp.db.types import UtcDateTime

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
    date_purchased = Column(UtcDateTime, nullable=False, default=utcnow, index=True)
    metal_type = Column(SAEnum(MetalType), nullable=False, index=True)

    # Weight & Pricing
    weight_g = Column(
        WEIGHT_NUMERIC, nullable=False
    )  # Original purchase weight in grams
    remaining_weight_g = Column(WEIGHT_NUMERIC, nullable=False)  # Decreases as used
    price_total = Column(MONEY_NUMERIC, nullable=False)  # Total price paid (EUR)
    price_per_gram = Column(
        PRICE_PER_GRAM_NUMERIC, nullable=False
    )  # Calculated: price_total / weight_g

    # Supplier Information
    supplier = Column(String(200), nullable=True)
    invoice_number = Column(String(100), nullable=True)

    # Additional Info
    notes = Column(Text, nullable=True)
    lot_number = Column(String(100), nullable=True)  # For tracking/certification

    # Timestamps
    created_at = Column(UtcDateTime, default=utcnow, nullable=False)
    updated_at = Column(UtcDateTime, default=utcnow, onupdate=utcnow, nullable=False)

    # Relationships
    usage_records = relationship(
        "MaterialUsage", back_populates="metal_purchase", cascade="all, delete-orphan"
    )

    @property
    def used_weight_g(self) -> Decimal:
        """Calculate how much weight has been used from this purchase"""
        return Decimal(str(self.weight_g)) - Decimal(str(self.remaining_weight_g))

    @property
    def usage_percentage(self) -> float:
        """Calculate what percentage of this batch has been used"""
        if self.weight_g == 0:
            return 100.0
        return float(self.used_weight_g / Decimal(str(self.weight_g)) * 100)

    @property
    def is_depleted(self) -> bool:
        """Check if this batch is fully consumed"""
        return self.remaining_weight_g <= 0.01  # Allow 0.01g tolerance

    @property
    def remaining_value(self) -> Decimal:
        """Calculate the value of remaining metal in this batch"""
        return Decimal(str(self.remaining_weight_g)) * Decimal(str(self.price_per_gram))

    def __repr__(self):
        return f"<MetalPurchase {self.metal_type.value} {self.weight_g}g @ {self.price_per_gram:.2f} EUR/g>"


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
    price_per_gram_eur = Column(PRICE_PER_GRAM_NUMERIC, nullable=False)
    source = Column(
        SAEnum(MetalPriceSource), nullable=False, default=MetalPriceSource.API
    )
    fetched_at = Column(UtcDateTime, nullable=False, default=utcnow, index=True)

    def __repr__(self) -> str:
        return (
            f"<MetalPriceHistory {self.metal_type.value} "
            f"{self.price_per_gram_eur:.4f} EUR/g @ {self.fetched_at}>"
        )


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

    created_at = Column(UtcDateTime, default=utcnow, nullable=False)
    updated_at = Column(UtcDateTime, default=utcnow, onupdate=utcnow, nullable=False)

    def __repr__(self) -> str:
        return (
            f"<CustomMetalType code={self.code!r} display_name={self.display_name!r}>"
        )
