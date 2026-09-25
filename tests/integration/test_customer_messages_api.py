# tests/integration/test_customer_messages_api.py
"""
Integration tests for the W6 customer-message endpoints (Kundeninfo composer).

  POST /api/v1/orders/{id}/updates            photos without PHOTO_USE -> 422
  GET  /api/v1/orders/{id}/message-context    consent hint data
  POST /api/v1/orders/{id}/updates/preview    email text preview
  POST /api/v1/orders/{id}/updates/preview/pdf  same content as PDF
  GET/PUT /api/v1/customers/{id}/email-opt-out  Art. 21 "Keine E-Mail-Updates"
"""

import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.core.config import settings
from goldsmith_erp.db.models import (
    Customer,
    CustomerAuditLog,
    CustomerUpdate,
    Order,
    OrderPhoto,
    OrderStatusEnum,
)
from goldsmith_erp.services import email_service as email_service_module

# asyncio_mode = "auto" (pyproject.toml) runs the async tests.


@pytest_asyncio.fixture
async def test_order(db_session: AsyncSession, test_customer: Customer) -> Order:
    order = Order(
        title="W6 Composer Order",
        customer_id=test_customer.id,
        status=OrderStatusEnum.IN_PROGRESS,
        deadline=datetime.utcnow() + timedelta(days=14),
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)
    return order


@pytest_asyncio.fixture
async def order_photo(db_session, test_order, goldsmith_user, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "PHOTO_STORAGE_PATH", str(tmp_path))
    path = tmp_path / f"{uuid.uuid4().hex}.jpg"
    Image.new("RGB", (400, 300), color=(1, 2, 3)).save(path, format="JPEG")
    photo = OrderPhoto(
        id=str(uuid.uuid4()),
        order_id=test_order.id,
        file_path=str(path),
        taken_by=goldsmith_user.id,
    )
    db_session.add(photo)
    await db_session.commit()
    return photo


async def _grant_photo_consent(client, headers, customer_id):
    resp = await client.post(
        f"/api/v1/customers/{customer_id}/consents",
        json={"purpose": "photo_use", "method": "in_person"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text


class TestComposerPhotoConsent:
    async def test_photos_without_photo_consent_return_422_in_german(
        self,
        client: AsyncClient,
        goldsmith_auth_headers,
        test_order,
        order_photo,
        db_session,
    ):
        resp = await client.post(
            f"/api/v1/orders/{test_order.id}/updates",
            json={"kind": "progress", "photo_ids": [order_photo.id]},
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 422, resp.text
        detail = resp.json()["detail"]
        assert "Einwilligung" in detail
        assert "Fotos" in detail
        rows = (await db_session.execute(select(CustomerUpdate))).scalars().all()
        assert rows == []

    async def test_text_only_is_still_allowed_without_photo_consent(
        self, client: AsyncClient, goldsmith_auth_headers, test_order
    ):
        resp = await client.post(
            f"/api/v1/orders/{test_order.id}/updates",
            json={"kind": "progress"},
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 201, resp.text

    async def test_photos_with_photo_consent_are_accepted(
        self,
        client: AsyncClient,
        goldsmith_auth_headers,
        test_order,
        test_customer,
        order_photo,
    ):
        await _grant_photo_consent(client, goldsmith_auth_headers, test_customer.id)
        resp = await client.post(
            f"/api/v1/orders/{test_order.id}/updates",
            json={"kind": "progress", "photo_ids": [order_photo.id]},
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 201, resp.text

    async def test_price_in_status_update_returns_422(
        self, client: AsyncClient, goldsmith_auth_headers, test_order
    ):
        resp = await client.post(
            f"/api/v1/orders/{test_order.id}/updates",
            json={"kind": "progress", "subject": "Stand", "body": "Kostet 300 €"},
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 422
        assert "Preis" in resp.json()["detail"]


class TestMessageContextAndPreview:
    async def test_context_reports_consent_email_and_opt_out(
        self, client: AsyncClient, goldsmith_auth_headers, test_order, test_customer
    ):
        resp = await client.get(
            f"/api/v1/orders/{test_order.id}/message-context",
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body == {
            "customer_id": test_customer.id,
            "has_email": True,
            "photo_consent": False,
            "email_opt_out": False,
        }

    async def test_preview_returns_text_and_blocked_reason(
        self, client: AsyncClient, goldsmith_auth_headers, test_order, order_photo
    ):
        resp = await client.post(
            f"/api/v1/orders/{test_order.id}/updates/preview",
            json={
                "kind": "progress",
                "subject": "Stand",
                "body": "Wir fassen gerade den Stein.",
                "photo_ids": [order_photo.id],
            },
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert "Wir fassen gerade den Stein." in body["text"]
        assert "Datenschutz" in body["text"]
        assert body["photo_count"] == 1
        assert body["photo_consent"] is False
        assert "Einwilligung" in body["blocked_reason"]
        assert body["delivery_method"] == "email"

    async def test_preview_pdf_downloads_pdf(
        self, client: AsyncClient, goldsmith_auth_headers, test_order
    ):
        resp = await client.post(
            f"/api/v1/orders/{test_order.id}/updates/preview/pdf",
            json={"kind": "progress", "subject": "Stand", "body": "Text"},
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content.startswith(b"%PDF")

    async def test_preview_pdf_with_photos_without_consent_returns_422(
        self, client: AsyncClient, goldsmith_auth_headers, test_order, order_photo
    ):
        resp = await client.post(
            f"/api/v1/orders/{test_order.id}/updates/preview/pdf",
            json={"kind": "progress", "photo_ids": [order_photo.id]},
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 422
        assert "Einwilligung" in resp.json()["detail"]

    async def test_viewer_cannot_preview(
        self, client: AsyncClient, viewer_auth_headers, test_order
    ):
        resp = await client.post(
            f"/api/v1/orders/{test_order.id}/updates/preview",
            json={"kind": "progress"},
            headers=viewer_auth_headers,
        )
        assert resp.status_code == 403


class TestEmailOptOutEndpoints:
    async def test_opt_out_round_trip_and_send_falls_back_to_pdf(
        self,
        client: AsyncClient,
        goldsmith_auth_headers,
        test_order,
        test_customer,
        monkeypatch,
        db_session,
    ):
        monkeypatch.setattr(settings, "EMAIL_NOTIFICATIONS_ENABLED", True)
        monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test.local")
        monkeypatch.setattr(settings, "SMTP_FROM", "werkstatt@test.local")
        sent: list = []

        async def _capture(msg, **kwargs):
            sent.append(msg)

        monkeypatch.setattr(email_service_module.aiosmtplib, "send", _capture)

        url = f"/api/v1/customers/{test_customer.id}/email-opt-out"
        resp = await client.get(url, headers=goldsmith_auth_headers)
        assert resp.status_code == 200
        assert resp.json() == {"email_opt_out": False}

        resp = await client.put(
            url, json={"email_opt_out": True}, headers=goldsmith_auth_headers
        )
        assert resp.status_code == 200, resp.text
        assert resp.json() == {"email_opt_out": True}

        draft = await client.post(
            f"/api/v1/orders/{test_order.id}/updates",
            json={"kind": "progress"},
            headers=goldsmith_auth_headers,
        )
        send = await client.post(
            f"/api/v1/updates/{draft.json()['id']}/send", headers=goldsmith_auth_headers
        )
        assert send.status_code == 200
        assert send.json()["delivered"] is False
        assert send.json()["method"] == "pdf_manual"
        assert send.json()["reason"] == "opted_out"
        assert sent == []

        resp = await client.put(
            url, json={"email_opt_out": False}, headers=goldsmith_auth_headers
        )
        assert resp.json() == {"email_opt_out": False}

    async def test_viewer_cannot_change_opt_out(
        self, client: AsyncClient, viewer_auth_headers, test_customer
    ):
        resp = await client.put(
            f"/api/v1/customers/{test_customer.id}/email-opt-out",
            json={"email_opt_out": True},
            headers=viewer_auth_headers,
        )
        assert resp.status_code == 403

    async def test_unknown_customer_returns_404(
        self, client: AsyncClient, goldsmith_auth_headers
    ):
        resp = await client.get(
            "/api/v1/customers/999999/email-opt-out", headers=goldsmith_auth_headers
        )
        assert resp.status_code == 404


class TestSendAudit:
    async def test_send_endpoint_writes_customer_message_audit_row(
        self,
        client: AsyncClient,
        goldsmith_auth_headers,
        test_order,
        monkeypatch,
        db_session,
    ):
        monkeypatch.setattr(settings, "EMAIL_NOTIFICATIONS_ENABLED", True)
        monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test.local")
        monkeypatch.setattr(settings, "SMTP_FROM", "werkstatt@test.local")

        async def _capture(msg, **kwargs):
            return None

        monkeypatch.setattr(email_service_module.aiosmtplib, "send", _capture)
        draft = await client.post(
            f"/api/v1/orders/{test_order.id}/updates",
            json={"kind": "progress"},
            headers=goldsmith_auth_headers,
        )
        send = await client.post(
            f"/api/v1/updates/{draft.json()['id']}/send", headers=goldsmith_auth_headers
        )
        assert send.json()["delivered"] is True
        rows = (
            (
                await db_session.execute(
                    select(CustomerAuditLog).where(
                        CustomerAuditLog.action == "customer_message_sent"
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].entity_id == draft.json()["id"]
