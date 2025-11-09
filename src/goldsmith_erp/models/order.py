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
    deadline: Optional[datetime] = Field(None, description="Order deadline for calendar")
    materials: Optional[List[int]] = Field(
        None,
        description="List of material IDs",
        max_length=100  # Prevent abuse with huge lists
    )

    # Weight & Material (optional at creation)
    estimated_weight_g: Optional[float] = Field(None, ge=0, description="Estimated metal weight in grams")
    scrap_percentage: Optional[float] = Field(5.0, ge=0, le=50, description="Material loss percentage")

    # Cost Calculation (optional at creation)
    material_cost_override: Optional[float] = Field(None, ge=0, description="Manual material cost override")
    labor_hours: Optional[float] = Field(None, ge=0, description="Estimated work hours")
    hourly_rate: Optional[float] = Field(75.00, ge=0, description="Labor rate per hour")

    # Pricing (optional at creation)
    profit_margin_percent: Optional[float] = Field(40.0, ge=0, le=100, description="Profit margin percentage")
    vat_rate: Optional[float] = Field(19.0, ge=0, le=100, description="VAT rate percentage")

    @field_validator('deadline')
    @classmethod
    def validate_deadline(cls, v: Optional[datetime]) -> Optional[datetime]:
        """Validate deadline is in the future."""
        if v is not None:
            # Allow deadlines in the past for historical orders
            # But warn if deadline is more than 10 years in the future
            if v.year > datetime.utcnow().year + 10:
                raise ValueError("Deadline cannot be more than 10 years in the future")
        return v

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
    deadline: Optional[datetime] = Field(None, description="Order deadline for calendar")
    current_location: Optional[str] = Field(
        None,
        min_length=1,
        max_length=50,
        description="Current storage location"
    )

    # Weight & Material
    estimated_weight_g: Optional[float] = Field(None, ge=0)
    actual_weight_g: Optional[float] = Field(None, ge=0)
    scrap_percentage: Optional[float] = Field(None, ge=0, le=50)

    # Cost Calculation
    material_cost_override: Optional[float] = Field(None, ge=0)
    labor_hours: Optional[float] = Field(None, ge=0)
    hourly_rate: Optional[float] = Field(None, ge=0)

    # Pricing
    profit_margin_percent: Optional[float] = Field(None, ge=0, le=100)
    vat_rate: Optional[float] = Field(None, ge=0, le=100)

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
    deadline: Optional[datetime] = None
    current_location: Optional[str] = None

    # Weight & Material
    estimated_weight_g: Optional[float] = None
    actual_weight_g: Optional[float] = None
    scrap_percentage: Optional[float] = 5.0

    # Cost Calculation
    material_cost_calculated: Optional[float] = None
    material_cost_override: Optional[float] = None
    labor_hours: Optional[float] = None
    hourly_rate: Optional[float] = 75.00
    labor_cost: Optional[float] = None

    # Pricing
    profit_margin_percent: Optional[float] = 40.0
    vat_rate: Optional[float] = 19.0
    calculated_price: Optional[float] = None

    created_at: datetime
    updated_at: datetime
    materials: Optional[List[MaterialBase]] = None

    model_config = ConfigDict(from_attributes=True)