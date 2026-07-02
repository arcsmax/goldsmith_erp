"""Unit tests for NoGoService — V1.1 consultation module.

Covers the brief's three scenarios (add/list/delete roundtrip, duplicate guard,
bidirectional substring conflict matching) plus the legacy-field sync: adding
an ALLERGY no-go must also append to the legacy ``Customer.allergies`` string
(dedup case-insensitively, never truncate existing user data past the 500-char
column limit).
"""

import logging

import pytest

from goldsmith_erp.models.consultation import NoGoCreate
from goldsmith_erp.services.no_go_service import NoGoService


@pytest.mark.asyncio
async def test_add_list_delete_roundtrip(db_session, sample_customer):
    ng = await NoGoService.add_no_go(
        db_session, sample_customer.id, NoGoCreate(category="allergy", value="Nickel")
    )
    assert [
        n.value for n in await NoGoService.list_no_gos(db_session, sample_customer.id)
    ] == ["Nickel"]
    await NoGoService.delete_no_go(db_session, sample_customer.id, ng.id)
    assert await NoGoService.list_no_gos(db_session, sample_customer.id) == []


@pytest.mark.asyncio
async def test_duplicate_no_go_rejected(db_session, sample_customer):
    await NoGoService.add_no_go(
        db_session, sample_customer.id, NoGoCreate(category="allergy", value="Nickel")
    )
    with pytest.raises(ValueError, match="existiert bereits"):
        await NoGoService.add_no_go(
            db_session,
            sample_customer.id,
            NoGoCreate(category="allergy", value="nickel"),
        )


@pytest.mark.asyncio
async def test_check_conflicts_bidirectional_substring(db_session, sample_customer):
    await NoGoService.add_no_go(
        db_session, sample_customer.id, NoGoCreate(category="metal", value="Weißgold")
    )
    # candidate contains no-go
    hits = await NoGoService.check_conflicts(
        db_session, sample_customer.id, ["Weißgold 585 rhodiniert"]
    )
    assert len(hits) == 1 and hits[0].value == "Weißgold"
    # no-go contains candidate
    await NoGoService.add_no_go(
        db_session,
        sample_customer.id,
        NoGoCreate(category="stone", value="synthetischer Rubin"),
    )
    hits = await NoGoService.check_conflicts(db_session, sample_customer.id, ["Rubin"])
    assert any(h.category.value == "stone" for h in hits)
    # no match
    assert (
        await NoGoService.check_conflicts(db_session, sample_customer.id, ["Gelbgold"])
        == []
    )


@pytest.mark.asyncio
async def test_add_no_go_unknown_customer_raises(db_session):
    with pytest.raises(ValueError, match="Customer 99999 not found"):
        await NoGoService.add_no_go(
            db_session, 99999, NoGoCreate(category="allergy", value="Nickel")
        )


@pytest.mark.asyncio
async def test_delete_no_go_not_found_raises(db_session, sample_customer):
    with pytest.raises(ValueError):
        await NoGoService.delete_no_go(db_session, sample_customer.id, 99999)


# ── Legacy-field sync (Customer.allergies) ─────────────────────────────────


@pytest.mark.asyncio
async def test_add_allergy_no_go_syncs_legacy_field(db_session, sample_customer):
    assert sample_customer.allergies is None
    await NoGoService.add_no_go(
        db_session, sample_customer.id, NoGoCreate(category="allergy", value="Nickel")
    )
    assert "Nickel" in sample_customer.allergies


@pytest.mark.asyncio
async def test_add_allergy_no_go_does_not_duplicate_existing_legacy_value(
    db_session, sample_customer
):
    sample_customer.allergies = "Nickel"
    await db_session.commit()

    await NoGoService.add_no_go(
        db_session,
        sample_customer.id,
        NoGoCreate(category="allergy", value="nickel"),  # different casing
    )

    assert sample_customer.allergies == "Nickel"
    assert sample_customer.allergies.count("Nickel") == 1


@pytest.mark.asyncio
async def test_add_allergy_no_go_skips_legacy_sync_when_over_500_chars(
    db_session, sample_customer, caplog
):
    """Appending must never truncate existing user data — skip instead and warn."""
    sample_customer.allergies = "A" * 495
    await db_session.commit()

    with caplog.at_level(logging.WARNING):
        await NoGoService.add_no_go(
            db_session,
            sample_customer.id,
            NoGoCreate(category="allergy", value="Nickel"),
        )

    assert sample_customer.allergies == "A" * 495  # untouched, not truncated
    assert any("500" in record.message for record in caplog.records)


@pytest.mark.asyncio
async def test_add_non_allergy_no_go_does_not_touch_legacy_field(
    db_session, sample_customer
):
    await NoGoService.add_no_go(
        db_session, sample_customer.id, NoGoCreate(category="metal", value="Nickel")
    )
    assert sample_customer.allergies is None
