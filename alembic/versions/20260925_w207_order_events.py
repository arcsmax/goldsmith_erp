"""W2-07: order lifecycle events, on_hold / cancelled, legacy NEW mapping.

ARCH-01, BE-06, DOM-13, DOM-46 (docs/review/2026-09-25/).

Upgrade:
1. PostgreSQL only: ``ALTER TYPE orderstatusenum ADD VALUE IF NOT EXISTS``
   ``'on_hold'`` and ``'cancelled'`` (SQLite stores the enum as VARCHAR).
   The new values are not used inside this migration, so the PG rule that a
   freshly added enum value cannot be used in the same transaction is moot.
2. ``orders.hold_reason`` / ``orders.resume_date`` / ``orders.cancel_reason``.
3. ``order_events`` (id, order_id FK CASCADE, from_status, to_status,
   user_id FK SET NULL, reason, created_at, meta JSON) + index
   ``(order_id, created_at)``.
4. Data (DOM-46): legacy ``new`` -> ``draft`` when the order has no price
   (NULL or 0: nothing was agreed with the customer yet), otherwise
   ``confirmed`` (a price means the job was accepted). This is the rule the
   fix plan asked for; staff can move a mis-mapped order with one allowed
   transition (draft <-> confirmed).
5. Data: one synthetic event per order that has none yet:
   ``from_status`` NULL, ``to_status`` = the (mapped) current status,
   ``created_at`` = ``COALESCE(updated_at, created_at, now)`` (the last time
   the status could have changed), ``reason`` = ``'backfill'``,
   ``meta`` = ``{"backfill": true, "source": "w207"}`` plus
   ``"legacy_status": "new"`` when step 4 mapped the row. Rows are inserted
   through the ``JSON`` type so both dialects bind ``meta`` correctly.

Idempotent: DDL goes through the ``migration_helpers`` existence checks (a
fresh DB already got the columns and table from ``v1_initial``'s
``create_all()``), the mapping only touches ``new`` rows, and the backfill
skips orders that already have an event.

Downgrade (lossy only for the history itself):
- ``on_hold`` -> the latest non-hold/non-cancelled status in the order's
  events, else ``confirmed``; ``cancelled`` -> ``draft`` (pre-W2-07 code
  cannot render either value; ``draft`` keeps a cancelled order out of
  production lists).
- rows whose backfill event recorded ``legacy_status = new`` go back to
  ``new``.
- drop ``order_events`` and the three columns. PG enum values cannot be
  dropped; the two labels stay in ``orderstatusenum`` unused.

Revision ID: 20260925_w207_order_events
Revises: 20260925_c22_cu_dedupe
Create Date: 2026-09-25
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Optional, Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260925_w207_order_events"
down_revision: Union[str, None] = "20260925_c22_cu_dedupe"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

EVENTS = "order_events"
EVENTS_INDEX = "ix_order_events_order_created"
_NEW_COLUMNS = ("hold_reason", "resume_date", "cancel_reason")
_BACKFILL_REASON = "backfill"
_PAUSE_OR_CANCEL = ("on_hold", "cancelled")

_events_table = sa.table(
    EVENTS,
    sa.column("order_id", sa.Integer),
    sa.column("from_status", sa.String),
    sa.column("to_status", sa.String),
    sa.column("user_id", sa.Integer),
    sa.column("reason", sa.String),
    sa.column("created_at", sa.DateTime),
    sa.column("meta", sa.JSON),
)


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def _add_enum_values() -> None:
    if not _is_postgres():
        return
    for value in _PAUSE_OR_CANCEL:
        op.execute(f"ALTER TYPE orderstatusenum ADD VALUE IF NOT EXISTS '{value}'")


def _add_columns() -> None:
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        add_column_if_not_exists,
    )

    add_column_if_not_exists(
        "orders", sa.Column("hold_reason", sa.String(500), nullable=True)
    )
    add_column_if_not_exists(
        "orders", sa.Column("resume_date", sa.Date(), nullable=True)
    )
    add_column_if_not_exists(
        "orders", sa.Column("cancel_reason", sa.String(500), nullable=True)
    )


def _create_events_table() -> None:
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        create_index_if_not_exists,
        create_table_if_not_exists,
    )

    create_table_if_not_exists(
        EVENTS,
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "order_id",
            sa.Integer(),
            sa.ForeignKey("orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("from_status", sa.String(30), nullable=True),
        sa.Column("to_status", sa.String(30), nullable=False),
        sa.Column(
            "user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("meta", sa.JSON(), nullable=True),
    )
    create_index_if_not_exists("ix_order_events_id", EVENTS, ["id"])
    create_index_if_not_exists("ix_order_events_order_id", EVENTS, ["order_id"])
    create_index_if_not_exists(EVENTS_INDEX, EVENTS, ["order_id", "created_at"])


def _map_legacy_new(bind: sa.engine.Connection) -> set[int]:
    """DOM-46: new -> draft (no price) / confirmed (priced). Returns ids."""
    rows = bind.execute(
        sa.text("SELECT id, price FROM orders WHERE status = 'new'")
    ).all()
    mapped: set[int] = set()
    for order_id, price in rows:
        target = "confirmed" if price not in (None, 0) else "draft"
        bind.execute(
            sa.text("UPDATE orders SET status = :status WHERE id = :id"),
            {"status": target, "id": order_id},
        )
        mapped.add(order_id)
    return mapped


def _backfill_events(bind: sa.engine.Connection, legacy_ids: set[int]) -> None:
    # Typed table so both dialects hand back datetimes (SQLite returns text
    # for a raw SELECT, which the DateTime bind then rejects).
    orders = sa.table(
        "orders",
        sa.column("id", sa.Integer),
        sa.column("status", sa.String),
        sa.column("created_at", sa.DateTime),
        sa.column("updated_at", sa.DateTime),
    )
    has_event = sa.exists().where(_events_table.c.order_id == orders.c.id)
    rows = bind.execute(
        sa.select(
            orders.c.id, orders.c.status, orders.c.created_at, orders.c.updated_at
        )
        .where(~has_event)
        .order_by(orders.c.id)
    ).all()
    now = datetime.utcnow()
    payload: list[dict[str, Any]] = []
    for order_id, status, created_at, updated_at in rows:
        meta: dict[str, Any] = {"backfill": True, "source": "w207"}
        if order_id in legacy_ids:
            meta["legacy_status"] = "new"
        payload.append(
            {
                "order_id": order_id,
                "from_status": None,
                "to_status": str(status),
                "user_id": None,
                "reason": _BACKFILL_REASON,
                "created_at": updated_at or created_at or now,
                "meta": meta,
            }
        )
    if payload:
        op.bulk_insert(_events_table, payload)


def upgrade() -> None:
    from goldsmith_erp.db.migration_helpers import table_exists  # noqa: PLC0415

    if not table_exists("orders"):
        return
    _add_enum_values()
    _add_columns()
    _create_events_table()
    bind = op.get_bind()
    legacy_ids = _map_legacy_new(bind)
    _backfill_events(bind, legacy_ids)


# --------------------------------------------------------------------------- #
# Downgrade
# --------------------------------------------------------------------------- #


def _load_meta(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        loaded = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _status_before_hold(bind: sa.engine.Connection, order_id: int) -> Optional[str]:
    rows = bind.execute(
        sa.text(
            "SELECT to_status FROM order_events WHERE order_id = :id"
            " ORDER BY created_at DESC, id DESC"
        ),
        {"id": order_id},
    ).all()
    for (to_status,) in rows:
        if to_status not in _PAUSE_OR_CANCEL:
            return str(to_status)
    return None


def _restore_statuses(bind: sa.engine.Connection) -> None:
    held = bind.execute(sa.text("SELECT id FROM orders WHERE status = 'on_hold'")).all()
    for (order_id,) in held:
        previous = _status_before_hold(bind, order_id) or "confirmed"
        bind.execute(
            sa.text("UPDATE orders SET status = :status WHERE id = :id"),
            {"status": previous, "id": order_id},
        )
    bind.execute(
        sa.text("UPDATE orders SET status = 'draft' WHERE status = 'cancelled'")
    )

    backfills = bind.execute(
        sa.text("SELECT order_id, meta FROM order_events WHERE reason = :reason"),
        {"reason": _BACKFILL_REASON},
    ).all()
    for order_id, raw_meta in backfills:
        if _load_meta(raw_meta).get("legacy_status") != "new":
            continue
        bind.execute(
            sa.text(
                "UPDATE orders SET status = 'new' WHERE id = :id"
                " AND status IN ('draft', 'confirmed')"
            ),
            {"id": order_id},
        )


def downgrade() -> None:
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        drop_column_if_exists,
        drop_index_if_exists,
        drop_table_if_exists,
        table_exists,
    )

    if not table_exists("orders"):
        return
    if table_exists(EVENTS):
        _restore_statuses(op.get_bind())
        drop_index_if_exists(EVENTS_INDEX, EVENTS)
        drop_index_if_exists("ix_order_events_order_id", EVENTS)
        drop_index_if_exists("ix_order_events_id", EVENTS)
        drop_table_if_exists(EVENTS)
    for column in _NEW_COLUMNS:
        drop_column_if_exists("orders", column)
