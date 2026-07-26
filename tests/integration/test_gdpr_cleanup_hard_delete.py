"""Integration tests for the GDPR Art. 17 post-grace-period cleanup.

Covers ``CustomerService.hard_delete_expired_customers`` — the back half of
the erasure loop (production-readiness.md 2026-07-26, finding 1.3):

  (a) A customer WITH a §147-AO-retained invoice is ANONYMISED in place, not
      deleted; the invoice survives with a scrubbed customer link.
  (b) A customer WITHOUT financial records is HARD-DELETED (existing intent).
  (c) Thumbnails are erased alongside originals during the sweep (issue #24).
  (d) A failure on one customer does NOT silently continue — it is reported
      and the run's report flags it (the CLI turns that into a nonzero exit),
      while OTHER customers are still processed.

PG-vs-SQLite gotcha (see tests/integration/conftest.py):
  These tests run on file-backed SQLite by default. SQLite does NOT enforce
  the ``ondelete="RESTRICT"`` / ``CASCADE`` FK semantics that PostgreSQL does
  (foreign_keys pragma is off), so the anonymise-vs-delete DECISION here is
  driven by ``has_retained_financial_records`` (an explicit existence query),
  NOT by the DB raising an IntegrityError. That is deliberate: the service
  must behave identically on both backends. Enum values are lowercase on PG;
  we construct rows with the Enum members directly to stay backend-agnostic.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import (
    Customer,
    GDPRRequest,
    Invoice,
    InvoiceStatus,
    Order,
    OrderPhoto,
    OrderStatusEnum,
)
from goldsmith_erp.services.customer_service import (
    ANONYMIZED_CUSTOMER_NAME,
    CustomerService,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _mk_customer(
    db: AsyncSession, *, expired: bool = True, active: bool = False
) -> Customer:
    """Create a customer already scheduled for deletion (grace elapsed)."""
    scheduled = (
        datetime.utcnow() - timedelta(days=1)
        if expired
        else datetime.utcnow() + timedelta(days=10)
    )
    customer = Customer(
        first_name="Erika",
        last_name="Musterfrau",
        email=f"cust_{uuid.uuid4().hex[:8]}@example.com",
        phone="+49 30 1234567",
        allergies="Nickel",
        customer_type="private",
        is_active=active,
        deletion_scheduled_at=scheduled,
    )
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    return customer


async def _mk_order(db: AsyncSession, customer_id: int) -> Order:
    order = Order(
        title="Ring",
        description="750er Gelbgold",
        customer_id=customer_id,
        status=OrderStatusEnum.NEW,
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)
    return order


async def _mk_invoice(
    db: AsyncSession, *, order_id: int, customer_id: int, created_by: int
) -> Invoice:
    invoice = Invoice(
        invoice_number=f"RE-2026-{uuid.uuid4().hex[:6]}",
        order_id=order_id,
        customer_id=customer_id,
        created_by=created_by,
        status=InvoiceStatus.DRAFT,
        due_date=datetime.utcnow() + timedelta(days=14),
        subtotal=100.0,
        tax_amount=19.0,
        total=119.0,
    )
    db.add(invoice)
    await db.commit()
    await db.refresh(invoice)
    return invoice


# ---------------------------------------------------------------------------
# (a) Customer WITH a financial record → anonymised, invoice survives
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_customer_with_invoice_is_anonymized_not_deleted(
    db_session: AsyncSession, admin_user, tmp_path: Path
):
    customer = await _mk_customer(db_session)
    order = await _mk_order(db_session, customer.id)
    invoice = await _mk_invoice(
        db_session, order_id=order.id, customer_id=customer.id, created_by=admin_user.id
    )
    customer_id = customer.id
    invoice_id = invoice.id

    report = await CustomerService.hard_delete_expired_customers(
        db_session, storage_root=tmp_path
    )

    assert report.scanned == 1
    assert report.anonymized == [customer_id]
    assert report.hard_deleted == []
    assert not report.has_failures

    # Customer row STILL EXISTS but is anonymised.
    refreshed = await db_session.execute(
        select(Customer).filter(Customer.id == customer_id)
    )
    cust_after = refreshed.scalar_one()
    assert cust_after.first_name == ANONYMIZED_CUSTOMER_NAME
    assert cust_after.last_name == ANONYMIZED_CUSTOMER_NAME
    assert cust_after.email == f"deleted_{customer_id}@anonymized.local"
    assert cust_after.phone is None
    assert cust_after.allergies is None  # health-adjacent PII gone
    assert cust_after.is_deleted is True
    assert cust_after.deletion_scheduled_at is None  # schedule discharged

    # Invoice SURVIVES (§147 AO) with its link still pointing at the shell.
    inv_after = await db_session.execute(
        select(Invoice).filter(Invoice.id == invoice_id)
    )
    inv = inv_after.scalar_one()
    assert inv.customer_id == customer_id
    assert float(inv.total) == 119.0

    # Art. 30 completion row written with the anonymised disposition.
    gdpr = await db_session.execute(
        select(GDPRRequest).filter(
            GDPRRequest.customer_id == customer_id,
            GDPRRequest.request_type == "erasure_cleanup",
        )
    )
    row = gdpr.scalar_one()
    assert row.status == "completed"
    assert "anonymized" in (row.notes or "")
    assert "§147 AO" in (row.notes or "")


# ---------------------------------------------------------------------------
# (b) Customer WITHOUT financial records → hard-deleted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_customer_without_financial_records_is_hard_deleted(
    db_session: AsyncSession, tmp_path: Path
):
    customer = await _mk_customer(db_session)
    customer_id = customer.id

    report = await CustomerService.hard_delete_expired_customers(
        db_session, storage_root=tmp_path
    )

    assert report.scanned == 1
    assert report.hard_deleted == [customer_id]
    assert report.anonymized == []
    assert not report.has_failures

    # Row is GONE.
    refreshed = await db_session.execute(
        select(Customer).filter(Customer.id == customer_id)
    )
    assert refreshed.scalar_one_or_none() is None

    # Completion row survives the delete (gdpr_requests has no FK to customers).
    gdpr = await db_session.execute(
        select(GDPRRequest).filter(
            GDPRRequest.customer_id == customer_id,
            GDPRRequest.request_type == "erasure_cleanup",
        )
    )
    row = gdpr.scalar_one()
    assert row.status == "completed"
    assert "hard_deleted" in (row.notes or "")


@pytest.mark.asyncio
async def test_customer_before_grace_period_is_untouched(
    db_session: AsyncSession, tmp_path: Path
):
    """A customer whose 30-day grace has NOT elapsed is not swept."""
    customer = await _mk_customer(db_session, expired=False)
    customer_id = customer.id

    report = await CustomerService.hard_delete_expired_customers(
        db_session, storage_root=tmp_path
    )

    assert report.scanned == 0
    still_there = await db_session.execute(
        select(Customer).filter(Customer.id == customer_id)
    )
    assert still_there.scalar_one_or_none() is not None


# ---------------------------------------------------------------------------
# (c) Thumbnails erased with originals during the sweep (issue #24)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cleanup_erases_order_photo_thumbnail(
    db_session: AsyncSession, admin_user, tmp_path: Path
):
    customer = await _mk_customer(db_session)
    order = await _mk_order(db_session, customer.id)

    rel_path = f"orders/{order.id}/{uuid.uuid4().hex}.jpg"
    original = tmp_path / rel_path
    original.parent.mkdir(parents=True, exist_ok=True)
    original.write_bytes(b"jpeg-original")
    thumb = original.parent / "thumbs" / f"{original.stem}.jpg"
    thumb.parent.mkdir(parents=True, exist_ok=True)
    thumb.write_bytes(b"jpeg-thumb")

    photo = OrderPhoto(order_id=order.id, file_path=rel_path, taken_by=admin_user.id)
    db_session.add(photo)
    await db_session.commit()

    assert original.exists() and thumb.exists()

    report = await CustomerService.hard_delete_expired_customers(
        db_session, storage_root=tmp_path
    )

    assert not report.has_failures
    # Both the original AND the #24 thumbnail are gone from disk.
    assert not original.exists(), "order-photo original not erased"
    assert not thumb.exists(), "order-photo thumbnail not erased (issue #24 gap)"


# ---------------------------------------------------------------------------
# (d) One customer's failure is reported, others still processed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_one_failure_is_reported_and_does_not_abort_the_sweep(
    db_session: AsyncSession, tmp_path: Path, monkeypatch
):
    """A failure processing customer A must not silently swallow — it is
    recorded in report.failures (→ nonzero CLI exit) — and customer B is
    still hard-deleted."""
    cust_a = await _mk_customer(db_session)
    cust_b = await _mk_customer(db_session)
    id_a, id_b = cust_a.id, cust_b.id

    real_has_financial = CustomerService.has_retained_financial_records

    async def _boom(db, customer_id):
        if customer_id == id_a:
            raise RuntimeError("simulated disposition failure")
        return await real_has_financial(db, customer_id)

    monkeypatch.setattr(
        CustomerService,
        "has_retained_financial_records",
        staticmethod(_boom),
    )

    report = await CustomerService.hard_delete_expired_customers(
        db_session, storage_root=tmp_path
    )

    assert report.scanned == 2
    assert report.has_failures is True
    failed_ids = [cid for cid, _ in report.failures]
    assert id_a in failed_ids
    assert "RuntimeError" in report.failures[0][1]

    # Customer A survived (its transaction rolled back); B was hard-deleted.
    a_after = await db_session.execute(select(Customer).filter(Customer.id == id_a))
    assert a_after.scalar_one_or_none() is not None
    b_after = await db_session.execute(select(Customer).filter(Customer.id == id_b))
    assert b_after.scalar_one_or_none() is None
    assert id_b in report.hard_deleted


@pytest.mark.asyncio
async def test_empty_sweep_reports_zero(db_session: AsyncSession, tmp_path: Path):
    report = await CustomerService.hard_delete_expired_customers(
        db_session, storage_root=tmp_path
    )
    assert report.scanned == 0
    assert not report.has_failures
    assert report.as_dict()["succeeded"] == 0
