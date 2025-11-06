import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from goldsmith_erp.core.config import settings
from goldsmith_erp.api.routers import auth, orders, materials, customers
from goldsmith_erp.core.pubsub import subscribe_and_forward, publish_event
from goldsmith_erp.middleware import (
    AuditLoggingMiddleware,
    RequestLoggingMiddleware,
    RequestIDMiddleware,
    RateLimitMiddleware,
    SecurityHeadersMiddleware,
    SensitiveDataRedactionMiddleware,
)

# App-Instanz erstellen
app = FastAPI(
    title=settings.APP_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    description="GDPR-compliant ERP system for jewelry manufacturing",
    version="1.0.0",
)

# ═══════════════════════════════════════════════════════════════════════════
# Middleware Stack (order matters - first added = outermost = runs first)
# ═══════════════════════════════════════════════════════════════════════════

# 1. Request ID (outermost - adds ID to all requests)
app.add_middleware(RequestIDMiddleware)

# 2. Request Logging (log all requests)
app.add_middleware(RequestLoggingMiddleware)

# 3. Security Headers (add security headers to all responses)
app.add_middleware(SecurityHeadersMiddleware, production=not settings.DEBUG)

# 4. Sensitive Data Redaction (prevent data leakage)
app.add_middleware(SensitiveDataRedactionMiddleware)

# 5. Rate Limiting (protect against abuse)
app.add_middleware(RateLimitMiddleware)

# 6. GDPR Audit Logging (log customer data access)
app.add_middleware(AuditLoggingMiddleware)

# 7. CORS (should be last/innermost)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Router einbinden
app.include_router(auth.router, prefix=f"{settings.API_V1_STR}", tags=["auth"])
app.include_router(orders.router, prefix=f"{settings.API_V1_STR}/orders", tags=["orders"])
app.include_router(materials.router, prefix=f"{settings.API_V1_STR}/materials", tags=["materials"])
app.include_router(customers.router, prefix=f"{settings.API_V1_STR}/customers", tags=["customers"])

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
        print("WebSocket disconnected")
    finally:
        # Clean up the subscription task when the websocket disconnects
        subscribe_task.cancel()
        try:
            await subscribe_task
        except asyncio.CancelledError:
            print("Subscription task cancelled.")

# Example: Add a test endpoint to trigger a publish
@app.post("/trigger_order_update")
async def trigger_update(message: str = "Test order update!"):
    await publish_event("order_updates", f"Simulated Update: {message}")
    return {"message": "Event published"}

@app.get("/health")
async def health_check():
    return {"status": "ok"}

if __name__ == "__main__":
    uvicorn.run(
        "goldsmith_erp.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG
    )