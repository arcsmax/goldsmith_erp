"""
Unit tests for MetalInventoryService

Tests cover:
- Metal purchase creation and management
- Material allocation (FIFO, LIFO, AVERAGE, SPECIFIC)
- Material consumption and inventory updates
- Inventory statistics and reporting
- Error handling (insufficient inventory, validation)
"""
import pytest
from datetime import datetime

from goldsmith_erp.services.metal_inventory_service import MetalInventoryService
from goldsmith_erp.models.metal_inventory import (
    MetalPurchaseCreate, MaterialUsageCreate, MetalType, CostingMethod
)
from goldsmith_erp.db.models import MetalPurchase, MaterialUsage


@pytest.mark.asyncio
class TestMetalPurchaseCreation:
    """Test metal purchase creation and validation"""

    async def test_create_purchase_success(self, db_session):
        """Test successful metal purchase creation"""
        purchase_data = MetalPurchaseCreate(
            metal_type=MetalType.GOLD_18K,
            weight_g=100.0,
            price_total=4500.00,
            supplier="Test Supplier"
        )

        purchase = await MetalInventoryService.create_purchase(db_session, purchase_data)

        assert purchase.id is not None
        assert purchase.metal_type == MetalType.GOLD_18K
        assert purchase.weight_g == 100.0
        assert purchase.remaining_weight_g == 100.0
        assert purchase.price_total == 4500.00
        assert purchase.price_per_gram == 45.00  # Auto-calculated

    async def test_create_purchase_calculates_price_per_gram(self, db_session):
        """Test automatic EUR/gram calculation"""
        purchase_data = MetalPurchaseCreate(
            metal_type=MetalType.SILVER_925,
            weight_g=500.0,
            price_total=250.00
        )

        purchase = await MetalInventoryService.create_purchase(db_session, purchase_data)

        assert purchase.price_per_gram == 0.50  # 250 / 500 = 0.50

    async def test_create_purchase_rounds_price(self, db_session):
        """Test price rounding to 2 decimal places"""
        purchase_data = MetalPurchaseCreate(
            metal_type=MetalType.GOLD_18K,
            weight_g=333.0,
            price_total=15000.00
        )

        purchase = await MetalInventoryService.create_purchase(db_session, purchase_data)

        # 15000 / 333 = 45.045045... should round to 45.05
        assert purchase.price_per_gram == 45.05


@pytest.mark.asyncio
class TestMaterialAllocation:
    """Test material allocation with different costing methods"""

    async def test_allocate_fifo_single_batch(self, db_session, sample_metal_purchase):
        """Test FIFO allocation from single batch"""
        allocation = await MetalInventoryService.allocate_material(
            db_session,
            metal_type=MetalType.GOLD_18K,
            required_weight_g=25.0,
            costing_method=CostingMethod.FIFO
        )

        assert allocation.required_weight_g == 25.0
        assert allocation.total_cost == 1125.00  # 25 * 45.00
        assert allocation.costing_method == CostingMethod.FIFO
        assert len(allocation.allocations) == 1
        assert allocation.allocations[0].metal_purchase_id == sample_metal_purchase.id

    async def test_allocate_fifo_multiple_batches(self, db_session, multiple_metal_purchases):
        """Test FIFO uses oldest batches first"""
        allocation = await MetalInventoryService.allocate_material(
            db_session,
            metal_type=MetalType.GOLD_18K,
            required_weight_g=150.0,  # Needs 2 batches
            costing_method=CostingMethod.FIFO
        )

        # Should use oldest first: 100g @ 44 EUR/g + 50g @ 45 EUR/g
        assert len(allocation.allocations) == 2
        assert allocation.allocations[0].price_per_gram == 44.00  # Oldest
        assert allocation.allocations[0].weight_allocated_g == 100.0
        assert allocation.allocations[1].price_per_gram == 45.00  # Second oldest
        assert allocation.allocations[1].weight_allocated_g == 50.0
        
        expected_cost = (100 * 44.00) + (50 * 45.00)
        assert allocation.total_cost == expected_cost

    async def test_allocate_lifo_uses_newest_first(self, db_session, multiple_metal_purchases):
        """Test LIFO uses newest batches first"""
        allocation = await MetalInventoryService.allocate_material(
            db_session,
            metal_type=MetalType.GOLD_18K,
            required_weight_g=150.0,
            costing_method=CostingMethod.LIFO
        )

        # Should use newest first: 100g @ 46 EUR/g + 50g @ 45 EUR/g
        assert len(allocation.allocations) == 2
        assert allocation.allocations[0].price_per_gram == 46.00  # Newest
        assert allocation.allocations[1].price_per_gram == 45.00  # Second newest

    async def test_allocate_average_cost(self, db_session, multiple_metal_purchases):
        """Test weighted average cost calculation"""
        allocation = await MetalInventoryService.allocate_material(
            db_session,
            metal_type=MetalType.GOLD_18K,
            required_weight_g=50.0,
            costing_method=CostingMethod.AVERAGE
        )

        # Total: 300g @ (4400 + 4500 + 4600) / 300 = 45.00 EUR/g average
        assert allocation.allocations[0].price_per_gram == 45.00
        assert allocation.total_cost == 2250.00  # 50 * 45.00

    async def test_allocate_specific_batch(self, db_session, sample_metal_purchase):
        """Test specific batch selection"""
        allocation = await MetalInventoryService.allocate_material(
            db_session,
            metal_type=MetalType.GOLD_18K,
            required_weight_g=25.0,
            costing_method=CostingMethod.SPECIFIC,
            specific_purchase_id=sample_metal_purchase.id
        )

        assert len(allocation.allocations) == 1
        assert allocation.allocations[0].metal_purchase_id == sample_metal_purchase.id
        assert allocation.total_cost == 1125.00

    async def test_allocate_specific_insufficient_weight(self, db_session, sample_metal_purchase):
        """Test error when specific batch has insufficient weight"""
        with pytest.raises(ValueError, match="only has 100"):
            await MetalInventoryService.allocate_material(
                db_session,
                metal_type=MetalType.GOLD_18K,
                required_weight_g=200.0,  # More than available
                costing_method=CostingMethod.SPECIFIC,
                specific_purchase_id=sample_metal_purchase.id
            )

    async def test_allocate_insufficient_inventory_total(self, db_session, sample_metal_purchase):
        """Test error when insufficient total inventory"""
        with pytest.raises(ValueError, match="Insufficient inventory"):
            await MetalInventoryService.allocate_material(
                db_session,
                metal_type=MetalType.GOLD_18K,
                required_weight_g=200.0,  # More than available (100g)
                costing_method=CostingMethod.FIFO
            )

    async def test_allocate_no_inventory_available(self, db_session):
        """Test error when no inventory exists"""
        with pytest.raises(ValueError, match="No inventory available"):
            await MetalInventoryService.allocate_material(
                db_session,
                metal_type=MetalType.GOLD_24K,  # No inventory for this type
                required_weight_g=10.0,
                costing_method=CostingMethod.FIFO
            )


@pytest.mark.asyncio
class TestMaterialConsumption:
    """Test material consumption and inventory updates"""

    async def test_consume_material_reduces_inventory(self, db_session, sample_metal_purchase, sample_order):
        """Test that consuming material reduces remaining_weight_g"""
        initial_weight = sample_metal_purchase.remaining_weight_g

        usage_data = MaterialUsageCreate(
            order_id=sample_order.id,
            weight_used_g=25.0,
            costing_method=CostingMethod.FIFO
        )

        usage = await MetalInventoryService.consume_material(
            db_session, usage_data, MetalType.GOLD_18K
        )

        # Refresh to get updated values
        await db_session.refresh(sample_metal_purchase)

        assert sample_metal_purchase.remaining_weight_g == 75.0  # 100 - 25
        assert usage.weight_used_g == 25.0
        assert usage.cost_at_time == 1125.00  # 25 * 45.00

    async def test_consume_material_creates_usage_record(self, db_session, sample_metal_purchase, sample_order):
        """Test that MaterialUsage record is created"""
        usage_data = MaterialUsageCreate(
            order_id=sample_order.id,
            weight_used_g=25.0,
            costing_method=CostingMethod.FIFO,
            notes="Test consumption"
        )

        usage = await MetalInventoryService.consume_material(
            db_session, usage_data, MetalType.GOLD_18K
        )

        assert usage.id is not None
        assert usage.order_id == sample_order.id
        assert usage.metal_purchase_id == sample_metal_purchase.id
        assert usage.notes == "Test consumption"

    async def test_consume_material_updates_order_cost(self, db_session, sample_metal_purchase, sample_order):
        """Test that Order.material_cost_calculated is updated"""
        usage_data = MaterialUsageCreate(
            order_id=sample_order.id,
            weight_used_g=25.0,
            costing_method=CostingMethod.FIFO
        )

        await MetalInventoryService.consume_material(
            db_session, usage_data, MetalType.GOLD_18K
        )

        # Refresh order
        await db_session.refresh(sample_order)

        assert sample_order.material_cost_calculated == 1125.00
        assert sample_order.actual_weight_g == 25.0


@pytest.mark.asyncio
class TestInventoryStatistics:
    """Test inventory statistics and reporting"""

    async def test_get_inventory_summary(self, db_session, sample_metal_purchase, silver_purchase):
        """Test inventory summary calculation"""
        stats = await MetalInventoryService.get_inventory_summary(db_session)

        assert stats.total_value == 4900.00  # 4500 (gold) + 400 (silver)
        assert stats.total_weight_g == 600.0  # 100 + 500
        assert len(stats.metal_types) == 2  # Gold and silver

        # Check gold summary
        gold_summary = next(s for s in stats.metal_types if s.metal_type == MetalType.GOLD_18K)
        assert gold_summary.total_weight_g == 100.0
        assert gold_summary.total_value == 4500.00
        assert gold_summary.average_price_per_gram == 45.00

    async def test_get_inventory_summary_low_stock_alert(self, db_session):
        """Test low stock alerts (< 50g)"""
        # Create purchase with low stock
        purchase_data = MetalPurchaseCreate(
            metal_type=MetalType.PLATINUM_950,
            weight_g=25.0,  # Low stock
            price_total=2500.00
        )
        await MetalInventoryService.create_purchase(db_session, purchase_data)

        stats = await MetalInventoryService.get_inventory_summary(db_session)

        assert len(stats.low_stock_alerts) > 0
        assert "platinum_950: 25.0g" in stats.low_stock_alerts


@pytest.mark.asyncio
class TestListPurchases:
    """Test listing and filtering metal purchases"""

    async def test_list_purchases_all(self, db_session, sample_metal_purchase):
        """Test listing all purchases"""
        purchases = await MetalInventoryService.list_purchases(db_session)

        assert len(purchases) == 1
        assert purchases[0].id == sample_metal_purchase.id

    async def test_list_purchases_filter_by_metal_type(self, db_session, sample_metal_purchase, silver_purchase):
        """Test filtering by metal type"""
        gold_purchases = await MetalInventoryService.list_purchases(
            db_session,
            metal_type=MetalType.GOLD_18K
        )

        assert len(gold_purchases) == 1
        assert gold_purchases[0].metal_type == MetalType.GOLD_18K

    async def test_list_purchases_exclude_depleted(self, db_session, sample_metal_purchase):
        """Test excluding depleted batches"""
        # Deplete the purchase
        sample_metal_purchase.remaining_weight_g = 0.0
        await db_session.commit()

        purchases = await MetalInventoryService.list_purchases(
            db_session,
            include_depleted=False
        )

        assert len(purchases) == 0

    async def test_list_purchases_include_depleted(self, db_session, sample_metal_purchase):
        """Test including depleted batches"""
        # Deplete the purchase
        sample_metal_purchase.remaining_weight_g = 0.0
        await db_session.commit()

        purchases = await MetalInventoryService.list_purchases(
            db_session,
            include_depleted=True
        )

        assert len(purchases) == 1
