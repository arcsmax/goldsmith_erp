"""Job spine: sync from orders/repairs, list and lookup (ARCH-02, phase 5).

See docs/architecture/ADR-2026-09-25-jobs-spine.md.

For this release ``orders`` and ``repair_jobs`` stay the source of truth.
Every service path that creates one of them or changes its status calls
:meth:`JobService.sync_order` / :meth:`JobService.sync_repair` inside the
same transaction (no DB triggers):

- ``order_workflow.record_creation`` / ``order_workflow.transition``
- ``OrderService.update_order`` (title, deadline, customer) and deletion
- ``QuoteService.convert_quote`` (new order from a quote)
- ``repair_workflow.record_creation`` / ``repair_workflow.transition``
  (every repair status write) and ``RepairService.soft_delete``

``sync_*`` is an idempotent upsert: a row that has no job yet (created by
old code, the seed script or a test fixture) gets one on its next sync.
Nothing here commits; the caller's ``transactional(db)`` does.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Optional

from sqlalchemy import Select, func
from sqlalchemy import inspect as sa_inspect
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from goldsmith_erp.core.config import settings
from goldsmith_erp.db.models import (
    ORDER_NUMBER_KIND,
    Job,
    JobKind,
    JobStatus,
    Order,
    OrderStatusEnum,
    RepairJob,
    RepairJobStatus,
)
from goldsmith_erp.services.number_sequence_service import NumberSequenceService

logger = logging.getLogger(__name__)

TITLE_MAX_LENGTH = 200
#: pg_advisory_xact_lock key for the startup backfill ("JOBS" in ASCII).
_BACKFILL_LOCK_KEY = 0x4A4F4253

_O = OrderStatusEnum
_R = RepairJobStatus
_J = JobStatus

#: Unified lifecycle per order status (ADR "Status mapping").
ORDER_STATUS_TO_JOB: Mapping[OrderStatusEnum, JobStatus] = {
    _O.DRAFT: _J.DRAFT,
    _O.NEW: _J.DRAFT,
    _O.CONFIRMED: _J.CONFIRMED,
    _O.IN_PROGRESS: _J.IN_PROGRESS,
    _O.WAITING_FOR_FITTING: _J.IN_PROGRESS,
    _O.FITTING_DONE: _J.IN_PROGRESS,
    _O.READY_FOR_SETTING: _J.IN_PROGRESS,
    _O.QUALITY_CHECK: _J.QUALITY_CHECK,
    _O.COMPLETED: _J.READY,
    _O.DELIVERED: _J.DELIVERED,
    _O.ON_HOLD: _J.ON_HOLD,
    _O.CANCELLED: _J.CANCELLED,
}

#: Unified lifecycle per repair status.
REPAIR_STATUS_TO_JOB: Mapping[RepairJobStatus, JobStatus] = {
    _R.RECEIVED: _J.INTAKE,
    _R.DIAGNOSED: _J.INTAKE,
    _R.QUOTED: _J.AWAITING_APPROVAL,
    _R.APPROVED: _J.CONFIRMED,
    _R.IN_REPAIR: _J.IN_PROGRESS,
    _R.QUALITY_CHECK: _J.QUALITY_CHECK,
    _R.READY: _J.READY,
    _R.PICKED_UP: _J.DELIVERED,
    _R.CANCELLED: _J.CANCELLED,
}

JOB_STATUS_LABELS: Mapping[JobStatus, str] = {
    _J.DRAFT: "Entwurf",
    _J.INTAKE: "Eingang",
    _J.AWAITING_APPROVAL: "Wartet auf Freigabe",
    _J.CONFIRMED: "Bestätigt",
    _J.IN_PROGRESS: "In Arbeit",
    _J.QUALITY_CHECK: "Qualitätskontrolle",
    _J.READY: "Fertig",
    _J.DELIVERED: "Ausgeliefert",
    _J.ON_HOLD: "Pausiert",
    _J.CANCELLED: "Storniert",
}

JOB_DETAIL_OPTIONS = (
    selectinload(Job.customer),
    selectinload(Job.order),
    selectinload(Job.repair),
)


#: Columns read by the snapshots (reloaded when expired).
_SYNCED_COLUMNS = frozenset(
    {
        "id",
        "job_id",
        "customer_id",
        "title",
        "item_description",
        "status",
        "deadline",
        "estimated_completion_date",
        "resume_date",
        "is_deleted",
        "created_at",
        "repair_number",
    }
)


def _value(status: Any) -> str:
    return str(getattr(status, "value", status))


def job_status_for_order(status: Any) -> JobStatus:
    return ORDER_STATUS_TO_JOB[OrderStatusEnum(_value(status))]


def job_status_for_repair(status: Any) -> JobStatus:
    return REPAIR_STATUS_TO_JOB[RepairJobStatus(_value(status))]


def _title(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    cleaned = " ".join(str(text).split())
    return cleaned[:TITLE_MAX_LENGTH] or None


def _hold_since(job: Any, status: JobStatus) -> Optional[datetime]:
    if status is not JobStatus.ON_HOLD:
        return None
    return job.on_hold_since or datetime.now(timezone.utc)


@dataclass(frozen=True)
class JobSnapshot:
    """The per-kind fields copied into ``jobs`` on every sync."""

    kind: JobKind
    customer_id: Optional[int]
    title: Optional[str]
    status: JobStatus
    kind_status: str
    deadline: Optional[datetime]
    resume_date: Any
    is_deleted: bool
    created_at: Optional[datetime]


def snapshot_order(order: Any) -> JobSnapshot:
    return JobSnapshot(
        kind=JobKind.ORDER,
        customer_id=order.customer_id,
        title=_title(order.title),
        status=job_status_for_order(order.status),
        kind_status=_value(order.status),
        deadline=order.deadline,
        resume_date=order.resume_date,
        is_deleted=bool(order.is_deleted),
        created_at=order.created_at,
    )


def snapshot_repair(repair: Any) -> JobSnapshot:
    return JobSnapshot(
        kind=JobKind.REPAIR,
        customer_id=repair.customer_id,
        title=_title(repair.item_description),
        status=job_status_for_repair(repair.status),
        kind_status=_value(repair.status),
        deadline=repair.estimated_completion_date,
        resume_date=None,
        is_deleted=bool(repair.is_deleted),
        created_at=repair.created_at,
    )


def _apply(job: Any, snap: JobSnapshot) -> None:
    job.customer_id = snap.customer_id
    job.title = snap.title
    job.on_hold_since = _hold_since(job, snap.status)
    job.status = snap.status.value
    job.kind_status = snap.kind_status
    job.deadline = snap.deadline
    job.resume_date = snap.resume_date if snap.status is JobStatus.ON_HOLD else None
    job.is_deleted = snap.is_deleted
    job.updated_at = datetime.now(timezone.utc)


async def _load_job(db: AsyncSession, job_id: Optional[int]) -> Optional[Job]:
    if job_id is None:
        return None
    return await db.get(Job, job_id)


class JobService:
    """Static-method service; every method takes the AsyncSession first."""

    # ------------------------------------------------------------------ sync

    @staticmethod
    async def _upsert(
        db: AsyncSession, row: Any, snap: JobSnapshot, number: Optional[str]
    ) -> Job:
        job: Any = await _load_job(db, row.job_id)
        created = job is None
        if job is None:
            if number is None:
                number = await NumberSequenceService.next_number(db, ORDER_NUMBER_KIND)
            job = Job(
                kind=snap.kind.value,
                number=number,
                created_at=snap.created_at or datetime.now(timezone.utc),
            )
            db.add(job)
        _apply(job, snap)
        await db.flush()
        if created:
            row.job_id = job.id
            await db.flush()
            logger.info(
                "Job created",
                extra={"job_id": job.id, "kind": snap.kind.value, "row_id": row.id},
            )
        return job  # type: ignore[no-any-return]

    @staticmethod
    async def _loaded(db: AsyncSession, row: Any) -> Any:
        """Flush pending changes, then reload expired columns (async-safe)."""
        await db.flush()
        expired = set(sa_inspect(row).expired_attributes) & _SYNCED_COLUMNS
        if expired:
            await db.refresh(row, attribute_names=sorted(expired))
        return row

    @staticmethod
    async def sync_order(db: AsyncSession, order: Order) -> Job:
        """Create or refresh the job of ``order`` (flushed, not committed)."""
        row = await JobService._loaded(db, order)
        return await JobService._upsert(db, row, snapshot_order(row), None)

    @staticmethod
    async def sync_repair(db: AsyncSession, repair: RepairJob) -> Job:
        """Create or refresh the job of ``repair``; its number is the repair's."""
        row = await JobService._loaded(db, repair)
        return await JobService._upsert(
            db, row, snapshot_repair(row), str(row.repair_number)
        )

    # --------------------------------------------------------------- lookup

    @staticmethod
    async def job_id_for(
        db: AsyncSession,
        *,
        order_id: Optional[int] = None,
        repair_job_id: Optional[int] = None,
    ) -> Optional[int]:
        """The job id of an order or a repair (None when it has none yet)."""
        if order_id is not None:
            stmt: Select[Any] = select(Order.job_id).where(Order.id == order_id)
        elif repair_job_id is not None:
            stmt = select(RepairJob.job_id).where(RepairJob.id == repair_job_id)
        else:
            return None
        value = (await db.execute(stmt)).scalar_one_or_none()
        return int(value) if value is not None else None

    @staticmethod
    async def get_job(db: AsyncSession, job_id: int) -> Optional[Job]:
        result = await db.execute(
            select(Job)
            .options(*JOB_DETAIL_OPTIONS)
            .where(Job.id == job_id, Job.is_deleted.is_(False))
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def count_missing(db: AsyncSession) -> dict[str, int]:
        """Orders / repairs without a job (health check for the sync rules)."""
        orders = await db.execute(
            select(func.count()).select_from(Order).where(Order.job_id.is_(None))
        )
        repairs = await db.execute(
            select(func.count())
            .select_from(RepairJob)
            .where(RepairJob.job_id.is_(None))
        )
        return {
            "orders": int(orders.scalar_one()),
            "repairs": int(repairs.scalar_one()),
        }

    @staticmethod
    async def backfill_missing(db: AsyncSession) -> dict[str, int]:
        """Give every order / repair without a job one (idempotent)."""
        orders = (
            (await db.execute(select(Order).where(Order.job_id.is_(None))))
            .scalars()
            .all()
        )
        for order in orders:
            await JobService.sync_order(db, order)
        repairs = (
            (await db.execute(select(RepairJob).where(RepairJob.job_id.is_(None))))
            .scalars()
            .all()
        )
        for repair in repairs:
            await JobService.sync_repair(db, repair)
        return {"orders": len(orders), "repairs": len(repairs)}

    @staticmethod
    async def backfill_on_startup(
        session_factory: Callable[[], Any],
    ) -> Optional[dict[str, int]]:
        """Run :meth:`backfill_missing` once in its own transaction.

        Gated by ``settings.JOBS_BACKFILL_ON_STARTUP``. On PostgreSQL an
        advisory transaction lock serialises concurrent workers, so two
        processes starting together cannot both create a job for one row.
        A failure is logged with its traceback and does not stop the app:
        the sync rules repair a missing job on the row's next write.
        """
        if not settings.JOBS_BACKFILL_ON_STARTUP:
            return None
        async with session_factory() as db:
            try:
                if db.get_bind().dialect.name == "postgresql":
                    await db.execute(
                        text("SELECT pg_advisory_xact_lock(:key)"),
                        {"key": _BACKFILL_LOCK_KEY},
                    )
                counts = await JobService.backfill_missing(db)
                await db.commit()
            except SQLAlchemyError:
                await db.rollback()
                logger.exception("jobs_backfill_on_startup_failed")
                return None
        logger.info("jobs_backfill_on_startup", extra={"jobs_created": counts})
        return counts


__all__ = [
    "JOB_DETAIL_OPTIONS",
    "JOB_STATUS_LABELS",
    "JobService",
    "ORDER_STATUS_TO_JOB",
    "REPAIR_STATUS_TO_JOB",
    "job_status_for_order",
    "job_status_for_repair",
]
