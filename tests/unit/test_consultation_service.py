"""Unit tests for ConsultationService."""

from datetime import datetime, timedelta

import pytest

from goldsmith_erp.db.models import ConsultationStatus
from goldsmith_erp.models.consultation import ConsultationCreate, ConsultationUpdate
from goldsmith_erp.services.consultation_service import ConsultationService


@pytest.mark.asyncio
async def test_create_and_get_roundtrip(db_session, sample_customer, sample_user):
    created = await ConsultationService.create_consultation(
        db_session,
        ConsultationCreate(customer_id=sample_customer.id, wishes="Rotgold-Ring"),
        conducted_by_user_id=sample_user.id,
    )
    fetched = await ConsultationService.get_consultation(db_session, created.id)
    assert fetched is not None
    assert fetched.wishes == "Rotgold-Ring"
    assert fetched.status is ConsultationStatus.DRAFT


@pytest.mark.asyncio
async def test_create_unknown_customer_raises(db_session, sample_user):
    with pytest.raises(ValueError, match="Customer 99999 not found"):
        await ConsultationService.create_consultation(
            db_session,
            ConsultationCreate(customer_id=99999),
            conducted_by_user_id=sample_user.id,
        )


@pytest.mark.asyncio
async def test_patch_update_only_touches_set_fields(
    db_session, sample_customer, sample_user
):
    created = await ConsultationService.create_consultation(
        db_session,
        ConsultationCreate(customer_id=sample_customer.id, wishes="A", notes="B"),
        conducted_by_user_id=sample_user.id,
    )
    updated = await ConsultationService.update_consultation(
        db_session, created.id, ConsultationUpdate(notes="C")
    )
    assert updated.wishes == "A"  # untouched
    assert updated.notes == "C"


@pytest.mark.asyncio
async def test_update_converted_consultation_blocked(
    db_session, sample_customer, sample_user
):
    created = await ConsultationService.create_consultation(
        db_session,
        ConsultationCreate(customer_id=sample_customer.id),
        conducted_by_user_id=sample_user.id,
    )
    created.status = ConsultationStatus.CONVERTED
    await db_session.flush()
    with pytest.raises(ValueError, match="bereits konvertiert"):
        await ConsultationService.update_consultation(
            db_session, created.id, ConsultationUpdate(wishes="Neu")
        )


@pytest.mark.asyncio
async def test_follow_up_creates_calendar_event(
    db_session, sample_customer, sample_user
):
    from sqlalchemy import select

    from goldsmith_erp.db.models import CalendarEvent, CalendarEventType

    when = datetime.utcnow() + timedelta(days=7)
    created = await ConsultationService.create_consultation(
        db_session,
        ConsultationCreate(customer_id=sample_customer.id, follow_up_at=when),
        conducted_by_user_id=sample_user.id,
    )
    events = (
        (
            await db_session.execute(
                select(CalendarEvent).filter(
                    CalendarEvent.event_type == CalendarEventType.REMINDER
                )
            )
        )
        .scalars()
        .all()
    )
    assert any(f"Beratung #{created.id}" in e.title for e in events)
    assert created.calendar_event_id is not None
