# src/goldsmith_erp/services/system_monitor.py
"""
Background system health monitor.

Runs an async loop every 5 minutes that:
1. Calls SystemHealthService.get_full_health() and compares with previous state.
2. Creates notifications for ADMIN users on state transitions or threshold breaches.
3. Deduplicates: the same notification category is not created more than once per hour.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.core.config import settings
from goldsmith_erp.db.models import (
    Notification,
    NotificationSeverityEnum,
    NotificationTypeEnum,
    User,
    UserRole,
)
from goldsmith_erp.db.session import AsyncSessionLocal
from goldsmith_erp.services.notification_service import NotificationService
from goldsmith_erp.services.system_health_service import SystemHealthService

logger = logging.getLogger(__name__)

# How long to wait between monitoring cycles (seconds)
MONITOR_INTERVAL_SECONDS: int = 5 * 60  # 5 minutes

# How many hours before the same system notification category is repeated
DEDUP_HOURS: int = 1

# How many hours between backup warnings
BACKUP_WARNING_HOURS: int = 25


# ---------------------------------------------------------------------------
# Module-level state (in-memory, resets on restart)
# ---------------------------------------------------------------------------
_previous_health_status: Optional[str] = None


async def _get_admin_users(db: AsyncSession):
    """Return all active ADMIN users."""
    stmt = select(User).where(
        and_(User.is_active.is_(True), User.role == UserRole.ADMIN)
    )
    result = await db.execute(stmt)
    return result.scalars().all()


async def _already_notified(
    db: AsyncSession,
    user_id: int,
    title: str,
    within_hours: int = DEDUP_HOURS,
) -> bool:
    """
    Return True if a SYSTEM notification with the same title was created for this
    user within the last ``within_hours`` hours.
    """
    cutoff = datetime.utcnow() - timedelta(hours=within_hours)
    stmt = select(Notification).where(
        and_(
            Notification.user_id == user_id,
            Notification.notification_type == NotificationTypeEnum.SYSTEM,
            Notification.title == title,
            Notification.created_at >= cutoff,
        )
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none() is not None


async def _notify_admins(
    db: AsyncSession,
    title: str,
    message: str,
    severity: NotificationSeverityEnum,
) -> None:
    """
    Create a system notification for all ADMIN users, with deduplication.
    """
    admins = await _get_admin_users(db)
    for admin in admins:
        if await _already_notified(db, admin.id, title):
            logger.debug(
                "Skipping duplicate system notification",
                extra={"user_id": admin.id, "title": title},
            )
            continue
        try:
            await NotificationService.create_notification(
                db=db,
                user_id=admin.id,
                title=title,
                message=message,
                notification_type=NotificationTypeEnum.SYSTEM,
                severity=severity,
            )
        except Exception as exc:
            logger.error(
                "Failed to create system notification",
                extra={"user_id": admin.id, "title": title, "error": str(exc)},
            )


async def _check_backup_age(db: AsyncSession) -> None:
    """Warn if the last backup is older than BACKUP_WARNING_HOURS."""
    backup_info = SystemHealthService.get_last_backup_info()
    timestamp_str: Optional[str] = backup_info.get("timestamp")

    if timestamp_str is None:
        # No backup found at all
        await _notify_admins(
            db=db,
            title="Kein Backup gefunden",
            message=(
                f"Im Backup-Verzeichnis '{backup_info['backup_dir']}' wurde kein "
                "Backup gefunden. Bitte Backup-Konfiguration prüfen."
            ),
            severity=NotificationSeverityEnum.WARNING,
        )
        return

    last_backup_dt = datetime.fromisoformat(timestamp_str)
    age_hours = (datetime.utcnow() - last_backup_dt).total_seconds() / 3600

    if age_hours > BACKUP_WARNING_HOURS:
        await _notify_admins(
            db=db,
            title="Backup veraltet",
            message=(
                f"Das letzte Backup ({backup_info['filename']}) ist "
                f"{int(age_hours)} Stunden alt. "
                "Bitte sicherstellen, dass das automatische Backup läuft."
            ),
            severity=NotificationSeverityEnum.WARNING,
        )


async def _check_disk(db: AsyncSession, disk: Dict[str, Any]) -> None:
    """Notify if disk usage exceeds thresholds."""
    status = disk.get("status", "ok")
    used_percent = disk.get("used_percent", 0.0)
    free_gb = disk.get("free_gb", 0.0)

    if status == "critical":
        await _notify_admins(
            db=db,
            title="Festplatte kritisch voll",
            message=(
                f"Festplattenauslastung: {used_percent}% belegt, "
                f"noch {free_gb} GB frei. "
                "Sofortige Maßnahmen erforderlich!"
            ),
            severity=NotificationSeverityEnum.URGENT,
        )
    elif status == "warning":
        await _notify_admins(
            db=db,
            title="Festplatte fast voll",
            message=(
                f"Festplattenauslastung: {used_percent}% belegt, "
                f"noch {free_gb} GB frei. "
                "Bitte Speicherplatz freigeben."
            ),
            severity=NotificationSeverityEnum.WARNING,
        )


async def _check_state_transition(
    db: AsyncSession,
    current_status: str,
) -> None:
    """Notify on health status transitions (e.g. healthy → degraded)."""
    global _previous_health_status

    if _previous_health_status is None:
        # First run — set baseline without notifying
        _previous_health_status = current_status
        return

    if current_status == _previous_health_status:
        return

    logger.info(
        "System health status changed",
        extra={"from": _previous_health_status, "to": current_status},
    )

    severity_map = {
        "degraded": NotificationSeverityEnum.WARNING,
        "unhealthy": NotificationSeverityEnum.URGENT,
        "healthy": NotificationSeverityEnum.INFO,
    }

    await _notify_admins(
        db=db,
        title=f"Systemstatus: {current_status.upper()}",
        message=(
            f"Systemstatus wechselte von '{_previous_health_status}' "
            f"zu '{current_status}'."
        ),
        severity=severity_map.get(current_status, NotificationSeverityEnum.INFO),
    )

    _previous_health_status = current_status


async def _run_one_cycle() -> None:
    """Run a single monitoring cycle."""
    async with AsyncSessionLocal() as db:
        try:
            health = await SystemHealthService.get_full_health(db)
            current_status: str = health["status"]
            disk: Dict[str, Any] = health["components"].get("disk", {})

            await _check_state_transition(db, current_status)
            await _check_disk(db, disk)
            await _check_backup_age(db)

        except Exception as exc:
            logger.error(
                "System monitor cycle failed",
                extra={"error": str(exc)},
                exc_info=True,
            )

        # Business-level notification scans — run independently of the system
        # health block so a health-check failure does not suppress business alerts.
        for _scan_name, _scan_coro in (
            ("deadline_warnings", NotificationService.check_deadline_warnings(db)),
            ("low_stock_alerts", NotificationService.check_low_stock_alerts(db)),
            ("pickup_reminders", NotificationService.check_pickup_reminders(db)),
            ("fitting_reminders", NotificationService.check_fitting_reminders(db)),
        ):
            try:
                await _scan_coro
            except Exception as exc:
                logger.error(
                    "Notification scan failed",
                    extra={"scan": _scan_name, "error": str(exc)},
                    exc_info=True,
                )


async def system_monitor_loop() -> None:
    """
    Infinite async loop — run a health check cycle every MONITOR_INTERVAL_SECONDS.

    Register this in main.py startup via:
        asyncio.create_task(system_monitor_loop())
    """
    logger.info(
        "System monitor started",
        extra={"interval_seconds": MONITOR_INTERVAL_SECONDS},
    )
    while True:
        await _run_one_cycle()
        await asyncio.sleep(MONITOR_INTERVAL_SECONDS)
