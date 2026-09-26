# src/goldsmith_erp/services/consultation_carry.py
"""
Carry consultation data onto the order (DOM-03 / DOM-09 / DOM-11b, W2-05).

The consultation wizard captures occasion date, piece type, discussed
metals and (via the customer's Massbibliothek) the ring size. Conversion
used to create an order with only title, description and customer, so the
goldsmith had to retype everything.

Mapping (consultation -> order):

- ``occasion_date`` (future dates only) -> ``deadline`` (00:00, naive UTC)
- ``piece_type`` -> ``order_type``
- first parseable ``materials_discussed[].metal`` ("585 Gelbgold",
  "750 Weißgold", "Silber 925", "gold_585", ...) -> ``alloy`` + ``metal_type``
- latest RING_SIZE measurement in mm/EU (fallback ``Customer.ring_size``)
  -> ``ring_size_mm``, only when the piece is a ring
- consultation photos -> linked to the order (``ConsultationPhoto.order_id``)

Both conversion paths use it: consultation -> order directly, and
consultation -> quote -> order (the quote has no columns for these fields,
so ``QuoteService.convert_quote`` looks the consultation up by
``Consultation.converted_quote_id``).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from typing import Any, Optional, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from goldsmith_erp.db.models import (
    Consultation,
    Customer,
    CustomerMeasurement,
    MeasurementType,
    MetalType,
    Order,
    OrderTypeEnum,
)

RING_SIZE_MIN_MM = 30.0
RING_SIZE_MAX_MM = 100.0
_RING_SIZE_UNITS = {"mm", "eu"}

_YELLOW_GOLD: dict[str, Optional[MetalType]] = {
    "999": MetalType.GOLD_24K,
    "916": MetalType.GOLD_22K,
    "900": None,  # no MetalType for 900 gold; the alloy is still carried
    "750": MetalType.GOLD_18K,
    "585": MetalType.GOLD_14K,
    "375": MetalType.GOLD_9K,
    "333": None,  # no MetalType for 333 gold; the alloy is still carried
}
_WHITE_GOLD = {"750": MetalType.WHITE_GOLD_18K, "585": MetalType.WHITE_GOLD_14K}
_ROSE_GOLD = {"750": MetalType.ROSE_GOLD_18K, "585": MetalType.ROSE_GOLD_14K}
_SILVER = {
    "999": ("Ag999", MetalType.SILVER_999),
    "925": ("Ag925", MetalType.SILVER_925),
    "800": ("Ag800", MetalType.SILVER_800),
}
_PLATINUM = {
    "950": ("Pt950", MetalType.PLATINUM_950),
    "900": ("Pt900", MetalType.PLATINUM_900),
}
_ALLOY_OF_METAL_TYPE: dict[MetalType, str] = {
    MetalType.GOLD_24K: "999",
    MetalType.GOLD_22K: "916",
    MetalType.GOLD_18K: "750",
    MetalType.GOLD_14K: "585",
    MetalType.GOLD_9K: "375",
    MetalType.WHITE_GOLD_18K: "750",
    MetalType.WHITE_GOLD_14K: "585",
    MetalType.ROSE_GOLD_18K: "750",
    MetalType.ROSE_GOLD_14K: "585",
    MetalType.SILVER_999: "Ag999",
    MetalType.SILVER_925: "Ag925",
    MetalType.SILVER_800: "Ag800",
    MetalType.PLATINUM_950: "Pt950",
    MetalType.PLATINUM_900: "Pt900",
}
_NUMBER = re.compile(r"(?<!\d)(\d{3})(?!\d)")


@dataclass(frozen=True)
class CarriedOrderFields:
    """Order fields derived from a consultation (None = nothing captured)."""

    deadline: Optional[datetime] = None
    order_type: Optional[OrderTypeEnum] = None
    alloy: Optional[str] = None
    metal_type: Optional[MetalType] = None
    ring_size_mm: Optional[float] = None

    def as_order_kwargs(self) -> dict[str, Any]:
        """Only the captured fields, ready for ``OrderCreate`` / ``Order``."""
        values = {
            "deadline": self.deadline,
            "order_type": self.order_type,
            "alloy": self.alloy,
            "metal_type": self.metal_type,
            "ring_size_mm": self.ring_size_mm,
        }
        return {k: v for k, v in values.items() if v is not None}


def _normalise(text: str) -> str:
    lowered = text.strip().lower()
    return lowered.replace("ß", "ss").replace("é", "e").replace("_", " ")


def parse_metal(text: Optional[str]) -> tuple[Optional[str], Optional[MetalType]]:
    """Map a free-text metal ("585 Gelbgold") to (alloy, MetalType).

    Returns (None, None) when the text names no known alloy. The alloy uses
    the order form's vocabulary ("585", "Ag925", "Pt950").
    """
    if not text:
        return None, None
    try:
        enum_value = MetalType(text.strip().lower())
        return _ALLOY_OF_METAL_TYPE.get(enum_value), enum_value
    except ValueError:
        pass

    norm = _normalise(text)
    match = _NUMBER.search(norm)
    fineness = match.group(1) if match else None

    if "palladium" in norm:
        return (f"Pd{fineness}" if fineness else None), MetalType.PALLADIUM
    if "platin" in norm or re.search(r"\bpt\b", norm):
        return _PLATINUM.get(fineness or "950", (None, None))
    if "silber" in norm or "silver" in norm or "sterling" in norm:
        if "sterling" in norm and fineness is None:
            fineness = "925"
        return _SILVER.get(fineness or "", (None, None))
    if fineness in _YELLOW_GOLD:
        if "weiss" in norm or "white" in norm:
            return fineness, _WHITE_GOLD.get(fineness)
        if "rot" in norm or "rose" in norm:
            return fineness, _ROSE_GOLD.get(fineness)
        return fineness, _YELLOW_GOLD[fineness]
    if fineness in _SILVER and "gold" not in norm:
        return _SILVER[fineness]
    return None, None


def _first_metal(materials: Any) -> tuple[Optional[str], Optional[MetalType]]:
    if not isinstance(materials, list):
        return None, None
    for entry in materials:
        raw = entry.get("metal") if isinstance(entry, dict) else entry
        alloy, metal_type = parse_metal(raw if isinstance(raw, str) else None)
        if alloy is not None or metal_type is not None:
            return alloy, metal_type
    return None, None


def _deadline_from(occasion_date: Optional[date]) -> Optional[datetime]:
    if occasion_date is None or occasion_date < datetime.now(timezone.utc).date():
        return None
    return datetime.combine(occasion_date, time.min, tzinfo=timezone.utc)


def _plausible_ring_size(value: Optional[float]) -> Optional[float]:
    if value is None:
        return None
    size = float(value)
    return size if RING_SIZE_MIN_MM <= size <= RING_SIZE_MAX_MM else None


async def _ring_size_for(db: AsyncSession, customer_id: int) -> Optional[float]:
    rows = (
        await db.execute(
            select(CustomerMeasurement.value, CustomerMeasurement.unit)
            .where(CustomerMeasurement.customer_id == customer_id)
            .where(CustomerMeasurement.measurement_type == MeasurementType.RING_SIZE)
            .order_by(CustomerMeasurement.measured_at.desc())
        )
    ).all()
    for value, unit in rows:
        if str(unit or "").strip().lower() in _RING_SIZE_UNITS:
            size = _plausible_ring_size(value)
            if size is not None:
                return size
    legacy = (
        await db.execute(select(Customer.ring_size).where(Customer.id == customer_id))
    ).scalar_one_or_none()
    return _plausible_ring_size(legacy)


async def fields_from_consultation(
    db: AsyncSession, consultation: Consultation
) -> CarriedOrderFields:
    """Derive the order fields a consultation captured."""
    order_type = cast(Optional[OrderTypeEnum], consultation.piece_type)
    alloy, metal_type = _first_metal(consultation.materials_discussed)
    ring_size = None
    if order_type is OrderTypeEnum.RING:
        ring_size = await _ring_size_for(db, int(consultation.customer_id))
    return CarriedOrderFields(
        deadline=_deadline_from(cast(Optional[date], consultation.occasion_date)),
        order_type=order_type,
        alloy=alloy,
        metal_type=metal_type,
        ring_size_mm=ring_size,
    )


async def consultation_for_quote(
    db: AsyncSession, quote_id: int
) -> Optional[Consultation]:
    """The consultation a quote was created from, with photos loaded."""
    return (
        await db.execute(
            select(Consultation)
            .options(selectinload(Consultation.photos))
            .where(Consultation.converted_quote_id == quote_id)
            .limit(1)
        )
    ).scalar_one_or_none()


def fill_empty_order_fields(order: Order, fields: CarriedOrderFields) -> list[str]:
    """Set captured fields the order does not have yet. Never overwrites."""
    filled = []
    for name, value in fields.as_order_kwargs().items():
        if getattr(order, name) is None:
            setattr(order, name, value)
            filled.append(name)
    return filled


def link_consultation_to_order(consultation: Consultation, order_id: int) -> None:
    """Record the order on the consultation and show its photos on the order.

    Caller holds the transaction; ``consultation.photos`` must be loaded.
    """
    # cast(Any): classic Column() declarations type these attributes as
    # Column[int] for mypy; on a loaded instance they are plain ints.
    cast(Any, consultation).converted_order_id = order_id
    for photo in consultation.photos:
        cast(Any, photo).order_id = order_id
