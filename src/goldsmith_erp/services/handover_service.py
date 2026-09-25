"""Abholprotokoll (handover report) data for a finished order (W2-11, DOM-35).

Collects what the customer takes home on paper: the newest order photo
(EXIF-stripped email variant, design IP: the endpoint needs DESIGN_VIEW),
metal/alloy/weight, the stones (description only, never their cost), the
materials, care advice by metal and stone, the warranty note and the
signature lines. Rendering lives in ``services/pdf_reports.py``.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.core.config import settings
from goldsmith_erp.db.models import OrderPhoto, OrderStatusEnum
from goldsmith_erp.models.gemstone import describe_gemstone
from goldsmith_erp.services.image_validation import (
    PhotoValidationError,
    create_email_variant,
    resolve_within_root,
)
from goldsmith_erp.services.pdf_reports import HandoverData

logger = logging.getLogger(__name__)

#: Orders that can be handed over (finished or already picked up).
HANDOVER_STATUSES = frozenset({OrderStatusEnum.COMPLETED, OrderStatusEnum.DELIVERED})

_METAL_LABELS = {
    "gold_24k": "Feingold",
    "gold_22k": "Gelbgold",
    "gold_18k": "Gelbgold",
    "gold_14k": "Gelbgold",
    "gold_9k": "Gelbgold",
    "white_gold_18k": "Weißgold",
    "white_gold_14k": "Weißgold",
    "rose_gold_18k": "Roségold",
    "rose_gold_14k": "Roségold",
    "silver_999": "Feinsilber",
    "silver_925": "Silber",
    "silver_800": "Silber",
    "platinum_950": "Platin",
    "platinum_900": "Platin",
    "palladium": "Palladium",
}


def _enum_value(value: Any) -> Optional[str]:
    if value is None:
        return None
    return str(getattr(value, "value", value))


def can_hand_over(order: Any) -> bool:
    status = order.status
    if not isinstance(status, OrderStatusEnum):
        status = OrderStatusEnum(str(status))
    return status in HANDOVER_STATUSES


async def _newest_photo(db: AsyncSession, order_id: int) -> List[bytes]:
    result = await db.execute(
        select(OrderPhoto)
        .where(OrderPhoto.order_id == order_id)
        .order_by(OrderPhoto.timestamp.desc())
        .limit(1)
    )
    photo = result.scalar_one_or_none()
    if photo is None:
        return []
    root = Path(settings.PHOTO_STORAGE_PATH).resolve()
    resolved = resolve_within_root(cast(str, photo.file_path), root)
    if resolved is None or not resolved.is_file():
        logger.warning(
            "Handover photo path invalid or missing",
            extra={"photo_id": photo.id, "order_id": order_id},
        )
        return []
    try:
        return [await asyncio.to_thread(create_email_variant, resolved)]
    except (PhotoValidationError, OSError):
        logger.warning(
            "Handover photo could not be prepared",
            extra={"photo_id": photo.id, "order_id": order_id},
            exc_info=True,
        )
        return []


def _customer_name(customer: Any) -> str:
    if customer is None:
        return ""
    parts = (customer.first_name, customer.last_name)
    return " ".join(p for p in parts if p)


async def build_handover_data(
    db: AsyncSession, order: Any, *, now: Optional[datetime] = None
) -> HandoverData:
    """HandoverData for an order loaded with customer, materials, gemstones."""
    metal_type = _enum_value(order.metal_type)
    stones = list(order.gemstones or [])
    return HandoverData(
        order_id=int(order.id),
        title=order.title or f"Auftrag #{order.id}",
        customer_name=_customer_name(order.customer),
        handed_over_at=now or datetime.now(timezone.utc),
        metal_label=_METAL_LABELS.get(metal_type or ""),
        alloy=order.alloy,
        weight_g=order.actual_weight_g or order.estimated_weight_g,
        ring_size_mm=order.ring_size_mm,
        surface_finish=order.surface_finish,
        gemstone_lines=[describe_gemstone(stone) for stone in stones],
        materials=[m.name for m in (order.materials or []) if m.name],
        metal_type=metal_type,
        stone_types=[stone.type for stone in stones if stone.type],
        photos=await _newest_photo(db, int(order.id)),
    )
