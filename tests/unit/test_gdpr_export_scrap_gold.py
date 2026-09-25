# tests/unit/test_gdpr_export_scrap_gold.py
"""W2-06-14-16-11 open item #6: the W2-16 Altgold ID-capture fields
(id_document_type/number/issuing_authority/checked_at) are the customer's
own identification data and belong in their Art. 15 export — previously
``gdpr_export_service._scrap_gold`` omitted them entirely.
"""

from __future__ import annotations

import pytest

from goldsmith_erp.db.models import ScrapGold, ScrapGoldStatus
from goldsmith_erp.services.gdpr_export_service import collect_export_sections

pytestmark = pytest.mark.asyncio


async def _scrap_gold(
    db_session, *, order, customer, admin_user, **id_fields
) -> ScrapGold:
    scrap = ScrapGold(
        order_id=order.id,
        customer_id=customer.id,
        created_by=admin_user.id,
        status=ScrapGoldStatus.RECEIVED,
        total_fine_gold_g=1.0,
        total_value_eur=60.0,
        gold_price_per_g=60.0,
        price_source="fixed_rate",
        **id_fields,
    )
    db_session.add(scrap)
    await db_session.commit()
    await db_session.refresh(scrap)
    return scrap


async def test_export_includes_decrypted_id_fields_when_captured(
    db_session, sample_order, sample_customer, admin_user
) -> None:
    await _scrap_gold(
        db_session,
        order=sample_order,
        customer=sample_customer,
        admin_user=admin_user,
        id_document_type="personalausweis",
        id_document_number="L01X00T47",
        id_issuing_authority="Stadt Berlin",
    )

    sections = await collect_export_sections(
        db_session, sample_customer.id, [sample_order.id]
    )
    (row,) = sections["scrap_gold"]

    # Decrypted, plain values — not ciphertext — because this is the
    # customer's own copy of their data (Art. 15), and EncryptedString
    # decrypts transparently on ORM attribute access.
    assert row["id_document_type"] == "personalausweis"
    assert row["id_document_number"] == "L01X00T47"
    assert row["id_issuing_authority"] == "Stadt Berlin"
    # Internal staff audit reference, not the customer's data — omitted.
    assert "id_checked_by" not in row


async def test_export_has_none_id_fields_when_not_captured(
    db_session, sample_order, sample_customer, admin_user
) -> None:
    await _scrap_gold(
        db_session, order=sample_order, customer=sample_customer, admin_user=admin_user
    )

    sections = await collect_export_sections(
        db_session, sample_customer.id, [sample_order.id]
    )
    (row,) = sections["scrap_gold"]

    assert row["id_document_type"] is None
    assert row["id_document_number"] is None
    assert row["id_issuing_authority"] is None
    assert row["id_checked_at"] is None
