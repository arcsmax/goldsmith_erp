"""Unit tests for TimeTrackingService.get_summary aggregation."""

import pytest
from datetime import datetime, timedelta

from goldsmith_erp.db.models import Activity, TimeEntry as TimeEntryModel
from goldsmith_erp.services.time_tracking_service import TimeTrackingService


async def _activity(db, name, category, is_billable):
    a = Activity(
        name=name,
        category=category,
        icon="🔨",
        color="#FF6B6B",
        usage_count=0,
        is_custom=False,
        is_billable=is_billable,
    )
    db.add(a)
    await db.flush()
    return a


async def _entry(db, *, user_id, order_id, activity_id, start, minutes):
    e = TimeEntryModel(
        order_id=order_id,
        user_id=user_id,
        activity_id=activity_id,
        start_time=start,
        end_time=start + timedelta(minutes=minutes),
        duration_minutes=minutes,
    )
    db.add(e)
    await db.flush()
    return e


@pytest.mark.asyncio
class TestGetSummary:
    async def test_empty_window_returns_zeros(self, db_session, sample_user):
        now = datetime(2026, 5, 20, 9, 0, 0)
        result = await TimeTrackingService.get_summary(
            db_session, user_id=sample_user.id, start=now, end=now + timedelta(days=7)
        )
        assert result.total_hours == 0
        assert result.billable_hours == 0
        assert result.entries_count == 0
        assert result.average_session_minutes == 0
        assert result.most_used_activity is None
        assert result.comparison_previous_period is None

    async def test_billable_excludes_non_billable_activity(
        self, db_session, sample_user, sample_order
    ):
        start = datetime(2026, 5, 12, 9, 0, 0)
        end = start + timedelta(days=7)
        bill = await _activity(db_session, "Polieren", "fabrication", True)
        nonbill = await _activity(db_session, "Pause", "waiting", False)
        await _entry(
            db_session,
            user_id=sample_user.id,
            order_id=sample_order.id,
            activity_id=bill.id,
            start=start + timedelta(hours=1),
            minutes=120,
        )
        await _entry(
            db_session,
            user_id=sample_user.id,
            order_id=sample_order.id,
            activity_id=nonbill.id,
            start=start + timedelta(hours=4),
            minutes=60,
        )
        result = await TimeTrackingService.get_summary(
            db_session, user_id=sample_user.id, start=start, end=end
        )
        assert result.total_hours == 3.0  # 120 + 60 min
        assert result.billable_hours == 2.0  # only the fabrication 120 min
        assert result.entries_count == 2
        assert result.average_session_minutes == 90.0

    async def test_most_used_activity_is_by_total_time(
        self, db_session, sample_user, sample_order
    ):
        start = datetime(2026, 5, 12, 9, 0, 0)
        end = start + timedelta(days=7)
        a_long = await _activity(db_session, "Fassen", "fabrication", True)
        a_freq = await _activity(db_session, "Löten", "fabrication", True)
        # a_freq appears more often but a_long has more total minutes
        await _entry(
            db_session,
            user_id=sample_user.id,
            order_id=sample_order.id,
            activity_id=a_long.id,
            start=start + timedelta(hours=1),
            minutes=200,
        )
        for h in (3, 5, 7):
            await _entry(
                db_session,
                user_id=sample_user.id,
                order_id=sample_order.id,
                activity_id=a_freq.id,
                start=start + timedelta(hours=h),
                minutes=30,
            )
        result = await TimeTrackingService.get_summary(
            db_session, user_id=sample_user.id, start=start, end=end
        )
        assert result.most_used_activity == "Fassen"

    async def test_comparison_percentage_vs_prior_window(
        self, db_session, sample_user, sample_order
    ):
        start = datetime(2026, 5, 12, 9, 0, 0)  # window length 7 days
        end = start + timedelta(days=7)
        act = await _activity(db_session, "Polieren", "fabrication", True)
        # prior window: 10 hours (600 min)
        await _entry(
            db_session,
            user_id=sample_user.id,
            order_id=sample_order.id,
            activity_id=act.id,
            start=start - timedelta(days=3),
            minutes=600,
        )
        # current window: 12 hours (720 min) -> +20%
        await _entry(
            db_session,
            user_id=sample_user.id,
            order_id=sample_order.id,
            activity_id=act.id,
            start=start + timedelta(days=1),
            minutes=720,
        )
        result = await TimeTrackingService.get_summary(
            db_session, user_id=sample_user.id, start=start, end=end
        )
        assert result.comparison_previous_period == 20.0

    async def test_running_entries_excluded(
        self, db_session, sample_user, sample_order
    ):
        start = datetime(2026, 5, 12, 9, 0, 0)
        end = start + timedelta(days=7)
        act = await _activity(db_session, "Polieren", "fabrication", True)
        running = TimeEntryModel(
            order_id=sample_order.id,
            user_id=sample_user.id,
            activity_id=act.id,
            start_time=start + timedelta(hours=1),
            end_time=None,
            duration_minutes=None,
        )
        db_session.add(running)
        await db_session.flush()
        result = await TimeTrackingService.get_summary(
            db_session, user_id=sample_user.id, start=start, end=end
        )
        assert result.entries_count == 0
        assert result.total_hours == 0
