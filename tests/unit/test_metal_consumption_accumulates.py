"""
Regression tests for BE-07 — metal consumption must ACCUMULATE.

Prior bug: ``MetalInventoryService.consume_material`` step 5 did a plain
assignment (``order.material_cost_calculated = allocation.total_cost``,
``order.actual_weight_g = usage_data.weight_used_g``) instead of adding to
whatever was already recorded. A second consumption on the same order (e.g.
casting, then a later sizing/repair top-up) silently discarded the first
one's cost and weight.

These tests pin the fixed behaviour:
  1. Two sequential ``consume_material`` calls on one order SUM their cost
     and weight on the order aggregate fields.
  2. ``CostCalculationService._calculate_material_cost`` prefers the
     recorded ``MaterialUsage`` total once usage exists, instead of
     re-previewing a fresh allocation against current (already-reduced)
     remaining stock — which used to double-count consumed metal or blow
     up with "Insufficient inventory" once a batch was exhausted.
"""

from datetime import datetime

import pytest

from goldsmith_erp.db.models import MetalPurchase
from goldsmith_erp.models.metal_inventory import (
    CostingMethod,
    MaterialUsageCreate,
    MetalType,
)
from goldsmith_erp.services.cost_calculation_service import CostCalculationService
from goldsmith_erp.services.metal_inventory_service import MetalInventoryService


@pytest.fixture
async def gold_750_batch(db_session):
    """100g of 18K (750) gold at 65.00 EUR/g — plenty of headroom for two draws."""
    purchase = MetalPurchase(
        date_purchased=datetime.utcnow(),
        metal_type=MetalType.GOLD_18K,
        weight_g=100.0,
        remaining_weight_g=100.0,
        price_total=6500.00,
        price_per_gram=65.00,
        supplier="Accumulation Test Supplier",
        invoice_number="ACC-001",
    )
    db_session.add(purchase)
    await db_session.commit()
    await db_session.refresh(purchase)
    return purchase


@pytest.mark.asyncio
class TestMetalConsumptionAccumulates:
    async def test_two_consumptions_sum_cost_and_weight(
        self, db_session, gold_750_batch, sample_order
    ):
        """Casting (12g, 780.00) then sizing (1.5g, 97.50): the order
        aggregate must be the SUM (877.50 / 13.5g), not just the second
        call's numbers."""
        first = await MetalInventoryService.consume_material(
            db_session,
            MaterialUsageCreate(
                order_id=sample_order.id,
                weight_used_g=12.0,
                costing_method=CostingMethod.FIFO,
            ),
            MetalType.GOLD_18K,
        )
        assert first.cost_at_time == pytest.approx(780.00, rel=0.001)

        await db_session.refresh(sample_order)
        assert sample_order.material_cost_calculated == pytest.approx(780.00, rel=0.001)
        assert sample_order.actual_weight_g == pytest.approx(12.0, rel=0.001)

        second = await MetalInventoryService.consume_material(
            db_session,
            MaterialUsageCreate(
                order_id=sample_order.id,
                weight_used_g=1.5,
                costing_method=CostingMethod.FIFO,
            ),
            MetalType.GOLD_18K,
        )
        assert second.cost_at_time == pytest.approx(97.50, rel=0.001)

        await db_session.refresh(sample_order)
        assert sample_order.material_cost_calculated == pytest.approx(
            877.50, rel=0.001
        ), "second consumption must ADD to the first, not overwrite it"
        assert sample_order.actual_weight_g == pytest.approx(13.5, rel=0.001)

        # The metal batch itself must reflect BOTH draws.
        await db_session.refresh(gold_750_batch)
        assert gold_750_batch.remaining_weight_g == pytest.approx(86.5, abs=0.01)

    async def test_three_consumptions_keep_accumulating(
        self, db_session, gold_750_batch, sample_order
    ):
        """A third draw keeps summing rather than resetting to itself."""
        for weight in (5.0, 3.0, 2.0):
            await MetalInventoryService.consume_material(
                db_session,
                MaterialUsageCreate(
                    order_id=sample_order.id,
                    weight_used_g=weight,
                    costing_method=CostingMethod.FIFO,
                ),
                MetalType.GOLD_18K,
            )

        await db_session.refresh(sample_order)
        # (5 + 3 + 2) * 65.00 = 650.00; weight = 10.0g
        assert sample_order.material_cost_calculated == pytest.approx(650.00, rel=0.001)
        assert sample_order.actual_weight_g == pytest.approx(10.0, rel=0.001)


@pytest.mark.asyncio
class TestCostCalculationUsesRecordedUsage:
    """BE-07 companion fix in CostCalculationService: once material has
    actually been consumed for an order, cost calculation must use the
    recorded total instead of re-allocating a fresh preview against
    current (already-depleted) remaining stock."""

    async def test_preview_after_consumption_uses_recorded_sum(
        self, db_session, gold_750_batch, sample_order
    ):
        await MetalInventoryService.consume_material(
            db_session,
            MaterialUsageCreate(
                order_id=sample_order.id,
                weight_used_g=12.0,
                costing_method=CostingMethod.FIFO,
            ),
            MetalType.GOLD_18K,
        )
        await MetalInventoryService.consume_material(
            db_session,
            MaterialUsageCreate(
                order_id=sample_order.id,
                weight_used_g=1.5,
                costing_method=CostingMethod.FIFO,
            ),
            MetalType.GOLD_18K,
        )

        await db_session.refresh(sample_order)
        # Deliberately mismatched estimate: if the preview path ran, it
        # would try to allocate ~1050g (way beyond the 86.5g left in the
        # batch) and raise "Insufficient inventory". The recorded-usage
        # path must short-circuit before ever calling allocate_material.
        sample_order.estimated_weight_g = 1000.0
        sample_order.metal_type = MetalType.GOLD_18K
        sample_order.costing_method_used = CostingMethod.FIFO
        await db_session.flush()

        cost = await CostCalculationService._calculate_material_cost(
            db_session, sample_order
        )

        assert cost == pytest.approx(877.50, rel=0.001)
