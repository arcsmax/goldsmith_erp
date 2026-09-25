"""User accounts."""

from sqlalchemy import Boolean, Column, Index, Integer, String, text

from goldsmith_erp.core.timeutil import utcnow
from goldsmith_erp.db.models.base import Base, SAEnum, UserRole
from goldsmith_erp.db.types import UtcDateTime


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    first_name = Column(String)
    last_name = Column(String)
    role = Column(SAEnum(UserRole), default=UserRole.VIEWER, nullable=False, index=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(UtcDateTime, default=utcnow)

    # ── GDPR Art. 17 anonymisation infrastructure (Slice 0) ─────────────────
    # Populated by services.user_service.anonymize_user(). See
    # docs/superpowers/plans/qr-barcode-workflow/V1.1-ANONYMIZE-USER-CONTRACT.md.
    is_deleted = Column(Boolean, default=False, nullable=False, index=True)
    deleted_at = Column(UtcDateTime, nullable=True)
    # Short (16-char) HMAC tracking token. Internal correlation aid only —
    # not user-facing, not a re-identification vector on its own.
    anonymization_hash = Column(String(64), nullable=True)
    # Forward-compat slot for V1.2 multi-tenancy (per DECISIONS-2026-04-16
    # SQ1). Nullable in V1.1; V1.2 migration will make it NOT NULL after
    # backfilling a tenant for every user + sentinel row.
    tenant_id = Column(Integer, nullable=True, index=True)

    # A2.1 — excludes fixture / seed accounts from the 30-day scan-adoption
    # metric (Lena §1). Default FALSE so existing users are unaffected.
    is_test_user = Column(
        Boolean,
        nullable=False,
        server_default=text("FALSE"),
        default=False,
    )


Index(
    "idx_users_is_test_user",
    User.is_test_user,
    postgresql_where=User.is_test_user.is_(True),
)
