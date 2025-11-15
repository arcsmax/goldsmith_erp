"""
Input validation models for API requests.

Provides Pydantic models for validating path parameters, query parameters,
and other inputs to prevent SQL injection, DoS attacks, and invalid data.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional
import uuid as uuid_lib


class OrderIdParam(BaseModel):
    """Validated order ID path parameter."""

    order_id: int = Field(
        ...,
        gt=0,
        le=2147483647,  # Max PostgreSQL integer
        description="Order ID must be a positive integer",
        examples=[123, 456]
    )


class UserIdParam(BaseModel):
    """Validated user ID path parameter."""

    user_id: int = Field(
        ...,
        gt=0,
        le=2147483647,
        description="User ID must be a positive integer",
        examples=[1, 5]
    )


class MaterialIdParam(BaseModel):
    """Validated material ID path parameter."""

    material_id: int = Field(
        ...,
        gt=0,
        le=2147483647,
        description="Material ID must be a positive integer",
        examples=[42, 100]
    )


class ActivityIdParam(BaseModel):
    """Validated activity ID path parameter."""

    activity_id: int = Field(
        ...,
        gt=0,
        le=2147483647,
        description="Activity ID must be a positive integer",
        examples=[10, 25]
    )


class CustomerIdParam(BaseModel):
    """Validated customer ID path parameter."""

    customer_id: int = Field(
        ...,
        gt=0,
        le=2147483647,
        description="Customer ID must be a positive integer",
        examples=[7, 99]
    )


class UUIDParam(BaseModel):
    """Validated UUID string parameter (for time entries, etc.)."""

    id: str = Field(
        ...,
        min_length=36,
        max_length=36,
        description="Valid UUID v4 string",
        examples=["550e8400-e29b-41d4-a716-446655440000"]
    )

    @field_validator("id")
    @classmethod
    def validate_uuid_format(cls, v: str) -> str:
        """Ensure the string is a valid UUID."""
        try:
            uuid_lib.UUID(v, version=4)
        except ValueError:
            raise ValueError(f"Invalid UUID format: {v}")
        return v


class PaginationParams(BaseModel):
    """Standard pagination parameters with security limits."""

    skip: int = Field(
        0,
        ge=0,
        le=10000,  # Maximum offset to prevent DoS
        description="Number of records to skip (offset)",
        examples=[0, 10, 50]
    )

    limit: int = Field(
        50,
        ge=1,
        le=100,  # Maximum 100 items per page to prevent DoS
        description="Maximum number of records to return (page size)",
        examples=[10, 50, 100]
    )


class DateRangeParams(BaseModel):
    """Date range filter parameters."""

    start_date: Optional[str] = Field(
        None,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Start date in YYYY-MM-DD format",
        examples=["2025-01-01", "2025-11-15"]
    )

    end_date: Optional[str] = Field(
        None,
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="End date in YYYY-MM-DD format",
        examples=["2025-12-31", "2025-11-30"]
    )

    @field_validator("end_date")
    @classmethod
    def validate_date_range(cls, v: Optional[str], info) -> Optional[str]:
        """Ensure end_date is after start_date."""
        if v and info.data.get("start_date"):
            if v < info.data["start_date"]:
                raise ValueError("end_date must be after start_date")
        return v


class SearchParams(BaseModel):
    """Search query parameters with security limits."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=200,  # Prevent extremely long search queries
        description="Search query string",
        examples=["gold ring", "customer name"]
    )

    @field_validator("query")
    @classmethod
    def sanitize_query(cls, v: str) -> str:
        """
        Sanitize search query to prevent SQL injection.

        SQLAlchemy parameterizes queries, but this adds extra safety.
        """
        # Remove dangerous characters (just in case)
        dangerous_chars = [";", "--", "/*", "*/", "xp_", "sp_"]
        for char in dangerous_chars:
            if char in v.lower():
                raise ValueError(f"Query contains forbidden pattern: {char}")

        return v.strip()


class RatingParam(BaseModel):
    """Validated rating (1-5 stars)."""

    rating: Optional[int] = Field(
        None,
        ge=1,
        le=5,
        description="Rating from 1 (worst) to 5 (best)",
        examples=[1, 3, 5]
    )


# Pre-built query dependencies for common use cases

def validate_order_id(order_id: int) -> int:
    """
    Dependency for validating order_id path parameter.

    Usage:
        @router.get("/orders/{order_id}")
        async def get_order(order_id: int = Depends(validate_order_id)):
            ...
    """
    if order_id <= 0:
        raise ValueError("order_id must be positive")
    if order_id > 2147483647:
        raise ValueError("order_id exceeds maximum value")
    return order_id


def validate_uuid(entry_id: str) -> str:
    """
    Dependency for validating UUID path parameter.

    Usage:
        @router.get("/entries/{entry_id}")
        async def get_entry(entry_id: str = Depends(validate_uuid)):
            ...
    """
    try:
        uuid_lib.UUID(entry_id, version=4)
    except ValueError:
        raise ValueError(f"Invalid UUID format: {entry_id}")
    return entry_id


def validate_pagination(skip: int = 0, limit: int = 50) -> tuple[int, int]:
    """
    Dependency for validating pagination parameters.

    Usage:
        @router.get("/items")
        async def list_items(pagination = Depends(validate_pagination)):
            skip, limit = pagination
            ...
    """
    if skip < 0:
        raise ValueError("skip must be >= 0")
    if skip > 10000:
        raise ValueError("skip exceeds maximum offset (10000)")

    if limit < 1:
        raise ValueError("limit must be >= 1")
    if limit > 100:
        raise ValueError("limit exceeds maximum (100)")

    return skip, limit
