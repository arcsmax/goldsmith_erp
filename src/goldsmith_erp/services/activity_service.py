from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update, delete, func
from typing import List, Optional, Dict, Any
from datetime import datetime

from goldsmith_erp.db.models import Activity as ActivityModel
from goldsmith_erp.models.activity import ActivityCreate, ActivityUpdate


class ActivityService:
    @staticmethod
    async def get_activities(
        db: AsyncSession,
        category: Optional[str] = None,
        sort_by_usage: bool = False,
        skip: int = 0,
        limit: int = 100
    ) -> List[ActivityModel]:
        """
        Holt alle Aktivitäten mit optionaler Filterung und Sortierung.

        Args:
            db: Database session
            category: Optional filter by category (fabrication, administration, waiting)
            sort_by_usage: Sort by usage_count descending (most used first)
            skip: Pagination offset
            limit: Max results
        """
        query = select(ActivityModel)

        # Filter by category
        if category:
            query = query.filter(ActivityModel.category == category)

        # Sort
        if sort_by_usage:
            query = query.order_by(ActivityModel.usage_count.desc())
        else:
            query = query.order_by(ActivityModel.category, ActivityModel.name)

        # Pagination
        query = query.offset(skip).limit(limit)

        result = await db.execute(query)
        return result.scalars().all()

    @staticmethod
    async def get_activity(db: AsyncSession, activity_id: int) -> Optional[ActivityModel]:
        """Holt eine einzelne Aktivität über ihre ID."""
        result = await db.execute(
            select(ActivityModel).filter(ActivityModel.id == activity_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create_activity(db: AsyncSession, activity_in: ActivityCreate) -> ActivityModel:
        """Erstellt eine neue Aktivität (Custom Activity)."""
        activity_data = activity_in.model_dump()
        db_activity = ActivityModel(
            **activity_data,
            usage_count=0,
            created_at=datetime.utcnow()
        )

        db.add(db_activity)
        await db.commit()
        await db.refresh(db_activity)

        return db_activity

    @staticmethod
    async def update_activity(
        db: AsyncSession, activity_id: int, activity_in: ActivityUpdate
    ) -> Optional[ActivityModel]:
        """Aktualisiert eine bestehende Aktivität."""
        # Prüfen ob Aktivität existiert
        activity = await ActivityService.get_activity(db, activity_id)
        if not activity:
            return None

        # Update durchführen
        update_data = activity_in.model_dump(exclude_unset=True)
        await db.execute(
            update(ActivityModel)
            .where(ActivityModel.id == activity_id)
            .values(**update_data)
        )
        await db.commit()

        # Aktualisiertes Objekt holen
        return await ActivityService.get_activity(db, activity_id)

    @staticmethod
    async def delete_activity(db: AsyncSession, activity_id: int) -> Dict[str, Any]:
        """Löscht eine Aktivität (nur Custom Activities)."""
        activity = await ActivityService.get_activity(db, activity_id)
        if not activity:
            return {"success": False, "message": "Activity not found"}

        # Nur Custom Activities können gelöscht werden
        if not activity.is_custom:
            return {"success": False, "message": "Cannot delete standard activity"}

        await db.execute(
            delete(ActivityModel).where(ActivityModel.id == activity_id)
        )
        await db.commit()

        return {"success": True}

    @staticmethod
    async def increment_usage(db: AsyncSession, activity_id: int) -> Optional[ActivityModel]:
        """
        Erhöht den usage_count und aktualisiert last_used.
        Wird automatisch beim Erstellen eines TimeEntry aufgerufen.
        """
        activity = await ActivityService.get_activity(db, activity_id)
        if not activity:
            return None

        await db.execute(
            update(ActivityModel)
            .where(ActivityModel.id == activity_id)
            .values(
                usage_count=ActivityModel.usage_count + 1,
                last_used=datetime.utcnow()
            )
        )
        await db.commit()

        return await ActivityService.get_activity(db, activity_id)

    @staticmethod
    async def update_average_duration(
        db: AsyncSession, activity_id: int, new_duration: float
    ) -> Optional[ActivityModel]:
        """
        Aktualisiert die durchschnittliche Dauer basierend auf neuen TimeEntries.
        Verwendet gleitenden Durchschnitt.
        """
        activity = await ActivityService.get_activity(db, activity_id)
        if not activity:
            return None

        # Gleitender Durchschnitt berechnen
        if activity.average_duration_minutes is None:
            new_avg = new_duration
        else:
            # Weighted average (neuere Einträge gewichten stärker)
            weight = min(activity.usage_count, 10)  # Max 10 für Stabilität
            new_avg = (activity.average_duration_minutes * weight + new_duration) / (weight + 1)

        await db.execute(
            update(ActivityModel)
            .where(ActivityModel.id == activity_id)
            .values(average_duration_minutes=new_avg)
        )
        await db.commit()

        return await ActivityService.get_activity(db, activity_id)

    @staticmethod
    async def get_most_used_activities(
        db: AsyncSession, limit: int = 10
    ) -> List[ActivityModel]:
        """Holt die am häufigsten genutzten Aktivitäten für Quick-Actions."""
        result = await db.execute(
            select(ActivityModel)
            .order_by(ActivityModel.usage_count.desc())
            .limit(limit)
        )
        return result.scalars().all()
