"""Customers, measurements, consents, GDPR requests and the customer audit log."""

from sqlalchemy import (
    Boolean,
    Column,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    event,
    text,
)
from sqlalchemy.dialects.postgresql import JSON
from sqlalchemy.orm import relationship

from goldsmith_erp.core.timeutil import utcnow
from goldsmith_erp.db.models.base import (
    Base,
    FingerPosition,
    HandSide,
    MeasurementType,
    SAEnum,
)
from goldsmith_erp.db.types import EncryptedString, UtcDateTime


class Customer(Base):
    """Customer/Client Model for CRM.

    PII fields (names, company, email, phone, address) and the
    health-adjacent ``allergies`` field are encrypted at rest via
    ``EncryptedString`` — CLAUDE.md "Data Privacy Rules (CRITICAL)". The
    raw DB columns hold Fernet ciphertext; the ORM round-trips plaintext
    transparently. See ``db/types.py`` + fix items **C1** (names/contact/
    address) and **I15** (allergies) for the design.

    Because Fernet is non-deterministic, the ``email`` column cannot
    carry a UNIQUE constraint or be searched by equality. The companion
    ``email_hash`` column holds an HMAC-SHA-256 tag (see
    ``core.encryption.hmac_blind_index``) — unique-indexed, searchable,
    and the new ground truth for duplicate detection.

    Previous plain ``String(...)`` columns had per-column length limits
    (email ``String(255)``, street ``String(200)``, …). Those limits
    enforced input hygiene. Because the ciphertext size now drives the
    column type (TEXT), length validation moves up to the Pydantic
    schemas in ``models/customer.py``.
    """

    __tablename__ = "customers"
    __table_args__ = (
        Index(
            "ix_customers_email_hash",
            "email_hash",
            unique=True,
            postgresql_where=text("email_hash IS NOT NULL"),
            sqlite_where=text("email_hash IS NOT NULL"),
        ),
    )

    id = Column(Integer, primary_key=True, index=True)
    # Basic Info — PII, encrypted at rest (C1).
    first_name = Column(EncryptedString, nullable=False)
    last_name = Column(EncryptedString, nullable=False)
    company_name = Column(EncryptedString, nullable=True)

    # Contact Info — PII, encrypted at rest (C1).
    # ``email`` is ciphertext (no unique / no index — Fernet is non-
    # deterministic). ``email_hash`` is the HMAC-SHA-256 blind-index tag;
    # it carries the uniqueness constraint and is the column we equality-
    # search on. See ``core.encryption.hmac_blind_index``.
    # W2-10 (DOM-02, D-11): email is optional (walk-in / phone-only
    # customers). Uniqueness applies only when an email is present: the
    # partial unique index ``ix_customers_email_hash`` below covers
    # ``WHERE email_hash IS NOT NULL``. A customer needs at least one of
    # email / phone / mobile (enforced in models/customer.py + service).
    email = Column(EncryptedString, nullable=True)
    email_hash = Column(String(64), nullable=True)
    phone = Column(EncryptedString, nullable=True)
    mobile = Column(EncryptedString, nullable=True)

    # Address — PII, encrypted at rest (C1).
    street = Column(EncryptedString, nullable=True)
    city = Column(EncryptedString, nullable=True)
    postal_code = Column(EncryptedString, nullable=True)
    country = Column(String(100), default="Deutschland")

    # CRM Fields
    customer_type = Column(String(50), default="private")  # private, business
    source = Column(String(100), nullable=True)  # referral, website, walk-in, etc.
    notes = Column(Text, nullable=True)
    tags = Column(JSON, default=list)  # ["VIP", "Stammkunde", etc.]

    # Measurement Library (Mass-Bibliothek)
    ring_size = Column(Float, nullable=True)  # EU ring size (e.g., 52, 54.5)
    chain_length_cm = Column(Float, nullable=True)  # Preferred chain length in cm
    bracelet_length_cm = Column(Float, nullable=True)  # Preferred bracelet length in cm
    # Health-adjacent PII, encrypted at rest (I15 — see fix item C1 for the
    # pattern this follows). Plaintext length stays governed by the 500-char
    # Pydantic schema / _ALLERGIES_MAX_LENGTH guard in no_go_service.py; the
    # storage column itself is TEXT (see EncryptedString) so ciphertext never
    # truncates. e.g. "Nickel", "Kupfer"
    allergies = Column(EncryptedString, nullable=True)
    preferences = Column(
        JSON, default=dict
    )  # {"bevorzugt": "Platin", "style": "modern"}
    style_profile = Column(
        JSON, nullable=True
    )  # V1.1: {metal_tones, finishes, stone_preferences, style_words}
    birthday = Column(UtcDateTime, nullable=True)  # For marketing/gift vouchers

    # Metadata
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(UtcDateTime, default=utcnow, index=True)
    updated_at = Column(UtcDateTime, default=utcnow, onupdate=utcnow)

    # GDPR Art. 17 — scheduled hard-delete date (set on erasure request).
    # After this date the gdpr-cleanup.sh cron job permanently deletes the record.
    deletion_scheduled_at = Column(UtcDateTime, nullable=True, index=True)

    # GDPR-01 — legal hold. Set on erasure when the customer has records that
    # §147 AO / §14b UStG / GwG §8 Abs. 4 require us to keep (invoices,
    # quotes, Altgold purchases, valuation certificates). Those records are
    # NOT scrubbed (Art. 17 Abs. 3 lit. b DSGVO); this date is the earliest
    # point at which they — and the anonymised customer row they point at —
    # may be deleted. NULL = no hold.
    retention_hold_until = Column(UtcDateTime, nullable=True, index=True)

    # Soft delete
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    deleted_at = Column(UtcDateTime, nullable=True)
    deleted_by = Column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    deletion_reason = Column(String(500), nullable=True)

    # Beziehungen
    orders = relationship("Order", back_populates="customer")
    measurements = relationship(
        "CustomerMeasurement",
        back_populates="customer",
        cascade="all, delete-orphan",
        order_by="CustomerMeasurement.measured_at.desc()",
    )


# ── C1 — auto-populate email_hash on insert / update ──────────────────
# The ``email_hash`` column carries the UNIQUE constraint for the customer
# table (because the ``email`` column itself is non-deterministic
# ciphertext — see ``db/types.py`` for the design). Application code in
# ``services.customer_service`` already sets ``email_hash`` explicitly on
# create / update, but tests (and any future direct-ORM-insert path)
# frequently construct ``Customer(email=..., ...)`` without thinking
# about the hash. The event hook below derives ``email_hash`` from the
# current ``email`` whenever it's missing or stale, keeping the blind-
# index in lock-step with the plaintext email without a second code
# path for callers to remember.


@event.listens_for(Customer, "before_insert")
def _customer_before_insert(_mapper, _connection, target: "Customer") -> None:
    """Ensure ``email_hash`` is populated on insert.

    If the service layer already set ``email_hash``, we leave it alone.
    If not (direct-ORM construction in tests / seed scripts), we derive
    it from ``email`` so the INSERT doesn't fail the NOT NULL + UNIQUE
    constraint.
    """
    if target.email and not target.email_hash:
        # Import locally to avoid a cycle (encryption → config → logging → …).
        from goldsmith_erp.core.encryption import hmac_blind_index  # noqa: PLC0415

        target.email_hash = hmac_blind_index(target.email)


@event.listens_for(Customer, "before_update")
def _customer_before_update(_mapper, _connection, target: "Customer") -> None:
    """Keep ``email_hash`` in lock-step with ``email`` on update.

    If the email was changed but the hash wasn't recomputed, derive it
    here. Cheap — one HMAC per update. W2-10: a cleared email clears the
    hash too, so the partial unique index never keeps a stale tag.
    """
    if not target.email:
        target.email_hash = None
        return
    if not target.email_hash:
        from goldsmith_erp.core.encryption import hmac_blind_index  # noqa: PLC0415

        target.email_hash = hmac_blind_index(target.email)


class CustomerMeasurement(Base):
    """
    Massbibliothek — persistent body measurements per customer.

    Goldsmiths capture measurements once and reuse them across all future
    orders, eliminating repeated re-measurement sessions.  Each row stores
    one measurement (e.g. ring size on the left ring finger) with full
    provenance: who measured, when, and any fitting notes.
    """

    __tablename__ = "customer_measurements"

    id = Column(Integer, primary_key=True, index=True)

    # Links
    customer_id = Column(
        Integer,
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    measured_by = Column(
        Integer,
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # What was measured
    measurement_type = Column(
        SAEnum(MeasurementType),
        nullable=False,
        index=True,
    )

    # The numeric value — interpretation depends on measurement_type + unit
    # Ring sizes (EU): inner circumference in mm, range 38-80
    # Chain / neck / wrist / ankle: centimetres
    # Finger circumference: millimetres (raw tape measurement, basis for EU size)
    value = Column(Float, nullable=False)
    unit = Column(String(20), nullable=False)  # "mm", "cm", "EU", "US"

    # Ring-specific anatomy
    hand = Column(SAEnum(HandSide), nullable=True)  # LEFT / RIGHT
    finger = Column(SAEnum(FingerPosition), nullable=True)  # RING, INDEX, …

    # Goldsmith notes — e.g. "Knöchel etwas breiter, Weitungsring empfohlen"
    notes = Column(Text, nullable=True)

    # When the measurement was physically taken (not necessarily = created_at)
    measured_at = Column(UtcDateTime, nullable=False, default=utcnow, index=True)

    # Audit timestamps
    created_at = Column(UtcDateTime, default=utcnow, nullable=False)
    updated_at = Column(
        UtcDateTime,
        default=utcnow,
        onupdate=utcnow,
        nullable=False,
    )

    # Beziehungen
    customer = relationship("Customer", back_populates="measurements")
    goldsmith = relationship("User", foreign_keys=[measured_by])

    def __repr__(self) -> str:
        return (
            f"<CustomerMeasurement customer={self.customer_id} "
            f"{self.measurement_type.value}={self.value}{self.unit}>"
        )


# ============================================================================
# CUSTOMER AUDIT & GDPR
# ============================================================================


class CustomerAuditLog(Base):
    """Audit trail for customer data access and changes."""

    __tablename__ = "customer_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(
        Integer,
        ForeignKey("customers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    action = Column(String(50), nullable=False)
    entity = Column(String(50), nullable=True)
    entity_id = Column(Integer, nullable=True)
    field_name = Column(String(100), nullable=True)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)
    user_email = Column(String(255), nullable=True)
    user_role = Column(String(50), nullable=True)
    user_agent = Column(String(500), nullable=True)
    details = Column(JSON, nullable=True)
    ip_address = Column(String(45), nullable=True)
    timestamp = Column(UtcDateTime, default=utcnow, nullable=True)
    created_at = Column(UtcDateTime, default=utcnow, nullable=False)


class GDPRRequest(Base):
    """Tracks GDPR data export and erasure requests."""

    __tablename__ = "gdpr_requests"

    id = Column(Integer, primary_key=True, index=True)
    # No ForeignKey: an audit log of GDPR erasure requests must outlive its
    # subject (CLAUDE.md "Anonymize audit logs when user requests erasure")
    # and must accept requests for customer IDs that never existed (the
    # Art. 30 404 path: see `_write_pending_gdpr_request` in customers.py).
    # FK enforcement contradicts both. See migration
    # `20260610_e1_gdpr_audit_nofk` and issue #7.
    customer_id = Column(Integer, nullable=True)
    request_type = Column(String(20), nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    requested_at = Column(UtcDateTime, default=utcnow, nullable=False)
    completed_at = Column(UtcDateTime, nullable=True)
    requested_by = Column(
        Integer, ForeignKey("users.id", ondelete="RESTRICT"), nullable=True
    )
    notes = Column(Text, nullable=True)


class CustomerConsent(Base):
    """Per-purpose consent record — Art. 7(1) DSGVO proof (GDPR-02 / GDPR-11).

    One row per grant. ``revoked_at`` is set on withdrawal (Art. 7(3)); a new
    grant after a withdrawal is a new row, so the history stays provable.

    ``purpose`` / ``method`` are plain strings validated by the Pydantic
    enums in ``models/consent.py`` (``ConsentPurpose`` / ``ConsentMethod``) —
    String rather than a native PG enum so adding a purpose never needs an
    ``ALTER TYPE`` migration.

    ``note`` may carry free text about the grant ("Bogen v1 unterschrieben"),
    so it is encrypted at rest like the other customer free text.

    Erasure: rows are deleted with the customer's other preference/health
    data (``CustomerService.scrub_customer_pii``); ``customer_id`` CASCADEs
    on a hard-delete.
    """

    __tablename__ = "customer_consents"

    id = Column(Integer, primary_key=True, index=True)
    customer_id = Column(
        Integer,
        ForeignKey("customers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    purpose = Column(String(32), nullable=False, index=True)
    method = Column(String(20), nullable=False)
    wording_version = Column(String(32), nullable=True)
    granted_at = Column(UtcDateTime, nullable=False, default=utcnow)
    revoked_at = Column(UtcDateTime, nullable=True)
    recorded_by_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    revoked_by_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    note = Column(EncryptedString, nullable=True)
    created_at = Column(UtcDateTime, nullable=False, default=utcnow)
