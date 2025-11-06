from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Table, Boolean, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime

Base = declarative_base()

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
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    first_name = Column(String)
    last_name = Column(String)
    role = Column(String, default="goldsmith")  # admin, goldsmith, receptionist, quality_manager
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Beziehungen
    orders = relationship("Order", back_populates="customer")

class Order(Base):
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    description = Column(Text)
    price = Column(Float)
    status = Column(String, default="new", nullable=False, index=True)  # new, in_progress, completed, delivered
    customer_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    delivery_date = Column(DateTime)
    notes = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Beziehungen
    customer = relationship("User", back_populates="orders")
    materials = relationship("Material", secondary=order_materials, back_populates="orders")

class Material(Base):
    __tablename__ = "materials"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False, index=True)
    material_type = Column(String, nullable=False, index=True)  # gold, silver, platinum, stone, tool, other
    description = Column(Text)
    unit_price = Column(Float, nullable=False)
    stock = Column(Float, nullable=False, default=0)
    unit = Column(String, nullable=False)  # g, kg, pcs (pieces), ct (carat)
    min_stock = Column(Float, default=0)  # Minimum stock level for alerts
    properties = Column(JSONB)  # Type-specific fields: purity, size, color, quality, etc.
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Beziehungen
    orders = relationship("Order", secondary=order_materials, back_populates="materials")