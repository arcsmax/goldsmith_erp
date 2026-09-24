"""W1-10 (GDPR-01, BE-23): the invoice PDF endpoint serves a stable document.

- DRAFT: re-rendered on every request, but from the snapshot taken at
  creation, so a later change to the customer row does not leak in.
- SENT / PAID / CANCELLED: the PDF frozen at issue time is served
  byte-for-byte; its SHA-256 matches ``invoices.issued_pdf_sha256``.
- After ``anonymize_customer`` (GDPR erasure after the grace period) an
  issued invoice still shows the original recipient.

``PDFService.render_invoice_pdf`` is spied on to observe which recipient a
render used (fpdf2 output is compressed with subset fonts, so the text is
not greppable in the bytes).
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import select

from goldsmith_erp.db.models import Invoice, OrderStatusEnum
from goldsmith_erp.services.customer_service import CustomerService
from goldsmith_erp.services.pdf_service import PDFService

pytestmark = pytest.mark.asyncio

INVOICES_URL = "/api/v1/invoices"


@pytest.fixture
def render_spy(monkeypatch):
    calls: list[dict[str, Any]] = []
    original = PDFService.render_invoice_pdf

    def _spy(*args: Any, **kwargs: Any) -> bytes:
        customer = kwargs["customer"]
        calls.append(
            {
                "name": customer.name,
                "address": customer.address,
                "city": customer.city,
            }
        )
        return original(*args, **kwargs)

    monkeypatch.setattr(PDFService, "render_invoice_pdf", staticmethod(_spy))
    return calls


async def _invoice_via_api(client, headers, db_session, customer, order) -> int:
    customer.street = "Alte Gasse 1"
    customer.postal_code = "10115"
    customer.city = "Berlin"
    order.status = OrderStatusEnum.COMPLETED
    order.price = 500.0
    await db_session.commit()

    resp = await client.post(
        f"{INVOICES_URL}/",
        json={
            "order_id": order.id,
            "due_date": (datetime.utcnow() + timedelta(days=14)).isoformat(),
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return int(resp.json()["id"])


async def _pdf(client, headers, invoice_id: int) -> bytes:
    resp = await client.get(f"{INVOICES_URL}/{invoice_id}/pdf", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    return resp.content


async def test_draft_pdf_uses_snapshot_not_live_customer(
    client, admin_auth_headers, db_session, sample_customer, sample_order, render_spy
) -> None:
    invoice_id = await _invoice_via_api(
        client, admin_auth_headers, db_session, sample_customer, sample_order
    )

    sample_customer.street = "Neue Allee 99"
    sample_customer.city = "Hamburg"
    await db_session.commit()
    await _pdf(client, admin_auth_headers, invoice_id)

    assert render_spy[-1]["name"] == "Max Mustermann"
    assert render_spy[-1]["address"] == "Alte Gasse 1"
    assert render_spy[-1]["city"] == "10115 Berlin"


async def test_sent_pdf_is_frozen_and_matches_hash(
    client, admin_auth_headers, db_session, sample_customer, sample_order, render_spy
) -> None:
    invoice_id = await _invoice_via_api(
        client, admin_auth_headers, db_session, sample_customer, sample_order
    )
    send = await client.post(
        f"{INVOICES_URL}/{invoice_id}/send", headers=admin_auth_headers
    )
    assert send.status_code == 200, send.text
    renders_at_send = len(render_spy)

    first = await _pdf(client, admin_auth_headers, invoice_id)
    sample_customer.street = "Neue Allee 99"
    await db_session.commit()
    second = await _pdf(client, admin_auth_headers, invoice_id)

    stored = (
        await db_session.execute(select(Invoice).where(Invoice.id == invoice_id))
    ).scalar_one()
    await db_session.refresh(stored)
    assert first == second
    assert hashlib.sha256(first).hexdigest() == stored.issued_pdf_sha256
    assert len(render_spy) == renders_at_send  # served, not re-rendered


async def test_issued_invoice_survives_customer_anonymisation(
    client, admin_auth_headers, db_session, sample_customer, sample_order, render_spy
) -> None:
    invoice_id = await _invoice_via_api(
        client, admin_auth_headers, db_session, sample_customer, sample_order
    )
    await client.post(f"{INVOICES_URL}/{invoice_id}/send", headers=admin_auth_headers)
    before = await _pdf(client, admin_auth_headers, invoice_id)

    customer_id = sample_customer.id
    assert await CustomerService.anonymize_customer(db_session, customer_id)
    await db_session.commit()
    after = await _pdf(client, admin_auth_headers, invoice_id)

    assert after == before
    # The only render happened at issue time, with the real recipient.
    assert render_spy[-1]["name"] == "Max Mustermann"


async def test_cancelled_draft_serves_a_frozen_pdf_too(
    client, admin_auth_headers, db_session, sample_customer, sample_order
) -> None:
    invoice_id = await _invoice_via_api(
        client, admin_auth_headers, db_session, sample_customer, sample_order
    )
    cancel = await client.post(
        f"{INVOICES_URL}/{invoice_id}/cancel", headers=admin_auth_headers
    )
    assert cancel.status_code == 200, cancel.text

    first = await _pdf(client, admin_auth_headers, invoice_id)
    second = await _pdf(client, admin_auth_headers, invoice_id)

    assert first == second
