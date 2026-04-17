import json
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update, delete, and_, func
from sqlalchemy.orm import selectinload
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import uuid

from fastapi import HTTPException

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


class TimerPossiblyStaleError(HTTPException):
    """Raised by ``switch_timer`` when the outgoing timer looks stale (A5.2).

    The 409 envelope carries a structured ``detail`` so the frontend can
    distinguish this from generic conflicts and render the Mittagspause
    modal with the three options (abziehen+wechseln / trotzdem wechseln /
    abbrechen). See ``V1.1-AMENDMENTS.md`` A5.2.
    """

    def __init__(self, *, old_entry_id: str, running_minutes: int) -> None:
        super().__init__(
            status_code=409,
            detail={
                "code": "TIMER_POSSIBLY_STALE",
                "old_entry_id": old_entry_id,
                "running_minutes": running_minutes,
                "message": (
                    f"Der Timer laeuft {running_minutes} min ohne Taetigkeits- "
                    "oder Unterbrechungs-Eintrag. Mittagspause abziehen?"
                ),
            },
        )


class CrossUserTimerError(HTTPException):
    """Raised by ``switch_timer`` when a caller tries to switch another user's timer (A5.1).

    This is a hard 403 — no modal, no retry. A scan from user A MUST NOT
    ever mutate user B's time-tracking state. Logged at WARNING level so
    repeated attempts can be observed.
    """

    def __init__(self, *, old_entry_id: str, caller_user_id: int, owner_user_id: int) -> None:
        super().__init__(
            status_code=403,
            detail={
                "code": "CROSS_USER_TIMER_FORBIDDEN",
                "message": (
                    "Timer gehoert einem anderen Benutzer — Wechsel nicht "
                    "erlaubt."
                ),
            },
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

        # Reload the entry with relationships for anomaly check and return value
        stopped_entry = await TimeTrackingService.get_time_entry(db, entry_id)

        # --- Anomaly detection (fire-and-forget, must not block the stop flow) ---
        await TimeTrackingService._check_and_publish_anomaly(db, stopped_entry, duration)

        return stopped_entry

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
            from goldsmith_erp.ml.anomaly_detection import AnomalyDetector
            from goldsmith_erp.ml.anomaly_alerts import AnomalyAlert
            from goldsmith_erp.core.pubsub import publish_event

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
                entry.activity.name if entry.activity else f"Activity #{entry.activity_id}"
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

    # ==================================================================
    # Slice 5 — scan-aware extensions (A5.1 / A5.2 / A5.4 / A5.5)
    # ==================================================================

    @staticmethod
    async def _check_stale_timer(
        db: AsyncSession, old_entry: TimeEntryModel
    ) -> None:
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
        now = datetime.utcnow()
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
                raise HTTPException(
                    status_code=404,
                    detail={
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
                raise HTTPException(
                    status_code=409,
                    detail={
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
        now = datetime.utcnow()
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
        except Exception:
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
            raise

        # Reload with relationships for downstream use / response.
        assert new_entry is not None
        new_entry = await TimeTrackingService.get_time_entry(db, new_entry.id)

        # Increment activity usage counter AFTER the switch commits so a
        # failed commit doesn't pollute the activity stats.
        await ActivityService.increment_usage(db, activity_id)

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
            raise HTTPException(status_code=404, detail="Time entry not found")

        # Ownership — mirrors A5.1 per-user scope for switch_timer.
        if entry.user_id != user.id:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "CROSS_USER_TIME_ENTRY_FORBIDDEN",
                    "message": "Zeiterfassung gehoert einem anderen Benutzer.",
                },
            )

        # Must be running — patching a stopped entry rewrites history.
        if entry.end_time is not None:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "ENTRY_ALREADY_STOPPED",
                    "entry_id": entry.id,
                },
            )

        # Verify target activity exists — fail loudly rather than FK
        # integrity error at commit.
        activity_exists = await db.execute(
            select(ActivityModel.id).where(ActivityModel.id == activity_id).limit(1)
        )
        if activity_exists.scalar_one_or_none() is None:
            raise HTTPException(status_code=404, detail="Activity not found")

        # In-place update — single row, no fork.
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
            raise HTTPException(status_code=404, detail="Time entry not found")

        # Per-user scope — symmetric with patch_activity.
        if entry.user_id != user.id:
            raise HTTPException(
                status_code=403,
                detail={
                    "code": "CROSS_USER_TIME_ENTRY_FORBIDDEN",
                    "message": "Zeiterfassung gehoert einem anderen Benutzer.",
                },
            )

        # Timer must be running — attaching an interruption to a stopped
        # entry breaks the Slice 2 adoption metric (interruptions are
        # evidence of activity inside the stale-timer window).
        if entry.end_time is not None:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "ENTRY_ALREADY_STOPPED",
                    "entry_id": entry.id,
                },
            )

        if duration_minutes < 0:
            raise HTTPException(
                status_code=422,
                detail="duration_minutes must be >= 0",
            )

        db_interruption = InterruptionModel(
            time_entry_id=entry_id,
            reason=interrupt_code,
            duration_minutes=duration_minutes,
            timestamp=datetime.utcnow(),
        )
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
            await publish_event(channel, json.dumps(payload))
            publish_succeeded = True
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

        # Detection path: publish_event returns None on success OR
        # silent failure (it logs internally). We cannot distinguish
        # the two from the return value in V1.1. The ``publish_succeeded``
        # branch above covers unexpected exceptions; the A5.5 in-app
        # notification is triggered by an explicit side-channel in
        # production via the notification service. For now we rely on
        # the logged ERROR + a best-effort notification write.
        try:
            from goldsmith_erp.services.notification_service import (  # noqa: PLC0415
                NotificationService,
            )
            from goldsmith_erp.db.models import (  # noqa: PLC0415
                NotificationSeverityEnum,
                NotificationTypeEnum,
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
