import asyncio
import logging
import os
from pathlib import Path
from typing import List

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from jose import JWTError, jwt
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware

from goldsmith_erp.api.routers import (
    activities,
    admin_email,
    admin_scan_metrics,
    analytics,
    auth,
    calendar,
    comments,
    consultations,
    customer_portal,
    customer_updates,
    customers,
    estimator,
    hallmarks,
    handoffs,
    health,
)
from goldsmith_erp.api.routers import imports as imports_router
from goldsmith_erp.api.routers import (
    invoices,
    materials,
    measurements,
    metal_inventory,
    metal_prices,
    metal_types,
    ml,
    notifications,
    orders,
    photos,
    quotes,
    repairs,
)
from goldsmith_erp.api.routers import scanner as scanner_router
from goldsmith_erp.api.routers import scrap_gold
from goldsmith_erp.api.routers import theme as theme_router
from goldsmith_erp.api.routers import time_tracking, users, valuations
from goldsmith_erp.core.config import settings
from goldsmith_erp.core.encryption import EncryptionError, check_encryption_configured
from goldsmith_erp.core.logging import setup_logging
from goldsmith_erp.core.pubsub import publish_event, subscribe_and_forward
from goldsmith_erp.core.security import ALGORITHM
from goldsmith_erp.middleware import RequestLoggingMiddleware, RequestMetricsMiddleware
from goldsmith_erp.middleware.audit_logging import AuditLoggingMiddleware
from goldsmith_erp.middleware.auth_required import AuthRequiredMiddleware
from goldsmith_erp.middleware.security_headers import SecurityHeadersMiddleware
from goldsmith_erp.services.system_monitor import system_monitor_loop

# Setup structured logging
setup_logging()
logger = logging.getLogger(__name__)

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)


# Request Size Limiting Middleware (DoS Protection)
class RequestSizeLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware to limit request body size and prevent DoS attacks.

    Rejects requests with Content-Length exceeding MAX_REQUEST_SIZE.
    """

    MAX_REQUEST_SIZE = 10 * 1024 * 1024  # 10 MB

    async def dispatch(self, request: Request, call_next):
        """Check request size before processing."""
        if request.method in ["POST", "PUT", "PATCH"]:
            content_length = request.headers.get("content-length")

            if content_length:
                try:
                    content_length_int = int(content_length)
                    if content_length_int > self.MAX_REQUEST_SIZE:
                        logger.warning(
                            "Request body too large",
                            extra={
                                "content_length": content_length_int,
                                "max_allowed": self.MAX_REQUEST_SIZE,
                                "path": request.url.path,
                                "method": request.method,
                            },
                        )
                        return JSONResponse(
                            status_code=413,
                            content={"detail": "Anfrage zu groß. Maximum: 10 MB."},
                        )
                except ValueError:
                    # Invalid Content-Length header
                    logger.warning(
                        "Invalid Content-Length header",
                        extra={"content_length": content_length},
                    )

        return await call_next(request)


# App-Instanz erstellen
app = FastAPI(
    title=settings.APP_NAME, openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# Ensure uploads directory exists (photos served via authenticated router endpoints)
_uploads_dir = Path(settings.PHOTO_STORAGE_PATH).parent  # ./uploads
_uploads_dir.mkdir(parents=True, exist_ok=True)

# Add rate limiting state and error handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add security middleware (order matters — Starlette runs middleware in
# REVERSE order of add(), so the LAST add() is the OUTERMOST / first to run
# on an incoming request).  Target order (outer → inner):
#   AuthRequiredMiddleware   — reject unauthenticated + populate user_id
#   AuditLoggingMiddleware   — read user_id written by auth, write audit row
#   RequestSizeLimitMiddleware
#   RequestLoggingMiddleware
#   RequestMetricsMiddleware
# That means we add() them in the inverse order below.
app.add_middleware(
    AuditLoggingMiddleware
)  # GDPR Art. 30 audit (reads user_id from state)
app.add_middleware(
    AuthRequiredMiddleware
)  # Deny-by-default auth check + sets request.state.user_id
app.add_middleware(RequestSizeLimitMiddleware)  # Check size first
app.add_middleware(RequestLoggingMiddleware)  # Then log
app.add_middleware(
    RequestMetricsMiddleware
)  # Lightweight request metrics (innermost before CORS)

# CORS-Middleware einrichten
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
)

# Security headers middleware (innermost - decorates all responses with security headers)
app.add_middleware(SecurityHeadersMiddleware)

# Router einbinden
app.include_router(health.router, tags=["health"])  # Health checks at root level
app.include_router(auth.router, prefix=f"{settings.API_V1_STR}", tags=["auth"])
app.include_router(users.router, prefix=f"{settings.API_V1_STR}/users", tags=["users"])
app.include_router(
    customers.router, prefix=f"{settings.API_V1_STR}", tags=["customers"]
)  # CRM
app.include_router(
    orders.router, prefix=f"{settings.API_V1_STR}/orders", tags=["orders"]
)
app.include_router(
    materials.router, prefix=f"{settings.API_V1_STR}/materials", tags=["materials"]
)
app.include_router(
    metal_inventory.router, prefix=f"{settings.API_V1_STR}", tags=["metal-inventory"]
)  # Metal Inventory Management
app.include_router(
    activities.router, prefix=f"{settings.API_V1_STR}/activities", tags=["activities"]
)
app.include_router(
    time_tracking.router,
    prefix=f"{settings.API_V1_STR}/time-tracking",
    tags=["time-tracking"],
)
app.include_router(
    comments.router, prefix=f"{settings.API_V1_STR}", tags=["comments"]
)  # Order Comments
app.include_router(
    scrap_gold.router, prefix=f"{settings.API_V1_STR}", tags=["scrap-gold"]
)  # Altgold
app.include_router(
    calendar.router, prefix=f"{settings.API_V1_STR}/calendar", tags=["calendar"]
)  # Calendar/Planning
app.include_router(
    invoices.router, prefix=f"{settings.API_V1_STR}/invoices", tags=["invoices"]
)  # Rechnungswesen
app.include_router(
    metal_prices.router, prefix=f"{settings.API_V1_STR}", tags=["metal-prices"]
)  # Live metal spot prices
app.include_router(
    ml.router, prefix=f"{settings.API_V1_STR}/ml", tags=["ml"]
)  # ML predictions and monitoring
app.include_router(
    measurements.router, prefix=f"{settings.API_V1_STR}", tags=["measurements"]
)  # Massbibliothek
app.include_router(
    notifications.router,
    prefix=f"{settings.API_V1_STR}/notifications",
    tags=["notifications"],
)  # In-app notifications
app.include_router(
    analytics.router, prefix=f"{settings.API_V1_STR}", tags=["analytics"]
)  # Soll/Ist-Vergleich
app.include_router(
    handoffs.router, prefix=f"{settings.API_V1_STR}", tags=["handoffs"]
)  # Stabuebergabe
app.include_router(
    photos.router, prefix=f"{settings.API_V1_STR}", tags=["photos"]
)  # Order photo documentation
app.include_router(
    metal_types.router, prefix=f"{settings.API_V1_STR}", tags=["metal-types"]
)  # Custom metal type management
app.include_router(
    quotes.router, prefix=f"{settings.API_V1_STR}/quotes", tags=["quotes"]
)  # Kostenvoranschlag
app.include_router(
    repairs.router, prefix=f"{settings.API_V1_STR}/repairs", tags=["repairs"]
)  # Repair tracking (Reparaturverwaltung)
app.include_router(
    hallmarks.router, prefix=f"{settings.API_V1_STR}", tags=["hallmarks"]
)  # Hallmarking / Punzierung
app.include_router(
    valuations.router, prefix=f"{settings.API_V1_STR}", tags=["valuations"]
)  # Insurance valuation certificates / Wertgutachten
app.include_router(
    consultations.router,
    prefix=f"{settings.API_V1_STR}/consultations",
    tags=["consultations"],
)  # Beratung & Annahme (V1.1)
app.include_router(
    admin_email.router, prefix=f"{settings.API_V1_STR}", tags=["admin-email"]
)  # Email/SMTP admin configuration
app.include_router(
    admin_scan_metrics.router,
    prefix=f"{settings.API_V1_STR}",
    tags=["admin-scan-metrics"],
)  # V1.1 Slice 13 — scan-adoption dashboard data
app.include_router(
    customer_portal.router,
    prefix=f"{settings.API_V1_STR}/portal",
    tags=["customer-portal"],
)  # Public self-service portal
app.include_router(
    theme_router.router, prefix=f"{settings.API_V1_STR}", tags=["theme"]
)  # Admin-configurable branding (GET public, PUT ADMIN-only)
app.include_router(
    imports_router.router, prefix=f"{settings.API_V1_STR}", tags=["import"]
)  # Bulk CSV data import (ADMIN-only)
app.include_router(
    scanner_router.router, prefix=f"{settings.API_V1_STR}/scan", tags=["scanner"]
)  # V1.1 QR/Barcode scanner workflow
app.include_router(
    customer_updates.router,
    prefix=f"{settings.API_V1_STR}",
    tags=["customer-updates"],
)  # V1.2 Kundeninfo + §649 BGB Kostenfreigabe (mixed /orders, /updates,
#    /cost-changes path roots — bare API prefix, handoffs.py precedent)
app.include_router(
    estimator.router,
    prefix=f"{settings.API_V1_STR}/estimates",
    tags=["estimator"],
)  # V1.3 Phase 1 — statistical labor estimator (financial, ADMIN/GOLDSMITH only)


async def _authenticate_websocket(websocket: WebSocket) -> int | None:
    """Extract and validate JWT from WebSocket cookie or query param."""
    token = websocket.cookies.get("access_token")
    if not token:
        token = websocket.query_params.get("token")
    if not token:
        return None
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("sub")
        return int(user_id) if user_id else None
    except (JWTError, ValueError, TypeError):
        return None


# WebSocket endpoint with Redis Pub/Sub integration
@app.websocket("/ws/orders")
async def websocket_endpoint(websocket: WebSocket):
    user_id = await _authenticate_websocket(websocket)
    if user_id is None:
        await websocket.close(code=4001, reason="Authentication required")
        return
    await websocket.accept()
    channel = "order_updates"
    subscribe_task = asyncio.create_task(subscribe_and_forward(websocket, channel))
    try:
        while True:
            data = await websocket.receive_text()
            logger.debug(
                "WS client message", extra={"channel": channel, "user_id": user_id}
            )
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected", extra={"channel": channel})
    finally:
        subscribe_task.cancel()
        try:
            await subscribe_task
        except asyncio.CancelledError:
            pass


# Per-user notification WebSocket — channel: ``notifications:{user_id}``
# The frontend opens this socket for the currently logged-in user.
# JWT authentication is enforced at the HTTP level by AuthRequiredMiddleware
# before the WebSocket upgrade is accepted.
@app.websocket("/ws/notifications/{user_id}")
async def notification_websocket_endpoint(websocket: WebSocket, user_id: int):
    authenticated_user_id = await _authenticate_websocket(websocket)
    if authenticated_user_id is None or authenticated_user_id != user_id:
        await websocket.close(code=4001, reason="Authentication required")
        return
    await websocket.accept()
    channel = f"notifications:{user_id}"
    subscribe_task = asyncio.create_task(subscribe_and_forward(websocket, channel))
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        logger.info(
            "Notification WebSocket disconnected",
            extra={"channel": channel, "user_id": user_id},
        )
    finally:
        subscribe_task.cancel()
        try:
            await subscribe_task
        except asyncio.CancelledError:
            pass


@app.on_event("startup")
async def start_background_tasks() -> None:
    """Register long-running background tasks on application startup."""
    asyncio.create_task(system_monitor_loop())
    logger.info("System monitor background task registered")


@app.on_event("startup")
async def _verify_encryption_health() -> None:
    """Fail-loud check on the encryption pipeline (C4 / GDPR Art. 32).

    Called after config validation has already enforced that
    ``ENCRYPTION_KEY`` is set in production. This check additionally
    verifies the key is Fernet-shaped — catches typos / corrupted secrets
    that config validation alone cannot spot.

    In production (``DEBUG=False``) a bad key raises ``EncryptionError``
    and aborts startup — we refuse to serve if PII cannot be protected.
    In DEBUG mode we log CRITICAL and continue so local test runs without
    encryption don't block developers.
    """
    try:
        check_encryption_configured()
        logger.info(
            "encryption_health",
            extra={"audit": True, "status": "ok"},
        )
    except EncryptionError as exc:
        logger.critical(
            "encryption_health_failed",
            extra={"audit": True, "status": "critical", "error": str(exc)},
        )
        if not settings.DEBUG:
            # Production: refuse to start with a broken encryption path.
            raise


if __name__ == "__main__":
    uvicorn.run(
        "goldsmith_erp.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
