# src/goldsmith_erp/api/routers/notifications.py
"""
Notification API endpoints.

All endpoints are scoped to the authenticated user's own notifications —
a user can never read another user's notifications through this router.

Routes:
  GET  /api/v1/notifications                   — list notifications (own)
  GET  /api/v1/notifications/unread-count      — badge count
  PUT  /api/v1/notifications/{id}/read         — mark one as read
  PUT  /api/v1/notifications/read-all          — mark all as read
  POST /api/v1/notifications/check-deadlines   — trigger deadline scan (ADMIN)
  POST /api/v1/notifications/check-low-stock   — trigger stock scan (ADMIN)
"""

from typing import Any, Dict, List, Sequence, Union

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.api.deps import get_current_user
from goldsmith_erp.core.permissions import Permission, require_permission
from goldsmith_erp.db.models import User
from goldsmith_erp.db.session import get_db
from goldsmith_erp.models.notification import NotificationRead, UnreadCountResponse
from goldsmith_erp.models.pagination import (
    Page,
    PageParams,
    legacy_list_response,
    make_page_params,
    page_response,
)
from goldsmith_erp.services import list_queries
from goldsmith_erp.services.notification_service import NotificationService

router = APIRouter()


@router.get(
    "/",
    # W3-08: Page[...] when ``offset`` is sent, the legacy list otherwise.
    response_model=Union[Page[NotificationRead], List[NotificationRead]],
)
@require_permission(Permission.NOTIFICATION_VIEW)
async def list_notifications(
    unread_only: bool = Query(
        False, description="When true, return only unread notifications"
    ),
    page: PageParams = Depends(
        make_page_params(legacy_default_limit=50, legacy_max_limit=200)
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JSONResponse:
    """
    Return the authenticated user's notifications, newest first.

    Use ``unread_only=true`` to fetch only unread items (e.g. for notification panel).
    With ``offset``: a ``Page``; without it (deprecated): the legacy list with
    ``X-Deprecated-List: true`` (legacy mode ignores ``skip``, as before).
    """
    if page.is_paged:
        stmt = list_queries.notifications_statement(
            user_id=current_user.id, unread_only=unread_only
        )
        result = await list_queries.fetch_page(db, stmt, page)
        return page_response(_notification_rows(result.items), result.total, page)
    notifications = await NotificationService.get_notifications(
        db=db,
        user_id=current_user.id,
        unread_only=unread_only,
        limit=page.limit,
    )
    return legacy_list_response(_notification_rows(notifications))


def _notification_rows(rows: Sequence[Any]) -> List[Dict[str, Any]]:
    return [NotificationRead.model_validate(n).model_dump() for n in rows]


@router.get("/unread-count", response_model=UnreadCountResponse)
@require_permission(Permission.NOTIFICATION_VIEW)
async def get_unread_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UnreadCountResponse:
    """
    Return the number of unread notifications for the notification badge.

    Clients should poll this endpoint on focus or subscribe via WebSocket
    to ``notifications:{user_id}`` for real-time updates.
    """
    count = await NotificationService.get_unread_count(db=db, user_id=current_user.id)
    return UnreadCountResponse(unread_count=count)


@router.put("/{notification_id}/read", response_model=NotificationRead)
@require_permission(Permission.NOTIFICATION_VIEW)
async def mark_notification_read(
    notification_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> NotificationRead:
    """
    Mark a single notification as read.

    Returns 404 if the notification does not exist or belongs to another user.
    """
    notification = await NotificationService.mark_as_read(
        db=db,
        notification_id=notification_id,
        user_id=current_user.id,
    )
    if notification is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Benachrichtigung nicht gefunden.",
        )
    return notification  # type: ignore[return-value]


@router.put("/read-all", response_model=dict)
@require_permission(Permission.NOTIFICATION_VIEW)
async def mark_all_notifications_read(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Mark all of the authenticated user's unread notifications as read.

    Returns the count of notifications that were updated.
    """
    count = await NotificationService.mark_all_read(db=db, user_id=current_user.id)
    return {"updated_count": count}


@router.post("/check-deadlines", response_model=dict)
@require_permission(Permission.NOTIFICATION_CHECK_DEADLINES)
async def trigger_deadline_check(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Manually trigger the deadline warning scan.

    Scans all open orders with deadlines in the next 4 days and creates
    per-user notifications for ADMIN and GOLDSMITH users.  Duplicate
    notifications for the same order on the same day are suppressed.

    Restricted to ADMIN role via NOTIFICATION_CHECK_DEADLINES permission.
    """
    created = await NotificationService.check_deadline_warnings(db=db)
    return {
        "message": f"Deadline-Scan abgeschlossen. {created} neue Benachrichtigungen erstellt.",
        "notifications_created": created,
    }


@router.post("/check-low-stock", response_model=dict)
@require_permission(Permission.NOTIFICATION_CHECK_DEADLINES)
async def trigger_low_stock_check(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    """
    Manually trigger the low-stock alert scan.

    Scans all materials below the stock threshold and notifies ADMIN users.
    Restricted to ADMIN role.
    """
    created = await NotificationService.check_low_stock_alerts(db=db)
    return {
        "message": f"Lagerbestand-Scan abgeschlossen. {created} neue Benachrichtigungen erstellt.",
        "notifications_created": created,
    }
