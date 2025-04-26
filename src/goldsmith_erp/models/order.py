# src/goldsmith_erp/models/order.py
from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List

class MaterialBase(BaseModel):
    id: int
    name: str
    unit_price: float
    
    class Config:
        orm_mode = True

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

class OrderRead(OrderBase):
    """Schema für Order-Anzeige."""
    id: int
    status: str
    customer_id: int
    created_at: datetime
    updated_at: datetime
    materials: Optional[List[MaterialBase]] = None

    class Config:
        orm_mode = True