"""
Metal Inventory Service

Business logic for managing metal purchases, inventory tracking, and material usage.
Supports multiple costing methods: FIFO, LIFO, Weighted Average, and Specific Identification.
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, desc, asc
from sqlalchemy.orm import selectinload
from typing import List, Optional, Tuple
from datetime import datetime
import logging

from ..db.models import (
    MetalPurchase, MaterialUsage, InventoryAdjustment,
    MetalType, CostingMethod, Order
)
from ..models.metal_inventory import (
    MetalPurchaseCreate, MetalPurchaseUpdate, MetalPurchaseRead,
    MaterialUsageCreate, MaterialUsageRead,
    InventoryAdjustmentCreate,
    MetalInventorySummary, InventoryStatistics,
    MetalAllocation, OrderMaterialAllocation
)
from ..db.transaction import transactional

logger = logging.getLogger(__name__)


class MetalInventoryService:
    """Service for metal inventory management and cost accounting"""

    # ========================================================================
    # Metal Purchase Management
    # ========================================================================

    @staticmethod
    async def create_purchase(
        db: AsyncSession,
        purchase_data: MetalPurchaseCreate
    ) -> MetalPurchase:
        """
        Record a new metal purchase.

        Automatically calculates price_per_gram and sets remaining_weight_g to weight_g.
        """
        async with transactional(db):
            # Calculate price per gram
            price_per_gram = purchase_data.price_total / purchase_data.weight_g

            purchase = MetalPurchase(
                date_purchased=purchase_data.date_purchased,
                metal_type=purchase_data.metal_type,
                weight_g=purchase_data.weight_g,
                remaining_weight_g=purchase_data.weight_g,  # Initially no usage
                price_total=purchase_data.price_total,
                price_per_gram=round(price_per_gram, 2),
                supplier=purchase_data.supplier,
                invoice_number=purchase_data.invoice_number,
                notes=purchase_data.notes,
                lot_number=purchase_data.lot_number,
            )

            db.add(purchase)
            await db.flush()
            await db.refresh(purchase)

        logger.info(
            f"Created metal purchase: {purchase.metal_type.value} "
            f"{purchase.weight_g}g @ {purchase.price_per_gram:.2f} EUR/g "
            f"(Total: {purchase.price_total:.2f} EUR)"
        )

        return purchase

    @staticmethod
    async def get_purchase(db: AsyncSession, purchase_id: int) -> Optional[MetalPurchase]:
        """Get a single metal purchase by ID"""
        result = await db.execute(
            select(MetalPurchase)
            .options(selectinload(MetalPurchase.usage_records))
            .filter(MetalPurchase.id == purchase_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_purchases(
        db: AsyncSession,
        metal_type: Optional[MetalType] = None,
        include_depleted: bool = False,
        skip: int = 0,
        limit: int = 100
    ) -> List[MetalPurchase]:
        """
        List metal purchases with optional filtering.

        Args:
            metal_type: Filter by specific metal type
            include_depleted: Include batches with remaining_weight_g <= 0
            skip: Pagination offset
            limit: Maximum results
        """
        query = select(MetalPurchase).order_by(desc(MetalPurchase.date_purchased))

        # Filter by metal type
        if metal_type:
            query = query.filter(MetalPurchase.metal_type == metal_type)

        # Filter out depleted batches
        if not include_depleted:
            query = query.filter(MetalPurchase.remaining_weight_g > 0.01)

        query = query.offset(skip).limit(limit)

        result = await db.execute(query)
        return list(result.scalars().all())

    @staticmethod
    async def update_purchase(
        db: AsyncSession,
        purchase_id: int,
        update_data: MetalPurchaseUpdate
    ) -> Optional[MetalPurchase]:
        """Update metal purchase metadata (not weight or price)"""
        async with transactional(db):
            purchase = await MetalInventoryService.get_purchase(db, purchase_id)
            if not purchase:
                return None

            # Update allowed fields
            if update_data.supplier is not None:
                purchase.supplier = update_data.supplier
            if update_data.invoice_number is not None:
                purchase.invoice_number = update_data.invoice_number
            if update_data.notes is not None:
                purchase.notes = update_data.notes
            if update_data.lot_number is not None:
                purchase.lot_number = update_data.lot_number

            await db.flush()
            await db.refresh(purchase)

        return purchase

    # ========================================================================
    # Material Usage & Allocation
    # ========================================================================

    @staticmethod
    async def allocate_material(
        db: AsyncSession,
        metal_type: MetalType,
        required_weight_g: float,
        costing_method: CostingMethod,
        specific_purchase_id: Optional[int] = None
    ) -> OrderMaterialAllocation:
        """
        Allocate metal from inventory using specified costing method.

        Does NOT consume inventory - only calculates allocation plan.
        Use consume_material() to actually reduce inventory.

        Args:
            metal_type: Type of metal needed
            required_weight_g: Weight needed in grams
            costing_method: FIFO, LIFO, AVERAGE, or SPECIFIC
            specific_purchase_id: Required if costing_method=SPECIFIC

        Returns:
            OrderMaterialAllocation with detailed allocation plan

        Raises:
            ValueError: If insufficient inventory or invalid parameters
        """
        # Validate specific purchase if SPECIFIC method
        if costing_method == CostingMethod.SPECIFIC:
            if not specific_purchase_id:
                raise ValueError("specific_purchase_id required for SPECIFIC costing method")

            purchase = await MetalInventoryService.get_purchase(db, specific_purchase_id)
            if not purchase:
                raise ValueError(f"Metal purchase {specific_purchase_id} not found")
            if purchase.metal_type != metal_type:
                raise ValueError(
                    f"Purchase {specific_purchase_id} is {purchase.metal_type.value}, "
                    f"but {metal_type.value} was requested"
                )
            if purchase.remaining_weight_g < required_weight_g:
                raise ValueError(
                    f"Purchase {specific_purchase_id} only has {purchase.remaining_weight_g}g "
                    f"remaining, but {required_weight_g}g requested"
                )

            # Simple allocation from specific batch
            allocations = [
                MetalAllocation(
                    metal_purchase_id=purchase.id,
                    metal_type=purchase.metal_type,
                    weight_allocated_g=required_weight_g,
                    price_per_gram=purchase.price_per_gram,
                    cost=required_weight_g * purchase.price_per_gram,
                    date_purchased=purchase.date_purchased
                )
            ]

            return OrderMaterialAllocation(
                order_id=0,  # Will be set when creating usage record
                required_weight_g=required_weight_g,
                allocations=allocations,
                total_cost=sum(a.cost for a in allocations),
                costing_method=costing_method
            )

        # For FIFO, LIFO, AVERAGE: Get available purchases
        if costing_method == CostingMethod.FIFO:
            order_by = asc(MetalPurchase.date_purchased)
        elif costing_method == CostingMethod.LIFO:
            order_by = desc(MetalPurchase.date_purchased)
        else:  # AVERAGE
            order_by = asc(MetalPurchase.date_purchased)  # Order doesn't matter for average

        # Get available batches
        result = await db.execute(
            select(MetalPurchase)
            .filter(
                and_(
                    MetalPurchase.metal_type == metal_type,
                    MetalPurchase.remaining_weight_g > 0.01
                )
            )
            .order_by(order_by)
        )
        available_purchases = list(result.scalars().all())

        if not available_purchases:
            raise ValueError(f"No inventory available for {metal_type.value}")

        # Calculate total available weight
        total_available = sum(p.remaining_weight_g for p in available_purchases)
        if total_available < required_weight_g:
            raise ValueError(
                f"Insufficient inventory: {total_available:.2f}g available, "
                f"{required_weight_g:.2f}g required"
            )

        # Weighted Average Cost calculation
        if costing_method == CostingMethod.AVERAGE:
            total_value = sum(p.remaining_weight_g * p.price_per_gram for p in available_purchases)
            avg_price_per_gram = total_value / total_available

            # Allocate from first batch (for simplicity), but use average price
            allocations = [
                MetalAllocation(
                    metal_purchase_id=available_purchases[0].id,
                    metal_type=metal_type,
                    weight_allocated_g=required_weight_g,
                    price_per_gram=avg_price_per_gram,
                    cost=required_weight_g * avg_price_per_gram,
                    date_purchased=available_purchases[0].date_purchased
                )
            ]

            return OrderMaterialAllocation(
                order_id=0,
                required_weight_g=required_weight_g,
                allocations=allocations,
                total_cost=sum(a.cost for a in allocations),
                costing_method=costing_method
            )

        # FIFO/LIFO: Allocate from multiple batches if needed
        allocations = []
        remaining_need = required_weight_g

        for purchase in available_purchases:
            if remaining_need <= 0:
                break

            # How much to take from this batch
            allocated_from_batch = min(purchase.remaining_weight_g, remaining_need)

            allocations.append(
                MetalAllocation(
                    metal_purchase_id=purchase.id,
                    metal_type=purchase.metal_type,
                    weight_allocated_g=allocated_from_batch,
                    price_per_gram=purchase.price_per_gram,
                    cost=allocated_from_batch * purchase.price_per_gram,
                    date_purchased=purchase.date_purchased
                )
            )

            remaining_need -= allocated_from_batch

        if remaining_need > 0.01:  # Floating point tolerance
            raise ValueError("Failed to allocate sufficient material (internal error)")

        return OrderMaterialAllocation(
            order_id=0,
            required_weight_g=required_weight_g,
            allocations=allocations,
            total_cost=sum(a.cost for a in allocations),
            costing_method=costing_method
        )

    @staticmethod
    async def consume_material(
        db: AsyncSession,
        usage_data: MaterialUsageCreate,
        metal_type: MetalType
    ) -> MaterialUsage:
        """
        Consume metal from inventory and create usage record.

        This method:
        1. Allocates material using specified costing method
        2. Creates MaterialUsage record
        3. Reduces remaining_weight_g in MetalPurchase(s)
        4. Updates Order.material_cost_calculated

        Args:
            usage_data: Usage details (order_id, weight, costing method)
            metal_type: Type of metal to consume

        Returns:
            MaterialUsage record

        Raises:
            ValueError: If insufficient inventory or invalid data
        """
        async with transactional(db):
            # 1. Allocate material
            allocation = await MetalInventoryService.allocate_material(
                db,
                metal_type=metal_type,
                required_weight_g=usage_data.weight_used_g,
                costing_method=usage_data.costing_method,
                specific_purchase_id=usage_data.metal_purchase_id
            )

            # 2. Consume from inventory
            for alloc in allocation.allocations:
                purchase = await MetalInventoryService.get_purchase(db, alloc.metal_purchase_id)
                if not purchase:
                    raise ValueError(f"Metal purchase {alloc.metal_purchase_id} not found")

                # Reduce remaining weight
                purchase.remaining_weight_g -= alloc.weight_allocated_g

                if purchase.remaining_weight_g < -0.01:  # Allow small tolerance
                    raise ValueError(
                        f"Cannot consume {alloc.weight_allocated_g}g from purchase {purchase.id}: "
                        f"only {purchase.remaining_weight_g + alloc.weight_allocated_g}g remaining"
                    )

                # Ensure non-negative (handle floating point errors)
                if purchase.remaining_weight_g < 0.01:
                    purchase.remaining_weight_g = 0.0

            # 3. Create MaterialUsage record
            # For simplicity, if multiple batches used, create one record for primary batch
            primary_allocation = allocation.allocations[0]

            usage = MaterialUsage(
                order_id=usage_data.order_id,
                metal_purchase_id=primary_allocation.metal_purchase_id,
                weight_used_g=usage_data.weight_used_g,
                cost_at_time=allocation.total_cost,
                price_per_gram_at_time=allocation.total_cost / usage_data.weight_used_g,
                costing_method=usage_data.costing_method,
                notes=usage_data.notes
            )

            db.add(usage)
            await db.flush()
            await db.refresh(usage)

            # 4. Update Order.material_cost_calculated
            order_result = await db.execute(
                select(Order).filter(Order.id == usage_data.order_id)
            )
            order = order_result.scalar_one_or_none()
            if order:
                order.material_cost_calculated = allocation.total_cost
                order.actual_weight_g = usage_data.weight_used_g

        logger.info(
            f"Consumed {usage_data.weight_used_g}g of {metal_type.value} "
            f"for order #{usage_data.order_id} using {usage_data.costing_method.value} "
            f"(Cost: {allocation.total_cost:.2f} EUR)"
        )

        return usage

    # ========================================================================
    # Inventory Queries & Statistics
    # ========================================================================

    @staticmethod
    async def get_inventory_summary(db: AsyncSession) -> InventoryStatistics:
        """
        Get overall inventory statistics by metal type.

        Returns summary of total weight, value, and batch counts.
        """
        result = await db.execute(
            select(
                MetalPurchase.metal_type,
                func.sum(MetalPurchase.remaining_weight_g).label('total_weight'),
                func.sum(MetalPurchase.remaining_weight_g * MetalPurchase.price_per_gram).label('total_value'),
                func.count(MetalPurchase.id).label('batch_count'),
                func.min(MetalPurchase.date_purchased).label('oldest'),
                func.max(MetalPurchase.date_purchased).label('newest')
            )
            .filter(MetalPurchase.remaining_weight_g > 0.01)
            .group_by(MetalPurchase.metal_type)
        )

        summaries = []
        for row in result:
            avg_price = row.total_value / row.total_weight if row.total_weight > 0 else 0
            summaries.append(
                MetalInventorySummary(
                    metal_type=row.metal_type,
                    total_weight_g=round(row.total_weight, 2),
                    total_value=round(row.total_value, 2),
                    average_price_per_gram=round(avg_price, 2),
                    batch_count=row.batch_count,
                    oldest_batch_date=row.oldest,
                    newest_batch_date=row.newest
                )
            )

        # Calculate overall totals
        total_value = sum(s.total_value for s in summaries)
        total_weight = sum(s.total_weight_g for s in summaries)

        # Count depleted batches
        depleted_result = await db.execute(
            select(func.count(MetalPurchase.id))
            .filter(MetalPurchase.remaining_weight_g <= 0.01)
        )
        depleted_count = depleted_result.scalar() or 0

        # Identify low stock (< 50g remaining)
        low_stock_alerts = [
            f"{s.metal_type.value}: {s.total_weight_g:.2f}g"
            for s in summaries
            if s.total_weight_g < 50
        ]

        return InventoryStatistics(
            total_value=round(total_value, 2),
            total_weight_g=round(total_weight, 2),
            metal_types=summaries,
            depleted_batches_count=depleted_count,
            low_stock_alerts=low_stock_alerts
        )

    @staticmethod
    async def get_usage_history(
        db: AsyncSession,
        order_id: Optional[int] = None,
        metal_type: Optional[MetalType] = None,
        skip: int = 0,
        limit: int = 100
    ) -> List[MaterialUsage]:
        """Get material usage history with optional filtering"""
        query = select(MaterialUsage).options(
            selectinload(MaterialUsage.metal_purchase),
            selectinload(MaterialUsage.order)
        ).order_by(desc(MaterialUsage.used_at))

        if order_id:
            query = query.filter(MaterialUsage.order_id == order_id)

        if metal_type:
            # Join with metal_purchases to filter by metal_type
            query = query.join(MetalPurchase).filter(MetalPurchase.metal_type == metal_type)

        query = query.offset(skip).limit(limit)

        result = await db.execute(query)
        return list(result.scalars().all())
