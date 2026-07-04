# src/goldsmith_erp/api/routers/activities.py
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.api.deps import get_current_user
from goldsmith_erp.core.permissions import Permission, require_permission
from goldsmith_erp.db.models import User, UserRole
from goldsmith_erp.db.session import get_db
from goldsmith_erp.models.activity import ActivityCreate, ActivityRead, ActivityUpdate
from goldsmith_erp.services.activity_service import ActivityService

router = APIRouter()


# --------------------------------------------------------------------------- #
# Financial-data content projection — mirrors the SCAN_READ pattern in
# core/permissions.py + services/scanner_service.py: ACTIVITY_VIEW is granted
# to VIEWER too (it also gates non-financial fields like name/category/icon),
# so the router — not the permission check — is responsible for withholding
# ``hourly_rate`` (labor pricing) from roles other than ADMIN/GOLDSMITH, per
# CLAUDE.md's financial-data rule. Same role predicate used throughout
# scanner_service.py's ORDER/REPAIR/METAL/MATERIAL_FIELDS_BY_ROLE projections.
# --------------------------------------------------------------------------- #


def _is_financial_role(user: User) -> bool:
    """True if ``user`` may see pricing/labor-rate fields (ADMIN or GOLDSMITH)."""
    return user.role in (UserRole.ADMIN, UserRole.GOLDSMITH)


def _project_activity(activity: ActivityRead, current_user: User) -> ActivityRead:
    """Return an ``ActivityRead`` with ``hourly_rate`` withheld for non-financial
    roles. Never mutates ``activity`` — returns the original for financial
    roles, or a copy with ``hourly_rate=None`` otherwise."""
    if _is_financial_role(current_user):
        return activity
    return activity.model_copy(update={"hourly_rate": None})


@router.get("/", response_model=List[ActivityRead])
@require_permission(Permission.ACTIVITY_VIEW)
async def list_activities(
    category: Optional[str] = Query(
        None, description="Filter by category: fabrication, administration, waiting"
    ),
    sort_by_usage: bool = Query(False, description="Sort by most used"),
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Liste aller Aktivitäten.

    - **category**: Optional filter (fabrication, administration, waiting)
    - **sort_by_usage**: Sortierung nach Nutzungshäufigkeit

    ``hourly_rate`` is projected out for roles other than ADMIN/GOLDSMITH —
    it is financial data (labor pricing) per CLAUDE.md.
    """
    activities = await ActivityService.get_activities(
        db, category=category, sort_by_usage=sort_by_usage, skip=skip, limit=limit
    )
    return [
        _project_activity(ActivityRead.model_validate(activity), current_user)
        for activity in activities
    ]


@router.get("/most-used", response_model=List[ActivityRead])
@require_permission(Permission.ACTIVITY_VIEW)
async def get_most_used_activities(
    limit: int = Query(10, description="Number of activities to return"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Holt die am häufigsten genutzten Aktivitäten für Quick-Actions.

    ``hourly_rate`` is projected out for roles other than ADMIN/GOLDSMITH —
    it is financial data (labor pricing) per CLAUDE.md. ``ACTIVITY_VIEW`` is
    granted to VIEWER too, same as ``list_activities``/``get_activity``, so
    this endpoint needs the same projection.
    """
    activities = await ActivityService.get_most_used_activities(db, limit=limit)
    return [
        _project_activity(ActivityRead.model_validate(activity), current_user)
        for activity in activities
    ]


@router.post("/", response_model=ActivityRead)
@require_permission(Permission.ACTIVITY_CREATE)
async def create_activity(
    activity_in: ActivityCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Erstellt eine neue Custom Activity.

    Not currently reachable by VIEWER (``ACTIVITY_CREATE`` is ADMIN/GOLDSMITH
    only), but projected for defense-in-depth/consistency with the other
    ``ActivityRead``-returning endpoints — the financial-data rule must not
    depend on the permission table staying exactly as-is.
    """
    # Set created_by to current user if not specified
    if activity_in.created_by is None:
        activity_in.created_by = current_user.id

    activity = await ActivityService.create_activity(db, activity_in)
    return _project_activity(ActivityRead.model_validate(activity), current_user)


@router.get("/{activity_id}", response_model=ActivityRead)
@require_permission(Permission.ACTIVITY_VIEW)
async def get_activity(
    activity_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Einzelne Aktivität abrufen.

    ``hourly_rate`` is projected out for roles other than ADMIN/GOLDSMITH —
    it is financial data (labor pricing) per CLAUDE.md.
    """
    activity = await ActivityService.get_activity(db, activity_id)
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    return _project_activity(ActivityRead.model_validate(activity), current_user)


@router.put("/{activity_id}", response_model=ActivityRead)
@require_permission(Permission.ACTIVITY_EDIT)
async def update_activity(
    activity_id: int,
    activity_in: ActivityUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Aktivität aktualisieren.

    Not currently reachable by VIEWER (``ACTIVITY_EDIT`` is ADMIN-only), but
    projected for defense-in-depth/consistency with the other
    ``ActivityRead``-returning endpoints.
    """
    activity = await ActivityService.update_activity(db, activity_id, activity_in)
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    return _project_activity(ActivityRead.model_validate(activity), current_user)


@router.delete("/{activity_id}")
@require_permission(Permission.ACTIVITY_DELETE)
async def delete_activity(
    activity_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Löscht eine Custom Activity.
    Standard-Aktivitäten können nicht gelöscht werden.
    """
    result = await ActivityService.delete_activity(db, activity_id)
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["message"])
    return result
