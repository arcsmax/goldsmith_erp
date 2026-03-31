# src/goldsmith_erp/models/__init__.py
"""Pydantic Schemas für API Validation"""

# User Schemas
from .user import (
    UserBase,
    UserCreate,
    UserUpdate,
    User,
    UserInDB,
)

# Order Schemas
from .order import (
    MaterialBase,
    OrderBase,
    OrderCreate,
    OrderUpdate,
    OrderRead,
)

# Material Schemas
from .material import (
    MaterialBase as MaterialBaseSchema,
    MaterialCreate,
    MaterialUpdate,
    MaterialRead as Material,
)

# Activity Schemas
from .activity import (
    ActivityBase,
    ActivityCreate,
    ActivityUpdate,
    ActivityRead,
    ActivityWithStats,
)

# TimeEntry Schemas
from .time_entry import (
    TimeEntryBase,
    TimeEntryStart,
    TimeEntryStop,
    TimeEntryCreate,
    TimeEntryUpdate,
    TimeEntryRead,
    TimeEntryWithDetails,
)

# Interruption Schemas
from .interruption import (
    InterruptionBase,
    InterruptionCreate,
    InterruptionRead,
)

# LocationHistory Schemas
from .location_history import (
    LocationHistoryBase,
    LocationHistoryCreate,
    LocationHistoryRead,
)

# OrderPhoto Schemas
from .order_photo import (
    OrderPhotoBase,
    OrderPhotoCreate,
    OrderPhotoRead,
    OrderPhotoUpload,
)

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
