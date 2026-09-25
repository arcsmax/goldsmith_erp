# src/goldsmith_erp/models/media_asset.py
"""API schemas for media assets (ARCH phase 4, ADR-2026-09-25-media).

``storage_key`` is deliberately absent: it is an internal storage address
(a filesystem path for the local store) and never leaves the server.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from goldsmith_erp.db.models import MediaKind, MediaOwnerType


class MediaAssetRead(BaseModel):
    """Metadata of one media asset."""

    id: str
    owner_type: MediaOwnerType
    owner_id: int
    kind: MediaKind
    mime: str
    bytes: Optional[int] = None
    width: Optional[int] = None
    height: Optional[int] = None
    customer_visible: bool
    caption: Optional[str] = None
    sort_order: int
    taken_at: Optional[datetime] = None
    uploaded_by: Optional[int] = None
    created_at: datetime
    # Id of the deprecated photo row (order/repair/consultation) this asset
    # mirrors, and that row's phase or kind.
    legacy_id: Optional[str] = None
    tag: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class MediaAssetUpdate(BaseModel):
    """``PATCH /media/{id}``: only the customer-visibility flag is editable."""

    customer_visible: bool

    model_config = ConfigDict(extra="forbid")
