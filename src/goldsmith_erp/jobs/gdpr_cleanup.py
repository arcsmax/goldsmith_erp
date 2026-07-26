"""GDPR Art. 17 post-grace-period cleanup — runnable entry point.

Runs the back half of the erasure loop that ``scripts/gdpr-cleanup.sh`` was
supposed to drive but never did (production-readiness.md 2026-07-26, finding
1.3). Delegates all logic to ``CustomerService.hard_delete_expired_customers``
so the behaviour is unit-testable without spawning a process.

Invocation (inside the backend container, daily, via the systemd timer in
``deploy/systemd/``)::

    python -m goldsmith_erp.jobs.gdpr_cleanup

Exit codes:

- ``0`` — the sweep completed and every expired customer was processed
  cleanly (hard-deleted or anonymised).
- ``1`` — at least one customer failed (each failure is logged with its
  PRIMARY KEY only — never names/emails), OR a fatal error occurred
  (import failure, DB unreachable). The systemd unit's ``OnFailure=`` fires
  the alert unit, which notifies admins via the in-app notification path.

§147 AO retention overrides Art. 17 for invoices / quotes / valuation
certificates — see ``CustomerService.hard_delete_expired_customers`` and
``docs/technical/GDPR_ERASURE_RETENTION.md`` for the policy.
"""

from __future__ import annotations

import asyncio
import logging
import sys

logger = logging.getLogger("goldsmith_erp.jobs.gdpr_cleanup")


async def _run() -> "object":
    """Open a session, run the cleanup sweep, return the report.

    Imports are deferred into the coroutine so that a misconfigured
    environment surfaces as a logged fatal error (exit 1) rather than an
    import-time crash the shell wrapper cannot classify.
    """
    from goldsmith_erp.db.session import AsyncSessionLocal
    from goldsmith_erp.services.customer_service import CustomerService

    async with AsyncSessionLocal() as db:
        return await CustomerService.hard_delete_expired_customers(db)


def _report_exit_code(report: "object") -> int:
    """Map a cleanup report to a process exit code + emit the summary log.

    Pure (no I/O beyond logging) so the exit-code contract is unit-testable
    without spinning an event loop.

    Returns ``1`` when any customer failed (→ systemd ``OnFailure=`` alert),
    ``0`` otherwise.
    """
    if report.has_failures:
        failed_ids = [cid for cid, _ in report.failures]
        logger.error(
            "GDPR cleanup finished WITH FAILURES: scanned=%d succeeded=%d "
            "failed=%d failed_customer_ids=%s",
            report.scanned,
            report.succeeded,
            len(report.failures),
            failed_ids,
        )
        return 1

    logger.info(
        "GDPR cleanup finished OK: scanned=%d hard_deleted=%d anonymized=%d",
        report.scanned,
        len(report.hard_deleted),
        len(report.anonymized),
    )
    return 0


def main() -> int:
    """Entry point. Returns the process exit code (0 ok, 1 failure)."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    try:
        report = asyncio.run(_run())
    except Exception:  # noqa: BLE001 — top-level guard: log + nonzero exit
        logger.error("GDPR cleanup crashed before completing", exc_info=True)
        return 1

    return _report_exit_code(report)


if __name__ == "__main__":
    sys.exit(main())
