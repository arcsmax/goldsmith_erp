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
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Beziehungen
    orders = relationship("Order", back_populates="customer")

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String)
    description = Column(String)
    price = Column(Float)
    status = Column(SAEnum(OrderStatusEnum), default=OrderStatusEnum.NEW, nullable=False)
    customer_id = Column(Integer, ForeignKey("users.id"))
    current_location = Column(String(50), nullable=True)  # Aktueller Lagerort
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Beziehungen
    customer = relationship("User", back_populates="orders")
    materials = relationship("Material", secondary=order_materials, back_populates="materials")

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