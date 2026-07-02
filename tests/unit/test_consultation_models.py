"""Model-level tests for the V1.1 consultation tables."""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from goldsmith_erp.db.models import (
    Consultation,
    ConsultationOccasion,
    ConsultationPhoto,
    ConsultationPhotoKind,
    ConsultationStatus,
    CustomerNoGo,
    NoGoCategory,
)


@pytest.mark.asyncio
async def test_consultation_roundtrip(db_session, sample_customer, sample_user):
    """Consultation round-trips through the DB with enum columns intact."""
    consultation = Consultation(
        customer_id=sample_customer.id,
        conducted_by=sample_user.id,
        occasion=ConsultationOccasion.ENGAGEMENT,
        wishes="Verlobungsring, Rotgold, schlicht",
        status=ConsultationStatus.DRAFT,
    )
    db_session.add(consultation)
    await db_session.flush()

    row = (
        await db_session.execute(select(Consultation).filter_by(id=consultation.id))
    ).scalar_one()
    assert row.status is ConsultationStatus.DRAFT
    assert row.occasion is ConsultationOccasion.ENGAGEMENT
    assert row.created_at is not None


@pytest.mark.asyncio
async def test_no_go_and_photo_relationships(db_session, sample_customer, sample_user):
    """CustomerNoGo and ConsultationPhoto attach correctly to a Consultation."""
    consultation = Consultation(
        customer_id=sample_customer.id, conducted_by=sample_user.id
    )
    db_session.add(consultation)
    await db_session.flush()

    db_session.add(
        CustomerNoGo(
            customer_id=sample_customer.id,
            category=NoGoCategory.ALLERGY,
            value="Nickel",
            source_consultation_id=consultation.id,
        )
    )
    db_session.add(
        ConsultationPhoto(
            consultation_id=consultation.id,
            kind=ConsultationPhotoKind.SKETCH,
            file_path="/tmp/x.jpg",
            taken_by=sample_user.id,
        )
    )
    await db_session.flush()

    # Use selectinload rather than a bare attribute access — the ORM's
    # default lazy-load strategy is not awaitable under AsyncSession
    # (CLAUDE.md: "All database queries must use selectinload()").
    row = (
        await db_session.execute(
            select(Consultation)
            .options(selectinload(Consultation.photos))
            .filter_by(id=consultation.id)
        )
    ).scalar_one()
    assert row.photos[0].kind is ConsultationPhotoKind.SKETCH
