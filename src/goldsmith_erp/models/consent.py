"""Pydantic schemas for customer consent records (GDPR-02 / GDPR-11).

The enums live here (not in ``db.models``) on purpose: the ORM column is a
plain string, and importing ``db.models`` from a Pydantic module at import
time re-creates the circular import documented on
``models.customer.CustomerOrderExport``.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class ConsentPurpose(str, Enum):
    """What the customer agreed to."""

    HEALTH_DATA = "health_data"  # Art. 9 Abs. 2 lit. a — Allergien
    PHOTO_USE = "photo_use"  # Fotos des Schmuckstücks (Portfolio, Social Media)
    EMAIL_CONTACT = "email_contact"  # Statusmeldungen per E-Mail
    MARKETING = "marketing"  # Werbung, Geburtstagsgrüße


class ConsentMethod(str, Enum):
    """How the consent was given (evidence for Art. 7 Abs. 1)."""

    IN_PERSON = "in_person"
    WRITTEN = "written"
    PORTAL = "portal"


class ConsentGrant(BaseModel):
    """Request body for ``POST /customers/{id}/consents``."""

    model_config = ConfigDict(extra="forbid")

    purpose: ConsentPurpose
    method: ConsentMethod
    wording_version: Optional[str] = Field(
        None,
        max_length=32,
        description="Version of the consent text shown to the customer",
    )
    note: Optional[str] = Field(None, max_length=500)


class ConsentRead(BaseModel):
    """One consent record as returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    purpose: ConsentPurpose
    method: ConsentMethod
    wording_version: Optional[str] = None
    granted_at: datetime
    revoked_at: Optional[datetime] = None
    recorded_by_user_id: Optional[int] = None
    revoked_by_user_id: Optional[int] = None
    note: Optional[str] = None


class ConsentExport(BaseModel):
    """One entry in the Art. 15 export's ``consents`` list."""

    model_config = ConfigDict(extra="forbid")

    purpose: str
    method: str
    wording_version: Optional[str] = None
    granted_at: Optional[str] = None
    revoked_at: Optional[str] = None
    note: Optional[str] = None
