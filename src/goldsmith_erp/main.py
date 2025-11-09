import asyncio
import logging
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
import uvicorn
from typing import List

from goldsmith_erp.core.config import settings
from goldsmith_erp.core.logging import setup_logging
from goldsmith_erp.middleware import RequestLoggingMiddleware
from goldsmith_erp.api.routers import auth, orders, users, materials, activities, time_tracking, health
from goldsmith_erp.core.pubsub import subscribe_and_forward, publish_event

# Setup structured logging
setup_logging()
logger = logging.getLogger(__name__)

# Initialize rate limiter
limiter = Limiter(key_func=get_remote_address)

# App-Instanz erstellen
app = FastAPI(
    title=settings.APP_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# Add rate limiting state and error handler
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Add request logging middleware (must be before CORS)
app.add_middleware(RequestLoggingMiddleware)

# CORS-Middleware einrichten
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Router einbinden
app.include_router(health.router, tags=["health"])  # Health checks at root level
app.include_router(auth.router, prefix=f"{settings.API_V1_STR}", tags=["auth"])
app.include_router(users.router, prefix=f"{settings.API_V1_STR}/users", tags=["users"])
app.include_router(orders.router, prefix=f"{settings.API_V1_STR}/orders", tags=["orders"])
app.include_router(materials.router, prefix=f"{settings.API_V1_STR}/materials", tags=["materials"])
app.include_router(activities.router, prefix=f"{settings.API_V1_STR}/activities", tags=["activities"])
app.include_router(time_tracking.router, prefix=f"{settings.API_V1_STR}/time-tracking", tags=["time-tracking"])

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