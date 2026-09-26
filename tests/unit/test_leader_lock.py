# tests/unit/test_leader_lock.py
"""
Unit tests for core.leader_lock.LeaderLease (ARCH-04 / BE-09).

PostgreSQL is simulated with small fakes that record the SQL sent, so the
lease logic (acquire, keep, lose, release, degrade) is tested without a
server. The SQLite path is tested against the real dialect name.
"""

from types import SimpleNamespace
from typing import Any, List, Optional

import pytest

from goldsmith_erp.core.leader_lock import LeaderLease

pytestmark = pytest.mark.asyncio

LOCK_KEY = 4242


class _FakeResult:
    def __init__(self, value: Any) -> None:
        self._value = value

    def scalar(self) -> Any:
        return self._value


class _FakeConnection:
    def __init__(self, lock_granted: bool, fail_ping: bool = False) -> None:
        self.lock_granted = lock_granted
        self.fail_ping = fail_ping
        self.statements: List[str] = []
        self.closed = False

    async def execute(self, statement: Any, params: Optional[dict] = None) -> Any:
        sql = str(statement)
        self.statements.append(sql)
        if "pg_try_advisory_lock" in sql:
            assert params == {"key": LOCK_KEY}
            return _FakeResult(self.lock_granted)
        if "SELECT 1" in sql and self.fail_ping:
            raise ConnectionError("server closed the connection (test double)")
        return _FakeResult(True)

    async def commit(self) -> None:
        return None

    async def close(self) -> None:
        self.closed = True


class _FakeEngine:
    def __init__(self, dialect: str, connections: List[Any]) -> None:
        self.dialect = SimpleNamespace(name=dialect)
        self._connections = list(connections)
        self.connect_calls = 0

    async def connect(self) -> Any:
        self.connect_calls += 1
        conn = self._connections.pop(0)
        if isinstance(conn, Exception):
            raise conn
        return conn


async def test_non_postgres_engine_is_always_leader_without_connecting():
    engine = _FakeEngine("sqlite", [])
    lease = LeaderLease(engine, LOCK_KEY)

    assert await lease.try_acquire() is True
    assert await lease.try_acquire() is True
    assert engine.connect_calls == 0


async def test_postgres_lock_granted_keeps_dedicated_connection():
    conn = _FakeConnection(lock_granted=True)
    engine = _FakeEngine("postgresql", [conn])
    lease = LeaderLease(engine, LOCK_KEY)

    assert await lease.try_acquire() is True
    # Second call re-checks liveness on the SAME connection; it must not
    # open a new one or re-issue the lock.
    assert await lease.try_acquire() is True
    assert engine.connect_calls == 1
    assert conn.closed is False
    assert sum("pg_try_advisory_lock" in s for s in conn.statements) == 1


async def test_postgres_lock_held_elsewhere_returns_false_and_closes_connection():
    conn = _FakeConnection(lock_granted=False)
    engine = _FakeEngine("postgresql", [conn])
    lease = LeaderLease(engine, LOCK_KEY)

    assert await lease.try_acquire() is False
    assert conn.closed is True


async def test_postgres_connect_failure_returns_false_without_raising():
    engine = _FakeEngine("postgresql", [OSError("db down (test double)")])
    lease = LeaderLease(engine, LOCK_KEY)

    assert await lease.try_acquire() is False


async def test_lost_connection_drops_lease_and_reacquires():
    dead = _FakeConnection(lock_granted=True, fail_ping=True)
    fresh = _FakeConnection(lock_granted=True)
    engine = _FakeEngine("postgresql", [dead, fresh])
    lease = LeaderLease(engine, LOCK_KEY)

    assert await lease.try_acquire() is True
    # Ping on ``dead`` fails, so the lease is dropped and taken again on a
    # new connection.
    assert await lease.try_acquire() is True
    assert dead.closed is True
    assert engine.connect_calls == 2


async def test_release_unlocks_and_closes():
    conn = _FakeConnection(lock_granted=True)
    engine = _FakeEngine("postgresql", [conn])
    lease = LeaderLease(engine, LOCK_KEY)
    await lease.try_acquire()

    await lease.release()

    assert any("pg_advisory_unlock" in s for s in conn.statements)
    assert conn.closed is True


class TestSystemMonitorUsesLease:
    async def test_non_leader_worker_skips_cycle(self, monkeypatch):
        from goldsmith_erp.services import system_monitor

        runs: List[int] = []

        async def _fake_cycle() -> None:
            runs.append(1)

        monkeypatch.setattr(system_monitor, "_run_one_cycle", _fake_cycle)
        follower = LeaderLease(
            _FakeEngine("postgresql", [_FakeConnection(lock_granted=False)]),
            LOCK_KEY,
        )

        ran = await system_monitor.run_cycle_if_leader(follower)

        assert ran is False
        assert runs == []

    async def test_leader_worker_runs_cycle(self, monkeypatch):
        from goldsmith_erp.services import system_monitor

        runs: List[int] = []

        async def _fake_cycle() -> None:
            runs.append(1)

        monkeypatch.setattr(system_monitor, "_run_one_cycle", _fake_cycle)
        leader = LeaderLease(
            _FakeEngine("postgresql", [_FakeConnection(lock_granted=True)]),
            LOCK_KEY,
        )

        assert await system_monitor.run_cycle_if_leader(leader) is True
        assert await system_monitor.run_cycle_if_leader(leader) is True
        assert runs == [1, 1]
