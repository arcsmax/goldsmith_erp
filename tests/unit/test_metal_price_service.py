"""Unit tests for MetalPriceService's external-API fetch (W2-15 / BE-22).

The previous implementation silently treated a missing EUR conversion rate
as 1.0 (i.e. "1 USD == 1 EUR"), which mispriced gold ~8% high without any
signal to the operator. It also assigned the raw XPT (pure platinum) price
straight through with no indication that the fine-content ratio still needs
to be applied by the caller, and used a hardcoded 10s httpx timeout that
wasn't configurable.

These tests exercise ``MetalPriceService._fetch_from_api`` directly (the
tier-2 fetch step) with a faked ``httpx.AsyncClient`` so no network or Redis
is required. Per CLAUDE.md ("fail loudly"), a missing/invalid EUR rate or a
timeout must raise a typed error — never a silently wrong price — so the
4-tier fallback chain (DB history, then hardcoded defaults) takes over.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx
import pytest

from goldsmith_erp.core.config import settings
from goldsmith_erp.db.models import MetalPriceSource, MetalType
from goldsmith_erp.services.metal_inventory_service import resolve_alloy_to_metal_type
from goldsmith_erp.services.metal_price_service import (
    MetalPriceCurrencyError,
    MetalPriceError,
    MetalPriceService,
    MetalPriceTimeoutError,
)


class _FakeResponse:
    """Minimal stand-in for httpx.Response."""

    def __init__(self, json_data: dict) -> None:
        self._json_data = json_data

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._json_data


class _FakeAsyncClient:
    """Minimal stand-in for httpx.AsyncClient as an async context manager."""

    def __init__(
        self,
        *,
        json_data: Optional[dict] = None,
        raise_exc: Optional[Exception] = None,
        **_kwargs: Any,
    ) -> None:
        self._json_data = json_data
        self._raise_exc = raise_exc

    async def __aenter__(self) -> "_FakeAsyncClient":
        return self

    async def __aexit__(self, *_exc_info: Any) -> bool:
        return False

    async def get(self, _url: str) -> _FakeResponse:
        if self._raise_exc is not None:
            raise self._raise_exc
        assert self._json_data is not None
        return _FakeResponse(self._json_data)


def _install_fake_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    json_data: Optional[dict] = None,
    raise_exc: Optional[Exception] = None,
) -> None:
    """Patch httpx.AsyncClient (as imported into metal_price_service) with a
    fake that returns `json_data` from .get(), or raises `raise_exc`."""

    def _factory(*_args: Any, **_kwargs: Any) -> _FakeAsyncClient:
        return _FakeAsyncClient(json_data=json_data, raise_exc=raise_exc)

    monkeypatch.setattr(
        "goldsmith_erp.services.metal_price_service.httpx.AsyncClient", _factory
    )
    monkeypatch.setattr(settings, "METAL_PRICE_API_URL", "https://fake.example/prices")


@pytest.mark.asyncio
class TestFetchFromApiEurHandling:
    """The XAU/XAG/XPT (Open Exchange Rates style) branch must never treat
    a non-EUR base currency as EUR when no explicit EUR rate is present."""

    async def test_missing_eur_rate_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """base=USD with no 'EUR' key in rates must raise, not default to 1.0."""
        _install_fake_client(
            monkeypatch,
            json_data={
                "base": "USD",
                "rates": {"XAU": 0.000524, "XAG": 0.033, "XPT": 0.00083},
            },
        )

        with pytest.raises(MetalPriceCurrencyError):
            await MetalPriceService._fetch_from_api()

    async def test_usd_only_response_is_not_silently_converted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Regression guard for the specific BE-22 bug: USD-denominated
        rates with no EUR key must never be returned as if they were EUR
        prices (eur_rate defaulting to 1.0)."""
        _install_fake_client(
            monkeypatch,
            json_data={"base": "USD", "rates": {"XAU": 0.0005}},
        )

        with pytest.raises(MetalPriceError):
            await MetalPriceService._fetch_from_api()

    async def test_zero_eur_rate_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """An explicit but non-positive EUR rate is just as dangerous as a
        missing one (division-by-zero-adjacent nonsense price) and must
        raise rather than be used."""
        _install_fake_client(
            monkeypatch,
            json_data={
                "base": "USD",
                "rates": {"XAU": 0.000524, "EUR": 0.0},
            },
        )

        with pytest.raises(MetalPriceCurrencyError):
            await MetalPriceService._fetch_from_api()

    async def test_eur_base_currency_needs_no_conversion(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """base=EUR (no separate EUR rate needed) must still work."""
        _install_fake_client(
            monkeypatch,
            json_data={
                "base": "EUR",
                "rates": {"XAU": 0.00048, "XAG": 0.030, "XPT": 0.00076},
            },
        )

        prices = await MetalPriceService._fetch_from_api()

        assert MetalType.GOLD_24K in prices
        price, source, _updated_at = prices[MetalType.GOLD_24K]
        assert price > 0
        assert source == MetalPriceSource.API

    async def test_valid_usd_response_with_eur_rate_stores_converted_price(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The happy path: base=USD with an explicit EUR rate converts
        correctly and stamps a timestamp on every returned entry."""
        before = datetime.now(timezone.utc)
        _install_fake_client(
            monkeypatch,
            json_data={
                "base": "USD",
                "rates": {
                    "XAU": 0.000524,
                    "XAG": 0.033,
                    "XPT": 0.00083,
                    "EUR": 0.92,
                },
            },
        )

        prices = await MetalPriceService._fetch_from_api()
        after = datetime.now(timezone.utc)

        assert set(prices) == {
            MetalType.GOLD_24K,
            MetalType.SILVER_999,
            MetalType.PLATINUM_950,
        }
        for metal_type, (price, source, updated_at) in prices.items():
            assert price > 0, f"{metal_type} priced at/below zero"
            assert source == MetalPriceSource.API
            assert before <= updated_at <= after

        # Manually derive the expected GOLD_24K EUR/g price to confirm the
        # USD->EUR conversion (eur_rate) was actually applied, not skipped.
        troy_oz_g = 31.1035
        expected_gold_usd_per_g = (1.0 / 0.000524) / troy_oz_g
        expected_gold_eur_per_g = round(expected_gold_usd_per_g * 0.92, 4)
        gold_price, _source, _ts = prices[MetalType.GOLD_24K]
        assert gold_price == pytest.approx(expected_gold_eur_per_g, rel=1e-6)

    async def test_direct_eur_per_gram_format_still_works(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The simpler direct 'gold_eur_per_gram' style API response
        (already denominated in EUR) is unaffected by the EUR-rate fix."""
        _install_fake_client(
            monkeypatch,
            json_data={
                "gold_eur_per_gram": 75.5,
                "silver_eur_per_gram": 0.88,
                "platinum_eur_per_gram": 30.2,
            },
        )

        prices = await MetalPriceService._fetch_from_api()

        assert prices[MetalType.GOLD_24K][0] == 75.5
        assert prices[MetalType.SILVER_999][0] == 0.88
        assert prices[MetalType.PLATINUM_950][0] == 30.2


@pytest.mark.asyncio
class TestFetchFromApiTimeout:
    async def test_timeout_raises_typed_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _install_fake_client(
            monkeypatch,
            raise_exc=httpx.TimeoutException("simulated timeout"),
        )

        with pytest.raises(MetalPriceTimeoutError):
            await MetalPriceService._fetch_from_api()

    async def test_timeout_uses_configured_setting(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The httpx client must be built with settings.METAL_PRICE_HTTP_TIMEOUT_SECONDS
        rather than a hardcoded value, so operators can tune it."""
        seen_kwargs: dict = {}

        class _CapturingFakeClient(_FakeAsyncClient):
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                seen_kwargs.update(kwargs)
                super().__init__(
                    json_data={
                        "gold_eur_per_gram": 75.0,
                        "silver_eur_per_gram": 0.9,
                        "platinum_eur_per_gram": 30.0,
                    }
                )

        monkeypatch.setattr(
            "goldsmith_erp.services.metal_price_service.httpx.AsyncClient",
            _CapturingFakeClient,
        )
        monkeypatch.setattr(
            settings, "METAL_PRICE_API_URL", "https://fake.example/prices"
        )
        monkeypatch.setattr(settings, "METAL_PRICE_HTTP_TIMEOUT_SECONDS", 3.5)

        await MetalPriceService._fetch_from_api()

        assert seen_kwargs.get("timeout") == 3.5


@pytest.mark.asyncio
class TestPlatinumFineness:
    """Locks in that get_price_for_metal_type still applies the Pt950
    fine-content ratio (0.95) on top of the base spot price — i.e. Pt950 is
    never billed at the pure-platinum (999.5) rate."""

    async def test_platinum_950_alloy_price_applies_fineness_ratio(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        pure_platinum_spot = 30.0
        now = datetime.now(timezone.utc)

        async def _fake_get_spot_prices(db: Any = None) -> dict:
            return {
                MetalType.GOLD_24K: (75.0, MetalPriceSource.API, now),
                MetalType.SILVER_999: (0.9, MetalPriceSource.API, now),
                MetalType.PLATINUM_950: (
                    pure_platinum_spot,
                    MetalPriceSource.API,
                    now,
                ),
            }

        monkeypatch.setattr(MetalPriceService, "get_spot_prices", _fake_get_spot_prices)

        price, _source, _updated_at = await MetalPriceService.get_price_for_metal_type(
            MetalType.PLATINUM_950
        )

        assert price == pytest.approx(pure_platinum_spot * 0.95, rel=1e-9)
        assert price < pure_platinum_spot, (
            "Pt950 must be cheaper than the pure (999.5) platinum spot price "
            "it is derived from"
        )


@pytest.mark.asyncio
class TestPersistPricesNeverStoresNonPositive:
    async def test_zero_or_negative_price_is_not_persisted(self) -> None:
        """Defence in depth: even if a bad price ever reaches the persist
        step, it must never be written to metal_price_history as if it
        were a real EUR value."""
        from unittest.mock import AsyncMock, MagicMock

        db = MagicMock()
        db.add = MagicMock()
        db.flush = AsyncMock()

        now = datetime.now(timezone.utc)
        prices = {
            MetalType.GOLD_24K: (75.0, MetalPriceSource.API, now),
            MetalType.SILVER_999: (0.0, MetalPriceSource.API, now),
            MetalType.PLATINUM_950: (-1.0, MetalPriceSource.API, now),
        }

        await MetalPriceService._persist_prices(db, prices, MetalPriceSource.API)

        persisted_metal_types = [
            call.args[0].metal_type for call in db.add.call_args_list
        ]
        assert persisted_metal_types == [MetalType.GOLD_24K]


class TestStalenessSetting:
    def test_staleness_threshold_is_configurable(self) -> None:
        assert settings.METAL_PRICE_STALENESS_HOURS > 0

    def test_http_timeout_is_configurable(self) -> None:
        assert settings.METAL_PRICE_HTTP_TIMEOUT_SECONDS > 0


class TestResolveAlloyToMetalType:
    """Covers the alloy-string -> MetalType resolver that backs
    GET /metal-prices/by-alloy/{alloy}, used by the EstimatorPanel to show
    a live price for whatever alloy the order/quote actually specifies."""

    @pytest.mark.parametrize(
        "alloy,expected",
        [
            ("750", MetalType.GOLD_18K),
            ("585", MetalType.GOLD_14K),
            ("999", MetalType.GOLD_24K),
            ("Pt950", MetalType.PLATINUM_950),
            ("pt950", MetalType.PLATINUM_950),
            ("Ag925", MetalType.SILVER_925),
            ("Ag800", MetalType.SILVER_800),
            ("  750  ", MetalType.GOLD_18K),
        ],
    )
    def test_known_alloy_resolves(self, alloy: str, expected: MetalType) -> None:
        assert resolve_alloy_to_metal_type(alloy) == expected

    @pytest.mark.parametrize("alloy", ["333", "900", "", "unknown-alloy"])
    def test_unknown_alloy_returns_none_not_a_guess(self, alloy: str) -> None:
        assert resolve_alloy_to_metal_type(alloy) is None

    def test_none_alloy_returns_none(self) -> None:
        assert resolve_alloy_to_metal_type(None) is None  # type: ignore[arg-type]
