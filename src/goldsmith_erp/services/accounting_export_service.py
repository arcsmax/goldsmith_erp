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

Both functions accept a list of Invoice ORM model instances and return a
UTF-8 string (with BOM prefix) ready to be served as a StreamingResponse.

No external dependencies beyond the Python standard library.
Financial data exports are audit-logged by the router layer.
"""

import csv
import io
import logging
from datetime import datetime
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    # Imported only for type hints — avoids circular imports at runtime.
    from goldsmith_erp.db.models import Invoice

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DATEV account constants (Goldsmith / Einzelhandel, SKR03 chart of accounts)
# ---------------------------------------------------------------------------

# Revenue account: 8400 = Erlöse 19% USt (standard revenue in SKR03)
DATEV_REVENUE_ACCOUNT = "8400"

# Receivables account: 1400 = Forderungen aus Lieferungen und Leistungen (SKR03)
DATEV_RECEIVABLES_ACCOUNT = "1400"

# Identifier for the DATEV Buchungsstapel format version 510
DATEV_FORMAT_VERSION = "510"

# Date of this software for the DATEV header (YYYYMMDD)
_DATEV_CREATED_DATE = datetime.utcnow().strftime("%Y%m%d")

# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------


def _csv_string(write_fn) -> str:
    """
    Execute a writer callback against a StringIO buffer and return the
    resulting string including the UTF-8 BOM prefix that DATEV and Excel
    expect when opening CSV files directly.
    """
    buf = io.StringIO()
    write_fn(buf)
    return "\ufeff" + buf.getvalue()


def _format_amount_datev(amount: float) -> str:
    """
    Format a monetary amount for DATEV: two decimal places, comma as
    decimal separator (German locale convention required by DATEV).
    Example: 1234.50 -> "1234,50"
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


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def export_datev_csv(invoices: "List[Invoice]") -> str:
    """
    Generate a DATEV Buchungsstapel CSV for the given invoices.

    The DATEV Buchungsstapel format (Format 510) consists of two sections:
    1. A fixed metadata header (rows 1–2) with format identifiers.
    2. A column-header row followed by one data row per invoice.

    Columns (per DATEV format 510 specification):
      Umsatz         - Gross amount (Brutto, two decimal places, comma separator)
      Soll/Haben     - "H" = Haben (revenue credit entry)
      Konto          - Revenue account (8400 in SKR03)
      Gegenkonto     - Counter account (1400 Forderungen, debit side)
      Belegdatum     - Document date DDMM
      Belegfeld1     - Invoice number (Rechnungsnummer, max 12 chars)
      Buchungstext   - Short booking description (max 60 chars)

    Args:
        invoices: List of Invoice ORM model instances to export.

    Returns:
        UTF-8 string with BOM, suitable for StreamingResponse.
    """
    logger.info(
        "Generating DATEV export",
        extra={"audit": True, "action": "export_datev", "invoice_count": len(invoices)},
    )

    def _write(buf: io.StringIO) -> None:
        writer = csv.writer(buf, delimiter=";", quoting=csv.QUOTE_MINIMAL, lineterminator="\r\n")

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
            "EXTF",          # Fixed identifier — marks an external file
            DATEV_FORMAT_VERSION,
            "21",            # Category 21 = Buchungsstapel
            "Buchungsstapel",
            "7",             # Format version 7
            _DATEV_CREATED_DATE,
            "",              # Import date (filled by DATEV on import)
            "RE",            # Source abbreviation ("Rechnung")
            "",              # Reserved
            "",              # Creator ID
            "",              # Reserved
            "",              # Client number (Mandantennummer)
            "",              # Consultant number (Beraternummer)
            "",              # Start of fiscal year (YYYYMMDD)
            "",              # End of fiscal year (YYYYMMDD)
            "4",             # Account length (Kontonummernlänge)
            "",              # Date from (YYYYMMDD)
            "",              # Date to (YYYYMMDD)
            "Goldsmith ERP Export",  # Description
            "",              # Dictation abbreviation
            "",              # Reserved
            "03",            # SKR chart (03 = SKR03)
            "",              # Lock flag
            "",              # Reserved
            "",              # Reserved
        ]
        writer.writerow(header_meta)

        # -- Column header row (mandatory, line 2) ---------------------------
        writer.writerow([
            "Umsatz (ohne Soll/Haben-Kz)",
            "Soll/Haben-Kennzeichen",
            "Konto",
            "Gegenkonto (ohne BU-Schlüssel)",
            "Belegdatum",
            "Belegfeld1",
            "Buchungstext",
        ])

        # -- Data rows -------------------------------------------------------
        for inv in invoices:
            booking_text = f"Rechnung {inv.invoice_number}"[:60]
            writer.writerow([
                _format_amount_datev(inv.total),
                "H",                              # Haben = credit on revenue account
                DATEV_REVENUE_ACCOUNT,            # 8400 Erlöse
                DATEV_RECEIVABLES_ACCOUNT,        # 1400 Forderungen
                _format_date_datev(inv.issue_date),
                inv.invoice_number[:12],          # Belegfeld1 max 12 chars
                booking_text,
            ])

    return _csv_string(_write)


def export_lexoffice_csv(invoices: "List[Invoice]") -> str:
    """
    Generate a Lexoffice-compatible simplified CSV for the given invoices.

    Lexoffice accepts a straightforward format for revenue journal imports:
      Datum        - Issue date in DD.MM.YYYY format
      Belegnummer  - Invoice number
      Beschreibung - Short description referencing the invoice
      Netto        - Net amount (Zwischensumme) with two decimal places
      MwSt-Satz    - VAT rate as an integer percentage (e.g. "19")
      Brutto       - Gross total with two decimal places

    Amounts use a period as decimal separator (Lexoffice CSV convention).

    Args:
        invoices: List of Invoice ORM model instances to export.

    Returns:
        UTF-8 string with BOM, suitable for StreamingResponse.
    """
    logger.info(
        "Generating Lexoffice export",
        extra={"audit": True, "action": "export_lexoffice", "invoice_count": len(invoices)},
    )

    def _write(buf: io.StringIO) -> None:
        writer = csv.writer(buf, delimiter=",", quoting=csv.QUOTE_ALL, lineterminator="\r\n")

        writer.writerow([
            "Datum",
            "Belegnummer",
            "Beschreibung",
            "Netto",
            "MwSt-Satz (%)",
            "Brutto",
        ])

        for inv in invoices:
            description = f"Rechnung {inv.invoice_number}"
            writer.writerow([
                _format_date_lexoffice(inv.issue_date),
                inv.invoice_number,
                description,
                f"{inv.subtotal:.2f}",
                str(int(inv.tax_rate)),
                f"{inv.total:.2f}",
            ])

    return _csv_string(_write)
