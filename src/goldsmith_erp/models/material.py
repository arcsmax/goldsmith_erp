"""Pydantic schemas for Material."""
from typing import Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field, validator


class MaterialBase(BaseModel):
    """Base material schema with common fields."""

    name: str = Field(..., description="Material name", min_length=1, max_length=100)
    material_type: str = Field(
        ...,
        description="Type of material",
        regex="^(gold|silver|platinum|stone|tool|other)$"
    )
    description: Optional[str] = Field(None, description="Material description")
    unit_price: float = Field(..., description="Price per unit", ge=0)
    stock: float = Field(0, description="Current stock quantity", ge=0)
    unit: str = Field(
        ...,
        description="Unit of measurement",
        regex="^(g|kg|pcs|ct)$"
    )
    min_stock: float = Field(0, description="Minimum stock level for alerts", ge=0)
    properties: Optional[Dict[str, Any]] = Field(
        None,
        description="Type-specific properties (purity, size, color, quality, etc.)"
    )

    @validator("properties")
    def validate_properties(cls, v, values):
        """Validate properties based on material_type."""
        if not v:
            return v

        material_type = values.get("material_type")

        # Validate properties fields based on material type
        if material_type == "gold" and v:
            if "purity" in v:
                purity = v["purity"]
                if not isinstance(purity, (int, float)) or purity not in [333, 585, 750, 916, 999]:
                    raise ValueError(
                        "Gold purity must be one of: 333, 585, 750, 916, 999"
                    )

        if material_type == "stone" and v:
            valid_stone_fields = {
                "size",
                "color",
                "quality",
                "shape",
                "certification"
            }
            # Just check that only valid fields are present (optional)
            invalid_fields = set(v.keys()) - valid_stone_fields
            if invalid_fields:
                raise ValueError(
                    f"Invalid properties fields for stone: {invalid_fields}"
                )

        return v


class MaterialCreate(MaterialBase):
    """Schema for creating a new material."""

    pass


class MaterialUpdate(BaseModel):
    """Schema for updating a material (all fields optional)."""

    name: Optional[str] = Field(None, min_length=1, max_length=100)
    material_type: Optional[str] = Field(
        None,
        regex="^(gold|silver|platinum|stone|tool|other)$"
    )
    description: Optional[str] = None
    unit_price: Optional[float] = Field(None, ge=0)
    stock: Optional[float] = Field(None, ge=0)
    unit: Optional[str] = Field(None, regex="^(g|kg|pcs|ct)$")
    min_stock: Optional[float] = Field(None, ge=0)
    properties: Optional[Dict[str, Any]] = None


class MaterialStockAdjust(BaseModel):
    """Schema for adjusting material stock."""

    quantity: float = Field(..., description="Quantity to add/subtract", gt=0)
    operation: str = Field(
        "add",
        description="Operation type",
        regex="^(add|subtract)$"
    )
    note: Optional[str] = Field(None, description="Optional note for the adjustment")


class MaterialResponse(MaterialBase):
    """Schema for material response (includes DB fields)."""

    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class MaterialWithStock(MaterialResponse):
    """Material response with stock status indicators."""

    is_low_stock: bool = Field(description="Whether stock is below minimum")
    stock_value: float = Field(description="Total value of stock (stock * unit_price)")

    @classmethod
    def from_material(cls, material: "Material") -> "MaterialWithStock":
        """Create from Material model instance."""
        is_low_stock = material.stock <= material.min_stock
        stock_value = material.stock * material.unit_price

        return cls(
            id=material.id,
            name=material.name,
            material_type=material.material_type,
            description=material.description,
            unit_price=material.unit_price,
            stock=material.stock,
            unit=material.unit,
            min_stock=material.min_stock,
            properties=material.properties,
            created_at=material.created_at,
            updated_at=material.updated_at,
            is_low_stock=is_low_stock,
            stock_value=stock_value,
        )


class MaterialList(BaseModel):
    """Schema for paginated material list."""

    items: list[MaterialResponse]
    total: int
    skip: int
    limit: int
    has_more: bool

    @classmethod
    def create(
        cls,
        items: list,
        total: int,
        skip: int,
        limit: int
    ) -> "MaterialList":
        """Create paginated response."""
        return cls(
            items=items,
            total=total,
            skip=skip,
            limit=limit,
            has_more=(skip + len(items)) < total,
        )
