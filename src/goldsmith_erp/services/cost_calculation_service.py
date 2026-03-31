"""Cost Calculation Service for Goldsmith Orders

Calculates order costs based on:
- Material weight and prices (from Metal Inventory System)
- Gemstones
- Labor hours
- Profit margin
- VAT (MwSt)

IMPORTANT: As of Phase 2.3, this service uses MetalInventoryService
for real-time inventory pricing instead of hardcoded prices.
"""
import logging
from typing import Dict, Any, Optional
from decimal import Decimal
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from goldsmith_erp.db.models import Order as OrderModel, Gemstone as GemstoneModel, CostingMethod
from goldsmith_erp.services.metal_inventory_service import MetalInventoryService

logger = logging.getLogger(__name__)


class PriceBreakdown:
    """Data class for price breakdown"""
    def __init__(
        self,
        material_cost: float = 0.0,
        gemstone_cost: float = 0.0,
        labor_cost: float = 0.0,
        subtotal: float = 0.0,
        margin_amount: float = 0.0,
        subtotal_with_margin: float = 0.0,
        vat_amount: float = 0.0,
        final_price: float = 0.0,
    ):
        self.material_cost = round(material_cost, 2)
        self.gemstone_cost = round(gemstone_cost, 2)
        self.labor_cost = round(labor_cost, 2)
        self.subtotal = round(subtotal, 2)
        self.margin_amount = round(margin_amount, 2)
        self.subtotal_with_margin = round(subtotal_with_margin, 2)
        self.vat_amount = round(vat_amount, 2)
        self.final_price = round(final_price, 2)

    def to_dict(self) -> Dict[str, float]:
        """Convert to dictionary"""
        return {
            'material_cost': self.material_cost,
            'gemstone_cost': self.gemstone_cost,
            'labor_cost': self.labor_cost,
            'subtotal': self.subtotal,
            'margin_amount': self.margin_amount,
            'margin_percent': 0.0,  # Will be filled by service
            'subtotal_with_margin': self.subtotal_with_margin,
            'vat_amount': self.vat_amount,
            'vat_percent': 0.0,  # Will be filled by service
            'final_price': self.final_price,
        }


class CostCalculationService:
    """
    Service for automatic cost and price calculation for goldsmith orders.

    Calculation Formula:
    1. Material Cost = Weight (g) × Price per gram [override possible]
    2. Gemstone Cost = Sum of all gemstone costs
    3. Labor Cost = Hours × Hourly rate
    4. Subtotal = Material + Gemstones + Labor
    5. With Margin = Subtotal × (1 + Margin%)
    6. With VAT = With Margin × (1 + VAT%)
    7. Final Price = Rounded to .00 or .99
    """

    @staticmethod
    async def calculate_order_cost(
        db: AsyncSession,
        order_id: int
    ) -> PriceBreakdown:
        """
        Calculate complete cost breakdown for an order.

        Uses MetalInventoryService to get real inventory prices based on
        the order's metal_type and costing_method.

        Args:
            db: Database session
            order_id: Order ID

        Returns:
            PriceBreakdown with all cost components

        Raises:
            ValueError: If order not found or insufficient inventory
        """
        # Fetch order with gemstones
        result = await db.execute(
            select(OrderModel)
            .options(selectinload(OrderModel.gemstones))
            .filter(OrderModel.id == order_id)
        )
        order = result.scalar_one_or_none()

        if not order:
            raise ValueError(f"Order {order_id} not found")

        # 1. Material Cost (from inventory)
        material_cost = await CostCalculationService._calculate_material_cost(
            db, order
        )

        # 2. Gemstone Cost
        gemstone_cost = await CostCalculationService._calculate_gemstone_cost(order)

        # 3. Labor Cost
        labor_cost = await CostCalculationService._calculate_labor_cost(order)

        # 4. Subtotal
        subtotal = material_cost + gemstone_cost + labor_cost

        # 5. Apply profit margin
        margin_percent = order.profit_margin_percent or 40.0
        margin_amount = subtotal * (margin_percent / 100.0)
        subtotal_with_margin = subtotal + margin_amount

        # 6. Apply VAT
        vat_percent = order.vat_rate or 19.0
        vat_amount = subtotal_with_margin * (vat_percent / 100.0)
        total_with_vat = subtotal_with_margin + vat_amount

        # 7. Round final price
        final_price = CostCalculationService._round_price(total_with_vat)

        breakdown = PriceBreakdown(
            material_cost=material_cost,
            gemstone_cost=gemstone_cost,
            labor_cost=labor_cost,
            subtotal=subtotal,
            margin_amount=margin_amount,
            subtotal_with_margin=subtotal_with_margin,
            vat_amount=vat_amount,
            final_price=final_price,
        )

        # Add percentages to dict
        result_dict = breakdown.to_dict()
        result_dict['margin_percent'] = margin_percent
        result_dict['vat_percent'] = vat_percent

        logger.info(
            "Cost calculation completed",
            extra={
                "order_id": order_id,
                "material_cost": material_cost,
                "gemstone_cost": gemstone_cost,
                "labor_cost": labor_cost,
                "final_price": final_price,
            }
        )

        return breakdown

    @staticmethod
    async def _calculate_material_cost(
        db: AsyncSession,
        order: OrderModel
    ) -> float:
        """
        Calculate material cost from real metal inventory.

        Uses MetalInventoryService to get actual cost based on:
        - Order's metal_type
        - Order's estimated_weight_g (with scrap percentage)
        - Order's costing_method (FIFO/LIFO/AVERAGE/SPECIFIC)

        Args:
            db: Database session
            order: Order model instance

        Returns:
            Material cost in EUR

        Raises:
            ValueError: If insufficient inventory
        """
        # Check for manual override first
        if order.material_cost_override is not None:
            logger.debug(
                "Using manual material cost override",
                extra={
                    "order_id": order.id,
                    "override_cost": order.material_cost_override
                }
            )
            return order.material_cost_override

        # If no metal type specified, cannot calculate from inventory
        if not order.metal_type:
            logger.warning(
                "Order has no metal_type specified - cannot calculate material cost from inventory",
                extra={"order_id": order.id}
            )
            return 0.0

        # Use estimated or actual weight
        weight_g = order.actual_weight_g or order.estimated_weight_g

        if not weight_g or weight_g <= 0:
            logger.warning(
                "No weight specified for order - cannot calculate material cost",
                extra={"order_id": order.id}
            )
            return 0.0

        # Apply scrap percentage (material loss during work)
        scrap_percent = order.scrap_percentage or 5.0
        effective_weight = weight_g * (1 + scrap_percent / 100.0)

        # Get allocation from MetalInventoryService
        # This calculates cost WITHOUT consuming inventory (preview mode)
        try:
            costing_method = order.costing_method_used or CostingMethod.FIFO

            allocation = await MetalInventoryService.allocate_material(
                db,
                metal_type=order.metal_type,
                required_weight_g=effective_weight,
                costing_method=costing_method,
                specific_purchase_id=order.specific_metal_purchase_id
            )

            material_cost = allocation.total_cost

            logger.info(
                "Material cost calculated from inventory",
                extra={
                    "order_id": order.id,
                    "metal_type": order.metal_type.value,
                    "weight_g": weight_g,
                    "scrap_percent": scrap_percent,
                    "effective_weight": round(effective_weight, 2),
                    "costing_method": costing_method.value,
                    "material_cost": round(material_cost, 2),
                    "batches_used": len(allocation.allocations)
                }
            )

            return material_cost

        except ValueError as e:
            # Insufficient inventory or other allocation error
            logger.error(
                "Failed to allocate material from inventory",
                extra={
                    "order_id": order.id,
                    "metal_type": order.metal_type.value,
                    "required_weight": round(effective_weight, 2),
                    "error": str(e)
                }
            )
            # Re-raise with more context
            raise ValueError(
                f"Cannot calculate material cost for order {order.id}: {e}"
            ) from e

    @staticmethod
    async def _calculate_gemstone_cost(order: OrderModel) -> float:
        """Calculate total cost of all gemstones"""
        if not order.gemstones:
            return 0.0

        total = sum(
            (gem.cost * gem.quantity) for gem in order.gemstones
        )

        logger.debug(
            "Gemstone cost calculated",
            extra={
                "order_id": order.id,
                "gemstone_count": len(order.gemstones),
                "total_cost": total,
            }
        )

        return total

    @staticmethod
    async def _calculate_labor_cost(order: OrderModel) -> float:
        """Calculate labor cost from hours × rate"""
        if not order.labor_hours:
            return 0.0

        hourly_rate = order.hourly_rate or 75.0  # Default 75 EUR/hour
        labor_cost = order.labor_hours * hourly_rate

        logger.debug(
            "Labor cost calculated",
            extra={
                "order_id": order.id,
                "labor_hours": order.labor_hours,
                "hourly_rate": hourly_rate,
                "labor_cost": labor_cost,
            }
        )

        return labor_cost

    @staticmethod
    def _round_price(price: float) -> float:
        """
        Round price to .00 or .99

        Examples:
        - 243.45 → 243.00
        - 245.67 → 245.99
        - 248.12 → 248.00
        """
        # Round to nearest integer
        rounded = round(price)

        # If original price is close to .50 or higher, use .99
        decimal_part = price - int(price)
        if decimal_part >= 0.50:
            return rounded - 0.01  # x.99

        return float(rounded)  # x.00

    @staticmethod
    async def update_order_calculated_price(
        db: AsyncSession,
        order_id: int,
        price_breakdown: Optional[PriceBreakdown] = None
    ) -> OrderModel:
        """
        Update order with calculated costs and price.

        Stores calculated values in order fields for reference.
        """
        if price_breakdown is None:
            price_breakdown = await CostCalculationService.calculate_order_cost(
                db, order_id
            )

        # Fetch order
        result = await db.execute(
            select(OrderModel).filter(OrderModel.id == order_id)
        )
        order = result.scalar_one()

        # Update calculated fields
        order.material_cost_calculated = price_breakdown.material_cost
        order.labor_cost = price_breakdown.labor_cost
        order.calculated_price = price_breakdown.final_price

        # Don't override manual price if set
        if order.price is None:
            order.price = price_breakdown.final_price

        await db.commit()
        await db.refresh(order)

        logger.info(
            "Order price updated",
            extra={
                "order_id": order_id,
                "calculated_price": price_breakdown.final_price,
                "final_price": order.price,
            }
        )

        return order
