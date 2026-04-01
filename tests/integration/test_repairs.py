"""
Integration tests for the Repair Tracking API (/api/v1/repairs).

Endpoint coverage:
  POST   /api/v1/repairs/                    - create repair intake
  GET    /api/v1/repairs/                    - list repairs
  GET    /api/v1/repairs/{id}                - get single repair
  POST   /api/v1/repairs/{id}/diagnose       - diagnose and cost estimate
  POST   /api/v1/repairs/{id}/approve        - customer approval
  POST   /api/v1/repairs/{id}/start          - begin repair work
  POST   /api/v1/repairs/{id}/quality-check  - submit for quality check
  POST   /api/v1/repairs/{id}/complete       - mark ready for pickup
  POST   /api/v1/repairs/{id}/pickup         - confirm pickup

Permission matrix:
  - ADMIN / GOLDSMITH  — full create + edit workflow
  - VIEWER             — REPAIR_VIEW (list, get) only
  - No auth            — 401
"""
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import Customer, RepairItemType, User

REPAIRS_URL = "/api/v1/repairs/"


def _repair_url(repair_id: int) -> str:
    return f"{REPAIRS_URL}{repair_id}"


def _action_url(repair_id: int, action: str) -> str:
    return f"{REPAIRS_URL}{repair_id}/{action}"


# ---------------------------------------------------------------------------
# Payload helpers
# ---------------------------------------------------------------------------

def _create_payload(customer_id: int | None = None) -> dict:
    payload: dict = {
        "item_description": "Ehering Gelbgold 585 — Stein locker",
        "item_type": RepairItemType.RING.value,
        "metal_type": "585 Gelbgold",
    }
    if customer_id is not None:
        payload["customer_id"] = customer_id
    return payload


def _diagnose_payload() -> dict:
    return {
        "diagnosis_notes": "Krappenfassung gebrochen, Stein lose",
        "estimated_cost": 85.00,
    }


def _complete_payload() -> dict:
    return {
        "actual_cost": 80.00,
        "notes": "Krappen erneuert, Stein gesetzt",
    }


# ---------------------------------------------------------------------------
# Helper: create a repair and return its ID
# ---------------------------------------------------------------------------

async def _create_repair(client: AsyncClient, headers: dict, customer_id: int | None = None) -> int:
    resp = await client.post(REPAIRS_URL, json=_create_payload(customer_id), headers=headers)
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ===========================================================================
# POST /api/v1/repairs/ — create
# ===========================================================================

class TestCreateRepair:

    @pytest.mark.asyncio
    async def test_create_repair_unauthenticated_returns_401(
        self, client: AsyncClient
    ):
        """Deny-by-default middleware blocks unauthenticated requests."""
        response = await client.post(REPAIRS_URL, json=_create_payload())
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_repair_as_admin_returns_201(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        """ADMIN can create a new repair intake."""
        response = await client.post(REPAIRS_URL, json=_create_payload(), headers=admin_auth_headers)
        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_create_repair_as_goldsmith_returns_201(
        self, client: AsyncClient, goldsmith_auth_headers: dict
    ):
        """GOLDSMITH has REPAIR_CREATE permission."""
        response = await client.post(REPAIRS_URL, json=_create_payload(), headers=goldsmith_auth_headers)
        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_create_repair_response_has_rep_number(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        """Created repair must have a REP-YYYY-NNNN number and correct initial status."""
        response = await client.post(REPAIRS_URL, json=_create_payload(), headers=admin_auth_headers)
        assert response.status_code == 201
        data = response.json()

        assert "repair_number" in data
        assert data["repair_number"].startswith("REP-")
        # Format: REP-YYYY-NNNN
        parts = data["repair_number"].split("-")
        assert len(parts) == 3
        assert parts[0] == "REP"
        assert len(parts[1]) == 4 and parts[1].isdigit()
        assert len(parts[2]) == 4 and parts[2].isdigit()

    @pytest.mark.asyncio
    async def test_create_repair_has_bag_number(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        """Created repair must have an auto-generated bag number."""
        response = await client.post(REPAIRS_URL, json=_create_payload(), headers=admin_auth_headers)
        assert response.status_code == 201
        data = response.json()
        assert "bag_number" in data
        assert data["bag_number"]  # non-empty

    @pytest.mark.asyncio
    async def test_create_repair_initial_status_is_received(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        """Initial status must always be RECEIVED."""
        response = await client.post(REPAIRS_URL, json=_create_payload(), headers=admin_auth_headers)
        assert response.status_code == 201
        assert response.json()["status"] == "received"

    @pytest.mark.asyncio
    async def test_create_repair_with_customer(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        """Creating repair with a customer_id links customer correctly."""
        payload = _create_payload(customer_id=test_customer.id)
        response = await client.post(REPAIRS_URL, json=payload, headers=admin_auth_headers)
        assert response.status_code == 201
        data = response.json()
        assert data["customer_id"] == test_customer.id

    @pytest.mark.asyncio
    async def test_create_repair_viewer_returns_403(
        self, client: AsyncClient, viewer_auth_headers: dict
    ):
        """VIEWER does not have REPAIR_CREATE permission."""
        response = await client.post(REPAIRS_URL, json=_create_payload(), headers=viewer_auth_headers)
        assert response.status_code == 403


# ===========================================================================
# GET /api/v1/repairs/ — list
# ===========================================================================

class TestListRepairs:

    @pytest.mark.asyncio
    async def test_list_repairs_unauthenticated_returns_401(
        self, client: AsyncClient
    ):
        response = await client.get(REPAIRS_URL)
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_list_repairs_returns_list(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        """Authenticated request returns a JSON list."""
        response = await client.get(REPAIRS_URL, headers=admin_auth_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    @pytest.mark.asyncio
    async def test_list_repairs_viewer_can_list(
        self, client: AsyncClient, viewer_auth_headers: dict
    ):
        """VIEWER has REPAIR_VIEW permission."""
        response = await client.get(REPAIRS_URL, headers=viewer_auth_headers)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_repairs_contains_created_repair(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        """A newly created repair appears in the list."""
        repair_id = await _create_repair(client, admin_auth_headers)

        resp = await client.get(REPAIRS_URL, headers=admin_auth_headers)
        assert resp.status_code == 200
        ids = [r["id"] for r in resp.json()]
        assert repair_id in ids


# ===========================================================================
# POST /api/v1/repairs/{id}/diagnose — diagnose
# ===========================================================================

class TestDiagnoseRepair:

    @pytest.mark.asyncio
    async def test_diagnose_repair_sets_status(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        """
        Calling /diagnose on a RECEIVED repair transitions through
        DIAGNOSED to QUOTED (the service does both steps in one call).
        """
        repair_id = await _create_repair(client, admin_auth_headers)

        resp = await client.post(
            _action_url(repair_id, "diagnose"),
            json=_diagnose_payload(),
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        # The diagnose endpoint transitions to QUOTED (via DIAGNOSED)
        assert data["status"] in ("diagnosed", "quoted")

    @pytest.mark.asyncio
    async def test_diagnose_repair_stores_cost(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        """Estimated cost from the diagnose payload is stored on the repair."""
        repair_id = await _create_repair(client, admin_auth_headers)

        resp = await client.post(
            _action_url(repair_id, "diagnose"),
            json=_diagnose_payload(),
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["estimated_cost"] == 85.00

    @pytest.mark.asyncio
    async def test_diagnose_nonexistent_repair_returns_404(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        resp = await client.post(
            _action_url(99999, "diagnose"),
            json=_diagnose_payload(),
            headers=admin_auth_headers,
        )
        assert resp.status_code in (404, 422)

    @pytest.mark.asyncio
    async def test_diagnose_unauthenticated_returns_401(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        repair_id = await _create_repair(client, admin_auth_headers)
        resp = await client.post(
            _action_url(repair_id, "diagnose"),
            json=_diagnose_payload(),
        )
        assert resp.status_code == 401


# ===========================================================================
# Status transition: full happy path
# RECEIVED -> DIAGNOSED/QUOTED -> APPROVED -> IN_REPAIR -> QUALITY_CHECK
#          -> READY -> PICKED_UP
# ===========================================================================

class TestStatusTransitions:

    async def _advance_to_approved(
        self, client: AsyncClient, headers: dict
    ) -> int:
        """Create a repair and advance it to APPROVED status."""
        repair_id = await _create_repair(client, headers)

        # Diagnose (-> QUOTED)
        resp = await client.post(
            _action_url(repair_id, "diagnose"),
            json=_diagnose_payload(),
            headers=headers,
        )
        assert resp.status_code == 200

        # Approve (-> APPROVED)
        resp = await client.post(
            _action_url(repair_id, "approve"),
            json={},
            headers=headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"
        return repair_id

    @pytest.mark.asyncio
    async def test_full_lifecycle_received_to_picked_up(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        """Walk the happy path from RECEIVED to PICKED_UP."""
        repair_id = await self._advance_to_approved(client, admin_auth_headers)

        # Start repair (APPROVED -> IN_REPAIR)
        resp = await client.post(_action_url(repair_id, "start"), headers=admin_auth_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "in_repair"

        # Quality check (IN_REPAIR -> QUALITY_CHECK)
        resp = await client.post(_action_url(repair_id, "quality-check"), headers=admin_auth_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "quality_check"

        # Complete (QUALITY_CHECK -> READY)
        resp = await client.post(
            _action_url(repair_id, "complete"),
            json=_complete_payload(),
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ready"

        # Pickup (READY -> PICKED_UP)
        resp = await client.post(_action_url(repair_id, "pickup"), headers=admin_auth_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "picked_up"

    @pytest.mark.asyncio
    async def test_invalid_transition_skipping_stages_returns_422(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        """
        Attempting to start a repair that is still RECEIVED (not APPROVED)
        must be rejected with 422.
        """
        repair_id = await _create_repair(client, admin_auth_headers)

        # Skipping diagnose + approve and trying to start directly
        resp = await client.post(_action_url(repair_id, "start"), headers=admin_auth_headers)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_approve_from_received_returns_422(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        """RECEIVED -> APPROVED is an invalid skip; service raises ValueError -> 422."""
        repair_id = await _create_repair(client, admin_auth_headers)

        resp = await client.post(
            _action_url(repair_id, "approve"),
            json={},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_pickup_from_received_returns_422(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        """RECEIVED -> PICKED_UP is an invalid skip."""
        repair_id = await _create_repair(client, admin_auth_headers)

        resp = await client.post(_action_url(repair_id, "pickup"), headers=admin_auth_headers)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_viewer_cannot_approve_returns_403(
        self, client: AsyncClient, admin_auth_headers: dict, viewer_auth_headers: dict
    ):
        """VIEWER lacks REPAIR_EDIT; any write action must return 403."""
        repair_id = await _create_repair(client, admin_auth_headers)

        resp = await client.post(
            _action_url(repair_id, "diagnose"),
            json=_diagnose_payload(),
            headers=viewer_auth_headers,
        )
        assert resp.status_code == 403
