# src/goldsmith_erp/services/accounting_export_service.py
"""
Accounting export service — DATEV and Lexoffice CSV generation.

Generates CSV exports of invoices in two formats:

1. DATEV Buchungsstapel (Buchungssatz-Format)
   - Header row: DATEV-specific metadata header (Format 510)
   - Data rows:  Umsatz, Soll/Haben, Konto, Gegenkonto, Belegdatum,
                 Belegfeld1, Buchungstext
   - Encoding:   UTF-8 with BOM (required by DATEV import tool)

2. Lexoffice simplified CSV
   - Columns:    Datum, Belegnummer, Beschreibung, Netto, MwSt-Satz, Brutto
   - Encoding:   UTF-8 with BOM (Excel compatibility)

Both functions accept two lists of Invoice-like objects (any object exposing
``invoice_number``, ``status``, ``issue_date``, ``updated_at``, ``subtotal``,
``tax_rate``, ``tax_amount`` and ``total`` — ORM instances or plain test
doubles both work, since this module has no DB dependency):

- ``invoices``: booked as normal revenue (Haben) when their status is
  SENT/PAID/OVERDUE ("issued" — a legal document exists). Anything else
  (DRAFT, CANCELLED) in this list is silently skipped.
- ``reversal_invoices``: booked as a reversal (Storno, Soll) when their
  status is CANCELLED. Anything else in this list is silently skipped.

Callers (the invoices router) are responsible for deciding which invoices go
in which list — see BE-13 in
docs/review/2026-09-25/03-backend-correctness.md and W1-09 in
docs/review/2026-09-25/MASTER-FIX-PLAN.md. Financial data exports are
audit-logged by the router layer.

KNOWN LIMITATION (documented, not silently assumed): the Invoice model has
no record of which status an invoice held before it was CANCELLED (out of
scope for this fix — would need a schema change, see the W1-10 ADR's
planned ``issued_at`` column). Every CANCELLED invoice the router passes in
is therefore conservatively treated as "was issued" and gets a reversal
booking. This favours never silently dropping a needed Storno (the
concrete BE-13 harm: the accountant over-files VAT) over avoiding a rare
phantom reversal for an invoice that was cancelled while still a DRAFT.
"""

import csv
import io
import logging
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import TYPE_CHECKING, List, Mapping, Optional

from goldsmith_erp.core.config import settings

if TYPE_CHECKING:
    # Structural typing only — this module has no runtime ORM dependency so
    # it stays a pure formatter (see module docstring) and is trivial to
    # unit test with plain objects.
    from goldsmith_erp.db.models import Invoice

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class AccountingExportError(ValueError):
    """Raised when an invoice cannot be exported for a data/config reason.

    Financial data: callers (the router) must surface this to the operator
    as a clear error rather than silently skipping the invoice or booking
    it to the wrong account.
    """


# ---------------------------------------------------------------------------
# DATEV account constants (Goldsmith / Einzelhandel, SKR03 chart of accounts)
# ---------------------------------------------------------------------------

# Identifier for the DATEV Buchungsstapel format version 510
DATEV_FORMAT_VERSION = "510"

# Invoice statuses treated as "issued" (a legal document exists) and booked
# as normal revenue. OVERDUE is SENT invoices whose due_date has passed —
# still an issued document.
_ISSUED_STATUS_VALUES = frozenset({"sent", "paid", "overdue"})
_CANCELLED_STATUS_VALUE = "cancelled"

_CENT = Decimal("0.01")

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _status_value(invoice: "Invoice") -> str:
    """Normalize ``invoice.status`` to a lowercase string.

    Works whether ``status`` is the real ``InvoiceStatus`` enum (``.value``
    is a plain str already) or a plain string test double.
    """
    status = getattr(invoice, "status", None)
    value = getattr(status, "value", status)
    return str(value).lower() if value is not None else ""


def _to_cents(value: "float | Decimal") -> Decimal:
    """Convert a money amount to Decimal rounded half-up to cents.

    Never uses plain ``round()`` on a float: Python's float rounding is
    banker's-rounding on an imprecise binary value (``round(119.005, 2) ==
    119.0``), which silently loses a cent on a legally binding document.
    ``Decimal(str(value))`` reads the value's shortest round-tripping
    decimal representation first, per ADR-2026-09-25-price-semantics.
    """
    return Decimal(str(value)).quantize(_CENT, rounding=ROUND_HALF_UP)


def _vat_rate_key(tax_rate: "float | Decimal") -> str:
    """Normalize a VAT rate to the string key used in the account mapping.

    19.0 -> "19", 7.0 -> "7", 0.0 -> "0"; a non-integral rate (not used in
    Germany today, but not assumed impossible) keeps its fractional part.
    """
    rate = Decimal(str(tax_rate))
    if rate == rate.to_integral_value():
        return str(int(rate))
    return str(rate.normalize())


def _resolve_revenue_account(
    tax_rate: "float | Decimal", accounts: Mapping[str, str]
) -> str:
    """Look up the SKR03 revenue account for a VAT rate.

    Raises ``AccountingExportError`` for an unmapped rate instead of
    silently booking it to the wrong account (BE-13: this was the original
    bug — every rate booked to the 19% account regardless of ``tax_rate``).
    """
    key = _vat_rate_key(tax_rate)
    account = accounts.get(key)
    if not account:
        raise AccountingExportError(
            f"Kein Erloeskonto fuer {key}% MwSt hinterlegt. Bitte beim "
            "Steuerberater erfragen und in DATEV_REVENUE_ACCOUNTS "
            "ergaenzen (core/config.py Settings)."
        )
    return account


def _format_amount_datev(amount: Decimal) -> str:
    """
    Format a monetary amount for DATEV: two decimal places, comma as
    decimal separator (German locale convention required by DATEV).
    Example: Decimal("1234.50") -> "1234,50"
    """
    return f"{amount:.2f}".replace(".", ",")


def _format_date_datev(dt: Optional[datetime]) -> str:
    """
    Format a date as DDMM — the Belegdatum field format required by DATEV
    Buchungsstapel import (the year is encoded in the stack header).
    Returns an empty string if dt is None.
    """
    if dt is None:
        return ""
    return dt.strftime("%d%m")


def _format_date_lexoffice(dt: Optional[datetime]) -> str:
    """Format date as DD.MM.YYYY for Lexoffice."""
    if dt is None:
        return ""
    return dt.strftime("%d.%m.%Y")


def _reversal_booking_date(invoice: "Invoice") -> Optional[datetime]:
    """Best available date for a Storno booking.

    The Invoice model has no ``cancelled_at`` column (see module
    docstring's KNOWN LIMITATION); ``updated_at`` is the closest proxy —
    cancellation is the last write to a CANCELLED invoice in the current
    workflow. Falls back to ``issue_date`` for lightweight test doubles
    that omit ``updated_at``.
    """
    return getattr(invoice, "updated_at", None) or getattr(invoice, "issue_date", None)


def _csv_string(write_fn) -> str:
    """
    Execute a writer callback against a StringIO buffer and return the
    resulting string including the UTF-8 BOM prefix that DATEV and Excel
    expect when opening CSV files directly.
    """
    buf = io.StringIO()
    write_fn(buf)
    return "﻿" + buf.getvalue()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def export_datev_csv(
    invoices: "List[Invoice]",
    *,
    reversal_invoices: "Optional[List[Invoice]]" = None,
    revenue_accounts: Optional[Mapping[str, str]] = None,
    receivables_account: Optional[str] = None,
) -> str:
    """
    Generate a DATEV Buchungsstapel CSV for the given invoices.

    The DATEV Buchungsstapel format (Format 510) consists of two sections:
    1. A fixed metadata header (rows 1-2) with format identifiers.
    2. A column-header row followed by one data row per booking.

    Columns (per DATEV format 510 specification):
      Umsatz         - Amount (always positive; sign is carried by
                       Soll/Haben-Kennzeichen), two decimals, comma
                       separator, Decimal-rounded to the cent.
      Soll/Haben     - "H" (Haben/credit) for a normal revenue booking,
                       "S" (Soll/debit) for a Storno reversal booking.
      Konto          - Revenue account chosen per the invoice's VAT rate
                       (``revenue_accounts`` / Settings.DATEV_REVENUE_ACCOUNTS).
      Gegenkonto     - Counter account (Forderungen, receivables).
      Belegdatum     - Document date DDMM (issue_date for a normal booking,
                       the best available cancellation date for a Storno).
      Belegfeld1     - Invoice number (Rechnungsnummer, max 12 chars).
      Buchungstext   - Short booking description (max 60 chars).

    Args:
        invoices: Invoices booked as normal revenue. Only SENT/PAID/OVERDUE
            entries produce a row; DRAFT/CANCELLED entries are skipped.
        reversal_invoices: Invoices booked as a Storno reversal. Only
            CANCELLED entries produce a row.
        revenue_accounts: VAT-rate -> account mapping. Defaults to
            ``settings.DATEV_REVENUE_ACCOUNTS``.
        receivables_account: Gegenkonto for every row. Defaults to
            ``settings.DATEV_RECEIVABLES_ACCOUNT``.

    Returns:
        UTF-8 string with BOM, suitable for StreamingResponse.

    Raises:
        AccountingExportError: an invoice's VAT rate has no mapped account.
    """
    accounts = (
        revenue_accounts
        if revenue_accounts is not None
        else settings.DATEV_REVENUE_ACCOUNTS
    )
    receivables = (
        receivables_account
        if receivables_account is not None
        else settings.DATEV_RECEIVABLES_ACCOUNT
    )
    # Computed fresh on every call — never cached at import time, so a long-
    # running process exports today's date, not the date it was started.
    created_date = datetime.utcnow().strftime("%Y%m%d")

    logger.info(
        "Generating DATEV export",
        extra={
            "audit": True,
            "action": "export_datev",
            "invoice_count": len(invoices),
            "reversal_count": len(reversal_invoices or []),
        },
    )

    def _write(buf: io.StringIO) -> None:
        writer = csv.writer(
            buf, delimiter=";", quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n"
        )

        # -- DATEV metadata header (mandatory, line 1) -----------------------
        # Format: "EXTF";<version>;<category>;<format-name>;<format-version>;
        #         <created-date>;<import-date>;<source>;;<creator-id>;;<client-number>;
        #         <consultant-number>;<start-date>;<end-date>;<account-length>;
        #         <date-from>;<date-to>;<description>;<dictation-flag>;;<SKR>;<locked>;;
        #
        # For a minimal valid header only the first several fixed fields are required.
        # All optional fields are left empty so the DATEV import wizard prompts the user
        # to confirm account mappings interactively.
        header_meta = [
            "EXTF",  # Fixed identifier — marks an external file
            DATEV_FORMAT_VERSION,
            "21",  # Category 21 = Buchungsstapel
            "Buchungsstapel",
            "7",  # Format version 7
            created_date,
            "",  # Import date (filled by DATEV on import)
            "RE",  # Source abbreviation ("Rechnung")
            "",  # Reserved
            "",  # Creator ID
            "",  # Reserved
            "",  # Client number (Mandantennummer)
            "",  # Consultant number (Beraternummer)
            "",  # Start of fiscal year (YYYYMMDD)
            "",  # End of fiscal year (YYYYMMDD)
            "4",  # Account length (Kontonummernlaenge)
            "",  # Date from (YYYYMMDD)
            "",  # Date to (YYYYMMDD)
            "Goldsmith ERP Export",  # Description
            "",  # Dictation abbreviation
            "",  # Reserved
            "03",  # SKR chart (03 = SKR03)
            "",  # Lock flag
            "",  # Reserved
            "",  # Reserved
        ]
        writer.writerow(header_meta)

        # -- Column header row (mandatory, line 2) ---------------------------
        writer.writerow(
            [
                "Umsatz (ohne Soll/Haben-Kz)",
                "Soll/Haben-Kennzeichen",
                "Konto",
                "Gegenkonto (ohne BU-Schluessel)",
                "Belegdatum",
                "Belegfeld1",
                "Buchungstext",
            ]
        )

        # -- Normal revenue bookings (issued invoices) -----------------------
        for inv in invoices:
            if _status_value(inv) not in _ISSUED_STATUS_VALUES:
                continue
            account = _resolve_revenue_account(inv.tax_rate, accounts)
            amount = _to_cents(inv.total)
            booking_text = f"Rechnung {inv.invoice_number}"[:60]
            writer.writerow(
                [
                    _format_amount_datev(amount),
                    "H",  # Haben = credit on revenue account
                    account,
                    receivables,
                    _format_date_datev(inv.issue_date),
                    inv.invoice_number[:12],  # Belegfeld1 max 12 chars
                    booking_text,
                ]
            )

        # -- Storno reversal bookings (cancelled invoices) -------------------
        for inv in reversal_invoices or []:
            if _status_value(inv) != _CANCELLED_STATUS_VALUE:
                continue
            account = _resolve_revenue_account(inv.tax_rate, accounts)
            amount = _to_cents(inv.total)
            booking_text = f"Storno Rechnung {inv.invoice_number}"[:60]
            writer.writerow(
                [
                    _format_amount_datev(amount),
                    "S",  # Soll = debit — reverses the original Haben booking
                    account,
                    receivables,
                    _format_date_datev(_reversal_booking_date(inv)),
                    inv.invoice_number[:12],
                    booking_text,
                ]
            )

    return _csv_string(_write)


def export_lexoffice_csv(
    invoices: "List[Invoice]",
    *,
    reversal_invoices: "Optional[List[Invoice]]" = None,
) -> str:
    """
    Generate a Lexoffice-compatible simplified CSV for the given invoices.

    Lexoffice accepts a straightforward format for revenue journal imports:
      Datum        - Issue date in DD.MM.YYYY format (cancellation date for
                     a Storno row).
      Belegnummer  - Invoice number.
      Beschreibung - Short description referencing the invoice ("Storno
                     Rechnung ..." for a reversal row).
      Netto        - Net amount (Zwischensumme), Decimal-rounded to the
                     cent, negative for a Storno row.
      MwSt-Satz    - VAT rate as a percentage (e.g. "19").
      Brutto       - Gross total, Decimal-rounded to the cent, negative for
                     a Storno row.

    Lexoffice's own bookkeeping assigns the G/L account internally from the
    VAT rate, so (unlike DATEV) this format has no account column and no
    account-mapping validation.

    Args:
        invoices: Invoices booked as normal revenue. Only SENT/PAID/OVERDUE
            entries produce a row.
        reversal_invoices: Invoices booked as a negative Storno row. Only
            CANCELLED entries produce a row.

    Returns:
        UTF-8 string with BOM, suitable for StreamingResponse.
    """
    logger.info(
        "Generating Lexoffice export",
        extra={
            "audit": True,
            "action": "export_lexoffice",
            "invoice_count": len(invoices),
            "reversal_count": len(reversal_invoices or []),
        },
    )

    def _write(buf: io.StringIO) -> None:
        writer = csv.writer(
            buf, delimiter=",", quoting=csv.QUOTE_ALL, lineterminator="\r\n"
        )

        writer.writerow(
            [
                "Datum",
                "Belegnummer",
                "Beschreibung",
                "Netto",
                "MwSt-Satz (%)",
                "Brutto",
            ]
        )

        for inv in invoices:
            if _status_value(inv) not in _ISSUED_STATUS_VALUES:
                continue
            description = f"Rechnung {inv.invoice_number}"
            writer.writerow(
                [
                    _format_date_lexoffice(inv.issue_date),
                    inv.invoice_number,
                    description,
                    f"{_to_cents(inv.subtotal):.2f}",
                    _vat_rate_key(inv.tax_rate),
                    f"{_to_cents(inv.total):.2f}",
                ]
            )

        for inv in reversal_invoices or []:
            if _status_value(inv) != _CANCELLED_STATUS_VALUE:
                continue
            description = f"Storno Rechnung {inv.invoice_number}"
            writer.writerow(
                [
                    _format_date_lexoffice(_reversal_booking_date(inv)),
                    inv.invoice_number,
                    description,
                    f"{-_to_cents(inv.subtotal):.2f}",
                    _vat_rate_key(inv.tax_rate),
                    f"{-_to_cents(inv.total):.2f}",
                ]
            )

    return _csv_string(_write)
