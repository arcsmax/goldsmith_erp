"""
Regression tests for the invoice money path (audit 2026-09-25).

Covers:
- BE-01: quote conversion stores NET price on the order; invoice adds VAT once
- BE-02: invoice bills the agreed price, not the material purchase cost
- BE-03: Altgold credit is a post-tax deduction and does not crash creation
- BE-04: tz-aware due_date (browser ``toISOString()``) is accepted
- BE-17: converting a quote built from an existing order confirms that order

See docs/architecture/ADR-2026-09-25-price-semantics.md.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException

from goldsmith_erp.core.security import get_password_hash
from goldsmith_erp.db.models import (
    Customer,
    InvoiceStatus,
    Order,
    OrderStatusEnum,
    QuoteLineType,
    QuoteStatus,
    ScrapGold,
    ScrapGoldStatus,
    User,
    UserRole,
)
from goldsmith_erp.models.invoice import InvoiceCreate, InvoiceUpdate, MarkPaidRequest
from goldsmith_erp.models.quote import QuoteCreate, QuoteLineItemCreate
from goldsmith_erp.services.invoice_service import InvoiceService
from goldsmith_erp.services.quote_service import QuoteService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _future_due_date() -> datetime:
    return datetime.utcnow() + timedelta(days=30)


async def _make_user(db_session) -> User:
    user = User(
        email=f"money_path_{id(db_session)}@example.com",
        hashed_password=get_password_hash("pw"),
        first_name="Money",
        last_name="Path",
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _make_customer(db_session, suffix: str = "a") -> Customer:
    customer = Customer(
        first_name="Anna",
        last_name="Kundin",
        email=f"money_{suffix}_{id(db_session)}@example.com",
        customer_type="private",
        is_active=True,
    )
    db_session.add(customer)
    await db_session.commit()
    await db_session.refresh(customer)
    return customer


async def _make_order(db_session, customer: Customer, **fields) -> Order:
    defaults = {
        "title": "Trauring",
        "description": "Money path test order",
        "customer_id": customer.id,
        "status": OrderStatusEnum.COMPLETED,
    }
    defaults.update(fields)
    order = Order(**defaults)
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)
    return order


async def _approved_quote(db_session, user, customer, order_id=None, net=1000.0):
    quote_in = QuoteCreate(
        customer_id=customer.id,
        order_id=order_id,
        tax_rate=19.0,
        valid_days=14,
        additional_line_items=[
            QuoteLineItemCreate(
                line_type=QuoteLineType.OTHER,
                description="Trauring nach Entwurf",
                quantity=1.0,
                unit_price=net,
            )
        ],
    )
    quote = await QuoteService.create_quote(db_session, quote_in, user)
    quote.status = QuoteStatus.APPROVED
    await db_session.commit()
    return quote


# ===========================================================================
# BE-04: tz-aware datetimes
# ===========================================================================


class TestAwareDatetimes:
    def test_invoice_create_accepts_aware_due_date(self):
        aware = datetime.now(timezone.utc) + timedelta(days=14)
        invoice_in = InvoiceCreate(order_id=1, due_date=aware.isoformat())
        assert invoice_in.due_date.tzinfo is None
        assert invoice_in.due_date == aware.replace(tzinfo=None)

    def test_invoice_create_converts_offset_to_utc(self):
        berlin = timezone(timedelta(hours=2))
        local = (datetime.now(berlin) + timedelta(days=14)).replace(
            hour=10, minute=0, second=0, microsecond=0
        )
        invoice_in = InvoiceCreate(order_id=1, due_date=local)
        assert invoice_in.due_date.tzinfo is None
        assert invoice_in.due_date.hour == 8

    def test_invoice_create_still_rejects_past_aware_due_date(self):
        past = datetime.now(timezone.utc) - timedelta(days=1)
        with pytest.raises(ValueError):
            InvoiceCreate(order_id=1, due_date=past)

    def test_invoice_update_and_mark_paid_normalize_aware(self):
        aware = datetime.now(timezone.utc) + timedelta(days=3)
        assert InvoiceUpdate(due_date=aware).due_date.tzinfo is None
        assert MarkPaidRequest(paid_date=aware).paid_date.tzinfo is None


# ===========================================================================
# net_from_gross helper
# ===========================================================================


class TestNetFromGross:
    def test_exact_division(self):
        from goldsmith_erp.services.invoice_service import net_from_gross

        assert net_from_gross(1190.0, 19.0) == Decimal("1000.00")

    def test_rounds_half_up_to_cents(self):
        # 1332.99 / 1.19 = 1120.1596... -> 1120.16
        from goldsmith_erp.services.invoice_service import net_from_gross

        assert net_from_gross(1332.99, 19.0) == Decimal("1120.16")

    def test_zero_rate(self):
        from goldsmith_erp.services.invoice_service import net_from_gross

        assert net_from_gross(99.99, 0.0) == Decimal("99.99")


# ===========================================================================
# BE-01 / BE-17: quote conversion
# ===========================================================================


@pytest.mark.asyncio
class TestQuoteConversion:
    async def test_convert_writes_net_total_to_order_price(self, db_session):
        user = await _make_user(db_session)
        customer = await _make_customer(db_session)
        quote = await _approved_quote(db_session, user, customer, net=1000.0)
        assert float(quote.total) == pytest.approx(1190.0)

        converted = await QuoteService.convert_quote(db_session, quote.id, user)

        order = await db_session.get(Order, converted.order_id)
        assert float(order.price) == pytest.approx(1000.0)

    async def test_quote_convert_then_invoice_charges_vat_once(self, db_session):
        """End-to-end: 1,000 net quote -> order -> invoice total 1,190.00."""
        user = await _make_user(db_session)
        customer = await _make_customer(db_session)
        quote = await _approved_quote(db_session, user, customer, net=1000.0)
        converted = await QuoteService.convert_quote(db_session, quote.id, user)
        order = await db_session.get(Order, converted.order_id)
        order.status = OrderStatusEnum.COMPLETED
        await db_session.commit()

        invoice = await InvoiceService.create_invoice_from_order(
            db_session,
            InvoiceCreate(order_id=order.id, due_date=_future_due_date()),
            user,
        )

        assert float(invoice.subtotal) == pytest.approx(1000.0)
        assert float(invoice.tax_amount) == pytest.approx(190.0)
        assert float(invoice.total) == pytest.approx(1190.0)

    async def test_convert_quote_from_existing_order_reuses_order(self, db_session):
        user = await _make_user(db_session)
        customer = await _make_customer(db_session)
        order = await _make_order(
            db_session, customer, status=OrderStatusEnum.DRAFT, price=None
        )
        quote = await _approved_quote(
            db_session, user, customer, order_id=order.id, net=800.0
        )
        order_count_before = len(
            (await db_session.execute(Order.__table__.select())).all()
        )

        converted = await QuoteService.convert_quote(db_session, quote.id, user)

        order_count_after = len(
            (await db_session.execute(Order.__table__.select())).all()
        )
        assert converted.order_id == order.id
        assert order_count_after == order_count_before
        await db_session.refresh(order)
        assert float(order.price) == pytest.approx(800.0)
        assert order.status == OrderStatusEnum.CONFIRMED

    async def test_convert_does_not_regress_order_in_progress(self, db_session):
        user = await _make_user(db_session)
        customer = await _make_customer(db_session)
        order = await _make_order(
            db_session, customer, status=OrderStatusEnum.IN_PROGRESS
        )
        quote = await _approved_quote(db_session, user, customer, order_id=order.id)

        await QuoteService.convert_quote(db_session, quote.id, user)

        await db_session.refresh(order)
        assert order.status == OrderStatusEnum.IN_PROGRESS

    async def test_convert_expired_quote_rejected(self, db_session):
        user = await _make_user(db_session)
        customer = await _make_customer(db_session)
        quote = await _approved_quote(db_session, user, customer)
        quote.valid_until = datetime.utcnow() - timedelta(days=1)
        await db_session.commit()

        with pytest.raises(HTTPException) as exc_info:
            await QuoteService.convert_quote(db_session, quote.id, user)
        assert exc_info.value.status_code == 422

    async def test_quote_for_other_customers_order_rejected(self, db_session):
        user = await _make_user(db_session)
        customer_a = await _make_customer(db_session, "a")
        customer_b = await _make_customer(db_session, "b")
        order = await _make_order(db_session, customer_a, price=500.0)

        with pytest.raises(HTTPException) as exc_info:
            await QuoteService.create_quote(
                db_session,
                QuoteCreate(customer_id=customer_b.id, order_id=order.id),
                user,
            )
        assert exc_info.value.status_code == 422


# ===========================================================================
# BE-02: bill agreed price, not purchase cost
# ===========================================================================


@pytest.mark.asyncio
class TestInvoiceBillsAgreedPrice:
    async def test_order_price_wins_over_cost_breakdown(self, db_session):
        user = await _make_user(db_session)
        customer = await _make_customer(db_session)
        # Cost: 500 material + 4h x 75 = 800 net cost; agreed NET price 1120.
        order = await _make_order(
            db_session,
            customer,
            price=1120.0,
            material_cost_calculated=500.0,
            labor_hours=4.0,
            hourly_rate=75.0,
        )

        invoice = await InvoiceService.create_invoice_from_order(
            db_session,
            InvoiceCreate(order_id=order.id, due_date=_future_due_date()),
            user,
        )

        assert float(invoice.subtotal) == pytest.approx(1120.0)
        assert float(invoice.total) == pytest.approx(1332.80)
        assert all(li.unit_price != 500.0 for li in invoice.line_items)

    async def test_calculated_gross_price_is_converted_to_net(self, db_session):
        user = await _make_user(db_session)
        customer = await _make_customer(db_session)
        order = await _make_order(
            db_session,
            customer,
            price=None,
            calculated_price=1332.99,
            vat_rate=19.0,
            material_cost_calculated=500.0,
            labor_hours=4.0,
            hourly_rate=75.0,
        )

        invoice = await InvoiceService.create_invoice_from_order(
            db_session,
            InvoiceCreate(order_id=order.id, due_date=_future_due_date()),
            user,
        )

        assert float(invoice.subtotal) == pytest.approx(1120.16)
        assert float(invoice.total) == pytest.approx(1332.99)

    async def test_converted_quote_lines_are_billed(self, db_session):
        user = await _make_user(db_session)
        customer = await _make_customer(db_session)
        order = await _make_order(
            db_session,
            customer,
            status=OrderStatusEnum.DRAFT,
            material_cost_calculated=300.0,
        )
        quote = await _approved_quote(
            db_session, user, customer, order_id=order.id, net=950.0
        )
        await QuoteService.convert_quote(db_session, quote.id, user)
        order.status = OrderStatusEnum.COMPLETED
        await db_session.commit()

        invoice = await InvoiceService.create_invoice_from_order(
            db_session,
            InvoiceCreate(order_id=order.id, due_date=_future_due_date()),
            user,
        )

        # The quote (auto "Material" line from the order + manual line) is
        # exactly what the customer approved; the invoice bills those lines.
        assert [li.description for li in invoice.line_items] == [
            li.description for li in quote.line_items
        ]
        assert invoice.subtotal == pytest.approx(quote.subtotal)
        assert invoice.total == pytest.approx(quote.total)
        assert float(invoice.subtotal) == pytest.approx(1250.0)

    async def test_no_agreed_price_fails_loudly(self, db_session):
        user = await _make_user(db_session)
        customer = await _make_customer(db_session)
        order = await _make_order(
            db_session, customer, price=None, material_cost_calculated=500.0
        )

        with pytest.raises(HTTPException) as exc_info:
            await InvoiceService.create_invoice_from_order(
                db_session,
                InvoiceCreate(order_id=order.id, due_date=_future_due_date()),
                user,
            )
        assert exc_info.value.status_code == 422


# ===========================================================================
# BE-03: Altgold credit as post-tax deduction
# ===========================================================================


@pytest.mark.asyncio
class TestScrapGoldCredit:
    async def _signed_scrap(self, db_session, order, user, value=250.0):
        scrap = ScrapGold(
            order_id=order.id,
            customer_id=order.customer_id,
            created_by=user.id,
            status=ScrapGoldStatus.SIGNED,
            total_fine_gold_g=4.2,
            total_value_eur=value,
        )
        db_session.add(scrap)
        await db_session.commit()
        await db_session.refresh(scrap)
        return scrap

    async def test_credit_is_deducted_after_vat(self, db_session):
        user = await _make_user(db_session)
        customer = await _make_customer(db_session)
        order = await _make_order(db_session, customer, price=1000.0)
        scrap = await self._signed_scrap(db_session, order, user, value=250.0)

        invoice = await InvoiceService.create_invoice_from_order(
            db_session,
            InvoiceCreate(order_id=order.id, due_date=_future_due_date()),
            user,
        )

        # VAT base is the full sale price, the credit reduces only the payable.
        assert float(invoice.subtotal) == pytest.approx(1000.0)
        assert float(invoice.tax_amount) == pytest.approx(190.0)
        assert float(invoice.total) == pytest.approx(1190.0)
        assert float(invoice.scrap_gold_credit) == pytest.approx(250.0)
        assert float(invoice.amount_due) == pytest.approx(940.0)
        assert all(li.unit_price >= 0 for li in invoice.line_items)
        await db_session.refresh(scrap)
        assert scrap.status == ScrapGoldStatus.CREDITED

    async def test_get_invoice_reports_credit_and_amount_due(self, db_session):
        user = await _make_user(db_session)
        customer = await _make_customer(db_session)
        order = await _make_order(db_session, customer, price=1000.0)
        await self._signed_scrap(db_session, order, user, value=250.0)
        created = await InvoiceService.create_invoice_from_order(
            db_session,
            InvoiceCreate(order_id=order.id, due_date=_future_due_date()),
            user,
        )

        fetched = await InvoiceService.get_invoice(db_session, created.id, user)
        items, _ = await InvoiceService.list_invoices(db_session, user)

        assert float(fetched.amount_due) == pytest.approx(940.0)
        assert float(items[0].amount_due) == pytest.approx(940.0)

    async def test_invoice_without_scrap_gold_amount_due_equals_total(self, db_session):
        user = await _make_user(db_session)
        customer = await _make_customer(db_session)
        order = await _make_order(db_session, customer, price=100.0)

        invoice = await InvoiceService.create_invoice_from_order(
            db_session,
            InvoiceCreate(order_id=order.id, due_date=_future_due_date()),
            user,
        )

        assert float(invoice.scrap_gold_credit) == pytest.approx(0.0)
        assert invoice.amount_due == pytest.approx(invoice.total)
        assert invoice.status == InvoiceStatus.DRAFT
