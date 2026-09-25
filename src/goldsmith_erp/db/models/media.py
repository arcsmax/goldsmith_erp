"""Unified media assets (ARCH phase 4, ADR-2026-09-25-media).

One row per stored file (photo, signature, document) regardless of what it
belongs to. ``owner_type`` + ``owner_id`` is a polymorphic reference (no FK):
the owner tables stay the source of truth for who may see the asset, and the
authorization rules live in ``services/media_service.py``.

``storage_key`` is opaque to everything except ``services/media_store.py``.
New uploads get a content-addressed key; rows copied from the three legacy
photo tables keep the old absolute ``file_path`` as their key (the store's
compatibility branch reads those).

The legacy tables (``order_photos``, ``repair_photos``,
``consultation_photos``) are kept for one release and dual-written; see
``legacy_id`` for the link back.
"""

import enum
import uuid

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)

from goldsmith_erp.core.timeutil import utcnow
from goldsmith_erp.db.models.base import Base
from goldsmith_erp.db.types import UtcDateTime


class MediaOwnerType(str, enum.Enum):
    """What a media asset belongs to."""

    ORDER = "order"
    REPAIR = "repair"
    CONSULTATION = "consultation"
    CUSTOMER_UPDATE = "customer_update"


class MediaKind(str, enum.Enum):
    """What a media asset is."""

    PHOTO = "photo"
    SIGNATURE = "signature"
    DOCUMENT = "document"


MEDIA_OWNER_TYPE_VALUES = tuple(member.value for member in MediaOwnerType)
MEDIA_KIND_VALUES = tuple(member.value for member in MediaKind)


def _in_list(column: str, values: tuple[str, ...]) -> str:
    quoted = ", ".join(f"'{value}'" for value in values)
    return f"{column} IN ({quoted})"


class MediaAsset(Base):
    """A stored file attached to an order, repair, consultation or update."""

    __tablename__ = "media_assets"
    __table_args__ = (
        CheckConstraint(
            _in_list("owner_type", MEDIA_OWNER_TYPE_VALUES),
            name="ck_media_assets_owner_type",
        ),
        CheckConstraint(
            _in_list("kind", MEDIA_KIND_VALUES), name="ck_media_assets_kind"
        ),
    )

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    owner_type = Column(String(20), nullable=False)
    owner_id = Column(Integer, nullable=False)
    # ARCH phase 5: the job of an order/repair owner (NULL otherwise).
    job_id = Column(
        Integer,
        ForeignKey("jobs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    kind = Column(String(20), nullable=False, default=MediaKind.PHOTO.value)
    storage_key = Column(String(500), nullable=False)
    mime = Column(String(100), nullable=False)
    bytes = Column(Integer, nullable=True)
    width = Column(Integer, nullable=True)
    height = Column(Integer, nullable=True)
    sha256 = Column(String(64), nullable=True, index=True)
    customer_visible = Column(Boolean, nullable=False, default=False)
    caption = Column(Text, nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    taken_at = Column(UtcDateTime, nullable=True)
    uploaded_by = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(UtcDateTime, nullable=False, default=utcnow)
    deleted_at = Column(UtcDateTime, nullable=True)
    # Deprecated-table bridge (one release): the id of the matching row in
    # order_photos / repair_photos / consultation_photos, and that row's
    # phase or kind (e.g. "intake", "sketch").
    legacy_id = Column(String(36), nullable=True)
    tag = Column(String(32), nullable=True)


Index(
    "ix_media_assets_owner",
    MediaAsset.owner_type,
    MediaAsset.owner_id,
)
Index(
    "ix_media_assets_legacy",
    MediaAsset.owner_type,
    MediaAsset.legacy_id,
)
