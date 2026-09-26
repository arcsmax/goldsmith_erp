"""BE-18 + SEC-13 (W1-17): sane time edits and owner checks.

BE-18: ``update_time_entry`` recomputed the duration from
``end_time - start_time`` without checking ``end > start`` (a correction to
08:00 on a 09:00 entry stored -60 minutes), accepted ``duration_minutes``
together with a conflicting ``end_time``, and a PUT with ``end_time`` on a
running entry stopped it without the stop-flow side effects.

SEC-13: stop, PUT and interruptions looked entries up by id only, so a
goldsmith who learned a colleague's entry id could edit their hours.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from goldsmith_erp.core.security import create_access_token, get_password_hash
from goldsmith_erp.db.models import TimeEntry, User, UserRole
from goldsmith_erp.models.time_entry import TimeEntryUpdate
from goldsmith_erp.services.activity_service import ActivityService
from goldsmith_erp.services.time_tracking_service import TimeTrackingService

# ---------------------------------------------------------------------------
# Schema level
# ---------------------------------------------------------------------------


class TestTimeEntryUpdateSchema:
    def test_duration_together_with_end_time_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            TimeEntryUpdate(end_time=datetime.utcnow(), duration_minutes=30)

    def test_end_time_alone_is_accepted(self) -> None:
        assert TimeEntryUpdate(end_time=datetime.utcnow()).end_time is not None

    def test_aware_end_time_is_normalised_to_aware_utc(self) -> None:
        aware = datetime(2026, 9, 25, 10, 0, tzinfo=timezone(timedelta(hours=2)))
        update = TimeEntryUpdate(end_time=aware)
        assert update.end_time == datetime(2026, 9, 25, 8, 0, tzinfo=timezone.utc)
        assert update.end_time.utcoffset() == timedelta(0)


# ---------------------------------------------------------------------------
# HTTP level (422 / stop flow / owner checks)
# ---------------------------------------------------------------------------


def _headers(user: User) -> dict:
    token = create_access_token(
        data={"sub": str(user.id)}, expires_delta=timedelta(hours=1)
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
async def other_goldsmith(db_session) -> User:
    user = User(
        email=f"gs_b_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash("otherpassword123"),
        first_name="Goldschmied",
        last_name="B",
        role=UserRole.GOLDSMITH,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _entry(db_session, user, order, activity, *, running: bool) -> str:
    start = datetime.utcnow() - timedelta(hours=2)
    entry = TimeEntry(
        id=str(uuid.uuid4()),
        order_id=order.id,
        user_id=user.id,
        activity_id=activity.id,
        start_time=start,
        end_time=None if running else start + timedelta(hours=1),
        duration_minutes=None if running else 60,
        created_at=datetime.utcnow(),
    )
    db_session.add(entry)
    await db_session.commit()
    return entry.id


@pytest.mark.asyncio
class TestUpdateValidation:
    async def test_end_before_start_is_422(
        self, client, db_session, sample_user, sample_order, sample_activity
    ) -> None:
        entry_id = await _entry(
            db_session, sample_user, sample_order, sample_activity, running=False
        )
        too_early = (datetime.utcnow() - timedelta(hours=3)).isoformat()

        resp = await client.put(
            f"/api/v1/time-tracking/{entry_id}",
            json={"end_time": too_early},
            headers=_headers(sample_user),
        )

        assert resp.status_code == 422, resp.text
        entry = await TimeTrackingService.get_time_entry(db_session, entry_id)
        await db_session.refresh(entry)
        assert entry.duration_minutes == 60

    async def test_longer_than_24h_is_422(
        self, client, db_session, sample_user, sample_order, sample_activity
    ) -> None:
        entry_id = await _entry(
            db_session, sample_user, sample_order, sample_activity, running=False
        )
        too_late = (datetime.utcnow() + timedelta(hours=30)).isoformat()

        resp = await client.put(
            f"/api/v1/time-tracking/{entry_id}",
            json={"end_time": too_late},
            headers=_headers(sample_user),
        )

        assert resp.status_code == 422, resp.text

    async def test_duration_with_end_time_is_422(
        self, client, db_session, sample_user, sample_order, sample_activity
    ) -> None:
        entry_id = await _entry(
            db_session, sample_user, sample_order, sample_activity, running=False
        )

        resp = await client.put(
            f"/api/v1/time-tracking/{entry_id}",
            json={"end_time": datetime.utcnow().isoformat(), "duration_minutes": 5},
            headers=_headers(sample_user),
        )

        assert resp.status_code == 422, resp.text

    async def test_valid_correction_recomputes_duration(
        self, client, db_session, sample_user, sample_order, sample_activity
    ) -> None:
        entry_id = await _entry(
            db_session, sample_user, sample_order, sample_activity, running=False
        )
        entry = await TimeTrackingService.get_time_entry(db_session, entry_id)
        new_end = entry.start_time + timedelta(minutes=90)

        resp = await client.put(
            f"/api/v1/time-tracking/{entry_id}",
            json={"end_time": new_end.isoformat()},
            headers=_headers(sample_user),
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["duration_minutes"] == 90

    async def test_end_time_on_running_entry_runs_the_stop_flow(
        self,
        client,
        db_session,
        sample_user,
        sample_order,
        sample_activity,
        monkeypatch,
    ) -> None:
        entry_id = await _entry(
            db_session, sample_user, sample_order, sample_activity, running=True
        )
        entry = await TimeTrackingService.get_time_entry(db_session, entry_id)
        new_end = entry.start_time + timedelta(minutes=45)
        averaged: list[float] = []
        original = ActivityService.update_average_duration

        async def _spy(db, activity_id, duration):
            averaged.append(duration)
            return await original(db, activity_id, duration)

        monkeypatch.setattr(ActivityService, "update_average_duration", _spy)

        resp = await client.put(
            f"/api/v1/time-tracking/{entry_id}",
            json={"end_time": new_end.isoformat(), "notes": "vergessen zu stoppen"},
            headers=_headers(sample_user),
        )

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["duration_minutes"] == 45
        assert body["notes"] == "vergessen zu stoppen"
        assert averaged == [45.0]

    async def test_duration_on_running_entry_is_422(
        self, client, db_session, sample_user, sample_order, sample_activity
    ) -> None:
        entry_id = await _entry(
            db_session, sample_user, sample_order, sample_activity, running=True
        )

        resp = await client.put(
            f"/api/v1/time-tracking/{entry_id}",
            json={"duration_minutes": 30},
            headers=_headers(sample_user),
        )

        assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
class TestOwnerChecks:
    async def test_other_goldsmith_cannot_stop_edit_or_interrupt(
        self,
        client,
        db_session,
        sample_user,
        other_goldsmith,
        sample_order,
        sample_activity,
    ) -> None:
        entry_id = await _entry(
            db_session, sample_user, sample_order, sample_activity, running=True
        )
        headers_b = _headers(other_goldsmith)

        stop = await client.post(
            f"/api/v1/time-tracking/{entry_id}/stop", json={}, headers=headers_b
        )
        put = await client.put(
            f"/api/v1/time-tracking/{entry_id}",
            json={"notes": "fremd"},
            headers=headers_b,
        )
        interrupt = await client.post(
            f"/api/v1/time-tracking/{entry_id}/interruptions",
            json={"time_entry_id": entry_id, "reason": "Kunde", "duration_minutes": 5},
            headers=headers_b,
        )

        for resp in (stop, put, interrupt):
            assert resp.status_code == 403, resp.text

        entry = await TimeTrackingService.get_time_entry(db_session, entry_id)
        await db_session.refresh(entry)
        assert entry.end_time is None
        assert entry.notes is None

    async def test_owner_can_stop_own_entry(
        self, client, db_session, sample_user, sample_order, sample_activity
    ) -> None:
        entry_id = await _entry(
            db_session, sample_user, sample_order, sample_activity, running=True
        )

        resp = await client.post(
            f"/api/v1/time-tracking/{entry_id}/stop",
            json={},
            headers=_headers(sample_user),
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["end_time"] is not None

    async def test_admin_can_edit_and_stop_any_entry(
        self,
        client,
        db_session,
        sample_user,
        admin_auth_headers,
        sample_order,
        sample_activity,
    ) -> None:
        entry_id = await _entry(
            db_session, sample_user, sample_order, sample_activity, running=True
        )

        put = await client.put(
            f"/api/v1/time-tracking/{entry_id}",
            json={"notes": "Admin-Korrektur"},
            headers=admin_auth_headers,
        )
        interrupt = await client.post(
            f"/api/v1/time-tracking/{entry_id}/interruptions",
            json={"time_entry_id": entry_id, "reason": "Kunde", "duration_minutes": 5},
            headers=admin_auth_headers,
        )
        stop = await client.post(
            f"/api/v1/time-tracking/{entry_id}/stop",
            json={},
            headers=admin_auth_headers,
        )

        assert put.status_code == 200, put.text
        assert interrupt.status_code == 200, interrupt.text
        assert stop.status_code == 200, stop.text

    async def test_unknown_entry_is_404_not_403(self, client, other_goldsmith) -> None:
        resp = await client.post(
            f"/api/v1/time-tracking/{uuid.uuid4()}/stop",
            json={},
            headers=_headers(other_goldsmith),
        )
        assert resp.status_code == 404, resp.text
