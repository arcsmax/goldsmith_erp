"""Material API endpoints."""
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, Query, Path
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.session import get_session
from goldsmith_erp.db.repositories.material import MaterialRepository
from goldsmith_erp.services.material_service import MaterialService
from goldsmith_erp.models.material import (
    MaterialCreate,
    MaterialUpdate,
    MaterialResponse,
    MaterialWithStock,
    MaterialStockAdjust,
    MaterialList,
)

router = APIRouter()


def get_material_service(
    session: AsyncSession = Depends(get_session)
) -> MaterialService:
    """Dependency to get material service."""
    repository = MaterialRepository(session)
    return MaterialService(repository)


@router.get("/", response_model=MaterialList)
async def list_materials(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=1000, description="Maximum number of records"),
    material_type: Optional[str] = Query(
        None,
        regex="^(gold|silver|platinum|stone|tool|other)$",
        description="Filter by material type"
    ),
    search: Optional[str] = Query(None, description="Search in name and description"),
    service: MaterialService = Depends(get_material_service)
):
    """
    Get list of materials with optional filtering.

    - **skip**: Number of records to skip (pagination)
    - **limit**: Maximum records to return (pagination)
    - **material_type**: Filter by specific material type
    - **search**: Search term for name/description
    """
    materials = await service.list_materials(skip, limit, material_type, search)

    # Get total count (simplified - in production, use a separate count query)
    total = len(materials) + skip  # Approximation

    return MaterialList.create(materials, total, skip, limit)


@router.get("/low-stock", response_model=List[MaterialWithStock])
async def get_low_stock_materials(
    threshold_factor: float = Query(
        1.0,
        ge=0.1,
        le=10.0,
        description="Threshold multiplier (1.0 = at minimum, 1.5 = 50% above minimum)"
    ),
    service: MaterialService = Depends(get_material_service)
):
    """
    Get materials with low stock.

    Returns materials where stock <= min_stock * threshold_factor.

    - **threshold_factor**: Multiplier for minimum stock threshold
    """
    return await service.get_low_stock_materials(threshold_factor)


@router.get("/total-value")
async def get_total_stock_value(
    material_type: Optional[str] = Query(
        None,
        regex="^(gold|silver|platinum|stone|tool|other)$",
        description="Filter by material type"
    ),
    service: MaterialService = Depends(get_material_service)
):
    """
    Get total value of materials in stock.

    Calculates sum of (stock * unit_price) for all materials.

    - **material_type**: Optional filter by material type
    """
    total_value = await service.get_total_stock_value(material_type)
    return {
        "total_value": total_value,
        "material_type": material_type,
        "currency": "EUR"
    }


@router.get("/search/metadata", response_model=List[MaterialResponse])
async def search_by_properties(
    purity: Optional[int] = Query(None, description="Gold purity (333, 585, 750, etc.)"),
    color: Optional[str] = Query(None, description="Stone color"),
    quality: Optional[str] = Query(None, description="Stone quality"),
    size: Optional[float] = Query(None, description="Stone size in mm"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    service: MaterialService = Depends(get_material_service)
):
    """
    Search materials by properties fields.

    Build properties filters from query parameters and search.

    - **purity**: Gold purity (for gold materials)
    - **color**: Stone color (for stone materials)
    - **quality**: Stone quality (for stone materials)
    - **size**: Stone size in mm (for stone materials)
    """
    # Build properties filters from provided parameters
    properties_filters = {}
    if purity is not None:
        properties_filters["purity"] = purity
    if color:
        properties_filters["color"] = color
    if quality:
        properties_filters["quality"] = quality
    if size is not None:
        properties_filters["size"] = size

    if not properties_filters:
        return []

    return await service.search_by_properties(properties_filters, skip, limit)


@router.get("/{material_id}", response_model=MaterialWithStock)
async def get_material(
    material_id: int = Path(..., description="Material ID"),
    service: MaterialService = Depends(get_material_service)
):
    """
    Get a specific material by ID.

    Returns material details with stock status indicators.

    - **material_id**: ID of the material to retrieve
    """
    return await service.get_material_with_stock_status(material_id)


@router.post("/", response_model=MaterialResponse, status_code=201)
async def create_material(
    data: MaterialCreate,
    service: MaterialService = Depends(get_material_service)
):
    """
    Create a new material.

    - **name**: Material name (required)
    - **material_type**: Type (gold, silver, platinum, stone, tool, other)
    - **unit_price**: Price per unit (required)
    - **stock**: Initial stock quantity (default: 0)
    - **unit**: Unit of measurement (g, kg, pcs, ct)
    - **min_stock**: Minimum stock threshold (default: 0)
    - **properties**: Type-specific properties (optional)
    """
    return await service.create_material(data)


@router.put("/{material_id}", response_model=MaterialResponse)
async def update_material(
    data: MaterialUpdate,
    material_id: int = Path(..., description="Material ID"),
    service: MaterialService = Depends(get_material_service)
):
    """
    Update a material.

    All fields are optional - only provided fields will be updated.

    - **material_id**: ID of the material to update
    """
    return await service.update_material(material_id, data)


@router.delete("/{material_id}", status_code=204)
async def delete_material(
    material_id: int = Path(..., description="Material ID"),
    service: MaterialService = Depends(get_material_service)
):
    """
    Delete a material.

    - **material_id**: ID of the material to delete
    """
    await service.delete_material(material_id)


@router.patch("/{material_id}/stock", response_model=MaterialResponse)
async def adjust_stock(
    adjustment: MaterialStockAdjust,
    material_id: int = Path(..., description="Material ID"),
    service: MaterialService = Depends(get_material_service)
):
    """
    Adjust material stock.

    - **material_id**: ID of the material
    - **quantity**: Amount to add or subtract (must be positive)
    - **operation**: "add" to increase stock, "subtract" to decrease
    - **note**: Optional note for the adjustment
    """
    return await service.adjust_stock(material_id, adjustment)


@router.put("/{material_id}/stock", response_model=MaterialResponse)
async def set_stock(
    quantity: float = Query(..., ge=0, description="New stock quantity"),
    material_id: int = Path(..., description="Material ID"),
    service: MaterialService = Depends(get_material_service)
):
    """
    Set material stock to a specific value.

    - **material_id**: ID of the material
    - **quantity**: New stock quantity (must be non-negative)
    """
    return await service.set_stock(material_id, quantity)
