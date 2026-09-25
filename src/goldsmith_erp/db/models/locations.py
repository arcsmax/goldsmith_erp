"""Workshop locations (Standorte): benches, safe, showroom, ...

ADMIN-configurable list that feeds the "Standort" dropdown of the timer,
the time-entry edit form and the order's Standort field. Time entries and
orders reference a row via a nullable ``location_id`` FK; their legacy
``location`` / ``current_location`` text columns are kept (synced on
write) for one release. Migration: 20260925_w8_workshop_locations.
"""

import enum

from sqlalchemy import Boolean, CheckConstraint, Column, Integer, String, text

from goldsmith_erp.core.timeutil import utcnow
from goldsmith_erp.db.models.base import Base
from goldsmith_erp.db.types import UtcDateTime


class LocationKind(str, enum.Enum):
    """What kind of place a workshop location is."""

    BENCH = "bench"
    SAFE = "safe"
    SHOWROOM = "showroom"
    EXTERNAL = "external"
    OTHER = "other"


LOCATION_KIND_VALUES = tuple(k.value for k in LocationKind)

LOCATION_NAME_MAX = 50


class WorkshopLocation(Base):
    """One selectable Standort."""

    __tablename__ = "workshop_locations"
    __table_args__ = (
        CheckConstraint(
            "kind IN ('bench', 'safe', 'showroom', 'external', 'other')",
            name="ck_workshop_locations_kind",
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(LOCATION_NAME_MAX), nullable=False, unique=True)
    kind = Column(
        String(20),
        nullable=False,
        server_default=text("'other'"),
        default=LocationKind.OTHER.value,
    )
    is_active = Column(
        Boolean, nullable=False, server_default=text("true"), default=True
    )
    sort_order = Column(Integer, nullable=False, server_default=text("0"), default=0)
    created_at = Column(UtcDateTime, default=utcnow, nullable=False)
