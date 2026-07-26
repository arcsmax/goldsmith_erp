#!/usr/bin/env python3
"""Production-safe reference-data seed for Goldsmith ERP.

This is the ONE seed path that is safe to run against a real production
database on every boot / upgrade.  It seeds only *reference data* — the pure
lookup rows an empty workshop needs on day one — and NOTHING else.

CONTRACT — this module NEVER creates:
  * users        (no demo staff, no shared demo passwords)
  * customers    (no PII)
  * orders / quotes / invoices / consultations / repairs (no business data)

It creates only:
  * the 15 standard goldsmith activities (time-tracking catalogue, incl. the
    V1.3 ``is_billable`` / ``hourly_rate`` rubric the estimator reads)
  * a standard materials catalogue (the common alloys + consumables a fresh
    workshop starts with — nominal reference prices, stock 0)

Idempotency (the whole point): every row is matched by its natural key
(activity → ``name`` + ``category``, material → ``name``) and inserted only
when absent.  Re-running is a no-op that returns zero-created counts, so it is
safe to wire behind an unconditional boot step — see the ``SEED_REFERENCE_DATA``
gate in ``main()`` and ``podman-compose.prod.yml``.

Wiring:
  * Boot hook: the prod backend command runs ``python -m
    goldsmith_erp.db.reference_seed`` right after ``alembic upgrade head``.
    ``SEED_REFERENCE_DATA=false`` turns it into a clean no-op exit.
  * Make target: ``make seed-production`` runs it inside the backend container.
  * CLI: ``python -m goldsmith_erp.db.reference_seed`` (reads DATABASE_URL via
    ``core.config.settings`` like the rest of the app).

Unlike ``db/seed_data.py`` (sync, DEV-ONLY, seeds demo users/customers/orders)
and ``scripts/seed_demo.py`` (the full demo showcase), this module is async,
uses the app's ``AsyncSessionLocal``, and is the reference-data source of truth
that the demo seeder composes on top of.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db._seed_helpers import filter_model_fields
from goldsmith_erp.db.models import Activity, Customer, Material, User

logger = logging.getLogger("reference_seed")

# ---------------------------------------------------------------------------
# Canonical reference data (single source of truth)
# ---------------------------------------------------------------------------

# The 15 standard goldsmith activities.  Names are the ASCII spellings the rest
# of the codebase already keys on (time-tracking, the demo seeder's activity
# map, the V1.3 estimator).  ``is_billable`` / ``hourly_rate`` follow the V1.3
# Phase-3 rubric: CAD/Design 85, Saegen/Feilen/Loeten 75, Polieren 65,
# Steinfassen 95, Endkontrolle 60; consultation / waiting / admin non-billable.
STANDARD_ACTIVITIES: tuple[dict[str, Any], ...] = (
    # Fertigung (fabrication)
    {
        "name": "Saegen",
        "category": "fabrication",
        "icon": "✂",
        "color": "#FF6B6B",
        "is_billable": True,
        "hourly_rate": 75,
    },
    {
        "name": "Feilen",
        "category": "fabrication",
        "icon": "\U0001f4a0",
        "color": "#4ECDC4",
        "is_billable": True,
        "hourly_rate": 75,
    },
    {
        "name": "Loeten",
        "category": "fabrication",
        "icon": "\U0001f525",
        "color": "#FF8C42",
        "is_billable": True,
        "hourly_rate": 75,
    },
    {
        "name": "Polieren",
        "category": "fabrication",
        "icon": "✨",
        "color": "#95E1D3",
        "is_billable": True,
        "hourly_rate": 65,
    },
    {
        "name": "Fassen (Steine)",
        "category": "fabrication",
        "icon": "\U0001f48e",
        "color": "#A8E6CF",
        "is_billable": True,
        "hourly_rate": 95,
    },
    {
        "name": "Gravieren",
        "category": "fabrication",
        "icon": "✏",
        "color": "#FFD3B6",
        "is_billable": False,
        "hourly_rate": None,
    },
    {
        "name": "Emaillieren",
        "category": "fabrication",
        "icon": "\U0001f3a8",
        "color": "#FFAAA5",
        "is_billable": False,
        "hourly_rate": None,
    },
    {
        "name": "Schmieden",
        "category": "fabrication",
        "icon": "\U0001f528",
        "color": "#E07A5F",
        "is_billable": False,
        "hourly_rate": None,
    },
    {
        "name": "Giessen",
        "category": "fabrication",
        "icon": "\U0001f3ed",
        "color": "#3D405B",
        "is_billable": False,
        "hourly_rate": None,
    },
    # Verwaltung (administration)
    {
        "name": "Kundenberatung",
        "category": "administration",
        "icon": "\U0001f4de",
        "color": "#d97706",
        "is_billable": False,
        "hourly_rate": None,
    },
    {
        "name": "Angebot erstellen",
        "category": "administration",
        "icon": "\U0001f4dd",
        "color": "#b45309",
        "is_billable": False,
        "hourly_rate": None,
    },
    {
        "name": "Dokumentation",
        "category": "administration",
        "icon": "\U0001f4cb",
        "color": "#92400e",
        "is_billable": False,
        "hourly_rate": None,
    },
    {
        "name": "Qualitaetskontrolle",
        "category": "administration",
        "icon": "\U0001f50d",
        "color": "#006BA6",
        "is_billable": True,
        "hourly_rate": 60,
    },
    # Wartezeit (waiting)
    {
        "name": "Warten auf Material",
        "category": "waiting",
        "icon": "⏳",
        "color": "#A0AEC0",
        "is_billable": False,
        "hourly_rate": None,
    },
    {
        "name": "Pause",
        "category": "waiting",
        "icon": "☕",
        "color": "#CBD5E0",
        "is_billable": False,
        "hourly_rate": None,
    },
)

# Standard materials catalogue.  These are *reference* rows: the common alloys
# and consumables any goldsmith workshop starts with.  Stock is 0 (inventory is
# operational data the workshop enters itself); ``unit_price`` is a nominal
# reference figure the workshop updates to its own supplier prices.
STANDARD_MATERIALS: tuple[dict[str, Any], ...] = (
    # Edelmetalle (alloys)
    {
        "name": "Gelbgold 750 (18K)",
        "description": "Legierung 750/000 Gelbgold, Standardlegierung fuer Schmuck",
        "unit_price": 62.50,
        "stock": 0.0,
        "unit": "g",
        "min_stock": 20.0,
    },
    {
        "name": "Weissgold 750 (18K)",
        "description": "Legierung 750/000 Weissgold mit Palladium, nickelfrei",
        "unit_price": 68.00,
        "stock": 0.0,
        "unit": "g",
        "min_stock": 15.0,
    },
    {
        "name": "Rotgold 750 (18K)",
        "description": "Legierung 750/000 Rotgold, kupferbetont",
        "unit_price": 63.00,
        "stock": 0.0,
        "unit": "g",
        "min_stock": 10.0,
    },
    {
        "name": "Gelbgold 585 (14K)",
        "description": "Legierung 585/000 Gelbgold",
        "unit_price": 47.50,
        "stock": 0.0,
        "unit": "g",
        "min_stock": 15.0,
    },
    {
        "name": "Silber 925 (Sterling)",
        "description": "Sterlingsilber 925/000 fuer Schmuck und Accessoires",
        "unit_price": 1.20,
        "stock": 0.0,
        "unit": "g",
        "min_stock": 50.0,
    },
    {
        "name": "Platin 950",
        "description": "Platin 950/000, hypoallergen, fuer hochwertige Trauringe",
        "unit_price": 38.00,
        "stock": 0.0,
        "unit": "g",
        "min_stock": 10.0,
    },
    {
        "name": "Palladium 950",
        "description": "Palladium 950/000, leicht und nickelfrei",
        "unit_price": 32.00,
        "stock": 0.0,
        "unit": "g",
        "min_stock": 5.0,
    },
    # Verbrauchsmaterial (consumables)
    {
        "name": "Hartlot Gold 750",
        "description": "Hartlot fuer Gold 750, Schmelzbereich 780-800 Grad C",
        "unit_price": 95.00,
        "stock": 0.0,
        "unit": "g",
        "min_stock": 2.0,
    },
    {
        "name": "Hartlot Silber 925",
        "description": "Hartlot fuer Silber 925",
        "unit_price": 3.50,
        "stock": 0.0,
        "unit": "g",
        "min_stock": 5.0,
    },
    {
        "name": "Saegeblaetter Gr. 3/0",
        "description": "Goldschmiedesaegeblaetter Groesse 3/0",
        "unit_price": 8.50,
        "stock": 0.0,
        "unit": "Stueck",
        "min_stock": 10.0,
    },
    {
        "name": "Polierpaste Rot (Eisenoxid)",
        "description": "Eisenoxid-Polierpaste fuer Hochglanzpolitur",
        "unit_price": 12.00,
        "stock": 0.0,
        "unit": "Stueck",
        "min_stock": 1.0,
    },
    {
        "name": "Rhodium-Bad Loesung",
        "description": "Rhodinierungs-Loesung fuer Weissgold-Oberflaeche",
        "unit_price": 185.00,
        "stock": 0.0,
        "unit": "Stueck",
        "min_stock": 1.0,
    },
)

# Environment flag that gates the boot hook.  Default ON so a fresh production
# deploy gets its reference data without an extra manual step.
_SEED_FLAG_ENV = "SEED_REFERENCE_DATA"


def _reference_seed_enabled() -> bool:
    """Return whether the boot hook should seed (default: yes)."""
    return os.getenv(_SEED_FLAG_ENV, "true").strip().lower() not in {
        "false",
        "0",
        "no",
        "off",
    }


# ---------------------------------------------------------------------------
# Seed functions (idempotent, upsert-or-skip by natural key)
# ---------------------------------------------------------------------------


async def seed_reference_activities(
    db: AsyncSession, *, commit: bool = False
) -> tuple[int, int]:
    """Insert the 15 standard activities that don't already exist.

    Natural key: (``name``, ``category``).  Returns ``(created, skipped)``.
    Flushes so intra-session re-checks see the new rows; commits only when
    asked (the demo seeder composes this inside its own transaction).
    """
    created = 0
    skipped = 0
    for data in STANDARD_ACTIVITIES:
        exists = await db.scalar(
            select(Activity.id).where(
                Activity.name == data["name"],
                Activity.category == data["category"],
            )
        )
        if exists is not None:
            skipped += 1
            continue

        payload = filter_model_fields(
            Activity,
            {**data, "usage_count": 0, "is_custom": False, "created_by": None},
        )
        db.add(Activity(**payload))
        created += 1

    await db.flush()
    if commit:
        await db.commit()
    logger.info("Reference activities: %d created, %d skipped", created, skipped)
    return created, skipped


async def seed_reference_materials(
    db: AsyncSession, *, commit: bool = False
) -> tuple[int, int]:
    """Insert the standard materials catalogue rows that don't already exist.

    Natural key: ``name``.  Returns ``(created, skipped)``.
    """
    created = 0
    skipped = 0
    for data in STANDARD_MATERIALS:
        exists = await db.scalar(
            select(Material.id).where(Material.name == data["name"])
        )
        if exists is not None:
            skipped += 1
            continue

        db.add(Material(**filter_model_fields(Material, dict(data))))
        created += 1

    await db.flush()
    if commit:
        await db.commit()
    logger.info("Reference materials: %d created, %d skipped", created, skipped)
    return created, skipped


async def seed_reference_data(
    db: AsyncSession, *, commit: bool = True
) -> dict[str, int]:
    """Seed all reference data (activities + materials), idempotently.

    Commits by default so the standalone / boot-hook path persists its work.
    Callers that compose this inside a larger transaction (the demo seeder)
    pass ``commit=False``.
    """
    act_created, act_skipped = await seed_reference_activities(db, commit=False)
    mat_created, mat_skipped = await seed_reference_materials(db, commit=False)
    if commit:
        await db.commit()
    return {
        "activities_created": act_created,
        "activities_skipped": act_skipped,
        "materials_created": mat_created,
        "materials_skipped": mat_skipped,
    }


# ---------------------------------------------------------------------------
# Standalone / boot-hook entrypoint
# ---------------------------------------------------------------------------


async def _run() -> dict[str, int]:
    """Open a session, seed reference data, and assert the prod-safety contract.

    The zero-users / zero-customers assertion is a defence-in-depth guard: this
    module must never introduce identity or PII rows.  If it ever does, boot
    fails loudly instead of silently polluting a production DB.
    """
    from goldsmith_erp.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        users_before = await db.scalar(select(func.count()).select_from(User))
        customers_before = await db.scalar(select(func.count()).select_from(Customer))

        result = await seed_reference_data(db, commit=True)

        users_after = await db.scalar(select(func.count()).select_from(User))
        customers_after = await db.scalar(select(func.count()).select_from(Customer))

    if users_after != users_before or customers_after != customers_before:
        raise RuntimeError(
            "reference_seed violated its contract: it changed the User/Customer "
            f"row count (users {users_before}->{users_after}, customers "
            f"{customers_before}->{customers_after}). Refusing to continue."
        )

    logger.info(
        "Reference data seeded: %d activities created (%d skipped), "
        "%d materials created (%d skipped).",
        result["activities_created"],
        result["activities_skipped"],
        result["materials_created"],
        result["materials_skipped"],
    )
    return result


def main() -> None:
    """CLI / boot-hook entry. Honours ``SEED_REFERENCE_DATA`` (default true)."""
    logging.basicConfig(
        level=logging.INFO, format="  [%(levelname)s] %(name)s: %(message)s"
    )
    if not _reference_seed_enabled():
        logger.info("%s is disabled — skipping reference-data seed.", _SEED_FLAG_ENV)
        return
    asyncio.run(_run())


if __name__ == "__main__":
    main()
