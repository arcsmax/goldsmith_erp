"""
BE-05 regression: ``PUT /invoices/{id}`` must not change the invoice status.

Before the fix ``InvoiceUpdate`` exposed ``status`` and the route was gated
only by INVOICE_EDIT. A GOLDSMITH (who lacks INVOICE_DELETE by design) could
cancel a PAID invoice through PUT, bypassing ``POST /cancel``.

Status transitions now go through the dedicated action endpoints:
  POST /invoices/{id}/send       DRAFT -> SENT          (INVOICE_EDIT)
  POST /invoices/{id}/mark-paid  DRAFT/SENT/OVERDUE -> PAID (INVOICE_EDIT)
  POST /invoices/{id}/cancel     -> CANCELLED           (INVOICE_DELETE)
A PAID or CANCELLED invoice rejects PUT edits with 409.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import (
    Customer,
    Invoice,
    InvoiceStatus,
    Order,
    OrderStatusEnum,
    User,
)

INVOICES_URL = "/api/v1/invoices"


async def _make_invoice(
    db_session: AsyncSession,
    customer: Customer,
    creator: User,
    status: InvoiceStatus,
) -> Invoice:
    order = Order(
        title="Ring",
        description="BE-05 test order",
        customer_id=customer.id,
        status=OrderStatusEnum.COMPLETED,
        price=500.0,
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)

    invoice = Invoice(
        invoice_number=f"RE-2026-{uuid.uuid4().hex[:6]}",
        order_id=order.id,
        customer_id=customer.id,
        created_by=creator.id,
        status=status,
        issue_date=datetime.utcnow(),
        due_date=datetime.utcnow() + timedelta(days=14),
        subtotal=500.0,
        tax_rate=19.0,
        tax_amount=95.0,
        total=595.0,
    )
    db_session.add(invoice)
    await db_session.commit()
    await db_session.refresh(invoice)
    return invoice


@pytest_asyncio.fixture
async def paid_invoice(db_session, test_customer, admin_user) -> Invoice:
    return await _make_invoice(
        db_session, test_customer, admin_user, InvoiceStatus.PAID
    )


@pytest_asyncio.fixture
async def draft_invoice(db_session, test_customer, admin_user) -> Invoice:
    return await _make_invoice(
        db_session, test_customer, admin_user, InvoiceStatus.DRAFT
    )


@pytest.mark.asyncio
class TestInvoicePutCannotChangeStatus:
    async def test_goldsmith_cannot_cancel_paid_invoice_via_put(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        goldsmith_auth_headers: dict,
        paid_invoice: Invoice,
    ):
        resp = await client.put(
            f"{INVOICES_URL}/{paid_invoice.id}",
            json={"status": "cancelled"},
            headers=goldsmith_auth_headers,
        )

        assert resp.status_code in (409, 422), resp.text
        await db_session.refresh(paid_invoice)
        assert paid_invoice.status == InvoiceStatus.PAID

    async def test_status_field_is_rejected_on_draft_invoice(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        goldsmith_auth_headers: dict,
        draft_invoice: Invoice,
    ):
        resp = await client.put(
            f"{INVOICES_URL}/{draft_invoice.id}",
            json={"status": "cancelled"},
            headers=goldsmith_auth_headers,
        )

        assert resp.status_code == 422, resp.text
        await db_session.refresh(draft_invoice)
        assert draft_invoice.status == InvoiceStatus.DRAFT

    async def test_put_notes_on_paid_invoice_returns_409(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        paid_invoice: Invoice,
    ):
        resp = await client.put(
            f"{INVOICES_URL}/{paid_invoice.id}",
            json={"notes": "nachtraeglich"},
            headers=admin_auth_headers,
        )

        assert resp.status_code == 409, resp.text

    async def test_put_notes_on_draft_invoice_still_works(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        draft_invoice: Invoice,
    ):
        resp = await client.put(
            f"{INVOICES_URL}/{draft_invoice.id}",
            json={"notes": "Bitte bis Monatsende"},
            headers=goldsmith_auth_headers,
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["notes"] == "Bitte bis Monatsende"
        assert resp.json()["status"] == "draft"

    async def test_goldsmith_cannot_cancel_via_cancel_endpoint(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        draft_invoice: Invoice,
    ):
        resp = await client.post(
            f"{INVOICES_URL}/{draft_invoice.id}/cancel",
            headers=goldsmith_auth_headers,
        )

        assert resp.status_code == 403, resp.text

    async def test_send_endpoint_moves_draft_to_sent(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        draft_invoice: Invoice,
    ):
        resp = await client.post(
            f"{INVOICES_URL}/{draft_invoice.id}/send",
            headers=goldsmith_auth_headers,
        )

        assert resp.status_code == 200, resp.text
        assert resp.json()["status"] == "sent"

    async def test_send_endpoint_rejects_paid_invoice(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        paid_invoice: Invoice,
    ):
        resp = await client.post(
            f"{INVOICES_URL}/{paid_invoice.id}/send",
            headers=goldsmith_auth_headers,
        )

        assert resp.status_code == 409, resp.text
