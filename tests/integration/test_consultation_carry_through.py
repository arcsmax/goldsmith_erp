# tests/integration/test_consultation_carry_through.py
"""
DOM-03 / DOM-11b / DOM-09 (W2-05): what the consultation captured reaches
the order without retyping.

Domain DoD: "Converting a consultation with occasion date, ring size and
'585 Gelbgold' yields a quote and then an order with deadline, ring size,
alloy, order type and photos, no retyping."

Two paths are covered:
- consultation -> quote -> approve -> convert -> order
- consultation -> order (direct)
"""

from datetime import date, datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import (
    Consultation,
    ConsultationPhoto,
    ConsultationPhotoKind,
    Customer,
    CustomerMeasurement,
    FingerPosition,
    HandSide,
    MeasurementType,
    MetalType,
    Order,
    OrderTypeEnum,
    User,
)

pytestmark = pytest.mark.asyncio

CONSULTATIONS_URL = "/api/v1/consultations/"
QUOTES_URL = "/api/v1/quotes/"
OCCASION_DATE = date(2027, 5, 14)
RING_SIZE_MM = 54.5


async def _consultation_with_fields(
    client: AsyncClient,
    db: AsyncSession,
    headers: dict,
    customer: Customer,
    goldsmith: User,
) -> int:
    resp = await client.post(
        CONSULTATIONS_URL,
        json={
            "customer_id": customer.id,
            "occasion": "engagement",
            "occasion_date": OCCASION_DATE.isoformat(),
            "piece_type": "ring",
            "materials_discussed": [{"metal": "585 Gelbgold"}],
            "wishes": "Verlobungsring, schlicht",
            "budget_min": 1200,
            "budget_max": 1500,
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    consultation_id = int(resp.json()["id"])

    db.add(
        CustomerMeasurement(
            customer_id=customer.id,
            measured_by=goldsmith.id,
            measurement_type=MeasurementType.RING_SIZE,
            value=RING_SIZE_MM,
            unit="mm",
            hand=HandSide.LEFT,
            finger=FingerPosition.RING,
            measured_at=datetime(2026, 9, 1, 10, 0),
        )
    )
    db.add(
        ConsultationPhoto(
            consultation_id=consultation_id,
            kind=ConsultationPhotoKind.SKETCH,
            file_path="consultations/test/sketch.jpg",
            taken_by=goldsmith.id,
        )
    )
    await db.commit()
    return consultation_id


async def _load_order(db: AsyncSession, order_id: int) -> Order:
    db.expire_all()
    return (await db.execute(select(Order).where(Order.id == order_id))).scalar_one()


async def _assert_carried(db: AsyncSession, order: Order, consultation_id: int) -> None:
    assert order.deadline is not None
    assert order.deadline.date() == OCCASION_DATE
    assert order.ring_size_mm == pytest.approx(RING_SIZE_MM)
    assert order.alloy == "585"
    assert order.metal_type == MetalType.GOLD_14K
    assert order.order_type == OrderTypeEnum.RING

    photos = (
        (
            await db.execute(
                select(ConsultationPhoto).where(
                    ConsultationPhoto.consultation_id == consultation_id
                )
            )
        )
        .scalars()
        .all()
    )
    assert photos and all(p.order_id == order.id for p in photos)

    consultation = (
        await db.execute(select(Consultation).where(Consultation.id == consultation_id))
    ).scalar_one()
    assert consultation.converted_order_id == order.id


async def test_consultation_to_quote_to_order_carries_fields(
    client: AsyncClient,
    db_session: AsyncSession,
    goldsmith_auth_headers: dict,
    goldsmith_user: User,
    test_customer: Customer,
) -> None:
    cid = await _consultation_with_fields(
        client, db_session, goldsmith_auth_headers, test_customer, goldsmith_user
    )

    converted = await client.post(
        f"{CONSULTATIONS_URL}{cid}/convert",
        json={"target": "quote"},
        headers=goldsmith_auth_headers,
    )
    assert converted.status_code == 200, converted.text
    quote_id = converted.json()["converted_quote_id"]
    assert quote_id is not None

    approved = await client.post(
        f"{QUOTES_URL}{quote_id}/approve",
        json={"response_method": "in_person"},
        headers=goldsmith_auth_headers,
    )
    assert approved.status_code == 200, approved.text

    to_order = await client.post(
        f"{QUOTES_URL}{quote_id}/convert", headers=goldsmith_auth_headers
    )
    assert to_order.status_code == 200, to_order.text
    order_id = to_order.json()["order_id"]
    assert order_id is not None

    order = await _load_order(db_session, order_id)
    await _assert_carried(db_session, order, cid)
    # Quote lines reach the order: its agreed NET price is the quote subtotal.
    assert order.price == pytest.approx(1200.0)
    assert "Verlobungsring" in (order.description or "")


async def test_consultation_to_order_directly_carries_fields(
    client: AsyncClient,
    db_session: AsyncSession,
    goldsmith_auth_headers: dict,
    goldsmith_user: User,
    test_customer: Customer,
) -> None:
    cid = await _consultation_with_fields(
        client, db_session, goldsmith_auth_headers, test_customer, goldsmith_user
    )

    converted = await client.post(
        f"{CONSULTATIONS_URL}{cid}/convert",
        json={"target": "order"},
        headers=goldsmith_auth_headers,
    )
    assert converted.status_code == 200, converted.text
    order_id = converted.json()["converted_order_id"]

    order = await _load_order(db_session, order_id)
    await _assert_carried(db_session, order, cid)


async def test_non_ring_piece_gets_no_ring_size(
    client: AsyncClient,
    db_session: AsyncSession,
    goldsmith_auth_headers: dict,
    goldsmith_user: User,
    test_customer: Customer,
) -> None:
    """A pendant must not inherit the customer's ring size."""
    cid = await _consultation_with_fields(
        client, db_session, goldsmith_auth_headers, test_customer, goldsmith_user
    )
    patched = await client.patch(
        f"{CONSULTATIONS_URL}{cid}",
        json={
            "piece_type": "pendant",
            "materials_discussed": [{"metal": "Silber 925"}],
        },
        headers=goldsmith_auth_headers,
    )
    assert patched.status_code == 200, patched.text

    converted = await client.post(
        f"{CONSULTATIONS_URL}{cid}/convert",
        json={"target": "order"},
        headers=goldsmith_auth_headers,
    )
    assert converted.status_code == 200, converted.text
    order = await _load_order(db_session, converted.json()["converted_order_id"])
    assert order.order_type == OrderTypeEnum.PENDANT
    assert order.ring_size_mm is None
    assert order.alloy == "Ag925"
    assert order.metal_type == MetalType.SILVER_925
