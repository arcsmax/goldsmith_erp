"""Partial seeder that bypasses the ``SENTINEL_EMAIL`` global gate in
``scripts/seed_demo.py`` and runs the full V1.0 + V1.1 + V1.2 demo set
against an existing DB that has real data in it.

**Two-transaction design**: Phase A (V1.0 + V1.1) commits before Phase B
(V1.2 customer updates + cost changes) starts.  Reason: ``seed_customer_updates``
indexes into ``orders[0..4]`` and ``repairs[3]`` — when those don't exist,
the call raises ``IndexError`` and a single-transaction run would ROLLBACK
the entire 5-minute Phase A work, leaving the user with **no** seeded
consultations.  Splitting the commit boundary protects Phase A even when
Phase B blows up.

Why this exists at all: the full ``scripts/seed_demo.py`` bails out as soon
as ``demo-goldschmied@werkstatt.de`` exists.  When a real user has been
working in the DB without that sentinel, the seeder *would* run — but it
would also try to create the entire V1.0 demo set (12 customers, 18
materials, 12 orders, 4 quotes, etc.) on top of the user's real data.
This wrapper does the same thing but commits Phase A early so the user
sees the consultations right away.

Idempotency: each phase has its own existence checks.  The whole Phase A
is wrapped in one transaction that commits; Phase B is a second
transaction.  A re-run is a no-op (the underlying ``seed_*`` functions
all check for existing natural keys).

Pre-conditions:
  * Alembic migrations are up to date (``alembic upgrade head``).
  * DATABASE_URL points at the dev DB.
  * The V1.1 + V1.2 + photo tables exist (consultations, customer_updates,
    consultation_photos, order_photos, repair_photos, cost_change_requests).

Usage::

    DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5434/goldsmith \\
        poetry run python scripts/seed_v11_v12_only.py
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO_ROOT / "src"))
sys.path.insert(0, str(_REPO_ROOT / "scripts"))

import seed_demo as _sd  # noqa: E402
from goldsmith_erp.db.session import AsyncSessionLocal  # noqa: E402

logger = logging.getLogger("seed_v11_v12_only")


# ---------------------------------------------------------------------------
# Phase A — V1.0 + V1.1 in one transaction.
# ---------------------------------------------------------------------------


async def run_phase_a() -> None:
    """V1.0 + V1.1 entities, committed as one transaction.

    On success: ~10 customers, ~17 materials, 15 orders, 6 repair_jobs, 4
    quotes, 4 invoices, 24 time_entries, 6 calendar events, 12 notifications,
    5 consultations, 6 consultation_photos, 9 order_photos, 8 repair_photos.
    """
    async with AsyncSessionLocal() as db:
        # --- V1.0 phases 1..10 (no sentinel gate) ---
        users = await _sd.seed_users(db)
        activities = await _sd.seed_activities(db, users[0])
        customers = await _sd.seed_customers(db)
        await _sd.seed_measurements(db, customers, users[0])
        materials = await _sd.seed_materials(db)
        metal_purchases = await _sd.seed_metal_purchases(db)
        orders = await _sd.seed_orders(db, customers, users, metal_purchases)
        await _sd.seed_gemstones(db, orders)
        await _sd.seed_material_usage(db, orders, metal_purchases)
        time_entries = await _sd.seed_time_entries(
            db, orders, users, activities
        )
        await _sd.seed_interruptions(db, time_entries)
        repairs = await _sd.seed_repair_jobs(db, customers, users)
        quotes = await _sd.seed_quotes(db, orders, customers, users)
        await _sd.seed_invoices(db, orders, customers, users)
        await _sd.seed_scrap_gold(db, orders, customers, users)
        await _sd.seed_calendar_events(db, orders, users)
        await _sd.seed_notifications(db, orders, customers, users)
        await _sd.seed_comments(db, orders, users)
        await _sd.seed_handoffs(db, orders, users)
        await _sd.seed_hallmarks(db, orders, users)
        await _sd.seed_valuation_certificates(
            db, orders, customers, users
        )
        await _sd.seed_location_history(db, orders, users)

        # --- V1.1 phases 11 + 12 (consultations + photos) ---
        consultations = await _sd.seed_consultations(
            db, customers, orders, quotes, users
        )
        await _sd.seed_consultation_photos(db, consultations, users)
        await _sd.seed_order_photos(db, orders, time_entries, users)
        await _sd.seed_repair_photos(db, repairs, users)

        # Commit Phase A — once this returns, the 5 consultations are durable
        # in the DB and visible in the UI even if Phase B fails.
        await db.commit()
        logger.info(
            "Phase A committed: %d consultations, %d orders, %d repairs, %d quotes",
            len(consultations),
            len(orders),
            len(repairs),
            len(quotes),
        )


# ---------------------------------------------------------------------------
# Phase B — V1.2 in a separate transaction.  Phase A is already committed.
# ---------------------------------------------------------------------------


async def run_phase_b() -> None:
    """V1.2 customer updates + cost change requests, in a fresh transaction.

    This phase can fail without rolling back Phase A.  Re-runs are safe —
    the underlying seeders check for existing natural keys.
    """
    from sqlalchemy import select

    from goldsmith_erp.db.models import (
        Order,
        RepairJob,
        User,
    )

    async with AsyncSessionLocal() as db:
        users = (
            (await db.execute(
                select(User).where(User.role.in_(["goldsmith", "admin"]))
            )).scalars().all()
        )
        if not users:
            logger.warning(
                "Phase B skipped: keine goldsmith/admin-User in der DB."
            )
            return

        orders = (
            (await db.execute(select(Order))).scalars().all()
        )
        repairs = (
            (await db.execute(select(RepairJob))).scalars().all()
        )

        # Sanity: seed_customer_updates needs orders[0..4] + repairs[3].
        # seed_cost_change_requests needs orders[4].
        if len(orders) < 5:
            logger.warning(
                "Phase B: nur %d Orders, brauche >= 5 — ueberspringe "
                "seed_customer_updates.", len(orders),
            )
        else:
            await _sd.seed_customer_updates(db, orders, repairs, list(users))
            logger.info("Phase B: customer_updates erstellt")

        if len(orders) < 5:
            logger.warning(
                "Phase B: nur %d Orders, brauche >= 5 — ueberspringe "
                "seed_cost_change_requests.", len(orders),
            )
        else:
            await _sd.seed_cost_change_requests(db, orders, list(users))
            logger.info("Phase B: cost_change_requests erstellt")

        await db.commit()
        logger.info("Phase B committed.")


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


async def summarize() -> None:
    """Print post-seed row counts grouped by V1.0 / V1.1 / V1.2."""
    from sqlalchemy import select

    from goldsmith_erp.db.models import (
        Consultation,
        ConsultationPhoto,
        CostChangeRequest,
        Customer,
        CustomerUpdate,
        Invoice,
        Material,
        Order,
        OrderPhoto,
        Quote,
        RepairJob,
        RepairPhoto,
        TimeEntry,
        User,
    )

    async with AsyncSessionLocal() as db:
        rows: list[tuple[str, int]] = []
        for name, model in [
            ("users", User),
            ("customers", Customer),
            ("materials", Material),
            ("orders", Order),
            ("quotes", Quote),
            ("invoices", Invoice),
            ("time_entries", TimeEntry),
            ("repairs", RepairJob),
            ("consultations", Consultation),
            ("consultation_photos", ConsultationPhoto),
            ("order_photos", OrderPhoto),
            ("repair_photos", RepairPhoto),
            ("customer_updates", CustomerUpdate),
            ("cost_change_requests", CostChangeRequest),
        ]:
            n = len(list((await db.execute(select(model))).scalars().all()))
            rows.append((name, n))

        logger.info("=" * 60)
        logger.info("  Row counts in DB after re-seed:")
        for n, v in rows:
            logger.info("    %-22s %d", n, v)
        logger.info("=" * 60)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> None:
    await run_phase_a()
    try:
        await run_phase_b()
    except Exception as e:  # noqa: BLE001
        logger.exception("Phase B fehlgeschlagen — Phase A ist bereits committet: %s", e)
    await summarize()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="  [%(levelname)s] %(message)s",
    )
    logger.info("Starte V1.0+V1.1+V1.2 re-seed (2 Transaktionen)…")
    asyncio.run(main())
