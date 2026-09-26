"""W2-16 (DOM-21, decision D-16): Altgold ID capture and Ankaufsbuch.

Above ``SCRAP_GOLD_ID_THRESHOLD_EUR`` (default 2,000 EUR) the record cannot
be SIGNED without identification; the ID number and issuing authority are
stored encrypted; reads show only the last four digits; the Ankaufsbuch
export (CSV / PDF, ADMIN only) lists the signed purchases of a period.
"""

from __future__ import annotations

from datetime import datetime

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.core.config import settings
from goldsmith_erp.db.models import (
    AlloyType,
    Customer,
    Order,
    OrderStatusEnum,
    ScrapGold,
    ScrapGoldItem,
    ScrapGoldStatus,
    User,
)

SIGNATURE = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB"
ID_BODY = {
    "id_document_type": "personalausweis",
    "id_document_number": "L01X00T471234",
    "id_issuing_authority": "Stadt München",
}


@pytest.fixture(autouse=True)
def _patch_middleware_session(monkeypatch, db_session):
    from sqlalchemy.ext.asyncio import AsyncSession as _AsyncSession
    from sqlalchemy.orm import sessionmaker

    from goldsmith_erp.middleware import audit_logging

    factory = sessionmaker(
        bind=db_session.bind, class_=_AsyncSession, expire_on_commit=False
    )
    monkeypatch.setattr(audit_logging, "AsyncSessionLocal", factory)


async def _record(
    db: AsyncSession,
    customer: Customer,
    creator: User,
    value: float,
    status: ScrapGoldStatus = ScrapGoldStatus.CALCULATED,
    signed_at: datetime | None = None,
) -> ScrapGold:
    order = Order(
        title="Altgold",
        description="Ankauf",
        customer_id=customer.id,
        status=OrderStatusEnum.CONFIRMED,
        is_deleted=False,
    )
    db.add(order)
    await db.commit()
    scrap = ScrapGold(
        order_id=order.id,
        customer_id=customer.id,
        created_by=creator.id,
        status=status,
        total_fine_gold_g=round(value / 60, 3),
        total_value_eur=value,
        gold_price_per_g=60.0,
        price_source="fixed_rate",
        signed_at=signed_at,
    )
    db.add(scrap)
    await db.commit()
    db.add(
        ScrapGoldItem(
            scrap_gold_id=scrap.id,
            description="Alter Ehering",
            alloy=AlloyType.GOLD_585,
            weight_g=10.0,
            fine_content_g=5.85,
        )
    )
    await db.commit()
    await db.refresh(scrap)
    return scrap


@pytest_asyncio.fixture
async def big_purchase(db_session, test_customer, goldsmith_user) -> ScrapGold:
    return await _record(db_session, test_customer, goldsmith_user, 2500.0)


@pytest.mark.asyncio
async def test_sign_above_threshold_without_id_is_refused(
    client: AsyncClient, big_purchase: ScrapGold, goldsmith_auth_headers: dict
):
    resp = await client.post(
        f"/api/v1/scrap-gold/{big_purchase.id}/sign",
        json={"signature_data": SIGNATURE},
        headers=goldsmith_auth_headers,
    )
    assert resp.status_code == 422, resp.text
    assert "Ausweis" in resp.text


@pytest.mark.asyncio
async def test_sign_above_threshold_with_id_succeeds_and_masks_the_number(
    client: AsyncClient,
    db_session: AsyncSession,
    big_purchase: ScrapGold,
    goldsmith_user: User,
    goldsmith_auth_headers: dict,
):
    saved = await client.put(
        f"/api/v1/scrap-gold/{big_purchase.id}/identification",
        json=ID_BODY,
        headers=goldsmith_auth_headers,
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["id_document_type"] == "personalausweis"
    assert body["id_document_number_last4"] == "1234"
    assert body["has_identification"] is True
    assert body["id_required"] is True
    assert body["id_checked_by"] == goldsmith_user.id
    assert "L01X00T471234" not in saved.text

    signed = await client.post(
        f"/api/v1/scrap-gold/{big_purchase.id}/sign",
        json={"signature_data": SIGNATURE},
        headers=goldsmith_auth_headers,
    )
    assert signed.status_code == 200, signed.text
    assert signed.json()["status"] == "signed"

    # At rest the number and the authority are ciphertext.
    raw = (
        await db_session.execute(
            text(
                "SELECT id_document_number, id_issuing_authority FROM scrap_gold"
                " WHERE id = :id"
            ),
            {"id": big_purchase.id},
        )
    ).one()
    assert raw[0] and "L01X00T471234" not in raw[0]
    assert raw[1] and "München" not in raw[1]

    # Signed records are frozen, the ID data too (BE-11).
    again = await client.put(
        f"/api/v1/scrap-gold/{big_purchase.id}/identification",
        json=ID_BODY,
        headers=goldsmith_auth_headers,
    )
    assert again.status_code == 409


@pytest.mark.asyncio
async def test_below_threshold_id_is_optional(
    client: AsyncClient,
    db_session: AsyncSession,
    test_customer: Customer,
    goldsmith_user: User,
    goldsmith_auth_headers: dict,
):
    small = await _record(db_session, test_customer, goldsmith_user, 480.0)
    resp = await client.post(
        f"/api/v1/scrap-gold/{small.id}/sign",
        json={"signature_data": SIGNATURE},
        headers=goldsmith_auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["id_required"] is False


@pytest.mark.asyncio
async def test_threshold_is_configurable(
    client: AsyncClient,
    db_session: AsyncSession,
    test_customer: Customer,
    goldsmith_user: User,
    goldsmith_auth_headers: dict,
    monkeypatch,
):
    monkeypatch.setattr(settings, "SCRAP_GOLD_ID_THRESHOLD_EUR", 100.0)
    small = await _record(db_session, test_customer, goldsmith_user, 480.0)
    resp = await client.post(
        f"/api/v1/scrap-gold/{small.id}/sign",
        json={"signature_data": SIGNATURE},
        headers=goldsmith_auth_headers,
    )
    assert resp.status_code == 422


def test_default_threshold_is_2000_eur():
    assert settings.SCRAP_GOLD_ID_THRESHOLD_EUR == 2000.0


@pytest.mark.asyncio
async def test_identification_is_validated(
    client: AsyncClient, big_purchase: ScrapGold, goldsmith_auth_headers: dict
):
    resp = await client.put(
        f"/api/v1/scrap-gold/{big_purchase.id}/identification",
        json={**ID_BODY, "id_document_type": "bibliotheksausweis"},
        headers=goldsmith_auth_headers,
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_ankaufsbuch_csv_lists_signed_purchases_of_the_period(
    client: AsyncClient,
    db_session: AsyncSession,
    test_customer: Customer,
    goldsmith_user: User,
    admin_auth_headers: dict,
):
    signed = await _record(
        db_session,
        test_customer,
        goldsmith_user,
        2500.0,
        status=ScrapGoldStatus.SIGNED,
        signed_at=datetime(2026, 9, 10, 11, 0),
    )
    signed.id_document_type = "reisepass"
    signed.id_document_number = "C01X00T47"
    signed.id_issuing_authority = "Stadt Augsburg"
    await db_session.commit()
    await _record(  # outside the period
        db_session,
        test_customer,
        goldsmith_user,
        300.0,
        status=ScrapGoldStatus.SIGNED,
        signed_at=datetime(2026, 7, 1, 9, 0),
    )
    await _record(db_session, test_customer, goldsmith_user, 900.0)  # unsigned

    resp = await client.get(
        "/api/v1/scrap-gold/ankaufsbuch",
        params={"date_from": "2026-09-01", "date_to": "2026-09-30", "format": "csv"},
        headers=admin_auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"].startswith("text/csv")
    content = resp.content.decode("utf-8-sig")
    assert "vom Steuerberater zu bestätigen" in content
    assert f"AG-{signed.id:05d}" in content
    assert "Mustermann" in content
    assert "C01X00T47" in content
    assert "Stadt Augsburg" in content
    assert "2.500,00" in content
    data_rows = [line for line in content.splitlines() if line.startswith("AG-")]
    assert len(data_rows) == 1


@pytest.mark.asyncio
async def test_ankaufsbuch_pdf_and_admin_only(
    client: AsyncClient,
    admin_auth_headers: dict,
    goldsmith_auth_headers: dict,
):
    params = {"date_from": "2026-09-01", "date_to": "2026-09-30", "format": "pdf"}
    resp = await client.get(
        "/api/v1/scrap-gold/ankaufsbuch", params=params, headers=admin_auth_headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")

    denied = await client.get(
        "/api/v1/scrap-gold/ankaufsbuch", params=params, headers=goldsmith_auth_headers
    )
    assert denied.status_code == 403


@pytest.mark.asyncio
async def test_ankaufsbuch_rejects_an_inverted_period(
    client: AsyncClient, admin_auth_headers: dict
):
    resp = await client.get(
        "/api/v1/scrap-gold/ankaufsbuch",
        params={"date_from": "2026-09-30", "date_to": "2026-09-01"},
        headers=admin_auth_headers,
    )
    assert resp.status_code == 422
