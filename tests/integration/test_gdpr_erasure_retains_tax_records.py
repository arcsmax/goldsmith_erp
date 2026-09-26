"""GDPR-01 — Art. 17 erasure must not alter records the law requires us to keep.

§147 Abs. 1, 3 AO and §14b UStG require invoices (incl. line-item
descriptions) and trade letters (accepted quotes incl. signature) to be
kept for up to 10 years; GwG §8 Abs. 4 requires the Altgold purchase record
(signature, items, receipt) to be kept for 5 years. GDPR Art. 17(3)(b)
exempts exactly these records from erasure.

The end-to-end flow tested here:

1. ``DELETE /customers/{id}/gdpr-erase`` (request time) — contact PII is
   scrubbed elsewhere, but invoice / quote / Altgold rows keep their
   content, the Altgold receipt PDF stays on disk, health data (allergies,
   consents) is deleted, and a legal-hold marker
   (``customers.retention_hold_until``) is set with the legal basis in the
   audit trail.
2. ``hard_delete_expired_customers`` (after the 30-day grace) — the
   customer row is anonymised in place (FKs from the retained records keep
   pointing at the anonymised row) instead of being deleted; the hold
   stays; the Art. 30 row names Art. 17(3)(b).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import (
    AlloyType,
    Customer,
    CustomerAuditLog,
    CustomerConsent,
    GDPRRequest,
    Invoice,
    InvoiceLineItem,
    InvoiceLineType,
    InvoiceStatus,
    Order,
    OrderStatusEnum,
    Quote,
    QuoteLineItem,
    QuoteLineType,
    QuoteStatus,
    ScrapGold,
    ScrapGoldItem,
    ScrapGoldStatus,
    User,
)
from goldsmith_erp.services.customer_service import (
    ANONYMIZED_CUSTOMER_NAME,
    CustomerService,
)

SIGNATURE = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB"
LINE_TEXT = "Ring 750 Gelbgold für Erika Musterfrau"


@pytest.fixture
def storage_root(tmp_path, monkeypatch) -> Path:
    monkeypatch.setattr(
        "goldsmith_erp.core.config.settings.FILE_STORAGE_ROOT", str(tmp_path)
    )
    return tmp_path


async def _seed(db: AsyncSession, admin: User, storage_root: Path) -> dict:
    customer = Customer(
        first_name="Erika",
        last_name="Musterfrau",
        email=f"erika_{uuid.uuid4().hex[:8]}@example.com",
        phone="+49 30 1234567",
        street="Hauptstraße 1",
        city="Berlin",
        postal_code="10115",
        allergies="Nickel",
        customer_type="private",
        is_active=True,
    )
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    order = Order(
        title="Ring für Erika Musterfrau",
        customer_id=customer.id,
        status=OrderStatusEnum.COMPLETED,
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)

    invoice = Invoice(
        invoice_number=f"RE-2026-{uuid.uuid4().hex[:6]}",
        order_id=order.id,
        customer_id=customer.id,
        created_by=admin.id,
        status=InvoiceStatus.PAID,
        due_date=datetime.now(timezone.utc) + timedelta(days=14),
        subtotal=1000.0,
        tax_amount=190.0,
        total=1190.0,
        notes="Zahlung bar, Erika Musterfrau",
    )
    db.add(invoice)
    await db.commit()
    await db.refresh(invoice)
    inv_line = InvoiceLineItem(
        invoice_id=invoice.id,
        line_type=InvoiceLineType.MATERIAL,
        description=LINE_TEXT,
        quantity=1.0,
        unit_price=1000.0,
        total=1000.0,
    )
    db.add(inv_line)

    quote = Quote(
        quote_number=f"KV-2026-{uuid.uuid4().hex[:6]}",
        customer_id=customer.id,
        order_id=order.id,
        created_by=admin.id,
        status=QuoteStatus.APPROVED,
        valid_until=datetime.now(timezone.utc) + timedelta(days=14),
        customer_signature_data=SIGNATURE,
        notes="Angenommen von Erika Musterfrau",
    )
    db.add(quote)
    await db.commit()
    await db.refresh(quote)
    quote_line = QuoteLineItem(
        quote_id=quote.id,
        line_type=QuoteLineType.MATERIAL,
        description=LINE_TEXT,
        quantity=1.0,
        unit_price=1000.0,
        total=1000.0,
    )
    db.add(quote_line)

    receipt_rel = "scrap_gold/receipt_1.pdf"
    receipt_abs = storage_root / receipt_rel
    receipt_abs.parent.mkdir(parents=True, exist_ok=True)
    receipt_abs.write_bytes(b"%PDF-1.4 Ankaufbeleg")
    scrap = ScrapGold(
        order_id=order.id,
        customer_id=customer.id,
        created_by=admin.id,
        status=ScrapGoldStatus.RECEIVED,
        total_fine_gold_g=2.925,
        total_value_eur=150.0,
        signature_data=SIGNATURE,
        signed_at=datetime.now(timezone.utc),
        receipt_pdf_path=receipt_rel,
        notes="Ausweis geprüft, Erika Musterfrau",
    )
    db.add(scrap)
    await db.commit()
    await db.refresh(scrap)
    scrap_item = ScrapGoldItem(
        scrap_gold_id=scrap.id,
        description="Alter Ehering von Erika Musterfrau",
        alloy=AlloyType.GOLD_585,
        weight_g=5.0,
        fine_content_g=2.925,
    )
    db.add(scrap_item)
    db.add(
        CustomerConsent(
            customer_id=customer.id,
            purpose="health_data",
            method="written",
            granted_at=datetime.now(timezone.utc),
            recorded_by_user_id=admin.id,
        )
    )
    await db.commit()

    return {
        "customer_id": customer.id,
        "invoice_id": invoice.id,
        "invoice_line_id": inv_line.id,
        "quote_id": quote.id,
        "quote_line_id": quote_line.id,
        "scrap_id": scrap.id,
        "scrap_item_id": scrap_item.id,
        "receipt_abs": receipt_abs,
        "receipt_rel": receipt_rel,
    }


async def _one(db: AsyncSession, model, pk: int):
    row = (await db.execute(select(model).filter(model.id == pk))).scalar_one()
    await db.refresh(row)
    return row


def _assert_records_untouched(
    ids: dict, invoice, inv_line, quote, q_line, scrap, s_item
):
    assert invoice.customer_id == ids["customer_id"]
    assert float(invoice.total) == 1190.0
    assert float(invoice.tax_amount) == 190.0
    assert invoice.notes == "Zahlung bar, Erika Musterfrau"
    assert inv_line.description == LINE_TEXT
    assert quote.customer_id == ids["customer_id"]
    assert quote.customer_signature_data == SIGNATURE
    assert quote.notes == "Angenommen von Erika Musterfrau"
    assert q_line.description == LINE_TEXT
    assert scrap.customer_id == ids["customer_id"]
    assert scrap.signature_data == SIGNATURE
    assert scrap.receipt_pdf_path == ids["receipt_rel"]
    assert float(scrap.total_value_eur) == 150.0
    assert s_item.description == "Alter Ehering von Erika Musterfrau"
    assert ids["receipt_abs"].exists(), "Altgold receipt PDF must be retained"


async def _load_all(db: AsyncSession, ids: dict):
    return (
        await _one(db, Invoice, ids["invoice_id"]),
        await _one(db, InvoiceLineItem, ids["invoice_line_id"]),
        await _one(db, Quote, ids["quote_id"]),
        await _one(db, QuoteLineItem, ids["quote_line_id"]),
        await _one(db, ScrapGold, ids["scrap_id"]),
        await _one(db, ScrapGoldItem, ids["scrap_item_id"]),
    )


@pytest.mark.asyncio
async def test_erase_request_keeps_tax_and_gwg_records(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_user: User,
    admin_auth_headers: dict,
    storage_root: Path,
):
    ids = await _seed(db_session, admin_user, storage_root)

    resp = await client.delete(
        f"/api/v1/customers/{ids['customer_id']}/gdpr-erase",
        headers=admin_auth_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["retention_hold"]["legal_basis"].startswith("Art. 17 Abs. 3 lit. b")
    assert body["retention_hold"]["retained_records"] == {
        "invoices": 1,
        "quotes": 1,
        "scrap_gold": 1,
        "valuation_certificates": 0,
    }

    _assert_records_untouched(ids, *(await _load_all(db_session, ids)))

    customer = await _one(db_session, Customer, ids["customer_id"])
    # Health data goes immediately (no retention duty for it).
    assert customer.allergies is None
    consents = list(
        (
            await db_session.execute(
                select(CustomerConsent).filter(
                    CustomerConsent.customer_id == ids["customer_id"]
                )
            )
        ).scalars()
    )
    assert consents == []
    # Legal hold: end of the calendar year of the newest record + 10 years.
    assert customer.retention_hold_until is not None
    assert customer.retention_hold_until.year == datetime.now(timezone.utc).year + 10
    assert customer.retention_hold_until.month == 12
    assert customer.retention_hold_until.day == 31

    hold_audit = (
        await db_session.execute(
            select(CustomerAuditLog).filter(
                CustomerAuditLog.customer_id == ids["customer_id"],
                CustomerAuditLog.action == "gdpr_retention_hold",
            )
        )
    ).scalar_one()
    assert "Art. 17 Abs. 3 lit. b" in hold_audit.details["legal_basis"]
    assert "§147 AO" in hold_audit.details["legal_basis"]
    assert "GwG" in hold_audit.details["legal_basis"]

    gdpr_row = (
        await db_session.execute(
            select(GDPRRequest).filter(
                GDPRRequest.customer_id == ids["customer_id"],
                GDPRRequest.request_type == "erasure",
            )
        )
    ).scalar_one()
    assert "Art. 17 Abs. 3 lit. b" in (gdpr_row.notes or "")


@pytest.mark.asyncio
async def test_grace_period_cleanup_anonymizes_customer_keeps_records(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_user: User,
    admin_auth_headers: dict,
    storage_root: Path,
):
    ids = await _seed(db_session, admin_user, storage_root)
    resp = await client.delete(
        f"/api/v1/customers/{ids['customer_id']}/gdpr-erase",
        headers=admin_auth_headers,
    )
    assert resp.status_code == 200, resp.text

    report = await CustomerService.hard_delete_expired_customers(
        db_session,
        now=datetime.now(timezone.utc) + timedelta(days=31),
        storage_root=storage_root,
    )
    assert report.anonymized == [ids["customer_id"]]
    assert not report.has_failures

    customer = await _one(db_session, Customer, ids["customer_id"])
    assert customer.first_name == ANONYMIZED_CUSTOMER_NAME
    assert customer.last_name == ANONYMIZED_CUSTOMER_NAME
    assert customer.email == f"deleted_{ids['customer_id']}@anonymized.local"
    assert customer.phone is None
    assert customer.street is None
    assert customer.allergies is None
    assert customer.is_deleted is True
    # Hold survives anonymisation — it governs when the records may go.
    assert customer.retention_hold_until is not None

    # Retained records still intact and still linked to the anonymised row.
    _assert_records_untouched(ids, *(await _load_all(db_session, ids)))

    cleanup_row = (
        await db_session.execute(
            select(GDPRRequest).filter(
                GDPRRequest.customer_id == ids["customer_id"],
                GDPRRequest.request_type == "erasure_cleanup",
            )
        )
    ).scalar_one()
    assert "Art. 17 Abs. 3 lit. b" in (cleanup_row.notes or "")
    assert "anonymized" in (cleanup_row.notes or "")


@pytest.mark.asyncio
async def test_customer_with_only_scrap_gold_is_anonymized_not_deleted(
    db_session: AsyncSession, admin_user: User, storage_root: Path
):
    """ScrapGold.customer_id is SET NULL — a hard-delete would silently
    orphan the GwG record. It must count as a retained record."""
    customer = Customer(
        first_name="Otto",
        last_name="Altgold",
        email=f"otto_{uuid.uuid4().hex[:8]}@example.com",
        customer_type="private",
        is_active=False,
        deletion_scheduled_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db_session.add(customer)
    await db_session.commit()
    await db_session.refresh(customer)
    order = Order(title="Ankauf", customer_id=customer.id, status=OrderStatusEnum.NEW)
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)
    scrap = ScrapGold(
        order_id=order.id,
        customer_id=customer.id,
        created_by=admin_user.id,
        status=ScrapGoldStatus.RECEIVED,
        signature_data=SIGNATURE,
    )
    db_session.add(scrap)
    await db_session.commit()
    await db_session.refresh(scrap)

    assert await CustomerService.has_retained_financial_records(db_session, customer.id)
    report = await CustomerService.hard_delete_expired_customers(
        db_session, storage_root=storage_root
    )
    assert report.anonymized == [customer.id]
    scrap_after = await _one(db_session, ScrapGold, scrap.id)
    assert scrap_after.customer_id == customer.id
    assert scrap_after.signature_data == SIGNATURE
