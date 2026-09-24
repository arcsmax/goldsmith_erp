"""
A4 — Adversarial tests for the PUT /invoices/{id} status-change guard and
the /cancel business rule (audit 2026-09-25, BE-05).

tests/integration/test_invoice_status_guard.py already covers: GOLDSMITH
cannot cancel a PAID invoice via PUT; a bare ``status`` field is rejected on
a DRAFT invoice; PUT on a PAID invoice returns 409; GOLDSMITH cannot call
POST /cancel (403); POST /send transitions and rejects a PAID invoice.

These tests probe what that file does not: extra fields other than
``status`` (``paid_date``, ``total``) on PUT, a payload mixing legitimate
and illegitimate fields, and whether ADMIN (who DOES hold INVOICE_DELETE)
can cancel a PAID invoice — i.e. whether the block is a permission check
only, or a real business-state rule that applies even to the most
privileged role.
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
        description="A4 adversarial test order",
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
async def draft_invoice(db_session, sample_customer, admin_user) -> Invoice:
    return await _make_invoice(
        db_session, sample_customer, admin_user, InvoiceStatus.DRAFT
    )


@pytest_asyncio.fixture
async def paid_invoice(db_session, sample_customer, admin_user) -> Invoice:
    return await _make_invoice(
        db_session, sample_customer, admin_user, InvoiceStatus.PAID
    )


@pytest.mark.asyncio
class TestPutRejectsUndeclaredMutableFields:
    async def test_put_rejects_paid_date_field(
        self, client: AsyncClient, draft_invoice: Invoice, admin_auth_headers: dict
    ):
        """paid_date is set only by POST /mark-paid. A caller who knows the
        column name must not be able to backdate/forge it through PUT."""
        resp = await client.put(
            f"{INVOICES_URL}/{draft_invoice.id}",
            json={"paid_date": "2020-01-01T00:00:00"},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 422, resp.text

    async def test_put_rejects_total_field(
        self, client: AsyncClient, draft_invoice: Invoice, admin_auth_headers: dict
    ):
        """total (Gesamtbetrag) must only ever be derived server-side from
        line items; PUT must not let a caller overwrite it directly."""
        resp = await client.put(
            f"{INVOICES_URL}/{draft_invoice.id}",
            json={"total": 1.0},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 422, resp.text

    async def test_put_rejects_status_mixed_with_legitimate_fields(
        self, client: AsyncClient, draft_invoice: Invoice, admin_auth_headers: dict
    ):
        """A stray status alongside otherwise-legitimate fields must still be
        rejected wholesale (extra='forbid'), not silently dropped while the
        rest of the update applies."""
        resp = await client.put(
            f"{INVOICES_URL}/{draft_invoice.id}",
            json={"notes": "legit note", "status": "cancelled"},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 422, resp.text

        # Confirm the "legit" note was NOT silently applied by a partial
        # validate-then-strip path.
        get_resp = await client.get(
            f"{INVOICES_URL}/{draft_invoice.id}", headers=admin_auth_headers
        )
        assert get_resp.json()["notes"] != "legit note"


@pytest.mark.asyncio
class TestAdminCannotCancelPaidInvoiceEither:
    async def test_admin_cancel_of_paid_invoice_is_refused_by_business_rule(
        self, client: AsyncClient, paid_invoice: Invoice, admin_auth_headers: dict
    ):
        """ADMIN holds INVOICE_DELETE (unlike GOLDSMITH), so a 403 here would
        mean nothing — this must be blocked by cancel_invoice's own state
        check (invoice_service.py: 'PAID invoices cannot be cancelled — a
        credit note (Storno) process would be needed'), which the ADR
        documents as intentional. Confirm it holds for the most privileged
        role too, not only for callers who lack the permission."""
        resp = await client.post(
            f"{INVOICES_URL}/{paid_invoice.id}/cancel",
            headers=admin_auth_headers,
        )
        assert resp.status_code == 422, resp.text
        assert (await client.get(
            f"{INVOICES_URL}/{paid_invoice.id}", headers=admin_auth_headers
        )).json()["status"] == "paid"
