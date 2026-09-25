"""PATCH /time-tracking/{entry_id}: edit a RUNNING timer.

Owner or ADMIN only; activity, order, location, notes and start time;
start-time bounds; every change appends a change-log line to the notes;
an ``entry_edited`` event goes out on ``time_tracking_updates``.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.core.security import create_access_token, get_password_hash
from goldsmith_erp.db.models import Order, TimeEntry, User, UserRole, WorkshopLocation
from goldsmith_erp.services.running_timer_edit import EDIT_LOG_MARKER, split_notes

pytestmark = pytest.mark.asyncio

URL = "/api/v1/time-tracking/{}"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _entry(db: AsyncSession, order, user, activity, **kw) -> TimeEntry:
    entry = TimeEntry(
        id=str(uuid.uuid4()),
        order_id=order.id,
        user_id=user.id,
        activity_id=activity.id,
        start_time=kw.pop("start_time", _utcnow() - timedelta(minutes=30)),
        origin="manual",
        extra_metadata={},
        **kw,
    )
    db.add(entry)
    await db.commit()
    return entry


async def _location(db: AsyncSession, name: str, **kw) -> WorkshopLocation:
    loc = WorkshopLocation(name=name, kind="bench", is_active=True, **kw)
    db.add(loc)
    await db.commit()
    await db.refresh(loc)
    return loc


@pytest.fixture
def published(monkeypatch):
    events: list[tuple[str, dict]] = []

    async def _capture(channel, message):
        events.append((channel, json.loads(message)))
        return True

    monkeypatch.setattr("goldsmith_erp.core.pubsub.publish_event", _capture)
    return events


async def _other_goldsmith(db: AsyncSession) -> dict:
    user = User(
        email=f"other_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash("otherpassword123"),
        first_name="Other",
        last_name="Goldsmith",
        role=UserRole.GOLDSMITH,
        is_active=True,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    token = create_access_token(
        data={"sub": str(user.id)}, expires_delta=timedelta(hours=1)
    )
    return {"Authorization": f"Bearer {token}"}


class TestEditRunningTimer:
    async def test_owner_edits_activity_location_notes_while_running(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        sample_user,
        auth_headers,
        sample_order,
        sample_activity,
        polishing_activity,
        published,
    ):
        loc = await _location(db_session, "Werkbank 2")
        entry = await _entry(db_session, sample_order, sample_user, sample_activity)
        resp = await client.patch(
            URL.format(entry.id),
            headers=auth_headers,
            json={
                "activity_id": polishing_activity.id,
                "location": "Werkbank 2",
                "notes": "Stein sitzt locker",
            },
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["activity_id"] == polishing_activity.id
        assert body["activity_name"] == polishing_activity.name
        assert body["location"] == "Werkbank 2"
        assert body["location_id"] == loc.id
        assert body["end_time"] is None
        user_text, log = split_notes(body["notes"])
        assert user_text == "Stein sitzt locker"
        assert f"Benutzer #{sample_user.id}" in log
        assert f"Aktivität #{sample_activity.id} → #{polishing_activity.id}" in log
        assert "Werkbank 2" in log

        edits = [p for c, p in published if p.get("action") == "entry_edited"]
        assert [c for c, p in published if p.get("action") == "entry_edited"] == [
            "time_tracking_updates"
        ]
        assert edits[0]["entry_id"] == entry.id
        assert set(edits[0]["fields"]) == {"activity_id", "location", "notes"}

    async def test_running_endpoint_exposes_editable_fields(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        sample_user,
        auth_headers,
        sample_order,
        sample_activity,
    ):
        await _entry(
            db_session, sample_order, sample_user, sample_activity, location="Tresor"
        )
        body = (
            await client.get("/api/v1/time-tracking/running", headers=auth_headers)
        ).json()
        for key in ("activity_id", "order_id", "location", "notes", "start_time"):
            assert key in body
        assert body["activity_name"] == sample_activity.name
        assert body["order_title"] == sample_order.title

    async def test_change_order_and_log_is_kept_across_edits(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        sample_user,
        auth_headers,
        sample_order,
        sample_activity,
        sample_customer,
    ):
        other = Order(title="Kette kürzen", customer_id=sample_customer.id)
        db_session.add(other)
        await db_session.commit()
        entry = await _entry(db_session, sample_order, sample_user, sample_activity)

        first = await client.patch(
            URL.format(entry.id), headers=auth_headers, json={"order_id": other.id}
        )
        assert first.status_code == 200, first.text
        assert first.json()["order_id"] == other.id
        # The client sends plain notes (no log part): the log is kept.
        second = await client.patch(
            URL.format(entry.id), headers=auth_headers, json={"notes": "neu"}
        )
        notes = second.json()["notes"]
        assert notes.startswith("neu")
        assert notes.count(EDIT_LOG_MARKER) == 1
        assert f"Auftrag #{sample_order.id} → #{other.id}" in notes
        assert "Notiz geändert" in notes

    async def test_noop_edit_writes_no_log_and_no_event(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        sample_user,
        auth_headers,
        sample_order,
        sample_activity,
        published,
    ):
        entry = await _entry(db_session, sample_order, sample_user, sample_activity)
        resp = await client.patch(
            URL.format(entry.id),
            headers=auth_headers,
            json={"activity_id": sample_activity.id},
        )
        assert resp.status_code == 200
        assert resp.json()["notes"] is None
        assert [p for _, p in published if p.get("action") == "entry_edited"] == []

    async def test_other_goldsmith_gets_403(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        sample_user,
        sample_order,
        sample_activity,
    ):
        entry = await _entry(db_session, sample_order, sample_user, sample_activity)
        headers = await _other_goldsmith(db_session)
        resp = await client.patch(
            URL.format(entry.id), headers=headers, json={"location": "Tresor"}
        )
        assert resp.status_code == 403

    async def test_admin_may_edit_someone_elses_timer(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        sample_user,
        admin_user,
        admin_auth_headers,
        sample_order,
        sample_activity,
    ):
        await _location(db_session, "Labor")
        entry = await _entry(db_session, sample_order, sample_user, sample_activity)
        resp = await client.patch(
            URL.format(entry.id), headers=admin_auth_headers, json={"location": "Labor"}
        )
        assert resp.status_code == 200
        assert f"Benutzer #{admin_user.id}" in resp.json()["notes"]

    async def test_stopped_entry_is_409(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        sample_user,
        auth_headers,
        sample_order,
        sample_activity,
    ):
        entry = await _entry(
            db_session,
            sample_order,
            sample_user,
            sample_activity,
            end_time=_utcnow(),
            duration_minutes=30,
        )
        resp = await client.patch(
            URL.format(entry.id), headers=auth_headers, json={"location": "Tresor"}
        )
        assert resp.status_code == 409
        assert resp.json()["code"] == "time_entry.not_running"

    async def test_unknown_activity_is_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        sample_user,
        auth_headers,
        sample_order,
        sample_activity,
    ):
        entry = await _entry(db_session, sample_order, sample_user, sample_activity)
        resp = await client.patch(
            URL.format(entry.id), headers=auth_headers, json={"activity_id": 999999}
        )
        assert resp.status_code == 404

    async def test_empty_body_and_unknown_field_are_422(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        sample_user,
        auth_headers,
        sample_order,
        sample_activity,
    ):
        entry = await _entry(db_session, sample_order, sample_user, sample_activity)
        empty = await client.patch(URL.format(entry.id), headers=auth_headers, json={})
        assert empty.status_code == 422
        extra = await client.patch(
            URL.format(entry.id), headers=auth_headers, json={"user_id": 1}
        )
        assert extra.status_code == 422


class TestEditRunningTimerLocationResolve:
    """W8/timer-locations: PATCH resolves ``location_id``/``location`` through
    ``LocationService.resolve``, storing both columns; an unmatched name is a
    German 422 (the edit sheet is dropdown-backed, not legacy free text)."""

    async def test_location_id_writes_both_columns(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        sample_user,
        auth_headers,
        sample_order,
        sample_activity,
    ):
        loc = await _location(db_session, "Tresor")
        entry = await _entry(db_session, sample_order, sample_user, sample_activity)
        resp = await client.patch(
            URL.format(entry.id), headers=auth_headers, json={"location_id": loc.id}
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["location_id"] == loc.id
        assert body["location"] == "Tresor"

    async def test_location_name_resolves_to_matching_id(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        sample_user,
        auth_headers,
        sample_order,
        sample_activity,
    ):
        loc = await _location(db_session, "Werkbank 3")
        entry = await _entry(db_session, sample_order, sample_user, sample_activity)
        resp = await client.patch(
            URL.format(entry.id),
            headers=auth_headers,
            json={"location": "Werkbank 3"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["location_id"] == loc.id
        assert body["location"] == "Werkbank 3"

    async def test_unknown_location_name_is_german_422(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        sample_user,
        auth_headers,
        sample_order,
        sample_activity,
    ):
        entry = await _entry(db_session, sample_order, sample_user, sample_activity)
        resp = await client.patch(
            URL.format(entry.id),
            headers=auth_headers,
            json={"location": "Unbekannter Ort"},
        )
        assert resp.status_code == 422, resp.text
        body = resp.json()
        assert body["code"] == "location.unknown_name"
        assert "Unbekannter Ort" in body["detail"]
        assert "nicht gefunden" in body["detail"]

    async def test_unknown_location_id_is_german_422(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        sample_user,
        auth_headers,
        sample_order,
        sample_activity,
    ):
        entry = await _entry(db_session, sample_order, sample_user, sample_activity)
        resp = await client.patch(
            URL.format(entry.id), headers=auth_headers, json={"location_id": 999999}
        )
        assert resp.status_code == 422, resp.text
        assert resp.json()["code"] == "location.not_found"


class TestStartTimeBounds:
    async def test_earlier_start_is_applied_and_logged(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        sample_user,
        auth_headers,
        sample_order,
        sample_activity,
    ):
        entry = await _entry(db_session, sample_order, sample_user, sample_activity)
        new_start = _utcnow() - timedelta(hours=2)
        resp = await client.patch(
            URL.format(entry.id),
            headers=auth_headers,
            json={"start_time": new_start.isoformat()},
        )
        assert resp.status_code == 200, resp.text
        stored = datetime.fromisoformat(resp.json()["start_time"])
        if stored.tzinfo is None:
            stored = stored.replace(tzinfo=timezone.utc)
        assert abs((stored - new_start).total_seconds()) < 1
        assert "Startzeit" in resp.json()["notes"]

    async def test_future_start_is_422(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        sample_user,
        auth_headers,
        sample_order,
        sample_activity,
    ):
        entry = await _entry(db_session, sample_order, sample_user, sample_activity)
        resp = await client.patch(
            URL.format(entry.id),
            headers=auth_headers,
            json={"start_time": (_utcnow() + timedelta(minutes=10)).isoformat()},
        )
        assert resp.status_code == 422
        assert resp.json()["code"] == "time_entry.start_in_future"

    async def test_start_older_than_24h_is_422(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        sample_user,
        auth_headers,
        sample_order,
        sample_activity,
    ):
        entry = await _entry(db_session, sample_order, sample_user, sample_activity)
        resp = await client.patch(
            URL.format(entry.id),
            headers=auth_headers,
            json={"start_time": (_utcnow() - timedelta(hours=25)).isoformat()},
        )
        assert resp.status_code == 422
        assert resp.json()["code"] == "time_entry.start_too_old"

    async def test_start_before_previous_entry_end_is_422(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        sample_user,
        auth_headers,
        sample_order,
        sample_activity,
    ):
        previous_end = _utcnow() - timedelta(hours=1)
        await _entry(
            db_session,
            sample_order,
            sample_user,
            sample_activity,
            start_time=previous_end - timedelta(hours=1),
            end_time=previous_end,
            duration_minutes=60,
        )
        entry = await _entry(
            db_session,
            sample_order,
            sample_user,
            sample_activity,
            start_time=_utcnow() - timedelta(minutes=30),
        )
        resp = await client.patch(
            URL.format(entry.id),
            headers=auth_headers,
            json={"start_time": (previous_end - timedelta(minutes=5)).isoformat()},
        )
        assert resp.status_code == 422
        assert resp.json()["code"] == "time_entry.start_before_previous"
        assert "vorherigen Zeiterfassung" in resp.json()["detail"]
