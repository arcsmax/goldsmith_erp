import asyncio
import logging
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware
import uvicorn
from typing import List

from goldsmith_erp.core.config import settings
from goldsmith_erp.core.logging import setup_logging
from goldsmith_erp.middleware import RequestLoggingMiddleware
from goldsmith_erp.middleware.auth_required import AuthRequiredMiddleware
from goldsmith_erp.middleware.security_headers import SecurityHeadersMiddleware
from goldsmith_erp.api.routers import auth, orders, users, materials, activities, time_tracking, health, customers, metal_inventory, comments, scrap_gold, calendar, invoices, metal_prices, ml, measurements, analytics, notifications, handoffs
from goldsmith_erp.core.pubsub import subscribe_and_forward, publish_event

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
                            }
                        )
                        return JSONResponse(
                            status_code=413,
                            content={
                                "detail": f"Request body too large. Maximum allowed: {self.MAX_REQUEST_SIZE / (1024 * 1024):.1f} MB"
                            }
                        )
                except ValueError:
                    # Invalid Content-Length header
                    logger.warning(
                        "Invalid Content-Length header",
                        extra={"content_length": content_length}
                    )

        return await call_next(request)

# App-Instanz erstellen
app = FastAPI(
    title=settings.APP_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# Add rate limiting state and error handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add security middleware (order matters - from outermost to innermost)
app.add_middleware(AuthRequiredMiddleware)      # Deny-by-default auth check
app.add_middleware(RequestSizeLimitMiddleware)  # Check size first
app.add_middleware(RequestLoggingMiddleware)    # Then log

# CORS-Middleware einrichten
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Security headers middleware (innermost - decorates all responses with security headers)
app.add_middleware(SecurityHeadersMiddleware)

# Router einbinden
app.include_router(health.router, tags=["health"])  # Health checks at root level
app.include_router(auth.router, prefix=f"{settings.API_V1_STR}", tags=["auth"])
app.include_router(users.router, prefix=f"{settings.API_V1_STR}/users", tags=["users"])
app.include_router(customers.router, prefix=f"{settings.API_V1_STR}", tags=["customers"])  # CRM
app.include_router(orders.router, prefix=f"{settings.API_V1_STR}/orders", tags=["orders"])
app.include_router(materials.router, prefix=f"{settings.API_V1_STR}/materials", tags=["materials"])
app.include_router(metal_inventory.router, prefix=f"{settings.API_V1_STR}", tags=["metal-inventory"])  # Metal Inventory Management
app.include_router(activities.router, prefix=f"{settings.API_V1_STR}/activities", tags=["activities"])
app.include_router(time_tracking.router, prefix=f"{settings.API_V1_STR}/time-tracking", tags=["time-tracking"])
app.include_router(comments.router, prefix=f"{settings.API_V1_STR}", tags=["comments"])  # Order Comments
app.include_router(scrap_gold.router, prefix=f"{settings.API_V1_STR}", tags=["scrap-gold"])  # Altgold
app.include_router(calendar.router, prefix=f"{settings.API_V1_STR}/calendar", tags=["calendar"])  # Calendar/Planning
app.include_router(invoices.router, prefix=f"{settings.API_V1_STR}/invoices", tags=["invoices"])  # Rechnungswesen
app.include_router(metal_prices.router, prefix=f"{settings.API_V1_STR}", tags=["metal-prices"])  # Live metal spot prices
app.include_router(ml.router, prefix=f"{settings.API_V1_STR}/ml", tags=["ml"])  # ML predictions and monitoring
app.include_router(measurements.router, prefix=f"{settings.API_V1_STR}", tags=["measurements"])  # Massbibliothek
app.include_router(notifications.router, prefix=f"{settings.API_V1_STR}/notifications", tags=["notifications"])  # In-app notifications
app.include_router(analytics.router, prefix=f"{settings.API_V1_STR}", tags=["analytics"])  # Soll/Ist-Vergleich
app.include_router(handoffs.router, prefix=f"{settings.API_V1_STR}", tags=["handoffs"])  # Stabuebergabe

# WebSocket endpoint with Redis Pub/Sub integration
@app.websocket("/ws/orders")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    # Define the channel to listen to
    channel = "order_updates"
    # Start the task to listen to Redis and forward to this specific websocket
    subscribe_task = asyncio.create_task(
        subscribe_and_forward(websocket, channel)
    )
    try:
        # Keep the connection alive, potentially handle incoming messages if needed
        while True:
            # You might still want to handle incoming WebSocket messages
            # for bidirectional communication
            data = await websocket.receive_text()
            # Process client message if needed, but don't broadcast directly
            # Instead, you could publish to Redis to ensure all systems receive it
            await publish_event(channel, f"Client message: {data}")
    except WebSocketDisconnect:
        logger.info("WebSocket disconnected", extra={"channel": channel})
    finally:
        # Clean up the subscription task when the websocket disconnects
        subscribe_task.cancel()
        try:
            await subscribe_task
        except asyncio.CancelledError:
            logger.debug("Subscription task cancelled", extra={"channel": channel})


# Per-user notification WebSocket — channel: ``notifications:{user_id}``
# The frontend opens this socket for the currently logged-in user.
# JWT authentication is enforced at the HTTP level by AuthRequiredMiddleware
# before the WebSocket upgrade is accepted.
@app.websocket("/ws/notifications/{user_id}")
async def notification_websocket_endpoint(websocket: WebSocket, user_id: int):
    await websocket.accept()
    channel = f"notifications:{user_id}"
    subscribe_task = asyncio.create_task(
        subscribe_and_forward(websocket, channel)
    )
    try:
        while True:
            # Keep connection alive; no client messages expected on this channel
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
            logger.debug(
                "Notification subscription task cancelled",
                extra={"channel": channel},
            )


# Example: Add a test endpoint to trigger a publish
@app.post("/trigger_order_update")
async def trigger_update(message: str = "Test order update!"):
    await publish_event("order_updates", f"Simulated Update: {message}")
    return {"message": "Event published"}

if __name__ == "__main__":
    uvicorn.run(
        "goldsmith_erp.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )