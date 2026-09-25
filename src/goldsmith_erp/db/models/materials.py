"""Material inventory, material usage and inventory adjustments."""

from decimal import Decimal

from sqlalchemy import (
    Boolean,
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
    Table,
    Text,
    text,
)
from sqlalchemy.orm import relationship

from goldsmith_erp.core.timeutil import utcnow
from goldsmith_erp.db.models.base import (
    MONEY_NUMERIC,
    PRICE_PER_GRAM_NUMERIC,
    WEIGHT_NUMERIC,
    Base,
    CostingMethod,
    SAEnum,
)
from goldsmith_erp.db.types import UtcDateTime

# Many-to-Many zwischen Material und Order
order_materials = Table(
    "order_materials",
    Base.metadata,
    Column("order_id", Integer, ForeignKey("orders.id"), primary_key=True),
    Column("material_id", Integer, ForeignKey("materials.id"), primary_key=True),
)


class Material(Base):
    __tablename__ = "materials"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(String)
    unit_price = Column(MONEY_NUMERIC)
    stock = Column(WEIGHT_NUMERIC)
    unit = Column(String)  # g, kg, stück, etc.
    image_url = Column(String(500), nullable=True)
    supplier = Column(String(200), nullable=True)
    webshop_url = Column(String(500), nullable=True)
    min_stock = Column(WEIGHT_NUMERIC, default=Decimal("10.0"), nullable=False)

    # Beziehungen
    orders = relationship(
        "Order", secondary=order_materials, back_populates="materials"
    )


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
    weight_used_g = Column(WEIGHT_NUMERIC, nullable=False)  # How much was consumed
    cost_at_time = Column(
        MONEY_NUMERIC, nullable=False
    )  # Cost when used (weight * price_per_gram)
    price_per_gram_at_time = Column(
        PRICE_PER_GRAM_NUMERIC, nullable=False
    )  # Snapshot of price when used

    # Costing Method Used
    costing_method = Column(
        SAEnum(CostingMethod), nullable=False, default=CostingMethod.FIFO
    )

    # Timestamps
    used_at = Column(UtcDateTime, default=utcnow, nullable=False, index=True)
    created_at = Column(UtcDateTime, default=utcnow, nullable=False)

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
        WEIGHT_NUMERIC, nullable=False
    )  # Positive for additions, negative for reductions

    # Reason & Documentation
    reason = Column(Text, nullable=False)
    adjusted_by_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    # Timestamps
    adjusted_at = Column(UtcDateTime, default=utcnow, nullable=False, index=True)

    # Relationships
    metal_purchase = relationship("MetalPurchase")
    adjusted_by = relationship("User")

    def __repr__(self):
        return (
            f"<InventoryAdjustment {self.adjustment_type} {self.weight_change_g:+.2f}g>"
        )


Index("idx_material_usage_retention_class", MaterialUsage.retention_class)
