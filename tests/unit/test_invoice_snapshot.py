"""W1-10 (GDPR-01 snapshot part, BE-23): immutable invoice snapshot.

Decision D-06 / assumption A4: a JSON snapshot of the invoice-relevant
recipient, seller, order and line data is written when the invoice is
created. While the invoice is a DRAFT only its own editable fields
(due date, notes, payment method) follow edits; the recipient block never
follows the live customer row. When the invoice is issued (DRAFT -> SENT,
or DRAFT -> PAID directly) the rendered PDF bytes and their SHA-256 are
frozen, write-once.

Before this fix the invoice PDF was rendered from the live customer row
(``api/routers/invoices.py``), so a move or a GDPR anonymisation rewrote
already-issued invoices (§14 Abs. 4 UStG, §146 Abs. 4 AO).
"""

from __future__ import annotations

import base64
import hashlib
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import text

from goldsmith_erp.db.models import InvoiceStatus, OrderStatusEnum
from goldsmith_erp.models.invoice import InvoiceCreate, InvoiceUpdate, MarkPaidRequest
from goldsmith_erp.services.invoice_service import InvoiceService
from goldsmith_erp.services.invoice_snapshot_service import (
    SNAPSHOT_VERSION,
    InvoiceSnapshotService,
)

pytestmark = pytest.mark.asyncio


async def _completed_order(db_session, sample_order, sample_customer):
    sample_customer.street = "Alte Gasse 1"
    sample_customer.postal_code = "10115"
    sample_customer.city = "Berlin"
    sample_order.status = OrderStatusEnum.COMPLETED
    sample_order.price = 500.0
    await db_session.commit()
    return sample_order


async def _create(db_session, order_id, admin_user):
    return await InvoiceService.create_invoice_from_order(
        db_session,
        InvoiceCreate(
            order_id=order_id,
            due_date=datetime.utcnow() + timedelta(days=14),
            notes="Danke für Ihren Auftrag",
        ),
        admin_user,
    )


class TestSnapshotAtCreation:
    async def test_creation_writes_full_snapshot(
        self, db_session, sample_order, sample_customer, admin_user
    ) -> None:
        order = await _completed_order(db_session, sample_order, sample_customer)

        invoice = await _create(db_session, order.id, admin_user)
        snap = InvoiceSnapshotService.load(invoice)

        assert snap is not None
        assert snap["version"] == SNAPSHOT_VERSION
        assert snap["backfilled"] is False
        assert snap["recipient"]["name"] == "Max Mustermann"
        assert snap["recipient"]["street"] == "Alte Gasse 1"
        assert snap["recipient"]["postal_code"] == "10115"
        assert snap["recipient"]["city"] == "Berlin"
        assert "email" not in snap["recipient"]  # minimum data (Art. 5(1)(c))
        assert snap["seller"]["name"]
        assert snap["invoice"]["invoice_number"] == invoice.invoice_number
        assert snap["invoice"]["order_id"] == order.id
        assert snap["totals"]["subtotal"] == pytest.approx(500.0)
        assert snap["totals"]["total"] == pytest.approx(595.0)
        assert [line["description"] for line in snap["lines"]] == [
            line.description for line in invoice.line_items
        ]
        assert invoice.issued_pdf is None
        assert invoice.issued_pdf_sha256 is None

    async def test_snapshot_is_encrypted_at_rest(
        self, db_session, sample_order, sample_customer, admin_user
    ) -> None:
        order = await _completed_order(db_session, sample_order, sample_customer)
        invoice = await _create(db_session, order.id, admin_user)

        raw = (
            await db_session.execute(
                text("SELECT snapshot FROM invoices WHERE id = :id"),
                {"id": invoice.id},
            )
        ).scalar_one()

        assert raw
        assert "Mustermann" not in raw
        assert "Alte Gasse" not in raw

    async def test_customer_change_does_not_touch_snapshot(
        self, db_session, sample_order, sample_customer, admin_user
    ) -> None:
        order = await _completed_order(db_session, sample_order, sample_customer)
        invoice = await _create(db_session, order.id, admin_user)

        sample_customer.street = "Neue Allee 99"
        sample_customer.last_name = "Neumann"
        await db_session.commit()
        await InvoiceService.update_invoice(
            db_session, invoice.id, InvoiceUpdate(notes="neue Notiz"), admin_user
        )

        reloaded = await InvoiceService.get_invoice(db_session, invoice.id, admin_user)
        snap = InvoiceSnapshotService.load(reloaded)
        assert snap["recipient"]["street"] == "Alte Gasse 1"
        assert snap["recipient"]["name"] == "Max Mustermann"
        # DRAFT: the invoice's own editable fields follow the edit
        assert snap["invoice"]["notes"] == "neue Notiz"


class TestFreezeOnIssue:
    async def test_send_freezes_pdf_bytes_and_hash(
        self, db_session, sample_order, sample_customer, admin_user
    ) -> None:
        order = await _completed_order(db_session, sample_order, sample_customer)
        invoice = await _create(db_session, order.id, admin_user)

        sent = await InvoiceService.mark_as_sent(db_session, invoice.id, admin_user)

        assert sent.status == InvoiceStatus.SENT
        assert sent.issued_at is not None
        pdf = base64.b64decode(sent.issued_pdf)
        assert pdf.startswith(b"%PDF")
        assert sent.issued_pdf_sha256 == hashlib.sha256(pdf).hexdigest()
        assert InvoiceSnapshotService.frozen_pdf(sent) == pdf

    async def test_frozen_invoice_is_write_once(
        self, db_session, sample_order, sample_customer, admin_user
    ) -> None:
        order = await _completed_order(db_session, sample_order, sample_customer)
        invoice = await _create(db_session, order.id, admin_user)
        sent = await InvoiceService.mark_as_sent(db_session, invoice.id, admin_user)
        frozen_hash = sent.issued_pdf_sha256
        frozen_snapshot = sent.snapshot

        # W2-04: an issued invoice is locked; the edit is refused outright.
        with pytest.raises(HTTPException) as exc_info:
            await InvoiceService.update_invoice(
                db_session, invoice.id, InvoiceUpdate(notes="nachträglich"), admin_user
            )
        assert exc_info.value.status_code == 409
        paid = await InvoiceService.mark_as_paid(
            db_session, invoice.id, MarkPaidRequest(payment_method="Bar"), admin_user
        )

        assert paid.issued_pdf_sha256 == frozen_hash
        assert paid.snapshot == frozen_snapshot

    async def test_draft_marked_paid_directly_is_frozen(
        self, db_session, sample_order, sample_customer, admin_user
    ) -> None:
        order = await _completed_order(db_session, sample_order, sample_customer)
        invoice = await _create(db_session, order.id, admin_user)

        paid = await InvoiceService.mark_as_paid(
            db_session,
            invoice.id,
            MarkPaidRequest(payment_method="Karte"),
            admin_user,
        )

        assert paid.issued_pdf_sha256 is not None
        assert InvoiceSnapshotService.load(paid)["invoice"]["payment_method"] == (
            "Karte"
        )

    async def test_tampered_pdf_fails_integrity_check(
        self, db_session, sample_order, sample_customer, admin_user
    ) -> None:
        order = await _completed_order(db_session, sample_order, sample_customer)
        invoice = await _create(db_session, order.id, admin_user)
        sent = await InvoiceService.mark_as_sent(db_session, invoice.id, admin_user)

        sent.issued_pdf_sha256 = "0" * 64

        with pytest.raises(ValueError, match="SHA-256"):
            InvoiceSnapshotService.frozen_pdf(sent)


class TestLegacyInvoicesWithoutSnapshot:
    async def test_ensure_snapshot_backfills_from_current_data(
        self, db_session, sample_order, sample_customer, admin_user
    ) -> None:
        order = await _completed_order(db_session, sample_order, sample_customer)
        invoice = await _create(db_session, order.id, admin_user)
        invoice.snapshot = None  # simulate a pre-W1-10 row
        await db_session.commit()

        await InvoiceSnapshotService.ensure_snapshot(db_session, invoice)
        snap = InvoiceSnapshotService.load(invoice)

        assert snap["backfilled"] is True
        assert snap["recipient"]["name"] == "Max Mustermann"
