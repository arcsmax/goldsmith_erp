# src/goldsmith_erp/models/_common.py
"""
Shared Pydantic helpers for API input schemas.

Datetime convention (see docs/architecture/ADR-2026-09-25-price-semantics.md):
the DB columns are ``TIMESTAMP WITHOUT TIME ZONE`` holding UTC, and the rest
of the code compares against ``datetime.utcnow()``. The browser sends ISO
strings with a ``Z`` suffix, which Pydantic parses as tz-aware. Every API
datetime input is therefore normalised to naive UTC at the schema boundary:

- aware input  -> converted to UTC, tzinfo dropped
- naive input  -> interpreted as UTC (unchanged)

This is the same rule ``models/repair.py::_strip_tzinfo`` already applies.
"""

from datetime import datetime, timezone
from typing import Annotated, Optional

from pydantic import BeforeValidator, TypeAdapter

_DATETIME_ADAPTER: TypeAdapter[datetime] = TypeAdapter(datetime)


def to_naive_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Return ``value`` as naive UTC; ``None`` passes through."""
    if value is None:
        return None
    if value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def _parse_to_naive_utc(value: object) -> object:
    """BeforeValidator: parse str/datetime input and normalise to naive UTC."""
    if value is None:
        return None
    parsed = _DATETIME_ADAPTER.validate_python(value)
    return to_naive_utc(parsed)


UtcNaiveDatetime = Annotated[datetime, BeforeValidator(_parse_to_naive_utc)]
"""A datetime field that is always naive UTC after validation."""
