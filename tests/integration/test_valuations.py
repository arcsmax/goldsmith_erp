"""
Integration tests for the Valuation Certificate API (/api/v1/valuations).

Endpoint coverage:
  POST /api/v1/valuations                       - create certificate (manual)
  GET  /api/v1/valuations                       - list certificates
  GET  /api/v1/valuations/{id}                  - certificate detail
  GET  /api/v1/valuations/{id}/pdf              - download PDF
  POST /api/v1/orders/{order_id}/valuations     - create from order (auto-fill)

Permission matrix:
  - ADMIN / GOLDSMITH — full access (VALUATION_CREATE + VALUATION_VIEW)
  - VIEWER            — no access (no VALUATION_VIEW), all returns 403
  - No auth           — 401
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import (
    Customer,
    Order,
    OrderStatusEnum,
    User,
)

API_BASE = "/api/v1"
VALUATIONS_URL = f"{API_BASE}/valuations"


def _valuation_url(cert_id: int) -> str:
    return f"{VALUATIONS_URL}/{cert_id}"


def _pdf_url(cert_id: int) -> str:
    return f"{VALUATIONS_URL}/{cert_id}/pdf"


def _from_order_url(order_id: int) -> str:
    return f"{API_BASE}/orders/{order_id}/valuations"


# ---------------------------------------------------------------------------
# Payload helpers
# ---------------------------------------------------------------------------

def _create_payload(order_id: int, customer_id: int) -> dict:
    return {
        "order_id": order_id,
        "customer_id": customer_id,
        "item_description": "Brillantring 750 Gelbgold, 1 Brillant 0.50ct IF/D",
        "metal_type": "Gelbgold 750 (18K)",
        "metal_weight_g": 4.8,
        "metal_purity": "750",
        "gemstones_description": "1 Brillant ca. 0.50ct, Reinheit IF, Farbe D",
        "appraised_value": 3500.00,
        "goldsmith_name": "Maria Goldschmied",
        "goldsmith_qualification": "Goldschmiedemeisterin",
    }


def _from_order_payload() -> dict:
    return {
        "appraised_value": 2800.00,
        "goldsmith_name": "Hans Meister",
        "goldsmith_qualification": "Goldschmiedemeister",
    }


# ---------------------------------------------------------------------------
# DB fixture: order for valuation tests
# ---------------------------------------------------------------------------

async def _create_order(db_session: AsyncSession, customer: Customer) -> Order:
    """Insert a minimal order for valuation tests."""
    order = Order(
        title="Valuation Test Order",
        description="Order used for valuation certificate tests",
        customer_id=customer.id,
        status=OrderStatusEnum.COMPLETED,
        actual_weight_g=4.8,
        alloy="750",
        is_deleted=False,
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)
    return order


# ---------------------------------------------------------------------------
# Helper: create a valuation certificate and return its ID
# ---------------------------------------------------------------------------

async def _create_valuation(
    client: AsyncClient,
    headers: dict,
    order_id: int,
    customer_id: int,
) -> int:
    resp = await client.post(
        VALUATIONS_URL,
        json=_create_payload(order_id, customer_id),
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ===========================================================================
# POST /api/v1/valuations — create certificate
# ===========================================================================

class TestCreateValuation:

    @pytest.mark.asyncio
    async def test_create_valuation_unauthenticated_returns_401(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_customer: Customer,
    ):
        order = await _create_order(db_session, test_customer)
        resp = await client.post(
            VALUATIONS_URL,
            json=_create_payload(order.id, test_customer.id),
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_create_valuation_as_admin_returns_201(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        order = await _create_order(db_session, test_customer)
        resp = await client.post(
            VALUATIONS_URL,
            json=_create_payload(order.id, test_customer.id),
            headers=admin_auth_headers,
        )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_create_valuation_as_goldsmith_returns_201(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        goldsmith_auth_headers: dict,
        test_customer: Customer,
    ):
        """GOLDSMITH has VALUATION_CREATE permission."""
        order = await _create_order(db_session, test_customer)
        resp = await client.post(
            VALUATIONS_URL,
            json=_create_payload(order.id, test_customer.id),
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_create_valuation_viewer_returns_403(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        viewer_auth_headers: dict,
        test_customer: Customer,
    ):
        """VIEWER has no VALUATION_CREATE permission."""
        order = await _create_order(db_session, test_customer)
        resp = await client.post(
            VALUATIONS_URL,
            json=_create_payload(order.id, test_customer.id),
            headers=viewer_auth_headers,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_create_valuation_has_wg_certificate_number(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        """Created certificate must have a WG-YYYY-NNNN number."""
        order = await _create_order(db_session, test_customer)
        resp = await client.post(
            VALUATIONS_URL,
            json=_create_payload(order.id, test_customer.id),
            headers=admin_auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert "certificate_number" in data
        assert data["certificate_number"].startswith("WG-")
        parts = data["certificate_number"].split("-")
        assert len(parts) == 3
        assert parts[0] == "WG"
        assert len(parts[1]) == 4 and parts[1].isdigit()
        assert len(parts[2]) == 4 and parts[2].isdigit()

    @pytest.mark.asyncio
    async def test_create_valuation_stores_appraised_value(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        """Appraised value must be stored exactly as provided."""
        order = await _create_order(db_session, test_customer)
        resp = await client.post(
            VALUATIONS_URL,
            json=_create_payload(order.id, test_customer.id),
            headers=admin_auth_headers,
        )
        assert resp.status_code == 201
        assert resp.json()["appraised_value"] == pytest.approx(3500.00, abs=0.01)

    @pytest.mark.asyncio
    async def test_create_valuation_has_validity_dates(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        """Certificate must have valuation_date and valid_until (2 years)."""
        order = await _create_order(db_session, test_customer)
        resp = await client.post(
            VALUATIONS_URL,
            json=_create_payload(order.id, test_customer.id),
            headers=admin_auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["valuation_date"]
        assert data["valid_until"]
        # valid_until must be later than valuation_date
        assert data["valid_until"] > data["valuation_date"]


# ===========================================================================
# POST /api/v1/orders/{order_id}/valuations — create from order
# ===========================================================================

class TestCreateValuationFromOrder:

    @pytest.mark.asyncio
    async def test_create_from_order_returns_201(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        """Auto-fill endpoint creates a certificate from order data."""
        order = await _create_order(db_session, test_customer)

        resp = await client.post(
            _from_order_url(order.id),
            json=_from_order_payload(),
            headers=admin_auth_headers,
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["order_id"] == order.id
        assert "certificate_number" in data

    @pytest.mark.asyncio
    async def test_create_from_order_as_goldsmith_returns_201(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        goldsmith_auth_headers: dict,
        test_customer: Customer,
    ):
        order = await _create_order(db_session, test_customer)

        resp = await client.post(
            _from_order_url(order.id),
            json=_from_order_payload(),
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 201

    @pytest.mark.asyncio
    async def test_create_from_nonexistent_order_returns_422(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
    ):
        """Service raises ValueError for a non-existent order -> 422."""
        resp = await client.post(
            _from_order_url(99999),
            json=_from_order_payload(),
            headers=admin_auth_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_from_order_unauthenticated_returns_401(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        order = await _create_order(db_session, test_customer)
        resp = await client.post(
            _from_order_url(order.id),
            json=_from_order_payload(),
        )
        assert resp.status_code == 401


# ===========================================================================
# GET /api/v1/valuations — list
# ===========================================================================

class TestListValuations:

    @pytest.mark.asyncio
    async def test_list_valuations_unauthenticated_returns_401(
        self, client: AsyncClient
    ):
        resp = await client.get(VALUATIONS_URL)
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_list_valuations_viewer_returns_403(
        self, client: AsyncClient, viewer_auth_headers: dict
    ):
        """VIEWER has no VALUATION_VIEW permission."""
        resp = await client.get(VALUATIONS_URL, headers=viewer_auth_headers)
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_list_valuations_returns_list(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        resp = await client.get(VALUATIONS_URL, headers=admin_auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_list_valuations_contains_created_certificate(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        order = await _create_order(db_session, test_customer)
        cert_id = await _create_valuation(
            client, admin_auth_headers, order.id, test_customer.id
        )

        resp = await client.get(VALUATIONS_URL, headers=admin_auth_headers)
        assert resp.status_code == 200
        ids = [c["id"] for c in resp.json()]
        assert cert_id in ids


# ===========================================================================
# GET /api/v1/valuations/{id}/pdf — download PDF
# ===========================================================================

class TestValuationPdf:

    @pytest.mark.asyncio
    async def test_pdf_unauthenticated_returns_401(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        order = await _create_order(db_session, test_customer)
        cert_id = await _create_valuation(
            client, admin_auth_headers, order.id, test_customer.id
        )
        resp = await client.get(_pdf_url(cert_id))
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_pdf_returns_application_pdf_content_type(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        """PDF endpoint must return application/pdf content-type."""
        order = await _create_order(db_session, test_customer)
        cert_id = await _create_valuation(
            client, admin_auth_headers, order.id, test_customer.id
        )

        resp = await client.get(_pdf_url(cert_id), headers=admin_auth_headers)
        assert resp.status_code == 200
        assert "application/pdf" in resp.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_pdf_nonexistent_certificate_returns_404(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        resp = await client.get(_pdf_url(99999), headers=admin_auth_headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_pdf_viewer_returns_403(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict,
        viewer_auth_headers: dict,
        test_customer: Customer,
    ):
        """VIEWER has no VALUATION_VIEW permission, PDF must be denied."""
        order = await _create_order(db_session, test_customer)
        cert_id = await _create_valuation(
            client, admin_auth_headers, order.id, test_customer.id
        )
        resp = await client.get(_pdf_url(cert_id), headers=viewer_auth_headers)
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_pdf_goldsmith_can_download(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict,
        goldsmith_auth_headers: dict,
        test_customer: Customer,
    ):
        """GOLDSMITH has VALUATION_VIEW and can download PDFs."""
        order = await _create_order(db_session, test_customer)
        cert_id = await _create_valuation(
            client, admin_auth_headers, order.id, test_customer.id
        )

        resp = await client.get(_pdf_url(cert_id), headers=goldsmith_auth_headers)
        assert resp.status_code == 200
        assert "application/pdf" in resp.headers.get("content-type", "")
