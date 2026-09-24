"""
Unit tests for the DATEV / lexoffice accounting export (BE-13, W1-09).

See docs/review/2026-09-25/03-backend-correctness.md#be-13 and
docs/review/2026-09-25/MASTER-FIX-PLAN.md (W1-09) for the finding and fix
packet this covers.

Covers:
- DRAFT invoices are never booked (no legal document was ever issued).
- SENT / PAID invoices are booked as normal revenue (Haben).
- A CANCELLED invoice passed via ``reversal_invoices`` produces a Storno
  (reversal) booking instead of being silently dropped — the original bug
  caused the accountant to over-file VAT because a real cancellation was
  never reversed.
- The revenue account is chosen per VAT rate from a typed settings mapping;
  an unmapped rate fails loudly instead of booking to the wrong account.
- Amounts are Decimal-rounded to the cent (never float / banker's rounding).
- The DATEV header's created-date is computed fresh on every call.

Invoice fixtures are plain ``SimpleNamespace`` objects (not ORM instances) —
the export service is a pure formatter with no DB dependency, so it must
work from any object exposing the handful of attributes it reads.
"""

from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from goldsmith_erp.db.models import InvoiceStatus
from goldsmith_erp.services.accounting_export_service import (
    AccountingExportError,
    export_datev_csv,
    export_lexoffice_csv,
)

DEFAULT_ACCOUNTS = {"19": "8400", "7": "8300", "0": "8200"}
RECEIVABLES_ACCOUNT = "1400"


def _invoice(
    *,
    invoice_number: str = "RE-2026-0001",
    status=InvoiceStatus.SENT,
    issue_date: datetime = datetime(2026, 9, 5),
    updated_at: datetime | None = None,
    subtotal: float = 100.00,
    tax_rate: float = 19.0,
    tax_amount: float = 19.00,
    total: float = 119.00,
) -> SimpleNamespace:
    """Build a lightweight Invoice-like fixture (see module docstring)."""
    return SimpleNamespace(
        invoice_number=invoice_number,
        status=status,
        issue_date=issue_date,
        updated_at=updated_at if updated_at is not None else issue_date,
        subtotal=subtotal,
        tax_rate=tax_rate,
        tax_amount=tax_amount,
        total=total,
    )


def _data_rows(csv_text: str) -> list[str]:
    """Return the DATEV data rows (everything after the two header rows)."""
    lines = csv_text.lstrip("﻿").splitlines()
    return [line for line in lines[2:] if line]


class TestDatevExportStatusFiltering:
    """DRAFT and CANCELLED invoices never get a plain revenue booking."""

    def test_draft_invoice_excluded(self):
        draft = _invoice(status=InvoiceStatus.DRAFT)

        csv_text = export_datev_csv([draft], revenue_accounts=DEFAULT_ACCOUNTS)

        assert _data_rows(csv_text) == []

    def test_sent_invoice_included_as_revenue_booking(self):
        sent = _invoice(status=InvoiceStatus.SENT, invoice_number="RE-2026-0042")

        csv_text = export_datev_csv([sent], revenue_accounts=DEFAULT_ACCOUNTS)

        rows = _data_rows(csv_text)
        assert len(rows) == 1
        fields = rows[0].split(";")
        assert fields[1] == "H"  # Haben = revenue credit
        assert fields[2] == "8400"  # 19% account
        assert fields[3] == RECEIVABLES_ACCOUNT
        assert "RE-2026-0042" in fields[5]

    def test_paid_invoice_included_as_revenue_booking(self):
        paid = _invoice(status=InvoiceStatus.PAID)

        csv_text = export_datev_csv([paid], revenue_accounts=DEFAULT_ACCOUNTS)

        assert len(_data_rows(csv_text)) == 1

    def test_overdue_invoice_included_as_revenue_booking(self):
        overdue = _invoice(status=InvoiceStatus.OVERDUE)

        csv_text = export_datev_csv([overdue], revenue_accounts=DEFAULT_ACCOUNTS)

        assert len(_data_rows(csv_text)) == 1

    def test_cancelled_invoice_passed_as_plain_invoice_is_excluded(self):
        """A CANCELLED invoice passed through the normal ``invoices`` list
        (not ``reversal_invoices``) must never be booked as plain revenue —
        this was the literal BE-13 bug."""
        cancelled = _invoice(status=InvoiceStatus.CANCELLED)

        csv_text = export_datev_csv([cancelled], revenue_accounts=DEFAULT_ACCOUNTS)

        assert _data_rows(csv_text) == []


class TestDatevReversalBooking:
    """CANCELLED invoices supplied as ``reversal_invoices`` produce a Storno."""

    def test_cancelled_after_sent_produces_reversal_booking(self):
        cancelled = _invoice(
            status=InvoiceStatus.CANCELLED,
            invoice_number="RE-2026-0099",
            updated_at=datetime(2026, 9, 20),
        )

        csv_text = export_datev_csv(
            [], reversal_invoices=[cancelled], revenue_accounts=DEFAULT_ACCOUNTS
        )

        rows = _data_rows(csv_text)
        assert len(rows) == 1
        fields = rows[0].split(";")
        assert fields[1] == "S"  # Soll = reversal of the original Haben booking
        assert fields[2] == "8400"
        assert fields[3] == RECEIVABLES_ACCOUNT
        assert fields[4] == "2009"  # DDMM of updated_at (cancellation date)
        assert "RE-2026-0099" in fields[5]
        assert "Storno" in fields[6]

    def test_reversal_booking_uses_the_invoice_own_vat_rate_account(self):
        cancelled = _invoice(status=InvoiceStatus.CANCELLED, tax_rate=7.0, total=107.0)

        csv_text = export_datev_csv(
            [], reversal_invoices=[cancelled], revenue_accounts=DEFAULT_ACCOUNTS
        )

        fields = _data_rows(csv_text)[0].split(";")
        assert fields[2] == "8300"

    def test_reversal_invoices_that_are_not_cancelled_are_ignored(self):
        """Defensive: only status == CANCELLED items are reversed, even if
        the caller mistakenly includes something else."""
        sent = _invoice(status=InvoiceStatus.SENT)

        csv_text = export_datev_csv(
            [], reversal_invoices=[sent], revenue_accounts=DEFAULT_ACCOUNTS
        )

        assert _data_rows(csv_text) == []


class TestDatevAccountMapping:
    """Revenue account is chosen per VAT rate from a typed settings mapping."""

    def test_seven_percent_invoice_uses_the_seven_percent_account(self):
        inv = _invoice(tax_rate=7.0, total=107.0)

        csv_text = export_datev_csv([inv], revenue_accounts=DEFAULT_ACCOUNTS)

        fields = _data_rows(csv_text)[0].split(";")
        assert fields[2] == "8300"

    def test_zero_percent_invoice_uses_the_zero_percent_account(self):
        inv = _invoice(tax_rate=0.0, tax_amount=0.0, subtotal=50.0, total=50.0)

        csv_text = export_datev_csv([inv], revenue_accounts=DEFAULT_ACCOUNTS)

        fields = _data_rows(csv_text)[0].split(";")
        assert fields[2] == "8200"

    def test_unmapped_vat_rate_raises_a_clear_error(self):
        inv = _invoice(tax_rate=7.0, total=107.0)

        with pytest.raises(AccountingExportError, match="7"):
            export_datev_csv([inv], revenue_accounts={"19": "8400"})

    def test_unmapped_vat_rate_error_mentions_settings_key(self):
        inv = _invoice(tax_rate=7.0, total=107.0)

        with pytest.raises(AccountingExportError, match="DATEV_REVENUE_ACCOUNTS"):
            export_datev_csv([inv], revenue_accounts={"19": "8400"})


class TestDatevAmountsCentExact:
    """Amounts are Decimal-rounded to the cent, never float/banker's-rounded."""

    def test_amount_is_decimal_rounded_half_up_not_banker_rounded(self):
        # round(119.005, 2) == 119.0 in plain Python (float imprecision /
        # banker's rounding) — Decimal(str(...)) round-half-up must give
        # 119.01, per ADR-2026-09-25-price-semantics.
        assert round(119.005, 2) == 119.0  # sanity check on the float gotcha

        inv = _invoice(total=119.005)

        csv_text = export_datev_csv([inv], revenue_accounts=DEFAULT_ACCOUNTS)

        fields = _data_rows(csv_text)[0].split(";")
        assert fields[0] == "119,01"

    def test_totals_are_cent_exact_across_multiple_invoices(self):
        invoices = [
            _invoice(invoice_number="RE-2026-0001", total=100.10),
            _invoice(invoice_number="RE-2026-0002", total=49.995),
        ]

        csv_text = export_datev_csv(invoices, revenue_accounts=DEFAULT_ACCOUNTS)

        amounts = [row.split(";")[0] for row in _data_rows(csv_text)]
        assert amounts == ["100,10", "50,00"]


class TestDatevCreatedDatePerCall:
    """The header's created-date must never be frozen at import time."""

    def test_created_date_is_computed_per_call(self, monkeypatch):
        import goldsmith_erp.services.accounting_export_service as export_module

        class _FakeDatetime(datetime):
            _now = datetime(2026, 1, 1)

            @classmethod
            def utcnow(cls):
                return cls._now

        monkeypatch.setattr(export_module, "datetime", _FakeDatetime)
        _FakeDatetime._now = datetime(2026, 1, 1)
        first = export_module.export_datev_csv([], revenue_accounts=DEFAULT_ACCOUNTS)

        _FakeDatetime._now = datetime(2026, 9, 25)
        second = export_module.export_datev_csv([], revenue_accounts=DEFAULT_ACCOUNTS)

        header_first = first.lstrip("﻿").splitlines()[0]
        header_second = second.lstrip("﻿").splitlines()[0]
        assert "20260101" in header_first
        assert "20260925" in header_second
        assert header_first != header_second


class TestLexofficeExport:
    """Lexoffice CSV mirrors the same issued/reversal/cent-exact rules."""

    def _rows(self, csv_text: str) -> list[str]:
        lines = csv_text.lstrip("﻿").splitlines()
        return [line for line in lines[1:] if line]

    def test_draft_excluded(self):
        draft = _invoice(status=InvoiceStatus.DRAFT)
        assert self._rows(export_lexoffice_csv([draft])) == []

    def test_sent_included(self):
        sent = _invoice(status=InvoiceStatus.SENT)
        assert len(self._rows(export_lexoffice_csv([sent]))) == 1

    def test_cancelled_plain_is_excluded(self):
        cancelled = _invoice(status=InvoiceStatus.CANCELLED)
        assert self._rows(export_lexoffice_csv([cancelled])) == []

    def test_cancelled_via_reversal_param_produces_negative_storno_row(self):
        cancelled = _invoice(
            status=InvoiceStatus.CANCELLED,
            invoice_number="RE-2026-0007",
            subtotal=100.0,
            total=119.0,
        )

        csv_text = export_lexoffice_csv([], reversal_invoices=[cancelled])

        rows = self._rows(csv_text)
        assert len(rows) == 1
        fields = [f.strip('"') for f in rows[0].split(",")]
        assert fields[1] == "RE-2026-0007"
        assert "Storno" in fields[2]
        assert fields[3] == "-100.00"
        assert fields[5] == "-119.00"

    def test_totals_cent_exact(self):
        inv = _invoice(subtotal=49.995, total=59.4941)

        csv_text = export_lexoffice_csv([inv])

        fields = [f.strip('"') for f in self._rows(csv_text)[0].split(",")]
        assert fields[3] == "50.00"
        assert fields[5] == "59.49"
