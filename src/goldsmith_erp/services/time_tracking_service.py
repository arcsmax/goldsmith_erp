from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update, delete, and_, func
from sqlalchemy.orm import selectinload
from typing import List, Optional, Dict, Any
from datetime import datetime
import uuid

from goldsmith_erp.db.models import (
    TimeEntry as TimeEntryModel,
    Activity as ActivityModel,
    Order as OrderModel,
    User as UserModel,
    Interruption as InterruptionModel,
)
from goldsmith_erp.models.time_entry import (
    TimeEntryCreate,
    TimeEntryUpdate,
    TimeEntryStart,
    TimeEntryStop,
)
from goldsmith_erp.models.interruption import InterruptionCreate
from goldsmith_erp.services.activity_service import ActivityService


class TimeTrackingService:
    @staticmethod
    async def start_time_entry(
        db: AsyncSession, entry_in: TimeEntryStart
    ) -> TimeEntryModel:
        """
        Startet eine neue Zeiterfassung für einen Auftrag.

        Args:
            db: Database session
            entry_in: TimeEntryStart schema mit order_id, activity_id, user_id

        Returns:
            Created TimeEntry
        """
        # Prüfe ob bereits eine laufende Entry für diesen User existiert
        running_entry = await TimeTrackingService.get_running_entry(db, entry_in.user_id)
        if running_entry:
            raise ValueError(
                f"User hat bereits eine laufende Zeiterfassung (ID: {running_entry.id}). "
                "Bitte zuerst stoppen."
            )

        # Erstelle neue TimeEntry
        db_entry = TimeEntryModel(
            id=str(uuid.uuid4()),
            order_id=entry_in.order_id,
            user_id=entry_in.user_id,
            activity_id=entry_in.activity_id,
            start_time=datetime.utcnow(),
            location=entry_in.location,
            extra_metadata=entry_in.extra_metadata or {},
            created_at=datetime.utcnow(),
        )

        db.add(db_entry)
        await db.commit()
        await db.refresh(db_entry)

        # Increment activity usage counter
        await ActivityService.increment_usage(db, entry_in.activity_id)

        return db_entry

    @staticmethod
    async def stop_time_entry(
        db: AsyncSession, entry_id: str, stop_data: TimeEntryStop
    ) -> Optional[TimeEntryModel]:
        """
        Stoppt eine laufende Zeiterfassung und fügt Bewertungen hinzu.

        Args:
            db: Database session
            entry_id: UUID der TimeEntry
            stop_data: TimeEntryStop schema mit ratings und notes

        Returns:
            Updated TimeEntry or None
        """
        entry = await TimeTrackingService.get_time_entry(db, entry_id)
        if not entry:
            return None

        if entry.end_time is not None:
            raise ValueError("Diese Zeiterfassung wurde bereits gestoppt")

        # Berechne Dauer
        end_time = datetime.utcnow()
        duration = int((end_time - entry.start_time).total_seconds() / 60)

        # Update Entry
        await db.execute(
            update(TimeEntryModel)
            .where(TimeEntryModel.id == entry_id)
            .values(
                end_time=end_time,
                duration_minutes=duration,
                complexity_rating=stop_data.complexity_rating,
                quality_rating=stop_data.quality_rating,
                rework_required=stop_data.rework_required,
                notes=stop_data.notes,
            )
        )
        await db.commit()

        # Update activity average duration
        await ActivityService.update_average_duration(db, entry.activity_id, float(duration))

        return await TimeTrackingService.get_time_entry(db, entry_id)

    @staticmethod
    async def get_time_entry(db: AsyncSession, entry_id: str) -> Optional[TimeEntryModel]:
        """Holt eine einzelne TimeEntry über ihre ID."""
        result = await db.execute(
            select(TimeEntryModel)
            .options(
                selectinload(TimeEntryModel.activity),
                selectinload(TimeEntryModel.order),
                selectinload(TimeEntryModel.user),
                selectinload(TimeEntryModel.interruptions),
                selectinload(TimeEntryModel.photos),  # FIXED: Added photos
            )
            .filter(TimeEntryModel.id == entry_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_running_entry(
        db: AsyncSession, user_id: int
    ) -> Optional[TimeEntryModel]:
        """Holt die aktuell laufende TimeEntry für einen User (end_time = NULL)."""
        result = await db.execute(
            select(TimeEntryModel)
            .options(
                selectinload(TimeEntryModel.activity),
                selectinload(TimeEntryModel.order),
                selectinload(TimeEntryModel.user),  # FIXED: Added user
                selectinload(TimeEntryModel.interruptions),  # FIXED: Added interruptions
                selectinload(TimeEntryModel.photos),  # FIXED: Added photos
            )
            .filter(
                and_(
                    TimeEntryModel.user_id == user_id,
                    TimeEntryModel.end_time.is_(None)
                )
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_time_entries_for_order(
        db: AsyncSession, order_id: int, skip: int = 0, limit: int = 100
    ) -> List[TimeEntryModel]:
        """Holt alle Zeiterfassungen für einen bestimmten Auftrag."""
        result = await db.execute(
            select(TimeEntryModel)
            .options(
                selectinload(TimeEntryModel.activity),
                selectinload(TimeEntryModel.user),
                selectinload(TimeEntryModel.order),  # FIXED: Added order
                selectinload(TimeEntryModel.interruptions),  # FIXED: Added interruptions
                selectinload(TimeEntryModel.photos),  # FIXED: Added photos
            )
            .filter(TimeEntryModel.order_id == order_id)
            .order_by(TimeEntryModel.start_time.desc())
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()

    @staticmethod
    async def get_time_entries_for_user(
        db: AsyncSession,
        user_id: int,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[TimeEntryModel]:
        """Holt alle Zeiterfassungen für einen User, optional gefiltert nach Datum."""
        query = select(TimeEntryModel).options(
            selectinload(TimeEntryModel.activity),
            selectinload(TimeEntryModel.order),
            selectinload(TimeEntryModel.user),  # FIXED: Added user
            selectinload(TimeEntryModel.interruptions),  # FIXED: Added interruptions
            selectinload(TimeEntryModel.photos),  # FIXED: Added photos
        ).filter(TimeEntryModel.user_id == user_id)

        if start_date:
            query = query.filter(TimeEntryModel.start_time >= start_date)
        if end_date:
            query = query.filter(TimeEntryModel.start_time <= end_date)

        query = query.order_by(TimeEntryModel.start_time.desc()).offset(skip).limit(limit)

        result = await db.execute(query)
        return result.scalars().all()

    @staticmethod
    async def create_time_entry(
        db: AsyncSession, entry_in: TimeEntryCreate
    ) -> TimeEntryModel:
        """Erstellt eine manuelle TimeEntry (mit Start & End Zeit)."""
        entry_data = entry_in.model_dump(exclude={"duration_minutes"})

        # Berechne Dauer falls nicht angegeben
        duration = entry_in.duration_minutes
        if not duration and entry_in.end_time:
            duration = int((entry_in.end_time - entry_in.start_time).total_seconds() / 60)

        db_entry = TimeEntryModel(
            id=str(uuid.uuid4()),
            **entry_data,
            duration_minutes=duration,
            created_at=datetime.utcnow(),
        )

        db.add(db_entry)
        await db.commit()
        await db.refresh(db_entry)

        # Increment activity usage
        await ActivityService.increment_usage(db, entry_in.activity_id)

        # Update average duration if entry is completed
        if duration:
            await ActivityService.update_average_duration(db, entry_in.activity_id, float(duration))

        return db_entry

    @staticmethod
    async def update_time_entry(
        db: AsyncSession, entry_id: str, entry_in: TimeEntryUpdate
    ) -> Optional[TimeEntryModel]:
        """Aktualisiert eine bestehende TimeEntry."""
        entry = await TimeTrackingService.get_time_entry(db, entry_id)
        if not entry:
            return None

        update_data = entry_in.model_dump(exclude_unset=True)

        # Berechne Dauer neu falls end_time geändert wurde
        if "end_time" in update_data and update_data["end_time"] and entry.start_time:
            duration = int((update_data["end_time"] - entry.start_time).total_seconds() / 60)
            update_data["duration_minutes"] = duration

        await db.execute(
            update(TimeEntryModel)
            .where(TimeEntryModel.id == entry_id)
            .values(**update_data)
        )
        await db.commit()

        return await TimeTrackingService.get_time_entry(db, entry_id)

    @staticmethod
    async def delete_time_entry(db: AsyncSession, entry_id: str) -> Dict[str, Any]:
        """Löscht eine TimeEntry."""
        entry = await TimeTrackingService.get_time_entry(db, entry_id)
        if not entry:
            return {"success": False, "message": "Time entry not found"}

        await db.execute(
            delete(TimeEntryModel).where(TimeEntryModel.id == entry_id)
        )
        await db.commit()

        return {"success": True}

    @staticmethod
    async def add_interruption(
        db: AsyncSession, interruption_in: InterruptionCreate
    ) -> InterruptionModel:
        """Fügt eine Unterbrechung zu einer laufenden TimeEntry hinzu."""
        # Prüfe ob TimeEntry existiert
        entry = await TimeTrackingService.get_time_entry(db, interruption_in.time_entry_id)
        if not entry:
            raise ValueError("Time entry not found")

        db_interruption = InterruptionModel(
            time_entry_id=interruption_in.time_entry_id,
            reason=interruption_in.reason,
            duration_minutes=interruption_in.duration_minutes,
            timestamp=datetime.utcnow(),
        )

        db.add(db_interruption)
        await db.commit()
        await db.refresh(db_interruption)

        return db_interruption

    @staticmethod
    async def get_total_time_for_order(db: AsyncSession, order_id: int) -> Dict[str, Any]:
        """Berechnet die Gesamtzeit für einen Auftrag."""
        result = await db.execute(
            select(
                func.sum(TimeEntryModel.duration_minutes).label("total_minutes"),
                func.count(TimeEntryModel.id).label("entry_count"),
            )
            .filter(
                and_(
                    TimeEntryModel.order_id == order_id,
                    TimeEntryModel.end_time.isnot(None),  # Nur abgeschlossene Einträge
                )
            )
        )

        row = result.first()
        total_minutes = row.total_minutes or 0
        entry_count = row.entry_count or 0

        return {
            "order_id": order_id,
            "total_minutes": total_minutes,
            "total_hours": round(total_minutes / 60, 2),
            "entry_count": entry_count,
        }
