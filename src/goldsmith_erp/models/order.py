# src/goldsmith_erp/models/order.py
from pydantic import BaseModel, ConfigDict, Field, field_validator
from datetime import datetime
from typing import Optional, List
from decimal import Decimal

from goldsmith_erp.db.models import OrderStatusEnum


class MaterialBase(BaseModel):
    """Material schema for order display."""
    id: int = Field(..., gt=0, description="Material ID (must be positive)")
    name: str = Field(..., min_length=1, max_length=200, description="Material name")
    unit_price: float = Field(..., ge=0, description="Unit price (must be non-negative)")

    model_config = ConfigDict(from_attributes=True)


class OrderBase(BaseModel):
    """Basis-Schema für Orders mit Input Validation."""
    title: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Order title (1-200 characters)"
    )
    description: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Order description (1-2000 characters)"
    )
    price: Optional[float] = Field(
        None,
        ge=0,
        description="Order price (must be non-negative)"
    )

    @field_validator('title', 'description')
    @classmethod
    def sanitize_text(cls, v: str) -> str:
        """Sanitize text fields to prevent injection attacks."""
        # Strip leading/trailing whitespace
        v = v.strip()
        # Ensure not empty after stripping
        if not v:
            raise ValueError("Field cannot be empty or only whitespace")
        # Prevent SQL injection by blocking dangerous SQL keywords
        dangerous_patterns = [
            'DROP TABLE', 'DELETE FROM', 'INSERT INTO', 'UPDATE ',
            'TRUNCATE', 'ALTER TABLE', 'CREATE TABLE', '--', ';--'
        ]
        v_upper = v.upper()
        for pattern in dangerous_patterns:
            if pattern in v_upper:
                raise ValueError(
                    f"Text contains potentially dangerous SQL keyword: {pattern}"
                )
        return v

    @field_validator('price')
    @classmethod
    def validate_price(cls, v: Optional[float]) -> Optional[float]:
        """Validate price is reasonable."""
        if v is not None:
            if v < 0:
                raise ValueError("Price cannot be negative")
            if v > 1_000_000:  # 1 million max
                raise ValueError("Price exceeds maximum allowed value (1,000,000)")
        return v


class OrderCreate(OrderBase):
    """Schema für Order-Erstellung mit Validation."""
    customer_id: int = Field(..., gt=0, description="Customer ID (must be positive)")
    materials: Optional[List[int]] = Field(
        None,
        description="List of material IDs",
        max_length=100  # Prevent abuse with huge lists
    )

    @field_validator('materials')
    @classmethod
    def validate_materials(cls, v: Optional[List[int]]) -> Optional[List[int]]:
        """Validate material IDs."""
        if v is not None:
            # Check all IDs are positive
            for material_id in v:
                if material_id <= 0:
                    raise ValueError(f"Invalid material ID: {material_id}. Must be positive.")
            # Check for duplicates
            if len(v) != len(set(v)):
                raise ValueError("Duplicate material IDs not allowed")
        return v


class OrderUpdate(BaseModel):
    """Schema für Order-Updates mit Validation."""
    title: Optional[str] = Field(
        None,
        min_length=1,
        max_length=200,
        description="New order title"
    )
    description: Optional[str] = Field(
        None,
        min_length=1,
        max_length=2000,
        description="New order description"
    )
    price: Optional[float] = Field(
        None,
        ge=0,
        description="New order price"
    )
    status: Optional[OrderStatusEnum] = Field(
        None,
        description="Order status (new, in_progress, completed, delivered)"
    )
    current_location: Optional[str] = Field(
        None,
        min_length=1,
        max_length=50,
        description="Current storage location"
    )

    @field_validator('title', 'description', 'current_location')
    @classmethod
    def sanitize_text(cls, v: Optional[str]) -> Optional[str]:
        """Sanitize text fields to prevent injection attacks."""
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("Field cannot be empty or only whitespace")
        # Prevent SQL injection
        dangerous_patterns = [
            'DROP TABLE', 'DELETE FROM', 'INSERT INTO', 'UPDATE ',
            'TRUNCATE', 'ALTER TABLE', 'CREATE TABLE', '--', ';--'
        ]
        v_upper = v.upper()
        for pattern in dangerous_patterns:
            if pattern in v_upper:
                raise ValueError(
                    f"Text contains potentially dangerous SQL keyword: {pattern}"
                )
        return v

    @field_validator('price')
    @classmethod
    def validate_price(cls, v: Optional[float]) -> Optional[float]:
        """Validate price is reasonable."""
        if v is not None:
            if v < 0:
                raise ValueError("Price cannot be negative")
            if v > 1_000_000:
                raise ValueError("Price exceeds maximum allowed value (1,000,000)")
        return v


class OrderRead(OrderBase):
    """Schema für Order-Anzeige."""
    id: int
    status: OrderStatusEnum
    customer_id: int
    current_location: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    materials: Optional[List[MaterialBase]] = None

    model_config = ConfigDict(from_attributes=True)