from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Table, Boolean, Enum as SAEnum, Text
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import enum
import uuid

Base = declarative_base()


class OrderStatusEnum(str, enum.Enum):
    """Enumerated order statuses for consistency and validation."""
    NEW = "new"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    DELIVERED = "delivered"


class UserRole(str, enum.Enum):
    """User roles for RBAC (Role-Based Access Control)."""
    ADMIN = "admin"  # Full system access
    USER = "user"    # Standard user access

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
    role = Column(SAEnum(UserRole), default=UserRole.USER, nullable=False, index=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class Customer(Base):
    """Customer/Client Model for CRM"""
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    # Basic Info
    first_name = Column(String(100), nullable=False, index=True)
    last_name = Column(String(100), nullable=False, index=True)
    company_name = Column(String(200), nullable=True, index=True)

    # Contact Info
    email = Column(String(255), nullable=False, unique=True, index=True)
    phone = Column(String(50), nullable=True)
    mobile = Column(String(50), nullable=True)

    # Address
    street = Column(String(200), nullable=True)
    city = Column(String(100), nullable=True)
    postal_code = Column(String(20), nullable=True)
    country = Column(String(100), default="Deutschland")

    # CRM Fields
    customer_type = Column(String(50), default="private")  # private, business
    source = Column(String(100), nullable=True)  # referral, website, walk-in, etc.
    notes = Column(Text, nullable=True)
    tags = Column(JSON, default=list)  # ["VIP", "Stammkunde", etc.]

    # Metadata
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Beziehungen
    orders = relationship("Order", back_populates="customer")

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    description = Column(String)
    price = Column(Float)  # Final customer price (can be manually set)
    status = Column(SAEnum(OrderStatusEnum), default=OrderStatusEnum.NEW, nullable=False)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False, index=True)
    deadline = Column(DateTime, nullable=True, index=True)  # Deadline für Kalender
    current_location = Column(String(50), nullable=True)  # Aktueller Lagerort

    # Weight & Material Calculation
    estimated_weight_g = Column(Float, nullable=True)  # Estimated metal weight in grams
    actual_weight_g = Column(Float, nullable=True)  # Actual weight after completion
    scrap_percentage = Column(Float, default=5.0)  # Material loss percentage (default 5%)

    # Metal Inventory Integration
    metal_type = Column(SAEnum(MetalType), nullable=True, index=True)  # Which metal type to use
    costing_method_used = Column(SAEnum(CostingMethod), default=CostingMethod.FIFO, nullable=True)  # Costing method
    specific_metal_purchase_id = Column(Integer, ForeignKey("metal_purchases.id", ondelete="SET NULL"), nullable=True)  # For SPECIFIC method

    # Cost Calculation
    material_cost_calculated = Column(Float, nullable=True)  # Auto-calculated material cost
    material_cost_override = Column(Float, nullable=True)  # Manual override if needed
    labor_hours = Column(Float, nullable=True)  # Estimated or actual work hours
    hourly_rate = Column(Float, default=75.00)  # Labor rate (EUR/hour)
    labor_cost = Column(Float, nullable=True)  # labor_hours × hourly_rate

    # Pricing
    profit_margin_percent = Column(Float, default=40.0)  # Profit margin (%)
    vat_rate = Column(Float, default=19.0)  # VAT rate (%)
    calculated_price = Column(Float, nullable=True)  # Auto-calculated final price

    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Beziehungen
    customer = relationship("Customer", back_populates="orders")
    materials = relationship("Material", secondary=order_materials, back_populates="materials")
    gemstones = relationship("Gemstone", back_populates="order", cascade="all, delete-orphan")
    material_usage_records = relationship("MaterialUsage", back_populates="order", cascade="all, delete-orphan")
    specific_metal_purchase = relationship("MetalPurchase")  # For SPECIFIC costing method

class Material(Base):
    __tablename__ = "materials"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(String)
    unit_price = Column(Float)
    stock = Column(Float)
    unit = Column(String)  # g, kg, stück, etc.

    # Beziehungen
    orders = relationship("Order", secondary=order_materials, back_populates="materials")


class Activity(Base):
    """Aktivitäts-Presets für Time-Tracking"""
    __tablename__ = "activities"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    category = Column(String(50), nullable=False, index=True)  # fabrication, administration, waiting
    icon = Column(String(10))  # Emoji
    color = Column(String(7))  # Hex color #FF6B6B
    usage_count = Column(Integer, default=0, index=True)
    average_duration_minutes = Column(Float)
    last_used = Column(DateTime)
    is_custom = Column(Boolean, default=False)
    created_by = Column(Integer, ForeignKey("users.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Beziehungen
    creator = relationship("User", foreign_keys=[created_by])
    time_entries = relationship("TimeEntry", back_populates="activity")


class TimeEntry(Base):
    """Haupt-Zeiterfassung"""
    __tablename__ = "time_entries"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    activity_id = Column(Integer, ForeignKey("activities.id"), nullable=False, index=True)
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

    # Beziehungen
    order = relationship("Order")
    user = relationship("User")
    activity = relationship("Activity", back_populates="time_entries")
    interruptions = relationship("Interruption", back_populates="time_entry", cascade="all, delete-orphan")
    photos = relationship("OrderPhoto", back_populates="time_entry")


class Interruption(Base):
    """Unterbrechungen während der Arbeit"""
    __tablename__ = "interruptions"

    id = Column(Integer, primary_key=True, index=True)
    time_entry_id = Column(String(36), ForeignKey("time_entries.id", ondelete="CASCADE"), nullable=False, index=True)
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
    changed_by = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Beziehungen
    order = relationship("Order")
    user = relationship("User")


class OrderPhoto(Base):
    """Foto-Dokumentation für Aufträge"""
    __tablename__ = "order_photos"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    order_id = Column(Integer, ForeignKey("orders.id"), nullable=False, index=True)
    time_entry_id = Column(String(36), ForeignKey("time_entries.id", ondelete="SET NULL"), nullable=True)
    file_path = Column(String(500), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    taken_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    notes = Column(Text)

    # Beziehungen
    order = relationship("Order")
    time_entry = relationship("TimeEntry", back_populates="photos")
    user = relationship("User")


class Gemstone(Base):
    """Edelsteine für Aufträge"""
    __tablename__ = "gemstones"

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)

    # Gemstone Details
    type = Column(String(50), nullable=False)  # 'diamond', 'ruby', 'sapphire', 'emerald'
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
    setting_type = Column(String(100), nullable=True)  # 'Prong', 'Bezel', 'Channel', etc.

    # Optional certificate info
    certificate_number = Column(String(100), nullable=True)
    certificate_authority = Column(String(50), nullable=True)  # 'GIA', 'IGI', 'HRD'

    notes = Column(Text, nullable=True)

    # Beziehungen
    order = relationship("Order", back_populates="gemstones")


# ============================================================================
# METAL INVENTORY MANAGEMENT
# ============================================================================


class MetalType(str, enum.Enum):
    """Standard metal types used in goldsmith workshop"""
    GOLD_24K = "gold_24k"      # 999.9 Feingold
    GOLD_22K = "gold_22k"      # 916 Gold
    GOLD_18K = "gold_18k"      # 750 Gold
    GOLD_14K = "gold_14k"      # 585 Gold
    GOLD_9K = "gold_9k"        # 375 Gold
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
    FIFO = "fifo"              # First In, First Out
    LIFO = "lifo"              # Last In, First Out
    AVERAGE = "average"        # Weighted Average Cost
    SPECIFIC = "specific"      # Specific Identification (manual selection)


class MetalPurchase(Base):
    """
    Tracks metal purchases for inventory management.

    Each purchase represents a batch of metal bought at a specific price.
    Remaining weight decreases as metal is used for orders.
    """
    __tablename__ = "metal_purchases"

    id = Column(Integer, primary_key=True, index=True)

    # Purchase Details
    date_purchased = Column(DateTime, nullable=False, default=datetime.utcnow, index=True)
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
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    usage_records = relationship("MaterialUsage", back_populates="metal_purchase", cascade="all, delete-orphan")

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
    order_id = Column(Integer, ForeignKey("orders.id", ondelete="CASCADE"), nullable=False, index=True)
    metal_purchase_id = Column(Integer, ForeignKey("metal_purchases.id", ondelete="RESTRICT"), nullable=False, index=True)

    # Usage Details
    weight_used_g = Column(Float, nullable=False)  # How much was consumed
    cost_at_time = Column(Float, nullable=False)   # Cost when used (weight * price_per_gram)
    price_per_gram_at_time = Column(Float, nullable=False)  # Snapshot of price when used

    # Costing Method Used
    costing_method = Column(SAEnum(CostingMethod), nullable=False, default=CostingMethod.FIFO)

    # Timestamps
    used_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Notes
    notes = Column(Text, nullable=True)

    # Relationships
    order = relationship("Order", back_populates="material_usage_records")
    metal_purchase = relationship("MetalPurchase", back_populates="usage_records")

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
    metal_purchase_id = Column(Integer, ForeignKey("metal_purchases.id", ondelete="RESTRICT"), nullable=False, index=True)

    # Adjustment Details
    adjustment_type = Column(String(50), nullable=False)  # 'loss', 'theft', 'reclamation', 'correction', 'return'
    weight_change_g = Column(Float, nullable=False)  # Positive for additions, negative for reductions

    # Reason & Documentation
    reason = Column(Text, nullable=False)
    adjusted_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    # Timestamps
    adjusted_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Relationships
    metal_purchase = relationship("MetalPurchase")
    adjusted_by = relationship("User")

    def __repr__(self):
        return f"<InventoryAdjustment {self.adjustment_type} {self.weight_change_g:+.2f}g>"