"""Time helpers: aware UTC inside the application, Europe/Berlin for people.

BE-15 / docs/architecture/ADR-2026-09-25-numeric-and-tz.md:

- every datetime the application handles is timezone-aware UTC
  (``utcnow()``; the DB columns are ``TIMESTAMP WITH TIME ZONE``)
- naive values are still accepted at the boundaries for one release and are
  read as UTC (``ensure_utc``)
- documents and e-mails show Europe/Berlin local time (``format_local``)
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Optional, overload
from zoneinfo import ZoneInfo

UTC = timezone.utc
LOCAL_TZ = ZoneInfo("Europe/Berlin")

DATE_FORMAT = "%d.%m.%Y"
DATETIME_FORMAT = "%d.%m.%Y %H:%M"


def utcnow() -> datetime:
    """The current time as an aware UTC datetime."""
    return datetime.now(UTC)


@overload
def ensure_utc(value: datetime) -> datetime: ...


@overload
def ensure_utc(value: None) -> None: ...


def ensure_utc(value: Optional[datetime]) -> Optional[datetime]:
    """Return ``value`` as aware UTC; a naive value is read as UTC."""
    if value is None:
        return None
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def to_local(value: datetime) -> datetime:
    """Convert to Europe/Berlin (naive input is read as UTC)."""
    return ensure_utc(value).astimezone(LOCAL_TZ)


def format_local(
    value: Optional[datetime | date], fmt: str = DATETIME_FORMAT, empty: str = "-"
) -> str:
    """Render a datetime in Europe/Berlin local time for PDFs and e-mails.

    A plain ``date`` has no time zone and is formatted as is.
    """
    if value is None:
        return empty
    if isinstance(value, datetime):
        return to_local(value).strftime(fmt)
    return value.strftime(fmt)


def local_today() -> date:
    """Today's date in Europe/Berlin (a late-evening event is still today)."""
    return utcnow().astimezone(LOCAL_TZ).date()
