"""Unit tests for the consultation -> order field mapping (DOM-03, W2-05)."""

from datetime import date, datetime, timedelta, timezone

import pytest

from goldsmith_erp.db.models import MetalType, Order, OrderTypeEnum
from goldsmith_erp.services.consultation_carry import (
    CarriedOrderFields,
    _deadline_from,
    fill_empty_order_fields,
    parse_metal,
)


@pytest.mark.parametrize(
    ("text", "alloy", "metal_type"),
    [
        ("585 Gelbgold", "585", MetalType.GOLD_14K),
        ("750 Weißgold", "750", MetalType.WHITE_GOLD_18K),
        ("Rotgold 585", "585", MetalType.ROSE_GOLD_14K),
        ("gold_585", "585", MetalType.GOLD_14K),
        ("white_gold_18k", "750", MetalType.WHITE_GOLD_18K),
        ("Silber 925", "Ag925", MetalType.SILVER_925),
        ("Sterling", "Ag925", MetalType.SILVER_925),
        ("Platin 950", "Pt950", MetalType.PLATINUM_950),
        ("333 Gold", "333", None),
        ("Titan", None, None),
        ("", None, None),
        (None, None, None),
    ],
)
def test_parse_metal(text, alloy, metal_type) -> None:
    assert parse_metal(text) == (alloy, metal_type)


def test_deadline_only_from_future_dates() -> None:
    future = datetime.utcnow().date() + timedelta(days=30)
    assert _deadline_from(future) == datetime.combine(
        future, datetime.min.time(), tzinfo=timezone.utc
    )
    assert _deadline_from(datetime.utcnow().date() - timedelta(days=1)) is None
    assert _deadline_from(None) is None


def test_fill_empty_order_fields_never_overwrites() -> None:
    order = Order(alloy="750", order_type=None, ring_size_mm=None)
    fields = CarriedOrderFields(
        alloy="585", order_type=OrderTypeEnum.RING, ring_size_mm=54.0
    )

    filled = fill_empty_order_fields(order, fields)

    assert order.alloy == "750"
    assert order.order_type == OrderTypeEnum.RING
    assert order.ring_size_mm == 54.0
    assert sorted(filled) == ["order_type", "ring_size_mm"]


def test_as_order_kwargs_skips_missing_values() -> None:
    assert CarriedOrderFields(alloy="585").as_order_kwargs() == {"alloy": "585"}
