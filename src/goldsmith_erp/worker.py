# src/goldsmith_erp/worker.py
"""
Background worker process (ARCH-04, ADR-2026-09-25-outbox).

Run as ``python -m goldsmith_erp.worker`` from the same image as the web
backend. It

- drains ``outbox_messages`` (customer mails) every
  ``OUTBOX_POLL_INTERVAL_SECONDS`` via ``OutboxService.run_once``;
- runs the system monitor cycle (health, disk, backups, metal prices,
  deadline/pickup/fitting scans) every ``MONITOR_INTERVAL_SECONDS`` under the
  existing PostgreSQL leader lock, so at most one process scans even if two
  workers run during a rolling restart;
- touches a heartbeat file each loop; ``--healthcheck`` exits 0 while the
  heartbeat is fresh (compose healthcheck).

Flags: ``--once`` drains one outbox batch and exits (ops / tests);
``--healthcheck`` checks the heartbeat and exits.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import signal
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional

from goldsmith_erp.core.config import settings
from goldsmith_erp.core.leader_lock import SYSTEM_MONITOR_LOCK_KEY, LeaderLease
from goldsmith_erp.core.logging import setup_logging
from goldsmith_erp.db.session import AsyncSessionLocal, engine
from goldsmith_erp.services.outbox_service import OutboxService
from goldsmith_erp.services.system_monitor import (
    MONITOR_INTERVAL_SECONDS,
    run_cycle_if_leader,
)

logger = logging.getLogger("goldsmith_erp.worker")

# Default lives in the platform temp dir (``/tmp`` inside the container) so
# the loop and ``--healthcheck`` agree without a hard-coded path (bandit B108).
HEARTBEAT_PATH = Path(
    os.environ.get(
        "WORKER_HEARTBEAT_PATH",
        str(Path(tempfile.gettempdir()) / "goldsmith-worker.heartbeat"),
    )
)
# The loop touches the heartbeat at least every poll interval; a monitor
# cycle can add a few seconds. Anything older than this means "stuck".
HEARTBEAT_MAX_AGE_SECONDS = 120.0


def _touch_heartbeat(path: Path = HEARTBEAT_PATH) -> None:
    try:
        path.write_text(str(time.time()))
    except OSError:
        logger.error("Worker heartbeat write failed", exc_info=True)


def heartbeat_is_fresh(
    path: Path = HEARTBEAT_PATH, max_age: float = HEARTBEAT_MAX_AGE_SECONDS
) -> bool:
    try:
        return (time.time() - path.stat().st_mtime) <= max_age
    except OSError:
        return False


async def _drain_outbox() -> None:
    try:
        await OutboxService.run_once(AsyncSessionLocal)
    except Exception:
        logger.error("Outbox drain failed", exc_info=True)


async def _monitor_if_due(lease: LeaderLease, last_run: float) -> float:
    now = time.monotonic()
    if now - last_run < MONITOR_INTERVAL_SECONDS:
        return last_run
    try:
        await run_cycle_if_leader(lease)
    except Exception:
        logger.error("System monitor cycle crashed", exc_info=True)
    return now


async def run_worker(stop: asyncio.Event) -> None:
    """Main loop until ``stop`` is set."""
    logger.info(
        "Worker started",
        extra={
            "outbox_mode": settings.outbox_mode,
            "poll_seconds": settings.OUTBOX_POLL_INTERVAL_SECONDS,
            "monitor_seconds": MONITOR_INTERVAL_SECONDS,
        },
    )
    lease = LeaderLease(engine, SYSTEM_MONITOR_LOCK_KEY)
    last_monitor = float("-inf")
    try:
        while not stop.is_set():
            await _drain_outbox()
            last_monitor = await _monitor_if_due(lease, last_monitor)
            _touch_heartbeat()
            try:
                await asyncio.wait_for(
                    stop.wait(), timeout=settings.OUTBOX_POLL_INTERVAL_SECONDS
                )
            except asyncio.TimeoutError:
                pass
    finally:
        await lease.release()
        logger.info("Worker stopped")


def _install_signal_handlers(stop: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(sig, stop.set)
        except NotImplementedError:  # pragma: no cover - non-POSIX
            pass


async def _main(once: bool) -> None:
    if once:
        processed = await OutboxService.run_once(AsyncSessionLocal)
        logger.info("Worker --once done", extra={"processed": processed})
        return
    stop = asyncio.Event()
    _install_signal_handlers(stop)
    await run_worker(stop)


def main(argv: Optional[list[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m goldsmith_erp.worker")
    parser.add_argument("--once", action="store_true", help="drain one batch")
    parser.add_argument(
        "--healthcheck", action="store_true", help="exit 0 if heartbeat fresh"
    )
    args = parser.parse_args(argv)
    if args.healthcheck:
        return 0 if heartbeat_is_fresh() else 1
    setup_logging()
    asyncio.run(_main(args.once))
    return 0


if __name__ == "__main__":
    sys.exit(main())
