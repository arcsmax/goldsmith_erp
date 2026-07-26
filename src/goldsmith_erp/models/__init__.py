# src/goldsmith_erp/models/__init__.py
"""Pydantic Schemas für API Validation"""

# Activity Schemas
from .activity import (
    ActivityBase,
    ActivityCreate,
    ActivityRead,
    ActivityUpdate,
    ActivityWithStats,
)

# Interruption Schemas
from .interruption import InterruptionBase, InterruptionCreate, InterruptionRead

# LocationHistory Schemas
from .location_history import (
    LocationHistoryBase,
    LocationHistoryCreate,
    LocationHistoryRead,
)

# Material Schemas
from .material import MaterialBase as MaterialBaseSchema
from .material import MaterialCreate
from .material import MaterialRead as Material
from .material import MaterialUpdate

# Order Schemas
from .order import MaterialBase, OrderBase, OrderCreate, OrderRead, OrderUpdate

# OrderComment Schemas
from .order_comment import OrderCommentCreate, OrderCommentRead, OrderCommentUpdate

# OrderPhoto Schemas
from .order_photo import (
    OrderPhotoBase,
    OrderPhotoCreate,
    OrderPhotoRead,
    OrderPhotoUpload,
)

# TimeEntry Schemas
from .time_entry import (
    TimeEntryBase,
    TimeEntryCreate,
    TimeEntryRead,
    TimeEntryStart,
    TimeEntryStop,
    TimeEntryUpdate,
    TimeEntryWithDetails,
)

# User Schemas
from .user import User, UserBase, UserCreate, UserInDB, UserUpdate

__all__ = [
    # User
    "UserBase",
    "UserCreate",
    "UserUpdate",
    "User",
    "UserInDB",
    # Order
    "MaterialBase",
    "OrderBase",
    "OrderCreate",
    "OrderUpdate",
    "OrderRead",
    # Material
    "MaterialBaseSchema",
    "MaterialCreate",
    "MaterialUpdate",
    "Material",
    # Activity
    "ActivityBase",
    "ActivityCreate",
    "ActivityUpdate",
    "ActivityRead",
    "ActivityWithStats",
    # TimeEntry
    "TimeEntryBase",
    "TimeEntryStart",
    "TimeEntryStop",
    "TimeEntryCreate",
    "TimeEntryUpdate",
    "TimeEntryRead",
    "TimeEntryWithDetails",
    # Interruption
    "InterruptionBase",
    "InterruptionCreate",
    "InterruptionRead",
    # LocationHistory
    "LocationHistoryBase",
    "LocationHistoryCreate",
    "LocationHistoryRead",
    # OrderPhoto
    "OrderPhotoBase",
    "OrderPhotoCreate",
    "OrderPhotoRead",
    "OrderPhotoUpload",
]
