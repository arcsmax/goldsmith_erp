"""Real two-session concurrency tests on PostgreSQL (LV-03 follow-up, W1-17, A3.3, C2.2).

The existing race tests in this directory reproduce the race window
deterministically inside ONE session (they make the pre-check miss). These
tests open two independent ``AsyncSession`` objects on two separate
PostgreSQL connections and run the service calls at the same time with
``asyncio.gather``, so the database itself has to decide who wins:

(a) single running timer per user: two ``start_time_entry`` calls for the
    same user. Exactly one succeeds, the other gets the 409
    (``TimerAlreadyRunningError``). The barrier variant lets both calls pass
    the app-level pre-check first, so only the partial unique index
    ``uq_time_entries_one_running`` can reject the loser.
(b) quote double conversion: two ``convert_quote`` calls on the same
    APPROVED quote. Exactly one order is created. The barrier variant drops
    the ``FOR UPDATE`` lock so both calls read APPROVED, which leaves the
    compare-and-set UPDATE as the only guard; the loser must get a 409.
(c) customer-mail dedupe: two concurrent monitor ticks send one mail. With
    two workers the advisory leader lock lets only one tick run; with the
    lock bypassed (both treated as leader) the partial unique index
    ``uq_customer_updates_dedupe_key`` rejects the second row.

SQLite serialises writers and ignores ``FOR UPDATE`` and advisory locks, so
the whole module is skipped unless ``TEST_DATABASE_URL`` is PostgreSQL.
"""

from __future__ import annotations

import asyncio
import os
import secrets
from datetime import datetime, timedelta
from typing import Any, AsyncGenerator, Awaitable, Callable

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

from goldsmith_erp.core.config import settings
from goldsmith_erp.core.leader_lock import LeaderLease
from goldsmith_erp.db.models import (
    Customer,
    CustomerUpdate,
    NotificationTypeEnum,
    Order,
    OrderStatusEnum,
    Quote,
    QuoteLineType,
    QuoteStatus,
    TimeEntry,
    User,
)
from goldsmith_erp.models.quote import (
    ApproveQuoteRequest,
    QuoteCreate,
    QuoteLineItemCreate,
)
from goldsmith_erp.models.time_entry import TimeEntryStart
from goldsmith_erp.services import automated_customer_email
from goldsmith_erp.services import email_service as email_service_module
from goldsmith_erp.services import system_monitor
from goldsmith_erp.services.automated_customer_email import send_customer_mail_once
from goldsmith_erp.services.quote_service import QuoteService
from goldsmith_erp.services.time_tracking_service import (
    TimerAlreadyRunningError,
    TimeTrackingService,
)

_TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")

pytestmark = [
    pytest.mark.asyncio,
    pytest.mark.skipif(
        not _TEST_DATABASE_URL.startswith("postgresql"),
        reason=(
            "Two-session races need PostgreSQL (SQLite serialises writers and "
            "ignores FOR UPDATE and advisory locks). Set TEST_DATABASE_URL to "
            "a postgresql+asyncpg URL."
        ),
    ),
]

# Upper bound for one gathered race. A barrier whose partner never arrives
# (or a lock that is never released) fails the test instead of hanging CI.
RACE_TIMEOUT_SECONDS = 15.0

_PRICED_LINE = [
    QuoteLineItemCreate(
        line_type=QuoteLineType.LABOR,
        description="Fertigung",
        quantity=2.0,
        unit_price=75.0,
    )
]


# --------------------------------------------------------------------------- #
# Independent engine and session factory (mirrors tests/integration/conftest)
# --------------------------------------------------------------------------- #


@pytest_asyncio.fixture
async def race_engine() -> AsyncGenerator[AsyncEngine, None]:
    """A second engine on TEST_DATABASE_URL; NullPool gives each session its
    own asyncpg connection, bound to the running event loop."""
    engine = create_async_engine(
        _TEST_DATABASE_URL, poolclass=NullPool, hide_parameters=True
    )
    yield engine
    await engine.dispose()


@pytest.fixture
def session_factory(race_engine: AsyncEngine) -> sessionmaker:
    return sessionmaker(
        autocommit=False,
        autoflush=False,
        bind=race_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )


async def _race(*calls: Callable[[], Awaitable[Any]]) -> list[Any]:
    """Run the calls concurrently; return each result or raised exception."""
    return await asyncio.wait_for(
        asyncio.gather(*(call() for call in calls), return_exceptions=True),
        timeout=RACE_TIMEOUT_SECONDS,
    )


def _barrier_after(original: Callable[..., Awaitable[Any]], parties: int = 2):
    """Wrap ``original`` so every caller waits for the others after it ran.

    This forces both racers past the same check before either writes, which
    is the exact window two simultaneous HTTP requests can hit.
    """
    barrier = asyncio.Barrier(parties)

    async def _wrapped(*args: Any, **kwargs: Any) -> Any:
        result = await original(*args, **kwargs)
        await barrier.wait()
        return result

    return _wrapped


# --------------------------------------------------------------------------- #
# (a) single running timer per user (W1-17 / BE-12)
# --------------------------------------------------------------------------- #


async def _open_entries(session_factory: sessionmaker, user_id: int) -> int:
    async with session_factory() as session:
        result = await session.execute(
            select(func.count())
            .select_from(TimeEntry)
            .where(TimeEntry.user_id == user_id, TimeEntry.end_time.is_(None))
        )
        return int(result.scalar_one())


def _timer_start_calls(session_factory: sessionmaker, start: TimeEntryStart):
    async def _start() -> TimeEntry:
        async with session_factory() as session:
            return await TimeTrackingService.start_time_entry(session, start)

    return [_start, _start]


class TestTwoSessionTimerStart:
    async def test_concurrent_starts_leave_one_running_timer(
        self, db_session, session_factory, sample_user, sample_order, sample_activity
    ) -> None:
        user_id = sample_user.id
        start = TimeEntryStart(
            order_id=sample_order.id, activity_id=sample_activity.id, user_id=user_id
        )

        results = await _race(*_timer_start_calls(session_factory, start))

        winners = [r for r in results if isinstance(r, TimeEntry)]
        losers = [r for r in results if isinstance(r, TimerAlreadyRunningError)]
        assert len(winners) == 1, f"results={results!r}"
        assert len(losers) == 1, f"results={results!r}"
        assert losers[0].status_code == 409
        assert await _open_entries(session_factory, user_id) == 1

    async def test_partial_unique_index_rejects_the_lost_race(
        self,
        db_session,
        session_factory,
        sample_user,
        sample_order,
        sample_activity,
        monkeypatch,
    ) -> None:
        """Both calls pass the pre-check (no running entry yet); the index
        alone decides, and its IntegrityError becomes the 409."""
        user_id = sample_user.id
        monkeypatch.setattr(
            TimeTrackingService,
            "get_running_entry",
            staticmethod(_barrier_after(TimeTrackingService.get_running_entry)),
        )
        start = TimeEntryStart(
            order_id=sample_order.id, activity_id=sample_activity.id, user_id=user_id
        )

        results = await _race(*_timer_start_calls(session_factory, start))

        winners = [r for r in results if isinstance(r, TimeEntry)]
        losers = [r for r in results if isinstance(r, TimerAlreadyRunningError)]
        assert len(winners) == 1, f"results={results!r}"
        assert len(losers) == 1, f"results={results!r}"
        assert losers[0].status_code == 409
        assert isinstance(
            losers[0].__cause__, IntegrityError
        ), "the loser was not rejected by uq_time_entries_one_running"
        assert await _open_entries(session_factory, user_id) == 1


# --------------------------------------------------------------------------- #
# (b) quote double conversion (A3.3)
# --------------------------------------------------------------------------- #


async def _approved_quote(db_session, customer: Customer, user: User) -> int:
    quote = await QuoteService.create_quote(
        db_session,
        QuoteCreate(customer_id=customer.id, additional_line_items=_PRICED_LINE),
        user,
    )
    await QuoteService.approve_quote(
        db_session, quote.id, ApproveQuoteRequest(response_method="in_person"), user
    )
    return int(quote.id)


def _convert_calls(session_factory: sessionmaker, quote_id: int, user: User):
    async def _convert() -> Quote:
        async with session_factory() as session:
            return await QuoteService.convert_quote(session, quote_id, user)

    return [_convert, _convert]


async def _conversion_outcome(
    session_factory: sessionmaker, quote_id: int, customer_id: int
) -> tuple[Quote, int]:
    async with session_factory() as session:
        quote = (
            await session.execute(select(Quote).where(Quote.id == quote_id))
        ).scalar_one()
        orders = (
            await session.execute(
                select(func.count())
                .select_from(Order)
                .where(Order.customer_id == customer_id)
            )
        ).scalar_one()
        return quote, int(orders)


class TestTwoSessionQuoteConversion:
    async def test_concurrent_conversions_create_one_order(
        self, db_session, session_factory, admin_user, test_customer
    ) -> None:
        """With the FOR UPDATE lock the second call waits, then re-reads the
        quote as CONVERTED and is refused by the status check (422)."""
        user, customer_id = admin_user, test_customer.id
        quote_id = await _approved_quote(db_session, test_customer, user)

        results = await _race(*_convert_calls(session_factory, quote_id, user))

        winners = [r for r in results if isinstance(r, Quote)]
        losers = [r for r in results if isinstance(r, HTTPException)]
        assert len(winners) == 1, f"results={results!r}"
        assert len(losers) == 1, f"results={results!r}"
        # Observed on PG 15: 422 (status re-read after the lock wait). A 409
        # would be equally correct; what matters is one order.
        assert losers[0].status_code in (409, 422), losers[0].detail
        quote, order_count = await _conversion_outcome(
            session_factory, quote_id, customer_id
        )
        assert quote.status == QuoteStatus.CONVERTED
        assert order_count == 1
        assert quote.order_id == winners[0].order_id

    async def test_compare_and_set_alone_yields_one_order_and_409(
        self, db_session, session_factory, admin_user, test_customer, monkeypatch
    ) -> None:
        """Without the row lock both calls read APPROVED; the compare-and-set
        UPDATE (APPROVED -> CONVERTED) lets exactly one through."""
        user, customer_id = admin_user, test_customer.id
        quote_id = await _approved_quote(db_session, test_customer, user)

        original_load = QuoteService._load_quote
        barrier = asyncio.Barrier(2)

        async def _load_without_lock(db, qid, for_update=False):
            quote = await original_load(db, qid, for_update=False)
            if for_update:
                await barrier.wait()
            return quote

        monkeypatch.setattr(
            QuoteService, "_load_quote", staticmethod(_load_without_lock)
        )

        results = await _race(*_convert_calls(session_factory, quote_id, user))

        winners = [r for r in results if isinstance(r, Quote)]
        losers = [r for r in results if isinstance(r, HTTPException)]
        assert len(winners) == 1, f"results={results!r}"
        assert len(losers) == 1, f"results={results!r}"
        assert losers[0].status_code == 409, losers[0].detail
        quote, order_count = await _conversion_outcome(
            session_factory, quote_id, customer_id
        )
        assert quote.status == QuoteStatus.CONVERTED
        assert order_count == 1


# --------------------------------------------------------------------------- #
# (c) customer-mail dedupe across two monitor ticks (BE-09 / C2.2)
# --------------------------------------------------------------------------- #


class _SmtpDouble:
    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, msg: Any, **kwargs: Any) -> None:
        self.calls += 1


@pytest.fixture
def smtp(monkeypatch) -> _SmtpDouble:
    monkeypatch.setattr(settings, "EMAIL_NOTIFICATIONS_ENABLED", True)
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test.local")
    monkeypatch.setattr(settings, "SMTP_FROM", "werkstatt@test.local")
    monkeypatch.setattr(settings, "SMTP_USER", None)
    monkeypatch.setattr(settings, "SMTP_PASSWORD", None)
    double = _SmtpDouble()
    monkeypatch.setattr(email_service_module.aiosmtplib, "send", double)
    return double


@pytest_asyncio.fixture
async def completed_order(db_session, test_customer, admin_user) -> Order:
    """A completed order; admin_user is the system actor for the mail."""
    order = Order(
        title="Ring Parallel-Tick",
        customer_id=test_customer.id,
        status=OrderStatusEnum.COMPLETED,
        completed_at=datetime.utcnow() - timedelta(days=4),
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)
    return order


def _mail_tick(session_factory: sessionmaker, order_id: int):
    """One monitor tick's customer-mail step on its own session."""

    async def _tick() -> bool:
        async with session_factory() as session:
            order = (
                await session.execute(select(Order).where(Order.id == order_id))
            ).scalar_one()
            return await send_customer_mail_once(
                session, order, NotificationTypeEnum.PICKUP_READY
            )

    return _tick


async def _mail_rows(session_factory: sessionmaker, order_id: int) -> int:
    async with session_factory() as session:
        result = await session.execute(
            select(func.count())
            .select_from(CustomerUpdate)
            .where(CustomerUpdate.order_id == order_id)
        )
        return int(result.scalar_one())


class TestTwoTickCustomerMail:
    async def test_leader_lock_lets_one_of_two_workers_tick(
        self,
        db_session,
        race_engine,
        session_factory,
        smtp,
        completed_order,
        monkeypatch,
    ) -> None:
        order_id = completed_order.id
        tick = _mail_tick(session_factory, order_id)

        async def _cycle() -> None:
            await tick()

        monkeypatch.setattr(system_monitor, "_run_one_cycle", _cycle)
        # Private key per run: never contend with a real monitor on this DB.
        lock_key = secrets.randbelow(2**62) + 1
        worker_a = LeaderLease(race_engine, lock_key)
        worker_b = LeaderLease(race_engine, lock_key)
        try:
            ran = await _race(
                lambda: system_monitor.run_cycle_if_leader(worker_a),
                lambda: system_monitor.run_cycle_if_leader(worker_b),
            )
        finally:
            await worker_a.release()
            await worker_b.release()

        assert sorted(ran) == [False, True], f"ran={ran!r}"
        assert smtp.calls == 1
        assert await _mail_rows(session_factory, order_id) == 1

    async def test_unique_index_dedupes_two_ticks_that_both_pass_the_check(
        self, db_session, session_factory, smtp, completed_order, monkeypatch
    ) -> None:
        """Leader lock bypassed (e.g. during a failover both think they lead):
        both ticks see "not handled yet"; the index keeps it to one mail."""
        order_id = completed_order.id
        monkeypatch.setattr(
            automated_customer_email,
            "_already_handled",
            _barrier_after(automated_customer_email._already_handled),
        )
        tick = _mail_tick(session_factory, order_id)

        results = await _race(tick, tick)

        assert sorted(results) == [False, True], f"results={results!r}"
        assert smtp.calls == 1
        assert await _mail_rows(session_factory, order_id) == 1
