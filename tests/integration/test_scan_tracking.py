"""Scan tracking (2026-09 audit, SC-01/02/03): every scan is on record.

Covers the owner's requirement end to end on the HTTP surface:

  * a decode writes a ``scan_only`` row (user from JWT, device, location);
  * the action picked afterwards writes a second row linked by
    ``parent_scan_id`` with its result;
  * an unrecognised payload is logged as ``unrecognised``;
  * ``GET /orders/{id}/scans`` / ``GET /repairs/{id}/scans`` (VIEWER
    allowed, newest first, paged, no financial fields);
  * ``GET /scan/history`` (ADMIN/GOLDSMITH only) by code, number, text,
    user and time window;
  * ``last_scan`` on the order and repair detail reads;
  * the reduced ``scan_updates`` realtime hint.
"""

import json
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.core import ws_manager
from goldsmith_erp.db.models import (
    Order,
    OrderStatusEnum,
    RepairItemType,
    RepairJob,
    RepairJobStatus,
    WorkshopLocation,
)

LOG_URL = "/api/v1/scan/log"
HISTORY_URL = "/api/v1/scan/history"
DEVICE_ID = "6f1c2d3e-4b5a-4c6d-8e7f-9a0b1c2d3e4f"

PIECE_SCAN_KEYS = {
    "id",
    "scanned_at",
    "user_id",
    "user_name",
    "location",
    "location_id",
    "action_taken",
    "action_result",
    "input_source",
    "parent_scan_id",
}


@pytest_asyncio.fixture
async def piece_order(db_session: AsyncSession, test_customer) -> Order:
    order = Order(
        title="Verlobungsring Test",
        description="Design vertraulich",
        customer_id=test_customer.id,
        status=OrderStatusEnum.IN_PROGRESS,
        price=1234.00,
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)
    return order


@pytest_asyncio.fixture
async def piece_repair(
    db_session: AsyncSession, test_customer, admin_user
) -> RepairJob:
    token = uuid.uuid4().hex[:6].upper()
    repair = RepairJob(
        repair_number=f"R-SCAN-{token}",
        bag_number=f"T-{token}",
        customer_id=test_customer.id,
        received_by=admin_user.id,
        item_description="Kette Verschluss defekt",
        item_type=RepairItemType.RING,
        status=RepairJobStatus.RECEIVED,
        estimated_cost=80.0,
    )
    db_session.add(repair)
    await db_session.commit()
    await db_session.refresh(repair)
    return repair


def _scan_body(
    entity_type: str,
    entity_id: int,
    action: str = "scan_only",
    location: str = "Werkbank 2",
    **context: object,
) -> dict:
    prefix = entity_type.upper()
    return {
        "raw_payload": f"{prefix}:{entity_id}",
        "resolved_type": entity_type,
        "resolved_id": str(entity_id),
        "resolution_path": "prefix",
        "action_taken": action,
        "idempotency_key": str(uuid.uuid4()),
        "context": {
            "device_id": DEVICE_ID,
            "current_location": location,
            "input_source": "camera",
            "device_type": "tablet",
            **context,
        },
    }


async def _log(client: AsyncClient, headers: dict, body: dict) -> dict:
    resp = await client.post(LOG_URL, json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


class TestScanRows:
    @pytest.mark.asyncio
    async def test_decode_writes_scan_only_row_visible_on_the_piece(
        self, client, goldsmith_auth_headers, goldsmith_user, piece_order
    ):
        row = await _log(
            client, goldsmith_auth_headers, _scan_body("order", piece_order.id)
        )

        resp = await client.get(
            f"/api/v1/orders/{piece_order.id}/scans", headers=goldsmith_auth_headers
        )
        assert resp.status_code == 200
        page = resp.json()
        assert page["total"] == 1
        item = page["items"][0]
        assert set(item.keys()) == PIECE_SCAN_KEYS
        assert item["id"] == row["id"]
        assert item["user_id"] == goldsmith_user.id
        assert item["user_name"] == "Integration Goldsmith"
        assert item["location"] == "Werkbank 2"
        assert item["action_taken"] == "scan_only"
        assert item["input_source"] == "camera"

    @pytest.mark.asyncio
    async def test_action_row_links_to_scan_and_lists_newest_first(
        self, client, goldsmith_auth_headers, piece_order
    ):
        scan = await _log(
            client, goldsmith_auth_headers, _scan_body("order", piece_order.id)
        )
        await _log(
            client,
            goldsmith_auth_headers,
            _scan_body(
                "order",
                piece_order.id,
                action="start_timer",
                parent_scan_id=scan["id"],
                action_result="ok",
            ),
        )
        page = (
            await client.get(
                f"/api/v1/orders/{piece_order.id}/scans", headers=goldsmith_auth_headers
            )
        ).json()
        assert [i["action_taken"] for i in page["items"]] == [
            "start_timer",
            "scan_only",
        ]
        assert page["items"][0]["parent_scan_id"] == scan["id"]
        assert page["items"][0]["action_result"] == "ok"

    @pytest.mark.asyncio
    async def test_failed_action_is_logged_with_result(
        self, client, goldsmith_auth_headers, piece_order
    ):
        scan = await _log(
            client, goldsmith_auth_headers, _scan_body("order", piece_order.id)
        )
        await _log(
            client,
            goldsmith_auth_headers,
            _scan_body(
                "order",
                piece_order.id,
                action="switch_timer",
                parent_scan_id=scan["id"],
                action_result="failed",
            ),
        )
        page = (
            await client.get(
                f"/api/v1/orders/{piece_order.id}/scans", headers=goldsmith_auth_headers
            )
        ).json()
        assert page["items"][0]["action_result"] == "failed"

    @pytest.mark.asyncio
    async def test_unrecognised_payload_is_logged_and_searchable(
        self, client, goldsmith_auth_headers
    ):
        body = {
            "raw_payload": "ALTES-ETIKETT-0815",
            "resolution_path": "unknown",
            "action_taken": "unrecognised",
            "context": {"device_id": DEVICE_ID, "input_source": "manual"},
        }
        await _log(client, goldsmith_auth_headers, body)
        resp = await client.get(
            HISTORY_URL, params={"q": "ETIKETT-08"}, headers=goldsmith_auth_headers
        )
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 1
        assert items[0]["action_taken"] == "unrecognised"
        assert items[0]["resolution_path"] == "unknown"
        assert items[0]["device_id"] == DEVICE_ID

    @pytest.mark.asyncio
    async def test_context_rejects_bad_device_id_and_unknown_keys(
        self, client, goldsmith_auth_headers, piece_order
    ):
        bad_device = _scan_body("order", piece_order.id, device_id="kein-uuid")
        resp = await client.post(
            LOG_URL, json=bad_device, headers=goldsmith_auth_headers
        )
        assert resp.status_code == 422
        smuggle = _scan_body("order", piece_order.id, customer_name="Frau X")
        resp = await client.post(LOG_URL, json=smuggle, headers=goldsmith_auth_headers)
        assert resp.status_code == 422


class TestPieceHistoryAccess:
    @pytest.mark.asyncio
    async def test_viewer_reads_piece_history_without_financials(
        self, client, goldsmith_auth_headers, viewer_auth_headers, piece_order
    ):
        await _log(client, goldsmith_auth_headers, _scan_body("order", piece_order.id))
        resp = await client.get(
            f"/api/v1/orders/{piece_order.id}/scans", headers=viewer_auth_headers
        )
        assert resp.status_code == 200
        text = resp.text
        assert "price" not in text and "1234" not in text
        assert set(resp.json()["items"][0].keys()) == PIECE_SCAN_KEYS

    @pytest.mark.asyncio
    async def test_piece_history_is_paged(
        self, client, goldsmith_auth_headers, piece_order
    ):
        for _ in range(3):
            await _log(
                client, goldsmith_auth_headers, _scan_body("order", piece_order.id)
            )
        resp = await client.get(
            f"/api/v1/orders/{piece_order.id}/scans",
            params={"limit": 2, "offset": 0},
            headers=goldsmith_auth_headers,
        )
        page = resp.json()
        assert page["total"] == 3
        assert len(page["items"]) == 2
        assert page["next_offset"] == 2

    @pytest.mark.asyncio
    async def test_unknown_order_is_404(self, client, goldsmith_auth_headers):
        resp = await client.get(
            "/api/v1/orders/999999/scans", headers=goldsmith_auth_headers
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_repair_scans_and_last_scan(
        self, client, goldsmith_auth_headers, viewer_auth_headers, piece_repair
    ):
        await _log(
            client,
            goldsmith_auth_headers,
            _scan_body(
                "repair", piece_repair.id, action="change_location", location="Tresor"
            ),
        )
        scans = await client.get(
            f"/api/v1/repairs/{piece_repair.id}/scans", headers=viewer_auth_headers
        )
        assert scans.status_code == 200
        assert scans.json()["items"][0]["location"] == "Tresor"

        detail = await client.get(
            f"/api/v1/repairs/{piece_repair.id}", headers=viewer_auth_headers
        )
        assert detail.status_code == 200
        last = detail.json()["last_scan"]
        assert last["user_name"] == "Integration Goldsmith"
        assert last["location"] == "Tresor"
        assert last["action_taken"] == "change_location"
        # VIEWER still gets no financial fields on the detail read.
        assert "estimated_cost" not in detail.json()

    @pytest.mark.asyncio
    async def test_order_detail_carries_last_scan(
        self, client, goldsmith_auth_headers, piece_order
    ):
        detail = await client.get(
            f"/api/v1/orders/{piece_order.id}", headers=goldsmith_auth_headers
        )
        assert detail.json()["last_scan"] is None

        await _log(client, goldsmith_auth_headers, _scan_body("order", piece_order.id))
        detail = await client.get(
            f"/api/v1/orders/{piece_order.id}", headers=goldsmith_auth_headers
        )
        last = detail.json()["last_scan"]
        assert last["user_name"] == "Integration Goldsmith"
        assert last["location"] == "Werkbank 2"
        assert last["action_taken"] == "scan_only"


class TestCrossPieceSearch:
    @pytest.mark.asyncio
    async def test_viewer_is_refused(self, client, viewer_auth_headers):
        resp = await client.get(HISTORY_URL, headers=viewer_auth_headers)
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_search_by_code_number_and_user(
        self,
        client,
        goldsmith_auth_headers,
        admin_auth_headers,
        admin_user,
        piece_order,
        piece_repair,
    ):
        await _log(client, goldsmith_auth_headers, _scan_body("order", piece_order.id))
        await _log(client, admin_auth_headers, _scan_body("repair", piece_repair.id))

        by_code = await client.get(
            HISTORY_URL,
            params={"q": f"ORDER:{piece_order.id}"},
            headers=admin_auth_headers,
        )
        assert by_code.status_code == 200
        rows = by_code.json()["items"]
        assert len(rows) == 1
        assert rows[0]["resolved_type"] == "order"
        assert rows[0]["raw_payload"] == f"ORDER:{piece_order.id}"

        by_number = await client.get(
            HISTORY_URL,
            params={"q": piece_repair.repair_number},
            headers=goldsmith_auth_headers,
        )
        assert [r["resolved_type"] for r in by_number.json()["items"]] == ["repair"]

        by_user = await client.get(
            HISTORY_URL, params={"user": admin_user.id}, headers=goldsmith_auth_headers
        )
        assert {r["user_id"] for r in by_user.json()["items"]} == {admin_user.id}

    @pytest.mark.asyncio
    async def test_time_window_filters_and_validates(
        self, client, goldsmith_auth_headers, piece_order
    ):
        await _log(client, goldsmith_auth_headers, _scan_body("order", piece_order.id))
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()

        none_yet = await client.get(
            HISTORY_URL, params={"from": future}, headers=goldsmith_auth_headers
        )
        assert none_yet.json()["total"] == 0
        window = await client.get(
            HISTORY_URL,
            params={"from": past, "to": future},
            headers=goldsmith_auth_headers,
        )
        assert window.json()["total"] >= 1
        inverted = await client.get(
            HISTORY_URL,
            params={"from": future, "to": past},
            headers=goldsmith_auth_headers,
        )
        assert inverted.status_code == 422


class TestRealtimeHint:
    @pytest.mark.asyncio
    async def test_log_publishes_reduced_scan_updates_hint(
        self, client, goldsmith_auth_headers, piece_order
    ):
        with patch(
            "goldsmith_erp.core.pubsub.publish_event", new=AsyncMock(return_value=True)
        ) as publish:
            row = await _log(
                client, goldsmith_auth_headers, _scan_body("order", piece_order.id)
            )
        scan_calls = [c for c in publish.await_args_list if c.args[0] == "scan_updates"]
        assert len(scan_calls) == 1
        payload = json.loads(scan_calls[0].args[1])
        assert payload["scan_id"] == row["id"]
        assert payload["entity_type"] == "order"
        assert payload["entity_id"] == str(piece_order.id)
        assert "current_location" not in payload and "user_id" not in payload

    def test_ws_route_keeps_only_hint_keys(self):
        raw = json.dumps(
            {
                "action": "scan_logged",
                "scan_id": "x",
                "entity_type": "order",
                "entity_id": "7",
                "action_taken": "scan_only",
                "scanned_at": "2026-09-25T10:00:00+00:00",
                "user_name": "Leak",
                "current_location": "Leak",
            }
        )
        routed = ws_manager.route_event("scan_updates", raw)
        assert routed is not None
        assert routed.user_ids is None
        frame = json.loads(routed.frame)
        assert frame["channel"] == "scan_updates"
        assert "user_name" not in frame["data"]
        assert "current_location" not in frame["data"]
        assert frame["data"]["entity_id"] == "7"


class TestActionSheet:
    """The resolve action list is the scan sheet: only executable actions."""

    SHEET_IDS = {
        "start_timer",
        "stop_timer",
        "switch_timer",
        "punzierung_check",
        "take_photo",
        "change_status",
        "advance_repair",
        "handover",
        "change_location",
        "open_entity",
        "print_label",
        "consume_material",
        "log_only",
    }

    async def _actions(self, client, headers, payload: str) -> list:
        resp = await client.post(
            "/api/v1/scan/resolve", json={"raw_payload": payload}, headers=headers
        )
        assert resp.status_code == 200
        return [a["id"] for a in resp.json()["actions"]]

    @pytest.mark.asyncio
    async def test_goldsmith_order_sheet(
        self, client, goldsmith_auth_headers, piece_order
    ):
        ids = await self._actions(
            client, goldsmith_auth_headers, f"ORDER:{piece_order.id}"
        )
        assert ids[0] == "start_timer"
        assert ids[-1] == "log_only"
        assert {"take_photo", "change_status", "handover", "change_location"} <= set(
            ids
        )
        assert set(ids) <= self.SHEET_IDS

    @pytest.mark.asyncio
    async def test_viewer_order_sheet_has_log_only(
        self, client, viewer_auth_headers, piece_order
    ):
        ids = await self._actions(
            client, viewer_auth_headers, f"ORDER:{piece_order.id}"
        )
        assert "log_only" in ids and "open_entity" in ids
        assert "handover" not in ids and "change_status" not in ids

    @pytest.mark.asyncio
    async def test_repair_sheet(self, client, goldsmith_auth_headers, piece_repair):
        ids = await self._actions(
            client, goldsmith_auth_headers, f"REPAIR:{piece_repair.id}"
        )
        assert ids[0] == "advance_repair"
        assert "change_location" in ids and ids[-1] == "log_only"
        assert "start_timer" not in ids and "repair_diagnosis" not in ids
        assert set(ids) <= self.SHEET_IDS

    @pytest.mark.asyncio
    async def test_unknown_payload_has_no_actions(self, client, goldsmith_auth_headers):
        ids = await self._actions(client, goldsmith_auth_headers, "ALT-0815")
        assert ids == []


class TestWorkshopLocation:
    """W8 ``workshop_locations``: a scan may name its location by id."""

    @pytest_asyncio.fixture
    async def bench(self, db_session: AsyncSession) -> WorkshopLocation:
        location = WorkshopLocation(
            name=f"Werkbank {uuid.uuid4().hex[:4]}", kind="bench", is_active=True
        )
        db_session.add(location)
        await db_session.commit()
        await db_session.refresh(location)
        return location

    @pytest.mark.asyncio
    async def test_location_id_is_resolved_to_its_name(
        self, client, goldsmith_auth_headers, piece_order, bench
    ):
        body = _scan_body("order", piece_order.id, location="veraltet")
        body["context"]["location_id"] = bench.id
        await _log(client, goldsmith_auth_headers, body)
        item = (
            await client.get(
                f"/api/v1/orders/{piece_order.id}/scans", headers=goldsmith_auth_headers
            )
        ).json()["items"][0]
        assert item["location_id"] == bench.id
        assert item["location"] == bench.name

    @pytest.mark.asyncio
    async def test_unknown_location_id_never_loses_the_scan(
        self, client, goldsmith_auth_headers, piece_order
    ):
        body = _scan_body("order", piece_order.id, location="Werkbank 9")
        body["context"]["location_id"] = 987654
        await _log(client, goldsmith_auth_headers, body)
        item = (
            await client.get(
                f"/api/v1/orders/{piece_order.id}/scans", headers=goldsmith_auth_headers
            )
        ).json()["items"][0]
        assert item["location_id"] is None
        assert item["location"] == "Werkbank 9"
