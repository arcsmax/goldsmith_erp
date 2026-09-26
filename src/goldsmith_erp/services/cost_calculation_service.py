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
from decimal import ROUND_FLOOR, Decimal
from typing import Any, Dict, Optional, cast

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from goldsmith_erp.core.config import settings
from goldsmith_erp.db.models import Activity as ActivityModel
from goldsmith_erp.db.models import CostingMethod
from goldsmith_erp.db.models import Gemstone as GemstoneModel
from goldsmith_erp.db.models import MaterialUsage as MaterialUsageModel
from goldsmith_erp.db.models import Order as OrderModel
from goldsmith_erp.models._common import DecimalLike, dec, money
from goldsmith_erp.services.metal_inventory_service import MetalInventoryService

logger = logging.getLogger(__name__)


class PriceBreakdown:
    """Data class for price breakdown"""

    def __init__(
        self,
        material_cost: DecimalLike = 0,
        gemstone_cost: DecimalLike = 0,
        labor_cost: DecimalLike = 0,
        subtotal: DecimalLike = 0,
        margin_amount: DecimalLike = 0,
        subtotal_with_margin: DecimalLike = 0,
        vat_amount: DecimalLike = 0,
        final_price: DecimalLike = 0,
    ):
        # Decimal, rounded to the cent with ROUND_HALF_UP (BE-14).
        self.material_cost = money(material_cost)
        self.gemstone_cost = money(gemstone_cost)
        self.labor_cost = money(labor_cost)
        self.subtotal = money(subtotal)
        self.margin_amount = money(margin_amount)
        self.subtotal_with_margin = money(subtotal_with_margin)
        self.vat_amount = money(vat_amount)
        self.final_price = money(final_price)

    def to_dict(self) -> Dict[str, float]:
        """Convert to a JSON-ready dictionary (numbers stay JSON numbers)."""
        return {
            "material_cost": float(self.material_cost),
            "gemstone_cost": float(self.gemstone_cost),
            "labor_cost": float(self.labor_cost),
            "subtotal": float(self.subtotal),
            "margin_amount": float(self.margin_amount),
            "margin_percent": 0.0,  # Will be filled by service
            "subtotal_with_margin": float(self.subtotal_with_margin),
            "vat_amount": float(self.vat_amount),
            "vat_percent": 0.0,  # Will be filled by service
            "final_price": float(self.final_price),
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
    async def calculate_order_cost(db: AsyncSession, order_id: int) -> PriceBreakdown:
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
        material_cost = await CostCalculationService._calculate_material_cost(db, order)

        # 2. Gemstone Cost
        gemstone_cost = await CostCalculationService._calculate_gemstone_cost(order)

        # 3. Labor Cost
        labor_cost = await CostCalculationService._calculate_labor_cost(order)

        # 4. Subtotal
        subtotal = material_cost + gemstone_cost + labor_cost

        # 5. Apply profit margin — use explicit None check, 0.0 is valid (no margin)
        margin_percent = dec(order.profit_margin_percent, default=40)
        margin_amount = subtotal * margin_percent / 100
        subtotal_with_margin = subtotal + margin_amount

        # 6. Apply VAT
        vat_percent = dec(order.vat_rate, default=19)
        vat_amount = subtotal_with_margin * vat_percent / 100
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
        result_dict["margin_percent"] = float(margin_percent)
        result_dict["vat_percent"] = float(vat_percent)

        logger.info(
            "Cost calculation completed",
            extra={
                "order_id": order_id,
                "material_cost": material_cost,
                "gemstone_cost": gemstone_cost,
                "labor_cost": labor_cost,
                "final_price": final_price,
            },
        )

        return breakdown

    @staticmethod
    async def _calculate_material_cost(db: AsyncSession, order: OrderModel) -> Decimal:
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
                    "override_cost": order.material_cost_override,
                },
            )
            return dec(order.material_cost_override)

        # BE-07: once material has actually been consumed for this order,
        # MaterialUsage rows are the authoritative record of what it cost —
        # use their SUM instead of re-previewing a fresh allocation against
        # CURRENT remaining stock. The old preview-always approach either
        # double-counted already-consumed metal (previewing on top of what
        # was already drawn) or raised "Insufficient inventory" once a batch
        # was exhausted by the real consumption. Only orders with NO
        # recorded usage yet fall through to the estimate-based preview
        # below (Decimal summation — house convention for money, see
        # invoice_service.py / scrap_gold_service.py).
        recorded_usage_result = await db.execute(
            select(MaterialUsageModel.cost_at_time).where(
                MaterialUsageModel.order_id == order.id
            )
        )
        recorded_costs = recorded_usage_result.scalars().all()
        if recorded_costs:
            total_recorded_cost = sum((dec(c) for c in recorded_costs), Decimal("0"))
            logger.debug(
                "Using recorded MaterialUsage total instead of preview allocation",
                extra={
                    "order_id": order.id,
                    "usage_row_count": len(recorded_costs),
                    "material_cost": float(total_recorded_cost),
                },
            )
            return total_recorded_cost

        # If no metal type specified, cannot calculate from inventory
        if not order.metal_type:
            logger.warning(
                "Order has no metal_type specified - cannot calculate material cost from inventory",
                extra={"order_id": order.id},
            )
            return Decimal("0")

        # Use estimated or actual weight
        weight_g = dec(order.actual_weight_g or order.estimated_weight_g)

        if not weight_g or weight_g <= 0:
            logger.warning(
                "No weight specified for order - cannot calculate material cost",
                extra={"order_id": order.id},
            )
            return Decimal("0")

        # Apply scrap percentage (material loss during work).
        # Use explicit None check — 0.0 is a valid scrap percentage (no waste).
        scrap_percent = dec(order.scrap_percentage, default=5)
        effective_weight = weight_g * (1 + scrap_percent / 100)

        # Get allocation from MetalInventoryService
        # This calculates cost WITHOUT consuming inventory (preview mode)
        try:
            costing_method = order.costing_method_used or CostingMethod.FIFO

            allocation = await MetalInventoryService.allocate_material(
                db,
                metal_type=order.metal_type,
                required_weight_g=effective_weight,
                costing_method=costing_method,
                specific_purchase_id=order.specific_metal_purchase_id,
            )

            material_cost = dec(allocation.total_cost)

            logger.info(
                "Material cost calculated from inventory",
                extra={
                    "order_id": order.id,
                    "metal_type": order.metal_type.value,
                    "weight_g": weight_g,
                    "scrap_percent": scrap_percent,
                    "effective_weight": float(money(effective_weight)),
                    "costing_method": costing_method.value,
                    "material_cost": float(money(material_cost)),
                    "batches_used": len(allocation.allocations),
                },
            )

            return material_cost

        except ValueError as e:
            # Insufficient inventory or other allocation error
            logger.error(
                "Failed to allocate material from inventory",
                extra={
                    "order_id": order.id,
                    "metal_type": order.metal_type.value,
                    "required_weight": float(money(effective_weight)),
                    "error": str(e),
                },
            )
            # Re-raise with more context
            raise ValueError(
                f"Cannot calculate material cost for order {order.id}: {e}"
            ) from e

    @staticmethod
    async def _calculate_gemstone_cost(order: OrderModel) -> Decimal:
        """Calculate total cost of all gemstones"""
        if not order.gemstones:
            return Decimal("0")

        total = sum(
            (dec(gem.cost) * dec(gem.quantity, default=1) for gem in order.gemstones),
            Decimal("0"),
        )

        logger.debug(
            "Gemstone cost calculated",
            extra={
                "order_id": order.id,
                "gemstone_count": len(order.gemstones),
                "total_cost": total,
            },
        )

        return total

    @staticmethod
    async def _calculate_labor_cost(
        order: OrderModel,
        db: Optional[AsyncSession] = None,
        activity_hours: Optional[Dict[int, float]] = None,
    ) -> Decimal:
        """Calculate labor cost from hours × rate.

        Two modes, kept backward-compatible for existing callers:

        1. Aggregate (default): ``order.labor_hours`` × ``order.hourly_rate``,
           falling back to the shop default (``settings.DEFAULT_HOURLY_RATE``)
           when the order has no rate set. Unchanged behaviour.
        2. Per-activity breakdown: pass ``activity_hours`` (``{activity_id:
           hours}``, e.g. from a labor estimate) together with ``db`` to cost
           each activity at its own ``Activity.hourly_rate`` — falling back
           to the same shop default per-activity when unset.
        """
        if activity_hours is not None:
            if db is None:
                raise ValueError(
                    "db session is required when activity_hours is provided"
                )
            return await CostCalculationService._calculate_labor_cost_per_activity(
                db, activity_hours
            )

        if not order.labor_hours:
            return Decimal("0")

        hourly_rate = dec(order.hourly_rate or settings.DEFAULT_HOURLY_RATE)
        labor_cost = dec(order.labor_hours) * hourly_rate

        logger.debug(
            "Labor cost calculated",
            extra={
                "order_id": order.id,
                "labor_hours": order.labor_hours,
                "hourly_rate": hourly_rate,
                "labor_cost": labor_cost,
            },
        )

        return labor_cost

    @staticmethod
    async def _calculate_labor_cost_per_activity(
        db: AsyncSession,
        activity_hours: Dict[int, float],
    ) -> Decimal:
        """Sum labor cost across a per-activity ``{activity_id: hours}`` breakdown.

        Each activity's own ``hourly_rate`` is used when set; activities with
        no rate configured (NULL) — or an id not found in the DB — fall back
        to the shop default (``settings.DEFAULT_HOURLY_RATE``). Fails loudly
        only for programmer errors (empty/None input is a valid "no labor"
        case and returns 0.0).
        """
        if not activity_hours:
            return Decimal("0")

        result = await db.execute(
            select(ActivityModel).where(ActivityModel.id.in_(activity_hours.keys()))
        )
        # cast(): mypy sees Column[int] at class level for `a.id` (classic
        # declarative style, no Mapped[] annotations) — cast to the runtime
        # int so the dict key type matches `activity_hours`'s int keys.
        activities_by_id: Dict[int, ActivityModel] = {
            cast(int, a.id): a for a in result.scalars().all()
        }

        total_cost = Decimal("0")
        for activity_id, hours in activity_hours.items():
            activity = activities_by_id.get(activity_id)
            rate_column = activity.hourly_rate if activity is not None else None
            rate_decimal = cast(Optional[Decimal], rate_column)
            hourly_rate = (
                rate_decimal
                if rate_decimal is not None
                else dec(settings.DEFAULT_HOURLY_RATE)
            )
            total_cost += dec(hours) * hourly_rate

        logger.debug(
            "Per-activity labor cost calculated",
            extra={
                "activity_ids": list(activity_hours.keys()),
                "total_cost": total_cost,
            },
        )

        return total_cost

    @staticmethod
    def _round_price(price: DecimalLike) -> Decimal:
        """
        Psychological price rounding, explicit rule (BE-14):

        - cents below .50 are dropped: the price becomes ``x.00``
        - cents of .50 or more become ``x.99``

        Examples: 243.45 → 243.00, 243.49 → 243.00, 244.50 → 244.99,
        245.67 → 245.99, 248.12 → 248.00.

        The old float version used ``round()`` (banker's rounding), so
        244.50 came out as 243.99.
        """
        value = money(price)
        euros = value.to_integral_value(rounding=ROUND_FLOOR)
        if value - euros >= Decimal("0.50"):
            return euros + Decimal("0.99")
        return euros.quantize(Decimal("0.01"))

    @staticmethod
    async def update_order_calculated_price(
        db: AsyncSession,
        order_id: int,
        price_breakdown: Optional[PriceBreakdown] = None,
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
        result = await db.execute(select(OrderModel).filter(OrderModel.id == order_id))
        order = result.scalar_one()

        # Update calculated fields
        order.material_cost_calculated = price_breakdown.material_cost
        order.labor_cost = price_breakdown.labor_cost
        order.calculated_price = price_breakdown.final_price

        # Don't override manual price if set.
        #
        # ADR-2026-09-25 (price-semantics): Order.price is NET (excluding
        # VAT), so this must write subtotal_with_margin, not the gross
        # final_price (which still includes VAT and is kept separately in
        # calculated_price for cost-vs-price comparisons).
        if order.price is None:
            order.price = price_breakdown.subtotal_with_margin

        await db.commit()
        await db.refresh(order)

        logger.info(
            "Order price updated",
            extra={
                "order_id": order_id,
                "calculated_price_gross": price_breakdown.final_price,
                "order_price_net": order.price,
            },
        )

        return order
