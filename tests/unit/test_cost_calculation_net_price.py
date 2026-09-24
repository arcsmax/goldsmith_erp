"""Unit tests for the net-price fix on ``Order.price`` writes.

ADR-2026-09-25 (price-semantics) establishes that ``Order.price`` is NET
(excluding VAT). ``CostCalculationService.update_order_calculated_price``
previously wrote the GROSS ``final_price`` (subtotal + margin + VAT) into
``Order.price`` when it was empty, double-taxing the order at invoicing
time. This must write the NET ``subtotal_with_margin`` instead.

See docs/architecture/ADR-2026-09-25-price-semantics.md, "Consequences and
open items" (BE-01 follow-up).
"""

import pytest

from goldsmith_erp.services.cost_calculation_service import CostCalculationService


@pytest.mark.asyncio
class TestUpdateOrderCalculatedPriceWritesNetPrice:
    """``update_order_calculated_price`` must persist the NET price."""

    async def test_writes_net_price_not_gross_when_price_is_empty(
        self, db_session, sample_order
    ):
        """Net 1000.00 with 19% VAT must yield price=1000.00, not 1190.00."""
        sample_order.price = None
        sample_order.material_cost_override = 1000.0
        sample_order.profit_margin_percent = 0.0
        sample_order.vat_rate = 19.0
        sample_order.labor_hours = None
        sample_order.hourly_rate = None
        await db_session.flush()

        order = await CostCalculationService.update_order_calculated_price(
            db_session, sample_order.id
        )

        # NET (pre-VAT) figure, not the gross 1190.00 (1000 * 1.19).
        assert order.price == pytest.approx(1000.00, rel=0.001)
        # The gross figure is still tracked separately via calculated_price.
        assert order.calculated_price == pytest.approx(1190.00, rel=0.001)

    async def test_writes_net_price_with_margin_applied(self, db_session, sample_order):
        """Net price includes margin but excludes VAT."""
        sample_order.price = None
        sample_order.material_cost_override = 1000.0
        sample_order.profit_margin_percent = 20.0
        sample_order.vat_rate = 19.0
        sample_order.labor_hours = None
        sample_order.hourly_rate = None
        await db_session.flush()

        order = await CostCalculationService.update_order_calculated_price(
            db_session, sample_order.id
        )

        # Subtotal 1000 * 1.20 margin = 1200.00 (net, before VAT).
        assert order.price == pytest.approx(1200.00, rel=0.001)

    async def test_does_not_override_manually_set_price(self, db_session, sample_order):
        """A manually-set price is left untouched (existing behaviour)."""
        sample_order.price = 42.00
        sample_order.material_cost_override = 1000.0
        sample_order.profit_margin_percent = 0.0
        sample_order.vat_rate = 19.0
        await db_session.flush()

        order = await CostCalculationService.update_order_calculated_price(
            db_session, sample_order.id
        )

        assert order.price == pytest.approx(42.00, rel=0.001)
