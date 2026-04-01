"""
Integration tests for the Hallmarking API (/api/v1/orders/{order_id}/hallmarks).

Endpoint coverage:
  POST   /api/v1/orders/{order_id}/hallmarks                      - create hallmark
  GET    /api/v1/orders/{order_id}/hallmarks                      - list hallmarks
  GET    /api/v1/orders/{order_id}/hallmarks/{hallmark_id}        - get single
  POST   /api/v1/orders/{order_id}/hallmarks/{hallmark_id}/status - transition status

Status transitions tested:
  PENDING -> SUBMITTED (valid)
  SUBMITTED -> APPROVED (valid)
  APPROVED -> STAMPED (valid)
  PENDING -> APPROVED (invalid — skip)
  PENDING -> STAMPED (invalid — skip)

Permission matrix:
  - ADMIN / GOLDSMITH — full CRUD via HALLMARK_CREATE + HALLMARK_EDIT
  - VIEWER            — read-only (HALLMARK_VIEW), write returns 403
  - No auth           — 401
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import (
    Customer,
    HallmarkType,
    HallmarkStatus,
    Order,
    OrderStatusEnum,
    User,
)

API_BASE = "/api/v1"


def _hallmarks_url(order_id: int) -> str:
    return f"{API_BASE}/orders/{order_id}/hallmarks"


def _hallmark_url(order_id: int, hallmark_id: int) -> str:
    return f"{API_BASE}/orders/{order_id}/hallmarks/{hallmark_id}"


def _status_url(order_id: int, hallmark_id: int) -> str:
    return f"{API_BASE}/orders/{order_id}/hallmarks/{hallmark_id}/status"


# ---------------------------------------------------------------------------
# Payload helpers
# ---------------------------------------------------------------------------

def _create_payload(
    hallmark_type: str = HallmarkType.FINENESS_MARK.value,
    assay_office: str | None = "Pforzheim",
) -> dict:
    return {
        "hallmark_type": hallmark_type,
        "assay_office": assay_office,
        "notes": "Test hallmark record",
    }


def _status_payload(new_status: str, certificate_number: str | None = None) -> dict:
    payload: dict = {"new_status": new_status}
    if certificate_number:
        payload["certificate_number"] = certificate_number
    return payload


# ---------------------------------------------------------------------------
# DB fixture: order for hallmark tests
# ---------------------------------------------------------------------------

async def _create_order(db_session: AsyncSession, customer: Customer) -> Order:
    """Insert a minimal order into the DB for hallmark tests."""
    order = Order(
        title="Hallmark Test Order",
        description="Order for hallmark integration tests",
        customer_id=customer.id,
        status=OrderStatusEnum.IN_PROGRESS,
        is_deleted=False,
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)
    return order


# ---------------------------------------------------------------------------
# Helper: create a hallmark and return its ID
# ---------------------------------------------------------------------------

async def _create_hallmark(
    client: AsyncClient,
    headers: dict,
    order_id: int,
    hallmark_type: str = HallmarkType.FINENESS_MARK.value,
) -> int:
    resp = await client.post(
        _hallmarks_url(order_id),
        json=_create_payload(hallmark_type=hallmark_type),
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ===========================================================================
# POST /api/v1/orders/{order_id}/hallmarks — create
# ===========================================================================

class TestCreateHallmark:

    @pytest.mark.asyncio
    async def test_create_hallmark_unauthenticated_returns_401(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_customer: Customer,
    ):
        order = await _create_order(db_session, test_customer)
        resp = await client.post(_hallmarks_url(order.id), json=_create_payload())
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_create_hallmark_as_admin_returns_201(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        order = await _create_order(db_session, test_customer)
        resp = await client.post(
            _hallmarks_url(order.id),
            json=_create_payload(),
            headers=admin_auth_headers,
        )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_create_hallmark_as_goldsmith_returns_201(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        goldsmith_auth_headers: dict,
        test_customer: Customer,
    ):
        """GOLDSMITH has HALLMARK_CREATE permission."""
        order = await _create_order(db_session, test_customer)
        resp = await client.post(
            _hallmarks_url(order.id),
            json=_create_payload(),
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_create_hallmark_viewer_returns_403(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        viewer_auth_headers: dict,
        test_customer: Customer,
    ):
        """VIEWER has HALLMARK_VIEW only, not HALLMARK_CREATE."""
        order = await _create_order(db_session, test_customer)
        resp = await client.post(
            _hallmarks_url(order.id),
            json=_create_payload(),
            headers=viewer_auth_headers,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_create_hallmark_initial_status_is_pending(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        """New hallmarks always start in PENDING status."""
        order = await _create_order(db_session, test_customer)
        resp = await client.post(
            _hallmarks_url(order.id),
            json=_create_payload(),
            headers=admin_auth_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["status"] == "pending"

    @pytest.mark.asyncio
    async def test_create_hallmark_stores_type_and_assay_office(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        order = await _create_order(db_session, test_customer)
        resp = await client.post(
            _hallmarks_url(order.id),
            json=_create_payload(
                hallmark_type=HallmarkType.MAKERS_MARK.value,
                assay_office="Schwaebisch Gmuend",
            ),
            headers=admin_auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["hallmark_type"] == "makers_mark"
        assert data["assay_office"] == "Schwaebisch Gmuend"

    @pytest.mark.asyncio
    async def test_create_hallmark_nonexistent_order_returns_404(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
    ):
        """Creating a hallmark on a non-existent order returns 404."""
        resp = await client.post(
            _hallmarks_url(99999),
            json=_create_payload(),
            headers=admin_auth_headers,
        )
        assert resp.status_code == 404


# ===========================================================================
# GET /api/v1/orders/{order_id}/hallmarks — list
# ===========================================================================

class TestListHallmarks:

    @pytest.mark.asyncio
    async def test_list_hallmarks_unauthenticated_returns_401(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_customer: Customer,
    ):
        order = await _create_order(db_session, test_customer)
        resp = await client.get(_hallmarks_url(order.id))
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_list_hallmarks_viewer_can_list(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        viewer_auth_headers: dict,
        test_customer: Customer,
    ):
        """VIEWER has HALLMARK_VIEW permission for read access."""
        order = await _create_order(db_session, test_customer)
        resp = await client.get(_hallmarks_url(order.id), headers=viewer_auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_list_hallmarks_contains_created_hallmark(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        order = await _create_order(db_session, test_customer)
        hallmark_id = await _create_hallmark(client, admin_auth_headers, order.id)

        resp = await client.get(_hallmarks_url(order.id), headers=admin_auth_headers)
        assert resp.status_code == 200
        ids = [h["id"] for h in resp.json()]
        assert hallmark_id in ids


# ===========================================================================
# POST .../status — status transitions
# ===========================================================================

class TestHallmarkStatusTransitions:

    async def _advance_to(
        self,
        client: AsyncClient,
        headers: dict,
        order_id: int,
        target_status: str,
    ) -> int:
        """
        Create a PENDING hallmark and advance it step by step to target_status.
        Returns the hallmark ID.
        """
        hallmark_id = await _create_hallmark(client, headers, order_id)

        transitions = {
            "submitted": [("submitted", None)],
            "approved": [("submitted", None), ("approved", "CERT-001")],
            "stamped": [("submitted", None), ("approved", "CERT-002"), ("stamped", None)],
        }

        for step_status, cert in transitions.get(target_status, []):
            resp = await client.post(
                _status_url(order_id, hallmark_id),
                json=_status_payload(step_status, cert),
                headers=headers,
            )
            assert resp.status_code == 200, f"Failed at {step_status}: {resp.text}"

        return hallmark_id

    @pytest.mark.asyncio
    async def test_pending_to_submitted(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        """PENDING -> SUBMITTED is a valid transition."""
        order = await _create_order(db_session, test_customer)
        hallmark_id = await _create_hallmark(client, admin_auth_headers, order.id)

        resp = await client.post(
            _status_url(order.id, hallmark_id),
            json=_status_payload("submitted"),
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "submitted"

    @pytest.mark.asyncio
    async def test_submitted_to_approved(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        """SUBMITTED -> APPROVED is a valid transition."""
        order = await _create_order(db_session, test_customer)
        hallmark_id = await self._advance_to(
            client, admin_auth_headers, order.id, "submitted"
        )

        resp = await client.post(
            _status_url(order.id, hallmark_id),
            json=_status_payload("approved", certificate_number="CERT-2026-0001"),
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

    @pytest.mark.asyncio
    async def test_approved_to_stamped(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        """APPROVED -> STAMPED is a valid transition."""
        order = await _create_order(db_session, test_customer)
        hallmark_id = await self._advance_to(
            client, admin_auth_headers, order.id, "approved"
        )

        resp = await client.post(
            _status_url(order.id, hallmark_id),
            json=_status_payload("stamped"),
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "stamped"

    @pytest.mark.asyncio
    async def test_pending_to_approved_is_invalid(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        """Skipping SUBMITTED -> going PENDING -> APPROVED is not allowed."""
        order = await _create_order(db_session, test_customer)
        hallmark_id = await _create_hallmark(client, admin_auth_headers, order.id)

        resp = await client.post(
            _status_url(order.id, hallmark_id),
            json=_status_payload("approved"),
            headers=admin_auth_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_pending_to_stamped_is_invalid(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        """Skipping multiple steps PENDING -> STAMPED is not allowed."""
        order = await _create_order(db_session, test_customer)
        hallmark_id = await _create_hallmark(client, admin_auth_headers, order.id)

        resp = await client.post(
            _status_url(order.id, hallmark_id),
            json=_status_payload("stamped"),
            headers=admin_auth_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_viewer_cannot_change_status(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict,
        viewer_auth_headers: dict,
        test_customer: Customer,
    ):
        """VIEWER lacks HALLMARK_EDIT permission."""
        order = await _create_order(db_session, test_customer)
        hallmark_id = await _create_hallmark(client, admin_auth_headers, order.id)

        resp = await client.post(
            _status_url(order.id, hallmark_id),
            json=_status_payload("submitted"),
            headers=viewer_auth_headers,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_status_transition_unauthenticated_returns_401(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        order = await _create_order(db_session, test_customer)
        hallmark_id = await _create_hallmark(client, admin_auth_headers, order.id)

        resp = await client.post(
            _status_url(order.id, hallmark_id),
            json=_status_payload("submitted"),
        )
        assert resp.status_code == 401
