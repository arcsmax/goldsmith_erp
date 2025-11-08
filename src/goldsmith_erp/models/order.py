"""
Pydantic schemas for Order Management (Phase 1.8).

These schemas define the API contract for order, order item, and order status
management with comprehensive validation, cost tracking, and material allocation.

Author: Claude AI
Date: 2025-11-06
"""

from typing import Optional, List, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, validator
from decimal import Decimal


# ═══════════════════════════════════════════════════════════════════════════
# OrderItem Schemas
# ═══════════════════════════════════════════════════════════════════════════

class OrderItemBase(BaseModel):
    """Base schema for order items (materials used in order)."""

    material_id: int = Field(..., description="ID of material used")
    quantity_planned: float = Field(..., gt=0, description="Planned quantity to use")
    unit: str = Field(..., description="Unit of measurement (g, kg, pcs, ct)")
    unit_price: float = Field(..., ge=0, description="Unit price at time of order")
    notes: Optional[str] = Field(None, description="Notes about material usage")


class OrderItemCreate(OrderItemBase):
    """Schema for creating a new order item."""
    pass


class OrderItemUpdate(BaseModel):
    """Schema for updating an order item (all fields optional)."""

    quantity_planned: Optional[float] = Field(None, gt=0)
    quantity_used: Optional[float] = Field(None, ge=0)
    unit: Optional[str] = None
    unit_price: Optional[float] = Field(None, ge=0)
    is_allocated: Optional[bool] = None
    is_used: Optional[bool] = None
    notes: Optional[str] = None


class OrderItemResponse(OrderItemBase):
    """Schema for order item response (includes DB fields)."""

    id: int
    order_id: int
    quantity_used: float = Field(..., description="Actual quantity used")
    total_cost: float = Field(..., description="Total cost (quantity_used * unit_price)")
    is_allocated: bool = Field(..., description="Has stock been allocated?")
    is_used: bool = Field(..., description="Has material been used?")
    created_at: datetime
    allocated_at: Optional[datetime] = None
    used_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class OrderItemSummary(BaseModel):
    """Minimal order item info for order details."""

    id: int
    material_id: int
    material_name: Optional[str] = None  # Joined from Material table
    quantity_planned: float
    quantity_used: float
    unit: str
    unit_price: float
    total_cost: float
    is_allocated: bool
    is_used: bool

    class Config:
        from_attributes = True


# ═══════════════════════════════════════════════════════════════════════════
# OrderStatusHistory Schemas
# ═══════════════════════════════════════════════════════════════════════════

class OrderStatusHistoryBase(BaseModel):
    """Base schema for order status history."""

    new_status: str = Field(..., description="New status")
    reason: Optional[str] = Field(None, description="Reason for status change")
    notes: Optional[str] = Field(None, description="Additional notes")


class OrderStatusHistoryCreate(OrderStatusHistoryBase):
    """Schema for creating a new status history entry."""

    old_status: Optional[str] = Field(None, description="Previous status")
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class OrderStatusHistoryResponse(OrderStatusHistoryBase):
    """Schema for status history response."""

    id: int
    order_id: int
    old_status: Optional[str]
    changed_at: datetime
    changed_by: int
    changed_by_name: Optional[str] = None  # Joined from User table
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None

    class Config:
        from_attributes = True


# ═══════════════════════════════════════════════════════════════════════════
# Order Schemas
# ═══════════════════════════════════════════════════════════════════════════

class OrderBase(BaseModel):
    """Base order schema with common fields."""

    title: str = Field(..., description="Order title", min_length=1, max_length=200)
    description: Optional[str] = Field(None, description="Detailed order description")
    order_type: str = Field(
        "custom_jewelry",
        description="Type of order",
        regex="^(custom_jewelry|repair|modification|resizing|cleaning)$"
    )
    priority: str = Field(
        "normal",
        description="Order priority",
        regex="^(low|normal|high|urgent)$"
    )
    estimated_completion_date: Optional[datetime] = Field(
        None,
        description="Estimated completion date"
    )
    delivery_date: Optional[datetime] = Field(None, description="Promised delivery date")
    notes: Optional[str] = Field(None, description="Internal notes")
    customer_notes: Optional[str] = Field(None, description="Customer-facing notes")

    @validator("order_type")
    def validate_order_type(cls, v):
        """Validate order type."""
        valid_types = ["custom_jewelry", "repair", "modification", "resizing", "cleaning"]
        if v not in valid_types:
            raise ValueError(f"Order type must be one of: {', '.join(valid_types)}")
        return v

    @validator("priority")
    def validate_priority(cls, v):
        """Validate priority."""
        valid_priorities = ["low", "normal", "high", "urgent"]
        if v not in valid_priorities:
            raise ValueError(f"Priority must be one of: {', '.join(valid_priorities)}")
        return v


class OrderCreate(OrderBase):
    """Schema for creating a new order."""

    customer_id: int = Field(..., description="Customer ID")
    assigned_to: Optional[int] = Field(None, description="Assigned goldsmith user ID")

    # Financial estimates
    estimated_hours: Optional[float] = Field(None, gt=0, description="Estimated labor hours")
    hourly_rate: Optional[float] = Field(None, ge=0, description="Hourly rate for labor")
    customer_price: Optional[float] = Field(None, ge=0, description="Price quoted to customer")

    # Tax
    tax_rate: float = Field(19.0, ge=0, le=100, description="Tax rate percentage (e.g., 19 for 19%)")
    currency: str = Field("EUR", description="Currency code", max_length=3)

    # Order items (materials)
    order_items: List[OrderItemCreate] = Field(
        default_factory=list,
        description="Materials to be used in order"
    )

    # Attachments
    attachments: List[Dict[str, Any]] = Field(
        default_factory=list,
        description="File attachments (sketches, photos, etc.)"
    )


class OrderUpdate(BaseModel):
    """Schema for updating an order (all fields optional)."""

    title: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    order_type: Optional[str] = Field(
        None,
        regex="^(custom_jewelry|repair|modification|resizing|cleaning)$"
    )
    status: Optional[str] = Field(
        None,
        regex="^(draft|approved|in_progress|completed|delivered|cancelled)$"
    )
    priority: Optional[str] = Field(
        None,
        regex="^(low|normal|high|urgent)$"
    )
    assigned_to: Optional[int] = None

    # Dates
    estimated_completion_date: Optional[datetime] = None
    delivery_date: Optional[datetime] = None
    actual_completion_date: Optional[datetime] = None

    # Financial tracking
    material_cost: Optional[float] = Field(None, ge=0)
    labor_cost: Optional[float] = Field(None, ge=0)
    additional_cost: Optional[float] = Field(None, ge=0)
    customer_price: Optional[float] = Field(None, ge=0)

    # Labor
    estimated_hours: Optional[float] = Field(None, gt=0)
    actual_hours: Optional[float] = Field(None, ge=0)
    hourly_rate: Optional[float] = Field(None, ge=0)

    # Tax
    tax_rate: Optional[float] = Field(None, ge=0, le=100)

    # Notes
    notes: Optional[str] = None
    customer_notes: Optional[str] = None

    # Attachments
    attachments: Optional[List[Dict[str, Any]]] = None


class OrderResponse(OrderBase):
    """Schema for order response (includes DB fields)."""

    id: int
    order_number: str = Field(..., description="Unique order number (ORD-YYYYMM-XXXX)")
    customer_id: int
    customer_name: Optional[str] = None  # Joined from Customer table

    # Status
    status: str = Field(..., description="Current order status")

    # Assignment
    assigned_to: Optional[int] = None
    assigned_to_name: Optional[str] = None  # Joined from User table

    # Dates
    order_date: datetime
    actual_completion_date: Optional[datetime] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None

    # Financial tracking
    material_cost: float
    labor_cost: float
    additional_cost: float
    total_cost: float
    customer_price: float
    margin: float = Field(..., description="Profit margin (customer_price - total_cost)")
    currency: str

    # Tax
    tax_rate: float
    tax_amount: float
    total_amount: float = Field(..., description="Final amount including tax")

    # Labor
    estimated_hours: Optional[float] = None
    actual_hours: Optional[float] = None
    hourly_rate: Optional[float] = None

    # Attachments
    attachments: Optional[List[Dict[str, Any]]] = None

    # Soft delete
    is_deleted: bool
    deleted_at: Optional[datetime] = None
    deleted_by: Optional[int] = None

    # Audit
    created_at: datetime
    created_by: Optional[int] = None
    updated_at: datetime
    updated_by: Optional[int] = None

    # Relationships (optional, loaded separately)
    order_items: List[OrderItemSummary] = Field(default_factory=list)
    status_history: List[OrderStatusHistoryResponse] = Field(default_factory=list)

    class Config:
        from_attributes = True


class OrderSummary(BaseModel):
    """Minimal order information for lists and references."""

    id: int
    order_number: str
    title: str
    customer_id: int
    customer_name: Optional[str] = None
    status: str
    priority: str
    order_type: str
    order_date: datetime
    delivery_date: Optional[datetime] = None
    customer_price: float
    total_cost: float
    margin: float
    currency: str
    assigned_to: Optional[int] = None
    assigned_to_name: Optional[str] = None
    is_deleted: bool

    class Config:
        from_attributes = True


class OrderList(BaseModel):
    """Paginated list of orders."""

    items: List[OrderSummary]
    total: int = Field(..., description="Total number of orders matching filters")
    skip: int = Field(..., description="Number of records skipped")
    limit: int = Field(..., description="Maximum records per page")
    has_more: bool = Field(..., description="Whether there are more records")

    @staticmethod
    def create(items: List[OrderSummary], total: int, skip: int, limit: int) -> "OrderList":
        """Factory method to create OrderList with calculated has_more."""
        return OrderList(
            items=items,
            total=total,
            skip=skip,
            limit=limit,
            has_more=(skip + len(items)) < total
        )


# ═══════════════════════════════════════════════════════════════════════════
# Order-specific Request/Response Schemas
# ═══════════════════════════════════════════════════════════════════════════

class OrderStatusChangeRequest(BaseModel):
    """Request to change order status."""

    new_status: str = Field(
        ...,
        description="New status",
        regex="^(draft|approved|in_progress|completed|delivered|cancelled)$"
    )
    reason: Optional[str] = Field(None, description="Reason for status change")
    notes: Optional[str] = Field(None, description="Additional notes")


class OrderCostCalculation(BaseModel):
    """Order cost calculation breakdown."""

    material_cost: float = Field(..., description="Total material costs")
    labor_cost: float = Field(..., description="Labor costs (hours * rate)")
    additional_cost: float = Field(..., description="Additional costs")
    subtotal: float = Field(..., description="Sum of all costs")
    tax_rate: float = Field(..., description="Tax rate percentage")
    tax_amount: float = Field(..., description="Tax amount")
    total_amount: float = Field(..., description="Total including tax")
    customer_price: float = Field(..., description="Price quoted to customer")
    margin: float = Field(..., description="Profit margin")
    margin_percentage: float = Field(..., description="Margin as percentage of customer price")


class OrderStatistics(BaseModel):
    """Order statistics for dashboard and reporting."""

    total_orders: int
    draft_orders: int
    in_progress_orders: int
    completed_orders: int
    delivered_orders: int
    cancelled_orders: int

    total_revenue: float = Field(..., description="Sum of all delivered order customer_price")
    total_costs: float = Field(..., description="Sum of all delivered order total_cost")
    total_profit: float = Field(..., description="total_revenue - total_costs")
    average_margin: float = Field(..., description="Average profit margin percentage")

    overdue_orders: int = Field(..., description="Orders past estimated_completion_date")
    urgent_orders: int = Field(..., description="Orders with urgent priority")


class MaterialAllocationRequest(BaseModel):
    """Request to allocate materials for an order."""

    order_item_id: int = Field(..., description="Order item ID to allocate")
    allocate: bool = Field(True, description="True to allocate, False to deallocate")


class MaterialUsageRequest(BaseModel):
    """Request to mark materials as used."""

    order_item_id: int = Field(..., description="Order item ID")
    quantity_used: float = Field(..., gt=0, description="Actual quantity used")
    notes: Optional[str] = Field(None, description="Notes about usage")


# ═══════════════════════════════════════════════════════════════════════════
# Backward Compatibility (Legacy Schemas)
# ═══════════════════════════════════════════════════════════════════════════

class MaterialBase(BaseModel):
    """Legacy material schema for backward compatibility."""

    id: int
    name: str
    unit_price: float

    class Config:
        from_attributes = True


class OrderRead(OrderResponse):
    """Legacy schema for order read (backward compatibility)."""

    # Map legacy materials field to order_items
    materials: Optional[List[MaterialBase]] = None

    class Config:
        from_attributes = True
