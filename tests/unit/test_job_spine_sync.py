"""ARCH phase 5: the ``jobs`` spine follows every order / repair write.

Covers the sync rules of docs/architecture/ADR-2026-09-25-jobs-spine.md:
creation, every allowed status transition of both workflows, field edits,
soft delete, the lazy upsert for rows without a job, and the per-year
numbering from ``number_sequences``.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import select

from goldsmith_erp.db.models import (
    Job,
    JobKind,
    JobStatus,
    Order,
    OrderEvent,
    OrderStatusEnum,
    RepairItemType,
    RepairJob,
    RepairJobStatus,
)
from goldsmith_erp.models.order import OrderCreate, OrderUpdate
from goldsmith_erp.models.repair import (
    RepairCompleteInput,
    RepairDiagnoseInput,
    RepairJobCreate,
    RepairStatusUpdate,
)
from goldsmith_erp.services import order_workflow, repair_workflow
from goldsmith_erp.services.job_service import (
    ORDER_STATUS_TO_JOB,
    REPAIR_STATUS_TO_JOB,
    JobService,
)
from goldsmith_erp.services.number_sequence_service import berlin_year
from goldsmith_erp.services.order_service import OrderService
from goldsmith_erp.services.repair_service import RepairService

pytestmark = pytest.mark.asyncio

ORDER_PAIRS = [
    (current, target)
    for current, targets in order_workflow.ALLOWED_TRANSITIONS.items()
    for target in targets
]
REPAIR_PAIRS = [
    (current, target)
    for current in RepairJobStatus
    for target in RepairJobStatus
    if current is not target and repair_workflow.is_transition_allowed(current, target)
]


async def _job(db, job_id) -> Job:
    stmt = select(Job).where(Job.id == job_id).execution_options(populate_existing=True)
    return (await db.execute(stmt)).scalar_one()


async def _events(db, **where) -> list[OrderEvent]:
    stmt = select(OrderEvent).order_by(OrderEvent.id)
    for column, value in where.items():
        stmt = stmt.where(getattr(OrderEvent, column) == value)
    return list((await db.execute(stmt)).scalars().all())


async def _plain_order(db, customer_id, status=OrderStatusEnum.DRAFT) -> Order:
    order = Order(title="Siegelring", customer_id=customer_id, status=status)
    db.add(order)
    await db.commit()
    await db.refresh(order)
    return order


async def _plain_repair(db, customer_id, status=RepairJobStatus.RECEIVED) -> RepairJob:
    repair = RepairJob(
        repair_number=f"REP-2026-{9000 + (customer_id or 0):04d}",
        bag_number="TU-2026-9000",
        customer_id=customer_id,
        item_description="Kette löten",
        item_type=RepairItemType.CHAIN,
        status=status,
    )
    db.add(repair)
    await db.commit()
    await db.refresh(repair)
    return repair


# --------------------------------------------------------------------------- #
# Orders
# --------------------------------------------------------------------------- #


async def test_create_order_creates_job_and_links_the_creation_event(
    db_session, sample_customer, sample_user
):
    order = await OrderService.create_order(
        db_session,
        OrderCreate(
            title="Ehering", description="Gelbgold", customer_id=sample_customer.id
        ),
        user_id=sample_user.id,
    )

    assert order.job_id is not None
    job = await _job(db_session, order.job_id)
    assert job.kind == JobKind.ORDER.value
    assert job.number == f"AU-{berlin_year()}-0001"
    assert job.status == JobStatus.DRAFT.value
    assert job.kind_status == "draft"
    assert job.customer_id == sample_customer.id
    assert job.title == "Ehering"
    (event,) = await _events(db_session, order_id=order.id)
    assert event.job_id == job.id


async def test_order_numbers_increment_per_year(db_session, sample_customer):
    first = await OrderService.create_order(
        db_session,
        OrderCreate(title="A", description="x", customer_id=sample_customer.id),
    )
    second = await OrderService.create_order(
        db_session,
        OrderCreate(title="B", description="x", customer_id=sample_customer.id),
    )
    numbers = [(await _job(db_session, o.job_id)).number for o in (first, second)]
    year = berlin_year()
    assert numbers == [f"AU-{year}-0001", f"AU-{year}-0002"]


@pytest.mark.parametrize(
    "current,target", ORDER_PAIRS, ids=[f"{c.value}->{t.value}" for c, t in ORDER_PAIRS]
)
async def test_every_order_transition_syncs_the_job(
    db_session, sample_customer, current, target
):
    order = await _plain_order(db_session, sample_customer.id, status=current)
    reason = "Stein fehlt" if target in order_workflow.REASON_REQUIRED else None
    resume = (
        date.today() + timedelta(days=3) if target is OrderStatusEnum.ON_HOLD else None
    )

    event = await order_workflow.transition(
        db_session, order, target, reason=reason, resume_date=resume
    )
    await db_session.commit()

    assert event is not None and event.job_id == order.job_id
    job = await _job(db_session, order.job_id)
    assert job.status == ORDER_STATUS_TO_JOB[target].value
    assert job.kind_status == target.value
    if target is OrderStatusEnum.ON_HOLD:
        assert job.on_hold_since is not None
        assert job.resume_date == resume
    else:
        assert job.on_hold_since is None
        assert job.resume_date is None


async def test_order_field_edits_and_delete_reach_the_job(db_session, sample_customer):
    order = await OrderService.create_order(
        db_session,
        OrderCreate(title="Alt", description="x", customer_id=sample_customer.id),
    )
    deadline = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(days=9)

    await OrderService.update_order(
        db_session, order.id, OrderUpdate(title="Neu", deadline=deadline)
    )
    job = await _job(db_session, order.job_id)
    assert job.title == "Neu"
    assert job.deadline == deadline

    await OrderService.delete_order(db_session, order.id)
    job = await _job(db_session, order.job_id)
    assert job.is_deleted is True


async def test_order_without_job_gets_one_on_its_next_transition(
    db_session, sample_customer
):
    order = await _plain_order(db_session, sample_customer.id)
    assert order.job_id is None

    await order_workflow.transition(db_session, order, OrderStatusEnum.CONFIRMED)
    await db_session.commit()

    job = await _job(db_session, order.job_id)
    assert job.status == JobStatus.CONFIRMED.value


async def test_backfill_missing_and_count_missing(db_session, sample_customer):
    await _plain_order(db_session, sample_customer.id)
    await _plain_repair(db_session, sample_customer.id)
    assert await JobService.count_missing(db_session) == {"orders": 1, "repairs": 1}

    created = await JobService.backfill_missing(db_session)
    await db_session.commit()

    assert created == {"orders": 1, "repairs": 1}
    assert await JobService.count_missing(db_session) == {"orders": 0, "repairs": 0}
    assert await JobService.backfill_missing(db_session) == {"orders": 0, "repairs": 0}


# --------------------------------------------------------------------------- #
# Repairs
# --------------------------------------------------------------------------- #


async def _intake(db, customer_id, user_id) -> RepairJob:
    return await RepairService.create_repair(
        db,
        RepairJobCreate(
            customer_id=customer_id,
            item_description="Ring weiten",
            item_type=RepairItemType.RING,
        ),
        user_id,
    )


async def test_create_repair_creates_job_with_its_number(
    db_session, sample_customer, sample_user
):
    repair = await _intake(db_session, sample_customer.id, sample_user.id)

    job = await _job(db_session, repair.job_id)
    assert job.kind == JobKind.REPAIR.value
    assert job.number == repair.repair_number
    assert repair.repair_number == f"REP-{berlin_year()}-0001"
    assert repair.bag_number == f"TU-{berlin_year()}-0001"
    assert job.status == JobStatus.INTAKE.value
    (event,) = await _events(db_session, repair_job_id=repair.id)
    assert event.order_id is None
    assert event.job_id == job.id
    assert event.from_status is None and event.to_status == "received"


async def test_repair_numbers_continue_after_existing_numbers(
    db_session, sample_customer, sample_user
):
    year = berlin_year()
    legacy = await _plain_repair(db_session, sample_customer.id)
    legacy.repair_number = f"REP-{year}-0041"
    await db_session.commit()

    repair = await _intake(db_session, sample_customer.id, sample_user.id)

    assert repair.repair_number == f"REP-{year}-0042"


async def test_repair_happy_path_syncs_job_and_writes_events(
    db_session, sample_customer, sample_user
):
    repair = await _intake(db_session, sample_customer.id, sample_user.id)
    uid = sample_user.id
    steps = [
        (
            lambda: RepairService.diagnose(
                db_session,
                repair.id,
                RepairDiagnoseInput(
                    diagnosis_notes="Schiene gerissen", estimated_cost=Decimal("40")
                ),
                uid,
            ),
            JobStatus.AWAITING_APPROVAL,
        ),
        (
            lambda: RepairService.approve(
                db_session, repair.id, RepairStatusUpdate(), uid
            ),
            JobStatus.CONFIRMED,
        ),
        (
            lambda: RepairService.start_repair(db_session, repair.id, uid),
            JobStatus.IN_PROGRESS,
        ),
        (
            lambda: RepairService.submit_for_quality_check(db_session, repair.id, uid),
            JobStatus.QUALITY_CHECK,
        ),
        (
            lambda: RepairService.complete_repair(
                db_session,
                repair.id,
                RepairCompleteInput(actual_cost=Decimal("45")),
                uid,
            ),
            JobStatus.READY,
        ),
        (lambda: RepairService.pickup(db_session, repair.id, uid), JobStatus.DELIVERED),
    ]
    for call, expected in steps:
        await call()
        job = await _job(db_session, repair.job_id)
        assert job.status == expected.value

    events = await _events(db_session, repair_job_id=repair.id)
    assert [e.to_status for e in events] == [
        "received",
        "diagnosed",
        "quoted",
        "approved",
        "in_repair",
        "quality_check",
        "ready",
        "picked_up",
    ]
    assert {e.job_id for e in events} == {repair.job_id}
    assert all(e.user_id == uid for e in events)


async def test_repair_cancel_and_soft_delete_reach_the_job(
    db_session, sample_customer, sample_user
):
    repair = await _intake(db_session, sample_customer.id, sample_user.id)

    await RepairService.cancel(
        db_session, repair.id, RepairStatusUpdate(), sample_user.id
    )
    job = await _job(db_session, repair.job_id)
    assert job.status == JobStatus.CANCELLED.value

    await RepairService.soft_delete(db_session, repair.id, sample_user.id)
    job = await _job(db_session, repair.job_id)
    assert job.is_deleted is True


async def test_invalid_repair_transition_writes_nothing(
    db_session, sample_customer, sample_user
):
    repair = await _intake(db_session, sample_customer.id, sample_user.id)

    with pytest.raises(ValueError, match="nicht erlaubt"):
        await RepairService.pickup(db_session, repair.id, sample_user.id)

    job = await _job(db_session, repair.job_id)
    assert job.status == JobStatus.INTAKE.value
    assert len(await _events(db_session, repair_job_id=repair.id)) == 1


@pytest.mark.parametrize(
    "current,target",
    REPAIR_PAIRS,
    ids=[f"{c.value}->{t.value}" for c, t in REPAIR_PAIRS],
)
async def test_every_repair_transition_syncs_the_job(
    db_session, sample_customer, current, target
):
    repair = await _plain_repair(db_session, sample_customer.id, status=current)

    event = await repair_workflow.transition(db_session, repair, target)
    await db_session.commit()

    assert event is not None
    assert event.repair_job_id == repair.id and event.order_id is None
    assert event.job_id == repair.job_id
    job = await _job(db_session, repair.job_id)
    assert job.status == REPAIR_STATUS_TO_JOB[target].value
    assert job.kind_status == target.value
