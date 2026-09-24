"""
Regression tests for BE-08 — AVERAGE costing must draw ACROSS batches.

Prior bug: ``MetalInventoryService.allocate_material`` computed the correct
weighted-average PRICE across all available batches, but then built a
single ``MetalAllocation`` pinned to ``available_purchases[0]`` with
``weight_allocated_g=required_weight_g`` — i.e. it tried to take the ENTIRE
draw from one physical batch. Once that first batch was smaller than the
requested weight, the lock re-check in ``consume_material`` failed with a
misleading "concurrent consume" 400, and even when it happened to succeed
only one batch's ``remaining_weight_g`` moved, drifting per-batch stock
from reality.

Fix direction (master fix plan, W1-11 / BE-08): for AVERAGE, physically
draw FIFO across batches while pricing every gram at the weighted average.

Scenario pinned here (from the audit report): batch A has 10g, batch B has
100g; consuming 50g must succeed, leave A at 0 and B at 60, and price the
whole draw at the weighted average of the two batches.
"""

from datetime import datetime

import pytest

from goldsmith_erp.db.models import MetalPurchase
from goldsmith_erp.models.metal_inventory import (
    CostingMethod,
    MaterialUsageCreate,
    MetalType,
)
from goldsmith_erp.services.metal_inventory_service import MetalInventoryService


@pytest.fixture
async def two_batches(db_session):
    """Batch A: 10g @ 40.00 EUR/g (older). Batch B: 100g @ 51.00 EUR/g
    (newer). Weighted average = (10*40 + 100*51) / 110 = 5500/110 = 50.00
    EUR/g exactly — chosen so the expected numbers are clean."""
    batch_a = MetalPurchase(
        date_purchased=datetime(2025, 1, 1),
        metal_type=MetalType.GOLD_18K,
        weight_g=10.0,
        remaining_weight_g=10.0,
        price_total=400.00,
        price_per_gram=40.00,
        supplier="Batch A Supplier",
        invoice_number="AVG-A",
    )
    batch_b = MetalPurchase(
        date_purchased=datetime(2025, 6, 1),
        metal_type=MetalType.GOLD_18K,
        weight_g=100.0,
        remaining_weight_g=100.0,
        price_total=5100.00,
        price_per_gram=51.00,
        supplier="Batch B Supplier",
        invoice_number="AVG-B",
    )
    db_session.add_all([batch_a, batch_b])
    await db_session.commit()
    await db_session.refresh(batch_a)
    await db_session.refresh(batch_b)
    return batch_a, batch_b


@pytest.mark.asyncio
class TestAllocateAverageAcrossBatches:
    """Pure allocation planner — no DB writes."""

    async def test_average_allocation_spans_both_batches_at_weighted_price(
        self, db_session, two_batches
    ):
        batch_a, batch_b = two_batches

        allocation = await MetalInventoryService.allocate_material(
            db_session,
            metal_type=MetalType.GOLD_18K,
            required_weight_g=50.0,
            costing_method=CostingMethod.AVERAGE,
        )

        assert allocation.total_cost == pytest.approx(2500.00, rel=0.001)  # 50 * 50.00
        assert len(allocation.allocations) == 2

        first, second = allocation.allocations
        # FIFO physical draw: oldest batch (A) drained first.
        assert first.metal_purchase_id == batch_a.id
        assert first.weight_allocated_g == pytest.approx(10.0, abs=0.001)
        assert second.metal_purchase_id == batch_b.id
        assert second.weight_allocated_g == pytest.approx(40.0, abs=0.001)

        # BOTH allocations are priced at the weighted average, not each
        # batch's own price.
        assert first.price_per_gram == pytest.approx(50.00, rel=0.001)
        assert second.price_per_gram == pytest.approx(50.00, rel=0.001)

    async def test_average_allocation_within_first_batch_stays_single(
        self, db_session, two_batches
    ):
        """A draw that fits entirely inside the oldest batch is still a
        single allocation (no spurious splitting)."""
        allocation = await MetalInventoryService.allocate_material(
            db_session,
            metal_type=MetalType.GOLD_18K,
            required_weight_g=5.0,
            costing_method=CostingMethod.AVERAGE,
        )

        assert len(allocation.allocations) == 1
        assert allocation.allocations[0].price_per_gram == pytest.approx(
            50.00, rel=0.001
        )
        assert allocation.total_cost == pytest.approx(250.00, rel=0.001)


@pytest.mark.asyncio
class TestConsumeMaterialAverageAcrossBatches:
    """End-to-end: consume_material must physically decrement BOTH
    batches and record a single MaterialUsage at the weighted-average
    price."""

    async def test_consume_50g_average_drains_a_then_reduces_b(
        self, db_session, two_batches, sample_order
    ):
        batch_a, batch_b = two_batches

        usage = await MetalInventoryService.consume_material(
            db_session,
            MaterialUsageCreate(
                order_id=sample_order.id,
                weight_used_g=50.0,
                costing_method=CostingMethod.AVERAGE,
            ),
            MetalType.GOLD_18K,
        )

        assert usage.cost_at_time == pytest.approx(2500.00, rel=0.001)
        assert usage.price_per_gram_at_time == pytest.approx(50.00, rel=0.001)

        await db_session.refresh(batch_a)
        await db_session.refresh(batch_b)

        assert batch_a.remaining_weight_g == pytest.approx(0.0, abs=0.01)
        assert batch_b.remaining_weight_g == pytest.approx(60.0, abs=0.01)

        await db_session.refresh(sample_order)
        assert sample_order.material_cost_calculated == pytest.approx(
            2500.00, rel=0.001
        )
        assert sample_order.actual_weight_g == pytest.approx(50.0, rel=0.001)

    async def test_consume_across_batches_does_not_raise_concurrent_consume(
        self, db_session, two_batches, sample_order
    ):
        """The old bug raised a misleading 'concurrent consume' ValueError
        whenever the first available batch was smaller than the draw — even
        with zero actual concurrency. That must no longer happen."""
        try:
            await MetalInventoryService.consume_material(
                db_session,
                MaterialUsageCreate(
                    order_id=sample_order.id,
                    weight_used_g=50.0,
                    costing_method=CostingMethod.AVERAGE,
                ),
                MetalType.GOLD_18K,
            )
        except ValueError as exc:  # pragma: no cover - failure path
            pytest.fail(f"consume_material raised unexpectedly: {exc}")
