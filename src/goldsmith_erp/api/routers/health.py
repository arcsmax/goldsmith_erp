"""
Health check endpoints for monitoring and observability.
"""
import logging
from typing import Dict, Any
from datetime import datetime

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.session import get_db
from goldsmith_erp.core.pubsub import get_redis_client
from goldsmith_erp.core.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/health", tags=["health"])
async def basic_health_check() -> Dict[str, str]:
    """
    Basic health check - API is responding.
    
    Returns:
        dict: Basic status
    """
    return {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/health/detailed", tags=["health"])
async def detailed_health_check(db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """
    Detailed health check with database and Redis connectivity.
    
    Returns:
        JSONResponse: Detailed health status
    """
    health_status = {
        "status": "healthy",
        "timestamp": datetime.utcnow().isoformat(),
        "checks": {}
    }
    
    overall_healthy = True
    
    # Check Database
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
        logger.error(f"Health check: Database failed", exc_info=True)
    
    # Check Redis
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
        logger.error(f"Health check: Redis failed", exc_info=True)
    
    # Overall status
    health_status["status"] = "healthy" if overall_healthy else "unhealthy"
    
    # Return appropriate HTTP status code
    status_code = status.HTTP_200_OK if overall_healthy else status.HTTP_503_SERVICE_UNAVAILABLE
    
    return JSONResponse(
        status_code=status_code,
        content=health_status
    )


@router.get("/health/liveness", tags=["health"])
async def liveness_check() -> Dict[str, str]:
    """
    Kubernetes liveness probe - is the application running?
    
    Returns:
        dict: Liveness status
    """
    return {
        "status": "alive",
        "timestamp": datetime.utcnow().isoformat()
    }


@router.get("/health/readiness", tags=["health"])
async def readiness_check(db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """
    Kubernetes readiness probe - is the application ready to serve traffic?
    
    Checks critical dependencies (database, redis) before marking as ready.
    
    Returns:
        JSONResponse: Readiness status
    """
    ready = True
    checks = {}
    
    # Check Database
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ready"
    except Exception as e:
        ready = False
        checks["database"] = f"not ready: {str(e)}"
        logger.warning(f"Readiness check: Database not ready - {str(e)}")
    
    # Check Redis
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
    """
    Kubernetes startup probe - has the application finished starting?
    
    Returns:
        JSONResponse: Startup status
    """
    started = True
    checks = {}
    
    # Check Database is accessible
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "started"
    except Exception as e:
        started = False
        checks["database"] = f"not started: {str(e)}"
    
    # Check Redis is accessible
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
    """
    Get application version and configuration information.
    
    Returns:
        dict: Version and config info
    """
    return {
        "app_name": settings.APP_NAME,
        "api_version": settings.API_V1_STR,
        "debug_mode": settings.DEBUG,
        "timestamp": datetime.utcnow().isoformat(),
    }
