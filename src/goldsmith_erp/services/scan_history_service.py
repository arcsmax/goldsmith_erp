"""Scan history of a piece: who scanned it, when, where, and what they did.

2026-09 audit (SC-01/02/03). The owner's requirement: every scan of a job
bag is tracked, so a lost piece's history shows who scanned it last, where
and what they did.

Row model (append-only, no migration):

  * The client writes one ``scan_logs`` row per decode immediately
    (``action_taken="scan_only"``, or ``"unrecognised"`` when the payload
    resolved to nothing).
  * When the user then picks an action, the client writes a SECOND row
    with ``action_taken=<action id>`` and ``context.parent_scan_id`` /
    ``context.action_result``. ``scan_logs`` is a partitioned, append-only
    audit log; rows are never updated, so the scan itself stays on record
    even when the action fails or the tablet dies mid-action.
  * "Where" is ``context.current_location`` — the device's bench location,
    else the running timer's location, else null (text label; there is no
    ``location_id`` column on ``scan_logs``).

Reads here never return financial fields or entity payloads: only user
name, time, location, action and result.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Sequence, Tuple

from sqlalchemy import func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.sql import Select

from goldsmith_erp.core import pubsub
from goldsmith_erp.db.models import RepairJob as RepairJobModel
from goldsmith_erp.db.models import ScanLog as ScanLogModel
from goldsmith_erp.db.models import User as UserModel
from goldsmith_erp.models.scan_history import (
    LastScanRead,
    PieceScanPage,
    PieceScanRead,
    ScanHistoryPage,
    ScanHistoryRow,
)

logger = logging.getLogger(__name__)

SCAN_CHANNEL = "scan_updates"
DEFAULT_HISTORY_LIMIT = 25
MAX_HISTORY_LIMIT = 100
DELETED_USER_LABEL = "Gelöschter Benutzer"

# ``ORDER:42`` / ``repair:17`` — the label payload grammar (label_service).
_CODE_RE = re.compile(r"^([A-Za-z_]+):(\d+)$")
_DIGITS_RE = re.compile(r"^\d+$")
_PREFIX_TO_TYPE: Dict[str, str] = {
    "ORDER": "order",
    "REPAIR": "repair",
    "METAL": "metal_purchase",
    "MATERIAL": "material",
}


@dataclass(frozen=True)
class HistoryFilter:
    """Filters of the cross-piece search (all optional)."""

    q: Optional[str] = None
    user_id: Optional[int] = None
    date_from: Optional[datetime] = None
    date_to: Optional[datetime] = None


# --------------------------------------------------------------------------- #
# Projection helpers
# --------------------------------------------------------------------------- #


def user_display_name(user: Optional[UserModel]) -> str:
    """First + last name; anonymised / deleted users get a neutral label."""
    if user is None or bool(getattr(user, "is_deleted", False)):
        return DELETED_USER_LABEL
    name = f"{user.first_name or ''} {user.last_name or ''}".strip()
    return name or f"Benutzer #{user.id}"


def _context(row: ScanLogModel) -> Dict[str, Any]:
    ctx = row.context
    return ctx if isinstance(ctx, dict) else {}


def _ctx_int(row: Any, key: str) -> Optional[int]:
    value = _context(row).get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _ctx_str(row: ScanLogModel, key: str) -> Optional[str]:
    value = _context(row).get(key)
    return value if isinstance(value, str) and value else None


def to_piece_scan(row: Any, user: Optional[UserModel]) -> PieceScanRead:
    """Project one ``ScanLog`` row for the per-piece Scan-Verlauf (VIEWER ok).

    ``row`` is typed ``Any``: the legacy ``Column`` declarations type ORM
    attributes as ``Column[...]`` for mypy, not as their Python values.
    """
    return PieceScanRead(
        id=str(row.id),
        scanned_at=row.scanned_at,
        user_id=row.user_id,
        user_name=user_display_name(user),
        location=_ctx_str(row, "current_location"),
        location_id=_ctx_int(row, "location_id"),
        action_taken=row.action_taken,
        action_result=_ctx_str(row, "action_result"),
        input_source=_ctx_str(row, "input_source"),
        parent_scan_id=_ctx_str(row, "parent_scan_id"),
    )


def to_history_row(row: Any, user: Optional[UserModel]) -> ScanHistoryRow:
    """Project one row for the ADMIN/GOLDSMITH cross-piece search."""
    base = to_piece_scan(row, user).model_dump()
    return ScanHistoryRow(
        **base,
        raw_payload=row.raw_payload,
        resolved_type=row.resolved_type,
        resolved_id=row.resolved_id,
        resolution_path=row.resolution_path,
        device_id=_ctx_str(row, "device_id"),
    )


def _clamp_limit(limit: int) -> int:
    return max(1, min(limit, MAX_HISTORY_LIMIT))


def _next_offset(offset: int, limit: int, total: int) -> Optional[int]:
    following = offset + limit
    return following if following < total else None


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# --------------------------------------------------------------------------- #
# Queries
# --------------------------------------------------------------------------- #


def _joined(stmt_filter: Sequence[Any]) -> Select[Tuple[ScanLogModel, UserModel]]:
    return (
        select(ScanLogModel, UserModel)
        .outerjoin(UserModel, UserModel.id == ScanLogModel.user_id)
        .where(*stmt_filter)
    )


async def _page(
    db: AsyncSession,
    filters: Sequence[Any],
    limit: int,
    offset: int,
) -> Tuple[List[Tuple[ScanLogModel, Optional[UserModel]]], int]:
    """One page of (row, user) pairs, newest first, plus the total count."""
    total_stmt = select(func.count()).select_from(ScanLogModel).where(*filters)
    total = int((await db.execute(total_stmt)).scalar_one())
    stmt = (
        _joined(filters)
        .order_by(ScanLogModel.scanned_at.desc(), ScanLogModel.id.desc())
        .offset(offset)
        .limit(limit)
    )
    pairs = [(row, user) for row, user in (await db.execute(stmt)).all()]
    return pairs, total


def _piece_filters(entity_type: str, entity_id: int) -> List[Any]:
    return [
        ScanLogModel.resolved_type == entity_type,
        ScanLogModel.resolved_id == str(entity_id),
    ]


async def _resolve_query(db: AsyncSession, q: str) -> List[Any]:
    """Turn the search box text into scan_logs filters.

    ``ORDER:42`` → that piece; ``R-2026-0001`` (repair or bag number) → that
    repair; bare digits → any piece with that id; anything else → a
    substring match on the raw payload (unrecognised codes included).
    """
    text = q.strip()
    code = _CODE_RE.match(text)
    if code is not None:
        entity_type = _PREFIX_TO_TYPE.get(code.group(1).upper())
        if entity_type is not None:
            return _piece_filters(entity_type, int(code.group(2)))
    if _DIGITS_RE.match(text):
        return [ScanLogModel.resolved_id == text]
    repair_id = (
        await db.execute(
            select(RepairJobModel.id).where(
                or_(
                    RepairJobModel.repair_number == text,
                    RepairJobModel.bag_number == text,
                )
            )
        )
    ).scalar_one_or_none()
    if repair_id is not None:
        return _piece_filters("repair", int(repair_id))
    pattern = f"%{_escape_like(text)}%"
    return [ScanLogModel.raw_payload.ilike(pattern, escape="\\")]


class ScanHistoryService:
    """Read side of the scan tracking (per piece + admin search)."""

    @staticmethod
    async def list_piece_scans(
        db: AsyncSession,
        entity_type: str,
        entity_id: int,
        limit: int = DEFAULT_HISTORY_LIMIT,
        offset: int = 0,
    ) -> PieceScanPage:
        """Paged Scan-Verlauf of one order / repair, newest first."""
        capped = _clamp_limit(limit)
        pairs, total = await _page(
            db, _piece_filters(entity_type, entity_id), capped, offset
        )
        return PieceScanPage(
            items=[to_piece_scan(row, user) for row, user in pairs],
            total=total,
            limit=capped,
            offset=offset,
            next_offset=_next_offset(offset, capped, total),
        )

    @staticmethod
    async def last_scan(
        db: AsyncSession,
        entity_type: str,
        entity_id: int,
    ) -> Optional[LastScanRead]:
        """The newest scan row of a piece (scan or action), or None."""
        stmt = (
            _joined(_piece_filters(entity_type, entity_id))
            .order_by(ScanLogModel.scanned_at.desc(), ScanLogModel.id.desc())
            .limit(1)
        )
        found = (await db.execute(stmt)).first()
        if found is None:
            return None
        row, user = found
        return LastScanRead(
            scanned_at=row.scanned_at,
            user_id=row.user_id,
            user_name=user_display_name(user),
            location=_ctx_str(row, "current_location"),
            location_id=_ctx_int(row, "location_id"),
            action_taken=row.action_taken,
        )

    @staticmethod
    async def search(
        db: AsyncSession,
        filters: HistoryFilter,
        limit: int = DEFAULT_HISTORY_LIMIT,
        offset: int = 0,
    ) -> ScanHistoryPage:
        """Cross-piece, cross-user search (ADMIN/GOLDSMITH), newest first."""
        clauses: List[Any] = []
        if filters.q:
            clauses.extend(await _resolve_query(db, filters.q))
        if filters.user_id is not None:
            clauses.append(ScanLogModel.user_id == filters.user_id)
        if filters.date_from is not None:
            clauses.append(ScanLogModel.scanned_at >= filters.date_from)
        if filters.date_to is not None:
            clauses.append(ScanLogModel.scanned_at <= filters.date_to)
        capped = _clamp_limit(limit)
        pairs, total = await _page(db, clauses, capped, offset)
        return ScanHistoryPage(
            items=[to_history_row(row, user) for row, user in pairs],
            total=total,
            limit=capped,
            offset=offset,
            next_offset=_next_offset(offset, capped, total),
        )


async def publish_scan_event(row: ScanLogModel) -> None:
    """Publish a reduced ``scan_updates`` hint after the row is committed.

    Ids, action and time only — no user, location, payload or entity data;
    clients refetch the history through REST. Never fails the caller: the
    row is already durable.
    """
    payload = {
        "action": "scan_logged",
        "scan_id": str(row.id),
        "entity_type": row.resolved_type,
        "entity_id": row.resolved_id,
        "action_taken": row.action_taken,
        "scanned_at": row.scanned_at.isoformat() if row.scanned_at else None,
    }
    try:
        await pubsub.publish_event(SCAN_CHANNEL, json.dumps(payload))
    except Exception:
        logger.error(
            "Failed to publish scan_updates event",
            extra={"scan_id": str(row.id)},
            exc_info=True,
        )
