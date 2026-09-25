"""W2-14 (BE-19): interruptions reduce time; actual_hours is recomputed.

Acceptance (MASTER-FIX-PLAN W2-14): a 3 h entry with a 45 min interruption
counts 2.25 h; rework after completion updates ``actual_hours``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from goldsmith_erp.db.models import Interruption, Order, OrderStatusEnum, TimeEntry
from goldsmith_erp.models.time_entry import TimeEntryStop, TimeEntryUpdate
from goldsmith_erp.services.ml_data_service import MLDataService
from goldsmith_erp.services.time_tracking_service import (
    TimeTrackingService,
    interruption_minutes,
)

T0 = datetime(2026, 9, 25, 8, 0, 0)


def _intr(timestamp, resumed_at=None, duration=0):
    return SimpleNamespace(
        timestamp=timestamp, resumed_at=resumed_at, duration_minutes=duration
    )


class TestInterruptionMinutes:
    def test_resumed_interruption_counts_its_measured_span(self):
        intr = _intr(T0 + timedelta(hours=1), T0 + timedelta(hours=1, minutes=45))
        assert interruption_minutes(intr, T0, T0 + timedelta(hours=3)) == 45

    def test_span_is_clamped_to_the_entry_window(self):
        intr = _intr(T0 - timedelta(minutes=10), T0 + timedelta(hours=4))
        assert interruption_minutes(intr, T0, T0 + timedelta(hours=3)) == 180

    def test_legacy_interruption_without_resume_uses_its_duration(self):
        intr = _intr(T0 + timedelta(hours=1), None, 20)
        assert interruption_minutes(intr, T0, T0 + timedelta(hours=3)) == 20

    def test_open_marker_on_a_stopped_entry_runs_until_the_end(self):
        intr = _intr(T0 + timedelta(hours=2, minutes=30), None, 0)
        assert interruption_minutes(intr, T0, T0 + timedelta(hours=3)) == 30


async def _running_entry(db, order, user, activity, start=T0) -> TimeEntry:
    entry = TimeEntry(
        id=str(uuid.uuid4()),
        order_id=order.id,
        user_id=user.id,
        activity_id=activity.id,
        start_time=start,
        origin="scan",
        extra_metadata={},
    )
    db.add(entry)
    await db.commit()
    return entry


async def _open_interruption(db, entry, at) -> Interruption:
    intr = Interruption(
        time_entry_id=entry.id, reason="kundenanruf", duration_minutes=0, timestamp=at
    )
    db.add(intr)
    await db.commit()
    return intr


@pytest.mark.asyncio
class TestServiceArithmetic:
    async def test_resume_closes_the_open_interruption_with_its_duration(
        self, db_session, sample_order, sample_user, sample_activity
    ):
        entry = await _running_entry(
            db_session, sample_order, sample_user, sample_activity
        )
        await _open_interruption(db_session, entry, T0 + timedelta(hours=1))

        closed = await TimeTrackingService.resume_interruptions(
            db_session, entry.id, sample_user, at=T0 + timedelta(hours=1, minutes=45)
        )

        assert closed == 1
        intr = (
            await db_session.execute(
                select(Interruption).where(Interruption.time_entry_id == entry.id)
            )
        ).scalar_one()
        assert intr.resumed_at == T0 + timedelta(hours=1, minutes=45)
        assert intr.duration_minutes == 45

    async def test_stop_closes_a_still_open_interruption_at_the_end_time(
        self, db_session, sample_order, sample_user, sample_activity
    ):
        entry = await _running_entry(
            db_session, sample_order, sample_user, sample_activity
        )
        await _open_interruption(db_session, entry, T0 + timedelta(hours=2, minutes=30))

        await TimeTrackingService.stop_time_entry(
            db_session, entry.id, TimeEntryStop(), end_time=T0 + timedelta(hours=3)
        )

        intr = (
            await db_session.execute(
                select(Interruption).where(Interruption.time_entry_id == entry.id)
            )
        ).scalar_one()
        assert intr.duration_minutes == 30
        assert intr.resumed_at == T0 + timedelta(hours=3)

    async def test_three_hours_with_45_minutes_interruption_count_2_25_hours(
        self, db_session, sample_order, sample_user, sample_activity
    ):
        entry = await _running_entry(
            db_session, sample_order, sample_user, sample_activity
        )
        await _open_interruption(db_session, entry, T0 + timedelta(hours=1))
        await TimeTrackingService.resume_interruptions(
            db_session, entry.id, sample_user, at=T0 + timedelta(hours=1, minutes=45)
        )
        await TimeTrackingService.stop_time_entry(
            db_session, entry.id, TimeEntryStop(), end_time=T0 + timedelta(hours=3)
        )

        hours = await MLDataService.auto_calculate_actual_hours(
            db_session, sample_order.id
        )
        assert hours == pytest.approx(2.25)

        total = await TimeTrackingService.get_total_time_for_order(
            db_session, sample_order.id
        )
        assert total["total_minutes"] == 135
        assert total["gross_minutes"] == 180
        assert total["interruption_minutes"] == 45

    async def test_rework_after_completion_updates_actual_hours(
        self, db_session, sample_order, sample_user, sample_activity
    ):
        entry = await _running_entry(
            db_session, sample_order, sample_user, sample_activity
        )
        await TimeTrackingService.stop_time_entry(
            db_session, entry.id, TimeEntryStop(), end_time=T0 + timedelta(hours=2)
        )
        order = await db_session.get(Order, sample_order.id)
        order.status = OrderStatusEnum.COMPLETED
        order.completed_at = T0 + timedelta(hours=2)
        await db_session.commit()
        await MLDataService.auto_calculate_actual_hours(db_session, order.id)
        await db_session.commit()
        assert order.actual_hours == pytest.approx(2.0)

        rework = await _running_entry(
            db_session,
            sample_order,
            sample_user,
            sample_activity,
            start=T0 + timedelta(days=1),
        )
        await TimeTrackingService.stop_time_entry(
            db_session,
            rework.id,
            TimeEntryStop(rework_required=True),
            end_time=T0 + timedelta(days=1, minutes=30),
        )

        await db_session.refresh(order)
        assert order.actual_hours == pytest.approx(2.5)

        # Correcting the rework entry's end recomputes again.
        await TimeTrackingService.update_time_entry(
            db_session,
            rework.id,
            TimeEntryUpdate(end_time=T0 + timedelta(days=1, hours=1)),
        )
        await db_session.refresh(order)
        assert order.actual_hours == pytest.approx(3.0)

    async def test_open_order_keeps_actual_hours_empty_until_completion(
        self, db_session, sample_order, sample_user, sample_activity
    ):
        entry = await _running_entry(
            db_session, sample_order, sample_user, sample_activity
        )
        await TimeTrackingService.stop_time_entry(
            db_session, entry.id, TimeEntryStop(), end_time=T0 + timedelta(hours=1)
        )
        order = await db_session.get(Order, sample_order.id)
        await db_session.refresh(order)
        assert order.actual_hours is None

    async def test_running_entry_interruptions_do_not_reduce_closed_time(
        self, db_session, sample_order, sample_user, sample_activity
    ):
        closed = await _running_entry(
            db_session, sample_order, sample_user, sample_activity
        )
        await TimeTrackingService.stop_time_entry(
            db_session, closed.id, TimeEntryStop(), end_time=T0 + timedelta(hours=2)
        )
        running = await _running_entry(
            db_session,
            sample_order,
            sample_user,
            sample_activity,
            start=T0 + timedelta(hours=3),
        )
        db_session.add(
            Interruption(
                time_entry_id=running.id,
                reason="pause",
                duration_minutes=30,
                timestamp=T0 + timedelta(hours=3, minutes=5),
            )
        )
        await db_session.commit()

        hours = await MLDataService.auto_calculate_actual_hours(
            db_session, sample_order.id
        )
        assert hours == pytest.approx(2.0)

    async def test_next_interruption_scan_closes_the_previous_one(
        self, db_session, sample_order, sample_user, sample_activity
    ):
        start = datetime.utcnow() - timedelta(minutes=50)
        entry = await _running_entry(
            db_session, sample_order, sample_user, sample_activity, start=start
        )
        first = await _open_interruption(
            db_session, entry, datetime.utcnow() - timedelta(minutes=10)
        )

        await TimeTrackingService.log_interruption(
            db_session, entry.id, "material_holen", sample_user
        )

        await db_session.refresh(first)
        assert first.resumed_at is not None
        assert first.duration_minutes == 10
