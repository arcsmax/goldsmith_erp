# src/goldsmith_erp/models/order.py
from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional, List

class MaterialBase(BaseModel):
    id: int
    name: str
    unit_price: float

    model_config = ConfigDict(from_attributes=True)

class OrderBase(BaseModel):
    """Basis-Schema für Orders."""
    title: str
    description: str
    price: Optional[float] = None

class OrderCreate(OrderBase):
    """Schema für Order-Erstellung."""
    customer_id: int
    materials: Optional[List[int]] = None  # Liste von Material-IDs

class OrderUpdate(BaseModel):
    """Schema für Order-Updates."""
    title: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    status: Optional[str] = None
    current_location: Optional[str] = None

class OrderRead(OrderBase):
    """Schema für Order-Anzeige."""
    id: int
    status: str
    customer_id: int
    current_location: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    materials: Optional[List[MaterialBase]] = None

    model_config = ConfigDict(from_attributes=True)