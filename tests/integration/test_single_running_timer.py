"""BE-12 (W1-17): at most one running timer per user.

docs/review/2026-09-25/03-backend-correctness.md BE-12: ``start_time_entry``
checked for a running entry and then inserted, with no lock and no index.
A double tap (or bench tablet plus phone) created two open entries, after
which ``GET /running`` and every ``/start`` raised ``MultipleResultsFound``
(500) until someone edited the DB.

Fix under test:
- partial unique index ``uq_time_entries_one_running`` on
  ``time_entries(user_id) WHERE end_time IS NULL`` (PG and SQLite);
- the service maps the IntegrityError of a lost race to a 409;
- a sequential second start is a 409 with a German message;
- ``get_running_entry`` never raises ``MultipleResultsFound``.

The true two-session race runs on PostgreSQL only (SQLite serialises
writers); here the race is reproduced deterministically by making the
pre-insert check miss the running entry, which is exactly the window two
concurrent requests hit.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import func, inspect, select
from sqlalchemy.exc import IntegrityError

from goldsmith_erp.db.models import TimeEntry
from goldsmith_erp.models.time_entry import TimeEntryStart
from goldsmith_erp.services.time_tracking_service import TimeTrackingService

pytestmark = pytest.mark.asyncio


def _running(user_id: int, order_id: int, activity_id: int) -> TimeEntry:
    return TimeEntry(
        id=str(uuid.uuid4()),
        order_id=order_id,
        user_id=user_id,
        activity_id=activity_id,
        start_time=datetime.utcnow() - timedelta(minutes=5),
        end_time=None,
        created_at=datetime.utcnow(),
    )


async def _open_count(db_session, user_id: int) -> int:
    result = await db_session.execute(
        select(func.count())
        .select_from(TimeEntry)
        .where(TimeEntry.user_id == user_id, TimeEntry.end_time.is_(None))
    )
    return int(result.scalar_one())


class TestPartialUniqueIndex:
    async def test_index_exists_on_time_entries(self, db_session) -> None:
        def _index_names(sync_conn):
            return {i["name"] for i in inspect(sync_conn).get_indexes("time_entries")}

        conn = await db_session.connection()
        names = await conn.run_sync(_index_names)
        assert "uq_time_entries_one_running" in names

    async def test_second_open_entry_for_same_user_violates_index(
        self, db_session, sample_user, sample_order, sample_activity
    ) -> None:
        db_session.add(_running(sample_user.id, sample_order.id, sample_activity.id))
        await db_session.commit()

        db_session.add(_running(sample_user.id, sample_order.id, sample_activity.id))
        with pytest.raises(IntegrityError):
            await db_session.commit()
        await db_session.rollback()

    async def test_stopped_entries_and_other_users_are_not_restricted(
        self, db_session, sample_user, admin_user, sample_order, sample_activity
    ) -> None:
        stopped = _running(sample_user.id, sample_order.id, sample_activity.id)
        stopped.end_time = datetime.utcnow()
        stopped.duration_minutes = 5
        db_session.add(stopped)
        db_session.add(_running(sample_user.id, sample_order.id, sample_activity.id))
        db_session.add(_running(admin_user.id, sample_order.id, sample_activity.id))
        await db_session.commit()

        assert await _open_count(db_session, sample_user.id) == 1
        assert await _open_count(db_session, admin_user.id) == 1


class TestServiceStart:
    async def test_second_sequential_start_is_409(
        self, db_session, sample_user, sample_order, sample_activity
    ) -> None:
        start = TimeEntryStart(
            order_id=sample_order.id,
            activity_id=sample_activity.id,
            user_id=sample_user.id,
        )
        await TimeTrackingService.start_time_entry(db_session, start)

        with pytest.raises(HTTPException) as exc_info:
            await TimeTrackingService.start_time_entry(db_session, start)

        assert exc_info.value.status_code == 409
        assert "läuft bereits" in str(exc_info.value.detail)
        assert await _open_count(db_session, sample_user.id) == 1

    async def test_lost_race_maps_integrity_error_to_409(
        self, db_session, sample_user, sample_order, sample_activity, monkeypatch
    ) -> None:
        user_id = sample_user.id  # the rollback below expires ORM objects
        # The other request already committed its running entry ...
        db_session.add(_running(user_id, sample_order.id, sample_activity.id))
        await db_session.commit()

        # ... but this request's pre-check ran before that commit.
        async def _missed_check(db, user_id):
            return None

        monkeypatch.setattr(TimeTrackingService, "get_running_entry", _missed_check)

        with pytest.raises(HTTPException) as exc_info:
            await TimeTrackingService.start_time_entry(
                db_session,
                TimeEntryStart(
                    order_id=sample_order.id,
                    activity_id=sample_activity.id,
                    user_id=user_id,
                ),
            )

        assert exc_info.value.status_code == 409
        monkeypatch.undo()
        assert await _open_count(db_session, user_id) == 1

    async def test_switch_without_old_entry_while_running_is_409(
        self, db_session, sample_user, sample_order, sample_activity
    ) -> None:
        user_id = sample_user.id  # the rollback below expires ORM objects
        db_session.add(_running(user_id, sample_order.id, sample_activity.id))
        await db_session.commit()

        with pytest.raises(HTTPException) as exc_info:
            await TimeTrackingService.switch_timer(
                db_session,
                user=sample_user,
                old_entry_id=None,
                new_order_id=sample_order.id,
                activity_id=sample_activity.id,
            )

        assert exc_info.value.status_code == 409
        assert await _open_count(db_session, user_id) == 1

    async def test_get_running_entry_returns_the_single_open_entry(
        self, db_session, sample_user, sample_order, sample_activity
    ) -> None:
        entry = _running(sample_user.id, sample_order.id, sample_activity.id)
        entry_id = entry.id
        db_session.add(entry)
        await db_session.commit()

        running = await TimeTrackingService.get_running_entry(
            db_session, sample_user.id
        )

        assert running is not None
        assert running.id == entry_id


class TestHttpStart:
    async def test_double_tap_start_returns_409_german(
        self, client, auth_headers, sample_user, sample_order, sample_activity
    ) -> None:
        body = {"order_id": sample_order.id, "activity_id": sample_activity.id}

        first = await client.post(
            "/api/v1/time-tracking/start", json=body, headers=auth_headers
        )
        second = await client.post(
            "/api/v1/time-tracking/start", json=body, headers=auth_headers
        )

        assert first.status_code == 200, first.text
        assert second.status_code == 409, second.text
        assert "läuft bereits" in second.json()["detail"]

        running = await client.get(
            "/api/v1/time-tracking/running", headers=auth_headers
        )
        assert running.status_code == 200
        assert running.json()["id"] == first.json()["id"]
