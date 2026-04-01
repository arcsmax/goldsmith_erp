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
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.api.deps import get_current_user
from goldsmith_erp.core.permissions import Permission, require_permission
from goldsmith_erp.db.models import User
from goldsmith_erp.db.session import get_db
from goldsmith_erp.models.notification import (
    NotificationRead,
    UnreadCountResponse,
)
from goldsmith_erp.services.notification_service import NotificationService

router = APIRouter()


@router.get("/", response_model=List[NotificationRead])
@require_permission(Permission.NOTIFICATION_VIEW)
async def list_notifications(
    unread_only: bool = Query(False, description="When true, return only unread notifications"),
    limit: int = Query(50, ge=1, le=200, description="Maximum number of notifications to return"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[NotificationRead]:
    """
    Return the authenticated user's notifications, newest first.

    Use ``unread_only=true`` to fetch only unread items (e.g. for notification panel).
    """
    return await NotificationService.get_notifications(
        db=db,
        user_id=current_user.id,
        unread_only=unread_only,
        limit=limit,
    )


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
    return {"updated": count}


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
