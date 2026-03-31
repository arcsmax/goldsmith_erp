"""
Metal Inventory API Router

Endpoints for managing metal purchases, inventory tracking, and material usage.
"""

from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
import logging

from goldsmith_erp.db.session import get_db
from ...db.models import User, MetalType, CostingMethod
from ...models.metal_inventory import (
    MetalPurchaseCreate, MetalPurchaseUpdate, MetalPurchaseRead, MetalPurchaseListItem,
    MaterialUsageCreate, MaterialUsageRead,
    InventoryStatistics,
    OrderMaterialAllocation
)
from ...services.metal_inventory_service import MetalInventoryService
from ...api.deps import get_current_user, require_permission, Permission

router = APIRouter(prefix="/metal-inventory", tags=["metal-inventory"])
logger = logging.getLogger(__name__)


# ============================================================================
# Metal Purchase Endpoints
# ============================================================================


@router.post("/purchases", response_model=MetalPurchaseRead, status_code=status.HTTP_201_CREATED)
async def create_metal_purchase(
    purchase: MetalPurchaseCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.MATERIAL_CREATE))
):
    """
    Record a new metal purchase.

    **Permissions:** Requires `material:create`

    **Automatically calculates:**
    - `price_per_gram` = `price_total` / `weight_g`
    - `remaining_weight_g` = `weight_g` (initially no usage)

    **Example:**
    ```json
    {
      "metal_type": "gold_18k",
      "weight_g": 100.0,
      "price_total": 4500.00,
      "supplier": "Metalor Technologies",
      "invoice_number": "INV-2025-001"
    }
    ```
    """
    try:
        db_purchase = await MetalInventoryService.create_purchase(db, purchase)

        # Convert to Pydantic model with calculated properties
        return MetalPurchaseRead(
            id=db_purchase.id,
            date_purchased=db_purchase.date_purchased,
            metal_type=db_purchase.metal_type,
            weight_g=db_purchase.weight_g,
            remaining_weight_g=db_purchase.remaining_weight_g,
            price_total=db_purchase.price_total,
            price_per_gram=db_purchase.price_per_gram,
            supplier=db_purchase.supplier,
            invoice_number=db_purchase.invoice_number,
            notes=db_purchase.notes,
            lot_number=db_purchase.lot_number,
            created_at=db_purchase.created_at,
            updated_at=db_purchase.updated_at,
            used_weight_g=db_purchase.used_weight_g,
            usage_percentage=db_purchase.usage_percentage,
            is_depleted=db_purchase.is_depleted,
            remaining_value=db_purchase.remaining_value
        )
    except Exception as e:
        logger.error(f"Failed to create metal purchase: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/purchases", response_model=List[MetalPurchaseListItem])
async def list_metal_purchases(
    metal_type: Optional[MetalType] = Query(None, description="Filter by metal type"),
    include_depleted: bool = Query(False, description="Include depleted batches"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.MATERIAL_VIEW))
):
    """
    List metal purchases with optional filtering.

    **Permissions:** Requires `material:view`

    **Query Parameters:**
    - `metal_type`: Filter by specific metal type (e.g., `gold_18k`)
    - `include_depleted`: Include batches with 0 remaining weight
    - `skip`, `limit`: Pagination

    **Returns:** List of purchases ordered by date (newest first)
    """
    try:
        purchases = await MetalInventoryService.list_purchases(
            db,
            metal_type=metal_type,
            include_depleted=include_depleted,
            skip=skip,
            limit=limit
        )

        return [
            MetalPurchaseListItem(
                id=p.id,
                metal_type=p.metal_type,
                date_purchased=p.date_purchased,
                weight_g=p.weight_g,
                remaining_weight_g=p.remaining_weight_g,
                price_per_gram=p.price_per_gram,
                remaining_value=p.remaining_value,
                supplier=p.supplier,
                is_depleted=p.is_depleted
            )
            for p in purchases
        ]
    except Exception as e:
        logger.error(f"Failed to list metal purchases: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve metal purchases"
        )


@router.get("/purchases/{purchase_id}", response_model=MetalPurchaseRead)
async def get_metal_purchase(
    purchase_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.MATERIAL_VIEW))
):
    """
    Get detailed information about a specific metal purchase.

    **Permissions:** Requires `material:view`
    """
    purchase = await MetalInventoryService.get_purchase(db, purchase_id)

    if not purchase:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Metal purchase {purchase_id} not found"
        )

    return MetalPurchaseRead(
        id=purchase.id,
        date_purchased=purchase.date_purchased,
        metal_type=purchase.metal_type,
        weight_g=purchase.weight_g,
        remaining_weight_g=purchase.remaining_weight_g,
        price_total=purchase.price_total,
        price_per_gram=purchase.price_per_gram,
        supplier=purchase.supplier,
        invoice_number=purchase.invoice_number,
        notes=purchase.notes,
        lot_number=purchase.lot_number,
        created_at=purchase.created_at,
        updated_at=purchase.updated_at,
        used_weight_g=purchase.used_weight_g,
        usage_percentage=purchase.usage_percentage,
        is_depleted=purchase.is_depleted,
        remaining_value=purchase.remaining_value
    )


@router.patch("/purchases/{purchase_id}", response_model=MetalPurchaseRead)
async def update_metal_purchase(
    purchase_id: int,
    update: MetalPurchaseUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.MATERIAL_EDIT))
):
    """
    Update metal purchase metadata.

    **Permissions:** Requires `material:edit`

    **Note:** Cannot change weight or price after creation.
    Only metadata fields (supplier, invoice_number, notes, lot_number) can be updated.
    """
    purchase = await MetalInventoryService.update_purchase(db, purchase_id, update)

    if not purchase:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Metal purchase {purchase_id} not found"
        )

    return MetalPurchaseRead(
        id=purchase.id,
        date_purchased=purchase.date_purchased,
        metal_type=purchase.metal_type,
        weight_g=purchase.weight_g,
        remaining_weight_g=purchase.remaining_weight_g,
        price_total=purchase.price_total,
        price_per_gram=purchase.price_per_gram,
        supplier=purchase.supplier,
        invoice_number=purchase.invoice_number,
        notes=purchase.notes,
        lot_number=purchase.lot_number,
        created_at=purchase.created_at,
        updated_at=purchase.updated_at,
        used_weight_g=purchase.used_weight_g,
        usage_percentage=purchase.usage_percentage,
        is_depleted=purchase.is_depleted,
        remaining_value=purchase.remaining_value
    )


# ============================================================================
# Material Usage Endpoints
# ============================================================================


@router.post("/usage", response_model=MaterialUsageRead, status_code=status.HTTP_201_CREATED)
async def consume_material(
    usage: MaterialUsageCreate,
    metal_type: MetalType = Query(..., description="Type of metal to consume"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.ORDER_EDIT))
):
    """
    Consume metal from inventory for an order.

    **Permissions:** Requires `order:edit`

    **Costing Methods:**
    - **FIFO** (First In First Out): Uses oldest batches first
    - **LIFO** (Last In First Out): Uses newest batches first
    - **AVERAGE**: Uses weighted average price across all batches
    - **SPECIFIC**: Manually select batch (requires `metal_purchase_id`)

    **Example (FIFO):**
    ```json
    {
      "order_id": 123,
      "weight_used_g": 25.5,
      "costing_method": "fifo",
      "notes": "Ring fabrication"
    }
    ```

    **Example (SPECIFIC):**
    ```json
    {
      "order_id": 124,
      "weight_used_g": 30.0,
      "costing_method": "specific",
      "metal_purchase_id": 5,
      "notes": "Customer requested specific batch"
    }
    ```

    **Effects:**
    1. Reduces `remaining_weight_g` in metal purchase(s)
    2. Creates `MaterialUsage` record
    3. Updates `Order.material_cost_calculated`
    4. Updates `Order.actual_weight_g`
    """
    try:
        usage_record = await MetalInventoryService.consume_material(db, usage, metal_type)

        return MaterialUsageRead(
            id=usage_record.id,
            order_id=usage_record.order_id,
            metal_purchase_id=usage_record.metal_purchase_id,
            weight_used_g=usage_record.weight_used_g,
            cost_at_time=usage_record.cost_at_time,
            price_per_gram_at_time=usage_record.price_per_gram_at_time,
            costing_method=usage_record.costing_method,
            used_at=usage_record.used_at,
            created_at=usage_record.created_at,
            notes=usage_record.notes,
            metal_type=metal_type
        )
    except ValueError as e:
        logger.warning(f"Failed to consume material: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to consume material: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to consume material"
        )


@router.get("/usage", response_model=List[MaterialUsageRead])
async def get_usage_history(
    order_id: Optional[int] = Query(None, description="Filter by order ID"),
    metal_type: Optional[MetalType] = Query(None, description="Filter by metal type"),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.ORDER_VIEW))
):
    """
    Get material usage history with optional filtering.

    **Permissions:** Requires `order:view`

    **Returns:** List of material consumption records ordered by date (newest first)
    """
    try:
        usage_records = await MetalInventoryService.get_usage_history(
            db,
            order_id=order_id,
            metal_type=metal_type,
            skip=skip,
            limit=limit
        )

        return [
            MaterialUsageRead(
                id=u.id,
                order_id=u.order_id,
                metal_purchase_id=u.metal_purchase_id,
                weight_used_g=u.weight_used_g,
                cost_at_time=u.cost_at_time,
                price_per_gram_at_time=u.price_per_gram_at_time,
                costing_method=u.costing_method,
                used_at=u.used_at,
                created_at=u.created_at,
                notes=u.notes,
                metal_type=u.metal_purchase.metal_type if u.metal_purchase else None
            )
            for u in usage_records
        ]
    except Exception as e:
        logger.error(f"Failed to get usage history: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve usage history"
        )


# ============================================================================
# Inventory Statistics
# ============================================================================


@router.get("/statistics", response_model=InventoryStatistics)
async def get_inventory_statistics(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.MATERIAL_VIEW))
):
    """
    Get comprehensive inventory statistics.

    **Permissions:** Requires `material:view`

    **Returns:**
    - Total inventory value (EUR)
    - Total weight (grams)
    - Breakdown by metal type
    - Depleted batches count
    - Low stock alerts (< 50g)

    **Example Response:**
    ```json
    {
      "total_value": 45000.00,
      "total_weight_g": 1200.50,
      "metal_types": [
        {
          "metal_type": "gold_18k",
          "total_weight_g": 850.0,
          "total_value": 38250.00,
          "average_price_per_gram": 45.00,
          "batch_count": 3
        }
      ],
      "depleted_batches_count": 5,
      "low_stock_alerts": ["silver_925: 25.5g"]
    }
    ```
    """
    try:
        stats = await MetalInventoryService.get_inventory_summary(db)
        return stats
    except Exception as e:
        logger.error(f"Failed to get inventory statistics: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve inventory statistics"
        )


# ============================================================================
# Material Allocation Preview (for order planning)
# ============================================================================


@router.post("/allocate-preview", response_model=OrderMaterialAllocation)
async def preview_material_allocation(
    metal_type: MetalType = Query(..., description="Type of metal needed"),
    required_weight_g: float = Query(..., gt=0, description="Weight needed in grams"),
    costing_method: CostingMethod = Query(CostingMethod.FIFO, description="Costing method"),
    specific_purchase_id: Optional[int] = Query(None, description="For SPECIFIC method"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.ORDER_VIEW))
):
    """
    Preview material allocation without consuming inventory.

    **Permissions:** Requires `order:view`

    **Use Case:** Calculate cost before creating order.

    **Example:** Preview cost of 25.5g of 18K gold using FIFO:
    ```
    GET /api/v1/metal-inventory/allocate-preview?metal_type=gold_18k&required_weight_g=25.5&costing_method=fifo
    ```

    **Returns:**
    - Which batches would be used
    - Total cost
    - Price breakdown
    """
    try:
        allocation = await MetalInventoryService.allocate_material(
            db,
            metal_type=metal_type,
            required_weight_g=required_weight_g,
            costing_method=costing_method,
            specific_purchase_id=specific_purchase_id
        )
        return allocation
    except ValueError as e:
        logger.warning(f"Failed to preview allocation: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Failed to preview allocation: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to preview allocation"
        )
