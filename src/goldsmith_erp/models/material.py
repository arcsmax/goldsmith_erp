# src/goldsmith_erp/models/material.py

from pydantic import BaseModel, ConfigDict, Field, field_validator
from datetime import datetime
from typing import Optional


class MaterialBase(BaseModel):
    """Basis-Schema für Materials mit Input Validation."""
    name: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Material name (1-200 characters)"
    )
    description: Optional[str] = Field(
        None,
        max_length=1000,
        description="Material description (max 1000 characters)"
    )
    unit_price: float = Field(
        ...,
        gt=0,
        description="Unit price (must be positive)"
    )
    stock: float = Field(
        ...,
        ge=0,
        description="Stock quantity (must be non-negative)"
    )
    unit: str = Field(
        ...,
        min_length=1,
        max_length=20,
        description="Unit of measurement (e.g., 'g', 'kg', 'Stück', 'ct')"
    )

    @field_validator('unit_price')
    @classmethod
    def validate_unit_price(cls, v: float) -> float:
        """Validate unit price is reasonable."""
        if v > 100_000:  # 100k per unit max
            raise ValueError("Unit price exceeds maximum allowed value (100,000)")
        return v

    @field_validator('stock')
    @classmethod
    def validate_stock(cls, v: float) -> float:
        """Validate stock quantity is reasonable."""
        if v > 1_000_000:  # 1 million units max
            raise ValueError("Stock quantity exceeds maximum allowed value (1,000,000)")
        return v


class MaterialCreate(MaterialBase):
    """Schema für Material-Erstellung mit Validation."""
    pass


class MaterialUpdate(BaseModel):
    """Schema für Material-Updates mit Input Validation."""
    name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=200,
        description="Material name"
    )
    description: Optional[str] = Field(
        None,
        max_length=1000,
        description="Material description"
    )
    unit_price: Optional[float] = Field(
        None,
        gt=0,
        description="Unit price (must be positive)"
    )
    stock: Optional[float] = Field(
        None,
        ge=0,
        description="Stock quantity (must be non-negative)"
    )
    unit: Optional[str] = Field(
        None,
        min_length=1,
        max_length=20,
        description="Unit of measurement"
    )

    @field_validator('unit_price')
    @classmethod
    def validate_unit_price(cls, v: Optional[float]) -> Optional[float]:
        """Validate unit price is reasonable."""
        if v is not None and v > 100_000:
            raise ValueError("Unit price exceeds maximum allowed value (100,000)")
        return v

    @field_validator('stock')
    @classmethod
    def validate_stock(cls, v: Optional[float]) -> Optional[float]:
        """Validate stock quantity is reasonable."""
        if v is not None and v > 1_000_000:
            raise ValueError("Stock quantity exceeds maximum allowed value (1,000,000)")
        return v


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
