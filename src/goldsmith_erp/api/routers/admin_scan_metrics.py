"""
Admin endpoint: scan-metrics dashboard data (V1.1 Slice 13 / §14.a).

Exposes the six V1.1 success-metric tiles (spec §14.a rows a-f) as a
single JSON document consumed by ``ScanAdoptionDashboard.tsx``. ADMIN
role is enforced via ``get_current_admin_user`` for parity with
``admin_email.py``.

The queries are the authoritative versions; the dashboard does NOT
re-compute ratios on the client. If the SQL needs to change, change it
here and in the companion .sql files under
``docs/field-test-kit/V1.1-scan-*.sql`` to keep copy-paste parity.

Security / privacy:

* VIEWER financial-leak avoidance is enforced upstream at
  ``/scan/resolve``; this endpoint is ADMIN-only and therefore aggregated
  counts do not leak per-user data. Outputs are scalar metrics, not
  per-user rows, so BDSG §26 employee-profiling concerns do not apply.
* The endpoint is read-only. No PII is ever emitted.

The underlying tables (``time_entries``, ``users``, ``scan_logs``,
``material_usage``) are all scoped to the single-tenant V1.1 data model.
V1.2 multi-tenancy will need to add a tenant filter here.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.api.deps import get_current_admin_user
from goldsmith_erp.db.models import (
    MaterialUsage,
    ScanLog,
    TimeEntry,
    User,
    UserRole,
)
from goldsmith_erp.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------


class ScanMetricsResponse(BaseModel):
    """
    Aggregate V1.1 acceptance-gate metrics. Each field corresponds to a
    row in spec §14.a (a-f).

    All ratios are expressed as 0-100 floats with NULL ('None') when the
    denominator is zero (empty window). The dashboard renders "—" in
    that case.
    """

    # --- Row (a) ---------------------------------------------------------
    scan_adoption_pct_30d: Optional[float] = Field(
        default=None,
        description=(
            "Primary metric. %% of GOLDSMITH time_entries in the last 30 "
            "days started via scan vs. manual. Corrected query per A13.1 "
            "(excludes test users, corrections, and 'import'/'recovery' "
            "origins from the denominator)."
        ),
    )
    scan_breadth_pct_7d: Optional[float] = Field(
        default=None,
        description=(
            "Secondary metric (A13.2). %% of GOLDSMITH users who used "
            "scan at least once in the last 7 days. User-count ratio, "
            "not row-count; immune to per-user scan-volume skew."
        ),
    )

    # --- Row (b) — latency will come from a future histogram endpoint.
    # V1.1 ships the scalar median + p95 as part of this response so the
    # dashboard has a single round-trip for all six tiles.
    fab_tap_to_timer_ms_p50: Optional[float] = Field(
        default=None,
        description=(
            "Median (p50) milliseconds between client_tap_at and "
            "server_resolved_at on scan_logs rows where both are set. "
            "Target <= 5000 ms, stop-ship > 10000 ms."
        ),
    )
    fab_tap_to_timer_ms_p95: Optional[float] = Field(
        default=None,
        description="p95 of the same latency distribution.",
    )

    # --- Row (c) ---------------------------------------------------------
    alloy_override_count_30d: int = Field(
        default=0,
        description=(
            "Number of MaterialUsage rows with alloy_override=TRUE in the "
            "last 30 days. Used alongside the synthetic-QR fixture set "
            "for row (c)."
        ),
    )

    # --- Row (d) ---------------------------------------------------------
    camera_fallback_count_30d: int = Field(
        default=0,
        description=(
            "scan_logs rows where fallback_reason='camera_denied' in the "
            "last 30 days. Target >= 1 over the field-test window."
        ),
    )

    # --- Row (e) ---------------------------------------------------------
    usb_hid_scan_count_30d: int = Field(
        default=0,
        description=(
            "scan_logs rows where context->>'input_source' = 'usb_hid' "
            "in the last 30 days. Target >= 1 across the whole workshop."
        ),
    )

    # --- Row (f) — bundle size lives in CI and trend CSV, not DB.
    # The dashboard renders a static link to docs/field-test-kit/bundle-trend.csv.

    # Metadata for the dashboard header.
    window_days_primary: int = 30
    window_days_breadth: int = 7
    computed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# Metric queries
# ---------------------------------------------------------------------------


async def _scan_adoption_pct_30d(db: AsyncSession) -> Optional[float]:
    """Primary metric — matches V1.1-scan-adoption-query.sql exactly."""
    cutoff = datetime.utcnow() - timedelta(days=30)
    stmt = (
        select(
            func.count(TimeEntry.id)
            .filter(TimeEntry.origin == "scan")
            .label("scan_count"),
            func.count(TimeEntry.id)
            .filter(TimeEntry.origin.in_(("scan", "manual")))
            .label("scan_or_manual_count"),
        )
        .join(User, User.id == TimeEntry.user_id)
        .where(
            TimeEntry.created_at > cutoff,
            User.role == UserRole.GOLDSMITH,
            User.is_test_user.is_(False),
            TimeEntry.correction_of.is_(None),
        )
    )
    result = (await db.execute(stmt)).one()
    scan_count = result.scan_count or 0
    denom = result.scan_or_manual_count or 0
    if denom == 0:
        return None
    return round((scan_count * 100.0) / denom, 2)


async def _scan_breadth_pct_7d(db: AsyncSession) -> Optional[float]:
    """Secondary metric — matches V1.1-scan-breadth-query.sql."""
    cutoff = datetime.utcnow() - timedelta(days=7)
    # We issue two distinct-count queries rather than one CASE-style query
    # because it's clearer and the cardinalities are small (< 20 users).
    scan_users_stmt = (
        select(func.count(func.distinct(TimeEntry.user_id)))
        .join(User, User.id == TimeEntry.user_id)
        .where(
            TimeEntry.created_at > cutoff,
            TimeEntry.origin == "scan",
            User.role == UserRole.GOLDSMITH,
            User.is_test_user.is_(False),
            TimeEntry.correction_of.is_(None),
        )
    )
    all_users_stmt = (
        select(func.count(func.distinct(TimeEntry.user_id)))
        .join(User, User.id == TimeEntry.user_id)
        .where(
            TimeEntry.created_at > cutoff,
            User.role == UserRole.GOLDSMITH,
            User.is_test_user.is_(False),
            TimeEntry.correction_of.is_(None),
        )
    )
    scan_users = (await db.execute(scan_users_stmt)).scalar_one() or 0
    all_users = (await db.execute(all_users_stmt)).scalar_one() or 0
    if all_users == 0:
        return None
    return round((scan_users * 100.0) / all_users, 2)


async def _alloy_override_count_30d(db: AsyncSession) -> int:
    cutoff = datetime.utcnow() - timedelta(days=30)
    stmt = select(func.count(MaterialUsage.id)).where(
        MaterialUsage.alloy_override.is_(True),
        MaterialUsage.created_at > cutoff,
    )
    return int((await db.execute(stmt)).scalar_one() or 0)


async def _camera_fallback_count_30d(db: AsyncSession) -> int:
    cutoff = datetime.utcnow() - timedelta(days=30)
    stmt = select(func.count(ScanLog.id)).where(
        ScanLog.fallback_reason == "camera_denied",
        ScanLog.scanned_at > cutoff,
    )
    return int((await db.execute(stmt)).scalar_one() or 0)


async def _usb_hid_scan_count_30d(db: AsyncSession) -> int:
    """
    Counts scan_logs rows where context JSON contains
    ``input_source == 'usb_hid'``. PostgreSQL path-op is used for
    efficient JSON filtering; SQLite falls back to fetching all rows
    and filtering in Python.

    The fallback is only exercised in unit-test fixtures where the
    backing DB is SQLite; production is always PostgreSQL.
    """
    cutoff = datetime.utcnow() - timedelta(days=30)
    dialect_name = db.bind.dialect.name if db.bind else ""
    if dialect_name == "postgresql":
        # `context ->> 'input_source'` extracts the text value.
        stmt = select(func.count(ScanLog.id)).where(
            ScanLog.scanned_at > cutoff,
            ScanLog.context["input_source"].as_string() == "usb_hid",
        )
        return int((await db.execute(stmt)).scalar_one() or 0)

    # SQLite fallback — JSON1 is optional and the JSON column is a TEXT
    # column on sqlite. Fetch rows in window and filter in Python.
    stmt = select(ScanLog.context).where(ScanLog.scanned_at > cutoff)
    rows = (await db.execute(stmt)).scalars().all()
    count = 0
    for ctx in rows:
        if isinstance(ctx, dict) and ctx.get("input_source") == "usb_hid":
            count += 1
    return count


async def _fab_tap_latency(
    db: AsyncSession,
) -> tuple[Optional[float], Optional[float]]:
    """
    Compute p50 and p95 of (server_resolved_at - client_tap_at) in ms
    across scan_logs rows where both timestamps are set. 30-day window.

    Uses percentile_cont on PostgreSQL; SQLite falls back to fetching
    deltas and computing percentiles in Python (fine for < 10k rows).
    """
    cutoff = datetime.utcnow() - timedelta(days=30)
    dialect_name = db.bind.dialect.name if db.bind else ""

    if dialect_name == "postgresql":
        # EXTRACT(EPOCH FROM ...) gives seconds as float; *1000 for ms.
        delta_sec = func.extract(
            "epoch", ScanLog.server_resolved_at - ScanLog.client_tap_at
        )
        stmt = select(
            func.percentile_cont(0.5).within_group(delta_sec).label("p50"),
            func.percentile_cont(0.95).within_group(delta_sec).label("p95"),
        ).where(
            ScanLog.scanned_at > cutoff,
            ScanLog.client_tap_at.isnot(None),
            ScanLog.server_resolved_at.isnot(None),
        )
        row = (await db.execute(stmt)).one_or_none()
        if not row or row.p50 is None:
            return None, None
        return round(float(row.p50) * 1000.0, 1), round(float(row.p95) * 1000.0, 1)

    # SQLite fallback
    stmt = select(ScanLog.client_tap_at, ScanLog.server_resolved_at).where(
        ScanLog.scanned_at > cutoff,
        ScanLog.client_tap_at.isnot(None),
        ScanLog.server_resolved_at.isnot(None),
    )
    rows = (await db.execute(stmt)).all()
    if not rows:
        return None, None
    deltas_ms = sorted(
        (b - a).total_seconds() * 1000.0
        for a, b in rows
        if a is not None and b is not None
    )
    if not deltas_ms:
        return None, None

    def _pct(p: float) -> float:
        # Nearest-rank percentile; good enough for small samples.
        idx = max(0, min(len(deltas_ms) - 1, int(round(p * (len(deltas_ms) - 1)))))
        return round(deltas_ms[idx], 1)

    return _pct(0.5), _pct(0.95)


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.get(
    "/admin/scan-metrics",
    response_model=ScanMetricsResponse,
    summary="V1.1 scan-metrics dashboard data",
    description=(
        "Aggregate scan-adoption metrics for the V1.1 30-day gate (spec "
        "§14.a rows a-f). ADMIN-only. Returns six tiles: primary "
        "adoption %, secondary breadth %, FAB-tap latency p50/p95, "
        "alloy-override count, camera-denied fallback count, and USB "
        "HID scan count. Bundle-size (row f) is tracked in CI and in "
        "docs/field-test-kit/bundle-trend.csv, not in this endpoint."
    ),
)
async def get_scan_metrics(
    db: AsyncSession = Depends(get_db),
    _current_user: User = Depends(get_current_admin_user),
) -> ScanMetricsResponse:
    adoption = await _scan_adoption_pct_30d(db)
    breadth = await _scan_breadth_pct_7d(db)
    alloy_overrides = await _alloy_override_count_30d(db)
    camera_fallback = await _camera_fallback_count_30d(db)
    usb_hid = await _usb_hid_scan_count_30d(db)
    p50_ms, p95_ms = await _fab_tap_latency(db)

    logger.info(
        "scan_metrics_queried",
        extra={
            "admin_user_id": _current_user.id,
            "adoption_pct": adoption,
            "breadth_pct": breadth,
        },
    )

    return ScanMetricsResponse(
        scan_adoption_pct_30d=adoption,
        scan_breadth_pct_7d=breadth,
        fab_tap_to_timer_ms_p50=p50_ms,
        fab_tap_to_timer_ms_p95=p95_ms,
        alloy_override_count_30d=alloy_overrides,
        camera_fallback_count_30d=camera_fallback,
        usb_hid_scan_count_30d=usb_hid,
    )
