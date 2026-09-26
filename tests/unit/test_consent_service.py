"""Unit tests for ``ConsentService`` (GDPR-02 / GDPR-11).

A consent row is the Art. 7(1) proof that the data subject agreed to a
purpose (health data for allergies, photo use, e-mail contact, marketing).
The service must:

- grant a consent (idempotent while one is active for that purpose),
- revoke it (Art. 7(3)) — and, for HEALTH_DATA, delete the health data
  the consent covered (allergies text + ALLERGY no-gos),
- answer ``has_consent`` truthfully for active vs. revoked rows,
- refuse to operate on unknown / erased customers.
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from goldsmith_erp.db.models import (
    Customer,
    CustomerConsent,
    CustomerNoGo,
    NoGoCategory,
)
from goldsmith_erp.models.consent import ConsentMethod, ConsentPurpose
from goldsmith_erp.services.consent_service import (
    ConsentCustomerNotFoundError,
    ConsentService,
)


@pytest.mark.asyncio
async def test_grant_creates_active_consent(db_session, sample_customer, sample_user):
    consent = await ConsentService.grant(
        db_session,
        sample_customer.id,
        purpose=ConsentPurpose.HEALTH_DATA,
        method=ConsentMethod.WRITTEN,
        recorded_by_user_id=sample_user.id,
        note="Formular v1 unterschrieben",
    )
    await db_session.commit()

    assert consent.id is not None
    assert consent.purpose == ConsentPurpose.HEALTH_DATA.value
    assert consent.method == ConsentMethod.WRITTEN.value
    assert consent.granted_at is not None
    assert consent.revoked_at is None
    assert consent.recorded_by_user_id == sample_user.id
    assert await ConsentService.has_consent(
        db_session, sample_customer.id, ConsentPurpose.HEALTH_DATA
    )


@pytest.mark.asyncio
async def test_has_consent_is_purpose_specific(
    db_session, sample_customer, sample_user
):
    await ConsentService.grant(
        db_session,
        sample_customer.id,
        purpose=ConsentPurpose.MARKETING,
        method=ConsentMethod.IN_PERSON,
        recorded_by_user_id=sample_user.id,
    )
    await db_session.commit()

    assert not await ConsentService.has_consent(
        db_session, sample_customer.id, ConsentPurpose.HEALTH_DATA
    )
    assert await ConsentService.has_consent(
        db_session, sample_customer.id, ConsentPurpose.MARKETING
    )


@pytest.mark.asyncio
async def test_grant_is_idempotent_while_active(
    db_session, sample_customer, sample_user
):
    first = await ConsentService.grant(
        db_session,
        sample_customer.id,
        purpose=ConsentPurpose.PHOTO_USE,
        method=ConsentMethod.WRITTEN,
        recorded_by_user_id=sample_user.id,
    )
    second = await ConsentService.grant(
        db_session,
        sample_customer.id,
        purpose=ConsentPurpose.PHOTO_USE,
        method=ConsentMethod.WRITTEN,
        recorded_by_user_id=sample_user.id,
    )
    await db_session.commit()

    assert first.id == second.id
    rows = (
        await db_session.execute(
            select(CustomerConsent).filter(
                CustomerConsent.customer_id == sample_customer.id
            )
        )
    ).scalars()
    assert len(list(rows)) == 1


@pytest.mark.asyncio
async def test_revoke_sets_revoked_at_and_has_consent_false(
    db_session, sample_customer, sample_user
):
    await ConsentService.grant(
        db_session,
        sample_customer.id,
        purpose=ConsentPurpose.EMAIL_CONTACT,
        method=ConsentMethod.PORTAL,
        recorded_by_user_id=sample_user.id,
    )
    revoked = await ConsentService.revoke(
        db_session,
        sample_customer.id,
        ConsentPurpose.EMAIL_CONTACT,
        revoked_by_user_id=sample_user.id,
    )
    await db_session.commit()

    assert revoked is not None
    assert revoked.revoked_at is not None
    assert not await ConsentService.has_consent(
        db_session, sample_customer.id, ConsentPurpose.EMAIL_CONTACT
    )


@pytest.mark.asyncio
async def test_revoke_without_active_consent_returns_none(
    db_session, sample_customer, sample_user
):
    result = await ConsentService.revoke(
        db_session,
        sample_customer.id,
        ConsentPurpose.MARKETING,
        revoked_by_user_id=sample_user.id,
    )
    assert result is None


@pytest.mark.asyncio
async def test_revoking_health_consent_deletes_health_data(
    db_session, sample_customer, sample_user
):
    await ConsentService.grant(
        db_session,
        sample_customer.id,
        purpose=ConsentPurpose.HEALTH_DATA,
        method=ConsentMethod.WRITTEN,
        recorded_by_user_id=sample_user.id,
    )
    sample_customer.allergies = "Nickel"
    db_session.add(
        CustomerNoGo(
            customer_id=sample_customer.id,
            category=NoGoCategory.ALLERGY,
            value="Nickel",
        )
    )
    db_session.add(
        CustomerNoGo(
            customer_id=sample_customer.id,
            category=NoGoCategory.METAL,
            value="Rotgold",
        )
    )
    await db_session.commit()

    await ConsentService.revoke(
        db_session,
        sample_customer.id,
        ConsentPurpose.HEALTH_DATA,
        revoked_by_user_id=sample_user.id,
    )
    await db_session.commit()

    refreshed = (
        await db_session.execute(
            select(Customer).filter(Customer.id == sample_customer.id)
        )
    ).scalar_one()
    await db_session.refresh(refreshed)
    assert refreshed.allergies is None

    remaining = list(
        (
            await db_session.execute(
                select(CustomerNoGo).filter(
                    CustomerNoGo.customer_id == sample_customer.id
                )
            )
        ).scalars()
    )
    # The ALLERGY no-go is health data and goes; the metal preference stays.
    assert [n.category for n in remaining] == [NoGoCategory.METAL]


@pytest.mark.asyncio
async def test_grant_for_unknown_customer_raises(db_session, sample_user):
    with pytest.raises(ConsentCustomerNotFoundError):
        await ConsentService.grant(
            db_session,
            987654,
            purpose=ConsentPurpose.HEALTH_DATA,
            method=ConsentMethod.WRITTEN,
            recorded_by_user_id=sample_user.id,
        )


@pytest.mark.asyncio
async def test_grant_for_erased_customer_raises(
    db_session, sample_customer, sample_user
):
    sample_customer.is_deleted = True
    await db_session.commit()

    with pytest.raises(ConsentCustomerNotFoundError):
        await ConsentService.grant(
            db_session,
            sample_customer.id,
            purpose=ConsentPurpose.MARKETING,
            method=ConsentMethod.WRITTEN,
            recorded_by_user_id=sample_user.id,
        )


@pytest.mark.asyncio
async def test_delete_all_for_customer_removes_every_row(
    db_session, sample_customer, sample_user
):
    for purpose in (ConsentPurpose.HEALTH_DATA, ConsentPurpose.MARKETING):
        await ConsentService.grant(
            db_session,
            sample_customer.id,
            purpose=purpose,
            method=ConsentMethod.WRITTEN,
            recorded_by_user_id=sample_user.id,
        )
    await db_session.commit()

    deleted = await ConsentService.delete_all_for_customer(
        db_session, sample_customer.id
    )
    await db_session.commit()

    assert deleted == 2
    assert await ConsentService.list_consents(db_session, sample_customer.id) == []
