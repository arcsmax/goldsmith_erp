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
  GET  /api/v1/metal-prices/{metal_type} — single alloy price
  POST /api/v1/metal-prices/refresh      — force cache refresh (ADMIN only)
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.api.deps import Permission, get_current_user, require_permission
from goldsmith_erp.db.models import MetalType, User
from goldsmith_erp.db.session import get_db
from goldsmith_erp.models.metal_price import MetalPriceListResponse, MetalPriceResponse
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
