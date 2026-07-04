"""
Unit tests for CostCalculationService

Tests cover:
- Material cost calculation with real inventory (FIFO, LIFO, AVERAGE, SPECIFIC)
- Labor cost calculation
- Profit margin calculations
- Manual cost overrides
- Error handling (missing metal_type, insufficient inventory)
- Integration with MetalInventoryService
"""
import pytest
from decimal import Decimal
from datetime import datetime

from goldsmith_erp.services.cost_calculation_service import CostCalculationService
from goldsmith_erp.services.metal_inventory_service import MetalInventoryService
from goldsmith_erp.models.metal_inventory import MetalPurchaseCreate
from goldsmith_erp.db.models import MetalType, CostingMethod, OrderStatusEnum


@pytest.mark.asyncio
class TestMaterialCostCalculation:
    """Test material cost calculation from real inventory"""

    async def test_material_cost_fifo_single_batch(
        self, db_session, sample_metal_purchase, order_with_metal_type
    ):
        """Test material cost calculated from inventory using FIFO"""
        # Order needs 30g, batch has 100g @ 45 EUR/g
        order_with_metal_type.estimated_weight_g = 30.0
        order_with_metal_type.scrap_percentage = 5.0
        order_with_metal_type.metal_type = MetalType.GOLD_18K
        order_with_metal_type.costing_method_used = CostingMethod.FIFO

        # Expected: 30g * 1.05 (scrap) = 31.5g * 45 EUR/g = 1417.50 EUR
        cost = await CostCalculationService._calculate_material_cost(
            db_session, order_with_metal_type
        )

        assert cost == pytest.approx(1417.50, rel=0.01)

    async def test_material_cost_fifo_multiple_batches(
        self, db_session, multiple_metal_purchases, sample_customer
    ):
        """Test FIFO allocation across multiple batches"""
        from goldsmith_erp.db.models import Order

        # Create order needing 150g (uses 2 batches)
        order = Order(
            title="Large Bracelet",
            customer_id=sample_customer.id,
            status=OrderStatusEnum.NEW,
            estimated_weight_g=150.0,
            metal_type=MetalType.GOLD_18K,
            costing_method_used=CostingMethod.FIFO,
            scrap_percentage=0.0  # No scrap for simple calculation
        )
        db_session.add(order)
        await db_session.commit()
        await db_session.refresh(order)

        # Expected: 100g @ 44 EUR/g + 50g @ 45 EUR/g = 4400 + 2250 = 6650 EUR
        cost = await CostCalculationService._calculate_material_cost(db_session, order)

        assert cost == pytest.approx(6650.00, rel=0.01)

    async def test_material_cost_lifo_uses_newest(
        self, db_session, multiple_metal_purchases, sample_customer
    ):
        """Test LIFO uses newest batches first"""
        from goldsmith_erp.db.models import Order

        order = Order(
            title="Gold Ring",
            customer_id=sample_customer.id,
            status=OrderStatusEnum.NEW,
            estimated_weight_g=150.0,
            metal_type=MetalType.GOLD_18K,
            costing_method_used=CostingMethod.LIFO,
            scrap_percentage=0.0
        )
        db_session.add(order)
        await db_session.commit()
        await db_session.refresh(order)

        # Expected: 100g @ 46 EUR/g + 50g @ 45 EUR/g = 4600 + 2250 = 6850 EUR
        cost = await CostCalculationService._calculate_material_cost(db_session, order)

        assert cost == pytest.approx(6850.00, rel=0.01)

    async def test_material_cost_average_method(
        self, db_session, multiple_metal_purchases, sample_customer
    ):
        """Test weighted average cost calculation"""
        from goldsmith_erp.db.models import Order

        order = Order(
            title="Gold Necklace",
            customer_id=sample_customer.id,
            status=OrderStatusEnum.NEW,
            estimated_weight_g=60.0,
            metal_type=MetalType.GOLD_18K,
            costing_method_used=CostingMethod.AVERAGE,
            scrap_percentage=0.0
        )
        db_session.add(order)
        await db_session.commit()
        await db_session.refresh(order)

        # Total: 300g @ (4400 + 4500 + 4600) / 300 = 45.00 EUR/g average
        # Expected: 60g * 45.00 = 2700.00 EUR
        cost = await CostCalculationService._calculate_material_cost(db_session, order)

        assert cost == pytest.approx(2700.00, rel=0.01)

    async def test_material_cost_specific_batch(
        self, db_session, sample_metal_purchase, order_with_metal_type
    ):
        """Test specific batch selection"""
        order_with_metal_type.estimated_weight_g = 25.0
        order_with_metal_type.scrap_percentage = 0.0
        order_with_metal_type.metal_type = MetalType.GOLD_18K
        order_with_metal_type.costing_method_used = CostingMethod.SPECIFIC
        order_with_metal_type.specific_metal_purchase_id = sample_metal_purchase.id

        # Expected: 25g * 45 EUR/g = 1125.00 EUR
        cost = await CostCalculationService._calculate_material_cost(
            db_session, order_with_metal_type
        )

        assert cost == pytest.approx(1125.00, rel=0.01)

    async def test_material_cost_with_scrap_percentage(
        self, db_session, sample_metal_purchase, order_with_metal_type
    ):
        """Test scrap percentage increases material needed"""
        # sample_metal_purchase has 100g — use 80g base so scrap (10%) stays within stock
        order_with_metal_type.estimated_weight_g = 80.0
        order_with_metal_type.scrap_percentage = 10.0  # 10% scrap
        order_with_metal_type.metal_type = MetalType.GOLD_18K

        # Expected: 80g * 1.10 (scrap) = 88g * 45 EUR/g = 3960.00 EUR
        cost = await CostCalculationService._calculate_material_cost(
            db_session, order_with_metal_type
        )

        assert cost == pytest.approx(3960.00, rel=0.01)

    async def test_material_cost_no_metal_type_returns_zero(
        self, db_session, sample_order
    ):
        """Test that missing metal_type returns 0 cost"""
        # sample_order has no metal_type set
        cost = await CostCalculationService._calculate_material_cost(
            db_session, sample_order
        )

        assert cost == 0.0

    async def test_material_cost_insufficient_inventory_raises_error(
        self, db_session, sample_metal_purchase, order_with_metal_type
    ):
        """Test error when insufficient inventory available"""
        order_with_metal_type.estimated_weight_g = 200.0  # More than 100g available
        order_with_metal_type.metal_type = MetalType.GOLD_18K
        order_with_metal_type.scrap_percentage = 0.0

        with pytest.raises(ValueError, match="Insufficient inventory"):
            await CostCalculationService._calculate_material_cost(
                db_session, order_with_metal_type
            )


@pytest.mark.asyncio
@pytest.mark.asyncio
class TestLaborCostCalculation:
    """Test labor cost calculations"""

    async def test_labor_cost_with_hours_and_rate(self, sample_order):
        """Test labor cost = hours * hourly_rate"""
        sample_order.labor_hours = 5.0
        sample_order.hourly_rate = 75.0

        cost = await CostCalculationService._calculate_labor_cost(sample_order)

        assert cost == 375.00  # 5 * 75

    async def test_labor_cost_defaults_to_zero(self, sample_order):
        """Test labor cost defaults to 0 when not specified"""
        sample_order.labor_hours = None
        sample_order.hourly_rate = None

        cost = await CostCalculationService._calculate_labor_cost(sample_order)

        assert cost == 0.0

    async def test_labor_cost_with_only_hours(self, sample_order):
        """Test labor cost when only hours specified defaults to 75 EUR/h rate"""
        sample_order.labor_hours = 10.0
        sample_order.hourly_rate = None

        cost = await CostCalculationService._calculate_labor_cost(sample_order)

        # Service defaults to 75.00 EUR/h when no rate is set
        assert cost == pytest.approx(750.0, rel=0.01)

    async def test_labor_cost_with_only_rate(self, sample_order):
        """Test labor cost when only rate specified (no hours)"""
        sample_order.labor_hours = None
        sample_order.hourly_rate = 80.0

        cost = await CostCalculationService._calculate_labor_cost(sample_order)

        assert cost == 0.0


@pytest.mark.asyncio
class TestPerActivityLaborCost:
    """Task 1 (V1.3 estimator) — per-activity hourly-rate labor costing.

    ``_calculate_labor_cost`` gains an optional ``(db, activity_hours)`` mode
    that costs each activity at its own ``Activity.hourly_rate``, falling
    back to the shop default (``settings.DEFAULT_HOURLY_RATE``) per-activity
    when unset — without disturbing the existing aggregate-hours callers
    exercised by ``TestLaborCostCalculation`` above.
    """

    async def test_labor_cost_per_activity_with_explicit_rate(
        self, db_session, sample_order
    ):
        """Activity.hourly_rate=90 over 2h => 180 (its own rate wins)."""
        from goldsmith_erp.db.models import Activity

        activity = Activity(
            name="Fassen", category="fabrication", hourly_rate=Decimal("90.00")
        )
        db_session.add(activity)
        await db_session.commit()
        await db_session.refresh(activity)

        cost = await CostCalculationService._calculate_labor_cost(
            sample_order, db=db_session, activity_hours={activity.id: 2.0}
        )

        assert cost == pytest.approx(180.0, rel=0.001)

    async def test_labor_cost_per_activity_falls_back_to_shop_default(
        self, db_session, sample_order
    ):
        """Activity.hourly_rate=None falls back to settings.DEFAULT_HOURLY_RATE."""
        from goldsmith_erp.core.config import settings
        from goldsmith_erp.db.models import Activity

        activity = Activity(
            name="Polieren", category="fabrication", hourly_rate=None
        )
        db_session.add(activity)
        await db_session.commit()
        await db_session.refresh(activity)

        cost = await CostCalculationService._calculate_labor_cost(
            sample_order, db=db_session, activity_hours={activity.id: 3.0}
        )

        assert cost == pytest.approx(3.0 * settings.DEFAULT_HOURLY_RATE, rel=0.001)

    async def test_labor_cost_mixed_per_activity_breakdown_sums_each_at_own_rate(
        self, db_session, sample_order
    ):
        """A mix of rated + unrated activities each cost at their own rate."""
        from goldsmith_erp.core.config import settings
        from goldsmith_erp.db.models import Activity

        rated = Activity(
            name="Gravieren", category="fabrication", hourly_rate=Decimal("120.00")
        )
        unrated = Activity(
            name="Verpacken", category="administration", hourly_rate=None
        )
        db_session.add_all([rated, unrated])
        await db_session.commit()
        await db_session.refresh(rated)
        await db_session.refresh(unrated)

        cost = await CostCalculationService._calculate_labor_cost(
            sample_order,
            db=db_session,
            activity_hours={rated.id: 1.5, unrated.id: 2.0},
        )

        expected = (1.5 * 120.0) + (2.0 * settings.DEFAULT_HOURLY_RATE)
        assert cost == pytest.approx(expected, rel=0.001)

    async def test_labor_cost_per_activity_without_db_raises(self, sample_order):
        """activity_hours without a db session fails loudly (programmer error)."""
        with pytest.raises(ValueError, match="db session"):
            await CostCalculationService._calculate_labor_cost(
                sample_order, activity_hours={1: 2.0}
            )

    async def test_labor_cost_per_activity_empty_breakdown_returns_zero(
        self, db_session, sample_order
    ):
        """An empty per-activity breakdown is a valid 'no labor' case."""
        cost = await CostCalculationService._calculate_labor_cost(
            sample_order, db=db_session, activity_hours={}
        )

        assert cost == 0.0

    async def test_labor_cost_aggregate_path_still_works(self, sample_order):
        """Backward compatibility: existing aggregate-hours callers (no
        activity_hours/db args) are unaffected by the new per-activity mode."""
        sample_order.labor_hours = 5.0
        sample_order.hourly_rate = 75.0

        cost = await CostCalculationService._calculate_labor_cost(sample_order)

        assert cost == 375.00


@pytest.mark.asyncio
class TestFullOrderCostCalculation:
    """Test complete order cost calculation"""

    async def test_calculate_order_cost_with_all_components(
        self, db_session, sample_metal_purchase, order_with_metal_type
    ):
        """Test full cost calculation with material + labor + profit + VAT"""
        # Setup order — flush so the service re-fetches updated values from DB
        order_with_metal_type.estimated_weight_g = 20.0
        order_with_metal_type.scrap_percentage = 5.0
        order_with_metal_type.metal_type = MetalType.GOLD_18K
        order_with_metal_type.costing_method_used = CostingMethod.FIFO
        order_with_metal_type.labor_hours = 3.0
        order_with_metal_type.hourly_rate = 75.0
        order_with_metal_type.profit_margin_percent = 40.0
        order_with_metal_type.vat_rate = 19.0
        await db_session.flush()

        result = await CostCalculationService.calculate_order_cost(
            db_session, order_with_metal_type.id
        )

        # Material: 20g * 1.05 = 21g * 45 EUR/g = 945.00 EUR
        assert result.material_cost == pytest.approx(945.00, rel=0.01)

        # Labor: 3h * 75 EUR/h = 225.00 EUR
        assert result.labor_cost == pytest.approx(225.00, rel=0.01)

        # Subtotal: 945 + 225 = 1170.00 EUR
        assert result.subtotal == pytest.approx(1170.00, rel=0.01)

        # Profit: 1170 * 0.40 = 468.00 EUR
        assert result.margin_amount == pytest.approx(468.00, rel=0.01)

        # Total before VAT: 1170 + 468 = 1638.00 EUR
        assert result.subtotal_with_margin == pytest.approx(1638.00, rel=0.01)

        # VAT: 1638 * 0.19 = 311.22 EUR
        assert result.vat_amount == pytest.approx(311.22, rel=0.01)

        # Final total: service rounds to .00/.99; 1638 + 311.22 = 1949.22 EUR
        assert result.final_price == pytest.approx(1949.22, rel=0.01)

    async def test_calculate_order_cost_material_only(
        self, db_session, sample_metal_purchase, order_with_metal_type
    ):
        """Test cost calculation with only material cost"""
        order_with_metal_type.estimated_weight_g = 10.0
        order_with_metal_type.scrap_percentage = 0.0
        order_with_metal_type.metal_type = MetalType.GOLD_18K
        order_with_metal_type.labor_hours = None
        order_with_metal_type.hourly_rate = None
        order_with_metal_type.profit_margin_percent = 0.0
        order_with_metal_type.vat_rate = 0.0
        await db_session.flush()

        result = await CostCalculationService.calculate_order_cost(
            db_session, order_with_metal_type.id
        )

        # Material: 10g * 45 EUR/g = 450.00 EUR; no margin, no VAT
        assert result.material_cost == pytest.approx(450.00, rel=0.01)
        assert result.labor_cost == 0.0
        assert result.subtotal == pytest.approx(450.00, rel=0.01)
        assert result.final_price == pytest.approx(450.00, rel=0.01)

    async def test_calculate_order_cost_with_manual_overrides(
        self, db_session, order_with_metal_type
    ):
        """Test material cost override takes precedence over inventory calculation"""
        # Only material_cost_override exists in the model; labor is calculated
        # order_with_metal_type fixture: labor_hours=4.0, hourly_rate=75.00 → 300
        order_with_metal_type.material_cost_override = 1000.0
        order_with_metal_type.profit_margin_percent = 20.0
        order_with_metal_type.vat_rate = 19.0
        await db_session.flush()

        result = await CostCalculationService.calculate_order_cost(
            db_session, order_with_metal_type.id
        )

        # Material uses override
        assert result.material_cost == 1000.0
        # Labor: 4h * 75 EUR/h = 300 (calculated, no labor override in model)
        assert result.labor_cost == pytest.approx(300.0, rel=0.01)

        # Subtotal: 1000 + 300 = 1300.00
        assert result.subtotal == pytest.approx(1300.00, rel=0.01)

        # Profit: 1300 * 0.20 = 260.00
        assert result.margin_amount == pytest.approx(260.00, rel=0.01)

        # Total before VAT: 1300 + 260 = 1560.00
        assert result.subtotal_with_margin == pytest.approx(1560.00, rel=0.01)

        # VAT: 1560 * 0.19 = 296.40
        assert result.vat_amount == pytest.approx(296.40, rel=0.01)

    async def test_calculate_order_cost_zero_profit_margin(
        self, db_session, sample_metal_purchase, order_with_metal_type
    ):
        """Test calculation with 0% profit margin"""
        order_with_metal_type.estimated_weight_g = 10.0
        order_with_metal_type.scrap_percentage = 0.0
        order_with_metal_type.metal_type = MetalType.GOLD_18K
        order_with_metal_type.labor_hours = 2.0
        order_with_metal_type.hourly_rate = 50.0
        order_with_metal_type.profit_margin_percent = 0.0
        order_with_metal_type.vat_rate = 19.0
        await db_session.flush()

        result = await CostCalculationService.calculate_order_cost(
            db_session, order_with_metal_type.id
        )

        # Material: 10g * 45 = 450, Labor: 2 * 50 = 100
        # Subtotal: 550, no profit margin, so subtotal_with_margin = 550
        assert result.margin_amount == 0.0
        assert result.subtotal_with_margin == pytest.approx(550.00, rel=0.01)


@pytest.mark.asyncio
class TestCostCalculationEdgeCases:
    """Test edge cases and error handling"""

    async def test_very_small_weight(
        self, db_session, sample_metal_purchase, order_with_metal_type
    ):
        """Test calculation with very small weight (0.5g)"""
        order_with_metal_type.estimated_weight_g = 0.5
        order_with_metal_type.scrap_percentage = 0.0
        order_with_metal_type.metal_type = MetalType.GOLD_18K
        await db_session.flush()

        result = await CostCalculationService.calculate_order_cost(
            db_session, order_with_metal_type.id
        )

        # 0.5g * 45 EUR/g = 22.50 EUR
        assert result.material_cost == pytest.approx(22.50, rel=0.01)

    async def test_high_scrap_percentage(
        self, db_session, sample_metal_purchase, order_with_metal_type
    ):
        """Test calculation with high scrap percentage (20%)"""
        order_with_metal_type.estimated_weight_g = 50.0
        order_with_metal_type.scrap_percentage = 20.0
        order_with_metal_type.metal_type = MetalType.GOLD_18K
        await db_session.flush()

        result = await CostCalculationService.calculate_order_cost(
            db_session, order_with_metal_type.id
        )

        # 50g * 1.20 = 60g * 45 EUR/g = 2700.00 EUR
        assert result.material_cost == pytest.approx(2700.00, rel=0.01)

    async def test_no_vat(
        self, db_session, sample_metal_purchase, order_with_metal_type
    ):
        """Test calculation with 0% VAT"""
        order_with_metal_type.estimated_weight_g = 10.0
        order_with_metal_type.scrap_percentage = 0.0
        order_with_metal_type.metal_type = MetalType.GOLD_18K
        order_with_metal_type.vat_rate = 0.0
        order_with_metal_type.profit_margin_percent = 0.0
        await db_session.flush()

        result = await CostCalculationService.calculate_order_cost(
            db_session, order_with_metal_type.id
        )

        assert result.vat_amount == 0.0
        assert result.final_price == result.subtotal_with_margin

    async def test_different_metal_types(
        self, db_session, silver_purchase, order_with_metal_type
    ):
        """Test calculation with different metal type (silver)"""
        order_with_metal_type.estimated_weight_g = 50.0
        order_with_metal_type.scrap_percentage = 0.0
        order_with_metal_type.metal_type = MetalType.SILVER_925
        order_with_metal_type.costing_method_used = CostingMethod.FIFO
        await db_session.flush()

        result = await CostCalculationService.calculate_order_cost(
            db_session, order_with_metal_type.id
        )

        # 50g * 0.80 EUR/g = 40.00 EUR (silver is cheaper)
        assert result.material_cost == pytest.approx(40.00, rel=0.01)
