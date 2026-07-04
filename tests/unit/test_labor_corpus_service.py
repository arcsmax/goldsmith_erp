"""
Unit tests for labor_corpus_service.load_corpus (V1.3 estimator, Phase 1, Task 2).

Covers:
- Only completed/delivered orders are included (a non-completed order is excluded).
- Only BILLABLE activity time counts toward actual_hours / activity_hours.
- Per-activity hour split is correct.
- actual_hours total matches the sum of billable per-activity hours.
- Interruption minutes are subtracted from the raw duration_minutes.
- Orders with zero billable hours are excluded entirely.
- has_stone_setting reflects gemstone presence on the order (True/False).
"""

import uuid
from datetime import datetime, timedelta

import pytest

from goldsmith_erp.db.models import (
    Activity,
    Customer,
    Gemstone,
    Order,
    OrderStatusEnum,
    TimeEntry,
    User,
    UserRole,
)
from goldsmith_erp.services.labor_corpus_service import CorpusOrder, load_corpus


@pytest.fixture
async def corpus_user(db_session) -> User:
    user = User(
        email=f"corpus_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="x",
        first_name="Corpus",
        last_name="Tester",
        role=UserRole.GOLDSMITH,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.fixture
async def corpus_customer(db_session) -> Customer:
    customer = Customer(
        first_name="Erika",
        last_name="Musterfrau",
        email=f"erika_{uuid.uuid4().hex[:8]}@example.com",
        customer_type="private",
        is_active=True,
    )
    db_session.add(customer)
    await db_session.commit()
    await db_session.refresh(customer)
    return customer


@pytest.fixture
async def billable_activity(db_session) -> Activity:
    activity = Activity(
        name="Fassen (Steine)",
        category="fabrication",
        is_billable=True,
        is_custom=False,
        created_at=datetime.utcnow(),
    )
    db_session.add(activity)
    await db_session.commit()
    await db_session.refresh(activity)
    return activity


@pytest.fixture
async def billable_activity_2(db_session) -> Activity:
    activity = Activity(
        name="Polieren",
        category="fabrication",
        is_billable=True,
        is_custom=False,
        created_at=datetime.utcnow(),
    )
    db_session.add(activity)
    await db_session.commit()
    await db_session.refresh(activity)
    return activity


@pytest.fixture
async def non_billable_activity(db_session) -> Activity:
    activity = Activity(
        name="Kundenberatung",
        category="administration",
        is_billable=False,
        is_custom=False,
        created_at=datetime.utcnow(),
    )
    db_session.add(activity)
    await db_session.commit()
    await db_session.refresh(activity)
    return activity


def _make_order(customer_id: int, **overrides) -> Order:
    defaults = dict(
        title="Test Order",
        customer_id=customer_id,
        status=OrderStatusEnum.COMPLETED,
        order_type="ring",
        finish_type="high_polish",
        complexity_rating=3,
        alloy="585",
        completed_at=datetime.utcnow(),
    )
    defaults.update(overrides)
    return Order(**defaults)


def _make_entry(
    order_id: int,
    user_id: int,
    activity_id: int,
    duration_minutes: int,
    start_time: datetime | None = None,
) -> TimeEntry:
    start_time = start_time or (datetime.utcnow() - timedelta(minutes=duration_minutes))
    return TimeEntry(
        id=str(uuid.uuid4()),
        order_id=order_id,
        user_id=user_id,
        activity_id=activity_id,
        start_time=start_time,
        end_time=start_time + timedelta(minutes=duration_minutes),
        duration_minutes=duration_minutes,
    )


@pytest.mark.asyncio
class TestLoadCorpus:
    async def test_excludes_non_completed_orders(
        self, db_session, corpus_customer, corpus_user, billable_activity
    ):
        completed = _make_order(corpus_customer.id)
        in_progress = _make_order(
            corpus_customer.id,
            status=OrderStatusEnum.IN_PROGRESS,
            completed_at=None,
        )
        db_session.add_all([completed, in_progress])
        await db_session.commit()
        await db_session.refresh(completed)
        await db_session.refresh(in_progress)

        db_session.add_all(
            [
                _make_entry(completed.id, corpus_user.id, billable_activity.id, 60),
                _make_entry(in_progress.id, corpus_user.id, billable_activity.id, 60),
            ]
        )
        await db_session.commit()

        corpus = await load_corpus(db_session)

        order_ids = {row.order_id for row in corpus}
        assert completed.id in order_ids
        assert in_progress.id not in order_ids
        assert len(corpus) == 1

    async def test_only_billable_hours_counted(
        self,
        db_session,
        corpus_customer,
        corpus_user,
        billable_activity,
        non_billable_activity,
    ):
        order = _make_order(corpus_customer.id)
        db_session.add(order)
        await db_session.commit()
        await db_session.refresh(order)

        db_session.add_all(
            [
                _make_entry(order.id, corpus_user.id, billable_activity.id, 90),
                _make_entry(order.id, corpus_user.id, non_billable_activity.id, 45),
            ]
        )
        await db_session.commit()

        corpus = await load_corpus(db_session)

        assert len(corpus) == 1
        row = corpus[0]
        assert row.order_id == order.id
        # Only the 90 billable minutes count -> 1.5h; the 45 non-billable
        # minutes must not appear anywhere.
        assert row.actual_hours == pytest.approx(1.5)
        assert non_billable_activity.id not in row.activity_hours

    async def test_per_activity_split_and_total(
        self,
        db_session,
        corpus_customer,
        corpus_user,
        billable_activity,
        billable_activity_2,
    ):
        order = _make_order(corpus_customer.id)
        db_session.add(order)
        await db_session.commit()
        await db_session.refresh(order)

        db_session.add_all(
            [
                _make_entry(order.id, corpus_user.id, billable_activity.id, 60),
                _make_entry(order.id, corpus_user.id, billable_activity_2.id, 30),
            ]
        )
        await db_session.commit()

        corpus = await load_corpus(db_session)

        assert len(corpus) == 1
        row = corpus[0]
        assert row.activity_hours == {
            billable_activity.id: pytest.approx(1.0),
            billable_activity_2.id: pytest.approx(0.5),
        }
        assert row.actual_hours == pytest.approx(1.5)

    async def test_interruption_minutes_subtracted(
        self, db_session, corpus_customer, corpus_user, billable_activity
    ):
        order = _make_order(corpus_customer.id)
        db_session.add(order)
        await db_session.commit()
        await db_session.refresh(order)

        entry = _make_entry(order.id, corpus_user.id, billable_activity.id, 120)
        db_session.add(entry)
        await db_session.commit()
        await db_session.refresh(entry)

        from goldsmith_erp.db.models import Interruption

        db_session.add(
            Interruption(
                time_entry_id=entry.id, reason="material_fetch", duration_minutes=20
            )
        )
        await db_session.commit()

        corpus = await load_corpus(db_session)

        assert len(corpus) == 1
        row = corpus[0]
        # 120 raw minutes - 20 interruption minutes = 100 net minutes = 1.667h,
        # rounded to 2 decimals by load_corpus.
        assert row.actual_hours == pytest.approx(round(100 / 60, 2))

    async def test_excludes_zero_billable_hours_order(
        self, db_session, corpus_customer, corpus_user, non_billable_activity
    ):
        order = _make_order(corpus_customer.id)
        db_session.add(order)
        await db_session.commit()
        await db_session.refresh(order)

        db_session.add(
            _make_entry(order.id, corpus_user.id, non_billable_activity.id, 60)
        )
        await db_session.commit()

        corpus = await load_corpus(db_session)

        assert order.id not in {row.order_id for row in corpus}

    async def test_has_stone_setting_true_with_gemstone(
        self, db_session, corpus_customer, corpus_user, billable_activity
    ):
        order = _make_order(corpus_customer.id)
        db_session.add(order)
        await db_session.commit()
        await db_session.refresh(order)

        db_session.add(_make_entry(order.id, corpus_user.id, billable_activity.id, 60))
        db_session.add(
            Gemstone(
                order_id=order.id, type="diamond", carat=0.5, cost=200.0, quantity=1
            )
        )
        await db_session.commit()

        corpus = await load_corpus(db_session)

        row = next(r for r in corpus if r.order_id == order.id)
        assert row.has_stone_setting is True

    async def test_has_stone_setting_false_without_gemstone(
        self, db_session, corpus_customer, corpus_user, billable_activity
    ):
        order = _make_order(corpus_customer.id)
        db_session.add(order)
        await db_session.commit()
        await db_session.refresh(order)

        db_session.add(_make_entry(order.id, corpus_user.id, billable_activity.id, 60))
        await db_session.commit()

        corpus = await load_corpus(db_session)

        row = next(r for r in corpus if r.order_id == order.id)
        assert row.has_stone_setting is False

    async def test_order_fields_mapped_correctly(
        self, db_session, corpus_customer, corpus_user, billable_activity
    ):
        order = _make_order(
            corpus_customer.id,
            order_type="chain",
            finish_type="matte",
            complexity_rating=4,
            alloy="750",
        )
        db_session.add(order)
        await db_session.commit()
        await db_session.refresh(order)

        db_session.add(_make_entry(order.id, corpus_user.id, billable_activity.id, 60))
        await db_session.commit()

        corpus = await load_corpus(db_session)
        row = next(r for r in corpus if r.order_id == order.id)

        assert isinstance(row, CorpusOrder)
        assert row.order_type == "chain"
        assert row.finish_type == "matte"
        assert row.complexity_rating == 4
        assert row.alloy == "750"

    async def test_excludes_orders_missing_order_type(
        self, db_session, corpus_customer, corpus_user, billable_activity
    ):
        order = _make_order(corpus_customer.id, order_type=None)
        db_session.add(order)
        await db_session.commit()
        await db_session.refresh(order)

        db_session.add(_make_entry(order.id, corpus_user.id, billable_activity.id, 60))
        await db_session.commit()

        corpus = await load_corpus(db_session)

        assert order.id not in {row.order_id for row in corpus}

    async def test_full_three_completed_orders_scenario(
        self,
        db_session,
        corpus_customer,
        corpus_user,
        billable_activity,
        billable_activity_2,
        non_billable_activity,
    ):
        """Seed 3 synthetic completed orders + 1 non-completed, per the plan's
        TDD scenario, and assert the corpus reflects exactly the completed,
        billable-hours-bearing orders."""
        order_a = _make_order(corpus_customer.id, order_type="ring")
        order_b = _make_order(
            corpus_customer.id, order_type="chain", status=OrderStatusEnum.DELIVERED
        )
        order_c_zero_billable = _make_order(corpus_customer.id, order_type="pendant")
        order_d_not_completed = _make_order(
            corpus_customer.id,
            order_type="bracelet",
            status=OrderStatusEnum.DRAFT,
            completed_at=None,
        )
        db_session.add_all(
            [order_a, order_b, order_c_zero_billable, order_d_not_completed]
        )
        await db_session.commit()
        for o in (order_a, order_b, order_c_zero_billable, order_d_not_completed):
            await db_session.refresh(o)

        db_session.add_all(
            [
                _make_entry(order_a.id, corpus_user.id, billable_activity.id, 60),
                _make_entry(order_a.id, corpus_user.id, non_billable_activity.id, 15),
                _make_entry(order_b.id, corpus_user.id, billable_activity_2.id, 45),
                _make_entry(
                    order_c_zero_billable.id,
                    corpus_user.id,
                    non_billable_activity.id,
                    30,
                ),
                _make_entry(
                    order_d_not_completed.id, corpus_user.id, billable_activity.id, 999
                ),
            ]
        )
        await db_session.commit()

        corpus = await load_corpus(db_session)
        order_ids = {row.order_id for row in corpus}

        assert order_ids == {order_a.id, order_b.id}
        assert order_c_zero_billable.id not in order_ids
        assert order_d_not_completed.id not in order_ids

        row_a = next(r for r in corpus if r.order_id == order_a.id)
        assert row_a.actual_hours == pytest.approx(1.0)
