# src/goldsmith_erp/api/routers/time_tracking.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import datetime

from goldsmith_erp.api.deps import get_current_user
from goldsmith_erp.db.session import get_db
from goldsmith_erp.db.models import User
from goldsmith_erp.models.time_entry import (
    TimeEntryCreate,
    TimeEntryRead,
    TimeEntryUpdate,
    TimeEntryStart,
    TimeEntryStop,
    TimeEntryWithDetails,
)
from goldsmith_erp.models.interruption import InterruptionCreate, InterruptionRead
from goldsmith_erp.services.time_tracking_service import TimeTrackingService
from goldsmith_erp.core.permissions import Permission, require_permission, check_ownership_or_permission

router = APIRouter()


@router.post("/start", response_model=TimeEntryRead)
@require_permission(Permission.TIME_TRACK)
async def start_time_tracking(
    entry_in: TimeEntryStart,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Startet eine neue Zeiterfassung.

    - Prüft ob bereits eine laufende Zeiterfassung für den User existiert
    - Erstellt neue TimeEntry mit start_time
    - Inkrementiert Activity usage_count
    """
    # Override user_id with current user
    entry_in.user_id = current_user.id

    try:
        return await TimeTrackingService.start_time_entry(db, entry_in)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{entry_id}/stop", response_model=TimeEntryRead)
@require_permission(Permission.TIME_TRACK)
async def stop_time_tracking(
    entry_id: str,
    stop_data: TimeEntryStop,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Stoppt eine laufende Zeiterfassung.

    - Setzt end_time und berechnet Dauer
    - Speichert Bewertungen (complexity, quality, rework)
    - Aktualisiert Activity average_duration
    """
    try:
        entry = await TimeTrackingService.stop_time_entry(db, entry_id, stop_data)
        if not entry:
            raise HTTPException(status_code=404, detail="Time entry not found")
        return entry
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/running", response_model=Optional[TimeEntryRead])
@require_permission(Permission.TIME_VIEW_OWN)
async def get_running_entry(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Holt die aktuell laufende Zeiterfassung für den aktuellen User."""
    return await TimeTrackingService.get_running_entry(db, current_user.id)


@router.get("/order/{order_id}", response_model=List[TimeEntryRead])
@require_permission(Permission.TIME_VIEW_ALL)
async def get_time_entries_for_order(
    order_id: int,
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Holt alle Zeiterfassungen für einen bestimmten Auftrag."""
    return await TimeTrackingService.get_time_entries_for_order(db, order_id, skip, limit)


@router.get("/order/{order_id}/total")
@require_permission(Permission.TIME_VIEW_ALL)
async def get_total_time_for_order(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Berechnet die Gesamtzeit für einen Auftrag."""
    return await TimeTrackingService.get_total_time_for_order(db, order_id)


@router.get("/user/{user_id}", response_model=List[TimeEntryRead])
async def get_time_entries_for_user(
    user_id: int,
    start_date: Optional[datetime] = Query(None, description="Filter by start date"),
    end_date: Optional[datetime] = Query(None, description="Filter by end date"),
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Holt alle Zeiterfassungen für einen User, optional gefiltert nach Datum."""
    # Check if user owns resource or has permission to view all time entries
    if not check_ownership_or_permission(user_id, current_user, Permission.TIME_VIEW_ALL):
        raise HTTPException(
            status_code=403,
            detail="Permission denied: You can only view your own time entries or need TIME_VIEW_ALL permission"
        )

    return await TimeTrackingService.get_time_entries_for_user(
        db, user_id, start_date, end_date, skip, limit
    )


@router.post("/", response_model=TimeEntryRead)
@require_permission(Permission.TIME_TRACK)
async def create_time_entry(
    entry_in: TimeEntryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Erstellt eine manuelle Zeiterfassung (mit Start & End Zeit)."""
    # Override user_id with current user
    entry_in.user_id = current_user.id

    return await TimeTrackingService.create_time_entry(db, entry_in)


@router.get("/{entry_id}", response_model=TimeEntryRead)
@require_permission(Permission.TIME_VIEW_ALL)
async def get_time_entry(
    entry_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Holt eine einzelne Zeiterfassung."""
    entry = await TimeTrackingService.get_time_entry(db, entry_id)
    if not entry:
        raise HTTPException(status_code=404, detail="Time entry not found")
    return entry


@router.put("/{entry_id}", response_model=TimeEntryRead)
@require_permission(Permission.TIME_EDIT)
async def update_time_entry(
    entry_id: str,
    entry_in: TimeEntryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Aktualisiert eine Zeiterfassung."""
    entry = await TimeTrackingService.update_time_entry(db, entry_id, entry_in)
    if not entry:
        raise HTTPException(status_code=404, detail="Time entry not found")
    return entry


@router.delete("/{entry_id}")
@require_permission(Permission.TIME_DELETE)
async def delete_time_entry(
    entry_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Löscht eine Zeiterfassung."""
    result = await TimeTrackingService.delete_time_entry(db, entry_id)
    if not result["success"]:
        raise HTTPException(status_code=404, detail=result["message"])
    return result


@router.post("/{entry_id}/interruptions", response_model=InterruptionRead)
@require_permission(Permission.TIME_TRACK)
async def add_interruption(
    entry_id: str,
    interruption_in: InterruptionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Fügt eine Unterbrechung zu einer Zeiterfassung hinzu."""
    # Override entry_id from path
    interruption_in.time_entry_id = entry_id

    try:
        return await TimeTrackingService.add_interruption(db, interruption_in)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
