# src/goldsmith_erp/api/routers/locations.py
"""
Workshop locations (Standorte, W8).

GET    /locations?active=true      — picker list (every staff role)
GET    /admin/locations            — full list incl. deactivated (ADMIN)
POST   /admin/locations            — add a Standort (ADMIN)
PATCH  /admin/locations/{id}       — rename / kind / reorder / reactivate
DELETE /admin/locations/{id}       — deactivate (never deletes; history keeps it)

The admin routes are audited by the middleware (``admin/locations``
family, every verb). ``require_permission`` is an untyped decorator; the
``misc`` ignore keeps this module under strict mypy.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.api.deps import get_current_user
from goldsmith_erp.core.permissions import Permission, require_permission
from goldsmith_erp.db.models import User
from goldsmith_erp.db.session import get_db
from goldsmith_erp.models.location import LocationCreate, LocationRead, LocationUpdate
from goldsmith_erp.services.location_service import LocationService

router = APIRouter()


@router.get("/locations", response_model=list[LocationRead])
@require_permission(Permission.LOCATION_VIEW)  # type: ignore[misc]
async def list_locations(
    active: bool = Query(True, description="Nur aktive Standorte"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[LocationRead]:
    """Standorte für die Auswahlliste."""
    rows = await LocationService.list_locations(db, active_only=active)
    return [LocationRead.model_validate(r) for r in rows]


@router.get("/admin/locations", response_model=list[LocationRead])
@require_permission(Permission.LOCATION_MANAGE)  # type: ignore[misc]
async def admin_list_locations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[LocationRead]:
    """Alle Standorte inkl. deaktivierter (nur ADMIN)."""
    rows = await LocationService.list_locations(db, active_only=False)
    return [LocationRead.model_validate(r) for r in rows]


@router.post("/admin/locations", response_model=LocationRead, status_code=201)
@require_permission(Permission.LOCATION_MANAGE)  # type: ignore[misc]
async def create_location(
    payload: LocationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LocationRead:
    """Standort anlegen (nur ADMIN)."""
    return LocationRead.model_validate(await LocationService.create(db, payload))


@router.patch("/admin/locations/{location_id}", response_model=LocationRead)
@require_permission(Permission.LOCATION_MANAGE)  # type: ignore[misc]
async def update_location(
    location_id: int,
    payload: LocationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LocationRead:
    """Standort umbenennen, sortieren oder (re)aktivieren (nur ADMIN)."""
    location = await LocationService.update(db, location_id, payload)
    return LocationRead.model_validate(location)


@router.delete("/admin/locations/{location_id}", response_model=LocationRead)
@require_permission(Permission.LOCATION_MANAGE)  # type: ignore[misc]
async def deactivate_location(
    location_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> LocationRead:
    """Standort deaktivieren (nur ADMIN) — bleibt im Verlauf erhalten."""
    return LocationRead.model_validate(
        await LocationService.deactivate(db, location_id)
    )
