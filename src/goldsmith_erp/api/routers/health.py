"""
Health check endpoints for monitoring and observability.
"""
import asyncio
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import and_
from sqlalchemy import select as sa_select
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.api.deps import get_current_admin_user
from goldsmith_erp.core.config import settings
from goldsmith_erp.core.pubsub import get_redis_client
from goldsmith_erp.db.models import (
    Notification,
    NotificationSeverityEnum,
    NotificationTypeEnum,
    User,
    UserRole,
)
from goldsmith_erp.db.session import get_db
from goldsmith_erp.middleware.request_metrics import get_metrics
from goldsmith_erp.services.notification_service import NotificationService
from goldsmith_erp.services.system_health_service import SystemHealthService

router = APIRouter()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public health endpoints (no auth)
# ---------------------------------------------------------------------------

@router.get("/health", tags=["health"])
async def basic_health_check(db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """
    Full health check — returns component status, version and uptime.

    Returns HTTP 200 when healthy or degraded, HTTP 503 when unhealthy.
    """
    health = await SystemHealthService.get_full_health(db)
    http_status = (
        status.HTTP_503_SERVICE_UNAVAILABLE
        if health["status"] == "unhealthy"
        else status.HTTP_200_OK
    )
    return JSONResponse(status_code=http_status, content=health)


@router.get("/health/detailed", tags=["health"])
async def detailed_health_check(db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """
    Detailed health check with database and Redis connectivity.
    """
    health_status: Dict[str, Any] = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {}
    }

    overall_healthy = True

    try:
        await db.execute(text("SELECT 1"))
        health_status["checks"]["database"] = {
            "status": "healthy",
            "message": "Database connection successful"
        }
        logger.debug("Health check: Database OK")
    except Exception as e:
        overall_healthy = False
        health_status["checks"]["database"] = {
            "status": "unhealthy",
            "message": f"Database connection failed: {str(e)}"
        }
        logger.error("Health check: Database failed", exc_info=True)

    try:
        async with get_redis_client() as redis:
            await redis.ping()
        health_status["checks"]["redis"] = {
            "status": "healthy",
            "message": "Redis connection successful"
        }
        logger.debug("Health check: Redis OK")
    except Exception as e:
        overall_healthy = False
        health_status["checks"]["redis"] = {
            "status": "unhealthy",
            "message": f"Redis connection failed: {str(e)}"
        }
        logger.error("Health check: Redis failed", exc_info=True)

    health_status["status"] = "healthy" if overall_healthy else "unhealthy"
    status_code = status.HTTP_200_OK if overall_healthy else status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(status_code=status_code, content=health_status)


@router.get("/health/liveness", tags=["health"])
async def liveness_check() -> Dict[str, str]:
    """Kubernetes liveness probe."""
    return {
        "status": "alive",
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/health/readiness", tags=["health"])
async def readiness_check(db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """Kubernetes readiness probe."""
    ready = True
    checks: Dict[str, str] = {}

    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ready"
    except Exception as e:
        ready = False
        checks["database"] = f"not ready: {str(e)}"
        logger.warning(f"Readiness check: Database not ready - {str(e)}")

    try:
        async with get_redis_client() as redis:
            await redis.ping()
        checks["redis"] = "ready"
    except Exception as e:
        ready = False
        checks["redis"] = f"not ready: {str(e)}"
        logger.warning(f"Readiness check: Redis not ready - {str(e)}")

    status_code = status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "ready" if ready else "not ready",
            "timestamp": datetime.utcnow().isoformat(),
            "checks": checks
        }
    )


@router.get("/health/startup", tags=["health"])
async def startup_check(db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """Kubernetes startup probe."""
    started = True
    checks: Dict[str, str] = {}

    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "started"
    except Exception as e:
        started = False
        checks["database"] = f"not started: {str(e)}"

    try:
        async with get_redis_client() as redis:
            await redis.ping()
        checks["redis"] = "started"
    except Exception as e:
        started = False
        checks["redis"] = f"not started: {str(e)}"

    status_code = status.HTTP_200_OK if started else status.HTTP_503_SERVICE_UNAVAILABLE

    return JSONResponse(
        status_code=status_code,
        content={
            "status": "started" if started else "not started",
            "timestamp": datetime.utcnow().isoformat(),
            "checks": checks
        }
    )


@router.get("/version", tags=["health"])
async def version_info() -> Dict[str, Any]:
    """Application version and configuration information."""
    return {
        "app_name": settings.APP_NAME,
        "api_version": settings.API_V1_STR,
        "debug_mode": settings.DEBUG,
        "timestamp": datetime.utcnow().isoformat(),
    }


# ---------------------------------------------------------------------------
# Admin-only endpoints
# ---------------------------------------------------------------------------

@router.get(
    f"{settings.API_V1_STR}/admin/system-info",
    tags=["admin"],
    summary="Full system information (ADMIN only)",
)
async def get_system_info(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user),
) -> Dict[str, Any]:
    """
    Full health + business metrics + backup info + request metrics.
    Restricted to ADMIN role.
    """
    health = await SystemHealthService.get_full_health(db)
    business_metrics = await SystemHealthService.get_business_metrics(db)
    backup_info = SystemHealthService.get_last_backup_info()
    request_metrics = get_metrics()

    return {
        "health": health,
        "business_metrics": business_metrics,
        "backup": backup_info,
        "request_metrics": request_metrics,
    }


async def _run_backup_script(script_path: str) -> None:
    """Run the backup shell script using subprocess (args list, no shell injection)."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "bash",
            script_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        logger.info(
            "Backup script completed",
            extra={
                "returncode": proc.returncode,
                "stdout_tail": stdout.decode(errors="replace")[-500:],
                "stderr_tail": stderr.decode(errors="replace")[-500:],
            },
        )
    except Exception as exc:
        logger.error(
            "Backup script error",
            extra={"error": str(exc)},
            exc_info=True,
        )


@router.post(
    f"{settings.API_V1_STR}/admin/trigger-backup",
    tags=["admin"],
    summary="Trigger database backup (ADMIN only)",
    status_code=status.HTTP_202_ACCEPTED,
)
async def trigger_backup(
    current_user: User = Depends(get_current_admin_user),
) -> Dict[str, str]:
    """
    Trigger the backup script asynchronously.  Returns immediately with
    {"status": "started"}.  Restricted to ADMIN role.
    """
    script_candidates = [
        "/app/scripts/backup.sh",
        str(Path(__file__).parents[5] / "scripts" / "backup.sh"),
    ]

    script_path: Optional[str] = None
    for candidate in script_candidates:
        if os.path.isfile(candidate):
            script_path = candidate
            break

    if script_path is None:
        logger.warning("Backup script not found — skipping trigger")
        return {"status": "started", "note": "backup script not found"}

    asyncio.create_task(_run_backup_script(script_path))
    logger.info("Backup triggered by admin", extra={"user_id": current_user.id})
    return {"status": "started"}


@router.post(
    f"{settings.API_V1_STR}/admin/notify-backup",
    tags=["admin"],
    summary="Receive backup result notification (internal, no auth)",
    status_code=status.HTTP_200_OK,
)
async def notify_backup(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """
    Internal endpoint called by backup.sh after completion.
    No user auth — restricted to localhost callers only.
    Creates a SYSTEM notification for all ADMIN users.

    Expected JSON body:
        {"status": "success"|"failed", "filename": str, "size_mb": float, "message": str}
    """
    client_host = request.client.host if request.client else "unknown"
    if client_host not in ("127.0.0.1", "::1", "localhost"):
        logger.warning(
            "notify-backup called from non-localhost",
            extra={"client_host": client_host},
        )
        return {"status": "ignored", "reason": "not localhost"}

    try:
        body: Dict[str, Any] = await request.json()
    except Exception:
        body = {}

    backup_status = body.get("status", "unknown")
    filename = body.get("filename", "unbekannt")
    size_mb = float(body.get("size_mb", 0.0))
    message = body.get("message", "")

    if backup_status == "success":
        severity = NotificationSeverityEnum.INFO
        title = "Backup erfolgreich"
        text = f"Backup abgeschlossen: {filename} ({size_mb:.1f} MB). {message}"
    else:
        severity = NotificationSeverityEnum.WARNING
        title = "Backup fehlgeschlagen"
        text = f"Backup-Fehler für {filename}. {message}"

    admins_stmt = sa_select(User).where(
        and_(User.is_active.is_(True), User.role == UserRole.ADMIN)
    )
    admins_result = await db.execute(admins_stmt)
    admins = admins_result.scalars().all()

    created = 0
    for admin in admins:
        try:
            await NotificationService.create_notification(
                db=db,
                user_id=admin.id,
                title=title,
                message=text,
                notification_type=NotificationTypeEnum.SYSTEM,
                severity=severity,
            )
            created += 1
        except Exception as exc:
            logger.error(
                "Failed to create backup notification",
                extra={"user_id": admin.id, "error": str(exc)},
            )

    logger.info(
        "Backup notification sent",
        extra={"backup_status": backup_status, "notifications_created": created},
    )
    return {"status": "ok", "notifications_created": created}
