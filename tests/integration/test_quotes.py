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
    async def test_list_quotes_unauthenticated_returns_401(self, client: AsyncClient):
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

        resp = await client.post(
            _action_url(quote_id, "send"), headers=admin_auth_headers
        )
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

        resp = await client.get(
            _action_url(quote_id, "pdf"), headers=admin_auth_headers
        )
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
        resp = await client.get(
            _action_url(quote_id, "pdf"), headers=viewer_auth_headers
        )
        assert resp.status_code == 403


# ===========================================================================
# Line-item CRUD (editable-quotes plan, Task 1)
# ===========================================================================


def _line_items_url(quote_id: int, item_id: int | None = None) -> str:
    base = f"{_quote_url(quote_id)}/line-items"
    return f"{base}/{item_id}" if item_id is not None else base


def _line_item_payload(
    quantity: float = 1.0, unit_price: float = 10.0, description: str = "Position"
) -> dict:
    return {
        "line_type": QuoteLineType.OTHER.value,
        "description": description,
        "quantity": quantity,
        "unit_price": unit_price,
    }


class TestAddQuoteLineItem:

    @pytest.mark.asyncio
    async def test_add_line_item_as_admin_recomputes_totals(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        """Quote fixture starts with subtotal 210 (see _create_payload).
        Adding a 100 EUR line item must recompute subtotal/tax/total."""
        quote_id = await _create_quote(client, admin_auth_headers, test_customer.id)

        resp = await client.post(
            _line_items_url(quote_id),
            json=_line_item_payload(1.0, 100.0, "Zusatzposition"),
            headers=admin_auth_headers,
        )
        assert resp.status_code == 201, resp.text
        data = resp.json()
        assert len(data["line_items"]) == 3
        assert data["subtotal"] == pytest.approx(310.0, abs=0.01)
        assert data["tax_amount"] == pytest.approx(310.0 * 0.19, abs=0.01)
        assert data["total"] == pytest.approx(310.0 * 1.19, abs=0.01)

    @pytest.mark.asyncio
    async def test_add_line_item_unauthenticated_returns_401(
        self, client: AsyncClient, admin_auth_headers: dict, test_customer: Customer
    ):
        quote_id = await _create_quote(client, admin_auth_headers, test_customer.id)
        resp = await client.post(_line_items_url(quote_id), json=_line_item_payload())
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_add_line_item_viewer_returns_403(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        viewer_auth_headers: dict,
        test_customer: Customer,
    ):
        """VIEWER has no QUOTE_EDIT permission."""
        quote_id = await _create_quote(client, admin_auth_headers, test_customer.id)
        resp = await client.post(
            _line_items_url(quote_id),
            json=_line_item_payload(),
            headers=viewer_auth_headers,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_add_line_item_nonexistent_quote_returns_404(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        resp = await client.post(
            _line_items_url(99999),
            json=_line_item_payload(),
            headers=admin_auth_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_add_line_item_non_draft_quote_returns_409(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        quote_id = await _create_quote(client, admin_auth_headers, test_customer.id)
        await client.post(_action_url(quote_id, "send"), headers=admin_auth_headers)

        resp = await client.post(
            _line_items_url(quote_id),
            json=_line_item_payload(),
            headers=admin_auth_headers,
        )
        assert resp.status_code == 409


class TestUpdateQuoteLineItem:

    @pytest.mark.asyncio
    async def test_update_line_item_recomputes_totals(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        quote_id = await _create_quote(client, admin_auth_headers, test_customer.id)
        get_resp = await client.get(_quote_url(quote_id), headers=admin_auth_headers)
        item_id = get_resp.json()["line_items"][0]["id"]

        resp = await client.patch(
            _line_items_url(quote_id, item_id),
            json=_line_item_payload(1.0, 500.0, "Angepasste Position"),
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()
        updated_item = next(li for li in data["line_items"] if li["id"] == item_id)
        assert updated_item["description"] == "Angepasste Position"
        assert updated_item["total"] == pytest.approx(500.0, abs=0.01)
        # Other original line item (Gold 585 1.5g, 60.0) + 500.0 = 560.0
        assert data["subtotal"] == pytest.approx(560.0, abs=0.01)

    @pytest.mark.asyncio
    async def test_update_line_item_unknown_item_returns_404(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        quote_id = await _create_quote(client, admin_auth_headers, test_customer.id)

        resp = await client.patch(
            _line_items_url(quote_id, 99999),
            json=_line_item_payload(),
            headers=admin_auth_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_line_item_nonexistent_quote_returns_404(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        resp = await client.patch(
            _line_items_url(99999, 1),
            json=_line_item_payload(),
            headers=admin_auth_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_update_line_item_non_draft_quote_returns_409(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        quote_id = await _create_quote(client, admin_auth_headers, test_customer.id)
        get_resp = await client.get(_quote_url(quote_id), headers=admin_auth_headers)
        item_id = get_resp.json()["line_items"][0]["id"]
        await client.post(_action_url(quote_id, "send"), headers=admin_auth_headers)

        resp = await client.patch(
            _line_items_url(quote_id, item_id),
            json=_line_item_payload(),
            headers=admin_auth_headers,
        )
        assert resp.status_code == 409


class TestDeleteQuoteLineItem:

    @pytest.mark.asyncio
    async def test_delete_line_item_recomputes_totals(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        quote_id = await _create_quote(client, admin_auth_headers, test_customer.id)
        get_resp = await client.get(_quote_url(quote_id), headers=admin_auth_headers)
        items = get_resp.json()["line_items"]
        item_id = items[0]["id"]
        remaining_total = items[1]["total"]

        resp = await client.delete(
            _line_items_url(quote_id, item_id), headers=admin_auth_headers
        )
        assert resp.status_code == 204

        follow_up = await client.get(_quote_url(quote_id), headers=admin_auth_headers)
        data = follow_up.json()
        assert len(data["line_items"]) == 1
        assert data["subtotal"] == pytest.approx(remaining_total, abs=0.01)

    @pytest.mark.asyncio
    async def test_delete_line_item_unknown_item_returns_404(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        quote_id = await _create_quote(client, admin_auth_headers, test_customer.id)

        resp = await client.delete(
            _line_items_url(quote_id, 99999), headers=admin_auth_headers
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_line_item_nonexistent_quote_returns_404(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        resp = await client.delete(
            _line_items_url(99999, 1), headers=admin_auth_headers
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_line_item_non_draft_quote_returns_409(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        quote_id = await _create_quote(client, admin_auth_headers, test_customer.id)
        get_resp = await client.get(_quote_url(quote_id), headers=admin_auth_headers)
        item_id = get_resp.json()["line_items"][0]["id"]
        await client.post(_action_url(quote_id, "send"), headers=admin_auth_headers)

        resp = await client.delete(
            _line_items_url(quote_id, item_id), headers=admin_auth_headers
        )
        assert resp.status_code == 409


# ===========================================================================
# Route-shadowing: /line-items sub-paths vs /{quote_id}/pdf etc.
# ===========================================================================


class TestLineItemRouteShadowing:

    @pytest.mark.asyncio
    async def test_pdf_and_line_items_routes_are_both_reachable(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        """Deliberate check that /{quote_id}/pdf and /{quote_id}/line-items
        (and /{quote_id}/line-items/{item_id}) are distinct routes that do
        not shadow one another — each must be handled by its own endpoint,
        not accidentally matched against a differently-shaped path."""
        quote_id = await _create_quote(client, admin_auth_headers, test_customer.id)

        pdf_resp = await client.get(
            _action_url(quote_id, "pdf"), headers=admin_auth_headers
        )
        assert pdf_resp.status_code == 200
        assert "application/pdf" in pdf_resp.headers.get("content-type", "")

        add_resp = await client.post(
            _line_items_url(quote_id),
            json=_line_item_payload(),
            headers=admin_auth_headers,
        )
        assert add_resp.status_code == 201
        item_id = add_resp.json()["line_items"][-1]["id"]

        update_resp = await client.patch(
            _line_items_url(quote_id, item_id),
            json=_line_item_payload(2.0, 20.0),
            headers=admin_auth_headers,
        )
        assert update_resp.status_code == 200

        delete_resp = await client.delete(
            _line_items_url(quote_id, item_id), headers=admin_auth_headers
        )
        assert delete_resp.status_code == 204

        # /pdf still resolves correctly after line-item routes were hit.
        pdf_resp_2 = await client.get(
            _action_url(quote_id, "pdf"), headers=admin_auth_headers
        )
        assert pdf_resp_2.status_code == 200


# ===========================================================================
# PUT /quotes/{id} status/tax_rate guards (Fix round 1: HIGH + MEDIUM)
# ===========================================================================


class TestUpdateQuoteGuards:

    @pytest.mark.asyncio
    async def test_status_revert_via_put_is_rejected_and_edits_stay_locked(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        """HIGH: the send/approve→revert-to-DRAFT→edit→re-send bypass.
        A SENT quote must reject PUT status=draft with 409, and line items
        must remain non-addable (409) — the immutability premise holds."""
        quote_id = await _create_quote(client, admin_auth_headers, test_customer.id)
        send_resp = await client.post(
            _action_url(quote_id, "send"), headers=admin_auth_headers
        )
        assert send_resp.status_code == 200

        # Attempt the status revert via PUT → 409, status unchanged.
        revert_resp = await client.put(
            _quote_url(quote_id),
            json={"status": "draft"},
            headers=admin_auth_headers,
        )
        assert revert_resp.status_code == 409

        still_sent = await client.get(_quote_url(quote_id), headers=admin_auth_headers)
        assert still_sent.json()["status"] == "sent"

        # Line items still cannot be added to the (still SENT) quote.
        add_resp = await client.post(
            _line_items_url(quote_id),
            json=_line_item_payload(),
            headers=admin_auth_headers,
        )
        assert add_resp.status_code == 409

    @pytest.mark.asyncio
    async def test_tax_rate_change_on_sent_quote_returns_409(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        """MEDIUM: tax_rate is DRAFT-only — writing it on a SENT quote is 409
        (never a stale rate/total mismatch)."""
        quote_id = await _create_quote(client, admin_auth_headers, test_customer.id)
        await client.post(_action_url(quote_id, "send"), headers=admin_auth_headers)

        resp = await client.put(
            _quote_url(quote_id),
            json={"tax_rate": 7.0},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 409

    @pytest.mark.asyncio
    async def test_tax_rate_change_on_draft_recomputes_via_put(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        """DRAFT tax_rate edit via PUT recomputes tax_amount/total (subtotal
        210 from the fixture)."""
        quote_id = await _create_quote(client, admin_auth_headers, test_customer.id)

        resp = await client.put(
            _quote_url(quote_id),
            json={"tax_rate": 7.0},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["tax_rate"] == pytest.approx(7.0)
        assert data["subtotal"] == pytest.approx(210.0, abs=0.01)
        assert data["tax_amount"] == pytest.approx(210.0 * 0.07, abs=0.01)
        assert data["total"] == pytest.approx(210.0 * 1.07, abs=0.01)
