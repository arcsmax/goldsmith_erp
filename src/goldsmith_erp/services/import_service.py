# src/goldsmith_erp/services/import_service.py
"""
CSV data-import service for bulk customer onboarding.

Design contract:
- Never raises for individual row errors — collect them and continue.
- Fails loudly (raises) only for structural problems (bad CSV encoding, etc.).
- Duplicate detection is by email address (case-insensitive).
- PII in error messages is anonymised following GDPR logging rules.
- All DB writes use the standard async session passed by the caller.

Expected CSV columns (order-independent, header row required):
    first_name, last_name, email, phone, street, city, postal_code,
    customer_type, birthday, ring_size, notes
"""
from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import Customer as CustomerModel

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Public result type
# ---------------------------------------------------------------------------

SAMPLE_CSV_ROWS: list[dict[str, str]] = [
    {
        "first_name": "Maria",
        "last_name": "Muster",
        "email": "maria.muster@example.com",
        "phone": "+49 89 12345678",
        "street": "Musterstraße 1",
        "city": "München",
        "postal_code": "80331",
        "customer_type": "private",
        "birthday": "1985-04-23",
        "ring_size": "54",
        "notes": "Stammkundin seit 2018",
    }
]

CSV_HEADERS = list(SAMPLE_CSV_ROWS[0].keys())


@dataclass
class ImportRowError:
    """Describes a validation or persistence failure for a single CSV row."""

    row_number: int
    field: Optional[str]
    message: str


@dataclass
class ImportResult:
    """Summary returned to the caller after a CSV import run."""

    imported_count: int = 0
    skipped_count: int = 0
    errors: list[ImportRowError] = field(default_factory=list)

    @property
    def total_rows(self) -> int:
        return self.imported_count + self.skipped_count + len(self.errors)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_REQUIRED_HEADERS = {"first_name", "last_name", "email"}


def _anonymise_email(address: str) -> str:
    """Return a privacy-safe representation for log messages."""
    try:
        local, domain = address.split("@", 1)
        return f"{local[0]}***@{domain}"
    except Exception:
        return "***"


def _parse_date(value: str, fmt: str = "%Y-%m-%d") -> Optional[datetime]:
    """Parse an ISO-8601 date string; return None on failure."""
    if not value or not value.strip():
        return None
    try:
        return datetime.strptime(value.strip(), fmt)
    except ValueError:
        return None


def _parse_float(value: str) -> Optional[float]:
    """Parse a decimal string; return None on failure."""
    if not value or not value.strip():
        return None
    try:
        return float(value.replace(",", ".").strip())
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Service function
# ---------------------------------------------------------------------------


async def import_customers_csv(
    db: AsyncSession,
    csv_content: str,
    user_id: int,
) -> ImportResult:
    """
    Parse and import customer records from a UTF-8 CSV string.

    Parameters
    ----------
    db:
        Async SQLAlchemy session — the caller is responsible for commit/rollback.
    csv_content:
        Raw CSV text (UTF-8).  Must include a header row.
    user_id:
        ID of the admin performing the import (used for audit logging only).

    Returns
    -------
    ImportResult containing counts of imported / skipped / errored rows and
    per-row error details.

    Raises
    ------
    ValueError
        If the CSV cannot be parsed or the required header columns are absent.
    """
    result = ImportResult()

    # Parse CSV ---------------------------------------------------------------
    try:
        reader = csv.DictReader(io.StringIO(csv_content, newline=""))
    except Exception as exc:
        raise ValueError(f"CSV konnte nicht gelesen werden: {exc}") from exc

    if reader.fieldnames is None:
        raise ValueError("CSV hat keine Kopfzeile.")

    present_headers = {h.strip().lower() for h in reader.fieldnames if h}
    missing_required = _REQUIRED_HEADERS - present_headers
    if missing_required:
        raise ValueError(
            f"Fehlende Pflichtfelder in der CSV-Kopfzeile: "
            f"{', '.join(sorted(missing_required))}"
        )

    # Pre-load existing emails for duplicate detection (single query) ---------
    existing_emails_result = await db.execute(
        select(CustomerModel.email)
    )
    existing_emails: set[str] = {
        row[0].lower() for row in existing_emails_result.fetchall() if row[0]
    }

    # Track emails seen in this import batch to catch intra-batch duplicates.
    seen_in_batch: set[str] = set()

    # Process rows ------------------------------------------------------------
    for row_number, row in enumerate(reader, start=2):  # 2 = first data row
        # Strip whitespace from all values.
        row = {k.strip().lower(): (v or "").strip() for k, v in row.items()}

        # Validate required fields.
        first_name = row.get("first_name", "")
        last_name = row.get("last_name", "")
        email = row.get("email", "").lower()

        if not first_name:
            result.errors.append(
                ImportRowError(row_number, "first_name", "Vorname fehlt.")
            )
            continue
        if not last_name:
            result.errors.append(
                ImportRowError(row_number, "last_name", "Nachname fehlt.")
            )
            continue
        if not email or "@" not in email:
            result.errors.append(
                ImportRowError(row_number, "email", "Ungültige oder fehlende E-Mail-Adresse.")
            )
            continue

        # Duplicate detection (existing DB records + intra-batch).
        if email in existing_emails or email in seen_in_batch:
            logger.debug(
                "CSV import: skipping duplicate email",
                extra={"email": _anonymise_email(email), "row": row_number, "user_id": user_id},
            )
            result.skipped_count += 1
            seen_in_batch.add(email)
            continue

        # Build model instance.
        customer_type = row.get("customer_type", "private")
        if customer_type not in ("private", "business"):
            customer_type = "private"

        birthday = _parse_date(row.get("birthday", ""))
        ring_size = _parse_float(row.get("ring_size", ""))

        customer = CustomerModel(
            first_name=first_name,
            last_name=last_name,
            email=email,
            phone=row.get("phone") or None,
            street=row.get("street") or None,
            city=row.get("city") or None,
            postal_code=row.get("postal_code") or None,
            customer_type=customer_type,
            birthday=birthday,
            ring_size=ring_size,
            notes=row.get("notes") or None,
        )

        db.add(customer)
        existing_emails.add(email)
        seen_in_batch.add(email)
        result.imported_count += 1

        logger.debug(
            "CSV import: customer queued",
            extra={"email": _anonymise_email(email), "row": row_number, "user_id": user_id},
        )

    logger.info(
        "CSV customer import completed",
        extra={
            "imported": result.imported_count,
            "skipped": result.skipped_count,
            "errors": len(result.errors),
            "user_id": user_id,
        },
    )
    return result
