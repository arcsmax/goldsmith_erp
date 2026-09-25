# src/goldsmith_erp/api/routers/admin_outbox.py
"""
Admin view of the outbox ("Nachrichten-Warteschlange", ARCH-04 / ARCH-12).

GET  /admin/outbox?status=&limit=  — newest rows (optionally one status) plus
                                     per-status counts and the effective mode
POST /admin/outbox/{id}/retry      — a failed/dead row becomes pending with
                                     fresh attempts; the worker sends it

ADMIN only (``Permission.OUTBOX_MANAGE``). Every request is recorded by the
audit middleware (``admin/outbox`` family); the retry is also logged with
ids by the service. Responses carry ids and error codes only, never
recipient, subject or body.
"""

from __future__ import annotations

from typing import Literal, Optional, cast

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.api.deps import get_current_user
from goldsmith_erp.core.config import settings
from goldsmith_erp.core.permissions import Permission, require_permission
from goldsmith_erp.db.models import OutboxMessage, User
from goldsmith_erp.db.session import get_db
from goldsmith_erp.models.outbox import (
    OutboxCounts,
    OutboxListResponse,
    OutboxMessageRead,
    OutboxStatusLiteral,
)
from goldsmith_erp.services.outbox_service import (
    OutboxNotFoundError,
    OutboxNotRetryableError,
    OutboxService,
)

router = APIRouter()

DEFAULT_LIMIT = 100
MAX_LIMIT = 500


async def _counts(db: AsyncSession) -> OutboxCounts:
    rows = await db.execute(
        select(OutboxMessage.status, func.count()).group_by(OutboxMessage.status)
    )
    return OutboxCounts(**{str(s): int(n) for s, n in rows.all()})


@router.get("/admin/outbox", response_model=OutboxListResponse)
@require_permission(Permission.OUTBOX_MANAGE)  # type: ignore[misc]
async def list_outbox(
    status_filter: Optional[OutboxStatusLiteral] = Query(None, alias="status"),
    limit: int = Query(DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OutboxListResponse:
    """Nachrichten-Warteschlange anzeigen (nur ADMIN)."""
    rows = await OutboxService.list_messages(db, status=status_filter, limit=limit)
    return OutboxListResponse(
        items=[OutboxMessageRead.model_validate(r) for r in rows],
        counts=await _counts(db),
        mode=cast(Literal["inline", "worker"], settings.outbox_mode),
    )


@router.post("/admin/outbox/{message_id}/retry", response_model=OutboxMessageRead)
@require_permission(Permission.OUTBOX_MANAGE)  # type: ignore[misc]
async def retry_outbox_message(
    message_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OutboxMessageRead:
    """Fehlgeschlagene Nachricht erneut senden (nur ADMIN)."""
    try:
        msg = await OutboxService.retry(db, message_id)
    except OutboxNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Nachricht {message_id} nicht gefunden",
        )
    except OutboxNotRetryableError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Nur fehlgeschlagene oder aufgegebene Nachrichten können "
                "erneut gesendet werden."
            ),
        )
    return OutboxMessageRead.model_validate(msg)
