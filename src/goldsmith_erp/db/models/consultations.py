"""Consultations, consultation photos and customer no-gos."""

import enum
import uuid

from sqlalchemy import Column, Date, ForeignKey, Index, Integer, String, Text, event
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import relationship

from goldsmith_erp.core.timeutil import utcnow
from goldsmith_erp.db.models.base import MONEY_NUMERIC, Base, SAEnum
from goldsmith_erp.db.models.orders import OrderTypeEnum
from goldsmith_erp.db.types import EncryptedString, UtcDateTime

# ---------------------------------------------------------------------------
# V1.1 Consultation & Intake (Beratung & Annahme)
# ---------------------------------------------------------------------------


class ConsultationStatus(str, enum.Enum):
    """Lifecycle of a consultation (Beratungsgespräch)."""

    DRAFT = "draft"  # Laufende/unterbrochene Beratung — auto-save target
    COMPLETED = "completed"  # Beratung abgeschlossen, noch nicht konvertiert
    CONVERTED = "converted"  # In Auftrag oder Kostenvoranschlag überführt
    ARCHIVED = "archived"  # Nicht weiterverfolgt


class ConsultationOccasion(str, enum.Enum):
    """Anlass des Schmuckwunsches."""

    ENGAGEMENT = "engagement"
    WEDDING = "wedding"
    ANNIVERSARY = "anniversary"
    BIRTHDAY = "birthday"
    SELF = "self"  # Selbstkauf
    REDESIGN = "redesign"  # Umarbeitung
    REPAIR_CONSULT = "repair_consult"
    OTHER = "other"


class ConsultationPhotoKind(str, enum.Enum):
    """Art eines Beratungsfotos."""

    SKETCH = "sketch"  # Foto der Papierskizze
    REFERENCE = "reference"  # Referenz-/Inspirationsbild des Kunden
    INSPIRATION = "inspiration"
    EXISTING_PIECE = "existing_piece"  # Mitgebrachtes Stück (z. B. Erbstück)


class NoGoCategory(str, enum.Enum):
    """Kategorie eines Kunden-No-Gos."""

    METAL = "metal"
    STONE = "stone"
    FINISH = "finish"
    DESIGN_ELEMENT = "design_element"
    ALLERGY = "allergy"
    OTHER = "other"


class Consultation(Base):
    """Beratungsgespräch — strukturierte Aufnahme eines Schmuckwunsches.

    Wishes/notes/photos are design IP: GOLDSMITH/ADMIN access only.
    budget_min/budget_max are financial data (ADMIN/GOLDSMITH, audit-logged).
    """

    __tablename__ = "consultations"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(
        Integer,
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    conducted_by = Column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    calendar_event_id = Column(
        Integer, ForeignKey("calendar_events.id", ondelete="SET NULL"), nullable=True
    )
    occasion = Column(
        SAEnum(ConsultationOccasion),
        nullable=False,
        default=ConsultationOccasion.OTHER,
    )
    occasion_date = Column(Date, nullable=True)
    budget_min = Column(
        MONEY_NUMERIC, nullable=True
    )  # Finanzdaten — Sichtbarkeitsregeln!
    budget_max = Column(MONEY_NUMERIC, nullable=True)
    piece_type = Column(SAEnum(OrderTypeEnum), nullable=True)
    wishes = Column(Text, nullable=True)  # Design-IP
    materials_discussed = Column(JSON, nullable=True)  # [{"metal": "gold_585", ...}]
    source_material = Column(Text, nullable=True)  # Altgold/Erbstück des Kunden
    status = Column(
        SAEnum(ConsultationStatus),
        nullable=False,
        default=ConsultationStatus.DRAFT,
        index=True,
    )
    converted_quote_id = Column(
        Integer, ForeignKey("quotes.id", ondelete="SET NULL"), nullable=True
    )
    converted_order_id = Column(
        Integer, ForeignKey("orders.id", ondelete="SET NULL"), nullable=True
    )
    follow_up_at = Column(UtcDateTime, nullable=True)
    notes = Column(Text, nullable=True)  # Design-IP
    created_at = Column(UtcDateTime, default=utcnow, nullable=False, index=True)
    updated_at = Column(UtcDateTime, default=utcnow, onupdate=utcnow, nullable=False)

    customer = relationship("Customer")
    goldsmith = relationship("User", foreign_keys=[conducted_by])
    photos = relationship(
        "ConsultationPhoto",
        back_populates="consultation",
        cascade="all, delete-orphan",
        order_by="ConsultationPhoto.timestamp.asc()",
    )

    def __repr__(self) -> str:
        return f"<Consultation {self.id} customer={self.customer_id} status={self.status.value}>"


class ConsultationPhoto(Base):
    """Skizzen-/Referenzfoto einer Beratung. Cloned from OrderPhoto conventions."""

    __tablename__ = "consultation_photos"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    consultation_id = Column(
        Integer,
        ForeignKey("consultations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Set on conversion so the bench sees the sketch on the order (spec: link, not copy).
    order_id = Column(
        Integer, ForeignKey("orders.id", ondelete="SET NULL"), nullable=True, index=True
    )
    kind = Column(
        SAEnum(ConsultationPhotoKind),
        nullable=False,
        default=ConsultationPhotoKind.SKETCH,
    )
    file_path = Column(String(500), nullable=False)
    timestamp = Column(UtcDateTime, default=utcnow, index=True)
    taken_by = Column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    notes = Column(Text)

    consultation = relationship("Consultation", back_populates="photos")
    user = relationship("User")


class CustomerNoGo(Base):
    """Persistentes Kunden-No-Go (z. B. 'kein Nickel'). Warn-Quelle für Aufträge.

    ``value``/``note`` are health-adjacent PII (allergies live here — this
    table is the source of truth, the legacy ``Customer.allergies`` mirror
    is a read-compat sync target, see ``no_go_service._sync_legacy_
    allergies``) and are encrypted at rest via ``EncryptedString``, same
    C1 pattern as the ``Customer`` PII columns (``db/types.py``).

    Because Fernet ciphertext is non-deterministic, ``value`` itself can't
    carry the duplicate-detection unique constraint. ``value_hash`` is the
    HMAC-SHA-256 blind-index tag (see
    ``core.encryption.no_go_value_blind_index``) over
    ``"<category>:<value.strip().casefold()>"`` — composite because a
    no-go is only a duplicate when BOTH category and (casefolded) value
    match. This replaces the previous functional index on
    ``(customer_id, category, lower(value))``: that index (a) could never
    have worked once ``value`` became ciphertext (SQL ``lower()`` over a
    Fernet token is meaningless), and (b) used SQL ``lower()``, whose
    normalisation silently diverged from the app-side Python
    ``casefold()`` compare (e.g. 'Straße' vs 'STRASSE' collide app-side,
    NOT at that index) — casefold-everywhere closes both gaps at once.
    """

    __tablename__ = "customer_no_gos"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(
        Integer,
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    category = Column(SAEnum(NoGoCategory), nullable=False)
    value = Column(EncryptedString, nullable=False)
    # HMAC-SHA-256 blind-index tag over "<category>:<casefolded value>" —
    # see core.encryption.no_go_value_blind_index and the class docstring.
    # Populated by the before_insert/before_update hooks below whenever the
    # caller (NoGoService.add_no_go) hasn't already set it explicitly —
    # exact mirror of Customer.email_hash's event-hook pattern.
    value_hash = Column(String(64), nullable=False, index=True)
    note = Column(EncryptedString, nullable=True)
    source_consultation_id = Column(
        Integer, ForeignKey("consultations.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(UtcDateTime, default=utcnow, nullable=False)

    # DB-level backstop for the app-side duplicate check in
    # NoGoService.add_no_go (issue #12 — closes the duplicate TOCTOU: that
    # check runs BEFORE the transaction, so two concurrent requests can
    # both pass it). Plain (non-expression) composite unique index — now
    # that duplicate-detection lives entirely in value_hash, this no
    # longer needs to be a functional index over the encrypted column.
    # Named identically to the index created by
    # alembic/versions/20260703_i12_no_go_unique_index.py so that
    # ``Base.metadata.create_all()`` (unit-test DBs) and
    # ``alembic upgrade head`` (real deployments) produce the same
    # constraint shape.
    __table_args__ = (
        Index(
            "uq_customer_no_gos_customer_value_hash",
            customer_id,
            value_hash,
            unique=True,
        ),
    )

    customer = relationship("Customer")


# ── I12-follow-up — auto-populate value_hash on insert / update ────────
# Exact mirror of the Customer.email_hash hooks above: derives value_hash
# from (category, value) whenever the caller hasn't already set it,
# keeping the blind-index in lock-step for any direct-ORM construction
# path (tests, seed scripts) that doesn't go through NoGoService.add_no_go
# (which sets it explicitly — see services/no_go_service.py).


@event.listens_for(CustomerNoGo, "before_insert")
def _customer_no_go_before_insert(_mapper, _connection, target: "CustomerNoGo") -> None:
    """Ensure ``value_hash`` is populated on insert."""
    if target.value and target.category is not None and not target.value_hash:
        from goldsmith_erp.core.encryption import (  # noqa: PLC0415
            no_go_value_blind_index,
        )

        target.value_hash = no_go_value_blind_index(target.category.value, target.value)


@event.listens_for(CustomerNoGo, "before_update")
def _customer_no_go_before_update(_mapper, _connection, target: "CustomerNoGo") -> None:
    """Keep ``value_hash`` in lock-step with (category, value) on update.

    CAUTION (security review, 2026-07): the ``not target.value_hash`` guard
    means a future write path that mutates ``value``/``category`` WITHOUT
    clearing ``value_hash`` would leave a stale hash, silently breaking the
    duplicate-detection unique index for that row. No such path exists today
    (no-gos are immutable: created via NoGoService.add_no_go, only ever
    deleted) — if you add an update endpoint, set ``value_hash = None``
    before changing ``value`` or ``category``.
    """
    if target.value and target.category is not None and not target.value_hash:
        from goldsmith_erp.core.encryption import (  # noqa: PLC0415
            no_go_value_blind_index,
        )

        target.value_hash = no_go_value_blind_index(target.category.value, target.value)
