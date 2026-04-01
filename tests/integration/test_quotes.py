"""
Integration tests for the Quotes API (/api/v1/quotes).

Endpoint coverage:
  POST   /api/v1/quotes/              - create quote with line items
  GET    /api/v1/quotes/              - list quotes
  GET    /api/v1/quotes/{id}          - get single quote
  POST   /api/v1/quotes/{id}/send     - mark as SENT
  POST   /api/v1/quotes/{id}/approve  - mark as APPROVED (+ signature)
  POST   /api/v1/quotes/{id}/reject   - mark as REJECTED
  GET    /api/v1/quotes/{id}/pdf      - download PDF

Permission matrix:
  - ADMIN    — full CRUD including QUOTE_DELETE
  - GOLDSMITH — create, view, edit (no delete)
  - VIEWER   — no QUOTE_VIEW, all endpoints return 403
  - No auth  — 401
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import Customer, QuoteLineType, User

QUOTES_URL = "/api/v1/quotes/"


def _quote_url(quote_id: int) -> str:
    return f"{QUOTES_URL}{quote_id}"


def _action_url(quote_id: int, action: str) -> str:
    return f"{QUOTES_URL}{quote_id}/{action}"


# ---------------------------------------------------------------------------
# Payload helpers
# ---------------------------------------------------------------------------

def _create_payload(customer_id: int, with_line_items: bool = True) -> dict:
    payload: dict = {
        "customer_id": customer_id,
        "tax_rate": 19.0,
        "valid_days": 14,
        "notes": "Test quote notes",
    }
    if with_line_items:
        payload["additional_line_items"] = [
            {
                "line_type": QuoteLineType.LABOR.value,
                "description": "Fertigung Ring",
                "quantity": 2.0,
                "unit_price": 75.00,
            },
            {
                "line_type": QuoteLineType.MATERIAL.value,
                "description": "Gold 585 1.5g",
                "quantity": 1.5,
                "unit_price": 40.00,
            },
        ]
    return payload


# ---------------------------------------------------------------------------
# Helper: create a quote and return its ID
# ---------------------------------------------------------------------------

async def _create_quote(
    client: AsyncClient,
    headers: dict,
    customer_id: int,
    with_line_items: bool = True,
) -> int:
    resp = await client.post(
        QUOTES_URL,
        json=_create_payload(customer_id, with_line_items),
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ===========================================================================
# POST /api/v1/quotes/ — create
# ===========================================================================

class TestCreateQuote:

    @pytest.mark.asyncio
    async def test_create_quote_unauthenticated_returns_401(
        self, client: AsyncClient, test_customer: Customer
    ):
        response = await client.post(QUOTES_URL, json=_create_payload(test_customer.id))
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_create_quote_as_admin_returns_201(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        response = await client.post(
            QUOTES_URL,
            json=_create_payload(test_customer.id),
            headers=admin_auth_headers,
        )
        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_create_quote_as_goldsmith_returns_201(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        test_customer: Customer,
    ):
        """GOLDSMITH has QUOTE_CREATE permission."""
        response = await client.post(
            QUOTES_URL,
            json=_create_payload(test_customer.id),
            headers=goldsmith_auth_headers,
        )
        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_create_quote_viewer_returns_403(
        self,
        client: AsyncClient,
        viewer_auth_headers: dict,
        test_customer: Customer,
    ):
        """VIEWER does not have QUOTE_CREATE permission."""
        response = await client.post(
            QUOTES_URL,
            json=_create_payload(test_customer.id),
            headers=viewer_auth_headers,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_create_quote_has_kv_number(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        """Created quote must have a KV-YYYY-NNNN number."""
        response = await client.post(
            QUOTES_URL,
            json=_create_payload(test_customer.id),
            headers=admin_auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert "quote_number" in data
        assert data["quote_number"].startswith("KV-")

    @pytest.mark.asyncio
    async def test_create_quote_initial_status_is_draft(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        """Newly created quotes start in DRAFT status."""
        response = await client.post(
            QUOTES_URL,
            json=_create_payload(test_customer.id),
            headers=admin_auth_headers,
        )
        assert response.status_code == 201
        assert response.json()["status"] == "draft"

    @pytest.mark.asyncio
    async def test_create_quote_with_line_items_calculates_totals(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        """Subtotal, tax, and total are auto-calculated from line items."""
        response = await client.post(
            QUOTES_URL,
            json=_create_payload(test_customer.id, with_line_items=True),
            headers=admin_auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        # 2 x 75 + 1.5 x 40 = 150 + 60 = 210 subtotal
        assert data["subtotal"] == pytest.approx(210.0, abs=0.01)
        assert data["tax_rate"] == 19.0
        assert data["tax_amount"] == pytest.approx(210.0 * 0.19, abs=0.01)
        assert data["total"] == pytest.approx(210.0 * 1.19, abs=0.01)
        assert len(data["line_items"]) == 2

    @pytest.mark.asyncio
    async def test_create_quote_without_line_items(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        """Quote can be created without line items (zero amounts)."""
        response = await client.post(
            QUOTES_URL,
            json=_create_payload(test_customer.id, with_line_items=False),
            headers=admin_auth_headers,
        )
        assert response.status_code == 201
        data = response.json()
        assert data["subtotal"] == 0.0
        assert data["total"] == 0.0


# ===========================================================================
# GET /api/v1/quotes/ — list
# ===========================================================================

class TestListQuotes:

    @pytest.mark.asyncio
    async def test_list_quotes_unauthenticated_returns_401(
        self, client: AsyncClient
    ):
        response = await client.get(QUOTES_URL)
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_list_quotes_returns_paginated_response(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        """List endpoint returns items + total + skip + limit."""
        await _create_quote(client, admin_auth_headers, test_customer.id)

        response = await client.get(QUOTES_URL, headers=admin_auth_headers)
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "skip" in data
        assert "limit" in data

    @pytest.mark.asyncio
    async def test_list_quotes_viewer_returns_403(
        self, client: AsyncClient, viewer_auth_headers: dict
    ):
        """VIEWER does not have QUOTE_VIEW permission."""
        response = await client.get(QUOTES_URL, headers=viewer_auth_headers)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_list_quotes_contains_created_quote(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        """Created quote appears in the list."""
        quote_id = await _create_quote(client, admin_auth_headers, test_customer.id)

        response = await client.get(QUOTES_URL, headers=admin_auth_headers)
        assert response.status_code == 200
        ids = [q["id"] for q in response.json()["items"]]
        assert quote_id in ids


# ===========================================================================
# POST /api/v1/quotes/{id}/send — mark SENT
# ===========================================================================

class TestSendQuote:

    @pytest.mark.asyncio
    async def test_send_quote_transitions_to_sent(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        quote_id = await _create_quote(client, admin_auth_headers, test_customer.id)

        resp = await client.post(_action_url(quote_id, "send"), headers=admin_auth_headers)
        assert resp.status_code == 200
        assert resp.json()["status"] == "sent"

    @pytest.mark.asyncio
    async def test_send_nonexistent_quote_returns_404(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        resp = await client.post(_action_url(99999, "send"), headers=admin_auth_headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_send_quote_unauthenticated_returns_401(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        quote_id = await _create_quote(client, admin_auth_headers, test_customer.id)
        resp = await client.post(_action_url(quote_id, "send"))
        assert resp.status_code == 401


# ===========================================================================
# POST /api/v1/quotes/{id}/approve — mark APPROVED
# ===========================================================================

class TestApproveQuote:

    async def _create_sent_quote(
        self,
        client: AsyncClient,
        headers: dict,
        customer_id: int,
    ) -> int:
        """Helper: create a DRAFT quote and transition it to SENT."""
        quote_id = await _create_quote(client, headers, customer_id)
        resp = await client.post(_action_url(quote_id, "send"), headers=headers)
        assert resp.status_code == 200
        return quote_id

    @pytest.mark.asyncio
    async def test_approve_quote_transitions_to_approved(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        quote_id = await self._create_sent_quote(
            client, admin_auth_headers, test_customer.id
        )

        resp = await client.post(
            _action_url(quote_id, "approve"),
            json={"signature_data": None},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "approved"

    @pytest.mark.asyncio
    async def test_approve_quote_with_signature(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        """Customer signature (base64 PNG stub) is stored on approval."""
        quote_id = await self._create_sent_quote(
            client, admin_auth_headers, test_customer.id
        )

        fake_sig = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
        resp = await client.post(
            _action_url(quote_id, "approve"),
            json={"signature_data": fake_sig},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "approved"
        assert data["customer_signature_data"] == fake_sig

    @pytest.mark.asyncio
    async def test_approve_nonexistent_quote_returns_404(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        resp = await client.post(
            _action_url(99999, "approve"),
            json={},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 404


# ===========================================================================
# POST /api/v1/quotes/{id}/reject — mark REJECTED
# ===========================================================================

class TestRejectQuote:

    @pytest.mark.asyncio
    async def test_reject_draft_quote(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        """DRAFT quote can be rejected."""
        quote_id = await _create_quote(client, admin_auth_headers, test_customer.id)

        resp = await client.post(
            _action_url(quote_id, "reject"),
            json={"reason": "Preis zu hoch"},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"

    @pytest.mark.asyncio
    async def test_reject_sent_quote(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        """SENT quote can also be rejected."""
        quote_id = await _create_quote(client, admin_auth_headers, test_customer.id)
        await client.post(_action_url(quote_id, "send"), headers=admin_auth_headers)

        resp = await client.post(
            _action_url(quote_id, "reject"),
            json={"reason": "Kunde hat sich umentschieden"},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"

    @pytest.mark.asyncio
    async def test_reject_quote_without_reason(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        """Rejection reason is optional."""
        quote_id = await _create_quote(client, admin_auth_headers, test_customer.id)
        resp = await client.post(
            _action_url(quote_id, "reject"),
            json={},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "rejected"

    @pytest.mark.asyncio
    async def test_reject_nonexistent_quote_returns_404(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        resp = await client.post(
            _action_url(99999, "reject"),
            json={},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 404


# ===========================================================================
# GET /api/v1/quotes/{id}/pdf — download PDF
# ===========================================================================

class TestQuotePdf:

    @pytest.mark.asyncio
    async def test_pdf_download_unauthenticated_returns_401(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        quote_id = await _create_quote(client, admin_auth_headers, test_customer.id)
        resp = await client.get(_action_url(quote_id, "pdf"))
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_pdf_download_returns_pdf_content_type(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        """PDF endpoint must return application/pdf content-type."""
        quote_id = await _create_quote(client, admin_auth_headers, test_customer.id)

        resp = await client.get(_action_url(quote_id, "pdf"), headers=admin_auth_headers)
        assert resp.status_code == 200
        assert "application/pdf" in resp.headers.get("content-type", "")

    @pytest.mark.asyncio
    async def test_pdf_download_nonexistent_quote_returns_404(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        resp = await client.get(_action_url(99999, "pdf"), headers=admin_auth_headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_pdf_viewer_returns_403(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        viewer_auth_headers: dict,
        test_customer: Customer,
    ):
        """VIEWER has no QUOTE_VIEW permission, PDF must be denied."""
        quote_id = await _create_quote(client, admin_auth_headers, test_customer.id)
        resp = await client.get(_action_url(quote_id, "pdf"), headers=viewer_auth_headers)
        assert resp.status_code == 403
