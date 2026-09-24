"""
A3 — Adversarial tests for quote -> order conversion.

Target: QuoteService.convert_quote (audit 2026-09-25, BE-01/BE-17,
ADR-2026-09-25-price-semantics decision 6).

Already covered by tests/unit/test_invoice_money_path.py::TestQuoteConversion
(expired quote rejected, quote-for-other-customer's-order rejected AT
CREATION TIME, reuse of existing order). These tests probe what that
coverage does not: an empty/zero quote reaching CONVERTED, sequential and
concurrent double-conversion, and whether the same-customer invariant is
re-checked at CONVERSION time (not just at quote creation time).
"""

import asyncio
from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from goldsmith_erp.core.security import get_password_hash
from goldsmith_erp.db.models import (
    Customer,
    Order,
    OrderStatusEnum,
    QuoteStatus,
    User,
    UserRole,
)
from goldsmith_erp.models.quote import ApproveQuoteRequest, QuoteCreate
from goldsmith_erp.services.quote_service import QuoteService

pytestmark = pytest.mark.asyncio


async def _make_user(db_session, suffix: str) -> User:
    user = User(
        email=f"quoteconv_{suffix}_{id(db_session)}@example.com",
        hashed_password=get_password_hash("pw"),
        first_name="Quote",
        last_name="Conv",
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
        email=f"quoteconv_cust_{suffix}_{id(db_session)}@example.com",
        customer_type="private",
        is_active=True,
    )
    db_session.add(customer)
    await db_session.commit()
    await db_session.refresh(customer)
    return customer


class TestEmptyQuoteConversion:
    @pytest.mark.xfail(
        strict=True,
        reason="tracked: A3.1 — fixed by W2-05 quote agent",
    )
    async def test_zero_subtotal_quote_converts_to_zero_price_confirmed_order(
        self, db_session
    ):
        """Quote creation deliberately allows zero line items (quote_service.py
        create_quote: "A quote with no line items is valid (DRAFT) but note
        it explicitly" — logged, not blocked). convert_quote applies NO
        equivalent guard: it happily confirms a real order at price=0.0,
        with no warning and no error, unlike create_invoice_from_order which
        raises 422 rather than billing 0/nothing for the exact same
        "no agreed price" situation. Expectation: converting a quote that
        was never given a price should fail the same way invoicing does.
        """
        user = await _make_user(db_session, "empty")
        customer = await _make_customer(db_session, "empty")

        quote = await QuoteService.create_quote(
            db_session,
            QuoteCreate(customer_id=customer.id),  # no order_id, no line items
            user,
        )
        assert quote.subtotal == 0.0

        await QuoteService.approve_quote(
            db_session, quote.id, ApproveQuoteRequest(), user
        )

        with pytest.raises(HTTPException) as exc_info:
            await QuoteService.convert_quote(db_session, quote.id, user)
        assert exc_info.value.status_code == 422, (
            "convert_quote silently confirmed a real order at price=0.0 for "
            "a quote with no line items and no agreed price — "
            "src/goldsmith_erp/services/quote_service.py convert_quote does "
            "not apply the same 'no agreed price -> fail loudly' rule that "
            "InvoiceService.create_invoice_from_order enforces "
            "(ADR-2026-09-25-price-semantics decision 2)."
        )


class TestDoubleConversion:
    async def test_sequential_second_conversion_fails_cleanly(self, db_session):
        user = await _make_user(db_session, "seq")
        customer = await _make_customer(db_session, "seq")
        quote = await QuoteService.create_quote(
            db_session,
            QuoteCreate(customer_id=customer.id),
            user,
        )
        await QuoteService.approve_quote(
            db_session, quote.id, ApproveQuoteRequest(), user
        )
        await QuoteService.convert_quote(db_session, quote.id, user)

        with pytest.raises(HTTPException) as exc_info:
            await QuoteService.convert_quote(db_session, quote.id, user)
        assert exc_info.value.status_code == 422

    @pytest.mark.xfail(
        strict=True,
        reason="tracked: A3.3 — fixed by W2-05 quote agent",
    )
    async def test_concurrent_double_conversion_only_one_order_created(
        self, db_session: AsyncSession
    ):
        """Two 'staff members' hit convert on the same APPROVED quote at the
        same time. convert_quote takes a SELECT ... FOR UPDATE lock before
        checking status, so this should serialize: exactly one call must
        succeed and the quote must end up CONVERTED exactly once, never with
        two orders created for one quote.
        """
        user = await _make_user(db_session, "race")
        customer = await _make_customer(db_session, "race")
        quote = await QuoteService.create_quote(
            db_session,
            QuoteCreate(customer_id=customer.id),
            user,
        )
        await QuoteService.approve_quote(
            db_session, quote.id, ApproveQuoteRequest(), user
        )
        quote_id = quote.id

        # Two independent sessions against the same underlying (file-backed
        # SQLite) database, to genuinely race two DB transactions.
        from tests.conftest import test_engine as _test_engine

        SessionLocal = sessionmaker(
            bind=_test_engine, class_=AsyncSession, expire_on_commit=False
        )

        async def _attempt():
            async with SessionLocal() as session:
                try:
                    await QuoteService.convert_quote(session, quote_id, user)
                    return "ok"
                except HTTPException as exc:
                    return exc.status_code
                except Exception as exc:  # database-is-locked etc.
                    return f"error:{type(exc).__name__}:{exc}"

        results = await asyncio.gather(_attempt(), _attempt())

        successes = [r for r in results if r == "ok"]
        assert len(successes) == 1, (
            f"expected exactly one winning conversion, got results={results} "
            "(a race here would mean two orders created for one quote, or "
            "the quote's order_id silently overwritten)"
        )

        # Verify final state: exactly one CONFIRMED order references this
        # quote's order_id, not two.
        async with SessionLocal() as session:
            from goldsmith_erp.db.models import Quote as QuoteModel

            final_quote = (
                await session.execute(
                    select(QuoteModel).where(QuoteModel.id == quote_id)
                )
            ).scalar_one()
            assert final_quote.status == QuoteStatus.CONVERTED
            order_count = (
                await session.execute(
                    select(Order).where(Order.customer_id == customer.id)
                )
            ).scalars().all()
            assert len(order_count) == 1, (
                f"expected exactly 1 order for this customer after the race, "
                f"found {len(order_count)}"
            )


class TestCustomerDriftNotRevalidatedAtConversion:
    @pytest.mark.xfail(
        strict=True,
        reason="tracked: A3.4 — fixed by W2-05 quote agent",
    )
    async def test_order_reassigned_to_other_customer_after_quote_creation(
        self, db_session
    ):
        """create_quote enforces order.customer_id == quote.customer_id, but
        only at creation time. convert_quote re-loads the linked order and
        writes target_order.price / target_order.status without re-checking
        that invariant. If the order's customer_id ever drifts after the
        quote was created (there's no customer-reassignment endpoint today,
        so this simulates a future regression / direct-write bug elsewhere),
        convert_quote will silently price and confirm the WRONG customer's
        order. This is a defense-in-depth gap, not a live exploit today.
        """
        user = await _make_user(db_session, "drift")
        customer_a = await _make_customer(db_session, "drift-a")
        customer_b = await _make_customer(db_session, "drift-b")

        order = Order(
            title="Drift Auftrag",
            description="adversarial",
            customer_id=customer_a.id,
            status=OrderStatusEnum.NEW,
        )
        db_session.add(order)
        await db_session.commit()
        await db_session.refresh(order)

        quote = await QuoteService.create_quote(
            db_session,
            QuoteCreate(customer_id=customer_a.id, order_id=order.id),
            user,
        )
        await QuoteService.approve_quote(
            db_session, quote.id, ApproveQuoteRequest(), user
        )

        # Simulate drift: the order now belongs to a different customer.
        order.customer_id = customer_b.id
        db_session.add(order)
        await db_session.commit()

        with pytest.raises(HTTPException) as exc_info:
            await QuoteService.convert_quote(db_session, quote.id, user)
        assert exc_info.value.status_code == 422, (
            "convert_quote priced and confirmed an order that no longer "
            "belongs to the quote's customer, with no re-validation at "
            "conversion time (quote_service.py QuoteService.convert_quote — "
            "create_quote checks quote.customer_id == order.customer_id "
            "only once, at creation; convert_quote never re-checks it "
            "before writing price/status onto the linked order). Not "
            "reachable via any endpoint today (no order re-assignment "
            "route exists), but a defense-in-depth gap: the same invariant "
            "create_quote enforces should hold at conversion time too, in "
            "case a future feature or bug ever lets an order's customer_id "
            "change after a quote references it."
        )

        await db_session.refresh(order)
