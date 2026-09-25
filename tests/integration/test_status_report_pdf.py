# tests/integration/test_status_report_pdf.py
"""
Integration tests for the W6 customer-facing "Statusbericht" PDF
(DOM section D, Option 2 — Werkstattbericht).

  GET  /api/v1/orders/{id}/status-report.pdf
  GET  /api/v1/repairs/{id}/status-report.pdf
  POST /api/v1/updates/{id}/send  {"attach_status_report": true}
"""

import uuid
from datetime import datetime, timedelta

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
    CustomerUpdateKind,
    CustomerUpdateStatus,
    Order,
    OrderPhoto,
    OrderStatusEnum,
    RepairJob,
    RepairJobStatus,
)
from goldsmith_erp.services import email_service as email_service_module
from goldsmith_erp.services.status_report_service import build_order_status_report

# asyncio_mode = "auto" (pyproject.toml) runs the async tests.


@pytest_asyncio.fixture
async def test_order(db_session: AsyncSession, test_customer: Customer) -> Order:
    order = Order(
        title="Statusbericht Testauftrag",
        customer_id=test_customer.id,
        status=OrderStatusEnum.IN_PROGRESS,
        deadline=datetime.utcnow() + timedelta(days=14),
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)
    return order


@pytest_asyncio.fixture
async def test_repair(db_session: AsyncSession, test_customer: Customer) -> RepairJob:
    repair = RepairJob(
        repair_number=f"REP-{uuid.uuid4().hex[:8]}",
        bag_number=f"B-{uuid.uuid4().hex[:6]}",
        customer_id=test_customer.id,
        item_description="Goldring, Fassung lose",
        status=RepairJobStatus.IN_REPAIR,
    )
    db_session.add(repair)
    await db_session.commit()
    await db_session.refresh(repair)
    return repair


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


async def _revoke_photo_consent(client, headers, customer_id):
    resp = await client.delete(
        f"/api/v1/customers/{customer_id}/consents/photo_use", headers=headers
    )
    assert resp.status_code == 200, resp.text


async def _sent_update(
    db_session: AsyncSession,
    *,
    order_id=None,
    repair_job_id=None,
    kind=CustomerUpdateKind.PROGRESS,
    subject="Stand",
    body="Alles im Plan.",
    photo_ids=None,
    sent_by=1,
) -> CustomerUpdate:
    update = CustomerUpdate(
        order_id=order_id,
        repair_job_id=repair_job_id,
        kind=kind,
        subject=subject,
        body=body,
        photo_ids=photo_ids,
        status=CustomerUpdateStatus.SENT,
        sent_at=datetime.utcnow(),
        sent_by=sent_by,
    )
    db_session.add(update)
    await db_session.commit()
    await db_session.refresh(update)
    return update


class TestOrderStatusReportEndpoint:
    async def test_goldsmith_gets_pdf(
        self, client: AsyncClient, goldsmith_auth_headers, test_order
    ):
        resp = await client.get(
            f"/api/v1/orders/{test_order.id}/status-report.pdf",
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content.startswith(b"%PDF")

    async def test_unknown_order_is_404(
        self, client: AsyncClient, goldsmith_auth_headers
    ):
        resp = await client.get(
            "/api/v1/orders/999999999/status-report.pdf", headers=goldsmith_auth_headers
        )
        assert resp.status_code == 404

    async def test_viewer_is_forbidden(
        self, client: AsyncClient, viewer_auth_headers, test_order
    ):
        resp = await client.get(
            f"/api/v1/orders/{test_order.id}/status-report.pdf",
            headers=viewer_auth_headers,
        )
        assert resp.status_code == 403

    async def test_admin_gets_pdf(
        self, client: AsyncClient, admin_auth_headers, test_order
    ):
        resp = await client.get(
            f"/api/v1/orders/{test_order.id}/status-report.pdf",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200


class TestRepairStatusReportEndpoint:
    async def test_goldsmith_gets_pdf(
        self, client: AsyncClient, goldsmith_auth_headers, test_repair
    ):
        resp = await client.get(
            f"/api/v1/repairs/{test_repair.id}/status-report.pdf",
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        assert resp.headers["content-type"] == "application/pdf"
        assert resp.content.startswith(b"%PDF")

    async def test_viewer_is_forbidden(
        self, client: AsyncClient, viewer_auth_headers, test_repair
    ):
        resp = await client.get(
            f"/api/v1/repairs/{test_repair.id}/status-report.pdf",
            headers=viewer_auth_headers,
        )
        assert resp.status_code == 403

    async def test_unknown_repair_is_404(
        self, client: AsyncClient, goldsmith_auth_headers
    ):
        resp = await client.get(
            "/api/v1/repairs/999999999/status-report.pdf",
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 404


class TestStatusReportContent:
    """Service-level checks — the elements a PDF-text assertion cannot see."""

    async def test_never_includes_a_cost_change_or_a_price(
        self, db_session: AsyncSession, test_order, goldsmith_user
    ):
        await _sent_update(
            db_session,
            order_id=test_order.id,
            kind=CustomerUpdateKind.COST_CHANGE,
            subject="Mehrkosten",
            body="Zusatzkosten 150 €",
            sent_by=goldsmith_user.id,
        )
        await _sent_update(
            db_session,
            order_id=test_order.id,
            kind=CustomerUpdateKind.PROGRESS,
            subject="Stand",
            body="Die Fassung ist fertig.",
            sent_by=goldsmith_user.id,
        )
        data = await build_order_status_report(db_session, test_order.id)
        summaries = " ".join(event.summary for event in data.events)
        assert "€" not in summaries
        assert "cost_change" not in summaries.lower()
        assert "kostenänderung" not in summaries.lower()
        # the plain progress update IS represented
        assert any(
            "Fortschritts-Update gesendet" in event.summary for event in data.events
        )

    async def test_photos_require_active_photo_consent(
        self,
        client: AsyncClient,
        goldsmith_auth_headers,
        db_session: AsyncSession,
        test_order,
        test_customer,
        order_photo,
        goldsmith_user,
    ):
        await _grant_photo_consent(client, goldsmith_auth_headers, test_customer.id)
        await _sent_update(
            db_session,
            order_id=test_order.id,
            photo_ids=[order_photo.id],
            sent_by=goldsmith_user.id,
        )
        with_consent = await build_order_status_report(db_session, test_order.id)
        assert len(with_consent.photos) == 1

        await _revoke_photo_consent(client, goldsmith_auth_headers, test_customer.id)
        after_revoke = await build_order_status_report(db_session, test_order.id)
        assert after_revoke.photos == []

    async def test_never_includes_staff_names_or_internal_notes(
        self, db_session: AsyncSession, test_repair
    ):
        test_repair.diagnosis_notes = "Interne Notiz: schwierige Kundin"
        await db_session.commit()
        from goldsmith_erp.services.status_report_service import (
            build_repair_status_report,
        )

        data = await build_repair_status_report(db_session, test_repair.id)
        summaries = " ".join(event.summary for event in data.events)
        assert "Interne Notiz" not in summaries
        assert "schwierige" not in summaries


class TestComposerAttachStatusReport:
    async def test_attach_status_report_flag_is_audited_as_status_report(
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
        assert draft.status_code == 201, draft.text
        send = await client.post(
            f"/api/v1/updates/{draft.json()['id']}/send",
            json={"attach_status_report": True},
            headers=goldsmith_auth_headers,
        )
        assert send.status_code == 200, send.text
        assert send.json()["delivered"] is True

        rows = (
            (
                await db_session.execute(
                    select(CustomerAuditLog).where(
                        CustomerAuditLog.action == "customer_message_sent",
                        CustomerAuditLog.entity_id == draft.json()["id"],
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].details["message_kind"] == "status_report"
        assert "Art. 6(1)(b)" in rows[0].details["legal_basis"]

    async def test_send_without_the_flag_is_unaffected(
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
        assert send.status_code == 200, send.text
        rows = (
            (
                await db_session.execute(
                    select(CustomerAuditLog).where(
                        CustomerAuditLog.action == "customer_message_sent",
                        CustomerAuditLog.entity_id == draft.json()["id"],
                    )
                )
            )
            .scalars()
            .all()
        )
        assert rows[0].details["message_kind"] == "status_update"
