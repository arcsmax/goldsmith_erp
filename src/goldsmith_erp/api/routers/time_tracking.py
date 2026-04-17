# src/goldsmith_erp/api/routers/time_tracking.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import datetime

from goldsmith_erp.api.deps import get_current_user
from goldsmith_erp.core.idempotency import (
    IdempotencyContext,
    get_idempotency_context,
)
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
from goldsmith_erp.models.scanner import (
    LogInterruptionRequest,
    PatchActivityRequest,
    SwitchTimerRequest,
)
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


# ==================================================================
# Slice 5 — scan-aware extensions
# ==================================================================


@router.patch("/{entry_id}/activity", response_model=TimeEntryRead)
@require_permission(Permission.TIME_TRACK)
async def patch_activity(
    entry_id: str,
    body: PatchActivityRequest,
    idem: IdempotencyContext = Depends(get_idempotency_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mid-session activity switch for a scan-driven ``ACTIVITY:<code>`` event.

    Mutates the existing time entry in place — does NOT create a new row
    (Lena §1 resolution). Per-user scope enforced at service layer:
    a user can only patch their own entries. Slice 2 idempotency headers
    are accepted for forward-compat but not yet used server-side.
    """
    del idem  # transport-level idempotency only; V1.1.5 will consume
    return await TimeTrackingService.patch_activity(
        db=db,
        entry_id=entry_id,
        activity_id=body.activity_id,
        user=current_user,
        origin="scan",
    )


@router.post("/{entry_id}/switch", response_model=TimeEntryRead)
@require_permission(Permission.TIME_TRACK)
async def switch_timer_endpoint(
    entry_id: str,
    body: SwitchTimerRequest,
    idem: IdempotencyContext = Depends(get_idempotency_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> TimeEntryRead:
    """Atomically switch the active timer from ``entry_id`` to a new order.

    Delegates to :func:`TimeTrackingService.switch_timer`, which enforces:

      * Per-user scope (A5.1) — the old entry must belong to
        ``current_user`` or the service raises ``CrossUserTimerError``
        (403) before any DB write.
      * Stale-timer guard (A5.2) — if the outgoing timer has been
        running past the 20-minute threshold without an interruption,
        the service raises ``TimerPossiblyStaleError`` (409) with
        ``detail.code == "TIMER_POSSIBLY_STALE"`` so the frontend can
        render the Mittagspause modal (A11.5).
      * Atomicity — stop-old + start-new land in one transaction and
        publish a single pubsub event on ``time_tracking_updates``.

    H18 rationale: Slice 5 built the service method but never exposed
    an HTTP endpoint, so the V1.1 frontend had to emulate a switch via
    stop+start. On network failure between the two calls the user ended
    up with no running timer (dangling state), and the 409 stale-timer
    envelope never surfaced because the stop endpoint returns 400/404
    for its own reasons. This endpoint closes the atomicity gap.

    ``origin='scan'`` is hard-coded because V1.1's only consumer is the
    scan-triggered flow in ``ActionHandlers.switch_timer``. When a
    manual-UI switch becomes a feature (V1.2+), a distinct endpoint or
    an ``origin`` field in the body will carry ``origin='manual'`` —
    we do NOT want the client to self-declare the origin on the current
    surface because that would undermine the §14.a adoption metric.

    Transport-level idempotency headers (``Idempotency-Key``,
    ``X-Client-Created-At``) are accepted and forwarded for V1.1.5's
    server-side dedupe. In V1.1 they are validated but not consumed
    server-side beyond the header-format check (see
    ``core.idempotency``).
    """
    return await TimeTrackingService.switch_timer(
        db=db,
        user=current_user,
        old_entry_id=entry_id,
        new_order_id=body.new_order_id,
        activity_id=body.activity_id,
        origin="scan",
        idempotency_key=idem.key,
        location=body.location,
    )


@router.post(
    "/{entry_id}/interruption",
    response_model=InterruptionRead,
    status_code=201,
)
@require_permission(Permission.TIME_TRACK)
async def log_interruption_endpoint(
    entry_id: str,
    body: LogInterruptionRequest,
    idem: IdempotencyContext = Depends(get_idempotency_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Log an interruption event WITHOUT stopping the timer (A5 / Slice 5).

    Singular route name (``/interruption``) distinguishes the scan-path
    from the legacy plural ``/interruptions`` endpoint which preserves
    the historical ``InterruptionCreate`` contract.
    """
    del idem
    return await TimeTrackingService.log_interruption(
        db=db,
        entry_id=entry_id,
        interrupt_code=body.interrupt_code,
        user=current_user,
        notes=body.notes,
        duration_minutes=body.duration_minutes,
        origin="scan",
    )
