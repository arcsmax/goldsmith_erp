# src/goldsmith_erp/services/number_sequence_service.py
"""
Gap-free per-year document numbers (W2-04: BE-16, decision D-12).

Replaces the unlocked ``SELECT MAX(number) + 1`` scheme (two concurrent
creates got the same number and a 500; the string MAX stopped at
"RE-2026-9999" > "RE-2026-10000"; the year was UTC, not Berlin).

Design:

- One ``number_sequences`` row per (kind, year) holds ``last_value``.
- ``next_value`` bumps it with a single ``UPDATE ... SET last_value =
  last_value + 1 ... RETURNING last_value``. The UPDATE takes the row lock
  (PostgreSQL: row-level lock held to commit, equivalent to ``SELECT ... FOR
  UPDATE``; SQLite: the database write lock), so concurrent creates are
  serialised and each gets the next value.
- It runs inside the CALLER's transaction and never commits: if the
  document insert fails and the transaction rolls back, the increment rolls
  back too, so no number is lost (gap-free).
- A missing row (first document of a year, or a DB that pre-dates the
  migration seed) is created with ``INSERT ... ON CONFLICT DO NOTHING``,
  seeded from the numerically highest existing number of that kind and year,
  then bumped with the same UPDATE. Two racing first-of-year creates both
  insert-or-skip and then serialise on the UPDATE.
- The year is the Europe/Berlin calendar year of ``now``.

Format: ``<KIND>-<YYYY>-<NNNN>``; widths beyond 4 digits simply grow
("RE-2026-10000").
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple
from zoneinfo import ZoneInfo

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import Invoice, NumberSequence, Quote

logger = logging.getLogger(__name__)

INVOICE_KIND = "RE"
QUOTE_KIND = "KV"
_BERLIN = ZoneInfo("Europe/Berlin")

# kind -> numbered column, used to seed a missing counter row.
_NUMBERED_COLUMNS: Dict[str, Any] = {
    INVOICE_KIND: Invoice.invoice_number,
    QUOTE_KIND: Quote.quote_number,
}


def berlin_year(now: Optional[datetime] = None) -> int:
    """Calendar year in Europe/Berlin. Naive input is read as UTC."""
    moment = now or datetime.now(timezone.utc)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(_BERLIN).year


def format_number(kind: str, year: int, value: int) -> str:
    return f"{kind}-{year}-{value:04d}"


def parse_number(kind: str, number: str) -> Optional[Tuple[int, int]]:
    """(year, value) of ``number`` if it has the ``kind`` format."""
    match = re.match(rf"^{re.escape(kind)}-(\d{{4}})-(\d+)$", number or "")
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))


class NumberSequenceService:
    """Static-method service; all methods take the AsyncSession first."""

    @staticmethod
    async def next_number(
        db: AsyncSession, kind: str, now: Optional[datetime] = None
    ) -> str:
        """Next formatted number of ``kind`` for the Berlin year of ``now``.

        Must be called inside the transaction that inserts the document.
        """
        year = berlin_year(now)
        value = await NumberSequenceService.next_value(db, kind, year)
        return format_number(kind, year, value)

    @staticmethod
    async def next_value(db: AsyncSession, kind: str, year: int) -> int:
        value = await NumberSequenceService._bump(db, kind, year)
        if value is not None:
            return value
        seed = await NumberSequenceService._seed_value(db, kind, year)
        await NumberSequenceService._insert_if_missing(db, kind, year, seed)
        value = await NumberSequenceService._bump(db, kind, year)
        if value is None:  # pragma: no cover - the row was just ensured
            raise RuntimeError(f"number_sequences row {kind}/{year} missing")
        logger.info(
            "Number sequence initialised",
            extra={"kind": kind, "year": year, "seed": seed},
        )
        return value

    @staticmethod
    async def _bump(db: AsyncSession, kind: str, year: int) -> Optional[int]:
        result = await db.execute(
            update(NumberSequence)
            .where(NumberSequence.kind == kind, NumberSequence.year == year)
            .values(last_value=NumberSequence.last_value + 1)
            .returning(NumberSequence.last_value)
            .execution_options(synchronize_session=False)
        )
        value = result.scalar_one_or_none()
        return int(value) if value is not None else None

    @staticmethod
    async def _seed_value(db: AsyncSession, kind: str, year: int) -> int:
        """Highest existing value for (kind, year), compared as integers."""
        column = _NUMBERED_COLUMNS.get(kind)
        if column is None:
            return 0
        rows = await db.execute(select(column).where(column.like(f"{kind}-{year}-%")))
        highest = 0
        for (number,) in rows.all():
            parsed = parse_number(kind, number)
            if parsed is not None and parsed[0] == year:
                highest = max(highest, parsed[1])
        return highest

    @staticmethod
    async def _insert_if_missing(
        db: AsyncSession, kind: str, year: int, seed: int
    ) -> None:
        dialect = (await db.connection()).dialect.name
        insert_fn = pg_insert if dialect == "postgresql" else sqlite_insert
        stmt = (
            insert_fn(NumberSequence)
            .values(kind=kind, year=year, last_value=seed)
            .on_conflict_do_nothing(index_elements=["kind", "year"])
        )
        await db.execute(stmt)
