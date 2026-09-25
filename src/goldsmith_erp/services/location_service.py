# src/goldsmith_erp/services/location_service.py
"""Configurable workshop locations (Standorte).

ADMIN manages the list (create, rename, reorder, deactivate); every staff
member reads the active entries for the "Standort" dropdown. Time entries
and orders store both the FK (``location_id``) and the legacy name text
column for one release. ``resolve`` turns what a client sent into that
(id, name) pair so every write path keeps the two in sync.

Deactivating never deletes: history rows keep their FK and name, the
picker just stops offering the location.
"""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from goldsmith_erp.core.errors import (
    ConflictError,
    DomainValidationError,
    NotFoundError,
)
from goldsmith_erp.db.models import Order, TimeEntry, WorkshopLocation
from goldsmith_erp.models.location import LocationCreate, LocationUpdate

logger = logging.getLogger(__name__)

SORT_STEP = 10
DUPLICATE_MESSAGE = "Einen Standort mit diesem Namen gibt es bereits."
NOT_FOUND_MESSAGE = "Standort nicht gefunden."
INACTIVE_MESSAGE = "Dieser Standort ist deaktiviert."


class LocationService:
    """CRUD + write-path resolution for workshop locations."""

    @staticmethod
    async def list_locations(
        db: AsyncSession, *, active_only: bool = False
    ) -> list[WorkshopLocation]:
        stmt = select(WorkshopLocation).order_by(
            WorkshopLocation.sort_order, WorkshopLocation.name
        )
        if active_only:
            stmt = stmt.where(WorkshopLocation.is_active.is_(True))
        return list((await db.execute(stmt)).scalars().all())

    @staticmethod
    async def get(db: AsyncSession, location_id: int) -> WorkshopLocation:
        location = await db.get(WorkshopLocation, location_id)
        if location is None:
            raise NotFoundError(NOT_FOUND_MESSAGE, code="location.not_found")
        return location

    @staticmethod
    async def _find_by_name(
        db: AsyncSession, name: str, *, exclude_id: Optional[int] = None
    ) -> Optional[WorkshopLocation]:
        stmt = select(WorkshopLocation).where(
            func.lower(WorkshopLocation.name) == name.strip().lower()
        )
        if exclude_id is not None:
            stmt = stmt.where(WorkshopLocation.id != exclude_id)
        return (await db.execute(stmt)).scalars().first()

    @staticmethod
    async def _next_sort_order(db: AsyncSession) -> int:
        current = (
            await db.execute(select(func.max(WorkshopLocation.sort_order)))
        ).scalar()
        return int(current or 0) + SORT_STEP

    @staticmethod
    async def create(db: AsyncSession, data: LocationCreate) -> WorkshopLocation:
        if await LocationService._find_by_name(db, data.name):
            raise ConflictError(DUPLICATE_MESSAGE, code="location.duplicate")
        sort_order = (
            data.sort_order
            if data.sort_order is not None
            else await LocationService._next_sort_order(db)
        )
        location = WorkshopLocation(
            name=data.name,
            kind=data.kind.value,
            is_active=True,
            sort_order=sort_order,
        )
        db.add(location)
        await LocationService._commit_unique(db)
        await db.refresh(location)
        logger.info("Workshop location created", extra={"location_id": location.id})
        return location

    @staticmethod
    async def update(
        db: AsyncSession, location_id: int, data: LocationUpdate
    ) -> WorkshopLocation:
        location = await LocationService.get(db, location_id)
        changes = data.model_dump(exclude_unset=True, exclude_none=True)
        new_name: Optional[str] = changes.get("name")
        renamed = new_name is not None and new_name != location.name
        if (
            new_name is not None
            and renamed
            and await LocationService._find_by_name(
                db, new_name, exclude_id=location_id
            )
        ):
            raise ConflictError(DUPLICATE_MESSAGE, code="location.duplicate")
        if "kind" in changes:
            changes["kind"] = changes["kind"].value
        for field, value in changes.items():
            setattr(location, field, value)
        if new_name is not None and renamed:
            await LocationService._sync_names(db, location_id, new_name)
        await LocationService._commit_unique(db)
        await db.refresh(location)
        logger.info(
            "Workshop location updated",
            extra={"location_id": location_id, "fields": sorted(changes)},
        )
        return location

    @staticmethod
    async def deactivate(db: AsyncSession, location_id: int) -> WorkshopLocation:
        location = await LocationService.get(db, location_id)
        location.is_active = False  # type: ignore[assignment]
        await db.commit()
        await db.refresh(location)
        logger.info("Workshop location deactivated", extra={"location_id": location_id})
        return location

    @staticmethod
    async def _sync_names(db: AsyncSession, location_id: int, name: str) -> None:
        """Keep the legacy text columns equal to the renamed location."""
        await db.execute(
            update(TimeEntry)
            .where(TimeEntry.location_id == location_id)
            .values(location=name)
        )
        await db.execute(
            update(Order)
            .where(Order.location_id == location_id)
            .values(current_location=name)
        )

    @staticmethod
    async def _commit_unique(db: AsyncSession) -> None:
        try:
            await db.commit()
        except IntegrityError as exc:
            await db.rollback()
            raise ConflictError(DUPLICATE_MESSAGE, code="location.duplicate") from exc

    @staticmethod
    async def resolve(
        db: AsyncSession,
        location_id: Optional[int],
        location_name: Optional[str],
        *,
        keep_id: Optional[int] = None,
    ) -> tuple[Optional[int], Optional[str]]:
        """Map a client's ``location_id`` / legacy ``location`` text to (id, name).

        * ``location_id`` wins: it must exist and be active (422 otherwise);
          ``keep_id`` (the row's current location) may stay even when it
          was deactivated, so editing old history does not fail.
        * Only a name: linked to the matching location if there is one,
          otherwise stored as plain text (legacy clients, scanner labels).
        * Neither: ``(None, None)``.
        """
        if location_id is not None:
            location = await db.get(WorkshopLocation, location_id)
            if location is None:
                raise DomainValidationError(
                    NOT_FOUND_MESSAGE, code="location.not_found"
                )
            if not location.is_active and location.id != keep_id:
                raise DomainValidationError(INACTIVE_MESSAGE, code="location.inactive")
            return int(location.id), str(location.name)
        if location_name is None or not location_name.strip():
            return None, None
        match = await LocationService._find_by_name(db, location_name)
        if match is not None:
            return int(match.id), str(match.name)
        return None, location_name.strip()
