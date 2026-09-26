"""Altgold Ankaufsbuch export (W2-16, DOM-21; decision D-16).

The Ankaufsbuch lists every SIGNED (or already CREDITED) Altgold purchase of
a period with what a precious-metal buyer is expected to record: date,
receipt number, seller name and address, identity document (type, number,
issuing authority, checked by), items (description, alloy, weight, fine
content) and the price paid. The exact legal requirements (GwG §§ 10/11,
Gewerbeordnung / state rules for Edelmetallankauf, retention period) are
**vom Steuerberater zu bestätigen**; every export says so.

The export is ADMIN-only (router) and contains decrypted PII, so it is
audit-logged and no value is ever logged.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, List, Optional, Sequence

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from goldsmith_erp.core.timeutil import DATETIME_FORMAT, format_local
from goldsmith_erp.db.models import ScrapGold, ScrapGoldStatus
from goldsmith_erp.models.scrap_gold import ID_DOCUMENT_LABELS

LEGAL_NOTE = (
    "Hinweis: Inhalt und Aufbewahrungsfrist des Ankaufsbuchs "
    "(GwG, Edelmetallankauf) sind vom Steuerberater zu bestätigen."
)

CSV_HEADER: tuple[str, ...] = (
    "Beleg-Nr.",
    "Datum",
    "Verkäufer",
    "Anschrift",
    "Ausweisart",
    "Ausweisnummer",
    "Ausstellende Behörde",
    "Geprüft von",
    "Positionen",
    "Feingewicht (g)",
    "Kurs (EUR/g)",
    "Ankaufspreis (EUR)",
    "Status",
)

_STATUS_LABELS = {"signed": "unterschrieben", "credited": "verrechnet"}
_FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


@dataclass(frozen=True)
class AnkaufsbuchRow:
    receipt_number: str
    signed_at: Optional[datetime]
    seller: str
    address: str
    id_document: str
    id_number: str
    id_authority: str
    checked_by: str
    items: str
    fine_gold_g: float
    price_per_g: Optional[float]
    total_eur: float
    status: str


def _de_number(value: Optional[float], digits: int = 2) -> str:
    if value is None:
        return ""
    return f"{value:,.{digits}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _de_date(value: Optional[datetime]) -> str:
    # Ankaufsbuch entries show Europe/Berlin local time (BE-15).
    return format_local(value, DATETIME_FORMAT, empty="")


def _safe_cell(value: str) -> str:
    """Neutralise spreadsheet formulas in free text (CSV injection)."""
    return f"'{value}" if value.startswith(_FORMULA_PREFIXES) else value


def _person_name(person: Any) -> str:
    if person is None:
        return ""
    parts = (getattr(person, "first_name", None), getattr(person, "last_name", None))
    name = " ".join(p for p in parts if p)
    company = getattr(person, "company_name", None)
    return f"{name} ({company})" if company else name


def _address(customer: Any) -> str:
    if customer is None:
        return ""
    street = getattr(customer, "street", None) or ""
    place = " ".join(
        p
        for p in (
            getattr(customer, "postal_code", None),
            getattr(customer, "city", None),
        )
        if p
    )
    return ", ".join(p for p in (street, place) if p)


def _items(record: ScrapGold) -> str:
    lines = []
    for item in record.items:
        alloy = getattr(item.alloy, "value", item.alloy)
        lines.append(
            f"{item.description} ({alloy}, {_de_number(item.weight_g)} g, "
            f"fein {_de_number(item.fine_content_g, 3)} g)"
        )
    return "; ".join(lines)


def _row(record: Any) -> AnkaufsbuchRow:
    status = getattr(record.status, "value", record.status)
    doc_type = record.id_document_type or ""
    return AnkaufsbuchRow(
        receipt_number=f"AG-{record.id:05d}",
        signed_at=record.signed_at,
        seller=_person_name(record.customer),
        address=_address(record.customer),
        id_document=ID_DOCUMENT_LABELS.get(doc_type, doc_type),
        id_number=record.id_document_number or "",
        id_authority=record.id_issuing_authority or "",
        checked_by=_person_name(record.id_checker),
        items=_items(record),
        fine_gold_g=float(record.total_fine_gold_g or 0.0),
        price_per_g=record.gold_price_per_g,
        total_eur=float(record.total_value_eur or 0.0),
        status=_STATUS_LABELS.get(str(status), str(status)),
    )


async def load_rows(
    db: AsyncSession, date_from: date, date_to: date
) -> List[AnkaufsbuchRow]:
    """Signed purchases with ``signed_at`` in [date_from, date_to], oldest first."""
    start = datetime.combine(date_from, time.min, tzinfo=timezone.utc)
    end = datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=timezone.utc)
    result = await db.execute(
        select(ScrapGold)
        .where(
            or_(
                ScrapGold.status == ScrapGoldStatus.SIGNED,
                ScrapGold.status == ScrapGoldStatus.CREDITED,
            ),
            ScrapGold.signed_at >= start,
            ScrapGold.signed_at < end,
        )
        .options(
            selectinload(ScrapGold.items),
            selectinload(ScrapGold.customer),
            selectinload(ScrapGold.id_checker),
        )
        .order_by(ScrapGold.signed_at, ScrapGold.id)
    )
    return [_row(record) for record in result.scalars().all()]


def to_csv(rows: Sequence[AnkaufsbuchRow], date_from: date, date_to: date) -> bytes:
    """Semicolon CSV with decimal commas and a BOM (opens cleanly in German Excel)."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow(
        [f"Ankaufsbuch Altgold {date_from:%d.%m.%Y} bis {date_to:%d.%m.%Y}"]
    )
    writer.writerow([LEGAL_NOTE])
    writer.writerow(CSV_HEADER)
    for row in rows:
        writer.writerow(
            [
                row.receipt_number,
                _de_date(row.signed_at),
                _safe_cell(row.seller),
                _safe_cell(row.address),
                row.id_document,
                _safe_cell(row.id_number),
                _safe_cell(row.id_authority),
                _safe_cell(row.checked_by),
                _safe_cell(row.items),
                _de_number(row.fine_gold_g, 3),
                _de_number(row.price_per_g),
                _de_number(row.total_eur),
                row.status,
            ]
        )
    return ("﻿" + buffer.getvalue()).encode("utf-8")


def format_de_number(value: Optional[float], digits: int = 2) -> str:
    """Public alias for the PDF renderer."""
    return _de_number(value, digits)


def format_de_datetime(value: Optional[datetime]) -> str:
    return _de_date(value)
