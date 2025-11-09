# src/goldsmith_erp/models/common.py
"""
Common Pydantic models for validation across the application.
"""

from pydantic import BaseModel, Field
from typing import Optional


class IdParam(BaseModel):
    """Validation model for ID path parameters."""

    id: int = Field(gt=0, description="ID must be a positive integer")


class PaginationParams(BaseModel):
    """Validation model for pagination query parameters."""

    skip: int = Field(
        default=0,
        ge=0,
        description="Number of records to skip (offset)"
    )
    limit: int = Field(
        default=50,
        ge=1,
        le=100,
        description="Maximum number of records to return (1-100)"
    )


class OrderIdParam(BaseModel):
    """Validation model for order ID path parameters."""

    order_id: int = Field(gt=0, description="Order ID must be a positive integer")


class UserIdParam(BaseModel):
    """Validation model for user ID path parameters."""

    user_id: int = Field(gt=0, description="User ID must be a positive integer")


class MaterialIdParam(BaseModel):
    """Validation model for material ID path parameters."""

    material_id: int = Field(gt=0, description="Material ID must be a positive integer")


class CustomerIdParam(BaseModel):
    """Validation model for customer ID path parameters."""

    customer_id: int = Field(gt=0, description="Customer ID must be a positive integer")


class ActivityIdParam(BaseModel):
    """Validation model for activity ID path parameters."""

    activity_id: int = Field(gt=0, description="Activity ID must be a positive integer")


class TimeEntryIdParam(BaseModel):
    """Validation model for time entry UUID path parameters."""

    entry_id: str = Field(
        min_length=36,
        max_length=36,
        description="Time entry ID must be a valid UUID"
    )
