# src/goldsmith_erp/core/leader_lock.py
"""
Single-runner lease for in-process background jobs (ARCH-04 / BE-09).

Production runs ``uvicorn --workers 2``, and every worker starts
``system_monitor_loop``, so scans and their side effects (staff
notifications, customer mails, metal price rows) ran once per worker.

``LeaderLease`` holds a PostgreSQL session-level advisory lock
(``pg_try_advisory_lock``) on its own connection. The worker that gets the
lock is the leader and keeps it for as long as that connection lives. The
other workers call ``try_acquire`` each cycle, get False, and skip the run.
If the leader dies or its connection drops, PostgreSQL releases the lock and
another worker takes over on its next attempt.

On a non-PostgreSQL engine (SQLite in tests and single-process dev) there is
no cross-process lock, so every caller is treated as leader.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy import text

logger = logging.getLogger(__name__)

# Stable 64-bit key for the system monitor's advisory lock. Arbitrary, but it
# must never change between releases or old and new workers would not exclude
# each other during a rolling restart.
SYSTEM_MONITOR_LOCK_KEY: int = 0x676F6C645F6D6F6E  # "gold_mon"

_TRY_LOCK_SQL = text("SELECT pg_try_advisory_lock(:key)")
_UNLOCK_SQL = text("SELECT pg_advisory_unlock(:key)")
_PING_SQL = text("SELECT 1")


class LeaderLease:
    """Advisory-lock lease. ``engine`` is an ``AsyncEngine`` (duck-typed)."""

    def __init__(self, engine: Any, key: int) -> None:
        self._engine = engine
        self._key = key
        self._conn: Optional[Any] = None

    @property
    def _is_postgres(self) -> bool:
        return bool(self._engine.dialect.name == "postgresql")

    async def try_acquire(self) -> bool:
        """Return True if this process is (still) the leader. Never raises."""
        if not self._is_postgres:
            return True
        if self._conn is not None:
            if await self._still_alive():
                return True
            logger.warning("Leader lock connection lost, re-acquiring")
            await self._drop_connection()
        return await self._acquire()

    async def release(self) -> None:
        """Release the lock (e.g. on shutdown). Never raises."""
        if self._conn is None:
            return
        try:
            await self._conn.execute(_UNLOCK_SQL, {"key": self._key})
            await self._conn.commit()
        except Exception:
            logger.error("Failed to release leader lock", exc_info=True)
        await self._drop_connection()

    async def _acquire(self) -> bool:
        try:
            conn = await self._engine.connect()
        except Exception:
            logger.error("Leader lock: could not open DB connection", exc_info=True)
            return False
        try:
            result = await conn.execute(_TRY_LOCK_SQL, {"key": self._key})
            granted = bool(result.scalar())
            # Commit so the lock connection does not sit "idle in transaction".
            # A session-level advisory lock outlives the transaction.
            await conn.commit()
        except Exception:
            logger.error("Leader lock: pg_try_advisory_lock failed", exc_info=True)
            await _close_quietly(conn)
            return False
        if not granted:
            await _close_quietly(conn)
            return False
        self._conn = conn
        logger.info("Leader lock acquired", extra={"lock_key": self._key})
        return True

    async def _still_alive(self) -> bool:
        if self._conn is None:
            return False
        try:
            await self._conn.execute(_PING_SQL)
            await self._conn.commit()
            return True
        except Exception:
            return False

    async def _drop_connection(self) -> None:
        conn, self._conn = self._conn, None
        if conn is not None:
            await _close_quietly(conn)


async def _close_quietly(conn: Any) -> None:
    try:
        await conn.close()
    except Exception:
        logger.warning("Leader lock: closing connection failed", exc_info=True)
