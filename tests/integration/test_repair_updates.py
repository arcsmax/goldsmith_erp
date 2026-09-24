# tests/integration/test_repair_updates.py
"""
Integration tests for the repair pickup-ready Kundeninfo flow
(DOM-12 / W2-02).

Root cause fixed: RepairService.complete_repair used to stamp
RepairJob.customer_notified_at unconditionally the moment a repair reached
READY — no email or Kundeninfo update was ever actually sent at that point,
so the timestamp was a lie about whether the customer had been informed.

New behaviour:
  - Reaching READY creates a DRAFT CustomerUpdate (kind=READY_FOR_PICKUP,
    repair_job_id=<repair>) — the SAME CustomerUpdateService draft/send
    mechanism used for orders. Nothing is sent yet.
  - Staff sends it with one tap (POST .../customer-updates/send).
  - customer_notified_at is set ONLY when that send actually delivers, to
    the update's own ``sent_at`` (never a synthetic "now").
  - A second send of the same draft does not resend (409, same CAS-based
    guarantee CustomerUpdateService.send already provides for orders).
  - Without SMTP configured, the send is recorded as not-delivered (no
    crash, no 5xx) and the existing generic PDF/mark-delivered fallback
    (api/routers/customer_updates.py) still works for a repair-targeted
    update, since CustomerUpdateService's PDF/mark-delivered paths are
    target-agnostic.

Endpoint coverage:
  GET  /api/v1/repairs/{id}/customer-updates       - draft/history
  POST /api/v1/repairs/{id}/customer-updates/send  - one-tap send
"""

from datetime import datetime

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.core.config import settings
from goldsmith_erp.db.models import (
    CustomerUpdateKind,
    CustomerUpdateStatus,
    RepairItemType,
    RepairJob,
    UpdateDeliveryMethod,
)
from goldsmith_erp.services import email_service as email_service_module

pytestmark = pytest.mark.asyncio

REPAIRS_URL = "/api/v1/repairs/"


# ---------------------------------------------------------------------------
# SMTP test double — mirrors tests/integration/test_customer_email_once.py
# ---------------------------------------------------------------------------


class _CapturingSend:
    def __init__(self, should_raise: bool = False) -> None:
        self.should_raise = should_raise
        self.calls = 0

    async def __call__(self, msg, **kwargs):
        self.calls += 1
        if self.should_raise:
            raise ConnectionRefusedError("SMTP unreachable (test double)")
        return None


def _enable_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "EMAIL_NOTIFICATIONS_ENABLED", True)
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test.local")
    monkeypatch.setattr(settings, "SMTP_FROM", "werkstatt@test.local")
    monkeypatch.setattr(settings, "SMTP_USER", None)
    monkeypatch.setattr(settings, "SMTP_PASSWORD", None)


def _install_smtp_double(
    monkeypatch: pytest.MonkeyPatch, should_raise: bool = False
) -> _CapturingSend:
    capture = _CapturingSend(should_raise=should_raise)
    monkeypatch.setattr(email_service_module.aiosmtplib, "send", capture)
    return capture


# ---------------------------------------------------------------------------
# Payload / flow helpers — local to this file, mirrors test_repairs.py's
# own local helpers rather than importing across test modules.
# ---------------------------------------------------------------------------


def _create_payload(customer_id: int) -> dict:
    return {
        "item_description": "Kette Weissgold — Verschluss defekt",
        "item_type": RepairItemType.CHAIN.value,
        "metal_type": "750 Weissgold",
        "customer_id": customer_id,
    }


async def _create_repair(client: AsyncClient, headers: dict, customer_id: int) -> int:
    resp = await client.post(
        REPAIRS_URL, json=_create_payload(customer_id), headers=headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def _advance_to_ready(client: AsyncClient, headers: dict, repair_id: int) -> None:
    """Walk a fresh repair through RECEIVED -> ... -> READY."""
    resp = await client.post(
        f"{REPAIRS_URL}{repair_id}/diagnose",
        json={"diagnosis_notes": "Verschluss gebrochen", "estimated_cost": 40.0},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text

    resp = await client.post(
        f"{REPAIRS_URL}{repair_id}/approve", json={}, headers=headers
    )
    assert resp.status_code == 200, resp.text

    resp = await client.post(f"{REPAIRS_URL}{repair_id}/start", headers=headers)
    assert resp.status_code == 200, resp.text

    resp = await client.post(f"{REPAIRS_URL}{repair_id}/quality-check", headers=headers)
    assert resp.status_code == 200, resp.text

    resp = await client.post(
        f"{REPAIRS_URL}{repair_id}/complete",
        json={"actual_cost": 35.0, "notes": "Verschluss erneuert"},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "ready"


async def _get_repair_row(db_session: AsyncSession, repair_id: int) -> RepairJob:
    return (
        await db_session.execute(select(RepairJob).where(RepairJob.id == repair_id))
    ).scalar_one()


# ---------------------------------------------------------------------------
# READY -> draft created, nothing sent yet
# ---------------------------------------------------------------------------


class TestRepairReadyCreatesDraft:
    async def test_complete_creates_pickup_ready_draft_without_sending(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        test_customer,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ):
        _enable_smtp(monkeypatch)
        capture = _install_smtp_double(monkeypatch)

        repair_id = await _create_repair(client, admin_auth_headers, test_customer.id)
        await _advance_to_ready(client, admin_auth_headers, repair_id)

        # No email sent yet — reaching READY only creates a draft.
        assert capture.calls == 0

        resp = await client.get(
            f"{REPAIRS_URL}{repair_id}/customer-updates", headers=admin_auth_headers
        )
        assert resp.status_code == 200, resp.text
        updates = resp.json()
        assert len(updates) == 1
        assert updates[0]["kind"] == CustomerUpdateKind.READY_FOR_PICKUP.value
        assert updates[0]["status"] == CustomerUpdateStatus.DRAFT.value
        assert updates[0]["repair_job_id"] == repair_id
        assert updates[0]["order_id"] is None

        # DOM-12 root cause: customer_notified_at must NOT be set by a mere
        # draft — only by an actual, successful send.
        repair = await _get_repair_row(db_session, repair_id)
        assert repair.customer_notified_at is None


# ---------------------------------------------------------------------------
# One-tap send
# ---------------------------------------------------------------------------


class TestSendCustomerUpdate:
    async def test_send_delivers_email_and_stamps_truthful_notified_at(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        test_customer,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ):
        _enable_smtp(monkeypatch)
        capture = _install_smtp_double(monkeypatch)

        repair_id = await _create_repair(client, admin_auth_headers, test_customer.id)
        await _advance_to_ready(client, admin_auth_headers, repair_id)

        before_send = datetime.utcnow()
        resp = await client.post(
            f"{REPAIRS_URL}{repair_id}/customer-updates/send",
            headers=admin_auth_headers,
        )
        after_send = datetime.utcnow()

        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["delivered"] is True
        assert body["method"] == UpdateDeliveryMethod.EMAIL.value
        assert capture.calls == 1

        sent_at = datetime.fromisoformat(body["update"]["sent_at"])

        repair = await _get_repair_row(db_session, repair_id)
        assert repair.customer_notified_at is not None
        assert before_send <= repair.customer_notified_at <= after_send
        # Truthful timestamp: matches the update's OWN sent_at, not an
        # independently-computed "now".
        assert repair.customer_notified_at == sent_at.replace(tzinfo=None)

    async def test_second_send_does_not_resend_or_restamp(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        test_customer,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ):
        _enable_smtp(monkeypatch)
        capture = _install_smtp_double(monkeypatch)

        repair_id = await _create_repair(client, admin_auth_headers, test_customer.id)
        await _advance_to_ready(client, admin_auth_headers, repair_id)

        first = await client.post(
            f"{REPAIRS_URL}{repair_id}/customer-updates/send",
            headers=admin_auth_headers,
        )
        assert first.status_code == 200, first.text
        first_notified_at = (
            await _get_repair_row(db_session, repair_id)
        ).customer_notified_at
        assert first_notified_at is not None

        second = await client.post(
            f"{REPAIRS_URL}{repair_id}/customer-updates/send",
            headers=admin_auth_headers,
        )
        assert second.status_code == 409

        assert capture.calls == 1  # not resent
        repair = await _get_repair_row(db_session, repair_id)
        assert repair.customer_notified_at == first_notified_at  # unchanged

    async def test_send_without_smtp_records_not_delivered_and_pdf_fallback_works(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        test_customer,
        db_session: AsyncSession,
        monkeypatch: pytest.MonkeyPatch,
    ):
        # SMTP left disabled (default test settings) — do not call
        # _enable_smtp.
        capture = _install_smtp_double(monkeypatch)

        repair_id = await _create_repair(client, admin_auth_headers, test_customer.id)
        await _advance_to_ready(client, admin_auth_headers, repair_id)

        resp = await client.post(
            f"{REPAIRS_URL}{repair_id}/customer-updates/send",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["delivered"] is False
        assert body["method"] is None
        assert capture.calls == 0

        repair = await _get_repair_row(db_session, repair_id)
        assert repair.customer_notified_at is None  # never stamped on a non-delivery

        update_id = body["update"]["id"]

        # Existing (target-agnostic) PDF-manual fallback still works for a
        # repair-targeted update — not repair-specific code, just verifying
        # CustomerUpdateService's generic path covers this target too.
        pdf_resp = await client.get(
            f"/api/v1/updates/{update_id}/pdf", headers=admin_auth_headers
        )
        assert pdf_resp.status_code == 200
        assert pdf_resp.headers["content-type"] == "application/pdf"

        mark_resp = await client.post(
            f"/api/v1/updates/{update_id}/mark-delivered",
            json={"method": "pdf_manual"},
            headers=admin_auth_headers,
        )
        assert mark_resp.status_code == 200, mark_resp.text
        assert mark_resp.json()["status"] == CustomerUpdateStatus.SENT.value
        assert (
            mark_resp.json()["delivery_method"] == UpdateDeliveryMethod.PDF_MANUAL.value
        )


# ---------------------------------------------------------------------------
# Error / permission edges
# ---------------------------------------------------------------------------


class TestNoDraftYet:
    async def test_send_before_repair_reaches_ready_returns_404(
        self, client: AsyncClient, admin_auth_headers: dict, test_customer
    ):
        repair_id = await _create_repair(client, admin_auth_headers, test_customer.id)
        resp = await client.post(
            f"{REPAIRS_URL}{repair_id}/customer-updates/send",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 404


class TestPermissions:
    async def test_viewer_cannot_send_customer_update(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        viewer_auth_headers: dict,
        test_customer,
    ):
        repair_id = await _create_repair(client, admin_auth_headers, test_customer.id)
        await _advance_to_ready(client, admin_auth_headers, repair_id)

        resp = await client.post(
            f"{REPAIRS_URL}{repair_id}/customer-updates/send",
            headers=viewer_auth_headers,
        )
        assert resp.status_code == 403

    async def test_viewer_cannot_view_customer_updates(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        viewer_auth_headers: dict,
        test_customer,
    ):
        repair_id = await _create_repair(client, admin_auth_headers, test_customer.id)
        await _advance_to_ready(client, admin_auth_headers, repair_id)

        resp = await client.get(
            f"{REPAIRS_URL}{repair_id}/customer-updates",
            headers=viewer_auth_headers,
        )
        assert resp.status_code == 403
