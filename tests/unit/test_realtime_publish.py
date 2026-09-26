"""W2-13 / BE-20 — publish result and timer hints.

* ``publish_event`` returns True on success and False after its final
  retry, so "notify on publish failure" paths are live again.
* Starting and stopping a timer publishes a ``time_tracking_updates``
  hint carrying the user id (the hub routes it to that user only).
* ``route_event`` reduces every payload to a role-safe hint.
* W6 repair-realtime fix: repair status changes publish AFTER commit —
  a second, independent DB connection already sees the write when
  ``publish_event`` is invoked.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any

import pytest
from sqlalchemy import func, select

from goldsmith_erp.core import pubsub, ws_manager

# ``mock_publish_event`` (autouse) replaces pubsub.publish_event; keep the
# real function for the tests that exercise it directly.
from goldsmith_erp.core.pubsub import publish_event as real_publish_event
from goldsmith_erp.db.models import RepairItemType, RepairJob
from goldsmith_erp.models.repair import RepairDiagnoseInput, RepairJobCreate
from goldsmith_erp.models.time_entry import TimeEntryStart, TimeEntryStop
from goldsmith_erp.services.repair_service import RepairService
from goldsmith_erp.services.time_tracking_service import TimeTrackingService
from tests.conftest import TestSessionLocal


class _Client:
    def __init__(self, fail: bool) -> None:
        self.fail = fail
        self.published: list[tuple[str, str]] = []

    async def publish(self, channel: str, message: str) -> int:
        if self.fail:
            raise ConnectionError("redis down")
        self.published.append((channel, message))
        return 1


def _patch_client(monkeypatch: pytest.MonkeyPatch, client: _Client) -> None:
    @asynccontextmanager
    async def _factory():  # type: ignore[no-untyped-def]
        yield client

    async def _no_sleep(_: float) -> None:
        return None

    monkeypatch.setattr(pubsub, "get_redis_client", _factory)
    monkeypatch.setattr(pubsub.asyncio, "sleep", _no_sleep)


@pytest.mark.asyncio
class TestPublishEventResult:
    async def test_returns_true_when_redis_accepts(self, monkeypatch):
        client = _Client(fail=False)
        _patch_client(monkeypatch, client)
        assert await real_publish_event("order_updates", "{}") is True
        assert client.published == [("order_updates", "{}")]

    async def test_returns_false_after_final_retry(self, monkeypatch):
        _patch_client(monkeypatch, _Client(fail=True))
        assert await real_publish_event("order_updates", "{}") is False


@pytest.fixture()
def recorded(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []

    async def _record(channel: str, message: str) -> bool:
        if channel == "time_tracking_updates":
            events.append(json.loads(message))
        return True

    monkeypatch.setattr(pubsub, "publish_event", _record)
    return events


@pytest.mark.asyncio
class TestTimerHints:
    async def test_start_publishes_user_scoped_hint(
        self, db_session, sample_order, sample_activity, sample_user, recorded
    ):
        entry = await TimeTrackingService.start_time_entry(
            db_session,
            TimeEntryStart(
                order_id=sample_order.id,
                user_id=sample_user.id,
                activity_id=sample_activity.id,
            ),
        )
        assert recorded == [
            {
                "action": "start",
                "source": "manual",
                "user_id": sample_user.id,
                "entry_id": entry.id,
                "order_id": sample_order.id,
                "activity_id": sample_activity.id,
            }
        ]

    async def test_stop_publishes_user_scoped_hint(
        self, db_session, active_time_entry, recorded
    ):
        await TimeTrackingService.stop_time_entry(
            db_session,
            active_time_entry.id,
            TimeEntryStop(complexity_rating=3, quality_rating=4),
        )
        assert [e["action"] for e in recorded] == ["stop"]
        assert recorded[0]["user_id"] == active_time_entry.user_id
        assert recorded[0]["entry_id"] == active_time_entry.id

    async def test_start_succeeds_when_publish_fails(
        self, db_session, sample_order, sample_activity, sample_user, monkeypatch
    ):
        async def _fail(channel: str, message: str) -> bool:
            return False

        monkeypatch.setattr(pubsub, "publish_event", _fail)
        entry = await TimeTrackingService.start_time_entry(
            db_session,
            TimeEntryStart(
                order_id=sample_order.id,
                user_id=sample_user.id,
                activity_id=sample_activity.id,
            ),
        )
        assert entry.id is not None


class TestRouteEvent:
    def test_order_hint_keeps_only_whitelisted_keys(self):
        routed = ws_manager.route_event(
            "order_updates",
            json.dumps(
                {
                    "action": "update",
                    "order_id": 1,
                    "status": "completed",
                    "price": "10.00",
                    "data": {"price": "10.00", "customer_id": 3},
                }
            ),
        )
        assert routed is not None
        assert routed.user_ids is None
        assert json.loads(routed.frame) == {
            "channel": "order_updates",
            "data": {"action": "update", "order_id": 1, "status": "completed"},
        }

    def test_timer_event_routes_to_its_user(self):
        routed = ws_manager.route_event(
            "time_tracking_updates",
            json.dumps({"action": "stop", "user_id": 5, "interrupt_code": "x"}),
        )
        assert routed is not None
        assert routed.user_ids == frozenset({5})
        assert "interrupt_code" not in routed.frame

    def test_repair_hint_keeps_only_whitelisted_keys(self):
        routed = ws_manager.route_event(
            "repair_updates",
            json.dumps(
                {
                    "action": "status_changed",
                    "repair_id": 1,
                    "repair_number": "REP-2026-0001",
                    "new_status": "quoted",
                    "estimated_cost": "120.00",
                    "diagnosis_notes": "Kette gerissen",
                }
            ),
        )
        assert routed is not None
        assert routed.user_ids is None
        assert json.loads(routed.frame) == {
            "channel": "repair_updates",
            "data": {
                "action": "status_changed",
                "repair_id": 1,
                "repair_number": "REP-2026-0001",
                "new_status": "quoted",
            },
        }

    def test_job_hint_keeps_only_whitelisted_keys(self):
        routed = ws_manager.route_event(
            "job_updates",
            json.dumps(
                {
                    "job_id": 5,
                    "kind": "order",
                    "status": "in_progress",
                    "timestamp": "2026-09-25T10:00:00+00:00",
                    "customer_id": 3,
                    "title": "Verlobungsring",
                }
            ),
        )
        assert routed is not None
        assert routed.user_ids is None
        assert json.loads(routed.frame) == {
            "channel": "job_updates",
            "data": {
                "job_id": 5,
                "kind": "order",
                "status": "in_progress",
                "timestamp": "2026-09-25T10:00:00+00:00",
            },
        }

    @pytest.mark.parametrize(
        "channel,raw",
        [
            ("time_tracking_updates", json.dumps({"action": "stop"})),
            ("time_tracking_updates", json.dumps({"user_id": True})),
            ("notifications:abc", json.dumps({"id": 1})),
            ("order_updates", "not json"),
            ("order_updates", json.dumps([1, 2])),
            ("material_updates", json.dumps({"action": "x"})),
        ],
    )
    def test_unroutable_events_are_dropped(self, channel, raw):
        assert ws_manager.route_event(channel, raw) is None


@pytest.mark.asyncio
class TestRepairPublishAfterCommit:
    """W6 repair-realtime fix: repair_updates must publish AFTER commit.

    ``publish_event`` is monkeypatched to open a SECOND, independent
    session (own connection) and count RepairJob rows. If the repair
    service still published from inside its ``transactional(db)`` block
    (the pre-fix bug), that second connection would not yet see the
    just-inserted row and the count would be 0.
    """

    async def test_create_repair_publishes_after_commit(
        self, db_session, sample_customer, monkeypatch
    ):
        seen = {"committed": False}

        async def _record(channel: str, message: str) -> bool:
            if channel == "repair_updates":
                async with TestSessionLocal() as verify:
                    count = (
                        await verify.execute(
                            select(func.count()).select_from(RepairJob)
                        )
                    ).scalar_one()
                    seen["committed"] = count > 0
            return True

        monkeypatch.setattr(pubsub, "publish_event", _record)

        await RepairService.create_repair(
            db_session,
            RepairJobCreate(
                item_description="Kette Weissgold",
                item_type=RepairItemType.CHAIN,
                metal_type="750 Weissgold",
                customer_id=sample_customer.id,
            ),
            user_id=1,
        )

        assert seen["committed"] is True

    async def test_status_transition_publishes_after_commit(
        self, db_session, sample_customer, monkeypatch
    ):
        repair = await RepairService.create_repair(
            db_session,
            RepairJobCreate(
                item_description="Ring Gelbgold",
                item_type=RepairItemType.RING,
                metal_type="585 Gelbgold",
                customer_id=sample_customer.id,
            ),
            user_id=1,
        )

        seen = {"status_at_publish": None}

        async def _record(channel: str, message: str) -> bool:
            if channel == "repair_updates" and json.loads(message).get("new_status"):
                async with TestSessionLocal() as verify:
                    row = (
                        await verify.execute(
                            select(RepairJob).where(RepairJob.id == repair.id)
                        )
                    ).scalar_one()
                    seen["status_at_publish"] = row.status.value
            return True

        monkeypatch.setattr(pubsub, "publish_event", _record)

        await RepairService.diagnose(
            db_session,
            repair.id,
            RepairDiagnoseInput(diagnosis_notes="Loetstelle", estimated_cost=40.0),
            user_id=1,
        )

        # The independent connection saw the row already in its NEW status
        # ("quoted") — proof the commit had already landed when publish ran.
        assert seen["status_at_publish"] == "quoted"
