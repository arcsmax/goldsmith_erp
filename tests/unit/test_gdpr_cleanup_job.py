"""Unit tests for the GDPR cleanup CLI exit-code contract.

Focus: ``_report_exit_code`` turns a per-customer failure into a nonzero
process exit (so the systemd ``OnFailure=`` alert fires). Tested against the
pure helper — NOT ``main()`` — so no event loop is spun up here (calling
``asyncio.run`` inside a shared pytest session corrupts the integration
suite's session-scoped loop). The sweep logic itself is covered by
tests/integration/test_gdpr_cleanup_hard_delete.py.
"""

from __future__ import annotations

from goldsmith_erp.jobs.gdpr_cleanup import _report_exit_code
from goldsmith_erp.services.customer_service import CustomerCleanupReport


def test_exit_code_zero_on_clean_report():
    report = CustomerCleanupReport(scanned=2, hard_deleted=[1], anonymized=[2])
    assert _report_exit_code(report) == 0


def test_exit_code_one_when_a_customer_failed():
    report = CustomerCleanupReport(scanned=2, hard_deleted=[1])
    report.failures.append((99, "RuntimeError: boom"))
    assert _report_exit_code(report) == 1


def test_exit_code_zero_on_empty_sweep():
    assert _report_exit_code(CustomerCleanupReport(scanned=0)) == 0
