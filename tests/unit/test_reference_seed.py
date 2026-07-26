"""Tests for the production-safe reference-data seed (``db/reference_seed.py``).

Covers finding 1.6's contract:
  * idempotency — running twice creates no duplicates (safe for boot/upgrade),
  * production-safety — it creates ZERO User and ZERO Customer rows,
  * completeness — all 15 standard activities land, including every name the
    demo seeder's ``act_map`` looks up (drift guard),
  * the ``SEED_REFERENCE_DATA`` boot-gate parsing.

All DB tests use the shared in-memory SQLite ``db_session`` fixture.
"""

from __future__ import annotations

import pytest
from sqlalchemy import func, select

from goldsmith_erp.db.models import Activity, Customer, Material, User
from goldsmith_erp.db.reference_seed import (
    STANDARD_ACTIVITIES,
    STANDARD_MATERIALS,
    _reference_seed_enabled,
    seed_reference_data,
)

# Activity names the demo seeder (``scripts/seed_demo.py``) looks up by name in
# ``seed_time_entries`` — if the reference list ever drops one of these, the
# demo seed breaks. This locks the two in step.
_DEMO_ACT_MAP_NAMES = {
    "Fassen (Steine)",
    "Feilen",
    "Giessen",
    "Gravieren",
    "Kundenberatung",
    "Loeten",
    "Polieren",
    "Qualitaetskontrolle",
    "Saegen",
    "Schmieden",
}


async def _count(db, model) -> int:
    return await db.scalar(select(func.count()).select_from(model))


@pytest.mark.asyncio
async def test_reference_seed_creates_expected_counts(db_session):
    """A first run creates all standard activities + materials."""
    result = await seed_reference_data(db_session, commit=True)

    assert result["activities_created"] == len(STANDARD_ACTIVITIES) == 15
    assert result["materials_created"] == len(STANDARD_MATERIALS)
    assert await _count(db_session, Activity) == len(STANDARD_ACTIVITIES)
    assert await _count(db_session, Material) == len(STANDARD_MATERIALS)


@pytest.mark.asyncio
async def test_reference_seed_is_idempotent(db_session):
    """Running twice must not create duplicates — row counts stay identical."""
    await seed_reference_data(db_session, commit=True)
    activities_after_first = await _count(db_session, Activity)
    materials_after_first = await _count(db_session, Material)

    second = await seed_reference_data(db_session, commit=True)

    # Second run created nothing and skipped everything.
    assert second["activities_created"] == 0
    assert second["materials_created"] == 0
    assert second["activities_skipped"] == len(STANDARD_ACTIVITIES)
    assert second["materials_skipped"] == len(STANDARD_MATERIALS)

    # Counts unchanged — no duplicate rows.
    assert await _count(db_session, Activity) == activities_after_first
    assert await _count(db_session, Material) == materials_after_first


@pytest.mark.asyncio
async def test_reference_seed_creates_no_users_or_customers(db_session):
    """The production seed must NEVER introduce identity or PII rows."""
    await seed_reference_data(db_session, commit=True)

    assert await _count(db_session, User) == 0
    assert await _count(db_session, Customer) == 0

    # Idempotent re-run: still zero.
    await seed_reference_data(db_session, commit=True)
    assert await _count(db_session, User) == 0
    assert await _count(db_session, Customer) == 0


@pytest.mark.asyncio
async def test_reference_seed_covers_demo_activity_lookups(db_session):
    """Every name the demo's time-entry act_map keys on must exist after seeding."""
    await seed_reference_data(db_session, commit=True)

    names = set((await db_session.execute(select(Activity.name))).scalars().all())
    missing = _DEMO_ACT_MAP_NAMES - names
    assert not missing, f"reference seed is missing demo act_map names: {missing}"


@pytest.mark.asyncio
async def test_reference_seed_materials_have_zero_stock(db_session):
    """Reference materials are a catalogue, not inventory — stock starts at 0."""
    await seed_reference_data(db_session, commit=True)

    stocks = (await db_session.execute(select(Material.stock))).scalars().all()
    assert stocks and all(s == 0.0 for s in stocks)


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, True),  # unset → default ON
        ("true", True),
        ("True", True),
        ("1", True),
        ("false", False),
        ("0", False),
        ("no", False),
        ("off", False),
        ("  FALSE  ", False),
    ],
)
def test_reference_seed_enabled_flag_parsing(monkeypatch, value, expected):
    """The boot-gate defaults ON and turns off only for explicit false-ish values."""
    if value is None:
        monkeypatch.delenv("SEED_REFERENCE_DATA", raising=False)
    else:
        monkeypatch.setenv("SEED_REFERENCE_DATA", value)
    assert _reference_seed_enabled() is expected
