"""
A2 — Adversarial tests for the Altgold (scrap gold) post-tax credit.

Target: InvoiceService._set_payment_summary / _attach_payment_summaries /
_scrap_gold_credit_amount (audit 2026-09-25, ADR-2026-09-25-price-semantics
decision 3: "the credit is a POST-TAX deduction ... amount_due = total -
credit ... not floored, so nothing is hidden").
"""

from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException

from goldsmith_erp.core.security import get_password_hash
from goldsmith_erp.db.models import (
    Customer,
    InvoiceStatus,
    Order,
    OrderStatusEnum,
    ScrapGold,
    ScrapGoldStatus,
    User,
    UserRole,
)
from goldsmith_erp.models.invoice import InvoiceCreate
from goldsmith_erp.services.invoice_service import InvoiceService

pytestmark = pytest.mark.asyncio


def _future_due_date() -> datetime:
    return datetime.utcnow() + timedelta(days=30)


async def _make_user(db_session, suffix: str) -> User:
    user = User(
        email=f"altgold_{suffix}_{id(db_session)}@example.com",
        hashed_password=get_password_hash("pw"),
        first_name="Altgold",
        last_name="Test",
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _make_customer(db_session, suffix: str) -> Customer:
    customer = Customer(
        first_name="Anna",
        last_name="Kundin",
        email=f"altgold_cust_{suffix}_{id(db_session)}@example.com",
        customer_type="private",
        is_active=True,
    )
    db_session.add(customer)
    await db_session.commit()
    await db_session.refresh(customer)
    return customer


async def _make_order(db_session, customer, price: float) -> Order:
    order = Order(
        title="Altgold Test Auftrag",
        description="adversarial",
        customer_id=customer.id,
        status=OrderStatusEnum.COMPLETED,
        price=price,
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)
    return order


async def _make_scrap(db_session, order, user, value: float) -> ScrapGold:
    scrap = ScrapGold(
        order_id=order.id,
        customer_id=order.customer_id,
        created_by=user.id,
        status=ScrapGoldStatus.SIGNED,
        total_fine_gold_g=1.0,
        total_value_eur=value,
    )
    db_session.add(scrap)
    await db_session.commit()
    await db_session.refresh(scrap)
    return scrap


class TestCreditLargerThanGross:
    async def test_amount_due_goes_negative_and_is_not_floored(self, db_session):
        """ADR decision 3 says this is intentional: the workshop owes the
        customer the difference and it must not be hidden. Confirm the
        actual field is negative, present, and not clamped to zero."""
        user = await _make_user(db_session, "a")
        customer = await _make_customer(db_session, "a")
        order = await _make_order(db_session, customer, price=100.0)
        # Gross = 119.00 (100 net + 19% VAT). Credit far exceeds it.
        await _make_scrap(db_session, order, user, value=5000.0)

        invoice = await InvoiceService.create_invoice_from_order(
            db_session,
            InvoiceCreate(order_id=order.id, due_date=_future_due_date()),
            user,
        )

        assert invoice.total == pytest.approx(119.0)
        assert invoice.scrap_gold_credit == pytest.approx(5000.0)
        assert invoice.amount_due == pytest.approx(119.0 - 5000.0)
        assert invoice.amount_due < 0, (
            "amount_due should go negative (workshop owes customer) rather "
            "than being floored/hidden at 0 — ADR-2026-09-25 decision 3"
        )


class TestTwoSignedScrapGoldRecordsSum:
    async def test_credit_sums_across_multiple_signed_records(self, db_session):
        user = await _make_user(db_session, "b")
        customer = await _make_customer(db_session, "b")
        order = await _make_order(db_session, customer, price=1000.0)
        await _make_scrap(db_session, order, user, value=100.0)
        await _make_scrap(db_session, order, user, value=50.5)

        invoice = await InvoiceService.create_invoice_from_order(
            db_session,
            InvoiceCreate(order_id=order.id, due_date=_future_due_date()),
            user,
        )

        assert invoice.scrap_gold_credit == pytest.approx(150.5)
        assert invoice.amount_due == pytest.approx(invoice.total - 150.5)


class TestCancelledInvoiceCreditIsZero:
    async def test_cancelled_invoice_reports_zero_credit_on_reread(self, db_session):
        user = await _make_user(db_session, "c")
        customer = await _make_customer(db_session, "c")
        order = await _make_order(db_session, customer, price=500.0)
        await _make_scrap(db_session, order, user, value=75.0)

        invoice = await InvoiceService.create_invoice_from_order(
            db_session,
            InvoiceCreate(order_id=order.id, due_date=_future_due_date()),
            user,
        )
        assert invoice.scrap_gold_credit == pytest.approx(75.0)

        await InvoiceService.cancel_invoice(db_session, invoice.id, user)
        reread = await InvoiceService.get_invoice(db_session, invoice.id, user)

        assert reread.status == InvoiceStatus.CANCELLED
        assert reread.scrap_gold_credit == 0.0, (
            "A cancelled invoice must not keep reporting a live Altgold "
            "credit (it was never paid out against this document)"
        )
        assert reread.amount_due == pytest.approx(reread.total)


class TestCancelledInvoiceCreditReapplication:
    async def test_cancelling_then_recreating_invoice_reapplies_same_credit(
        self, db_session
    ):
        """Cancelling an invoice does not revert the underlying ScrapGold
        status back to SIGNED. A replacement invoice for the same order
        picks up the same (still CREDITED) scrap gold record again — by
        design, per _get_scrap_gold_credit's docstring ("idempotent
        re-generation of a cancelled invoice does not silently drop an
        already-applied credit"). This documents that a workshop can get a
        fresh, payable invoice with the credit intact after voiding a
        mistaken one — not a double-credit, since the cancelled invoice's
        own amount_due reads back as the full total (see test above)."""
        user = await _make_user(db_session, "d")
        customer = await _make_customer(db_session, "d")
        order = await _make_order(db_session, customer, price=200.0)
        scrap = await _make_scrap(db_session, order, user, value=40.0)

        first = await InvoiceService.create_invoice_from_order(
            db_session,
            InvoiceCreate(order_id=order.id, due_date=_future_due_date()),
            user,
        )
        await InvoiceService.cancel_invoice(db_session, first.id, user)
        await db_session.refresh(scrap)
        assert scrap.status == ScrapGoldStatus.CREDITED

        second = await InvoiceService.create_invoice_from_order(
            db_session,
            InvoiceCreate(order_id=order.id, due_date=_future_due_date()),
            user,
        )

        assert second.scrap_gold_credit == pytest.approx(40.0)
        assert second.amount_due == pytest.approx(second.total - 40.0)
