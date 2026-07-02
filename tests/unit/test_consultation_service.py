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


@pytest.mark.asyncio
async def test_converted_consultation_can_still_update_status_and_notes(
    db_session, sample_customer, sample_user
):
    """Post-conversion bookkeeping: status/notes stay mutable on CONVERTED rows."""
    created = await ConsultationService.create_consultation(
        db_session,
        ConsultationCreate(customer_id=sample_customer.id, notes="alt"),
        conducted_by_user_id=sample_user.id,
    )
    created.status = ConsultationStatus.CONVERTED
    await db_session.flush()

    updated = await ConsultationService.update_consultation(
        db_session,
        created.id,
        ConsultationUpdate(status=ConsultationStatus.ARCHIVED, notes="neu"),
    )
    assert updated.status is ConsultationStatus.ARCHIVED
    assert updated.notes == "neu"


@pytest.mark.asyncio
async def test_follow_up_side_effect_failure_never_propagates(
    db_session, sample_customer, sample_user, monkeypatch
):
    """Regression: a failing calendar-event write rolls back its own transaction,
    which expires all ORM objects — create_consultation must still return the
    committed consultation without raising (e.g. MissingGreenlet on expired
    attribute access).

    The failure is injected at flush time (not in the CalendarEvent constructor):
    a constructor error fires before any DB work, so no transaction has begun and
    the rollback is a no-op that expires nothing — it would not reproduce the bug.
    Failing the flush guarantees an active transaction whose rollback expires the
    identity map, which is the scenario the service must survive."""
    from goldsmith_erp.db.models import CalendarEvent

    real_flush = db_session.flush

    async def failing_flush(*args, **kwargs):
        if any(isinstance(obj, CalendarEvent) for obj in db_session.new):
            raise RuntimeError("calendar insert failed (simulated)")
        return await real_flush(*args, **kwargs)

    monkeypatch.setattr(db_session, "flush", failing_flush)

    # Capture before the call: the side-effect rollback expires ALL identity-map
    # objects (sample_customer included) — a lazy .id read afterwards would
    # itself raise MissingGreenlet in the test.
    expected_customer_id = sample_customer.id

    when = datetime.utcnow() + timedelta(days=3)
    created = await ConsultationService.create_consultation(
        db_session,
        ConsultationCreate(
            customer_id=sample_customer.id,
            wishes="Anhänger",
            follow_up_at=when,
        ),
        conducted_by_user_id=sample_user.id,
    )

    # (a) no exception propagated; (b) consultation persisted with correct fields
    assert created.id is not None
    assert created.wishes == "Anhänger"
    assert created.customer_id == expected_customer_id
    fetched = await ConsultationService.get_consultation(db_session, created.id)
    assert fetched is not None
    assert fetched.wishes == "Anhänger"
    # (c) no calendar event was linked
    assert created.calendar_event_id is None


def _sabotage_notification_commit(db_session, monkeypatch):
    """Make the notification's self-commit genuinely fail at the DB level.

    NotificationService.create_notification calls ``await db.commit()`` directly
    (no explicit flush), so wrapping flush would not intercept. Instead the
    wrapper nulls the pending Notification's NOT NULL ``title`` right before the
    real commit: the autoflush inside commit then raises a genuine
    IntegrityError, leaving the session in pending-rollback state — the exact
    scenario the guard must recover from. (A wrapper that merely raises before
    touching the DB would not poison the transaction and would not reproduce
    the PendingRollbackError.)
    """
    from goldsmith_erp.db.models import Notification

    real_commit = db_session.commit

    async def sabotaging_commit(*args, **kwargs):
        for obj in db_session.new:
            if isinstance(obj, Notification):
                obj.title = None  # NOT NULL violation -> commit genuinely fails
        return await real_commit(*args, **kwargs)

    monkeypatch.setattr(db_session, "commit", sabotaging_commit)


@pytest.mark.asyncio
async def test_notification_failure_never_propagates_on_create(
    db_session, sample_customer, sample_user, monkeypatch
):
    """Regression: a failed notification commit leaves the session in
    pending-rollback state; without a rollback in the guard, the subsequent
    _reload raises PendingRollbackError even though consultation + calendar
    event committed durably."""
    _sabotage_notification_commit(db_session, monkeypatch)

    when = datetime.utcnow() + timedelta(days=5)
    created = await ConsultationService.create_consultation(
        db_session,
        ConsultationCreate(
            customer_id=sample_customer.id,
            wishes="Kette",
            follow_up_at=when,
        ),
        conducted_by_user_id=sample_user.id,
    )

    # (a) no exception propagated; (b) consultation persisted
    assert created.id is not None
    assert created.wishes == "Kette"
    # (c) calendar branch succeeded before the notification failure
    assert created.calendar_event_id is not None
    # (d) subsequent reads on the recovered session work
    fetched = await ConsultationService.get_consultation(db_session, created.id)
    assert fetched is not None
    assert fetched.calendar_event_id == created.calendar_event_id


@pytest.mark.asyncio
async def test_notification_failure_never_propagates_on_update(
    db_session, sample_customer, sample_user, monkeypatch
):
    """Same guarantee on the update path (follow_up_at set via PATCH)."""
    created = await ConsultationService.create_consultation(
        db_session,
        ConsultationCreate(customer_id=sample_customer.id),
        conducted_by_user_id=sample_user.id,
    )
    _sabotage_notification_commit(db_session, monkeypatch)

    when = datetime.utcnow() + timedelta(days=5)
    updated = await ConsultationService.update_consultation(
        db_session, created.id, ConsultationUpdate(follow_up_at=when)
    )

    assert updated.calendar_event_id is not None
    fetched = await ConsultationService.get_consultation(db_session, updated.id)
    assert fetched is not None
    assert fetched.calendar_event_id == updated.calendar_event_id


@pytest.mark.asyncio
async def test_repeated_follow_up_update_reuses_calendar_event(
    db_session, sample_customer, sample_user
):
    """Regression (issue #13, item 7): two autosave PATCHes that each change
    follow_up_at must UPDATE the same REMINDER CalendarEvent in place rather
    than creating a second one — the previous behaviour orphaned a
    CalendarEvent row on every follow_up_at edit."""
    from sqlalchemy import select

    from goldsmith_erp.db.models import CalendarEvent, CalendarEventType

    first_when = datetime.utcnow() + timedelta(days=7)
    created = await ConsultationService.create_consultation(
        db_session,
        ConsultationCreate(customer_id=sample_customer.id, follow_up_at=first_when),
        conducted_by_user_id=sample_user.id,
    )
    first_event_id = created.calendar_event_id
    assert first_event_id is not None

    second_when = first_when + timedelta(days=10)
    updated = await ConsultationService.update_consultation(
        db_session, created.id, ConsultationUpdate(follow_up_at=second_when)
    )

    # Same event reused — no new CalendarEvent row was created.
    assert updated.calendar_event_id == first_event_id

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
    assert len(events) == 1
    assert events[0].id == first_event_id
    assert events[0].start_datetime == second_when
