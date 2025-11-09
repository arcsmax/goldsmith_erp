# src/goldsmith_erp/api/routers/activities.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional

from goldsmith_erp.api.deps import get_current_user
from goldsmith_erp.db.session import get_db
from goldsmith_erp.db.models import User
from goldsmith_erp.models.activity import ActivityCreate, ActivityRead, ActivityUpdate
from goldsmith_erp.services.activity_service import ActivityService

router = APIRouter()


@router.get("/", response_model=List[ActivityRead])
async def list_activities(
    category: Optional[str] = Query(None, description="Filter by category: fabrication, administration, waiting"),
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
    """
    return await ActivityService.get_activities(
        db, category=category, sort_by_usage=sort_by_usage, skip=skip, limit=limit
    )


@router.get("/most-used", response_model=List[ActivityRead])
async def get_most_used_activities(
    limit: int = Query(10, description="Number of activities to return"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Holt die am häufigsten genutzten Aktivitäten für Quick-Actions."""
    return await ActivityService.get_most_used_activities(db, limit=limit)


@router.post("/", response_model=ActivityRead)
async def create_activity(
    activity_in: ActivityCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Erstellt eine neue Custom Activity."""
    # Set created_by to current user if not specified
    if activity_in.created_by is None:
        activity_in.created_by = current_user.id

    return await ActivityService.create_activity(db, activity_in)


@router.get("/{activity_id}", response_model=ActivityRead)
async def get_activity(
    activity_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Einzelne Aktivität abrufen."""
    activity = await ActivityService.get_activity(db, activity_id)
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    return activity


@router.put("/{activity_id}", response_model=ActivityRead)
async def update_activity(
    activity_id: int,
    activity_in: ActivityUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Aktivität aktualisieren."""
    activity = await ActivityService.update_activity(db, activity_id, activity_in)
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    return activity


@router.delete("/{activity_id}")
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
