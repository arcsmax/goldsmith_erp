# src/goldsmith_erp/api/routers/admin_workshop.py
"""
Admin endpoints for the Werkstatt-Stammdaten (W2-04, DOM-24).

GET /admin/workshop-settings  — current seller data + §14 completeness check
PUT /admin/workshop-settings  — replace the seller data

ADMIN only (``Permission.WORKSHOP_SETTINGS_MANAGE``). Every request is
recorded by the audit middleware (``admin/workshop-settings`` family); the
service additionally logs which fields changed.

``require_permission`` is an untyped decorator (core/permissions.py); the
``misc`` ignore keeps this new module under strict mypy without a ledger
entry.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.api.deps import get_current_user
from goldsmith_erp.core.permissions import Permission, require_permission
from goldsmith_erp.db.models import User
from goldsmith_erp.db.session import get_db
from goldsmith_erp.models.workshop_settings import (
    WorkshopSettingsRead,
    WorkshopSettingsUpdate,
)
from goldsmith_erp.services.workshop_settings_service import WorkshopSettingsService

router = APIRouter()


@router.get("/admin/workshop-settings", response_model=WorkshopSettingsRead)
@require_permission(Permission.WORKSHOP_SETTINGS_MANAGE)  # type: ignore[misc]
async def get_workshop_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WorkshopSettingsRead:
    """Werkstatt-Stammdaten lesen (nur ADMIN)."""
    return await WorkshopSettingsService.read(db)


@router.put("/admin/workshop-settings", response_model=WorkshopSettingsRead)
@require_permission(Permission.WORKSHOP_SETTINGS_MANAGE)  # type: ignore[misc]
async def update_workshop_settings(
    payload: WorkshopSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WorkshopSettingsRead:
    """Werkstatt-Stammdaten speichern (nur ADMIN)."""
    return await WorkshopSettingsService.update(db, payload, current_user)
