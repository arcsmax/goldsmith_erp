import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from typing import List

from goldsmith_erp.core.config import settings
from goldsmith_erp.api.routers import auth, orders
from goldsmith_erp.core.pubsub import subscribe_and_forward, publish_event  # Import pubsub functions
import enum

from sqlalchemy import (
    Column,
    Integer,
    String,
    Float,
    DateTime,
    ForeignKey,
    Boolean,
    Enum as SAEnum,
)
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class OrderStatusEnum(str, enum.Enum):
    """Enumerated order statuses for consistency and validation."""
    NEW = "new"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    DELIVERED = "delivered"


class User(Base):
    """User account model."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    full_name = Column(String, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    # ... other fields ...


class Order(Base):
    """Order model with status enum."""
    __tablename__ = "orders"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    price = Column(Float, nullable=True)
    created_at = Column(DateTime, nullable=False)
    status = Column(
        SAEnum(OrderStatusEnum),
        default=OrderStatusEnum.NEW,
        nullable=False,
    )

# App-Instanz erstellen
app = FastAPI(
    title=settings.APP_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json"
)

# CORS-Middleware einrichten
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