# src/goldsmith_erp/services/system_health_service.py
"""
System health monitoring service.

Provides health checks for database, Redis, and disk, plus business metrics
and backup status — aggregated into a single full-health report used by the
admin dashboard and system monitor.
"""
from __future__ import annotations

import glob
import logging
import os
import shutil
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.core.config import settings
from goldsmith_erp.core.pubsub import get_redis_client
from goldsmith_erp.db.models import Order, OrderStatusEnum

logger = logging.getLogger(__name__)

# Module-level start time — used to calculate uptime
_app_start_time: float = time.time()


class SystemHealthService:
    """Static-method service.  All methods are async where I/O is involved."""

    # ------------------------------------------------------------------
    # Individual component checks
    # ------------------------------------------------------------------

    @staticmethod
    async def check_database(db: AsyncSession) -> Dict[str, Any]:
        """
        Execute SELECT 1 and return status + latency.

        Returns:
            {"status": "up"|"down", "latency_ms": float}
        """
        start = time.monotonic()
        try:
            await db.execute(text("SELECT 1"))
            latency_ms = round((time.monotonic() - start) * 1000, 2)
            return {"status": "up", "latency_ms": latency_ms}
        except Exception as exc:
            latency_ms = round((time.monotonic() - start) * 1000, 2)
            logger.error(
                "Database health check failed",
                extra={"error": str(exc), "latency_ms": latency_ms},
            )
            return {"status": "down", "latency_ms": latency_ms, "error": str(exc)}

    @staticmethod
    async def check_redis() -> Dict[str, Any]:
        """
        Ping Redis, gather memory info, return status + latency + memory.

        Returns:
            {"status": "up"|"down", "latency_ms": float, "used_memory_mb": float}
        """
        start = time.monotonic()
        try:
            async with get_redis_client() as redis:
                await redis.ping()
                latency_ms = round((time.monotonic() - start) * 1000, 2)
                info: Dict[str, Any] = await redis.info("memory")
                used_bytes = int(info.get("used_memory", 0))
                used_memory_mb = round(used_bytes / (1024 * 1024), 2)
            return {
                "status": "up",
                "latency_ms": latency_ms,
                "used_memory_mb": used_memory_mb,
            }
        except Exception as exc:
            latency_ms = round((time.monotonic() - start) * 1000, 2)
            logger.error(
                "Redis health check failed",
                extra={"error": str(exc), "latency_ms": latency_ms},
            )
            return {
                "status": "down",
                "latency_ms": latency_ms,
                "used_memory_mb": 0.0,
                "error": str(exc),
            }

    @staticmethod
    def check_disk() -> Dict[str, Any]:
        """
        Check root disk usage via shutil.disk_usage.

        Thresholds:
          - >= 95 % used → critical
          - >= 80 % used → warning
          - < 80 %        → ok

        Returns:
            {"status": "ok"|"warning"|"critical", "free_gb": float, "total_gb": float, "used_percent": float}
        """
        try:
            usage = shutil.disk_usage("/")
            total_gb = round(usage.total / (1024 ** 3), 2)
            free_gb = round(usage.free / (1024 ** 3), 2)
            used_percent = round((usage.used / usage.total) * 100, 1)

            if used_percent >= 95.0:
                disk_status = "critical"
            elif used_percent >= 80.0:
                disk_status = "warning"
            else:
                disk_status = "ok"

            return {
                "status": disk_status,
                "free_gb": free_gb,
                "total_gb": total_gb,
                "used_percent": used_percent,
            }
        except Exception as exc:
            logger.error("Disk health check failed", extra={"error": str(exc)})
            return {
                "status": "critical",
                "free_gb": 0.0,
                "total_gb": 0.0,
                "used_percent": 100.0,
                "error": str(exc),
            }

    @staticmethod
    def get_uptime() -> float:
        """Return seconds since module was first imported (proxy for app start)."""
        return round(time.time() - _app_start_time, 1)

    # ------------------------------------------------------------------
    # Aggregated health
    # ------------------------------------------------------------------

    @staticmethod
    async def get_full_health(db: AsyncSession) -> Dict[str, Any]:
        """
        Combine all component checks into one report.

        Overall status:
          - healthy   → all components up/ok
          - degraded  → at least one component has a warning condition
          - unhealthy → at least one component is down/critical

        Returns:
            {
                "status": "healthy"|"degraded"|"unhealthy",
                "components": { "database": {...}, "redis": {...}, "disk": {...} },
                "version": str,
                "uptime_seconds": float,
                "timestamp": str,
            }
        """
        db_check, redis_check = await _gather_safely(
            SystemHealthService.check_database(db),
            SystemHealthService.check_redis(),
        )
        disk_check = SystemHealthService.check_disk()

        # Determine worst status
        component_statuses = [
            db_check["status"],
            redis_check["status"],
            disk_check["status"],
        ]

        if "down" in component_statuses or "critical" in component_statuses:
            overall = "unhealthy"
        elif "warning" in component_statuses:
            overall = "degraded"
        else:
            overall = "healthy"

        return {
            "status": overall,
            "components": {
                "database": db_check,
                "redis": redis_check,
                "disk": disk_check,
            },
            "version": settings.APP_VERSION,
            "uptime_seconds": SystemHealthService.get_uptime(),
            "timestamp": datetime.utcnow().isoformat(),
        }

    # ------------------------------------------------------------------
    # Business metrics
    # ------------------------------------------------------------------

    @staticmethod
    async def get_business_metrics(db: AsyncSession) -> Dict[str, Any]:
        """
        Query DB for basic order metrics for the current calendar month.

        Returns:
            {"orders_this_month": int, "completed_this_month": int}
        """
        try:
            now = datetime.utcnow()
            month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

            # Orders created this month
            orders_stmt = select(func.count(Order.id)).where(
                Order.created_at >= month_start
            )
            orders_result = await db.execute(orders_stmt)
            orders_this_month: int = orders_result.scalar_one() or 0

            # Orders completed this month (completed_at is set when status changes)
            completed_stmt = select(func.count(Order.id)).where(
                Order.completed_at >= month_start,
                Order.status.in_([
                    OrderStatusEnum.COMPLETED,
                    OrderStatusEnum.DELIVERED,
                ]),
            )
            completed_result = await db.execute(completed_stmt)
            completed_this_month: int = completed_result.scalar_one() or 0

            return {
                "orders_this_month": orders_this_month,
                "completed_this_month": completed_this_month,
            }
        except Exception as exc:
            logger.error("Business metrics query failed", extra={"error": str(exc)})
            return {
                "orders_this_month": 0,
                "completed_this_month": 0,
                "error": str(exc),
            }

    # ------------------------------------------------------------------
    # Backup info
    # ------------------------------------------------------------------

    @staticmethod
    def get_last_backup_info() -> Dict[str, Any]:
        """
        Scan BACKUP_DIR for the newest goldsmith_erp_*.sql.gz file.

        Returns:
            {
                "filename": str | None,
                "size_mb": float,
                "timestamp": str | None,   # ISO 8601
                "backup_count": int,
                "backup_dir": str,
            }
        """
        backup_dir = Path(os.path.expanduser(settings.BACKUP_DIR))
        try:
            pattern = str(backup_dir / "goldsmith_erp_*.sql.gz")
            matches = sorted(glob.glob(pattern))

            if not matches:
                return {
                    "filename": None,
                    "size_mb": 0.0,
                    "timestamp": None,
                    "backup_count": 0,
                    "backup_dir": str(backup_dir),
                }

            newest = matches[-1]
            stat = os.stat(newest)
            size_mb = round(stat.st_size / (1024 * 1024), 2)
            timestamp = datetime.fromtimestamp(stat.st_mtime).isoformat()

            return {
                "filename": os.path.basename(newest),
                "size_mb": size_mb,
                "timestamp": timestamp,
                "backup_count": len(matches),
                "backup_dir": str(backup_dir),
            }
        except Exception as exc:
            logger.error(
                "Backup info scan failed",
                extra={"backup_dir": str(backup_dir), "error": str(exc)},
            )
            return {
                "filename": None,
                "size_mb": 0.0,
                "timestamp": None,
                "backup_count": 0,
                "backup_dir": str(backup_dir),
                "error": str(exc),
            }


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

async def _gather_safely(*coros):
    """Run coroutines concurrently, return results regardless of exceptions."""
    import asyncio

    results = await asyncio.gather(*coros, return_exceptions=True)
    safe = []
    for r in results:
        if isinstance(r, Exception):
            safe.append({"status": "down", "latency_ms": 0.0, "error": str(r)})
        else:
            safe.append(r)
    return safe
