"""
C2 — Adversarial tests for the leader lock (core/leader_lock.py, ARCH-04/BE-09)
under concurrent monitor ticks.

core/leader_lock.py's own docstring says it plainly: "On a non-PostgreSQL
engine (SQLite in tests and single-process dev) there is no cross-process
lock, so every caller is treated as leader." tests/unit/test_leader_lock.py
already unit-tests LeaderLease in isolation (mocked engines/dialects) very
thoroughly. What is NOT tested anywhere: what actually happens end-to-end
when two "workers" race a real monitor tick against the SAME SQLite database
— which is exactly the deployment misconfiguration the leader lock exists to
protect against (`uvicorn --workers 2` pointed at SQLite instead of
Postgres). No code anywhere refuses to boot / warns operators about that
combination.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from goldsmith_erp.core.config import settings
from goldsmith_erp.core.leader_lock import SYSTEM_MONITOR_LOCK_KEY, LeaderLease
from goldsmith_erp.core.security import get_password_hash
from goldsmith_erp.db.models import (
    Customer,
    CustomerUpdate,
    Order,
    OrderStatusEnum,
    User,
    UserRole,
)
from goldsmith_erp.services import email_service as email_service_module
from goldsmith_erp.services.notification_service import NotificationService
from tests.conftest import test_engine as _test_engine

pytestmark = pytest.mark.asyncio


class _CapturingSend:
    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, msg, **kwargs):
        self.calls += 1
        return None


@pytest.fixture(autouse=True)
def _enable_email(monkeypatch):
    monkeypatch.setattr(settings, "EMAIL_NOTIFICATIONS_ENABLED", True)
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test.local")
    monkeypatch.setattr(settings, "SMTP_FROM", "werkstatt@test.local")
    monkeypatch.setattr(settings, "SMTP_USER", None)
    monkeypatch.setattr(settings, "SMTP_PASSWORD", None)
    monkeypatch.setattr(email_service_module.aiosmtplib, "send", _CapturingSend())


class TestSqliteLeaderLockIsAlwaysGrantedToEveryWorker:
    async def test_two_leases_on_the_sqlite_test_engine_are_both_leader(self):
        """Documents the exact gap: on the SQLite engine this whole test
        suite runs on, TWO independent LeaderLease instances (standing in
        for two uvicorn workers) both get try_acquire() == True — there is
        no mutual exclusion at all. Nothing in main.py / leader_lock.py
        checks the DB dialect at startup and refuses/warns when
        workers > 1 with a non-Postgres engine, so this misconfiguration
        fails silently rather than fails loudly (CLAUDE.md: "Fail loudly —
        never swallow exceptions silently... provide user-friendly error
        messages")."""
        lease_a = LeaderLease(_test_engine, SYSTEM_MONITOR_LOCK_KEY)
        lease_b = LeaderLease(_test_engine, SYSTEM_MONITOR_LOCK_KEY)

        granted_a, granted_b = await asyncio.gather(
            lease_a.try_acquire(), lease_b.try_acquire()
        )

        assert granted_a is True
        assert granted_b is True, (
            "SQLite provides NO cross-worker mutual exclusion for the "
            "system monitor lease — both workers believe they are leader. "
            "This is documented as intentional for 'tests and single-"
            "process dev' in core/leader_lock.py, but nothing prevents a "
            "real multi-worker deployment from being pointed at SQLite by "
            "mistake and silently double-running every scan."
        )


class TestConcurrentMonitorTicksWithoutTheLock:
    async def test_two_concurrent_pickup_reminder_scans_send_customer_mail_twice(
        self,
    ):
        """The leader lock is what is SUPPOSED to prevent this. With it
        defeated (SQLite, as above — or simply two workers racing before
        either takes the advisory lock on Postgres, since the lock is taken
        once per process at loop-start, not around every single tick), the
        _already_handled check-then-act pattern in
        automated_customer_email.py has NO database-level backstop: there
        is no unique constraint on
        (CustomerUpdate.order_id, CustomerUpdate.kind[, subject]). Two
        genuinely concurrent ticks (two independent DB sessions, exactly
        what two workers would each hold) can both pass the "not already
        handled" check before either commits, and the customer receives the
        automated mail twice for one event — precisely the bug (BE-09/
        DOM-10) this whole fix wave exists to prevent, reintroduced by
        concurrency rather than by a per-staff-user loop."""
        SessionLocal = sessionmaker(
            bind=_test_engine, class_=AsyncSession, expire_on_commit=False
        )

        async with SessionLocal() as setup:
            admin = User(
                email=f"leader_lock_admin_{uuid.uuid4().hex[:8]}@example.com",
                hashed_password=get_password_hash("pw"),
                first_name="Admin",
                last_name="LeaderLock",
                role=UserRole.ADMIN,
                is_active=True,
            )
            setup.add(admin)
            customer = Customer(
                first_name="Anna",
                last_name="Kundin",
                email=f"leader_lock_cust_{uuid.uuid4().hex[:8]}@example.com",
                customer_type="private",
                is_active=True,
            )
            setup.add(customer)
            await setup.commit()
            await setup.refresh(customer)

            order = Order(
                title="Concurrent Tick Test Auftrag",
                description="adversarial",
                customer_id=customer.id,
                status=OrderStatusEnum.COMPLETED,
                completed_at=datetime.utcnow() - timedelta(days=4),
            )
            setup.add(order)
            await setup.commit()
            await setup.refresh(order)
            order_id = order.id

        async def _tick():
            async with SessionLocal() as session:
                try:
                    return await NotificationService.check_pickup_reminders(session)
                except Exception as exc:  # pragma: no cover - diagnostic
                    return f"error:{type(exc).__name__}:{exc}"

        await asyncio.gather(_tick(), _tick())

        async with SessionLocal() as verify:
            from sqlalchemy import select

            rows = (
                await verify.execute(
                    select(CustomerUpdate).where(CustomerUpdate.order_id == order_id)
                )
            ).scalars().all()

        assert len(rows) == 1, (
            f"expected exactly one CustomerUpdate (one customer email) for "
            f"order {order_id} after two concurrent monitor ticks, found "
            f"{len(rows)} — the customer was mailed {len(rows)} time(s) for "
            "a single pickup-ready event because nothing serializes "
            "concurrent ticks below the (absent, on SQLite) leader lock."
        )
