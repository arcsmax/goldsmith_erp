# src/goldsmith_erp/models/material.py

from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional


class MaterialBase(BaseModel):
    """Basis-Schema für Materials."""
    name: str
    description: Optional[str] = None
    unit_price: float
    stock: float
    unit: str  # z.B. "g", "kg", "Stück", "ct" (Karat)


class MaterialCreate(MaterialBase):
    """Schema für Material-Erstellung."""
    pass


class MaterialUpdate(BaseModel):
    """Schema für Material-Updates."""
    name: Optional[str] = None
    description: Optional[str] = None
    unit_price: Optional[float] = None
    stock: Optional[float] = None
    unit: Optional[str] = None


class MaterialRead(MaterialBase):
    """Schema für Material-Anzeige."""
    id: int

    model_config = ConfigDict(from_attributes=True)


class MaterialWithStock(MaterialRead):
    """
    Erweitertes Material-Schema mit zusätzlichen Stock-Informationen.
    Nützlich für Bestandsberichte.
    """
    stock_value: Optional[float] = None  # stock * unit_price

    @classmethod
    def from_material(cls, material):
        """Erstellt MaterialWithStock aus Material-Model."""
        return cls(
            id=material.id,
            name=material.name,
            description=material.description,
            unit_price=material.unit_price,
            stock=material.stock,
            unit=material.unit,
            stock_value=material.stock * material.unit_price
        )
