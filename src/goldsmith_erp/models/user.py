from pydantic import BaseModel, EmailStr, ConfigDict, Field, field_validator
from datetime import datetime
from typing import Optional
import re

from goldsmith_erp.db.models import UserRole


class UserBase(BaseModel):
    """Basis-Schema für User mit Input Validation."""
    email: EmailStr = Field(..., description="Valid email address")
    first_name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=100,
        description="First name (1-100 characters)"
    )
    last_name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=100,
        description="Last name (1-100 characters)"
    )

    @field_validator('first_name', 'last_name')
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        """Sanitize names to prevent injection attacks."""
        if v is None:
            return v
        # Strip leading/trailing whitespace
        v = v.strip()
        # Allow only letters, spaces, hyphens, and apostrophes
        if not re.match(r"^[a-zA-ZäöüÄÖÜß\s'-]+$", v):
            raise ValueError(
                "Name contains invalid characters. Only letters, spaces, hyphens, and apostrophes allowed."
            )
        return v


class UserCreate(UserBase):
    """Schema für User-Erstellung mit Passwort-Validierung."""
    password: str = Field(
        ...,
        min_length=8,
        max_length=128,
        description="Password (8-128 characters)"
    )

    @field_validator('password')
    @classmethod
    def validate_password(cls, v: str) -> str:
        """Enforce password strength requirements."""
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if len(v) > 128:
            raise ValueError("Password must be at most 128 characters long")
        # Check for at least one number
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one number")
        # Check for at least one letter
        if not re.search(r"[a-zA-Z]", v):
            raise ValueError("Password must contain at least one letter")
        return v


class UserUpdate(BaseModel):
    """Schema für User-Updates mit optionalen Feldern."""
    email: Optional[EmailStr] = Field(None, description="New email address")
    first_name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=100,
        description="New first name"
    )
    last_name: Optional[str] = Field(
        None,
        min_length=1,
        max_length=100,
        description="New last name"
    )
    password: Optional[str] = Field(
        None,
        min_length=8,
        max_length=128,
        description="New password"
    )
    is_active: Optional[bool] = Field(None, description="Account active status")

    @field_validator('first_name', 'last_name')
    @classmethod
    def validate_name(cls, v: Optional[str]) -> Optional[str]:
        """Sanitize names to prevent injection attacks."""
        if v is None:
            return v
        v = v.strip()
        if not re.match(r"^[a-zA-ZäöüÄÖÜß\s'-]+$", v):
            raise ValueError(
                "Name contains invalid characters. Only letters, spaces, hyphens, and apostrophes allowed."
            )
        return v

    @field_validator('password')
    @classmethod
    def validate_password(cls, v: Optional[str]) -> Optional[str]:
        """Enforce password strength requirements."""
        if v is None:
            return v
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        if len(v) > 128:
            raise ValueError("Password must be at most 128 characters long")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one number")
        if not re.search(r"[a-zA-Z]", v):
            raise ValueError("Password must contain at least one letter")
        return v


class User(UserBase):
    """Schema für User-Anzeige mit RBAC role."""
    id: int
    role: UserRole = Field(default=UserRole.GOLDSMITH, description="User role (admin/goldsmith/viewer)")
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserInDB(User):
    """Internes Schema mit Hash-Passwort."""
    hashed_password: str