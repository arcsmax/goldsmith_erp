from pydantic import BaseModel, EmailStr, ConfigDict, Field, field_validator
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import re

from goldsmith_erp.db.models import UserRole


# ─────────────────────────────────────────────────────────────────────────────
# GDPR Art. 17 — anonymize_user() result + error contract
# ─────────────────────────────────────────────────────────────────────────────
# See docs/superpowers/plans/qr-barcode-workflow/V1.1-ANONYMIZE-USER-CONTRACT.md §5.


@dataclass
class AnonymizationResult:
    """Outcome of a call to `UserService.anonymize_user`.

    The dataclass intentionally carries only non-PII summary data so it is
    safe to log or return as JSON. The raw HMAC tracking token is treated
    as admin-only and is also written to `gdpr_requests.notes`.
    """

    user_id: int
    """Original user id — preserved on the row to satisfy RESTRICT FKs."""

    sentinel_user_id: int
    """Id of the global sentinel row that now owns all anonymised FKs."""

    fk_updates: dict = field(default_factory=dict)
    """Per-table row count of FK references rewritten to the sentinel."""

    tracking_hmac: str = ""
    """Short (16-char) HMAC(salt, user_id) token for audit correlation."""

    gdpr_request_id: int = 0
    """Primary key of the `gdpr_requests` row recorded for this erasure."""

    already_anonymized: bool = False
    """True on an idempotent re-call (no FK updates, no exception)."""


class UserNotFound(Exception):
    """Raised when `anonymize_user` receives an id that does not exist."""


class LastAdminError(Exception):
    """Raised when anonymisation would leave the workshop with zero active admins."""


class SentinelMissing(Exception):
    """Bootstrap error — the global sentinel row was expected but absent.

    Indicates the Slice 0 migration did not run, or the row was manually
    deleted. The service lazily recreates the sentinel to be robust, so
    raising this exception should be a last resort.
    """


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
        if not re.match(r"^[a-zA-ZäöüÄÖÜß\s'\-.]+$", v):
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
        if not re.match(r"^[a-zA-ZäöüÄÖÜß\s'\-.]+$", v):
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