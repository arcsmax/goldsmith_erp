"""W2-04 (BE-16, decision D-12): gap-free per-year document numbers.

``NumberSequenceService`` draws RE-/KV- numbers from the ``number_sequences``
counter row with one row-locking ``UPDATE ... RETURNING`` inside the
caller's transaction:

- sequential per kind and year, starting at 1;
- the year is the Europe/Berlin calendar year (00:30 on 1 January in Berlin
  is still 31 December in UTC);
- a rolled back transaction gives its number back (gap-free);
- a missing counter is seeded from the numerically highest existing number
  (string MAX would put RE-2026-9999 above RE-2026-10000);
- concurrent callers on separate sessions get distinct numbers.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from goldsmith_erp.db.models import Customer
from goldsmith_erp.db.models import Invoice as InvoiceModel
from goldsmith_erp.db.models import InvoiceStatus, NumberSequence, Order, User
from goldsmith_erp.services.number_sequence_service import (
    INVOICE_KIND,
    QUOTE_KIND,
    NumberSequenceService,
    berlin_year,
)

pytestmark = pytest.mark.asyncio

_JUNE_2026 = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)


async def _invoice_row(db, number: str) -> None:
    user = User(email=f"u{number}@x.de", hashed_password="x", role="admin")
    customer = Customer(first_name="A", last_name="B", phone="+49 1")
    db.add_all([user, customer])
    await db.flush()
    order = Order(title="t", customer_id=customer.id)
    db.add(order)
    await db.flush()
    db.add(
        InvoiceModel(
            invoice_number=number,
            order_id=order.id,
            customer_id=customer.id,
            created_by=user.id,
            status=InvoiceStatus.CANCELLED,
            due_date=datetime.utcnow() + timedelta(days=14),
        )
    )
    await db.commit()


def test_berlin_year_boundary():
    # 23:30 UTC on 31 Dec is 00:30 on 1 Jan in Berlin (CET, UTC+1).
    assert berlin_year(datetime(2026, 12, 31, 23, 30, tzinfo=timezone.utc)) == 2027
    assert berlin_year(datetime(2026, 12, 31, 22, 30, tzinfo=timezone.utc)) == 2026
    # Naive values are read as UTC (codebase convention, ADR 2026-09-25).
    assert berlin_year(datetime(2026, 12, 31, 23, 30)) == 2027


async def test_numbers_are_sequential_per_kind(db_session):
    first = await NumberSequenceService.next_number(
        db_session, INVOICE_KIND, _JUNE_2026
    )
    second = await NumberSequenceService.next_number(
        db_session, INVOICE_KIND, _JUNE_2026
    )
    quote = await NumberSequenceService.next_number(db_session, QUOTE_KIND, _JUNE_2026)
    await db_session.commit()

    assert (first, second, quote) == ("RE-2026-0001", "RE-2026-0002", "KV-2026-0001")


async def test_counter_resets_per_year(db_session):
    await NumberSequenceService.next_number(db_session, INVOICE_KIND, _JUNE_2026)
    new_year = await NumberSequenceService.next_number(
        db_session, INVOICE_KIND, datetime(2027, 1, 2, tzinfo=timezone.utc)
    )
    await db_session.commit()

    assert new_year == "RE-2027-0001"


async def test_rolled_back_number_is_reused(db_session):
    await NumberSequenceService.next_number(db_session, INVOICE_KIND, _JUNE_2026)
    await db_session.commit()

    lost = await NumberSequenceService.next_number(db_session, INVOICE_KIND, _JUNE_2026)
    await db_session.rollback()
    again = await NumberSequenceService.next_number(
        db_session, INVOICE_KIND, _JUNE_2026
    )
    await db_session.commit()

    assert lost == again == "RE-2026-0002"


async def test_missing_counter_is_seeded_numerically_from_existing_numbers(
    db_session,
):
    await _invoice_row(db_session, "RE-2026-9999")
    await _invoice_row(db_session, "RE-2026-10000")

    number = await NumberSequenceService.next_number(
        db_session, INVOICE_KIND, _JUNE_2026
    )
    await db_session.commit()

    assert number == "RE-2026-10001"
    row = (
        await db_session.execute(
            select(NumberSequence).where(
                NumberSequence.kind == INVOICE_KIND, NumberSequence.year == 2026
            )
        )
    ).scalar_one()
    assert row.last_value == 10001


async def test_ten_thousand_follows_9999(db_session):
    db_session.add(NumberSequence(kind=INVOICE_KIND, year=2026, last_value=9999))
    await db_session.commit()

    number = await NumberSequenceService.next_number(
        db_session, INVOICE_KIND, _JUNE_2026
    )

    assert number == "RE-2026-10000"


async def test_concurrent_calls_on_separate_sessions_get_distinct_numbers(
    db_session,
):
    # Counter exists (as after the migration seed); each caller commits its
    # own transaction. The row lock serialises them.
    db_session.add(NumberSequence(kind=INVOICE_KIND, year=2026, last_value=0))
    await db_session.commit()

    # Bind to the engine db_session uses (not tests.conftest by module name:
    # a second conftest import builds a table-less engine, see
    # tests/integration/test_audit_logging_middleware.py).
    factory = sessionmaker(
        bind=db_session.bind, class_=AsyncSession, expire_on_commit=False
    )

    async def _draw() -> str:
        async with factory() as session:
            number = await NumberSequenceService.next_number(
                session, INVOICE_KIND, _JUNE_2026
            )
            await asyncio.sleep(0.01)  # hold the lock across a yield
            await session.commit()
            return number

    numbers = await asyncio.gather(*(_draw() for _ in range(5)))

    assert sorted(numbers) == [f"RE-2026-{i:04d}" for i in range(1, 6)]
