"""
Integration tests for GET /api/v1/admin/scan-metrics (Slice 13).

Covers:
  * ADMIN receives the six-tile payload with correct scalars.
  * GOLDSMITH and VIEWER are rejected with 403.
  * Unauthenticated is rejected with 401.
  * Empty window returns None for ratio metrics and 0 for counters.
  * Test users, correction rows, and non-GOLDSMITH roles are excluded
    from the adoption + breadth ratios (A13.1 / A13.2 contract).
  * alloy_override count, camera_fallback count, and usb_hid count
    reflect only the last-30-day window.

The metrics endpoint is ADMIN-only by design — it does not contain PII
but the aggregate numbers are business-sensitive (employee profiling
risk under BDSG §26 — A14.2).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import (
    Activity,
    MaterialUsage,
    MetalPurchase,
    MetalType,
    Order,
    OrderStatusEnum,
    ScanLog,
    TimeEntry,
    User,
    UserRole,
)
from goldsmith_erp.core.security import get_password_hash


METRICS_URL = "/api/v1/admin/scan-metrics"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unique(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:8]}"


async def _make_user(
    db: AsyncSession,
    *,
    role: UserRole = UserRole.GOLDSMITH,
    is_test_user: bool = False,
) -> User:
    user = User(
        email=f"{_unique('scan_metrics')}@integration-test.example.com",
        hashed_password=get_password_hash("TestPass123!"),
        first_name="Scan",
        last_name="Metrics",
        role=role,
        is_active=True,
        is_test_user=is_test_user,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def _make_order(db: AsyncSession, user: User) -> Order:
    order = Order(
        title=f"Order {_unique('o')}",
        customer_id=None,
        status=OrderStatusEnum.IN_PROGRESS,
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)
    return order


async def _make_activity(db: AsyncSession, user: User) -> Activity:
    activity = Activity(
        name=f"Activity {_unique('a')}",
        category="fabrication",
        created_by=user.id,
    )
    db.add(activity)
    await db.commit()
    await db.refresh(activity)
    return activity


async def _make_metal_purchase(db: AsyncSession) -> MetalPurchase:
    mp = MetalPurchase(
        date_purchased=datetime.now(timezone.utc),
        metal_type=MetalType.GOLD_14K,
        weight_g=100.0,
        remaining_weight_g=100.0,
        price_total=5000.0,
        price_per_gram=50.0,
    )
    db.add(mp)
    await db.commit()
    await db.refresh(mp)
    return mp


async def _make_time_entry(
    db: AsyncSession,
    user: User,
    order: Order,
    activity: Activity,
    *,
    origin: str,
    correction_of: str | None = None,
    created_at: datetime | None = None,
) -> TimeEntry:
    entry = TimeEntry(
        id=str(uuid.uuid4()),
        user_id=user.id,
        order_id=order.id,
        activity_id=activity.id,
        start_time=datetime.now(timezone.utc),
        origin=origin,
        correction_of=correction_of,
    )
    if created_at is not None:
        entry.created_at = created_at
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


# ---------------------------------------------------------------------------
# Auth guards
# ---------------------------------------------------------------------------


class TestScanMetricsAuthGuards:
    @pytest.mark.asyncio
    async def test_unauthenticated_returns_401(self, client: AsyncClient):
        response = await client.get(METRICS_URL)
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_goldsmith_forbidden(
        self, client: AsyncClient, goldsmith_auth_headers: dict
    ):
        response = await client.get(METRICS_URL, headers=goldsmith_auth_headers)
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_forbidden(
        self, client: AsyncClient, viewer_auth_headers: dict
    ):
        response = await client.get(METRICS_URL, headers=viewer_auth_headers)
        assert response.status_code == 403


# ---------------------------------------------------------------------------
# Empty-state defaults
# ---------------------------------------------------------------------------


class TestScanMetricsEmptyState:
    @pytest.mark.asyncio
    async def test_empty_db_returns_none_ratios_and_zero_counters(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        """A fresh DB with no time_entries / scan_logs must not divide by zero."""
        response = await client.get(METRICS_URL, headers=admin_auth_headers)
        assert response.status_code == 200
        body = response.json()
        assert body["scan_adoption_pct_30d"] is None
        assert body["scan_breadth_pct_7d"] is None
        assert body["fab_tap_to_timer_ms_p50"] is None
        assert body["fab_tap_to_timer_ms_p95"] is None
        assert body["alloy_override_count_30d"] == 0
        assert body["camera_fallback_count_30d"] == 0
        assert body["usb_hid_scan_count_30d"] == 0
        assert body["window_days_primary"] == 30
        assert body["window_days_breadth"] == 7


# ---------------------------------------------------------------------------
# Primary adoption metric (A13.1)
# ---------------------------------------------------------------------------


class TestScanAdoptionPct:
    @pytest.mark.asyncio
    async def test_scan_vs_manual_only_ratio(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        db_session: AsyncSession,
    ):
        """3 scan + 1 manual row for GOLDSMITH -> 75.0%. 'import' row excluded."""
        gm = await _make_user(db_session, role=UserRole.GOLDSMITH)
        order = await _make_order(db_session, gm)
        activity = await _make_activity(db_session, gm)
        for origin in ("scan", "scan", "scan", "manual", "import", "recovery"):
            await _make_time_entry(
                db_session, gm, order, activity, origin=origin
            )

        response = await client.get(METRICS_URL, headers=admin_auth_headers)
        assert response.status_code == 200
        # 3 / (3 + 1) = 75.00
        assert response.json()["scan_adoption_pct_30d"] == pytest.approx(75.0)

    @pytest.mark.asyncio
    async def test_test_users_excluded(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        db_session: AsyncSession,
    ):
        """A13.1 contract: is_test_user=True rows must not enter either side."""
        real = await _make_user(db_session, role=UserRole.GOLDSMITH)
        test = await _make_user(
            db_session, role=UserRole.GOLDSMITH, is_test_user=True
        )
        order_real = await _make_order(db_session, real)
        order_test = await _make_order(db_session, test)
        activity = await _make_activity(db_session, real)
        # Real GOLDSMITH: 1 scan, 1 manual -> 50%.
        await _make_time_entry(
            db_session, real, order_real, activity, origin="scan"
        )
        await _make_time_entry(
            db_session, real, order_real, activity, origin="manual"
        )
        # Test user: 5 scan rows — if included they would skew to ~85%.
        for _ in range(5):
            await _make_time_entry(
                db_session, test, order_test, activity, origin="scan"
            )

        response = await client.get(METRICS_URL, headers=admin_auth_headers)
        assert response.json()["scan_adoption_pct_30d"] == pytest.approx(50.0)

    @pytest.mark.asyncio
    async def test_correction_rows_excluded(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        db_session: AsyncSession,
    ):
        """A13.1 contract: correction_of IS NOT NULL rows are excluded."""
        gm = await _make_user(db_session, role=UserRole.GOLDSMITH)
        order = await _make_order(db_session, gm)
        activity = await _make_activity(db_session, gm)
        base = await _make_time_entry(
            db_session, gm, order, activity, origin="scan"
        )
        await _make_time_entry(
            db_session, gm, order, activity, origin="manual"
        )
        # Correction of the scan row. Must be excluded entirely.
        await _make_time_entry(
            db_session,
            gm,
            order,
            activity,
            origin="scan",
            correction_of=base.id,
        )

        # Without correction exclusion the ratio would be 2/3 = 66.67%.
        # With exclusion it is 1 scan / (1 scan + 1 manual) = 50%.
        response = await client.get(METRICS_URL, headers=admin_auth_headers)
        assert response.json()["scan_adoption_pct_30d"] == pytest.approx(50.0)

    @pytest.mark.asyncio
    async def test_non_goldsmith_roles_excluded(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        db_session: AsyncSession,
    ):
        """Admin diagnostic starts should not pollute the denominator."""
        gm = await _make_user(db_session, role=UserRole.GOLDSMITH)
        admin = await _make_user(db_session, role=UserRole.ADMIN)
        order = await _make_order(db_session, gm)
        activity = await _make_activity(db_session, gm)
        await _make_time_entry(
            db_session, gm, order, activity, origin="scan"
        )
        # Admin diagnostic — must be excluded.
        await _make_time_entry(
            db_session, admin, order, activity, origin="manual"
        )

        response = await client.get(METRICS_URL, headers=admin_auth_headers)
        # 1 / 1 = 100% because admin row excluded.
        assert response.json()["scan_adoption_pct_30d"] == pytest.approx(100.0)


# ---------------------------------------------------------------------------
# Secondary breadth metric (A13.2)
# ---------------------------------------------------------------------------


class TestScanBreadthPct:
    @pytest.mark.asyncio
    async def test_breadth_is_user_count_ratio_not_row_count(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        db_session: AsyncSession,
    ):
        """Two GOLDSMITH users; one scans many, the other only manual.

        Row-count ratio would be ~90%+, user-count breadth ratio is 50%.
        """
        heavy = await _make_user(db_session, role=UserRole.GOLDSMITH)
        light = await _make_user(db_session, role=UserRole.GOLDSMITH)
        order_h = await _make_order(db_session, heavy)
        order_l = await _make_order(db_session, light)
        activity = await _make_activity(db_session, heavy)
        for _ in range(20):
            await _make_time_entry(
                db_session, heavy, order_h, activity, origin="scan"
            )
        for _ in range(2):
            await _make_time_entry(
                db_session, light, order_l, activity, origin="manual"
            )

        response = await client.get(METRICS_URL, headers=admin_auth_headers)
        body = response.json()
        assert body["scan_breadth_pct_7d"] == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# Counter tiles
# ---------------------------------------------------------------------------


class TestCounterTiles:
    @pytest.mark.asyncio
    async def test_alloy_override_count(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        db_session: AsyncSession,
    ):
        gm = await _make_user(db_session, role=UserRole.GOLDSMITH)
        order = await _make_order(db_session, gm)
        mp = await _make_metal_purchase(db_session)
        # Row with override.
        db_session.add(
            MaterialUsage(
                order_id=order.id,
                metal_purchase_id=mp.id,
                weight_used_g=1.0,
                cost_at_time=50.0,
                price_per_gram_at_time=50.0,
                alloy_override=True,
                override_reason_category="charge_abweichung",
                override_reason="Reste",
                user_id=gm.id,
            )
        )
        # Row without override.
        db_session.add(
            MaterialUsage(
                order_id=order.id,
                metal_purchase_id=mp.id,
                weight_used_g=2.0,
                cost_at_time=100.0,
                price_per_gram_at_time=50.0,
                alloy_override=False,
                user_id=gm.id,
            )
        )
        await db_session.commit()

        response = await client.get(METRICS_URL, headers=admin_auth_headers)
        assert response.json()["alloy_override_count_30d"] == 1

    @pytest.mark.asyncio
    async def test_camera_fallback_and_usb_hid_counts(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        db_session: AsyncSession,
    ):
        gm = await _make_user(db_session, role=UserRole.GOLDSMITH)
        now = datetime.now(timezone.utc)
        db_session.add(
            ScanLog(
                user_id=gm.id,
                scanned_at=now,
                raw_payload="ORDER:1",
                fallback_reason="camera_denied",
                context={"input_source": "manual"},
            )
        )
        db_session.add(
            ScanLog(
                user_id=gm.id,
                scanned_at=now,
                raw_payload="ORDER:2",
                context={"input_source": "usb_hid"},
            )
        )
        db_session.add(
            ScanLog(
                user_id=gm.id,
                scanned_at=now,
                raw_payload="ORDER:3",
                context={"input_source": "camera"},
            )
        )
        await db_session.commit()

        response = await client.get(METRICS_URL, headers=admin_auth_headers)
        body = response.json()
        assert body["camera_fallback_count_30d"] == 1
        assert body["usb_hid_scan_count_30d"] == 1


# ---------------------------------------------------------------------------
# Latency histogram (SQLite percentile-fallback path)
# ---------------------------------------------------------------------------


class TestFabTapLatency:
    @pytest.mark.asyncio
    async def test_p50_p95_computed_on_sqlite_fallback(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        db_session: AsyncSession,
    ):
        gm = await _make_user(db_session, role=UserRole.GOLDSMITH)
        now = datetime.now(timezone.utc)
        # Deltas 1, 2, 3, 4, 5 seconds. p50 = 3000 ms, p95 -> nearest-rank = 5000 ms.
        for sec in (1, 2, 3, 4, 5):
            tap = now - timedelta(minutes=1)
            resolved = tap + timedelta(seconds=sec)
            db_session.add(
                ScanLog(
                    user_id=gm.id,
                    scanned_at=now,
                    raw_payload=f"ORDER:{sec}",
                    client_tap_at=tap,
                    server_resolved_at=resolved,
                )
            )
        await db_session.commit()

        response = await client.get(METRICS_URL, headers=admin_auth_headers)
        body = response.json()
        # Nearest-rank p50 on an odd-length sample picks the middle -> 3000 ms.
        assert body["fab_tap_to_timer_ms_p50"] == pytest.approx(3000.0)
        # Nearest-rank p95 on 5 points rounds up -> index 4 -> 5000 ms.
        assert body["fab_tap_to_timer_ms_p95"] == pytest.approx(5000.0)
