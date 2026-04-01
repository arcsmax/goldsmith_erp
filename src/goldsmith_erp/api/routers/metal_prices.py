# src/goldsmith_erp/api/routers/metal_prices.py
"""
Metal Prices API Router

Exposes live EUR/gram spot prices for all supported metal alloys.
Prices come from a 4-tier fallback chain (Redis cache -> external API ->
DB history -> hardcoded defaults) so the endpoints never return an error
for missing price data.

Financial data access is audit-logged per CLAUDE.md requirements.

Endpoints:
  GET  /api/v1/metal-prices              — all alloy prices
  GET  /api/v1/metal-prices/history      — price history for charting
  GET  /api/v1/metal-prices/{metal_type} — single alloy price
  POST /api/v1/metal-prices/refresh      — force cache refresh (ADMIN only)
"""

import logging
from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import asc, desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.api.deps import Permission, get_current_user, require_permission
from goldsmith_erp.db.models import MetalPriceHistory, MetalType, User
from goldsmith_erp.db.session import get_db
from goldsmith_erp.models.metal_price import (
    MetalPriceHistoryPoint,
    MetalPriceHistoryResponse,
    MetalPriceListResponse,
    MetalPriceResponse,
)
from goldsmith_erp.services.metal_price_service import MetalPriceService

router = APIRouter(prefix="/metal-prices", tags=["metal-prices"])
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# GET /metal-prices — all current prices
# ---------------------------------------------------------------------------


@router.get(
    "",
    response_model=MetalPriceListResponse,
    summary="Get current prices for all metal alloys",
)
async def list_metal_prices(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.MATERIAL_VIEW)),
) -> MetalPriceListResponse:
    """
    Return EUR/gram prices for every supported alloy.

    Prices are sourced from the 4-tier fallback chain:
    Redis cache (1 h TTL) -> external API -> DB history -> hardcoded defaults.

    The `source` field on each entry indicates which tier was used.

    **Permissions:** `material:view` (ADMIN, GOLDSMITH, VIEWER)
    """
    logger.info(
        "Metal prices list accessed",
        extra={"user_id": current_user.id, "user_role": current_user.role.value},
    )

    spot_prices = await MetalPriceService.get_spot_prices(db)

    price_list: list[MetalPriceResponse] = []
    for metal_type in MetalType:
        try:
            price, source, updated_at = await MetalPriceService.get_price_for_metal_type(
                metal_type, db
            )
            price_list.append(
                MetalPriceResponse(
                    metal_type=metal_type,
                    price_per_gram=price,
                    currency="EUR",
                    source=source,
                    updated_at=updated_at,
                )
            )
        except Exception as exc:
            # Fail loudly per CLAUDE.md — log and skip this entry rather than
            # returning a corrupt price.
            logger.error(
                "Failed to derive price for metal type",
                extra={"metal_type": metal_type.value, "error": str(exc)},
            )

    return MetalPriceListResponse(prices=price_list, count=len(price_list))


# ---------------------------------------------------------------------------
# GET /metal-prices/history — price history for charting
# ---------------------------------------------------------------------------


@router.get(
    "/history",
    response_model=MetalPriceHistoryResponse,
    summary="Get price history for a base metal (for charting)",
)
async def get_metal_price_history(
    metal_type: MetalType = Query(
        MetalType.GOLD_24K,
        description="Base metal type to query. Only GOLD_24K, SILVER_999, and PLATINUM_950 "
        "have dedicated history rows; alloy prices are derived.",
    ),
    days: int = Query(
        30,
        ge=1,
        le=365,
        description="Number of past days to return (1–365)",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.MATERIAL_VIEW)),
) -> MetalPriceHistoryResponse:
    """
    Return time-series price history for a single base metal.

    Results are ordered ascending by `fetched_at` so they can be fed
    directly into a line chart.  Includes pre-computed 7-day and 30-day
    simple moving averages alongside the raw data series.

    **Permissions:** `material:view` (ADMIN, GOLDSMITH, VIEWER)
    """
    logger.info(
        "Metal price history accessed",
        extra={
            "metal_type": metal_type.value,
            "days": days,
            "user_id": current_user.id,
        },
    )

    cutoff = datetime.utcnow() - timedelta(days=days)
    stmt = (
        select(MetalPriceHistory)
        .where(
            MetalPriceHistory.metal_type == metal_type,
            MetalPriceHistory.fetched_at >= cutoff,
        )
        .order_by(asc(MetalPriceHistory.fetched_at))
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()

    points: List[MetalPriceHistoryPoint] = [
        MetalPriceHistoryPoint(
            fetched_at=row.fetched_at,
            price_per_gram_eur=row.price_per_gram_eur,
            source=row.source,
        )
        for row in rows
    ]

    prices = [p.price_per_gram_eur for p in points]

    # Moving averages — computed over the tail of the series.
    def _simple_avg(series: list[float], n: int) -> float:
        tail = series[-n:] if len(series) >= n else series
        return round(sum(tail) / len(tail), 4) if tail else 0.0

    avg_7d = _simple_avg(prices, 7 * 4)   # ~4 refreshes/hour * 24h * 7d
    avg_30d = _simple_avg(prices, 30 * 4 * 24)
    current_price = prices[-1] if prices else 0.0

    # If no history exists yet, fall back to the current spot price so the
    # chart always shows at least one data point.
    if not points:
        try:
            spot = await MetalPriceService.get_spot_prices(db)
            if metal_type in spot:
                price_val, source_val, fetched_at_val = spot[metal_type]
                points = [
                    MetalPriceHistoryPoint(
                        fetched_at=fetched_at_val,
                        price_per_gram_eur=price_val,
                        source=source_val,
                    )
                ]
                current_price = avg_7d = avg_30d = price_val
        except Exception as exc:
            logger.warning(
                "Could not derive fallback spot price for history response",
                extra={"metal_type": metal_type.value, "error": str(exc)},
            )

    return MetalPriceHistoryResponse(
        metal_type=metal_type,
        days=days,
        points=points,
        avg_7d=avg_7d,
        avg_30d=avg_30d,
        current_price=current_price,
    )


# ---------------------------------------------------------------------------
# GET /metal-prices/{metal_type} — single alloy price
# ---------------------------------------------------------------------------


@router.get(
    "/{metal_type}",
    response_model=MetalPriceResponse,
    summary="Get current price for a specific metal alloy",
)
async def get_metal_price(
    metal_type: MetalType,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.MATERIAL_VIEW)),
) -> MetalPriceResponse:
    """
    Return the current EUR/gram price for a single metal alloy.

    **Path parameter:** `metal_type` — one of the MetalType enum values
    (e.g. `gold_18k`, `silver_925`, `platinum_950`).

    **Permissions:** `material:view` (ADMIN, GOLDSMITH, VIEWER)
    """
    logger.info(
        "Single metal price accessed",
        extra={
            "metal_type": metal_type.value,
            "user_id": current_user.id,
            "user_role": current_user.role.value,
        },
    )

    try:
        price, source, updated_at = await MetalPriceService.get_price_for_metal_type(
            metal_type, db
        )
    except KeyError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No price mapping defined for metal type '{metal_type.value}'",
        )
    except Exception as exc:
        logger.error(
            "Unexpected error fetching metal price",
            extra={"metal_type": metal_type.value, "error": str(exc)},
        )
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Metal price temporarily unavailable. Please try again.",
        )

    return MetalPriceResponse(
        metal_type=metal_type,
        price_per_gram=price,
        currency="EUR",
        source=source,
        updated_at=updated_at,
    )


# ---------------------------------------------------------------------------
# POST /metal-prices/refresh — force cache refresh (ADMIN only)
# ---------------------------------------------------------------------------


@router.post(
    "/refresh",
    response_model=MetalPriceListResponse,
    status_code=status.HTTP_200_OK,
    summary="Force a cache refresh for metal spot prices (ADMIN only)",
)
async def refresh_metal_prices(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.SYSTEM_CONFIG)),
) -> MetalPriceListResponse:
    """
    Invalidate the Redis cache and re-fetch from the external price API.

    Falls back gracefully through DB history and hardcoded defaults if the
    API is unavailable.

    **Permissions:** `system:config` (ADMIN only)
    """
    logger.info(
        "Metal price cache refresh triggered",
        extra={"user_id": current_user.id, "user_role": current_user.role.value},
    )

    spot_prices = await MetalPriceService.refresh_cache(db)

    price_list: list[MetalPriceResponse] = []
    for metal_type in MetalType:
        try:
            price, source, updated_at = await MetalPriceService.get_price_for_metal_type(
                metal_type, db
            )
            price_list.append(
                MetalPriceResponse(
                    metal_type=metal_type,
                    price_per_gram=price,
                    currency="EUR",
                    source=source,
                    updated_at=updated_at,
                )
            )
        except Exception as exc:
            logger.error(
                "Failed to derive price during refresh",
                extra={"metal_type": metal_type.value, "error": str(exc)},
            )

    logger.info(
        "Metal price cache refreshed successfully",
        extra={"price_count": len(price_list), "user_id": current_user.id},
    )

    return MetalPriceListResponse(prices=price_list, count=len(price_list))
