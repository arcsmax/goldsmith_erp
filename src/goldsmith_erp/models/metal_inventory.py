"""
Pydantic schemas for Metal Inventory Management

Provides type-safe validation for metal purchase tracking, inventory management,
and material usage calculations.
"""

from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import datetime
from enum import Enum


class MetalType(str, Enum):
    """Standard metal types used in goldsmith workshop"""
    GOLD_24K = "gold_24k"
    GOLD_22K = "gold_22k"
    GOLD_18K = "gold_18k"
    GOLD_14K = "gold_14k"
    GOLD_9K = "gold_9k"
    SILVER_999 = "silver_999"
    SILVER_925 = "silver_925"
    SILVER_800 = "silver_800"
    PLATINUM_950 = "platinum_950"
    PLATINUM_900 = "platinum_900"
    PALLADIUM = "palladium"
    WHITE_GOLD_18K = "white_gold_18k"
    WHITE_GOLD_14K = "white_gold_14k"
    ROSE_GOLD_18K = "rose_gold_18k"
    ROSE_GOLD_14K = "rose_gold_14k"


class CostingMethod(str, Enum):
    """Inventory costing method for material consumption"""
    FIFO = "fifo"              # First In, First Out
    LIFO = "lifo"              # Last In, First Out
    AVERAGE = "average"        # Weighted Average Cost
    SPECIFIC = "specific"      # Specific Identification (manual selection)


# ============================================================================
# Metal Purchase Schemas
# ============================================================================


class MetalPurchaseBase(BaseModel):
    """Base schema for metal purchase"""
    metal_type: MetalType
    weight_g: float = Field(..., gt=0, description="Weight in grams (must be positive)")
    price_total: float = Field(..., gt=0, description="Total purchase price in EUR")
    supplier: Optional[str] = Field(None, max_length=200)
    invoice_number: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = None
    lot_number: Optional[str] = Field(None, max_length=100)

    @field_validator('weight_g')
    @classmethod
    def validate_weight(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Weight must be positive")
        if v > 10000:  # Max 10kg per purchase (sanity check)
            raise ValueError("Weight exceeds maximum allowed (10000g)")
        return round(v, 2)  # Round to 2 decimal places

    @field_validator('price_total')
    @classmethod
    def validate_price(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Price must be positive")
        if v > 1000000:  # Max 1 million EUR (sanity check)
            raise ValueError("Price exceeds maximum allowed (1,000,000 EUR)")
        return round(v, 2)


class MetalPurchaseCreate(MetalPurchaseBase):
    """Schema for creating a new metal purchase"""
    date_purchased: Optional[datetime] = Field(default_factory=datetime.utcnow)

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "metal_type": "gold_18k",
                    "weight_g": 100.0,
                    "price_total": 4500.00,
                    "supplier": "Metalor Technologies",
                    "invoice_number": "INV-2025-001",
                    "notes": "18K Gold 750, certified batch",
                    "lot_number": "LOT-18K-2025-001"
                }
            ]
        }
    }


class MetalPurchaseUpdate(BaseModel):
    """Schema for updating a metal purchase (limited fields)"""
    supplier: Optional[str] = Field(None, max_length=200)
    invoice_number: Optional[str] = Field(None, max_length=100)
    notes: Optional[str] = None
    lot_number: Optional[str] = Field(None, max_length=100)


class MetalPurchaseRead(MetalPurchaseBase):
    """Schema for reading metal purchase data"""
    id: int
    date_purchased: datetime
    remaining_weight_g: float
    price_per_gram: float
    created_at: datetime
    updated_at: datetime

    # Calculated properties
    used_weight_g: float
    usage_percentage: float
    is_depleted: bool
    remaining_value: float

    model_config = {"from_attributes": True}


class MetalPurchaseListItem(BaseModel):
    """Simplified schema for listing metal purchases"""
    id: int
    metal_type: MetalType
    date_purchased: datetime
    weight_g: float
    remaining_weight_g: float
    price_per_gram: float
    remaining_value: float
    supplier: Optional[str]
    is_depleted: bool

    model_config = {"from_attributes": True}


# ============================================================================
# Material Usage Schemas
# ============================================================================


class MaterialUsageBase(BaseModel):
    """Base schema for material usage"""
    order_id: int = Field(..., gt=0)
    weight_used_g: float = Field(..., gt=0, description="Weight consumed in grams")
    notes: Optional[str] = None

    @field_validator('weight_used_g')
    @classmethod
    def validate_weight_used(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Weight used must be positive")
        if v > 1000:  # Max 1kg per order (sanity check)
            raise ValueError("Weight used exceeds maximum allowed (1000g)")
        return round(v, 3)  # Round to 3 decimal places for precision


class MaterialUsageCreate(MaterialUsageBase):
    """
    Schema for creating material usage record.

    Supports two modes:
    1. Automatic (FIFO/LIFO/AVERAGE): System selects metal batch
    2. Manual (SPECIFIC): User specifies metal_purchase_id
    """
    costing_method: CostingMethod = Field(default=CostingMethod.FIFO)
    metal_purchase_id: Optional[int] = Field(None, description="Required if costing_method=SPECIFIC")

    @field_validator('metal_purchase_id')
    @classmethod
    def validate_specific_purchase(cls, v: Optional[int], info) -> Optional[int]:
        """If SPECIFIC costing method, metal_purchase_id is required"""
        costing_method = info.data.get('costing_method')
        if costing_method == CostingMethod.SPECIFIC and v is None:
            raise ValueError("metal_purchase_id is required when using SPECIFIC costing method")
        return v

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "order_id": 123,
                    "weight_used_g": 25.5,
                    "costing_method": "fifo",
                    "notes": "Ring fabrication - 18K gold"
                },
                {
                    "order_id": 124,
                    "weight_used_g": 30.0,
                    "costing_method": "specific",
                    "metal_purchase_id": 5,
                    "notes": "Specific batch requested by customer"
                }
            ]
        }
    }


class MaterialUsageRead(MaterialUsageBase):
    """Schema for reading material usage data"""
    id: int
    metal_purchase_id: int
    cost_at_time: float
    price_per_gram_at_time: float
    costing_method: CostingMethod
    used_at: datetime
    created_at: datetime

    # Related data
    metal_type: Optional[MetalType] = None  # From metal_purchase

    model_config = {"from_attributes": True}


# ============================================================================
# Inventory Adjustment Schemas
# ============================================================================


class InventoryAdjustmentBase(BaseModel):
    """Base schema for inventory adjustment"""
    metal_purchase_id: int = Field(..., gt=0)
    adjustment_type: str = Field(..., pattern="^(loss|theft|reclamation|correction|return)$")
    weight_change_g: float = Field(..., description="Positive for additions, negative for reductions")
    reason: str = Field(..., min_length=10, max_length=1000, description="Detailed reason for adjustment")

    @field_validator('weight_change_g')
    @classmethod
    def validate_weight_change(cls, v: float) -> float:
        if v == 0:
            raise ValueError("Weight change cannot be zero")
        if abs(v) > 1000:  # Max ±1kg adjustment
            raise ValueError("Weight change exceeds maximum allowed (±1000g)")
        return round(v, 3)


class InventoryAdjustmentCreate(InventoryAdjustmentBase):
    """Schema for creating inventory adjustment"""
    pass


class InventoryAdjustmentRead(InventoryAdjustmentBase):
    """Schema for reading inventory adjustment"""
    id: int
    adjusted_by_user_id: int
    adjusted_at: datetime

    model_config = {"from_attributes": True}


# ============================================================================
# Inventory Summary & Statistics
# ============================================================================


class MetalInventorySummary(BaseModel):
    """Summary of metal inventory by type"""
    metal_type: MetalType
    total_weight_g: float
    total_value: float
    average_price_per_gram: float
    batch_count: int
    oldest_batch_date: Optional[datetime]
    newest_batch_date: Optional[datetime]


class InventoryStatistics(BaseModel):
    """Overall inventory statistics"""
    total_value: float
    total_weight_g: float
    metal_types: List[MetalInventorySummary]
    depleted_batches_count: int
    low_stock_alerts: List[str]  # Metal types running low


# ============================================================================
# Material Allocation (for order cost calculation)
# ============================================================================


class MetalAllocation(BaseModel):
    """Represents allocation of metal from specific purchase for order"""
    metal_purchase_id: int
    metal_type: MetalType
    weight_allocated_g: float
    price_per_gram: float
    cost: float
    date_purchased: datetime


class OrderMaterialAllocation(BaseModel):
    """Complete material allocation plan for an order"""
    order_id: int
    required_weight_g: float
    allocations: List[MetalAllocation]
    total_cost: float
    costing_method: CostingMethod
