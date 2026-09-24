"""
Unit tests for ScrapGoldService valuation (Altgold) — DOM-19 / DOM-20.

docs/review/2026-09-25/05-domain-product-fit.md, recommendation #3:
"Fix Altgold: alloy contract, per-metal valuation, no silent 0.0."

Definition of done exercised here:
- UI adds 15 g 585 + 8 g 750 -> 14.775 g fine gold.
- Adding 10 g Ag925 yields 9.25 g fine silver, valued at the SILVER price
  (not the gold price / not a manually-set gold override).
- An unknown alloy is rejected with a validation error (422 at the HTTP
  boundary), never silently valued as 0.0 fine content.

Before this fix:
- ``ScrapGoldItemCreate.alloy`` was a bare ``str`` and the frontend sent a
  ``number`` -> guaranteed 422 (the UI could never add an item at all).
- ``ScrapGoldService._recalculate_totals`` summed fine content across ALL
  metals and multiplied the total by a single ``gold_price_per_g`` -> a
  silver item was credited at ~90x its real value.
- ``ALLOY_RATIOS.get(alloy, 0.0)`` silently returned 0.0 for any alloy code
  it didn't recognise (e.g. the bare string "925" instead of "ag925").
"""

from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from goldsmith_erp.db.models import AlloyType, MetalPriceSource, MetalType
from goldsmith_erp.models.scrap_gold import ScrapGoldCreate, ScrapGoldItemCreate
from goldsmith_erp.services.metal_price_service import MetalPriceService
from goldsmith_erp.services.scrap_gold_service import ScrapGoldService


def _eur(*fine_and_price_pairs: tuple[float, float]) -> float:
    """Sum fine_g * price_per_g pairs and round EUR the same way the
    service does (Decimal, ROUND_HALF_UP, 2 decimals) — so test
    expectations never drift from the production rounding rule."""
    total = Decimal("0")
    for fine_g, price_per_g in fine_and_price_pairs:
        total += Decimal(str(fine_g)) * Decimal(str(price_per_g))
    return float(total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


# ---------------------------------------------------------------------------
# Deterministic, fixed metal spot prices for every test in this module.
#
# Unit tests must never connect to Redis (tests/conftest.py's own
# mock_publish_event docstring states this project convention). Without
# this patch, ScrapGoldService._recalculate_totals would drive
# MetalPriceService.get_spot_prices through its live 4-tier fallback chain
# (Redis cache -> external API -> DB history -> hardcoded settings), which
# is slow, network-dependent, and — critically for these tests — collapses
# gold and silver onto whatever the *same* hardcoded fallback constants
# happen to be, making a DOM-20 regression (silver priced as gold) much
# harder to catch. Fixing gold and silver at clearly distinct rates makes
# any accidental cross-metal pricing bug fail loudly.
# ---------------------------------------------------------------------------
GOLD_SPOT_EUR_PER_G = 60.0
SILVER_SPOT_EUR_PER_G = 0.90
PLATINUM_SPOT_EUR_PER_G = 32.0

_FIXED_SPOT_PRICES = {
    MetalType.GOLD_24K: (
        GOLD_SPOT_EUR_PER_G,
        MetalPriceSource.MANUAL,
        datetime.utcnow(),
    ),
    MetalType.SILVER_999: (
        SILVER_SPOT_EUR_PER_G,
        MetalPriceSource.MANUAL,
        datetime.utcnow(),
    ),
    MetalType.PLATINUM_950: (
        PLATINUM_SPOT_EUR_PER_G,
        MetalPriceSource.MANUAL,
        datetime.utcnow(),
    ),
}


@pytest.fixture(autouse=True)
def mock_spot_prices(monkeypatch):
    """Patch the live metal-price lookup with fixed, deterministic rates."""

    async def _fake_get_spot_prices(db: Any = None):
        return _FIXED_SPOT_PRICES

    monkeypatch.setattr(MetalPriceService, "get_spot_prices", _fake_get_spot_prices)


# ===========================================================================
# Pure fineness math (no DB) — Feingehalt per alloy code
# ===========================================================================


class TestCalculateFineContent:
    @pytest.mark.parametrize(
        "alloy, weight_g, expected_fine_g",
        [
            (AlloyType.GOLD_585, 15.0, 8.775),
            (AlloyType.GOLD_750, 8.0, 6.0),
            (AlloyType.SILVER_925, 10.0, 9.25),
            (AlloyType.GOLD_999, 5.0, 4.995),
            (AlloyType.GOLD_333, 12.0, 3.996),
            (AlloyType.PLATINUM_950, 20.0, 19.0),
            (AlloyType.SILVER_800, 6.0, 4.8),
        ],
    )
    def test_fine_content_matches_expected_feingehalt(
        self, alloy: AlloyType, weight_g: float, expected_fine_g: float
    ) -> None:
        # Act
        fine = ScrapGoldService.calculate_fine_content(alloy, weight_g)

        # Assert
        assert fine == pytest.approx(expected_fine_g, abs=1e-9)

    def test_service_fails_loudly_for_unknown_alloy_bypassing_the_schema(self) -> None:
        """Defense in depth: even called directly with a bad code (as the
        legacy alloy-calculator query-param endpoint does before its own
        400 guard), the service must never fall back to 0.0 fine content."""
        with pytest.raises(ValueError):
            ScrapGoldService.calculate_fine_content("925", 10.0)  # type: ignore[arg-type]


# ===========================================================================
# Alloy/fineness contract — unknown or malformed alloys are rejected
# ===========================================================================


class TestUnknownAlloyRejected:
    @pytest.mark.parametrize(
        "bad_alloy",
        [
            585,  # the exact frontend bug: ScrapGoldTab.tsx sent Number(alloy)
            750.0,
            "925",  # not a key of ALLOY_RATIOS -- only "ag925" is silver 925
            "xx999",
            "",
        ],
    )
    def test_bad_alloy_rejected_with_validation_error(self, bad_alloy: Any) -> None:
        with pytest.raises(ValidationError):
            ScrapGoldItemCreate(
                description="Unbekannte Legierung", alloy=bad_alloy, weight_g=10.0
            )

    def test_known_alloy_code_is_accepted(self) -> None:
        item = ScrapGoldItemCreate(
            description="Alter Ehering", alloy="585", weight_g=15.0
        )
        assert item.alloy == AlloyType.GOLD_585


# ===========================================================================
# Per-metal valuation — the DOM-20 money bug
# ===========================================================================


@pytest.mark.asyncio
class TestRecalculateTotals:
    async def test_two_gold_items_accumulate_fine_grams(
        self, db_session, sample_customer, sample_order, admin_user
    ) -> None:
        # Arrange: a fresh Altgold record, no manual price override
        scrap_gold = await ScrapGoldService.create(
            db_session,
            admin_user.id,
            ScrapGoldCreate(
                order_id=sample_order.id,
                customer_id=sample_customer.id,
                price_source="fixed_rate",
            ),
        )

        # Act: UI adds 15 g 585 + 8 g 750
        await ScrapGoldService.add_item(
            db_session,
            scrap_gold.id,
            ScrapGoldItemCreate(
                description="Alter Ehering", alloy=AlloyType.GOLD_585, weight_g=15.0
            ),
        )
        await ScrapGoldService.add_item(
            db_session,
            scrap_gold.id,
            ScrapGoldItemCreate(
                description="Kette", alloy=AlloyType.GOLD_750, weight_g=8.0
            ),
        )

        # Assert: 15*0.585 + 8*0.75 = 8.775 + 6.0 = 14.775 g fine gold
        result = await ScrapGoldService.get_by_id(db_session, scrap_gold.id)
        assert result.total_fine_gold_g == pytest.approx(14.775)
        assert result.total_value_eur == pytest.approx(
            14.775 * GOLD_SPOT_EUR_PER_G, rel=1e-6
        )

    async def test_silver_item_is_valued_at_the_silver_price_not_gold(
        self, db_session, sample_customer, sample_order, admin_user
    ) -> None:
        # Arrange: a manual GOLD override is set, to prove it cannot leak
        # into silver valuation.
        scrap_gold = await ScrapGoldService.create(
            db_session,
            admin_user.id,
            ScrapGoldCreate(
                order_id=sample_order.id,
                customer_id=sample_customer.id,
                gold_price_per_g=70.0,
                price_source="fixed_rate",
            ),
        )

        # Act: adding 10 g Ag925
        await ScrapGoldService.add_item(
            db_session,
            scrap_gold.id,
            ScrapGoldItemCreate(
                description="Silberkette", alloy=AlloyType.SILVER_925, weight_g=10.0
            ),
        )

        # Assert: yields 9.25 g fine silver, valued at the silver price
        result = await ScrapGoldService.get_by_id(db_session, scrap_gold.id)
        assert result.total_fine_gold_g == pytest.approx(9.25)
        assert result.total_value_eur == pytest.approx(
            _eur((9.25, SILVER_SPOT_EUR_PER_G))
        )
        # The pre-fix bug: valuing everything at the gold price/override.
        assert result.total_value_eur != pytest.approx(9.25 * 70.0)
        assert result.total_value_eur != pytest.approx(9.25 * GOLD_SPOT_EUR_PER_G)

    async def test_mixed_gold_and_silver_each_valued_at_its_own_metal_price(
        self, db_session, sample_customer, sample_order, admin_user
    ) -> None:
        scrap_gold = await ScrapGoldService.create(
            db_session,
            admin_user.id,
            ScrapGoldCreate(order_id=sample_order.id, customer_id=sample_customer.id),
        )
        await ScrapGoldService.add_item(
            db_session,
            scrap_gold.id,
            ScrapGoldItemCreate(
                description="Ring", alloy=AlloyType.GOLD_585, weight_g=15.0
            ),
        )
        await ScrapGoldService.add_item(
            db_session,
            scrap_gold.id,
            ScrapGoldItemCreate(
                description="Silberkette", alloy=AlloyType.SILVER_925, weight_g=10.0
            ),
        )

        result = await ScrapGoldService.get_by_id(db_session, scrap_gold.id)
        expected_value = _eur(
            (8.775, GOLD_SPOT_EUR_PER_G), (9.25, SILVER_SPOT_EUR_PER_G)
        )
        assert result.total_value_eur == pytest.approx(expected_value)

    async def test_manual_gold_price_override_applies_only_to_gold_items(
        self, db_session, sample_customer, sample_order, admin_user
    ) -> None:
        scrap_gold = await ScrapGoldService.create(
            db_session,
            admin_user.id,
            ScrapGoldCreate(
                order_id=sample_order.id,
                customer_id=sample_customer.id,
                gold_price_per_g=70.0,
            ),
        )
        await ScrapGoldService.add_item(
            db_session,
            scrap_gold.id,
            ScrapGoldItemCreate(
                description="Ring", alloy=AlloyType.GOLD_585, weight_g=10.0
            ),
        )

        result = await ScrapGoldService.get_by_id(db_session, scrap_gold.id)
        assert result.total_fine_gold_g == pytest.approx(5.85)
        assert result.total_value_eur == pytest.approx(5.85 * 70.0, rel=1e-6)

    async def test_remove_item_recalculates_totals_to_zero(
        self, db_session, sample_customer, sample_order, admin_user
    ) -> None:
        scrap_gold = await ScrapGoldService.create(
            db_session,
            admin_user.id,
            ScrapGoldCreate(order_id=sample_order.id, customer_id=sample_customer.id),
        )
        item = await ScrapGoldService.add_item(
            db_session,
            scrap_gold.id,
            ScrapGoldItemCreate(
                description="Ring", alloy=AlloyType.GOLD_585, weight_g=10.0
            ),
        )

        removed = await ScrapGoldService.remove_item(db_session, scrap_gold.id, item.id)
        assert removed is True

        result = await ScrapGoldService.get_by_id(db_session, scrap_gold.id)
        assert result.total_fine_gold_g == 0.0
        assert result.total_value_eur == 0.0


# ===========================================================================
# HTTP round trip — the frontend/backend contract itself (DOM-19)
# ===========================================================================


@pytest.mark.asyncio
class TestAddItemHttpContract:
    async def test_numeric_alloy_from_the_old_frontend_payload_returns_422(
        self, client, admin_auth_headers, sample_customer, sample_order
    ) -> None:
        create_resp = await client.post(
            f"/api/v1/orders/{sample_order.id}/scrap-gold",
            json={
                "order_id": sample_order.id,
                "customer_id": sample_customer.id,
                "price_source": "fixed_rate",
            },
            headers=admin_auth_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        scrap_gold_id = create_resp.json()["id"]

        # This is exactly the pre-fix frontend contract: ScrapGoldTab.tsx /
        # api/scrap-gold.ts sent `alloy: Number(alloy)`.
        resp = await client.post(
            f"/api/v1/scrap-gold/{scrap_gold_id}/items",
            json={"description": "Alter Ehering", "alloy": 585, "weight_g": 15.0},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 422, resp.text

    async def test_unknown_alloy_string_returns_422(
        self, client, admin_auth_headers, sample_customer, sample_order
    ) -> None:
        create_resp = await client.post(
            f"/api/v1/orders/{sample_order.id}/scrap-gold",
            json={"order_id": sample_order.id, "customer_id": sample_customer.id},
            headers=admin_auth_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        scrap_gold_id = create_resp.json()["id"]

        resp = await client.post(
            f"/api/v1/scrap-gold/{scrap_gold_id}/items",
            json={"description": "Silberring", "alloy": "925", "weight_g": 10.0},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 422, resp.text

    async def test_valid_alloy_string_is_accepted_and_valued_correctly(
        self, client, admin_auth_headers, sample_customer, sample_order
    ) -> None:
        create_resp = await client.post(
            f"/api/v1/orders/{sample_order.id}/scrap-gold",
            json={"order_id": sample_order.id, "customer_id": sample_customer.id},
            headers=admin_auth_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        scrap_gold_id = create_resp.json()["id"]

        add_resp = await client.post(
            f"/api/v1/scrap-gold/{scrap_gold_id}/items",
            json={"description": "Silberkette", "alloy": "ag925", "weight_g": 10.0},
            headers=admin_auth_headers,
        )
        assert add_resp.status_code == 201, add_resp.text
        assert add_resp.json()["fine_content_g"] == pytest.approx(9.25)

        get_resp = await client.get(
            f"/api/v1/orders/{sample_order.id}/scrap-gold",
            headers=admin_auth_headers,
        )
        assert get_resp.status_code == 200, get_resp.text
        body = get_resp.json()
        assert body["total_fine_gold_g"] == pytest.approx(9.25)
        assert body["total_value_eur"] == pytest.approx(
            _eur((9.25, SILVER_SPOT_EUR_PER_G))
        )
