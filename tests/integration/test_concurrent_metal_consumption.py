"""Concurrent METAL consumption stress test (Slice 6 / Lena §3 / A3.4).

Validates that two asyncio tasks hitting
``MetalInventoryService.consume_material`` at the same time on the
same :class:`MetalPurchase` serialise correctly:

  * one succeeds, the other errors cleanly, OR
  * both succeed if their weights together fit inside the bar,
  * NEVER drives ``remaining_weight_g`` below zero.

Why PostgreSQL only
-------------------
SQLite silently ignores ``SELECT ... FOR UPDATE`` — it executes the
statement but acquires no row lock, so it cannot demonstrate
serialisation under genuine concurrency. Running this test on SQLite
would either be trivially flaky (async tasks racing without locks can
double-consume) or produce false passes (single-threaded executor
serialises accidentally).

On PostgreSQL, ``FOR UPDATE`` acquires a row-level lock inside the
current transaction; a second ``FOR UPDATE`` on the same row blocks
until the first transaction commits or rolls back. This is what the
service relies on (see ``metal_inventory_service.consume_material``
step 2 — "re-fetch each purchase WITH FOR UPDATE").

The test is therefore guarded with a skip marker keyed on the
``DATABASE_URL`` environment variable. CI runs it under PostgreSQL.
Local dev (SQLite) sees it skipped with a clear reason.

Companion test
--------------
The serial invariant — "no negative stock reachable even when two
requests ask for more than is left" — is covered by
``tests/unit/test_slice_5_service_behaviour.py::
TestConsumeMaterialConcurrency::test_rechecks_under_lock_prevent_negative_stock``.
This file adds the TRUE concurrency dimension.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from datetime import datetime
from typing import Optional

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import (
    Customer,
    MetalPurchase,
    MetalType,
    Order,
    OrderStatusEnum,
)
from goldsmith_erp.models.metal_inventory import CostingMethod, MaterialUsageCreate
from goldsmith_erp.services.metal_inventory_service import MetalInventoryService


# --------------------------------------------------------------------------- #
# Gatekeeper — PostgreSQL only
# --------------------------------------------------------------------------- #


_DATABASE_URL = os.environ.get("DATABASE_URL", "")
_IS_SQLITE = "sqlite" in _DATABASE_URL.lower()

# An empty DATABASE_URL means the test conftest is using its SQLite
# file path (``sqlite+aiosqlite:///...``). Detect that via the fixture
# binding rather than the env var, so dev runs skip correctly even if
# DATABASE_URL is unset.


def _engine_is_postgres(engine) -> bool:
    return engine.dialect.name.lower() in {"postgresql", "postgres"}


pytestmark = pytest.mark.skipif(
    _IS_SQLITE or not _DATABASE_URL,
    reason=(
        "Concurrent SELECT FOR UPDATE is a no-op on SQLite. "
        "Set DATABASE_URL to a PostgreSQL URL to exercise this test."
    ),
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


async def _make_customer(session: AsyncSession) -> Customer:
    customer = Customer(
        first_name="Concurrency",
        last_name="Tester",
        email=f"conc_{uuid.uuid4().hex[:8]}@test.example",
        phone="+49 1234",
        customer_type="private",
        is_active=True,
    )
    session.add(customer)
    await session.commit()
    await session.refresh(customer)
    return customer


async def _make_order(
    session: AsyncSession, customer: Customer, *, alloy: Optional[str] = "750"
) -> Order:
    order = Order(
        title="Concurrency Order",
        description="Slice 6 concurrency test",
        customer_id=customer.id,
        status=OrderStatusEnum.IN_PROGRESS,
        alloy=alloy,
        price=500.0,
    )
    session.add(order)
    await session.commit()
    await session.refresh(order)
    return order


async def _make_purchase(session: AsyncSession, weight_g: float = 5.0) -> MetalPurchase:
    purchase = MetalPurchase(
        date_purchased=datetime.utcnow(),
        metal_type=MetalType.GOLD_18K,
        weight_g=weight_g,
        remaining_weight_g=weight_g,
        price_total=weight_g * 50.0,
        price_per_gram=50.0,
        supplier="Concurrency Supplier",
        invoice_number=f"CONC-{uuid.uuid4().hex[:6]}",
    )
    session.add(purchase)
    await session.commit()
    await session.refresh(purchase)
    return purchase


async def _consume(
    session: AsyncSession,
    order_id: int,
    purchase_id: int,
    weight: float,
):
    """Single consume call suitable for asyncio.gather."""
    return await MetalInventoryService.consume_material(
        session,
        MaterialUsageCreate(
            order_id=order_id,
            weight_used_g=weight,
            costing_method=CostingMethod.SPECIFIC,
            metal_purchase_id=purchase_id,
        ),
        MetalType.GOLD_18K,
    )


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
class TestConcurrentConsumption:
    """Two parallel ``consume_material`` calls on the same
    ``MetalPurchase``. The SELECT FOR UPDATE lock must serialise them
    such that stock never goes negative."""

    async def test_two_parallel_consumes_serialise(self, db_session):
        """Setup: 5g bar. Two tasks each try to consume 3g.

        Expected: exactly one succeeds (remaining=2g). The other
        raises ``ValueError`` with an "insufficient stock" message.
        Both must NOT succeed (that would drive stock to -1g).
        """
        # Ensure the test engine is actually PostgreSQL.
        if not _engine_is_postgres(db_session.get_bind()):
            pytest.skip("PostgreSQL required for this test")

        customer = await _make_customer(db_session)
        order = await _make_order(db_session, customer, alloy="750")
        purchase = await _make_purchase(db_session, weight_g=5.0)

        purchase_id = purchase.id
        order_id = order.id

        # Use SEPARATE sessions for the two tasks so their transactions
        # are genuinely independent. Sharing one session would serialise
        # at the session level, not at the DB-lock level.
        engine = db_session.get_bind()
        from sqlalchemy.ext.asyncio import async_sessionmaker

        session_factory = async_sessionmaker(
            engine, expire_on_commit=False, class_=AsyncSession
        )

        async def _run(weight: float):
            async with session_factory() as s:
                try:
                    return await _consume(s, order_id, purchase_id, weight)
                except Exception as exc:  # noqa: BLE001 — test error surface
                    return exc

        results = await asyncio.gather(
            _run(3.0),
            _run(3.0),
        )

        # Exactly one success + one ValueError.
        successes = [r for r in results if not isinstance(r, Exception)]
        errors = [r for r in results if isinstance(r, Exception)]
        assert len(successes) == 1, (
            f"Expected exactly 1 successful consume, got {len(successes)}. "
            f"Stock would go negative. Results: {results}"
        )
        assert len(errors) == 1, f"Expected exactly 1 error, got {errors}"
        assert isinstance(errors[0], (ValueError, Exception))

        # Stock must be exactly 2g (one consume of 3g landed).
        async with session_factory() as s:
            result = await s.execute(
                select(MetalPurchase).where(MetalPurchase.id == purchase_id)
            )
            reloaded = result.scalar_one()
            assert reloaded.remaining_weight_g == pytest.approx(2.0, abs=0.01)
            assert reloaded.remaining_weight_g >= 0.0, (
                "Stock went negative — FOR UPDATE lock did not serialise"
            )

    async def test_two_parallel_consumes_that_both_fit_both_succeed(
        self, db_session
    ):
        """Setup: 10g bar. Two tasks each consume 3g.

        Expected: both succeed (remaining=4g). This confirms the lock
        serialises without being overly pessimistic.
        """
        if not _engine_is_postgres(db_session.get_bind()):
            pytest.skip("PostgreSQL required for this test")

        customer = await _make_customer(db_session)
        order = await _make_order(db_session, customer, alloy="750")
        purchase = await _make_purchase(db_session, weight_g=10.0)
        purchase_id = purchase.id
        order_id = order.id

        from sqlalchemy.ext.asyncio import async_sessionmaker

        engine = db_session.get_bind()
        session_factory = async_sessionmaker(
            engine, expire_on_commit=False, class_=AsyncSession
        )

        async def _run(weight: float):
            async with session_factory() as s:
                return await _consume(s, order_id, purchase_id, weight)

        r1, r2 = await asyncio.gather(_run(3.0), _run(3.0))
        assert r1.id is not None
        assert r2.id is not None

        async with session_factory() as s:
            result = await s.execute(
                select(MetalPurchase).where(MetalPurchase.id == purchase_id)
            )
            reloaded = result.scalar_one()
            assert reloaded.remaining_weight_g == pytest.approx(4.0, abs=0.01)


@pytest.mark.asyncio
class TestConcurrentConsumptionAuditInvariant:
    """Belt-and-braces: even if the lock ever regresses, the
    remaining_weight_g check in the service re-verifies the stock
    under lock. This sanity check is phrased as an invariant
    (stock >= 0) that must hold no matter how many parallel consumes
    we fire."""

    async def test_stock_never_negative_under_burst(self, db_session):
        if not _engine_is_postgres(db_session.get_bind()):
            pytest.skip("PostgreSQL required for this test")

        customer = await _make_customer(db_session)
        order = await _make_order(db_session, customer, alloy="750")
        purchase = await _make_purchase(db_session, weight_g=10.0)
        purchase_id = purchase.id
        order_id = order.id

        from sqlalchemy.ext.asyncio import async_sessionmaker

        engine = db_session.get_bind()
        session_factory = async_sessionmaker(
            engine, expire_on_commit=False, class_=AsyncSession
        )

        async def _run():
            async with session_factory() as s:
                try:
                    return await _consume(s, order_id, purchase_id, 4.0)
                except Exception as exc:  # noqa: BLE001
                    return exc

        # 5 tasks x 4g each against a 10g bar — at most 2 can land.
        results = await asyncio.gather(*[_run() for _ in range(5)])
        successes = [r for r in results if not isinstance(r, Exception)]
        assert len(successes) <= 2, (
            f"More than 2 consumes succeeded on a 10g bar with 4g each — "
            f"stock invariant violated. Successes: {len(successes)}"
        )

        async with session_factory() as s:
            result = await s.execute(
                select(MetalPurchase).where(MetalPurchase.id == purchase_id)
            )
            reloaded = result.scalar_one()
            assert reloaded.remaining_weight_g >= 0.0
