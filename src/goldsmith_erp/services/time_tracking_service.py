import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, case, delete, func, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from goldsmith_erp.core.errors import (
    ConflictError,
    DomainValidationError,
    ForbiddenError,
    NotFoundError,
)
from goldsmith_erp.core.timeutil import ensure_utc, utcnow
from goldsmith_erp.db.models import Activity as ActivityModel
from goldsmith_erp.db.models import Interruption as InterruptionModel
from goldsmith_erp.db.models import Order as OrderModel
from goldsmith_erp.db.models import TimeEntry as TimeEntryModel
from goldsmith_erp.db.models import User as UserModel
from goldsmith_erp.models.interruption import InterruptionCreate
from goldsmith_erp.models.time_entry import (
    RunningTimeEntryEdit,
    TimeEntryCreate,
    TimeEntryStart,
    TimeEntryStop,
    TimeEntryUpdate,
    TimeSummaryStats,
)
from goldsmith_erp.services import running_timer_edit
from goldsmith_erp.services.activity_service import ActivityService
from goldsmith_erp.services.location_service import LocationService

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Slice 5 — stale-timer threshold for A5.2 ``switch_timer`` guard.
#
# If the outgoing timer has been running for longer than this window AND the
# goldsmith never recorded an activity change or interruption during the
# window, we refuse the silent switch and surface a 409 so the client can
# render the "Mittagspause abziehen?" modal. 20 minutes matches Meister
# Thomas's workshop cadence — shorter would nag on every coffee break;
# longer would allow a full lunch hour to silently be booked on the wrong
# order.
# ---------------------------------------------------------------------------
STALE_TIMER_THRESHOLD = timedelta(minutes=20)


# ---------------------------------------------------------------------------
# W2-14 (BE-19) — interruption arithmetic.
#
# ``time_entries.duration_minutes`` stays the gross wall-clock span (every
# consumer — MLDataService, the labor corpus, the ML feature builder — nets
# interruptions out of it). A scan interruption starts as an open marker
# (``duration_minutes == 0``, ``resumed_at`` NULL); the next scan on the
# running timer (activity change, next interruption, switch, stop or an
# explicit resume) closes it with ``resumed_at`` and the measured minutes.
# ---------------------------------------------------------------------------


def _whole_minutes(span: timedelta) -> int:
    return max(int(span.total_seconds() // 60), 0)


def interruption_minutes(
    interruption: Any, entry_start: datetime, entry_end: Optional[datetime]
) -> int:
    """Minutes ``interruption`` takes out of the entry window.

    * resumed: the measured span, clamped to [entry_start, entry_end];
    * open marker on a stopped entry: from its start until entry_end;
    * otherwise (legacy / manual): the stored ``duration_minutes``.
    """
    started = interruption.timestamp or entry_start
    begin = max(started, entry_start)
    resumed = interruption.resumed_at
    if resumed is not None:
        end = min(resumed, entry_end) if entry_end is not None else resumed
        return _whole_minutes(end - begin)
    stored = int(interruption.duration_minutes or 0)
    if stored == 0 and entry_end is not None:
        return _whole_minutes(entry_end - begin)
    return max(stored, 0)


def net_entry_minutes(entry: Any) -> int:
    """Gross ``duration_minutes`` of a stopped entry minus its interruptions.

    ``entry.interruptions`` must be loaded (selectinload).
    """
    gross = int(entry.duration_minutes or 0)
    taken = sum(
        interruption_minutes(i, entry.start_time, entry.end_time)
        for i in entry.interruptions
    )
    return max(gross - taken, 0)


class TimerPossiblyStaleError(ConflictError):
    """Raised by ``switch_timer`` when the outgoing timer looks stale (A5.2).

    The 409 envelope carries a structured ``detail`` so the frontend can
    distinguish this from generic conflicts and render the Mittagspause
    modal with the three options (abziehen+wechseln / trotzdem wechseln /
    abbrechen). See ``V1.1-AMENDMENTS.md`` A5.2.
    """

    def __init__(self, *, old_entry_id: str, running_minutes: int) -> None:
        message = (
            f"Der Timer laeuft {running_minutes} min ohne Taetigkeits- "
            "oder Unterbrechungs-Eintrag. Mittagspause abziehen?"
        )
        super().__init__(
            message,
            code="time_entry.possibly_stale",
            extra={"old_entry_id": old_entry_id, "running_minutes": running_minutes},
            legacy_detail={
                "code": "TIMER_POSSIBLY_STALE",
                "old_entry_id": old_entry_id,
                "running_minutes": running_minutes,
                "message": message,
            },
        )


# BE-18 (W1-17): an edited entry may not be longer than one working day.
MAX_EDITED_DURATION = timedelta(hours=24)


class TimerAlreadyRunningError(ConflictError):
    """409 when the user already has a running timer (BE-12, W1-17).

    Raised by the pre-insert check and, for the lost race of two concurrent
    starts, when the partial unique index ``uq_time_entries_one_running``
    rejects the INSERT.
    """

    def __init__(self, running_entry_id: Optional[str] = None) -> None:
        suffix = f" (ID: {running_entry_id})" if running_entry_id else ""
        super().__init__(
            f"Es läuft bereits eine Zeiterfassung{suffix}. Bitte zuerst stoppen.",
            code="time_entry.already_running",
            extra={"running_entry_id": running_entry_id} if running_entry_id else None,
        )


class TimeEntryValidationError(ValueError):
    """An edit would store an impossible time entry (BE-18) -> 422."""


class CrossUserTimerError(ForbiddenError):
    """Raised by ``switch_timer`` when a caller tries to switch another user's timer (A5.1).

    This is a hard 403 — no modal, no retry. A scan from user A MUST NOT
    ever mutate user B's time-tracking state. Logged at WARNING level so
    repeated attempts can be observed.
    """

    def __init__(
        self, *, old_entry_id: str, caller_user_id: int, owner_user_id: int
    ) -> None:
        message = "Timer gehoert einem anderen Benutzer — Wechsel nicht erlaubt."
        super().__init__(
            message,
            code="time_entry.cross_user_forbidden",
            legacy_detail={"code": "CROSS_USER_TIMER_FORBIDDEN", "message": message},
        )
        # Surface details only to server-side logs; not echoed to the
        # client because enumerating owner IDs is information leakage.
        self.caller_user_id = caller_user_id
        self.owner_user_id = owner_user_id
        self.old_entry_id = old_entry_id


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
        running_entry = await TimeTrackingService.get_running_entry(
            db, entry_in.user_id
        )
        if running_entry:
            raise TimerAlreadyRunningError(running_entry.id)

        location_id, location_name = await LocationService.resolve(
            db, entry_in.location_id, entry_in.location
        )
        # Erstelle neue TimeEntry
        db_entry = TimeEntryModel(
            id=str(uuid.uuid4()),
            order_id=entry_in.order_id,
            user_id=entry_in.user_id,
            activity_id=entry_in.activity_id,
            start_time=datetime.now(timezone.utc),
            location=location_name,
            location_id=location_id,
            extra_metadata=entry_in.extra_metadata or {},
            created_at=datetime.now(timezone.utc),
        )

        db.add(db_entry)
        try:
            await db.commit()
        except IntegrityError as exc:
            # Lost race: a concurrent start committed first and the partial
            # unique index rejected this INSERT (BE-12).
            await db.rollback()
            logger.info(
                "Concurrent timer start rejected by uq_time_entries_one_running",
                extra={"user_id": entry_in.user_id},
            )
            raise TimerAlreadyRunningError() from exc
        await db.refresh(db_entry)

        # Increment activity usage counter
        await ActivityService.increment_usage(db, entry_in.activity_id)

        # W2-13: other devices of this user refresh their timer.
        await TimeTrackingService._publish_timer_hint(
            action="start",
            user_id=db_entry.user_id,
            entry_id=db_entry.id,
            order_id=db_entry.order_id,
            activity_id=db_entry.activity_id,
        )

        return db_entry

    @staticmethod
    async def stop_time_entry(
        db: AsyncSession,
        entry_id: str,
        stop_data: TimeEntryStop,
        end_time: Optional[datetime] = None,
    ) -> Optional[TimeEntryModel]:
        """
        Stoppt eine laufende Zeiterfassung und fügt Bewertungen hinzu.

        Args:
            db: Database session
            entry_id: UUID der TimeEntry
            stop_data: TimeEntryStop schema mit ratings und notes
            end_time: explicit end (correction of a forgotten timer via PUT,
                already validated by ``update_time_entry``); default now.

        Returns:
            Updated TimeEntry or None
        """
        entry = await TimeTrackingService.get_time_entry(db, entry_id)
        if not entry:
            return None

        if entry.end_time is not None:
            raise ValueError("Diese Zeiterfassung wurde bereits gestoppt")

        # Berechne Dauer
        # Naive input is read as UTC for one release (BE-15).
        end_time = ensure_utc(end_time) if end_time is not None else utcnow()
        duration = int((end_time - entry.start_time).total_seconds() / 60)

        # W2-14: an interruption still open at the stop ends with the entry.
        await TimeTrackingService._close_open_interruptions(db, entry_id, end_time)

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
        await ActivityService.update_average_duration(
            db, entry.activity_id, float(duration)
        )

        # Reload the entry with relationships for anomaly check and return value
        stopped_entry = await TimeTrackingService.get_time_entry(db, entry_id)

        # --- Anomaly detection (fire-and-forget, must not block the stop flow) ---
        await TimeTrackingService._check_and_publish_anomaly(
            db, stopped_entry, duration
        )

        # --- V1.2 cost watcher (post-commit, fire-and-forget) ---
        # Late import to avoid a module-load cycle; mirrors the anomaly
        # detection imports above. Must never block or fail the stop flow —
        # see CostWatchService.safe_check.
        from goldsmith_erp.services.cost_watch_service import (  # noqa: PLC0415
            CostWatchService,
        )

        order_id = stopped_entry.order_id if stopped_entry is not None else None
        await CostWatchService.safe_check(db, order_id)

        # W2-14: rework on a completed order updates its actual hours.
        await TimeTrackingService._recompute_actual_hours(db, entry.order_id)

        # W2-13: other devices of this user drop the running timer.
        await TimeTrackingService._publish_timer_hint(
            action="stop",
            user_id=entry.user_id,
            entry_id=entry_id,
            order_id=entry.order_id,
            activity_id=entry.activity_id,
        )

        return stopped_entry

    @staticmethod
    async def _publish_timer_hint(
        *,
        action: str,
        user_id: int,
        entry_id: str,
        order_id: Optional[int],
        activity_id: Optional[int],
    ) -> None:
        """Post-commit ``time_tracking_updates`` hint for start/stop.

        Never raises: the mutation is committed; a lost hint only means the
        other device refreshes on its next poll or reconnect.
        """
        from goldsmith_erp.core import pubsub  # noqa: PLC0415 (patched in tests)

        payload = {
            "action": action,
            "source": "manual",
            "user_id": user_id,
            "entry_id": entry_id,
            "order_id": order_id,
            "activity_id": activity_id,
        }
        try:
            published = await pubsub.publish_event(
                "time_tracking_updates", json.dumps(payload)
            )
        except Exception as exc:
            logger.error(
                "Timer hint publish raised",
                extra={"action": action, "entry_id": entry_id, "error": str(exc)},
                exc_info=True,
            )
            return
        if published is False:
            logger.warning(
                "Timer hint not delivered; other devices refresh on reconnect",
                extra={"action": action, "entry_id": entry_id, "user_id": user_id},
            )

    @staticmethod
    async def _check_and_publish_anomaly(
        db: AsyncSession,
        entry: Optional[TimeEntryModel],
        duration_minutes: int,
    ) -> None:
        """
        Check the just-stopped time entry for anomalous duration and publish
        a WebSocket event over Redis if an anomaly is detected.

        Failures are logged and swallowed so the stop flow is never disrupted.
        Database commit has already happened before this is called.
        """
        if entry is None:
            return

        try:
            from goldsmith_erp.core.pubsub import publish_event
            from goldsmith_erp.ml.anomaly_alerts import AnomalyAlert
            from goldsmith_erp.ml.anomaly_detection import AnomalyDetector

            detector = AnomalyDetector()
            result = await detector.check_anomaly(
                db=db,
                activity_id=entry.activity_id,
                duration_minutes=duration_minutes,
                complexity_rating=entry.complexity_rating,
                user_id=entry.user_id,
            )

            if not result.is_anomaly:
                return

            user_name = (
                f"{entry.user.first_name} {entry.user.last_name}"
                if entry.user
                else f"User #{entry.user_id}"
            )
            activity_name = (
                entry.activity.name
                if entry.activity
                else f"Activity #{entry.activity_id}"
            )

            alert = AnomalyAlert(
                time_entry_id=entry.id,
                order_id=entry.order_id,
                activity_name=activity_name,
                user_name=user_name,
                expected_duration_minutes=result.expected_duration_minutes,
                actual_duration_minutes=result.actual_duration_minutes,
                deviation_factor=result.deviation_factor,
                severity=result.severity,
                suggested_reasons=result.suggested_reasons,
            )

            await publish_event(
                "anomaly_alerts",
                json.dumps(alert.model_dump(mode="json")),
            )

            logger.info(
                "Anomaly alert published",
                extra={
                    "time_entry_id": entry.id,
                    "order_id": entry.order_id,
                    "activity_id": entry.activity_id,
                    "duration_minutes": duration_minutes,
                    "deviation_factor": result.deviation_factor,
                    "severity": result.severity.value if result.severity else None,
                },
            )

        except Exception as exc:
            # Anomaly check must never break the time entry stop flow.
            logger.error(
                "Anomaly detection failed (non-fatal)",
                extra={"time_entry_id": entry.id if entry else None, "error": str(exc)},
                exc_info=True,
            )

    @staticmethod
    async def get_time_entry(
        db: AsyncSession, entry_id: str
    ) -> Optional[TimeEntryModel]:
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
                selectinload(
                    TimeEntryModel.interruptions
                ),  # FIXED: Added interruptions
                selectinload(TimeEntryModel.photos),  # FIXED: Added photos
            )
            .filter(
                and_(
                    TimeEntryModel.user_id == user_id, TimeEntryModel.end_time.is_(None)
                )
            )
            # The partial unique index guarantees at most one row; ordering +
            # first() keeps legacy data (pre-index duplicates) from turning
            # into a MultipleResultsFound 500 (BE-12).
            .order_by(TimeEntryModel.start_time.desc())
            .limit(1)
        )
        return result.scalars().first()

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
                selectinload(
                    TimeEntryModel.interruptions
                ),  # FIXED: Added interruptions
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
        query = (
            select(TimeEntryModel)
            .options(
                selectinload(TimeEntryModel.activity),
                selectinload(TimeEntryModel.order),
                selectinload(TimeEntryModel.user),  # FIXED: Added user
                selectinload(
                    TimeEntryModel.interruptions
                ),  # FIXED: Added interruptions
                selectinload(TimeEntryModel.photos),  # FIXED: Added photos
            )
            .filter(TimeEntryModel.user_id == user_id)
        )

        if start_date:
            query = query.filter(TimeEntryModel.start_time >= start_date)
        if end_date:
            query = query.filter(TimeEntryModel.start_time <= end_date)

        query = (
            query.order_by(TimeEntryModel.start_time.desc()).offset(skip).limit(limit)
        )

        result = await db.execute(query)
        return result.scalars().all()

    @staticmethod
    async def create_time_entry(
        db: AsyncSession, entry_in: TimeEntryCreate
    ) -> TimeEntryModel:
        """Erstellt eine manuelle TimeEntry (mit Start & End Zeit)."""
        entry_data = entry_in.model_dump(exclude={"duration_minutes"})
        entry_data["location_id"], entry_data["location"] = (
            await LocationService.resolve(db, entry_in.location_id, entry_in.location)
        )

        # Berechne Dauer falls nicht angegeben
        duration = entry_in.duration_minutes
        if not duration and entry_in.end_time:
            duration = int(
                (entry_in.end_time - entry_in.start_time).total_seconds() / 60
            )

        db_entry = TimeEntryModel(
            id=str(uuid.uuid4()),
            **entry_data,
            duration_minutes=duration,
            created_at=datetime.now(timezone.utc),
        )

        db.add(db_entry)
        await db.commit()
        await db.refresh(db_entry)

        # Increment activity usage
        await ActivityService.increment_usage(db, entry_in.activity_id)

        # Update average duration if entry is completed
        if duration:
            await ActivityService.update_average_duration(
                db, entry_in.activity_id, float(duration)
            )

        return db_entry

    @staticmethod
    async def update_time_entry(
        db: AsyncSession, entry_id: str, entry_in: TimeEntryUpdate
    ) -> Optional[TimeEntryModel]:
        """Aktualisiert eine bestehende TimeEntry.

        BE-18: ``end_time`` must lie after ``start_time`` and within 24 h;
        a running entry cannot get a duration without an end time and
        ``end_time`` cannot be cleared. Setting ``end_time`` on a running
        entry goes through ``stop_time_entry`` so the stop side effects
        (activity average, anomaly check, cost watch) run.

        Raises:
            TimeEntryValidationError: the edit is impossible (422).
        """
        entry = await TimeTrackingService.get_time_entry(db, entry_id)
        if not entry:
            return None

        update_data = entry_in.model_dump(exclude_unset=True)
        TimeTrackingService._validate_edit(entry, update_data)
        if "location" in update_data or "location_id" in update_data:
            update_data["location_id"], update_data["location"] = (
                await LocationService.resolve(
                    db,
                    update_data.get("location_id"),
                    update_data.get("location"),
                    keep_id=entry.location_id,
                )
            )

        new_end: Optional[datetime] = update_data.get("end_time")
        if entry.end_time is None and new_end is not None:
            return await TimeTrackingService._stop_via_edit(
                db, entry, new_end, update_data
            )

        if new_end is not None:
            update_data["duration_minutes"] = int(
                (new_end - entry.start_time).total_seconds() / 60
            )

        await db.execute(
            update(TimeEntryModel)
            .where(TimeEntryModel.id == entry_id)
            .values(**update_data)
        )
        await db.commit()

        # W2-14: a corrected end time or order changes the order's hours.
        await TimeTrackingService._recompute_actual_hours(db, entry.order_id)
        if update_data.get("order_id") not in (None, entry.order_id):
            await TimeTrackingService._recompute_actual_hours(
                db, update_data["order_id"]
            )

        return await TimeTrackingService.get_time_entry(db, entry_id)

    @staticmethod
    def _validate_edit(entry: TimeEntryModel, update_data: Dict[str, Any]) -> None:
        """Reject impossible time edits (BE-18) with a German message."""
        if "end_time" in update_data and update_data["end_time"] is None:
            raise TimeEntryValidationError(
                "Die Endzeit kann nicht entfernt werden. Bitte eine neue "
                "Zeiterfassung starten."
            )
        new_end: Optional[datetime] = update_data.get("end_time")
        if new_end is not None:
            if new_end <= entry.start_time:
                raise TimeEntryValidationError(
                    "Die Endzeit muss nach der Startzeit liegen."
                )
            if new_end - entry.start_time > MAX_EDITED_DURATION:
                raise TimeEntryValidationError(
                    "Eine Zeiterfassung darf höchstens 24 Stunden dauern."
                )
        elif entry.end_time is None and update_data.get("duration_minutes"):
            raise TimeEntryValidationError(
                "Eine laufende Zeiterfassung hat noch keine Dauer. Bitte "
                "stoppen oder eine Endzeit angeben."
            )

    @staticmethod
    async def _stop_via_edit(
        db: AsyncSession,
        entry: TimeEntryModel,
        end_time: datetime,
        update_data: Dict[str, Any],
    ) -> Optional[TimeEntryModel]:
        """PUT with ``end_time`` on a running entry = the stop flow (BE-18)."""
        entry_id = entry.id
        stop_keys = {
            "end_time",
            "notes",
            "complexity_rating",
            "quality_rating",
            "rework_required",
        }
        stop_data = TimeEntryStop(
            complexity_rating=update_data.get(
                "complexity_rating", entry.complexity_rating
            ),
            quality_rating=update_data.get("quality_rating", entry.quality_rating),
            rework_required=bool(
                update_data.get("rework_required", entry.rework_required)
            ),
            notes=update_data.get("notes", entry.notes),
        )
        stopped = await TimeTrackingService.stop_time_entry(
            db, entry_id, stop_data, end_time=end_time
        )
        rest = {k: v for k, v in update_data.items() if k not in stop_keys}
        if not rest:
            return stopped
        await db.execute(
            update(TimeEntryModel).where(TimeEntryModel.id == entry_id).values(**rest)
        )
        await db.commit()
        return await TimeTrackingService.get_time_entry(db, entry_id)

    @staticmethod
    async def delete_time_entry(db: AsyncSession, entry_id: str) -> Dict[str, Any]:
        """Löscht eine TimeEntry."""
        entry = await TimeTrackingService.get_time_entry(db, entry_id)
        if not entry:
            return {"success": False, "message": "Time entry not found"}

        order_id = entry.order_id
        await db.execute(delete(TimeEntryModel).where(TimeEntryModel.id == entry_id))
        await db.commit()

        await TimeTrackingService._recompute_actual_hours(db, order_id)
        return {"success": True}

    @staticmethod
    async def _close_open_interruptions(
        db: AsyncSession, entry_id: str, at: datetime
    ) -> int:
        """Close every open interruption marker of ``entry_id`` at ``at``.

        Flushes but does not commit: the caller's transaction owns the
        write. Returns the number of interruptions closed.
        """
        at = ensure_utc(at)
        result = await db.execute(
            select(InterruptionModel).where(
                InterruptionModel.time_entry_id == entry_id,
                InterruptionModel.resumed_at.is_(None),
                InterruptionModel.duration_minutes == 0,
            )
        )
        open_rows = list(result.scalars().all())
        for row in open_rows:
            started = row.timestamp or at
            resumed = max(at, started)
            row.resumed_at = resumed
            row.duration_minutes = _whole_minutes(resumed - started)
        if open_rows:
            await db.flush()
        return len(open_rows)

    @staticmethod
    async def resume_interruptions(
        db: AsyncSession,
        entry_id: str,
        user: UserModel,
        at: Optional[datetime] = None,
    ) -> int:
        """Work resumes on a running entry: close its open interruptions.

        Per-user scope like ``log_interruption``. Returns how many were
        closed (0 is not an error: nothing was open).
        """
        entry = await TimeTrackingService.get_time_entry(db, entry_id)
        if entry is None:
            raise NotFoundError(
                "Time entry not found",
                code="time_entry.not_found",
                extra={"entry_id": entry_id},
            )
        if entry.user_id != user.id:
            raise ForbiddenError(
                "Zeiterfassung gehoert einem anderen Benutzer.",
                code="time_entry.cross_user_forbidden",
            )
        closed = await TimeTrackingService._close_open_interruptions(
            db, entry_id, ensure_utc(at) if at is not None else utcnow()
        )
        await db.commit()
        return closed

    @staticmethod
    async def _has_open_interruption(db: AsyncSession, entry_id: str) -> bool:
        """True when ``entry_id`` has an unresumed interruption marker.

        A direct query — same ``resumed_at IS NULL AND duration_minutes ==
        0`` shape ``_close_open_interruptions`` uses — rather than trusting
        ``entry.interruptions`` from a possibly-stale identity-mapped
        object, since ``pause_time_entry``/``resume_time_entry`` call this
        right after a previous write in the same session.
        """
        result = await db.execute(
            select(InterruptionModel).where(
                InterruptionModel.time_entry_id == entry_id,
                InterruptionModel.resumed_at.is_(None),
                InterruptionModel.duration_minutes == 0,
            )
        )
        return result.scalars().first() is not None

    @staticmethod
    async def pause_time_entry(db: AsyncSession, entry_id: str) -> TimeEntryModel:
        """D-15: manually pause a running entry by opening an Interruption.

        Ownership (owner or ADMIN) is gated by the router's
        ``_get_owned_entry`` before this is called — no per-user check here,
        matching how ``add_interruption`` delegates without re-checking.
        409 if the entry is already stopped or already paused.
        """
        entry = await TimeTrackingService.get_time_entry(db, entry_id)
        if entry is None:
            raise NotFoundError(
                "Time entry not found",
                code="time_entry.not_found",
                extra={"entry_id": entry_id},
            )
        if entry.end_time is not None:
            raise ConflictError(
                "Zeiterfassung ist bereits gestoppt.",
                code="time_entry.not_running",
                extra={"entry_id": entry_id},
            )
        if await TimeTrackingService._has_open_interruption(db, entry_id):
            raise ConflictError(
                "Zeiterfassung ist bereits pausiert.",
                code="time_entry.already_paused",
                extra={"entry_id": entry_id},
            )
        db.add(
            InterruptionModel(
                time_entry_id=entry_id,
                reason="pause",
                duration_minutes=0,
                timestamp=datetime.utcnow(),
            )
        )
        await db.commit()
        return await TimeTrackingService.get_time_entry(db, entry_id)

    @staticmethod
    async def resume_time_entry(db: AsyncSession, entry_id: str) -> TimeEntryModel:
        """D-15: end the current manual pause (sets ``resumed_at`` + measured
        minutes on the open Interruption via ``_close_open_interruptions``).

        Ownership gated by the router, as in ``pause_time_entry``. 409 if
        the entry is stopped or is not currently paused — unlike
        ``resume_interruptions`` (the scan-driven flow, where "nothing was
        open" is a silent no-op), an explicit resume call must fail loudly
        when there is nothing to resume.
        """
        entry = await TimeTrackingService.get_time_entry(db, entry_id)
        if entry is None:
            raise NotFoundError(
                "Time entry not found",
                code="time_entry.not_found",
                extra={"entry_id": entry_id},
            )
        if entry.end_time is not None:
            raise ConflictError(
                "Zeiterfassung ist bereits gestoppt.",
                code="time_entry.not_running",
                extra={"entry_id": entry_id},
            )
        if not await TimeTrackingService._has_open_interruption(db, entry_id):
            raise ConflictError(
                "Zeiterfassung ist nicht pausiert.",
                code="time_entry.not_paused",
                extra={"entry_id": entry_id},
            )
        await TimeTrackingService._close_open_interruptions(
            db, entry_id, datetime.utcnow()
        )
        await db.commit()
        return await TimeTrackingService.get_time_entry(db, entry_id)

    @staticmethod
    async def _recompute_actual_hours(db: AsyncSession, order_id: Any) -> None:
        """W2-14: keep ``Order.actual_hours`` current once it is measured.

        Only orders that already carry actual hours or a completion time are
        recomputed (open orders get theirs on completion, as before). Never
        fails the time-tracking write that triggered it.
        """
        if order_id is None:
            return
        # Late import: ml_data_service imports models this module also uses.
        from goldsmith_erp.services.ml_data_service import (  # noqa: PLC0415
            MLDataService,
        )

        try:
            order = await db.get(OrderModel, order_id)
            if order is None:
                return
            await db.refresh(order)
            if order.completed_at is None and order.actual_hours is None:
                return
            await MLDataService.auto_calculate_actual_hours(db, order_id)
            await db.commit()
        except Exception:
            await db.rollback()
            logger.exception(
                "actual_hours recompute failed", extra={"order_id": order_id}
            )

    @staticmethod
    async def add_interruption(
        db: AsyncSession, interruption_in: InterruptionCreate
    ) -> InterruptionModel:
        """Fügt eine Unterbrechung zu einer laufenden TimeEntry hinzu."""
        # Prüfe ob TimeEntry existiert
        entry = await TimeTrackingService.get_time_entry(
            db, interruption_in.time_entry_id
        )
        if not entry:
            raise ValueError("Time entry not found")

        db_interruption = InterruptionModel(
            time_entry_id=interruption_in.time_entry_id,
            reason=interruption_in.reason,
            duration_minutes=interruption_in.duration_minutes,
            timestamp=datetime.now(timezone.utc),
        )

        db.add(db_interruption)
        await db.commit()
        await db.refresh(db_interruption)

        return db_interruption

    # ==================================================================
    # Slice 5 — scan-aware extensions (A5.1 / A5.2 / A5.4 / A5.5)
    # ==================================================================

    @staticmethod
    async def _check_stale_timer(db: AsyncSession, old_entry: TimeEntryModel) -> None:
        """Raise ``TimerPossiblyStaleError`` if ``old_entry`` looks abandoned.

        The "stale" signal is *intentionally conservative*: we only block
        the silent switch when BOTH of the following are true —

          1. The entry has been running for longer than
             ``STALE_TIMER_THRESHOLD`` (20 min).
          2. No interruption has been logged inside that window.

        A goldsmith who is genuinely working for 40 min without an
        interruption is allowed to scan-switch normally. The block only
        fires for the lunch-break / forgot-to-stop pattern that Meister
        Thomas flagged in the field-test brief.
        """
        now = datetime.now(timezone.utc)
        running_for = now - old_entry.start_time
        if running_for <= STALE_TIMER_THRESHOLD:
            return

        # Look for a recent interruption on this entry. Only the most
        # recent timestamp matters — a single acknowledgement resets the
        # stale window.
        interruption_cutoff = now - STALE_TIMER_THRESHOLD
        result = await db.execute(
            select(InterruptionModel.id)
            .where(
                InterruptionModel.time_entry_id == old_entry.id,
                InterruptionModel.timestamp >= interruption_cutoff,
            )
            .limit(1)
        )
        if result.scalar_one_or_none() is not None:
            return

        running_minutes = max(1, int(running_for.total_seconds() // 60))
        logger.info(
            "switch_timer blocked by stale-timer guard",
            extra={
                "time_entry_id": old_entry.id,
                "user_id": old_entry.user_id,
                "running_minutes": running_minutes,
            },
        )
        raise TimerPossiblyStaleError(
            old_entry_id=old_entry.id,
            running_minutes=running_minutes,
        )

    @staticmethod
    async def switch_timer(
        db: AsyncSession,
        user: UserModel,
        old_entry_id: Optional[str],
        new_order_id: int,
        activity_id: int,
        origin: str = "scan",
        idempotency_key: Optional[uuid.UUID] = None,
        location: Optional[str] = None,
    ) -> TimeEntryModel:
        """Atomically stop an outgoing timer and start a new one (scan flow).

        Invariants:

          * **Per-user scope (A5.1):** if ``old_entry_id`` is supplied it
            MUST belong to ``user.id``. A scan from user A never mutates
            user B's state — the method raises ``CrossUserTimerError``
            (403) before any DB write.
          * **Stale-timer guard (A5.2):** if the outgoing timer has been
            running past ``STALE_TIMER_THRESHOLD`` without an interruption,
            the method raises ``TimerPossiblyStaleError`` (409). The
            frontend catches this and presents the Mittagspause modal.
          * **Atomic:** the stop-old + start-new pair is wrapped in a
            single transaction. If ``start_time_entry`` fails for any
            reason, the old entry is NOT left in a stopped state — the
            whole transaction rolls back.
          * **Origin propagation (A5.4):** the new entry is written with
            ``origin='scan'`` so the 30-day adoption metric counts it.
          * **Pubsub (A5.4 / A5.5):** a single ``time_tracking_updates``
            event is published AFTER commit with a ``source="scan"`` field.
            A pubsub failure is logged AND surfaces as an in-app
            notification for the caller; it never rolls back the commit.

        Idempotency: ``idempotency_key`` is accepted for signature
        compatibility with the V1.1.5 server-side dedupe. V1.1 relies on
        the client (only retries with the same key) + DB-level unique
        indexes on ``scan_logs.idempotency_key``. When the V1.1.5 store
        lands, this parameter will drive the replay-vs-new decision.
        """
        # ------------------------------------------------------------------
        # Pre-flight: validate ownership + stale-timer before any writes.
        # ------------------------------------------------------------------
        old_entry: Optional[TimeEntryModel] = None
        if old_entry_id is not None:
            old_entry = await TimeTrackingService.get_time_entry(db, old_entry_id)
            if old_entry is None:
                # Spec A5.1 fault: old entry doesn't exist — 404 surface
                # rather than silently starting a new one. Client retry
                # with a stale cached ID must fail loudly.
                raise NotFoundError(
                    "Die zu wechselnde Zeiterfassung wurde nicht gefunden.",
                    code="time_entry.old_entry_not_found",
                    extra={"old_entry_id": old_entry_id},
                    legacy_detail={
                        "code": "OLD_ENTRY_NOT_FOUND",
                        "old_entry_id": old_entry_id,
                    },
                )

            # A5.1 — cross-user scope enforcement. Hard fail BEFORE any
            # transactional work so user B's state is provably untouched.
            if old_entry.user_id != user.id:
                logger.warning(
                    "switch_timer blocked: cross-user timer switch attempt",
                    extra={
                        "caller_user_id": user.id,
                        "owner_user_id": old_entry.user_id,
                        "time_entry_id": old_entry.id,
                    },
                )
                raise CrossUserTimerError(
                    old_entry_id=old_entry.id,
                    caller_user_id=user.id,
                    owner_user_id=old_entry.user_id,
                )

            # Old entry must actually be running — stopping a stopped
            # entry would double-count duration.
            if old_entry.end_time is not None:
                raise ConflictError(
                    "Die zu wechselnde Zeiterfassung ist bereits gestoppt.",
                    code="time_entry.old_already_stopped",
                    extra={"old_entry_id": old_entry.id},
                    legacy_detail={
                        "code": "OLD_TIMER_ALREADY_STOPPED",
                        "old_entry_id": old_entry.id,
                    },
                )

            # A5.2 — stale-timer guard. Raises 409 with structured detail.
            await TimeTrackingService._check_stale_timer(db, old_entry)

        # ------------------------------------------------------------------
        # Atomic stop + start.
        #
        # SQLite (used in unit tests) does not support nested SAVEPOINTs
        # cleanly through ``async with db.begin()`` when the session has
        # been commit()-ed earlier in the same test by a fixture, so we
        # drive the sequencing manually. The key guarantee is: if the
        # new-entry INSERT fails, we reset the old entry's end_time back
        # to NULL before re-raising. No partial "stopped but no new entry"
        # state can be observed by other sessions because both writes
        # land in a single commit at the end.
        # ------------------------------------------------------------------
        now = datetime.now(timezone.utc)
        old_entry_snapshot_end: Optional[datetime] = None
        # Capture id as plain string BEFORE the transaction — after rollback,
        # ORM attribute access triggers a lazy-reload that requires a greenlet
        # context the async session no longer owns (fixes MissingGreenlet).
        old_entry_id_snapshot: Optional[str] = (
            old_entry.id if old_entry is not None else None
        )
        new_entry: Optional[TimeEntryModel] = None

        try:
            # Stop old entry in-place.
            if old_entry is not None:
                old_entry_snapshot_end = old_entry.end_time  # always None here
                duration = int((now - old_entry.start_time).total_seconds() / 60)
                await TimeTrackingService._close_open_interruptions(
                    db, old_entry_id_snapshot, now
                )
                await db.execute(
                    update(TimeEntryModel)
                    .where(TimeEntryModel.id == old_entry_id_snapshot)
                    .values(end_time=now, duration_minutes=duration)
                )

            # Start new entry.
            new_entry = TimeEntryModel(
                id=str(uuid.uuid4()),
                order_id=new_order_id,
                user_id=user.id,
                activity_id=activity_id,
                start_time=now,
                location=location,
                origin=origin,
                extra_metadata={},
                created_at=now,
            )
            db.add(new_entry)
            await db.commit()
        except Exception as exc:
            # Roll back everything — if the new-entry insert failed the
            # old entry's stop must not stick.
            await db.rollback()
            if old_entry_id_snapshot is not None and old_entry_snapshot_end is None:
                # Belt-and-braces: make sure the old entry is still
                # running in case any partial state escaped. The commit
                # above is the only path to persistence, so a rollback
                # here should leave old_entry untouched — this restore
                # is defensive only. Uses the pre-captured id snapshot
                # because the ORM object is detached after rollback.
                await db.execute(
                    update(TimeEntryModel)
                    .where(TimeEntryModel.id == old_entry_id_snapshot)
                    .values(end_time=None, duration_minutes=None)
                )
                await db.commit()
            if isinstance(exc, IntegrityError):
                # Another timer of this user is already running (BE-12).
                raise TimerAlreadyRunningError() from exc
            raise

        # Reload with relationships for downstream use / response.
        assert new_entry is not None
        new_entry = await TimeTrackingService.get_time_entry(db, new_entry.id)

        # Increment activity usage counter AFTER the switch commits so a
        # failed commit doesn't pollute the activity stats.
        await ActivityService.increment_usage(db, activity_id)

        if old_entry is not None:
            # W2-14: the stopped entry may belong to a completed order.
            await TimeTrackingService._recompute_actual_hours(db, old_entry.order_id)

        # --------------------------------------------------------------
        # A5.4 + A5.5 — publish with source:"scan" envelope; failure is
        # surfaced via in-app notification, never silently swallowed.
        # --------------------------------------------------------------
        payload = {
            "action": "switch",
            "source": origin,  # 'scan' for scan-triggered switches
            "user_id": user.id,
            "old_entry_id": old_entry.id if old_entry else None,
            "new_entry_id": new_entry.id,
            "order_id": new_order_id,
            "activity_id": activity_id,
            "switched_at": now.isoformat(),
        }
        await TimeTrackingService._safe_publish(
            db=db,
            channel="time_tracking_updates",
            payload=payload,
            user_id=user.id,
            failure_context={
                "entry_id": new_entry.id,
                "order_id": new_order_id,
            },
        )

        return new_entry

    @staticmethod
    async def patch_activity(
        db: AsyncSession,
        entry_id: str,
        activity_id: int,
        user: UserModel,
        origin: str = "scan",
    ) -> TimeEntryModel:
        """Update activity on a running time entry **in place** (A5.4).

        Lena §1 / Slice 5 contract decision: PATCH mutates the current
        row — it does NOT create a new ``TimeEntry``. A goldsmith scanning
        ``ACTIVITY:hartloeten`` mid-session wants the same entry to
        continue with the updated activity; forking into a new row would
        inflate the adoption denominator and break duration reporting.

        Per-user scope: only the entry's owner may patch it. An admin
        making a correction uses the separate update / correction flow
        (``correction_of`` column, Slice 2 A2.2) — out of scope here.
        """
        entry = await TimeTrackingService.get_time_entry(db, entry_id)
        if entry is None:
            raise NotFoundError(
                "Time entry not found",
                code="time_entry.not_found",
                extra={"entry_id": entry_id},
            )

        # Ownership — mirrors A5.1 per-user scope for switch_timer.
        if entry.user_id != user.id:
            raise ForbiddenError(
                "Zeiterfassung gehoert einem anderen Benutzer.",
                code="time_entry.cross_user_forbidden",
                legacy_detail={
                    "code": "CROSS_USER_TIME_ENTRY_FORBIDDEN",
                    "message": "Zeiterfassung gehoert einem anderen Benutzer.",
                },
            )

        # Must be running — patching a stopped entry rewrites history.
        if entry.end_time is not None:
            raise ConflictError(
                "Diese Zeiterfassung ist bereits gestoppt.",
                code="time_entry.already_stopped",
                extra={"entry_id": entry.id},
                legacy_detail={"code": "ENTRY_ALREADY_STOPPED", "entry_id": entry.id},
            )

        # Verify target activity exists — fail loudly rather than FK
        # integrity error at commit.
        activity_exists = await db.execute(
            select(ActivityModel.id).where(ActivityModel.id == activity_id).limit(1)
        )
        if activity_exists.scalar_one_or_none() is None:
            raise NotFoundError(
                "Activity not found",
                code="activity.not_found",
                extra={"activity_id": activity_id},
            )

        # In-place update — single row, no fork. An activity scan means the
        # goldsmith is back at the bench: close an open interruption (W2-14).
        await TimeTrackingService._close_open_interruptions(
            db, entry_id, datetime.now(timezone.utc)
        )
        await db.execute(
            update(TimeEntryModel)
            .where(TimeEntryModel.id == entry_id)
            .values(activity_id=activity_id)
        )
        await db.commit()

        await ActivityService.increment_usage(db, activity_id)

        reloaded = await TimeTrackingService.get_time_entry(db, entry_id)

        # A5.4 pubsub + A5.5 failure handling.
        await TimeTrackingService._safe_publish(
            db=db,
            channel="time_tracking_updates",
            payload={
                "action": "activity_patched",
                "source": origin,
                "user_id": user.id,
                "entry_id": entry_id,
                "activity_id": activity_id,
            },
            user_id=user.id,
            failure_context={"entry_id": entry_id},
        )

        return reloaded

    @staticmethod
    async def edit_running_entry(
        db: AsyncSession,
        entry_id: str,
        edit: RunningTimeEntryEdit,
        user: UserModel,
    ) -> Optional[TimeEntryModel]:
        """Edit a RUNNING entry in place (activity, order, location, notes,
        start time) and publish ``entry_edited`` on ``time_tracking_updates``.

        Ownership (owner or ADMIN) is gated by the router. Validation, the
        change-log line and the write live in ``services.running_timer_edit``.
        """
        result = await running_timer_edit.edit_running_entry(db, entry_id, edit, user)
        # The router loaded the entry (and its activity / order) before the
        # UPDATE; expire so the reload does not serve the stale relationships.
        cached = await db.get(TimeEntryModel, entry_id)
        if cached is not None:
            db.expire(cached)
        reloaded = await TimeTrackingService.get_time_entry(db, entry_id)
        if not result.changed_fields or reloaded is None:
            return reloaded

        if "activity_id" in result.changed_fields:
            await ActivityService.increment_usage(db, reloaded.activity_id)

        await TimeTrackingService._safe_publish(
            db=db,
            channel="time_tracking_updates",
            payload={
                "action": "entry_edited",
                "source": "manual",
                "user_id": reloaded.user_id,
                "edited_by": user.id,
                "entry_id": entry_id,
                "order_id": reloaded.order_id,
                "activity_id": reloaded.activity_id,
                "fields": list(result.changed_fields),
            },
            user_id=user.id,
            failure_context={"entry_id": entry_id},
        )
        return reloaded

    @staticmethod
    async def log_interruption(
        db: AsyncSession,
        entry_id: str,
        interrupt_code: str,
        user: UserModel,
        notes: Optional[str] = None,
        duration_minutes: int = 0,
        origin: str = "scan",
    ) -> InterruptionModel:
        """Record an interruption on a RUNNING time entry without stopping it.

        ``interrupt_code`` is stored in the existing ``reason`` column —
        callers from Slice 5 supply short codes like ``kundenanruf`` /
        ``material_holen`` emitted by an ``INTERRUPT:<code>`` scan. The
        code vocabulary is validated at the router level.

        ``duration_minutes`` defaults to 0 for "event-marker" scans where
        the goldsmith tags an interruption as it starts (the timer keeps
        running — there is no duration yet). Admin-driven corrections
        with a known duration pass a positive value. Existing DB schema
        requires a non-null int; 0 is the sentinel for "not yet
        measured" and is discriminable from any real interruption.
        """
        entry = await TimeTrackingService.get_time_entry(db, entry_id)
        if entry is None:
            raise NotFoundError(
                "Time entry not found",
                code="time_entry.not_found",
                extra={"entry_id": entry_id},
            )

        # Per-user scope — symmetric with patch_activity.
        if entry.user_id != user.id:
            raise ForbiddenError(
                "Zeiterfassung gehoert einem anderen Benutzer.",
                code="time_entry.cross_user_forbidden",
                legacy_detail={
                    "code": "CROSS_USER_TIME_ENTRY_FORBIDDEN",
                    "message": "Zeiterfassung gehoert einem anderen Benutzer.",
                },
            )

        # Timer must be running — attaching an interruption to a stopped
        # entry breaks the Slice 2 adoption metric (interruptions are
        # evidence of activity inside the stale-timer window).
        if entry.end_time is not None:
            raise ConflictError(
                "Diese Zeiterfassung ist bereits gestoppt.",
                code="time_entry.already_stopped",
                extra={"entry_id": entry.id},
                legacy_detail={"code": "ENTRY_ALREADY_STOPPED", "entry_id": entry.id},
            )

        if duration_minutes < 0:
            raise DomainValidationError(
                "duration_minutes must be >= 0",
                code="interruption.invalid_duration",
            )

        now = datetime.now(timezone.utc)
        # W2-14: a new interruption scan ends the previous open one.
        await TimeTrackingService._close_open_interruptions(db, entry_id, now)
        db_interruption = InterruptionModel(
            time_entry_id=entry_id,
            reason=interrupt_code,
            duration_minutes=duration_minutes,
            timestamp=now,
        )
        if duration_minutes > 0:
            # A known duration is a closed interruption.
            db_interruption.resumed_at = now + timedelta(minutes=duration_minutes)
        if notes:
            # Notes piggyback on the reason column as a suffix for now —
            # the Slice 2 ``notes`` column on Interruption is out of V1.1
            # scope; adding it here without a migration would silently
            # drop the value. Safer to concatenate with a clear separator.
            db_interruption.reason = f"{interrupt_code} | {notes[:180]}"

        db.add(db_interruption)
        await db.commit()
        await db.refresh(db_interruption)

        await TimeTrackingService._safe_publish(
            db=db,
            channel="time_tracking_updates",
            payload={
                "action": "interruption_logged",
                "source": origin,
                "user_id": user.id,
                "entry_id": entry_id,
                "interrupt_code": interrupt_code,
            },
            user_id=user.id,
            failure_context={"entry_id": entry_id},
        )

        return db_interruption

    @staticmethod
    async def _safe_publish(
        *,
        db: AsyncSession,
        channel: str,
        payload: Dict[str, Any],
        user_id: int,
        failure_context: Dict[str, Any],
    ) -> None:
        """Publish to Redis with A5.5 failure handling.

        ``publish_event`` already retries internally (3 attempts with
        backoff) and never raises — it logs at ERROR on final failure.
        Slice 5 strengthens that contract by ALSO writing an in-app
        notification so the caller sees *something* when the
        mutation succeeded but the real-time fan-out did not. Without
        this, widgets would stay stale and the goldsmith would re-scan
        and book a duplicate timer (Lena §3).
        """
        # Late import — pubsub module monkey-patched to a no-op in the
        # unit test fixture, so we resolve it at call time to honour
        # the patch.
        from goldsmith_erp.core.pubsub import publish_event  # noqa: PLC0415

        publish_succeeded = False
        try:
            # BE-20: publish_event returns False after its final retry.
            publish_succeeded = (
                await publish_event(channel, json.dumps(payload)) is not False
            )
        except Exception as exc:
            # publish_event itself catches and logs — this branch only
            # fires if a caller subclass raises unexpectedly.
            logger.warning(
                "pubsub publish raised unexpectedly",
                extra={
                    "channel": channel,
                    "user_id": user_id,
                    "context": failure_context,
                    "error": str(exc),
                },
                exc_info=True,
            )

        if publish_succeeded:
            return

        # Detection path: publish_event returned False (all retries failed)
        # or raised unexpectedly — write the A5.5 in-app notification.
        try:
            from goldsmith_erp.db.models import (  # noqa: PLC0415
                NotificationSeverityEnum,
                NotificationTypeEnum,
            )
            from goldsmith_erp.services.notification_service import (  # noqa: PLC0415
                NotificationService,
            )

            await NotificationService.create_notification(
                db=db,
                user_id=user_id,
                title="Live-Update fehlgeschlagen",
                message=(
                    "Ein Scan-Vorgang wurde erfolgreich gespeichert, aber "
                    "die Live-Aktualisierung hat nicht funktioniert. "
                    "Bitte Seite neu laden, um den aktuellen Stand zu sehen."
                ),
                notification_type=NotificationTypeEnum.SYSTEM,
                severity=NotificationSeverityEnum.WARNING,
            )
        except Exception as notify_exc:
            # Notification write failure must not mask the original
            # mutation's success — just log.
            logger.error(
                "Failed to write pubsub-failure notification",
                extra={
                    "user_id": user_id,
                    "context": failure_context,
                    "error": str(notify_exc),
                },
                exc_info=True,
            )

    @staticmethod
    async def get_total_time_for_order(
        db: AsyncSession, order_id: int
    ) -> Dict[str, Any]:
        """Berechnet die Gesamtzeit für einen Auftrag.

        W2-14: ``total_minutes`` / ``total_hours`` are net of interruptions
        (closed entries only); ``gross_minutes`` and
        ``interruption_minutes`` show the split.
        """
        result = await db.execute(
            select(TimeEntryModel)
            .options(selectinload(TimeEntryModel.interruptions))
            .filter(
                and_(
                    TimeEntryModel.order_id == order_id,
                    TimeEntryModel.end_time.isnot(None),  # Nur abgeschlossene Einträge
                )
            )
        )
        entries = list(result.scalars().all())
        gross_minutes = sum(int(e.duration_minutes or 0) for e in entries)
        net_minutes = sum(net_entry_minutes(e) for e in entries)

        return {
            "order_id": order_id,
            "total_minutes": net_minutes,
            "total_hours": round(net_minutes / 60, 2),
            "gross_minutes": gross_minutes,
            "interruption_minutes": gross_minutes - net_minutes,
            "entry_count": len(entries),
        }

    @staticmethod
    async def get_summary(
        db: AsyncSession,
        *,
        user_id: int,
        start: datetime,
        end: datetime,
    ) -> TimeSummaryStats:
        """Aggregate a user's completed time entries within [start, end).

        Billable hours count only entries whose activity.is_billable is True.
        comparison_previous_period is the % change in total hours vs the
        immediately preceding window of equal length; None when that prior
        window has zero hours.
        """
        window = end - start
        prev_start = start - window

        current_filter = and_(
            TimeEntryModel.user_id == user_id,
            TimeEntryModel.end_time.isnot(None),
            TimeEntryModel.start_time >= start,
            TimeEntryModel.start_time < end,
        )

        totals = (
            await db.execute(
                select(
                    func.coalesce(func.sum(TimeEntryModel.duration_minutes), 0).label(
                        "total"
                    ),
                    func.count(TimeEntryModel.id).label("count"),
                    func.coalesce(
                        func.sum(
                            case(
                                (
                                    ActivityModel.is_billable.is_(True),
                                    TimeEntryModel.duration_minutes,
                                ),
                                else_=0,
                            )
                        ),
                        0,
                    ).label("billable"),
                )
                .join(ActivityModel, TimeEntryModel.activity_id == ActivityModel.id)
                .filter(current_filter)
            )
        ).one()

        total_minutes = totals.total or 0
        entries_count = totals.count or 0
        billable_minutes = totals.billable or 0

        most_used_row = (
            await db.execute(
                select(ActivityModel.name)
                .join(TimeEntryModel, TimeEntryModel.activity_id == ActivityModel.id)
                .filter(current_filter)
                .group_by(ActivityModel.id, ActivityModel.name)
                .order_by(func.sum(TimeEntryModel.duration_minutes).desc())
                .limit(1)
            )
        ).first()
        most_used_activity = most_used_row[0] if most_used_row else None

        prev_minutes = (
            await db.execute(
                select(
                    func.coalesce(func.sum(TimeEntryModel.duration_minutes), 0)
                ).filter(
                    and_(
                        TimeEntryModel.user_id == user_id,
                        TimeEntryModel.end_time.isnot(None),
                        TimeEntryModel.start_time >= prev_start,
                        TimeEntryModel.start_time < start,
                    )
                )
            )
        ).scalar() or 0

        average_session_minutes = (
            round(total_minutes / entries_count, 1) if entries_count else 0
        )
        comparison = (
            round(((total_minutes - prev_minutes) / prev_minutes) * 100, 1)
            if prev_minutes > 0
            else None
        )

        return TimeSummaryStats(
            total_hours=round(total_minutes / 60, 2),
            billable_hours=round(billable_minutes / 60, 2),
            entries_count=entries_count,
            average_session_minutes=average_session_minutes,
            most_used_activity=most_used_activity,
            comparison_previous_period=comparison,
        )
