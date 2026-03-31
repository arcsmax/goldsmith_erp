# src/goldsmith_erp/services/metal_price_service.py
"""
Metal Price Service

Provides EUR/gram spot prices for gold, silver, and platinum with a
4-tier fallback chain so a price is ALWAYS available:

  1. Redis cache (TTL from settings.METAL_PRICE_CACHE_TTL, default 1 hour)
  2. External price API (httpx, URL from settings.METAL_PRICE_API_URL)
  3. Most recent row in metal_price_history table (last-known-good)
  4. Hardcoded defaults from settings (METAL_PRICE_FALLBACK_*)

Only base-metal prices (GOLD_24K, SILVER_999, PLATINUM_950) are fetched
from external sources.  All alloy prices are derived by multiplying the
fine-metal price by the alloy's fine-content ratio.

Financial data access is audit-logged at the service level per CLAUDE.md.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Dict, Optional

import httpx
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.core.cache import get_cached, invalidate
from goldsmith_erp.core.config import settings
from goldsmith_erp.db.models import MetalPriceHistory, MetalPriceSource, MetalType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------

# Redis cache key for the complete spot-price payload.
_CACHE_KEY = "metal_prices:spot"

# Alloy fine-content ratios (alloy price = base-metal spot * ratio).
# White gold and rose gold are treated as their base-karat gold equivalent
# because the colour-alloying metals (Ni, Cu, Pd) add negligible cost
# compared to the gold content at workshop scale.
_ALLOY_RATIOS: Dict[MetalType, tuple[MetalType, float]] = {
    MetalType.GOLD_24K:      (MetalType.GOLD_24K,     1.000),
    MetalType.GOLD_22K:      (MetalType.GOLD_24K,     0.9166),
    MetalType.GOLD_18K:      (MetalType.GOLD_24K,     0.750),
    MetalType.GOLD_14K:      (MetalType.GOLD_24K,     0.585),
    MetalType.GOLD_9K:       (MetalType.GOLD_24K,     0.375),
    MetalType.WHITE_GOLD_18K:(MetalType.GOLD_24K,     0.750),
    MetalType.WHITE_GOLD_14K:(MetalType.GOLD_24K,     0.585),
    MetalType.ROSE_GOLD_18K: (MetalType.GOLD_24K,     0.750),
    MetalType.ROSE_GOLD_14K: (MetalType.GOLD_24K,     0.585),
    MetalType.SILVER_999:    (MetalType.SILVER_999,   1.000),
    MetalType.SILVER_925:    (MetalType.SILVER_999,   0.925),
    MetalType.SILVER_800:    (MetalType.SILVER_999,   0.800),
    MetalType.PLATINUM_950:  (MetalType.PLATINUM_950, 0.950),
    MetalType.PLATINUM_900:  (MetalType.PLATINUM_950, 0.900),
    MetalType.PALLADIUM:     (MetalType.PLATINUM_950, 1.000),  # Palladium tracks platinum
}

# Base metals stored in metal_price_history and returned by the external API.
_BASE_METALS = (MetalType.GOLD_24K, MetalType.SILVER_999, MetalType.PLATINUM_950)


class MetalPriceService:
    """
    Service for fetching and caching metal spot prices.

    All public methods are async and accept an optional AsyncSession.
    The session is only required when the DB fallback is needed.
    """

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    @staticmethod
    async def get_spot_prices(
        db: Optional[AsyncSession] = None,
    ) -> Dict[MetalType, tuple[float, MetalPriceSource, datetime]]:
        """
        Return current spot prices for the three base metals.

        Returns a dict mapping MetalType -> (price_per_gram_eur, source, updated_at).

        The 4-tier fallback chain is executed transparently; callers always
        receive a value.  They can inspect `source` to determine freshness.

        Args:
            db: AsyncSession required only for the DB-history fallback tier.
                If None and cache+API both fail, hardcoded defaults are used.
        """
        async def _fetch_prices() -> str:
            """
            Attempt to fetch from the external API and persist to DB history.
            Returns a JSON-serialised spot-price dict for the cache layer.
            Raises on failure so the cache module falls through to fetch_fn.
            """
            if not settings.METAL_PRICE_API_URL:
                raise ValueError("METAL_PRICE_API_URL not configured")

            prices = await MetalPriceService._fetch_from_api()
            # Persist to DB for future last-known-price fallback
            if db is not None:
                await MetalPriceService._persist_prices(db, prices, MetalPriceSource.API)
            return MetalPriceService._serialise_prices(prices)

        try:
            raw = await get_cached(
                key=_CACHE_KEY,
                ttl=settings.METAL_PRICE_CACHE_TTL,
                fetch_fn=_fetch_prices,
                serialise=lambda x: x,   # fetch_fn already returns a JSON str
                deserialise=lambda x: x,
            )
            prices_dict = MetalPriceService._deserialise_prices(raw)
            return prices_dict

        except Exception as exc:
            logger.warning(
                "Metal price cache+API tier failed, trying DB history",
                extra={"error": str(exc)},
            )

        # Tier 3: DB last-known price
        if db is not None:
            try:
                db_prices = await MetalPriceService._fetch_from_db(db)
                if db_prices:
                    logger.info("Metal prices sourced from DB history fallback")
                    return db_prices
            except Exception as exc:
                logger.warning(
                    "DB history fallback failed, using hardcoded defaults",
                    extra={"error": str(exc)},
                )

        # Tier 4: hardcoded defaults
        logger.warning("All metal price sources failed — using hardcoded defaults")
        return MetalPriceService._hardcoded_defaults()

    @staticmethod
    async def get_price_for_metal_type(
        metal_type: MetalType,
        db: Optional[AsyncSession] = None,
    ) -> tuple[float, MetalPriceSource, datetime]:
        """
        Return the EUR/gram price for any MetalType alloy.

        Derives alloy prices from spot prices using the fine-content ratios
        defined in _ALLOY_RATIOS.

        Args:
            metal_type: The target alloy.
            db: Forwarded to get_spot_prices for DB fallback.

        Returns:
            (price_per_gram_eur, source, updated_at)
        """
        spot_prices = await MetalPriceService.get_spot_prices(db)
        base_metal, ratio = _ALLOY_RATIOS[metal_type]

        if base_metal not in spot_prices:
            # Should never happen but fail loudly rather than silently
            raise RuntimeError(
                f"Base metal {base_metal.value} missing from spot prices dict. "
                "This is a bug in _ALLOY_RATIOS mapping."
            )

        spot_price, source, updated_at = spot_prices[base_metal]
        alloy_price = round(spot_price * ratio, 4)

        logger.debug(
            "Derived alloy price",
            extra={
                "metal_type": metal_type.value,
                "base_metal": base_metal.value,
                "ratio": ratio,
                "spot_price": spot_price,
                "alloy_price": alloy_price,
                "source": source.value,
            },
        )
        return alloy_price, source, updated_at

    @staticmethod
    async def refresh_cache(db: Optional[AsyncSession] = None) -> Dict[MetalType, tuple[float, MetalPriceSource, datetime]]:
        """
        Force-invalidate the Redis cache and re-fetch from the API.

        Used by the POST /metal-prices/refresh ADMIN endpoint.
        Falls back gracefully if the API is unavailable.
        """
        await invalidate(_CACHE_KEY)
        logger.info("Metal price cache invalidated by admin refresh")
        return await MetalPriceService.get_spot_prices(db)

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    @staticmethod
    async def _fetch_from_api() -> Dict[MetalType, tuple[float, MetalPriceSource, datetime]]:
        """
        Fetch spot prices from the configured external API.

        The service supports the frankfurter.app / Open Exchange Rates style
        response format.  If the API returns XAU/XAG/XPT commodity codes
        against USD, the service converts to EUR/gram using the ratios:
          - 1 troy ounce = 31.1035 g
          - USD/EUR rate is fetched from the same API when available

        For services that already return EUR/gram directly the response
        should be a flat JSON object:
          {"gold_eur_per_gram": 75.50, "silver_eur_per_gram": 0.88, "platinum_eur_per_gram": 30.20}

        If METAL_PRICE_API_URL is not set or returns an unexpected format,
        this method raises so the fallback chain takes over.
        """
        now = datetime.utcnow()

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(str(settings.METAL_PRICE_API_URL))
            response.raise_for_status()
            data = response.json()

        prices: Dict[MetalType, tuple[float, MetalPriceSource, datetime]] = {}

        # -- Try the Goldprice.org / direct EUR/gram format first --
        if "gold_eur_per_gram" in data:
            prices[MetalType.GOLD_24K] = (float(data["gold_eur_per_gram"]), MetalPriceSource.API, now)
            prices[MetalType.SILVER_999] = (float(data["silver_eur_per_gram"]), MetalPriceSource.API, now)
            prices[MetalType.PLATINUM_950] = (float(data["platinum_eur_per_gram"]), MetalPriceSource.API, now)
            return prices

        # -- Try the Open Exchange Rates / XAU format (troy oz in base currency) --
        # Example: {"rates": {"XAU": 0.000524, "XAG": 0.033, "XPT": 0.00083}, "base": "USD"}
        if "rates" in data:
            base_currency = data.get("base", "USD")
            rates = data["rates"]

            # Convert XAU (troy oz) to EUR/gram
            # XAU rate against USD: 1 USD = XAU oz  => 1 oz = 1/XAU USD
            troy_oz_g = 31.1035

            # Get USD/EUR conversion
            eur_rate = rates.get("EUR", 1.0) if base_currency == "USD" else 1.0

            if "XAU" in rates and rates["XAU"] > 0:
                price_usd_per_oz = 1.0 / rates["XAU"]
                price_usd_per_g = price_usd_per_oz / troy_oz_g
                price_eur_per_g = price_usd_per_g * eur_rate
                prices[MetalType.GOLD_24K] = (round(price_eur_per_g, 4), MetalPriceSource.API, now)

            if "XAG" in rates and rates["XAG"] > 0:
                price_usd_per_oz = 1.0 / rates["XAG"]
                price_usd_per_g = price_usd_per_oz / troy_oz_g
                price_eur_per_g = price_usd_per_g * eur_rate
                prices[MetalType.SILVER_999] = (round(price_eur_per_g, 4), MetalPriceSource.API, now)

            if "XPT" in rates and rates["XPT"] > 0:
                price_usd_per_oz = 1.0 / rates["XPT"]
                price_usd_per_g = price_usd_per_oz / troy_oz_g
                price_eur_per_g = price_usd_per_g * eur_rate
                prices[MetalType.PLATINUM_950] = (round(price_eur_per_g, 4), MetalPriceSource.API, now)

            if prices:
                return prices

        raise ValueError(
            f"Unrecognised API response format from {settings.METAL_PRICE_API_URL}. "
            "Expected keys: gold_eur_per_gram / silver_eur_per_gram / platinum_eur_per_gram "
            "or rates.XAU / rates.XAG / rates.XPT"
        )

    @staticmethod
    async def _fetch_from_db(
        db: AsyncSession,
    ) -> Optional[Dict[MetalType, tuple[float, MetalPriceSource, datetime]]]:
        """
        Query metal_price_history for the most recent price per base metal.

        Returns None if the table has no rows.
        """
        prices: Dict[MetalType, tuple[float, MetalPriceSource, datetime]] = {}

        for metal in _BASE_METALS:
            result = await db.execute(
                select(MetalPriceHistory)
                .where(MetalPriceHistory.metal_type == metal)
                .order_by(desc(MetalPriceHistory.fetched_at))
                .limit(1)
            )
            row = result.scalar_one_or_none()
            if row is not None:
                prices[metal] = (row.price_per_gram_eur, row.source, row.fetched_at)

        return prices if len(prices) == len(_BASE_METALS) else None

    @staticmethod
    def _hardcoded_defaults() -> Dict[MetalType, tuple[float, MetalPriceSource, datetime]]:
        """Return hardcoded fallback prices from settings."""
        now = datetime.utcnow()
        return {
            MetalType.GOLD_24K: (
                settings.METAL_PRICE_FALLBACK_GOLD,
                MetalPriceSource.FALLBACK,
                now,
            ),
            MetalType.SILVER_999: (
                settings.METAL_PRICE_FALLBACK_SILVER,
                MetalPriceSource.FALLBACK,
                now,
            ),
            MetalType.PLATINUM_950: (
                settings.METAL_PRICE_FALLBACK_PLATINUM,
                MetalPriceSource.FALLBACK,
                now,
            ),
        }

    @staticmethod
    async def _persist_prices(
        db: AsyncSession,
        prices: Dict[MetalType, tuple[float, MetalPriceSource, datetime]],
        source: MetalPriceSource,
    ) -> None:
        """
        Write base-metal prices to metal_price_history for the DB fallback tier.

        Called after a successful API fetch so the table stays current.
        Uses a standalone flush (no explicit transaction wrapper) because
        this is a fire-and-log operation — failure must never block the
        price response.
        """
        try:
            for metal_type, (price, _, fetched_at) in prices.items():
                if metal_type not in _BASE_METALS:
                    continue
                row = MetalPriceHistory(
                    metal_type=metal_type,
                    price_per_gram_eur=price,
                    source=source,
                    fetched_at=fetched_at,
                )
                db.add(row)
            await db.flush()
            logger.debug("Metal price history persisted", extra={"count": len(prices)})
        except Exception as exc:
            logger.warning(
                "Failed to persist metal prices to DB history",
                extra={"error": str(exc)},
            )
            await db.rollback()

    # -------------------------------------------------------------------------
    # Serialisation helpers for the Redis cache layer
    # -------------------------------------------------------------------------

    @staticmethod
    def _serialise_prices(
        prices: Dict[MetalType, tuple[float, MetalPriceSource, datetime]],
    ) -> str:
        """Convert a price dict to a JSON string for Redis storage."""
        payload: dict = {}
        for metal_type, (price, source, updated_at) in prices.items():
            payload[metal_type.value] = {
                "price": price,
                "source": source.value,
                "updated_at": updated_at.isoformat(),
            }
        return json.dumps(payload)

    @staticmethod
    def _deserialise_prices(
        raw: str,
    ) -> Dict[MetalType, tuple[float, MetalPriceSource, datetime]]:
        """Restore a price dict from the JSON string stored in Redis."""
        payload = json.loads(raw)
        prices: Dict[MetalType, tuple[float, MetalPriceSource, datetime]] = {}
        for metal_value, entry in payload.items():
            prices[MetalType(metal_value)] = (
                float(entry["price"]),
                MetalPriceSource(entry["source"]),
                datetime.fromisoformat(entry["updated_at"]),
            )
        return prices
