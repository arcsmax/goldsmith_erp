# tests/unit/test_cost_watch_service.py
"""
Unit tests for CostWatchService (V1.2 Task 3).

Covers:
- get_projected_cost rollup math: material (SUM MaterialUsage.cost_at_time),
  gemstones (SUM cost*quantity), billable-only labor minutes/cost, hourly
  rate fallback to settings.DEFAULT_HOURLY_RATE.
- Quote reference selection (latest SENT/APPROVED, fallback latest DRAFT,
  None-safe when no quote exists) and delta/over_threshold math, including
  the zero-quote-total division guard.
- check_order: creates a deduped COST_ALERT Notification for ADMIN+GOLDSMITH
  users only when over threshold; per-user dedup scoped by unread state
  (not day); never raises even when the rollup itself fails.
- safe_check: no-op on order_id=None; never raises even when check_order
  raises unexpectedly.
- Hook fire-and-forget regression: a failure inside the cost watcher must
  never break TimeTrackingService.stop_time_entry or
  MetalInventoryService.consume_material (V1.1 Task 4 fire-and-forget
  pattern).
"""
import uuid
from datetime import datetime, timedelta

import pytest

from goldsmith_erp.core.config import settings
from goldsmith_erp.db.models import (
    Activity,
    CostingMethod,
    Gemstone,
    MaterialUsage,
    MetalType,
    Notification,
    NotificationTypeEnum,
    Order,
    OrderStatusEnum,
    Quote,
    QuoteStatus,
    TimeEntry,
    User,
    UserRole,
)
from goldsmith_erp.models.metal_inventory import MaterialUsageCreate
from goldsmith_erp.models.time_entry import TimeEntryStop
from goldsmith_erp.services.cost_watch_service import CostWatchService
from goldsmith_erp.services.metal_inventory_service import MetalInventoryService
from goldsmith_erp.services.notification_service import NotificationService
from goldsmith_erp.services.time_tracking_service import TimeTrackingService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _add_material_usage(
    db, *, order_id: int, metal_purchase_id: int, cost_at_time: float
) -> MaterialUsage:
    usage = MaterialUsage(
        order_id=order_id,
        metal_purchase_id=metal_purchase_id,
        weight_used_g=10.0,
        cost_at_time=cost_at_time,
        price_per_gram_at_time=cost_at_time / 10.0,
        costing_method=CostingMethod.FIFO,
    )
    db.add(usage)
    await db.commit()
    await db.refresh(usage)
    return usage


async def _add_gemstone(
    db, *, order_id: int, cost: float, quantity: int = 1
) -> Gemstone:
    gemstone = Gemstone(
        order_id=order_id,
        type="diamond",
        cost=cost,
        quantity=quantity,
    )
    db.add(gemstone)
    await db.commit()
    await db.refresh(gemstone)
    return gemstone


async def _add_time_entry(
    db, *, order_id: int, user_id: int, activity_id: int, duration_minutes: int
) -> TimeEntry:
    start_time = datetime.utcnow() - timedelta(minutes=duration_minutes)
    entry = TimeEntry(
        id=str(uuid.uuid4()),
        order_id=order_id,
        user_id=user_id,
        activity_id=activity_id,
        start_time=start_time,
        end_time=datetime.utcnow(),
        duration_minutes=duration_minutes,
        created_at=datetime.utcnow(),
    )
    db.add(entry)
    await db.commit()
    await db.refresh(entry)
    return entry


async def _add_quote(
    db,
    *,
    order_id: int,
    customer_id: int,
    created_by_id: int,
    status: QuoteStatus,
    subtotal: float,
    created_at: datetime | None = None,
) -> Quote:
    """Create a REALISTIC quote: net subtotal + 19% VAT grossed into total.

    Regression guard: an earlier fixture set tax_amount=0 / total=subtotal,
    which masked the netto/brutto bug (service compared net costs against
    the gross total). Keeping tax_rate at the German default 19% ensures
    subtotal != total, so any accidental use of Quote.total as the net
    reference makes the threshold tests fail.
    """
    tax_rate = 19.0
    tax_amount = round(subtotal * tax_rate / 100.0, 2)
    quote = Quote(
        quote_number=f"KV-TEST-{uuid.uuid4().hex[:8]}",
        order_id=order_id,
        customer_id=customer_id,
        created_by=created_by_id,
        status=status,
        valid_until=datetime.utcnow() + timedelta(days=14),
        subtotal=subtotal,
        tax_rate=tax_rate,
        tax_amount=tax_amount,
        total=subtotal + tax_amount,
        created_at=created_at or datetime.utcnow(),
    )
    db.add(quote)
    await db.commit()
    await db.refresh(quote)
    return quote


async def _cost_alert_notifications(db, order_id: int) -> list[Notification]:
    from sqlalchemy import select

    result = await db.execute(
        select(Notification).where(
            Notification.related_order_id == order_id,
            Notification.notification_type == NotificationTypeEnum.COST_ALERT,
        )
    )
    return list(result.scalars().all())


@pytest.fixture
async def nonbillable_activity(db_session) -> Activity:
    activity = Activity(
        name="Warten",
        category="waiting",
        is_billable=False,
        is_custom=False,
        created_at=datetime.utcnow(),
    )
    db_session.add(activity)
    await db_session.commit()
    await db_session.refresh(activity)
    return activity


# ---------------------------------------------------------------------------
# get_projected_cost — rollup math
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetProjectedCostRollup:
    async def test_material_cost_sums_all_usage_rows(
        self, db_session, sample_order, sample_metal_purchase
    ):
        await _add_material_usage(
            db_session,
            order_id=sample_order.id,
            metal_purchase_id=sample_metal_purchase.id,
            cost_at_time=100.0,
        )
        await _add_material_usage(
            db_session,
            order_id=sample_order.id,
            metal_purchase_id=sample_metal_purchase.id,
            cost_at_time=50.0,
        )

        projected = await CostWatchService.get_projected_cost(
            db_session, sample_order.id
        )

        assert projected.material_cost == 150.0

    async def test_gemstone_cost_sums_cost_times_quantity(
        self, db_session, sample_order
    ):
        await _add_gemstone(
            db_session, order_id=sample_order.id, cost=200.0, quantity=2
        )
        await _add_gemstone(db_session, order_id=sample_order.id, cost=50.0, quantity=1)

        projected = await CostWatchService.get_projected_cost(
            db_session, sample_order.id
        )

        assert projected.gemstone_cost == 450.0

    async def test_labor_counts_only_billable_activities(
        self,
        db_session,
        sample_order,
        sample_user,
        sample_activity,
        nonbillable_activity,
    ):
        assert sample_activity.is_billable is True
        await _add_time_entry(
            db_session,
            order_id=sample_order.id,
            user_id=sample_user.id,
            activity_id=sample_activity.id,
            duration_minutes=120,
        )
        await _add_time_entry(
            db_session,
            order_id=sample_order.id,
            user_id=sample_user.id,
            activity_id=nonbillable_activity.id,
            duration_minutes=60,
        )

        projected = await CostWatchService.get_projected_cost(
            db_session, sample_order.id
        )

        assert projected.labor_minutes_billable == 120.0
        # sample_order.hourly_rate defaults to 75.0
        assert projected.labor_cost == pytest.approx(150.0)

    async def test_labor_excludes_running_time_entry(
        self, db_session, sample_order, sample_user, sample_activity
    ):
        running = TimeEntry(
            id=str(uuid.uuid4()),
            order_id=sample_order.id,
            user_id=sample_user.id,
            activity_id=sample_activity.id,
            start_time=datetime.utcnow() - timedelta(minutes=30),
            end_time=None,
            duration_minutes=None,
        )
        db_session.add(running)
        await db_session.commit()

        projected = await CostWatchService.get_projected_cost(
            db_session, sample_order.id
        )

        assert projected.labor_minutes_billable == 0.0
        assert projected.labor_cost == 0.0

    async def test_labor_uses_order_hourly_rate_override(
        self, db_session, sample_customer, sample_user, sample_activity
    ):
        order = Order(
            title="Custom rate order",
            customer_id=sample_customer.id,
            status=OrderStatusEnum.NEW,
            hourly_rate=100.0,
        )
        db_session.add(order)
        await db_session.commit()
        await db_session.refresh(order)

        await _add_time_entry(
            db_session,
            order_id=order.id,
            user_id=sample_user.id,
            activity_id=sample_activity.id,
            duration_minutes=60,
        )

        projected = await CostWatchService.get_projected_cost(db_session, order.id)

        assert projected.labor_cost == pytest.approx(100.0)

    async def test_labor_falls_back_to_default_hourly_rate_when_order_has_none(
        self, db_session, sample_customer, sample_user, sample_activity, monkeypatch
    ):
        from sqlalchemy import update

        monkeypatch.setattr(settings, "DEFAULT_HOURLY_RATE", 60.0)
        order = Order(
            title="No-rate order",
            customer_id=sample_customer.id,
            status=OrderStatusEnum.NEW,
        )
        db_session.add(order)
        await db_session.commit()
        await db_session.refresh(order)
        # Order.hourly_rate has a Python-side scalar default (75.0) that
        # SQLAlchemy re-applies on INSERT whenever the final pending value
        # is None — an explicit `hourly_rate=None` constructor arg does NOT
        # persist as NULL. Force NULL via a raw UPDATE to exercise the
        # genuine no-rate case (e.g. a row nulled out via migration/backfill).
        await db_session.execute(
            update(Order).where(Order.id == order.id).values(hourly_rate=None)
        )
        await db_session.commit()
        await db_session.refresh(order)
        assert order.hourly_rate is None

        await _add_time_entry(
            db_session,
            order_id=order.id,
            user_id=sample_user.id,
            activity_id=sample_activity.id,
            duration_minutes=60,
        )

        projected = await CostWatchService.get_projected_cost(db_session, order.id)

        assert projected.labor_cost == pytest.approx(60.0)

    async def test_explicit_zero_hourly_rate_is_honoured_not_defaulted(
        self, db_session, sample_customer, sample_user, sample_activity
    ):
        """An explicit 0.0 rate (e.g. warranty rework billed at zero) must
        yield zero labor cost — NOT silently fall back to the default rate
        (truthiness-vs-is-None regression)."""
        order = Order(
            title="Warranty rework order",
            customer_id=sample_customer.id,
            status=OrderStatusEnum.NEW,
            hourly_rate=0.0,
        )
        db_session.add(order)
        await db_session.commit()
        await db_session.refresh(order)
        assert order.hourly_rate == 0.0

        await _add_time_entry(
            db_session,
            order_id=order.id,
            user_id=sample_user.id,
            activity_id=sample_activity.id,
            duration_minutes=60,
        )

        projected = await CostWatchService.get_projected_cost(db_session, order.id)

        assert projected.labor_minutes_billable == 60.0
        assert projected.labor_cost == 0.0

    async def test_projected_total_is_sum_of_all_three_components(
        self,
        db_session,
        sample_order,
        sample_metal_purchase,
        sample_user,
        sample_activity,
    ):
        await _add_material_usage(
            db_session,
            order_id=sample_order.id,
            metal_purchase_id=sample_metal_purchase.id,
            cost_at_time=100.0,
        )
        await _add_gemstone(db_session, order_id=sample_order.id, cost=50.0, quantity=1)
        await _add_time_entry(
            db_session,
            order_id=sample_order.id,
            user_id=sample_user.id,
            activity_id=sample_activity.id,
            duration_minutes=60,
        )

        projected = await CostWatchService.get_projected_cost(
            db_session, sample_order.id
        )

        assert projected.projected_total == pytest.approx(
            projected.material_cost + projected.gemstone_cost + projected.labor_cost
        )
        assert projected.projected_total == pytest.approx(225.0)  # 100 + 50 + 75


# ---------------------------------------------------------------------------
# get_projected_cost — quote reference selection + deltas
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestQuoteReferenceAndDeltas:
    async def test_no_quote_returns_none_fields_and_not_over_threshold(
        self, db_session, sample_order, sample_metal_purchase
    ):
        await _add_material_usage(
            db_session,
            order_id=sample_order.id,
            metal_purchase_id=sample_metal_purchase.id,
            cost_at_time=500.0,
        )

        projected = await CostWatchService.get_projected_cost(
            db_session, sample_order.id
        )

        assert projected.quote_id is None
        assert projected.quote_total is None
        assert projected.delta_percent is None
        assert projected.delta_abs is None
        assert projected.over_threshold is False

    async def test_prefers_sent_over_draft(
        self, db_session, sample_order, sample_customer, sample_user
    ):
        await _add_quote(
            db_session,
            order_id=sample_order.id,
            customer_id=sample_customer.id,
            created_by_id=sample_user.id,
            status=QuoteStatus.DRAFT,
            subtotal=1000.0,
            created_at=datetime.utcnow() - timedelta(days=1),
        )
        sent = await _add_quote(
            db_session,
            order_id=sample_order.id,
            customer_id=sample_customer.id,
            created_by_id=sample_user.id,
            status=QuoteStatus.SENT,
            subtotal=1200.0,
        )

        projected = await CostWatchService.get_projected_cost(
            db_session, sample_order.id
        )

        assert projected.quote_id == sent.id
        assert projected.quote_total == 1200.0

    async def test_falls_back_to_latest_draft_when_no_sent_or_approved(
        self, db_session, sample_order, sample_customer, sample_user
    ):
        await _add_quote(
            db_session,
            order_id=sample_order.id,
            customer_id=sample_customer.id,
            created_by_id=sample_user.id,
            status=QuoteStatus.DRAFT,
            subtotal=900.0,
            created_at=datetime.utcnow() - timedelta(days=1),
        )
        latest_draft = await _add_quote(
            db_session,
            order_id=sample_order.id,
            customer_id=sample_customer.id,
            created_by_id=sample_user.id,
            status=QuoteStatus.DRAFT,
            subtotal=950.0,
        )

        projected = await CostWatchService.get_projected_cost(
            db_session, sample_order.id
        )

        assert projected.quote_id == latest_draft.id
        assert projected.quote_total == 950.0

    async def test_compares_against_net_subtotal_not_gross_total(
        self,
        db_session,
        sample_order,
        sample_customer,
        sample_user,
        sample_metal_purchase,
    ):
        """Netto/brutto regression (§649 Critical fix): the projected cost
        rollup is a NET figure, so the threshold must compare against
        Quote.subtotal (net), not Quote.total (gross, ×1.19).

        Quote: subtotal 1000 net → gross total 1190. Projected 1160 is 16%
        over NET (>= 15% threshold) → over_threshold MUST be True. The old
        gross-comparison code computed 1160 vs 1190 = -30 EUR delta and said
        False — a real overrun hidden behind the VAT margin.
        """
        quote = await _add_quote(
            db_session,
            order_id=sample_order.id,
            customer_id=sample_customer.id,
            created_by_id=sample_user.id,
            status=QuoteStatus.SENT,
            subtotal=1000.0,
        )
        assert quote.total == pytest.approx(1190.0)  # realistic grossed quote

        await _add_material_usage(
            db_session,
            order_id=sample_order.id,
            metal_purchase_id=sample_metal_purchase.id,
            cost_at_time=1160.0,
        )

        projected = await CostWatchService.get_projected_cost(
            db_session, sample_order.id
        )

        assert projected.quote_total == pytest.approx(1000.0)  # NET reference
        assert projected.delta_abs == pytest.approx(160.0)  # NET euros
        assert projected.delta_percent == pytest.approx(16.0)
        assert projected.over_threshold is True

    async def test_delta_percent_crossing_triggers_over_threshold(
        self,
        db_session,
        sample_order,
        sample_customer,
        sample_user,
        sample_metal_purchase,
    ):
        await _add_quote(
            db_session,
            order_id=sample_order.id,
            customer_id=sample_customer.id,
            created_by_id=sample_user.id,
            status=QuoteStatus.SENT,
            subtotal=100.0,
        )
        # Actual cost 120 vs quote 100 -> +20% (>=15% threshold), +20 EUR (<150 abs)
        await _add_material_usage(
            db_session,
            order_id=sample_order.id,
            metal_purchase_id=sample_metal_purchase.id,
            cost_at_time=120.0,
        )

        projected = await CostWatchService.get_projected_cost(
            db_session, sample_order.id
        )

        assert projected.delta_abs == pytest.approx(20.0)
        assert projected.delta_percent == pytest.approx(20.0)
        assert projected.over_threshold is True

    async def test_delta_abs_crossing_triggers_over_threshold_even_under_percent(
        self,
        db_session,
        sample_order,
        sample_customer,
        sample_user,
        sample_metal_purchase,
    ):
        await _add_quote(
            db_session,
            order_id=sample_order.id,
            customer_id=sample_customer.id,
            created_by_id=sample_user.id,
            status=QuoteStatus.SENT,
            subtotal=2000.0,
        )
        # Actual cost 2160 vs quote 2000 -> +8% (<15%), +160 EUR (>=150 abs)
        await _add_material_usage(
            db_session,
            order_id=sample_order.id,
            metal_purchase_id=sample_metal_purchase.id,
            cost_at_time=2160.0,
        )

        projected = await CostWatchService.get_projected_cost(
            db_session, sample_order.id
        )

        assert projected.delta_percent == pytest.approx(8.0)
        assert projected.delta_abs == pytest.approx(160.0)
        assert projected.over_threshold is True

    async def test_neither_threshold_crossed_stays_under(
        self,
        db_session,
        sample_order,
        sample_customer,
        sample_user,
        sample_metal_purchase,
    ):
        await _add_quote(
            db_session,
            order_id=sample_order.id,
            customer_id=sample_customer.id,
            created_by_id=sample_user.id,
            status=QuoteStatus.SENT,
            subtotal=2000.0,
        )
        # +100 EUR (<150), +5% (<15%)
        await _add_material_usage(
            db_session,
            order_id=sample_order.id,
            metal_purchase_id=sample_metal_purchase.id,
            cost_at_time=2100.0,
        )

        projected = await CostWatchService.get_projected_cost(
            db_session, sample_order.id
        )

        assert projected.over_threshold is False

    async def test_zero_quote_total_avoids_division_by_zero(
        self,
        db_session,
        sample_order,
        sample_customer,
        sample_user,
        sample_metal_purchase,
    ):
        await _add_quote(
            db_session,
            order_id=sample_order.id,
            customer_id=sample_customer.id,
            created_by_id=sample_user.id,
            status=QuoteStatus.SENT,
            subtotal=0.0,
        )
        await _add_material_usage(
            db_session,
            order_id=sample_order.id,
            metal_purchase_id=sample_metal_purchase.id,
            cost_at_time=200.0,
        )

        projected = await CostWatchService.get_projected_cost(
            db_session, sample_order.id
        )

        assert projected.delta_percent is None
        assert projected.delta_abs == pytest.approx(200.0)
        # Percent undefined but abs (200 >= 150) still trips the alert.
        assert projected.over_threshold is True


# ---------------------------------------------------------------------------
# check_order — alerting + dedup
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCheckOrderAlerting:
    async def _setup_over_threshold(
        self,
        db_session,
        sample_order,
        sample_customer,
        sample_user,
        sample_metal_purchase,
    ):
        await _add_quote(
            db_session,
            order_id=sample_order.id,
            customer_id=sample_customer.id,
            created_by_id=sample_user.id,
            status=QuoteStatus.SENT,
            subtotal=100.0,
        )
        await _add_material_usage(
            db_session,
            order_id=sample_order.id,
            metal_purchase_id=sample_metal_purchase.id,
            cost_at_time=200.0,
        )

    async def test_creates_notification_for_admin_and_goldsmith_when_over_threshold(
        self,
        db_session,
        sample_order,
        sample_customer,
        sample_user,
        admin_user,
        sample_metal_purchase,
    ):
        await self._setup_over_threshold(
            db_session,
            sample_order,
            sample_customer,
            sample_user,
            sample_metal_purchase,
        )

        result = await CostWatchService.check_order(db_session, sample_order.id)

        assert result is not None
        assert result.over_threshold is True
        notifications = await _cost_alert_notifications(db_session, sample_order.id)
        assert len(notifications) == 2
        recipient_ids = {n.user_id for n in notifications}
        assert recipient_ids == {sample_user.id, admin_user.id}
        assert all(n.is_read is False for n in notifications)

    async def test_no_alert_when_not_over_threshold(
        self, db_session, sample_order, sample_customer, sample_user, admin_user
    ):
        await _add_quote(
            db_session,
            order_id=sample_order.id,
            customer_id=sample_customer.id,
            created_by_id=sample_user.id,
            status=QuoteStatus.SENT,
            subtotal=10_000.0,
        )

        result = await CostWatchService.check_order(db_session, sample_order.id)

        assert result is not None
        assert result.over_threshold is False
        notifications = await _cost_alert_notifications(db_session, sample_order.id)
        assert notifications == []

    async def test_no_alert_when_no_quote(
        self, db_session, sample_order, sample_metal_purchase, sample_user, admin_user
    ):
        await _add_material_usage(
            db_session,
            order_id=sample_order.id,
            metal_purchase_id=sample_metal_purchase.id,
            cost_at_time=10_000.0,
        )

        result = await CostWatchService.check_order(db_session, sample_order.id)

        assert result is not None
        assert result.over_threshold is False
        notifications = await _cost_alert_notifications(db_session, sample_order.id)
        assert notifications == []

    async def test_never_raises_when_rollup_fails(
        self, db_session, sample_order, monkeypatch
    ):
        async def _boom(*args, **kwargs):
            raise RuntimeError("simulated rollup failure")

        monkeypatch.setattr(CostWatchService, "get_projected_cost", _boom)

        result = await CostWatchService.check_order(db_session, sample_order.id)

        assert result is None


@pytest.mark.asyncio
class TestCheckOrderDedup:
    async def _setup_over_threshold(
        self,
        db_session,
        sample_order,
        sample_customer,
        sample_user,
        sample_metal_purchase,
    ):
        await _add_quote(
            db_session,
            order_id=sample_order.id,
            customer_id=sample_customer.id,
            created_by_id=sample_user.id,
            status=QuoteStatus.SENT,
            subtotal=100.0,
        )
        await _add_material_usage(
            db_session,
            order_id=sample_order.id,
            metal_purchase_id=sample_metal_purchase.id,
            cost_at_time=200.0,
        )

    async def test_second_check_creates_no_duplicate_while_unread(
        self,
        db_session,
        sample_order,
        sample_customer,
        sample_user,
        admin_user,
        sample_metal_purchase,
    ):
        await self._setup_over_threshold(
            db_session,
            sample_order,
            sample_customer,
            sample_user,
            sample_metal_purchase,
        )

        await CostWatchService.check_order(db_session, sample_order.id)
        await CostWatchService.check_order(db_session, sample_order.id)

        notifications = await _cost_alert_notifications(db_session, sample_order.id)
        assert len(notifications) == 2  # still just one per user

    async def test_re_alerts_after_mark_read(
        self,
        db_session,
        sample_order,
        sample_customer,
        sample_user,
        admin_user,
        sample_metal_purchase,
    ):
        await self._setup_over_threshold(
            db_session,
            sample_order,
            sample_customer,
            sample_user,
            sample_metal_purchase,
        )

        await CostWatchService.check_order(db_session, sample_order.id)
        await NotificationService.mark_all_read(db_session, sample_user.id)
        await NotificationService.mark_all_read(db_session, admin_user.id)

        await CostWatchService.check_order(db_session, sample_order.id)

        notifications = await _cost_alert_notifications(db_session, sample_order.id)
        assert len(notifications) == 4  # 2 original (read) + 2 new (unread)
        unread = [n for n in notifications if not n.is_read]
        assert len(unread) == 2

    async def test_dedup_is_scoped_per_user(
        self,
        db_session,
        sample_order,
        sample_customer,
        sample_user,
        admin_user,
        sample_metal_purchase,
    ):
        """Marking only ONE user's alert read must re-alert only that user —
        the still-unread admin copy must keep blocking a duplicate for admin.
        """
        await self._setup_over_threshold(
            db_session,
            sample_order,
            sample_customer,
            sample_user,
            sample_metal_purchase,
        )

        await CostWatchService.check_order(db_session, sample_order.id)
        await NotificationService.mark_all_read(db_session, sample_user.id)
        # admin_user's copy stays unread.

        await CostWatchService.check_order(db_session, sample_order.id)

        notifications = await _cost_alert_notifications(db_session, sample_order.id)
        assert len(notifications) == 3  # 2 original + 1 new (sample_user only)
        admin_notifications = [n for n in notifications if n.user_id == admin_user.id]
        assert len(admin_notifications) == 1  # never duplicated — still unread
        goldsmith_notifications = [
            n for n in notifications if n.user_id == sample_user.id
        ]
        assert len(goldsmith_notifications) == 2  # original (read) + new (unread)


# ---------------------------------------------------------------------------
# safe_check — guarded fire-and-forget contract
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSafeCheck:
    async def test_skips_when_order_id_is_none(self, db_session, monkeypatch):
        calls = []

        async def _spy(db, order_id):
            calls.append(order_id)

        monkeypatch.setattr(CostWatchService, "check_order", _spy)

        await CostWatchService.safe_check(db_session, None)

        assert calls == []

    async def test_never_raises_when_check_order_raises(self, db_session, monkeypatch):
        async def _boom(db, order_id):
            raise RuntimeError("simulated check_order failure")

        monkeypatch.setattr(CostWatchService, "check_order", _boom)

        # Must not raise.
        await CostWatchService.safe_check(db_session, 1)


# ---------------------------------------------------------------------------
# Hook fire-and-forget regression — must never break the caller
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestHookFireAndForget:
    async def test_stop_time_entry_survives_cost_watch_failure(
        self, db_session, active_time_entry, monkeypatch
    ):
        async def _boom(*args, **kwargs):
            raise RuntimeError("simulated cost watch failure")

        monkeypatch.setattr(CostWatchService, "get_projected_cost", _boom)

        stopped = await TimeTrackingService.stop_time_entry(
            db_session, active_time_entry.id, TimeEntryStop()
        )

        assert stopped is not None
        assert stopped.end_time is not None

    async def test_consume_material_survives_cost_watch_failure(
        self, db_session, sample_order, sample_metal_purchase, monkeypatch
    ):
        async def _boom(*args, **kwargs):
            raise RuntimeError("simulated cost watch failure")

        monkeypatch.setattr(CostWatchService, "get_projected_cost", _boom)

        usage_data = MaterialUsageCreate(
            order_id=sample_order.id,
            weight_used_g=5.0,
            costing_method=CostingMethod.FIFO,
        )

        usage = await MetalInventoryService.consume_material(
            db_session, usage_data, MetalType.GOLD_18K
        )

        assert usage is not None
        assert usage.order_id == sample_order.id
