"""Shared helpers for the seed paths.

Keeps date arithmetic, UUID minting, and the forward-compatibility filter in
one place so that ``scripts/seed_demo.py``, ``db/seed_data.py``,
``db/reference_seed.py`` (and any future seed script) cannot drift out of step.

Split responsibility: :func:`filter_model_fields` / :func:`filter_per_field_models`
are pure schema-drift shims safe to use anywhere — including the production
reference-data seed (``db/reference_seed.py``).  The date / UUID helpers below
are fixture conveniences for the DEMO / sample seeders only, not runtime data
paths.  See ``scripts/seed_demo.py`` and ``db/seed_data.py`` for usage.
"""

from __future__ import annotations

import uuid as _uuid_lib
from datetime import datetime, timedelta
from typing import Any, Iterable

# Frozen-at-import time so the entire run of a single seed script computes
# timestamps relative to the SAME instant — keeps "now", "today", and
# "_days_ago(N)" internally consistent without requiring callers to thread
# a clock through every function.
NOW: datetime = datetime.utcnow()
TODAY: datetime = NOW.replace(hour=0, minute=0, second=0, microsecond=0)


def days_ago(n: int) -> datetime:
    """Return NOW minus ``n`` days (calendar resolution, time-of-day preserved)."""
    return NOW - timedelta(days=n)


def days_from_now(n: int) -> datetime:
    """Return NOW plus ``n`` days."""
    return NOW + timedelta(days=n)


def hours_ago(n: int) -> datetime:
    """Return NOW minus ``n`` hours."""
    return NOW - timedelta(hours=n)


def fresh_uuid() -> str:
    """Mint a fresh UUID4 hex — used for string-PK tables (OrderPhoto, TimeEntry)."""
    return str(_uuid_lib.uuid4())


# 12-month realistic time-spread that gives the V1.3 ML estimator enough
# variance to learn from.  Rounded Fibonacci days sample across the year
# in an organic-looking way without depending on calendar arithmetic.
# Callers can string these together to build a year of timestamps.
FIBONACCI_DAYS: tuple[int, ...] = (1, 2, 3, 5, 8, 13, 21, 34, 55, 89, 144, 233, 365)


def fibonacci_days_ago() -> list[datetime]:
    """Return a list of ``FIBONACCI_DAYS``-ago timestamps, **newest first**.

    Iteration order matches the underlying ``FIBONACCI_DAYS`` tuple
    (1, 2, 3, 5, 8, …) which yields the smallest day-count first (i.e.
    closest to ``NOW``).  Callers that need oldest-first should sort the
    result, e.g. ``sorted(fibonacci_days_ago())``.
    """
    return [days_ago(n) for n in FIBONACCI_DAYS]


def filter_model_fields(model_cls: type, data: dict[str, Any]) -> dict[str, Any]:
    """Return only fields that exist as columns on the given ORM model.

    Forward-compatibility shim — drops aspirational / drifty keys silently
    instead of raising ``TypeError: __init__() got an unexpected keyword
    argument``.  Used by every seed function so that adding a column to the
    ORM between releases does not break an old seed script pulled in by a
    rolling deploy.

    See also: ``scripts/seed_data.py`` for the original inline
    implementation that this replaces.
    """
    valid_columns = {col.key for col in model_cls.__table__.columns}  # type: ignore[attr-defined]
    return {k: v for k, v in data.items() if k in valid_columns}


def filter_per_field_models(
    model_classes: Iterable[type], data: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    """Variant of :func:`filter_model_fields` that returns one filtered dict per
    model class — handy when a single seed-data payload is reused across
    multiple ORM tables (e.g. an audit log row mirrors several columns of the
    primary entity).
    """
    return {cls.__name__: filter_model_fields(cls, data) for cls in model_classes}
