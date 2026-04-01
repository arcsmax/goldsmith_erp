"""
Unit tests for InvoiceService (Rechnungswesen).

Tests cover:
- generate_invoice_number(): RE-YYYY-NNNN sequential format
- calculate_totals(): subtotal, 19% MwSt, Gesamtbetrag
- create_invoice_from_order(): status guard (COMPLETED/DELIVERED only)
- create_invoice_from_order(): duplicate invoice guard (409)
- Status transitions: DRAFT->SENT->PAID and PAID cannot be cancelled
"""
import pytest
from datetime import datetime, timedelta

from goldsmith_erp.services.invoice_service import InvoiceService
from goldsmith_erp.models.invoice import (
    InvoiceCreate,
    InvoiceLineItemCreate,
    InvoiceUpdate,
    MarkPaidRequest,
)
from goldsmith_erp.db.models import (
    Invoice as InvoiceModel,
    InvoiceStatus,
    InvoiceLineType,
    Order,
    OrderStatusEnum,
    Customer,
    User,
    UserRole,
    MetalType,
)
from goldsmith_erp.core.security import get_password_hash


# ---------------------------------------------------------------------------
# Helpers / local fixtures
# ---------------------------------------------------------------------------


def _future_due_date() -> datetime:
    return datetime.utcnow() + timedelta(days=30)


async def _make_user(db_session) -> User:
    user = User(
        email=f"invoice_test_{id(db_session)}@example.com",
        hashed_password=get_password_hash("pw"),
        first_name="Invoice",
        last_name="Tester",
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _make_customer(db_session) -> Customer:
    customer = Customer(
        first_name="Goldie",
        last_name="Kunde",
        email=f"goldie_{id(db_session)}@example.com",
        customer_type="private",
        is_active=True,
    )
    db_session.add(customer)
    await db_session.commit()
    await db_session.refresh(customer)
    return customer


async def _make_order(
    db_session,
    customer: Customer,
    status: OrderStatusEnum = OrderStatusEnum.COMPLETED,
    price: float = 500.0,
) -> Order:
    order = Order(
        title="Test Ring",
        description="A test order for invoice unit tests",
        customer_id=customer.id,
        status=status,
        price=price,
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)
    return order


async def _make_invoice(db_session, order: Order, user: User) -> InvoiceModel:
    """Persist an invoice row directly (bypassing service) for state-setup purposes."""
    from goldsmith_erp.db.models import InvoiceLineItem

    invoice = InvoiceModel(
        invoice_number=f"RE-2026-TEST-{id(order)}",
        order_id=order.id,
        customer_id=order.customer_id,
        created_by=user.id,
        status=InvoiceStatus.DRAFT,
        issue_date=datetime.utcnow(),
        due_date=_future_due_date(),
        subtotal=500.0,
        tax_rate=19.0,
        tax_amount=95.0,
        total=595.0,
    )
    db_session.add(invoice)
    await db_session.commit()
    await db_session.refresh(invoice)
    return invoice


# ===========================================================================
# Tests: generate_invoice_number
# ===========================================================================


@pytest.mark.asyncio
class TestGenerateInvoiceNumber:
    """Verify the RE-YYYY-NNNN sequential numbering logic."""

    async def test_first_number_of_year_is_0001(self, db_session):
        """With no existing invoices the first number must be RE-<year>-0001."""
        year = datetime.utcnow().year
        number = await InvoiceService.generate_invoice_number(db_session)

        assert number == f"RE-{year}-0001"

    async def test_format_is_re_yyyy_nnnn(self, db_session):
        """Invoice number must strictly match RE-YYYY-NNNN."""
        number = await InvoiceService.generate_invoice_number(db_session)

        parts = number.split("-")
        assert len(parts) == 3, f"Expected 3 parts, got {parts}"
        assert parts[0] == "RE"
        assert len(parts[1]) == 4 and parts[1].isdigit()   # YYYY
        assert len(parts[2]) == 4 and parts[2].isdigit()   # NNNN

    async def test_second_number_increments(self, db_session):
        """After one invoice exists, the next number increments by 1."""
        year = datetime.utcnow().year
        user = await _make_user(db_session)
        customer = await _make_customer(db_session)
        order = await _make_order(db_session, customer)

        # Insert a REAL invoice so generate_invoice_number finds existing data
        existing = InvoiceModel(
            invoice_number=f"RE-{year}-0042",
            order_id=order.id,
            customer_id=customer.id,
            created_by=user.id,
            status=InvoiceStatus.DRAFT,
            issue_date=datetime.utcnow(),
            due_date=_future_due_date(),
            subtotal=100.0,
            tax_rate=19.0,
            tax_amount=19.0,
            total=119.0,
        )
        db_session.add(existing)
        await db_session.commit()

        next_number = await InvoiceService.generate_invoice_number(db_session)
        assert next_number == f"RE-{year}-0043"

    async def test_sequence_zero_pads_to_four_digits(self, db_session):
        """Sequence must be zero-padded to exactly 4 digits (e.g. 0001, 0099)."""
        year = datetime.utcnow().year
        number = await InvoiceService.generate_invoice_number(db_session)
        seq_part = number.split("-")[-1]

        assert len(seq_part) == 4
        assert seq_part.isdigit()


# ===========================================================================
# Tests: calculate_totals
# ===========================================================================


class TestCalculateTotals:
    """Verify subtotal, MwSt, and Gesamtbetrag arithmetic."""

    def _make_item(self, quantity: float, unit_price: float) -> InvoiceLineItemCreate:
        return InvoiceLineItemCreate(
            line_type=InvoiceLineType.OTHER,
            description="Test item",
            quantity=quantity,
            unit_price=unit_price,
        )

    def test_single_item_19_percent_mwst(self):
        """One item at 100 EUR net with 19% MwSt produces correct totals."""
        items = [self._make_item(1.0, 100.0)]
        result = InvoiceService.calculate_totals(items, tax_rate=19.0)

        assert result["subtotal"] == 100.0
        assert result["tax_amount"] == 19.0
        assert result["total"] == 119.0

    def test_multiple_items_summed_correctly(self):
        """Multiple line items: subtotals are added before tax is applied."""
        items = [
            self._make_item(2.0, 50.0),   # 100 EUR
            self._make_item(1.0, 75.0),   # 75 EUR
        ]
        result = InvoiceService.calculate_totals(items, tax_rate=19.0)

        assert result["subtotal"] == 175.0
        assert result["tax_amount"] == round(175.0 * 0.19, 2)
        assert result["total"] == round(175.0 + result["tax_amount"], 2)

    def test_zero_tax_rate(self):
        """With 0% tax rate, tax_amount is 0 and total equals subtotal."""
        items = [self._make_item(1.0, 200.0)]
        result = InvoiceService.calculate_totals(items, tax_rate=0.0)

        assert result["subtotal"] == 200.0
        assert result["tax_amount"] == 0.0
        assert result["total"] == 200.0

    def test_fractional_quantities_and_prices(self):
        """Labor hours (fractional quantity) compute correctly."""
        items = [self._make_item(2.5, 75.0)]   # 187.50 EUR
        result = InvoiceService.calculate_totals(items, tax_rate=19.0)

        assert result["subtotal"] == 187.5
        assert result["tax_amount"] == round(187.5 * 0.19, 2)
        assert result["total"] == round(187.5 + result["tax_amount"], 2)

    def test_totals_rounded_to_two_decimal_places(self):
        """Results must be rounded to 2 decimal places (currency precision)."""
        # 1/3 EUR unit price produces repeating decimal
        items = [self._make_item(1.0, 1 / 3)]
        result = InvoiceService.calculate_totals(items, tax_rate=19.0)

        # All values must have at most 2 decimal places
        for key in ("subtotal", "tax_amount", "total"):
            value = result[key]
            assert round(value, 2) == value, f"{key}={value} is not 2-decimal-precise"

    def test_standard_goldsmith_invoice(self):
        """Realistic scenario: material + labor + gemstone with 19% MwSt."""
        items = [
            self._make_item(1.0, 450.0),   # Gold material
            self._make_item(3.5, 75.0),    # 3.5h labor @ 75 EUR
            self._make_item(1.0, 120.0),   # Diamond
        ]
        # subtotal = 450 + 262.5 + 120 = 832.5
        result = InvoiceService.calculate_totals(items, tax_rate=19.0)

        assert result["subtotal"] == 832.5
        assert result["tax_amount"] == round(832.5 * 0.19, 2)   # 158.175 -> 158.18
        assert result["total"] == round(832.5 + result["tax_amount"], 2)


# ===========================================================================
# Tests: create_invoice_from_order — order status guard
# ===========================================================================


@pytest.mark.asyncio
class TestCreateInvoiceOrderStatusGuard:
    """Only COMPLETED or DELIVERED orders may generate invoices."""

    async def test_completed_order_creates_invoice(self, db_session):
        """COMPLETED order must successfully create an invoice."""
        user = await _make_user(db_session)
        customer = await _make_customer(db_session)
        order = await _make_order(db_session, customer, status=OrderStatusEnum.COMPLETED)

        invoice_in = InvoiceCreate(
            order_id=order.id,
            due_date=_future_due_date(),
            tax_rate=19.0,
        )
        invoice = await InvoiceService.create_invoice_from_order(db_session, invoice_in, user)

        assert invoice is not None
        assert invoice.order_id == order.id
        assert invoice.status == InvoiceStatus.DRAFT

    async def test_delivered_order_creates_invoice(self, db_session):
        """DELIVERED order must successfully create an invoice."""
        user = await _make_user(db_session)
        customer = await _make_customer(db_session)
        order = await _make_order(db_session, customer, status=OrderStatusEnum.DELIVERED)

        invoice_in = InvoiceCreate(
            order_id=order.id,
            due_date=_future_due_date(),
            tax_rate=19.0,
        )
        invoice = await InvoiceService.create_invoice_from_order(db_session, invoice_in, user)

        assert invoice is not None

    @pytest.mark.parametrize("bad_status", [
        OrderStatusEnum.NEW,
        OrderStatusEnum.IN_PROGRESS,
    ])
    async def test_non_completed_order_raises_422(self, db_session, bad_status):
        """Orders not in COMPLETED/DELIVERED state must be rejected with 422."""
        from fastapi import HTTPException

        user = await _make_user(db_session)
        customer = await _make_customer(db_session)
        order = await _make_order(db_session, customer, status=bad_status)

        invoice_in = InvoiceCreate(
            order_id=order.id,
            due_date=_future_due_date(),
            tax_rate=19.0,
        )

        with pytest.raises(HTTPException) as exc_info:
            await InvoiceService.create_invoice_from_order(db_session, invoice_in, user)

        assert exc_info.value.status_code == 422

    async def test_nonexistent_order_raises_404(self, db_session):
        """Referencing an order that does not exist must raise 404."""
        from fastapi import HTTPException

        user = await _make_user(db_session)
        invoice_in = InvoiceCreate(
            order_id=999_999,
            due_date=_future_due_date(),
            tax_rate=19.0,
        )

        with pytest.raises(HTTPException) as exc_info:
            await InvoiceService.create_invoice_from_order(db_session, invoice_in, user)

        assert exc_info.value.status_code == 404


# ===========================================================================
# Tests: create_invoice_from_order — duplicate guard
# ===========================================================================


@pytest.mark.asyncio
class TestDuplicateInvoiceGuard:
    """An active invoice for the same order must be rejected with 409."""

    async def test_duplicate_active_invoice_raises_409(self, db_session):
        """Second invoice for the same order (non-cancelled) must be rejected."""
        from fastapi import HTTPException

        user = await _make_user(db_session)
        customer = await _make_customer(db_session)
        order = await _make_order(db_session, customer, status=OrderStatusEnum.COMPLETED)

        # First invoice — must succeed
        invoice_in = InvoiceCreate(
            order_id=order.id,
            due_date=_future_due_date(),
            tax_rate=19.0,
        )
        await InvoiceService.create_invoice_from_order(db_session, invoice_in, user)

        # Second invoice for the same order — must fail
        with pytest.raises(HTTPException) as exc_info:
            await InvoiceService.create_invoice_from_order(db_session, invoice_in, user)

        assert exc_info.value.status_code == 409

    async def test_cancelled_invoice_allows_new_invoice(self, db_session):
        """After an invoice is CANCELLED a new invoice may be created for the order."""
        user = await _make_user(db_session)
        customer = await _make_customer(db_session)
        order = await _make_order(db_session, customer, status=OrderStatusEnum.COMPLETED)

        # Create and then cancel the first invoice via the service helpers
        existing = await _make_invoice(db_session, order, user)
        existing.status = InvoiceStatus.CANCELLED
        await db_session.commit()

        # A new invoice for the same order should now succeed
        invoice_in = InvoiceCreate(
            order_id=order.id,
            due_date=_future_due_date(),
            tax_rate=19.0,
        )
        new_invoice = await InvoiceService.create_invoice_from_order(db_session, invoice_in, user)

        assert new_invoice is not None
        assert new_invoice.status == InvoiceStatus.DRAFT


# ===========================================================================
# Tests: invoice number embedded in created invoice
# ===========================================================================


@pytest.mark.asyncio
class TestInvoiceNumberOnCreate:
    """The generated invoice number must follow RE-YYYY-NNNN and be persisted."""

    async def test_created_invoice_has_correct_number_format(self, db_session):
        """Invoice created via service must carry a properly formatted number."""
        year = datetime.utcnow().year
        user = await _make_user(db_session)
        customer = await _make_customer(db_session)
        order = await _make_order(db_session, customer, status=OrderStatusEnum.COMPLETED)

        invoice_in = InvoiceCreate(
            order_id=order.id,
            due_date=_future_due_date(),
            tax_rate=19.0,
        )
        invoice = await InvoiceService.create_invoice_from_order(db_session, invoice_in, user)

        assert invoice.invoice_number.startswith(f"RE-{year}-")
        seq = invoice.invoice_number.split("-")[-1]
        assert len(seq) == 4 and seq.isdigit()


# ===========================================================================
# Tests: status transitions
# ===========================================================================


@pytest.mark.asyncio
class TestStatusTransitions:
    """Verify allowed and forbidden status transitions."""

    async def test_draft_to_sent_via_update(self, db_session):
        """DRAFT invoice can be updated to SENT status."""
        user = await _make_user(db_session)
        customer = await _make_customer(db_session)
        order = await _make_order(db_session, customer)
        invoice = await _make_invoice(db_session, order, user)

        assert invoice.status == InvoiceStatus.DRAFT

        update = InvoiceUpdate(status=InvoiceStatus.SENT)
        updated = await InvoiceService.update_invoice(db_session, invoice.id, update, user)

        assert updated is not None
        assert updated.status == InvoiceStatus.SENT

    async def test_sent_to_paid_via_mark_paid(self, db_session):
        """SENT invoice can be marked as PAID."""
        user = await _make_user(db_session)
        customer = await _make_customer(db_session)
        order = await _make_order(db_session, customer)
        invoice = await _make_invoice(db_session, order, user)
        invoice.status = InvoiceStatus.SENT
        await db_session.commit()

        paid_request = MarkPaidRequest(paid_date=None)
        paid_invoice = await InvoiceService.mark_as_paid(
            db_session, invoice.id, paid_request, user
        )

        assert paid_invoice is not None
        assert paid_invoice.status == InvoiceStatus.PAID
        assert paid_invoice.paid_date is not None

    async def test_draft_to_paid_via_mark_paid(self, db_session):
        """DRAFT invoice can also be marked as PAID directly (e.g. counter sale)."""
        user = await _make_user(db_session)
        customer = await _make_customer(db_session)
        order = await _make_order(db_session, customer)
        invoice = await _make_invoice(db_session, order, user)

        assert invoice.status == InvoiceStatus.DRAFT

        paid_request = MarkPaidRequest(paid_date=None)
        paid_invoice = await InvoiceService.mark_as_paid(
            db_session, invoice.id, paid_request, user
        )

        assert paid_invoice.status == InvoiceStatus.PAID

    async def test_paid_invoice_cannot_be_cancelled(self, db_session):
        """PAID invoice must not be cancellable — raises 422."""
        from fastapi import HTTPException

        user = await _make_user(db_session)
        customer = await _make_customer(db_session)
        order = await _make_order(db_session, customer)
        invoice = await _make_invoice(db_session, order, user)
        invoice.status = InvoiceStatus.PAID
        await db_session.commit()

        with pytest.raises(HTTPException) as exc_info:
            await InvoiceService.cancel_invoice(db_session, invoice.id, user)

        assert exc_info.value.status_code == 422

    async def test_paid_invoice_mark_paid_again_raises_422(self, db_session):
        """Attempting to mark an already-PAID invoice as paid again must raise 422."""
        from fastapi import HTTPException

        user = await _make_user(db_session)
        customer = await _make_customer(db_session)
        order = await _make_order(db_session, customer)
        invoice = await _make_invoice(db_session, order, user)
        invoice.status = InvoiceStatus.PAID
        await db_session.commit()

        with pytest.raises(HTTPException) as exc_info:
            await InvoiceService.mark_as_paid(
                db_session, invoice.id, MarkPaidRequest(paid_date=None), user
            )

        assert exc_info.value.status_code == 422

    async def test_cancelled_invoice_cannot_be_updated(self, db_session):
        """CANCELLED invoice must raise 422 on any update attempt."""
        from fastapi import HTTPException

        user = await _make_user(db_session)
        customer = await _make_customer(db_session)
        order = await _make_order(db_session, customer)
        invoice = await _make_invoice(db_session, order, user)
        invoice.status = InvoiceStatus.CANCELLED
        await db_session.commit()

        with pytest.raises(HTTPException) as exc_info:
            await InvoiceService.update_invoice(
                db_session, invoice.id, InvoiceUpdate(notes="attempt"), user
            )

        assert exc_info.value.status_code == 422

    async def test_already_cancelled_invoice_cancel_again_raises_422(self, db_session):
        """Cancelling a CANCELLED invoice must raise 422."""
        from fastapi import HTTPException

        user = await _make_user(db_session)
        customer = await _make_customer(db_session)
        order = await _make_order(db_session, customer)
        invoice = await _make_invoice(db_session, order, user)
        invoice.status = InvoiceStatus.CANCELLED
        await db_session.commit()

        with pytest.raises(HTTPException):
            await InvoiceService.cancel_invoice(db_session, invoice.id, user)

    async def test_mark_paid_records_custom_paid_date(self, db_session):
        """paid_date in MarkPaidRequest must be persisted on the invoice."""
        user = await _make_user(db_session)
        customer = await _make_customer(db_session)
        order = await _make_order(db_session, customer)
        invoice = await _make_invoice(db_session, order, user)

        specific_date = datetime(2026, 3, 28, 12, 0, 0)
        paid_request = MarkPaidRequest(paid_date=specific_date)
        paid_invoice = await InvoiceService.mark_as_paid(
            db_session, invoice.id, paid_request, user
        )

        assert paid_invoice.paid_date == specific_date
