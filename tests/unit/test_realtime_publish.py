"""W2-13 / BE-20 — publish result and timer hints.

* ``publish_event`` returns True on success and False after its final
  retry, so "notify on publish failure" paths are live again.
* Starting and stopping a timer publishes a ``time_tracking_updates``
  hint carrying the user id (the hub routes it to that user only).
* ``route_event`` reduces every payload to a role-safe hint.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any

import pytest

from goldsmith_erp.core import pubsub, ws_manager

# ``mock_publish_event`` (autouse) replaces pubsub.publish_event; keep the
# real function for the tests that exercise it directly.
from goldsmith_erp.core.pubsub import publish_event as real_publish_event
from goldsmith_erp.models.time_entry import TimeEntryStart, TimeEntryStop
from goldsmith_erp.services.time_tracking_service import TimeTrackingService


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
