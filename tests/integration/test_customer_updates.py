# tests/integration/test_customer_updates.py
"""
Integration tests for the V1.2 Customer Updates & §649 BGB Cost Approval
API (Task 5).

Endpoint coverage:
  POST   /api/v1/orders/{id}/updates
  GET    /api/v1/orders/{id}/updates
  POST   /api/v1/updates/{id}/send
  GET    /api/v1/updates/{id}/pdf
  POST   /api/v1/updates/{id}/mark-delivered
  POST   /api/v1/orders/{id}/cost-changes
  GET    /api/v1/orders/{id}/cost-changes
  POST   /api/v1/cost-changes/{id}/send
  POST   /api/v1/cost-changes/{id}/record-response
  GET    /api/v1/orders/{id}/projected-cost

Covers: draft->send happy path (mocked aiosmtplib), send-failure path
(200 + delivered=false), SMTP-unset degradation, photo-ownership
rejection (422), cost-change lifecycle incl. supersede + record-response
guards, VIEWER 403 matrix, projected-cost endpoint.

aiosmtplib mocked at the same boundary as the unit tests
(``email_service_module.aiosmtplib.send``).
"""
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.core.config import settings
from goldsmith_erp.db.models import Customer, Order, OrderStatusEnum, Quote, QuoteStatus
from goldsmith_erp.services import email_service as email_service_module

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def test_order(db_session: AsyncSession, test_customer: Customer) -> Order:
    order = Order(
        title="V1.2 Integration Test Order",
        customer_id=test_customer.id,
        status=OrderStatusEnum.IN_PROGRESS,
        deadline=datetime.utcnow() + timedelta(days=14),
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)
    return order


@pytest_asyncio.fixture
async def order_with_quote(
    db_session: AsyncSession, test_order: Order, test_customer: Customer, goldsmith_user
):
    quote = Quote(
        quote_number=f"KV-INT-{test_order.id}",
        order_id=test_order.id,
        customer_id=test_customer.id,
        created_by=goldsmith_user.id,
        status=QuoteStatus.SENT,
        valid_until=datetime.utcnow() + timedelta(days=14),
        subtotal=1000.0,
        tax_rate=19.0,
        tax_amount=190.0,
        total=1190.0,
    )
    db_session.add(quote)
    await db_session.commit()
    await db_session.refresh(quote)
    return test_order


def _enable_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "EMAIL_NOTIFICATIONS_ENABLED", True)
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test.local")
    monkeypatch.setattr(settings, "SMTP_FROM", "werkstatt@test.local")
    monkeypatch.setattr(settings, "SMTP_USER", None)
    monkeypatch.setattr(settings, "SMTP_PASSWORD", None)


class _CapturingSend:
    def __init__(self, should_raise: bool = False) -> None:
        self.should_raise = should_raise
        self.sent_messages: list = []

    async def __call__(self, msg, **kwargs):
        if self.should_raise:
            raise ConnectionRefusedError("SMTP unreachable (test double)")
        self.sent_messages.append(msg)
        return None


# ---------------------------------------------------------------------------
# Draft -> send happy path
# ---------------------------------------------------------------------------


class TestDraftAndSendHappyPath:
    async def test_create_draft_returns_201_with_prefilled_content(
        self, client: AsyncClient, goldsmith_auth_headers: dict, test_order: Order
    ):
        resp = await client.post(
            f"/api/v1/orders/{test_order.id}/updates",
            json={"kind": "progress"},
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        assert body["subject"]
        assert body["body"]
        assert body["status"] == "draft"
        assert body["order_id"] == test_order.id
        assert len(body["token"]) == 32

    async def test_send_happy_path_delivers_and_marks_sent(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        test_order: Order,
        monkeypatch,
    ):
        _enable_smtp(monkeypatch)
        capture = _CapturingSend()
        monkeypatch.setattr(email_service_module.aiosmtplib, "send", capture)

        create_resp = await client.post(
            f"/api/v1/orders/{test_order.id}/updates",
            json={"kind": "ready_for_pickup"},
            headers=goldsmith_auth_headers,
        )
        update_id = create_resp.json()["id"]

        send_resp = await client.post(
            f"/api/v1/updates/{update_id}/send", headers=goldsmith_auth_headers
        )

        assert send_resp.status_code == 200, send_resp.text
        body = send_resp.json()
        assert body["delivered"] is True
        assert body["method"] == "email"
        assert body["update"]["status"] == "sent"
        assert len(capture.sent_messages) == 1

    async def test_resending_a_sent_update_returns_409(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        test_order: Order,
        monkeypatch,
    ):
        _enable_smtp(monkeypatch)
        monkeypatch.setattr(email_service_module.aiosmtplib, "send", _CapturingSend())

        create_resp = await client.post(
            f"/api/v1/orders/{test_order.id}/updates",
            json={"kind": "progress"},
            headers=goldsmith_auth_headers,
        )
        update_id = create_resp.json()["id"]
        await client.post(
            f"/api/v1/updates/{update_id}/send", headers=goldsmith_auth_headers
        )

        second = await client.post(
            f"/api/v1/updates/{update_id}/send", headers=goldsmith_auth_headers
        )
        assert second.status_code == 409

    async def test_get_order_updates_returns_history(
        self, client: AsyncClient, goldsmith_auth_headers: dict, test_order: Order
    ):
        await client.post(
            f"/api/v1/orders/{test_order.id}/updates",
            json={"kind": "progress"},
            headers=goldsmith_auth_headers,
        )

        resp = await client.get(
            f"/api/v1/orders/{test_order.id}/updates", headers=goldsmith_auth_headers
        )
        assert resp.status_code == 200
        assert len(resp.json()) == 1


# ---------------------------------------------------------------------------
# Send failure / SMTP-unset degradation
# ---------------------------------------------------------------------------


class TestSendDegradation:
    async def test_send_failure_returns_200_with_delivered_false(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        test_order: Order,
        monkeypatch,
    ):
        _enable_smtp(monkeypatch)
        monkeypatch.setattr(
            email_service_module.aiosmtplib, "send", _CapturingSend(should_raise=True)
        )

        create_resp = await client.post(
            f"/api/v1/orders/{test_order.id}/updates",
            json={"kind": "progress"},
            headers=goldsmith_auth_headers,
        )
        update_id = create_resp.json()["id"]

        resp = await client.post(
            f"/api/v1/updates/{update_id}/send", headers=goldsmith_auth_headers
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["delivered"] is False
        assert body["update"]["status"] == "send_failed"

    async def test_smtp_unset_returns_200_with_delivered_false(
        self, client: AsyncClient, goldsmith_auth_headers: dict, test_order: Order
    ):
        create_resp = await client.post(
            f"/api/v1/orders/{test_order.id}/updates",
            json={"kind": "progress"},
            headers=goldsmith_auth_headers,
        )
        update_id = create_resp.json()["id"]

        resp = await client.post(
            f"/api/v1/updates/{update_id}/send", headers=goldsmith_auth_headers
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["delivered"] is False
        assert body["method"] is None
        # Nothing was attempted (expected PDF-only mode) — draft persists.
        assert body["update"]["status"] == "draft"


# ---------------------------------------------------------------------------
# PDF download + mark-delivered
# ---------------------------------------------------------------------------


class TestPdfAndMarkDelivered:
    async def test_download_pdf_returns_pdf_without_mutating_status(
        self, client: AsyncClient, goldsmith_auth_headers: dict, test_order: Order
    ):
        create_resp = await client.post(
            f"/api/v1/orders/{test_order.id}/updates",
            json={"kind": "progress"},
            headers=goldsmith_auth_headers,
        )
        update_id = create_resp.json()["id"]

        resp = await client.get(
            f"/api/v1/updates/{update_id}/pdf", headers=goldsmith_auth_headers
        )

        assert resp.status_code == 200
        assert resp.headers["content-type"] == "application/pdf"
        assert len(resp.content) > 0

        history = await client.get(
            f"/api/v1/orders/{test_order.id}/updates", headers=goldsmith_auth_headers
        )
        assert history.json()[0]["status"] == "draft"

    async def test_mark_delivered_sets_sent_with_pdf_manual(
        self, client: AsyncClient, goldsmith_auth_headers: dict, test_order: Order
    ):
        create_resp = await client.post(
            f"/api/v1/orders/{test_order.id}/updates",
            json={"kind": "progress"},
            headers=goldsmith_auth_headers,
        )
        update_id = create_resp.json()["id"]

        resp = await client.post(
            f"/api/v1/updates/{update_id}/mark-delivered",
            json={"method": "pdf_manual"},
            headers=goldsmith_auth_headers,
        )

        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "sent"
        assert body["delivery_method"] == "pdf_manual"


# ---------------------------------------------------------------------------
# Photo ownership rejection
# ---------------------------------------------------------------------------


class TestPhotoOwnershipRejection:
    async def test_unknown_photo_id_returns_422(
        self, client: AsyncClient, goldsmith_auth_headers: dict, test_order: Order
    ):
        resp = await client.post(
            f"/api/v1/orders/{test_order.id}/updates",
            json={"kind": "progress", "photo_ids": ["not-a-real-photo-uuid"]},
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Cost-change lifecycle
# ---------------------------------------------------------------------------


class TestCostChangeLifecycle:
    async def test_create_without_quote_returns_409(
        self, client: AsyncClient, goldsmith_auth_headers: dict, test_order: Order
    ):
        resp = await client.post(
            f"/api/v1/orders/{test_order.id}/cost-changes",
            json={"new_amount": 1200.0, "reason": "Zusaetzliche Arbeit erforderlich"},
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 409

    async def test_full_lifecycle_create_send_record_response(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        order_with_quote: Order,
        monkeypatch,
    ):
        _enable_smtp(monkeypatch)
        monkeypatch.setattr(email_service_module.aiosmtplib, "send", _CapturingSend())

        create_resp = await client.post(
            f"/api/v1/orders/{order_with_quote.id}/cost-changes",
            json={
                "new_amount": 1200.0,
                "reason": "Zusaetzliche Fassung fuer Edelstein noetig",
            },
            headers=goldsmith_auth_headers,
        )
        assert create_resp.status_code == 201, create_resp.text
        cost_change = create_resp.json()
        assert cost_change["original_amount"] == 1000.0
        assert cost_change["status"] == "draft"

        send_resp = await client.post(
            f"/api/v1/cost-changes/{cost_change['id']}/send",
            headers=goldsmith_auth_headers,
        )
        assert send_resp.status_code == 200, send_resp.text
        assert send_resp.json()["delivered"] is True

        response_resp = await client.post(
            f"/api/v1/cost-changes/{cost_change['id']}/record-response",
            json={
                "status": "approved",
                "response_method": "email_reply",
                "response_evidence": "Kundin hat per Email zugestimmt",
            },
            headers=goldsmith_auth_headers,
        )
        assert response_resp.status_code == 200, response_resp.text
        assert response_resp.json()["status"] == "approved"

    async def test_record_response_before_send_returns_409(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        order_with_quote: Order,
    ):
        create_resp = await client.post(
            f"/api/v1/orders/{order_with_quote.id}/cost-changes",
            json={"new_amount": 1100.0, "reason": "Kleinere Anpassung noetig"},
            headers=goldsmith_auth_headers,
        )
        cost_change_id = create_resp.json()["id"]

        resp = await client.post(
            f"/api/v1/cost-changes/{cost_change_id}/record-response",
            json={
                "status": "approved",
                "response_method": "phone",
                "response_evidence": "Telefonisch zugestimmt",
            },
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 409

    async def test_creating_new_request_supersedes_sent_one(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        order_with_quote: Order,
        monkeypatch,
    ):
        _enable_smtp(monkeypatch)
        monkeypatch.setattr(email_service_module.aiosmtplib, "send", _CapturingSend())

        first_resp = await client.post(
            f"/api/v1/orders/{order_with_quote.id}/cost-changes",
            json={"new_amount": 1100.0, "reason": "Erste Anfrage an die Kundin"},
            headers=goldsmith_auth_headers,
        )
        first_id = first_resp.json()["id"]
        await client.post(
            f"/api/v1/cost-changes/{first_id}/send", headers=goldsmith_auth_headers
        )

        await client.post(
            f"/api/v1/orders/{order_with_quote.id}/cost-changes",
            json={"new_amount": 1300.0, "reason": "Zweite, groessere Anfrage"},
            headers=goldsmith_auth_headers,
        )

        history_resp = await client.get(
            f"/api/v1/orders/{order_with_quote.id}/cost-changes",
            headers=goldsmith_auth_headers,
        )
        by_id = {r["id"]: r for r in history_resp.json()}
        assert by_id[first_id]["status"] == "superseded"

    async def test_send_missing_cost_change_returns_404(
        self, client: AsyncClient, goldsmith_auth_headers: dict
    ):
        resp = await client.post(
            "/api/v1/cost-changes/999999/send", headers=goldsmith_auth_headers
        )
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Projected cost
# ---------------------------------------------------------------------------


class TestProjectedCost:
    async def test_returns_projection_breakdown(
        self, client: AsyncClient, goldsmith_auth_headers: dict, order_with_quote: Order
    ):
        resp = await client.get(
            f"/api/v1/orders/{order_with_quote.id}/projected-cost",
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["quote_id"] is not None
        assert body["quote_total"] == 1000.0
        assert "over_threshold" in body


# ---------------------------------------------------------------------------
# Permission matrix — VIEWER excluded (financial / design-IP data)
# ---------------------------------------------------------------------------


class TestPermissionMatrix:
    async def test_viewer_cannot_create_update(
        self, client: AsyncClient, viewer_auth_headers: dict, test_order: Order
    ):
        resp = await client.post(
            f"/api/v1/orders/{test_order.id}/updates",
            json={"kind": "progress"},
            headers=viewer_auth_headers,
        )
        assert resp.status_code == 403

    async def test_viewer_cannot_view_update_history(
        self, client: AsyncClient, viewer_auth_headers: dict, test_order: Order
    ):
        resp = await client.get(
            f"/api/v1/orders/{test_order.id}/updates", headers=viewer_auth_headers
        )
        assert resp.status_code == 403

    async def test_viewer_cannot_create_cost_change(
        self, client: AsyncClient, viewer_auth_headers: dict, test_order: Order
    ):
        resp = await client.post(
            f"/api/v1/orders/{test_order.id}/cost-changes",
            json={"new_amount": 1200.0, "reason": "Sollte nie ankommen"},
            headers=viewer_auth_headers,
        )
        assert resp.status_code == 403

    async def test_viewer_cannot_view_projected_cost(
        self, client: AsyncClient, viewer_auth_headers: dict, test_order: Order
    ):
        resp = await client.get(
            f"/api/v1/orders/{test_order.id}/projected-cost",
            headers=viewer_auth_headers,
        )
        assert resp.status_code == 403

    async def test_unauthenticated_request_returns_401(
        self, client: AsyncClient, test_order: Order
    ):
        resp = await client.get(f"/api/v1/orders/{test_order.id}/updates")
        assert resp.status_code == 401

    async def test_admin_can_access_all_endpoints(
        self, client: AsyncClient, admin_auth_headers: dict, test_order: Order
    ):
        resp = await client.get(
            f"/api/v1/orders/{test_order.id}/updates", headers=admin_auth_headers
        )
        assert resp.status_code == 200
