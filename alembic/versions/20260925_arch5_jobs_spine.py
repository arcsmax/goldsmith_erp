"""ARCH phase 5: ``jobs`` spine for orders and repairs (ARCH-02).

See docs/architecture/ADR-2026-09-25-jobs-spine.md.

Upgrade (additive; the per-kind tables stay the source of truth)
---------------------------------------------------------------
1. ``jobs`` (id, kind, customer_id, number, title, status, kind_status,
   deadline, on_hold_since, resume_date, is_deleted, created_at,
   updated_at). ``kind`` / ``status`` are String + CHECK, not PG enums.
2. Nullable ``job_id`` FKs on ``orders``, ``repair_jobs``, ``invoices``,
   ``customer_updates``, ``media_assets`` and ``order_events``; plus
   ``order_events.repair_job_id`` (repairs now get lifecycle events).
3. ``invoices.order_id`` and ``order_events.order_id`` become nullable (a
   repair invoice / a repair event has no order); partial unique index
   ``uq_invoices_one_active_per_job`` (one live invoice per job).
4. Data: one job per order (``AU-YYYY-NNNN``, numbered per Europe/Berlin
   year of ``created_at`` in (created_at, id) order) and per repair (its
   ``repair_number``); status mapped to the unified lifecycle; the
   ``number_sequences`` rows ``AU`` / ``REP`` are seeded with the highest
   value per year. ``job_id`` is backfilled on all six tables. Every
   repair without an event gets one synthetic ``order_events`` row
   (``reason = 'backfill'``, ``meta.source = 'arch5'``).

Idempotent: DDL goes through existence checks (a fresh DB already has the
columns and table from ``v1_initial``'s ``create_all()``), rows that already
have a job are skipped, the sequence seed only raises values.

Downgrade
---------
Refused while a repair invoice exists (``invoices.order_id IS NULL``):
dropping it would destroy a GoBD-relevant record. Otherwise: delete the
repair events, restore NOT NULL on the two ``order_id`` columns, drop the
index, the ``job_id`` / ``repair_job_id`` columns, the ``jobs`` table and the
``AU`` / ``REP`` counter rows (the old code derives repair numbers from
``MAX(repair_number)`` again).

Revision ID: 20260925_arch5_jobs
Revises: 20260925_arch4_media
Create Date: 2026-09-25
"""

from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple, Union
from zoneinfo import ZoneInfo

import sqlalchemy as sa

from alembic import op

revision: str = "20260925_arch5_jobs"
down_revision: Union[str, None] = "20260925_arch4_media"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

JOBS = "jobs"
ORDER_KIND = "AU"
REPAIR_KIND = "REP"
ACTIVE_PER_JOB_INDEX = "uq_invoices_one_active_per_job"
ACTIVE_WHERE = "status <> 'cancelled' AND cancels_invoice_id IS NULL"
_BERLIN = ZoneInfo("Europe/Berlin")
_TITLE_MAX = 200

# (table, ondelete) of every job_id FK.
JOB_FK_TABLES: Tuple[Tuple[str, str], ...] = (
    ("orders", "SET NULL"),
    ("repair_jobs", "SET NULL"),
    ("invoices", "RESTRICT"),
    ("customer_updates", "SET NULL"),
    ("media_assets", "SET NULL"),
    ("order_events", "SET NULL"),
)

JOB_KINDS = ("order", "repair")
JOB_STATUSES = (
    "draft",
    "intake",
    "awaiting_approval",
    "confirmed",
    "in_progress",
    "quality_check",
    "ready",
    "delivered",
    "on_hold",
    "cancelled",
)

# Frozen copies of services/job_service.py (a migration never imports app
# logic that may change later).
ORDER_STATUS_TO_JOB: Dict[str, str] = {
    "draft": "draft",
    "new": "draft",
    "confirmed": "confirmed",
    "in_progress": "in_progress",
    "waiting_for_fitting": "in_progress",
    "fitting_done": "in_progress",
    "ready_for_setting": "in_progress",
    "quality_check": "quality_check",
    "completed": "ready",
    "delivered": "delivered",
    "on_hold": "on_hold",
    "cancelled": "cancelled",
}
REPAIR_STATUS_TO_JOB: Dict[str, str] = {
    "received": "intake",
    "diagnosed": "intake",
    "quoted": "awaiting_approval",
    "approved": "confirmed",
    "in_repair": "in_progress",
    "quality_check": "quality_check",
    "ready": "ready",
    "picked_up": "delivered",
    "cancelled": "cancelled",
}


def _in_list(column: str, values: Iterable[str]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _dt() -> Any:
    from goldsmith_erp.db.types import UtcDateTime  # noqa: PLC0415

    return UtcDateTime()


def _is_sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


# --------------------------------------------------------------------------- #
# DDL
# --------------------------------------------------------------------------- #


def _create_jobs_table() -> None:
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        create_index_if_not_exists,
        create_table_if_not_exists,
    )

    create_table_if_not_exists(
        JOBS,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column(
            "customer_id",
            sa.Integer(),
            sa.ForeignKey("customers.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("number", sa.String(20), nullable=False),
        sa.Column("title", sa.String(_TITLE_MAX), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("kind_status", sa.String(30), nullable=False),
        sa.Column("deadline", sa.DateTime(timezone=True), nullable=True),
        sa.Column("on_hold_since", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resume_date", sa.Date(), nullable=True),
        sa.Column(
            "is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(_in_list("kind", JOB_KINDS), name="ck_jobs_kind"),
        sa.CheckConstraint(_in_list("status", JOB_STATUSES), name="ck_jobs_status"),
    )
    create_index_if_not_exists("ix_jobs_id", JOBS, ["id"])
    create_index_if_not_exists("ix_jobs_number", JOBS, ["number"], unique=True)
    create_index_if_not_exists("ix_jobs_kind", JOBS, ["kind"])
    create_index_if_not_exists("ix_jobs_customer_id", JOBS, ["customer_id"])
    create_index_if_not_exists("ix_jobs_status", JOBS, ["status"])
    create_index_if_not_exists("ix_jobs_deadline", JOBS, ["deadline"])
    create_index_if_not_exists("ix_jobs_created_at", JOBS, ["created_at"])
    create_index_if_not_exists("ix_jobs_status_deadline", JOBS, ["status", "deadline"])


def _add_fk_column(table: str, column: str, target: str, ondelete: str) -> None:
    """Nullable FK column + index; batch mode so SQLite gets the FK too."""
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        column_exists,
        create_index_if_not_exists,
        table_exists,
    )

    if not table_exists(table):
        return
    if not column_exists(table, column):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column(column, sa.Integer(), nullable=True))
            batch.create_foreign_key(
                f"fk_{table}_{column}",
                target,
                [column],
                ["id"],
                ondelete=ondelete,
            )
    create_index_if_not_exists(f"ix_{table}_{column}", table, [column])


def _set_order_id_nullable(table: str, nullable: bool) -> None:
    from goldsmith_erp.db.migration_helpers import table_exists  # noqa: PLC0415

    if not table_exists(table):
        return
    with op.batch_alter_table(table) as batch:
        batch.alter_column("order_id", existing_type=sa.Integer(), nullable=nullable)


def _create_active_per_job_index() -> None:
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        index_exists,
        table_exists,
    )

    if not table_exists("invoices") or index_exists("invoices", ACTIVE_PER_JOB_INDEX):
        return
    op.create_index(
        ACTIVE_PER_JOB_INDEX,
        "invoices",
        ["job_id"],
        unique=True,
        postgresql_where=sa.text(ACTIVE_WHERE),
        sqlite_where=sa.text(ACTIVE_WHERE),
    )


# --------------------------------------------------------------------------- #
# Data
# --------------------------------------------------------------------------- #


def _jobs_table() -> sa.TableClause:
    return sa.table(
        JOBS,
        sa.column("id", sa.Integer),
        sa.column("kind", sa.String),
        sa.column("customer_id", sa.Integer),
        sa.column("number", sa.String),
        sa.column("title", sa.String),
        sa.column("status", sa.String),
        sa.column("kind_status", sa.String),
        sa.column("deadline", _dt()),
        sa.column("on_hold_since", _dt()),
        sa.column("resume_date", sa.Date),
        sa.column("is_deleted", sa.Boolean),
        sa.column("created_at", _dt()),
        sa.column("updated_at", _dt()),
    )


def berlin_year(moment: Optional[datetime]) -> int:
    value = moment or datetime.now(timezone.utc)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(_BERLIN).year


def clean_title(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    cleaned = " ".join(str(text).split())
    return cleaned[:_TITLE_MAX] or None


def _parse(kind: str, number: Optional[str]) -> Optional[Tuple[int, int]]:
    match = re.match(rf"^{re.escape(kind)}-(\d{{4}})-(\d+)$", number or "")
    if match is None:
        return None
    return int(match.group(1)), int(match.group(2))


def _existing_numbers(conn: sa.engine.Connection) -> Dict[int, int]:
    """Highest AU value per year already used by jobs (re-run safety)."""
    highest: Dict[int, int] = {}
    for (number,) in conn.execute(sa.text("SELECT number FROM jobs")).all():
        parsed = _parse(ORDER_KIND, number)
        if parsed is not None:
            highest[parsed[0]] = max(highest.get(parsed[0], 0), parsed[1])
    return highest


def _insert_job(conn: sa.engine.Connection, values: Dict[str, Any]) -> int:
    jobs = _jobs_table()
    result = conn.execute(sa.insert(jobs).values(**values).returning(jobs.c.id))
    return int(result.scalar_one())


def _job_values(
    *,
    kind: str,
    number: str,
    customer_id: Optional[int],
    title: Optional[str],
    status: str,
    kind_status: str,
    deadline: Any,
    resume_date: Any,
    is_deleted: Any,
    created_at: Any,
    updated_at: Any,
) -> Dict[str, Any]:
    now = datetime.now(timezone.utc)
    on_hold = status == "on_hold"
    return {
        "kind": kind,
        "number": number,
        "customer_id": customer_id,
        "title": clean_title(title),
        "status": status,
        "kind_status": kind_status,
        "deadline": deadline,
        "on_hold_since": (updated_at or created_at or now) if on_hold else None,
        "resume_date": resume_date if on_hold else None,
        "is_deleted": bool(is_deleted),
        "created_at": created_at or now,
        "updated_at": updated_at or created_at or now,
    }


def backfill_order_jobs(conn: sa.engine.Connection) -> int:
    orders = sa.table(
        "orders",
        sa.column("id", sa.Integer),
        sa.column("customer_id", sa.Integer),
        sa.column("title", sa.String),
        sa.column("status", sa.String),
        sa.column("deadline", _dt()),
        sa.column("resume_date", sa.Date),
        sa.column("is_deleted", sa.Boolean),
        sa.column("created_at", _dt()),
        sa.column("updated_at", _dt()),
        sa.column("job_id", sa.Integer),
    )
    rows = conn.execute(
        sa.select(orders)
        .where(orders.c.job_id.is_(None))
        .order_by(orders.c.created_at.asc(), orders.c.id.asc())
    ).all()
    counters = _existing_numbers(conn)
    for row in rows:
        year = berlin_year(row.created_at)
        counters[year] = counters.get(year, 0) + 1
        status = str(row.status)
        job_id = _insert_job(
            conn,
            _job_values(
                kind="order",
                number=f"{ORDER_KIND}-{year}-{counters[year]:04d}",
                customer_id=row.customer_id,
                title=row.title,
                status=ORDER_STATUS_TO_JOB.get(status, "draft"),
                kind_status=status,
                deadline=row.deadline,
                resume_date=row.resume_date,
                is_deleted=row.is_deleted,
                created_at=row.created_at,
                updated_at=row.updated_at,
            ),
        )
        conn.execute(
            sa.update(orders).where(orders.c.id == row.id).values(job_id=job_id)
        )
    return len(rows)


def backfill_repair_jobs(conn: sa.engine.Connection) -> int:
    repairs = sa.table(
        "repair_jobs",
        sa.column("id", sa.Integer),
        sa.column("repair_number", sa.String),
        sa.column("customer_id", sa.Integer),
        sa.column("item_description", sa.Text),
        sa.column("status", sa.String),
        sa.column("estimated_completion_date", _dt()),
        sa.column("is_deleted", sa.Boolean),
        sa.column("created_at", _dt()),
        sa.column("updated_at", _dt()),
        sa.column("job_id", sa.Integer),
    )
    rows = conn.execute(
        sa.select(repairs)
        .where(repairs.c.job_id.is_(None))
        .order_by(repairs.c.id.asc())
    ).all()
    for row in rows:
        status = str(row.status)
        job_id = _insert_job(
            conn,
            _job_values(
                kind="repair",
                number=str(row.repair_number),
                customer_id=row.customer_id,
                title=row.item_description,
                status=REPAIR_STATUS_TO_JOB.get(status, "intake"),
                kind_status=status,
                deadline=row.estimated_completion_date,
                resume_date=None,
                is_deleted=row.is_deleted,
                created_at=row.created_at,
                updated_at=row.updated_at,
            ),
        )
        conn.execute(
            sa.update(repairs).where(repairs.c.id == row.id).values(job_id=job_id)
        )
    return len(rows)


def _highest_per_year(kind: str, numbers: Iterable[Optional[str]]) -> Dict[int, int]:
    highest: Dict[int, int] = {}
    for number in numbers:
        parsed = _parse(kind, number)
        if parsed is not None:
            highest[parsed[0]] = max(highest.get(parsed[0], 0), parsed[1])
    return highest


def seed_sequences(conn: sa.engine.Connection) -> Dict[str, Dict[int, int]]:
    from goldsmith_erp.db.migration_helpers import table_exists  # noqa: PLC0415

    if not table_exists("number_sequences"):
        return {}
    sequences = sa.table(
        "number_sequences",
        sa.column("kind", sa.String),
        sa.column("year", sa.Integer),
        sa.column("last_value", sa.Integer),
    )
    sources = {
        ORDER_KIND: "SELECT number FROM jobs",
        REPAIR_KIND: "SELECT repair_number FROM repair_jobs",
    }
    seeded: Dict[str, Dict[int, int]] = {}
    for kind, sql in sources.items():
        numbers = [r[0] for r in conn.execute(sa.text(sql)).all()]
        highest = _highest_per_year(kind, numbers)
        seeded[kind] = highest
        for year, value in highest.items():
            current = conn.execute(
                sa.select(sequences.c.last_value).where(
                    sequences.c.kind == kind, sequences.c.year == year
                )
            ).scalar_one_or_none()
            if current is None:
                conn.execute(
                    sa.insert(sequences).values(kind=kind, year=year, last_value=value)
                )
            elif int(current) < value:
                conn.execute(
                    sa.update(sequences)
                    .where(sequences.c.kind == kind, sequences.c.year == year)
                    .values(last_value=value)
                )
    return seeded


# (table, SQL that sets job_id where it is NULL)
_ATTACH_SQL: Tuple[Tuple[str, str], ...] = (
    (
        "invoices",
        "UPDATE invoices SET job_id = (SELECT o.job_id FROM orders o"
        " WHERE o.id = invoices.order_id) WHERE job_id IS NULL"
        " AND order_id IS NOT NULL",
    ),
    (
        "customer_updates",
        "UPDATE customer_updates SET job_id = COALESCE("
        "(SELECT o.job_id FROM orders o WHERE o.id = customer_updates.order_id),"
        " (SELECT r.job_id FROM repair_jobs r"
        " WHERE r.id = customer_updates.repair_job_id)) WHERE job_id IS NULL",
    ),
    (
        "media_assets",
        "UPDATE media_assets SET job_id = CASE owner_type"
        " WHEN 'order' THEN (SELECT o.job_id FROM orders o"
        " WHERE o.id = media_assets.owner_id)"
        " WHEN 'repair' THEN (SELECT r.job_id FROM repair_jobs r"
        " WHERE r.id = media_assets.owner_id) END"
        " WHERE job_id IS NULL AND owner_type IN ('order', 'repair')",
    ),
    (
        "order_events",
        "UPDATE order_events SET job_id = (SELECT o.job_id FROM orders o"
        " WHERE o.id = order_events.order_id) WHERE job_id IS NULL"
        " AND order_id IS NOT NULL",
    ),
)


def attach_job_ids(conn: sa.engine.Connection) -> Dict[str, int]:
    from goldsmith_erp.db.migration_helpers import table_exists  # noqa: PLC0415

    counts: Dict[str, int] = {}
    for table, sql in _ATTACH_SQL:
        if not table_exists(table):
            continue
        conn.execute(sa.text(sql))
        counts[table] = int(
            conn.execute(
                sa.text(f"SELECT COUNT(*) FROM {table} WHERE job_id IS NOT NULL")
            ).scalar_one()
        )
    return counts


def backfill_repair_events(conn: sa.engine.Connection) -> int:
    events = sa.table(
        "order_events",
        sa.column("order_id", sa.Integer),
        sa.column("repair_job_id", sa.Integer),
        sa.column("job_id", sa.Integer),
        sa.column("from_status", sa.String),
        sa.column("to_status", sa.String),
        sa.column("user_id", sa.Integer),
        sa.column("reason", sa.String),
        sa.column("created_at", _dt()),
        sa.column("meta", sa.JSON),
    )
    repairs = sa.table(
        "repair_jobs",
        sa.column("id", sa.Integer),
        sa.column("job_id", sa.Integer),
        sa.column("status", sa.String),
        sa.column("created_at", _dt()),
        sa.column("updated_at", _dt()),
    )
    has_event = sa.exists().where(events.c.repair_job_id == repairs.c.id)
    rows = conn.execute(
        sa.select(repairs).where(~has_event).order_by(repairs.c.id.asc())
    ).all()
    now = datetime.now(timezone.utc)
    payload: List[Dict[str, Any]] = [
        {
            "order_id": None,
            "repair_job_id": row.id,
            "job_id": row.job_id,
            "from_status": None,
            "to_status": str(row.status),
            "user_id": None,
            "reason": "backfill",
            "created_at": row.updated_at or row.created_at or now,
            "meta": {"backfill": True, "source": "arch5"},
        }
        for row in rows
    ]
    if payload:
        conn.execute(sa.insert(events), payload)
    return len(payload)


def upgrade() -> None:
    from goldsmith_erp.db.migration_helpers import table_exists  # noqa: PLC0415

    if not table_exists("orders") or not table_exists("repair_jobs"):
        return
    _create_jobs_table()
    for table, ondelete in JOB_FK_TABLES:
        _add_fk_column(table, "job_id", JOBS, ondelete)
    _add_fk_column("order_events", "repair_job_id", "repair_jobs", "CASCADE")
    _set_order_id_nullable("invoices", True)
    _set_order_id_nullable("order_events", True)
    _create_active_per_job_index()

    conn = op.get_bind()
    orders = backfill_order_jobs(conn)
    repairs = backfill_repair_jobs(conn)
    seeded = seed_sequences(conn)
    attached = attach_job_ids(conn)
    events = backfill_repair_events(conn) if table_exists("order_events") else 0
    logger.info(
        "arch5 jobs backfill: %d order jobs, %d repair jobs, %d repair events,"
        " attached %s, sequences %s",
        orders,
        repairs,
        events,
        attached,
        seeded,
    )


# --------------------------------------------------------------------------- #
# Downgrade
# --------------------------------------------------------------------------- #


def _drop_fk_column(table: str, column: str) -> None:
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        column_exists,
        drop_index_if_exists,
        table_exists,
    )

    if not table_exists(table) or not column_exists(table, column):
        return
    drop_index_if_exists(f"ix_{table}_{column}", table)
    if not _is_sqlite():
        # PostgreSQL drops the column's FK constraint with the column.
        op.drop_column(table, column)
        return
    with op.batch_alter_table(table) as batch:
        batch.drop_column(column)


def downgrade() -> None:
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        drop_index_if_exists,
        drop_table_if_exists,
        table_exists,
    )

    if not table_exists(JOBS):
        return
    conn = op.get_bind()
    if table_exists("invoices"):
        repair_invoices = conn.execute(
            sa.text("SELECT COUNT(*) FROM invoices WHERE order_id IS NULL")
        ).scalar_one()
        if int(repair_invoices):
            raise RuntimeError(
                f"arch5 downgrade refused: {repair_invoices} repair invoice(s)"
                " have no order. Invoices are retained records (GoBD); keep"
                " this revision or migrate them first."
            )
        drop_index_if_exists(ACTIVE_PER_JOB_INDEX, "invoices")
    if table_exists("order_events"):
        conn.execute(sa.text("DELETE FROM order_events WHERE order_id IS NULL"))
        _set_order_id_nullable("order_events", False)
    _set_order_id_nullable("invoices", False)
    _drop_fk_column("order_events", "repair_job_id")
    for table, _ondelete in JOB_FK_TABLES:
        _drop_fk_column(table, "job_id")
    if table_exists("number_sequences"):
        conn.execute(
            sa.text("DELETE FROM number_sequences WHERE kind IN (:a, :b)"),
            {"a": ORDER_KIND, "b": REPAIR_KIND},
        )
    for index in (
        "ix_jobs_status_deadline",
        "ix_jobs_created_at",
        "ix_jobs_deadline",
        "ix_jobs_status",
        "ix_jobs_customer_id",
        "ix_jobs_kind",
        "ix_jobs_number",
        "ix_jobs_id",
    ):
        drop_index_if_exists(index, JOBS)
    drop_table_if_exists(JOBS)
