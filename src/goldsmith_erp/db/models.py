from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Table, Boolean, Enum as SAEnum
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base
from datetime import datetime
import enum

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
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Beziehungen
    customer = relationship("User", back_populates="orders")
    materials = relationship("Material", secondary=order_materials, back_populates="orders")

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