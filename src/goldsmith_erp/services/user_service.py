# src/goldsmith_erp/services/user_service.py

import hashlib
import hmac
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import delete, text, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from goldsmith_erp.core.config import settings
from goldsmith_erp.core.security import get_password_hash
from goldsmith_erp.db.models import GDPRRequest
from goldsmith_erp.db.models import User as UserModel
from goldsmith_erp.db.models import UserRole
from goldsmith_erp.models.user import (
    AnonymizationResult,
    LastAdminError,
    SentinelMissing,
    UserCreate,
    UserNotFound,
    UserUpdate,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Sentinel + FK registry constants — see
# docs/superpowers/plans/qr-barcode-workflow/V1.1-ANONYMIZE-USER-CONTRACT.md.
# ─────────────────────────────────────────────────────────────────────────────

# Canonical sentinel lookup key. Seeded by the Slice 0 migration (id=0 is
# attempted first; the email remains the source-of-truth lookup so this
# code survives id collisions and dialects that disallow explicit id=0).
SENTINEL_EMAIL = "deleted@sentinel.invalid"
SENTINEL_FIRST_NAME = "<deleted>"
SENTINEL_PASSWORD_HASH = "!"  # bcrypt-invalid — cannot be used to log in

# Dev-only fallback salt. Production must set ANONYMIZATION_SALT explicitly
# (the Settings validator fails fast when DEBUG=False). Having a non-empty
# placeholder here keeps the import-time path clean for unit tests.
_DEV_FALLBACK_SALT = "dev-only-anonymization-salt-not-for-production"


# ANONYMIZABLE_FK_TARGETS — single source of truth for "every FK column
# that references users(id) and therefore needs to be rewritten to the
# sentinel on anonymisation".
#
# Each entry: (table_name, fk_column_name).
#
# Slice 0 registers every current reference extracted from db/models.py
# on 2026-04-17. Slice 1 (Migration 1) appends the two new FKs from the
# scan_logs / barcode_aliases tables — the registry exists so that
# extension is a one-line diff, not a service rewrite. Extensibility is
# covered by `test_fk_registry_is_extensible`.
#
# Three columns are deliberately excluded:
#   * notifications.user_id             → ON DELETE CASCADE, per-user data
#   * notification_preferences.user_id  → ON DELETE CASCADE, per-user data
#   * calendar_events.user_id           → ON DELETE CASCADE, per-user data
# Per contract §2: CASCADE FKs carry personal data that legally must
# disappear with the person — the cascade does the right thing already.
ANONYMIZABLE_FK_TARGETS: list[tuple[str, str]] = [
    ("customers", "deleted_by"),
    ("customer_measurements", "measured_by"),
    ("order_comments", "user_id"),
    ("activities", "created_by"),
    ("time_entries", "user_id"),
    ("location_history", "changed_by"),
    ("order_photos", "taken_by"),
    ("inventory_adjustments", "adjusted_by_user_id"),
    ("scrap_gold", "created_by"),
    ("invoices", "created_by"),
    ("quotes", "created_by"),
    ("order_handoffs", "from_user_id"),
    ("order_handoffs", "to_user_id"),
    ("repair_jobs", "received_by"),
    ("repair_photos", "taken_by"),
    ("order_hallmarks", "created_by"),
    ("valuation_certificates", "created_by"),
    ("customer_audit_logs", "user_id"),
    ("gdpr_requests", "requested_by"),
    ("order_status_history", "changed_by"),
    # Slice 1 (Migration 1) — QR/barcode workflow. Each of these FK
    # columns is declared ON DELETE RESTRICT at the DB level, so the
    # only path to removing a user referenced by any of these rows is
    # through `anonymize_user`. Registering them here is the one-line
    # extension the Slice 0 contract anticipated.
    ("scan_logs", "user_id"),
    ("barcode_aliases", "created_by"),
    ("label_templates", "created_by"),
    # Slice 2 (Migration 2) — security floor. Two new FK columns to
    # users(id) land as ON DELETE RESTRICT on orders and material_usage.
    # Same anonymisation contract — registry extension is the one-line
    # diff the contract anticipated.
    ("orders", "punzierung_verified_by"),
    ("material_usage", "user_id"),
]


def _get_anonymization_salt() -> str:
    """Return the configured salt, or the dev fallback when unset."""
    return settings.ANONYMIZATION_SALT or _DEV_FALLBACK_SALT


def _compute_tracking_hmac(user_id: int) -> str:
    """Derive the 16-char audit-correlation HMAC for a user id.

    Algorithm per contract §4: truncated SHA-256 HMAC over the ASCII
    user-id using `ANONYMIZATION_SALT` as the key. The truncation is
    deliberate — 16 hex chars (64 bits) is plenty for correlation within
    a single workshop and keeps log lines readable.
    """
    salt = _get_anonymization_salt().encode("utf-8")
    return hmac.new(salt, str(user_id).encode("utf-8"), hashlib.sha256).hexdigest()[:16]


class UserService:
    """Service für User-Management mit CRUD-Operationen."""

    @staticmethod
    async def get_users(
        db: AsyncSession, skip: int = 0, limit: int = 100
    ) -> List[UserModel]:
        """
        Holt alle Benutzer mit Pagination.

        Args:
            db: Datenbank-Session
            skip: Anzahl zu überspringender Einträge
            limit: Maximum Anzahl zurückzugebender Einträge

        Returns:
            Liste von User-Objekten
        """
        result = await db.execute(
            select(UserModel)
            .order_by(UserModel.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()

    @staticmethod
    async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[UserModel]:
        """
        Holt einen einzelnen Benutzer über seine ID.

        Args:
            db: Datenbank-Session
            user_id: ID des Benutzers

        Returns:
            User-Objekt oder None
        """
        result = await db.execute(select(UserModel).filter(UserModel.id == user_id))
        return result.scalar_one_or_none()

    @staticmethod
    async def get_user_by_email(db: AsyncSession, email: str) -> Optional[UserModel]:
        """
        Holt einen Benutzer über seine E-Mail-Adresse.

        Args:
            db: Datenbank-Session
            email: E-Mail-Adresse des Benutzers

        Returns:
            User-Objekt oder None
        """
        result = await db.execute(select(UserModel).filter(UserModel.email == email))
        return result.scalar_one_or_none()

    @staticmethod
    async def create_user(db: AsyncSession, user_in: UserCreate) -> UserModel:
        """
        Erstellt einen neuen Benutzer.

        Args:
            db: Datenbank-Session
            user_in: User-Erstellungsdaten

        Returns:
            Erstelltes User-Objekt
        """
        # Hash das Passwort
        hashed_password = get_password_hash(user_in.password)

        # Erstelle User-Objekt
        db_user = UserModel(
            email=user_in.email,
            hashed_password=hashed_password,
            first_name=user_in.first_name,
            last_name=user_in.last_name,
            is_active=True,  # Neue Benutzer sind standardmäßig aktiv
        )

        db.add(db_user)
        await db.commit()
        await db.refresh(db_user)

        return db_user

    @staticmethod
    async def update_user(
        db: AsyncSession, user_id: int, user_in: UserUpdate
    ) -> Optional[UserModel]:
        """
        Aktualisiert einen bestehenden Benutzer.

        Args:
            db: Datenbank-Session
            user_id: ID des zu aktualisierenden Benutzers
            user_in: Update-Daten

        Returns:
            Aktualisiertes User-Objekt oder None
        """
        # Prüfen ob Benutzer existiert
        user = await UserService.get_user_by_id(db, user_id)
        if not user:
            return None

        # Update-Daten vorbereiten
        update_data = user_in.model_dump(exclude_unset=True)

        # Passwort hashen, falls vorhanden
        if "password" in update_data:
            hashed_password = get_password_hash(update_data["password"])
            update_data["hashed_password"] = hashed_password
            del update_data["password"]

        # Update durchführen
        if update_data:
            await db.execute(
                update(UserModel).where(UserModel.id == user_id).values(**update_data)
            )
            await db.commit()

        # Aktualisiertes Objekt holen
        updated_user = await UserService.get_user_by_id(db, user_id)
        return updated_user

    @staticmethod
    async def delete_user(db: AsyncSession, user_id: int) -> Dict[str, Any]:
        """
        Löscht einen Benutzer (soft delete durch is_active=False).

        Args:
            db: Datenbank-Session
            user_id: ID des zu löschenden Benutzers

        Returns:
            Dict mit Erfolgs-Status
        """
        # Prüfen ob Benutzer existiert
        user = await UserService.get_user_by_id(db, user_id)
        if not user:
            return {"success": False, "message": "User not found"}

        # Soft delete: setze is_active auf False
        await db.execute(
            update(UserModel).where(UserModel.id == user_id).values(is_active=False)
        )
        await db.commit()

        return {"success": True, "message": f"User {user_id} deactivated successfully"}

    @staticmethod
    async def hard_delete_user(db: AsyncSession, user_id: int) -> Dict[str, Any]:
        """
        Löscht einen Benutzer permanent aus der Datenbank.
        ACHTUNG: Diese Operation kann nicht rückgängig gemacht werden!

        Args:
            db: Datenbank-Session
            user_id: ID des zu löschenden Benutzers

        Returns:
            Dict mit Erfolgs-Status
        """
        # Prüfen ob Benutzer existiert
        user = await UserService.get_user_by_id(db, user_id)
        if not user:
            return {"success": False, "message": "User not found"}

        # Hard delete: Benutzer permanent löschen
        await db.execute(delete(UserModel).where(UserModel.id == user_id))
        await db.commit()

        return {"success": True, "message": f"User {user_id} permanently deleted"}

    # ─────────────────────────────────────────────────────────────────
    # GDPR Art. 17 — user anonymisation (Slice 0)
    # ─────────────────────────────────────────────────────────────────

    @staticmethod
    async def _get_or_create_sentinel(db: AsyncSession) -> UserModel:
        """Return the global sentinel user, creating it lazily if missing.

        The Slice 0 migration seeds this row, but we tolerate its absence
        so that (a) the service is robust against a manually truncated
        `users` table in non-production environments and (b) tests that
        bypass migrations (creating tables straight from `Base.metadata`)
        still see a sentinel.
        """
        result = await db.execute(
            select(UserModel).filter(UserModel.email == SENTINEL_EMAIL)
        )
        sentinel = result.scalar_one_or_none()
        if sentinel is not None:
            return sentinel

        # Lazily create — prefer id=0 for the documented global-sentinel
        # contract. If the dialect (or an existing row) blocks id=0, let
        # the primary key default assign whatever it wants; the email
        # remains the source-of-truth lookup.
        sentinel = UserModel(
            id=0,
            email=SENTINEL_EMAIL,
            hashed_password=SENTINEL_PASSWORD_HASH,
            first_name=SENTINEL_FIRST_NAME,
            last_name=None,
            role=UserRole.VIEWER,
            is_active=False,
            is_deleted=True,
            deleted_at=datetime.utcnow(),
            tenant_id=None,
            created_at=datetime.utcnow(),
        )
        db.add(sentinel)
        try:
            await db.flush()
        except SQLAlchemyError:
            # id=0 conflict fallback — retry with the sequence assigning.
            await db.rollback()
            sentinel = UserModel(
                email=SENTINEL_EMAIL,
                hashed_password=SENTINEL_PASSWORD_HASH,
                first_name=SENTINEL_FIRST_NAME,
                last_name=None,
                role=UserRole.VIEWER,
                is_active=False,
                is_deleted=True,
                deleted_at=datetime.utcnow(),
                tenant_id=None,
                created_at=datetime.utcnow(),
            )
            db.add(sentinel)
            await db.flush()

        if sentinel.id is None:  # pragma: no cover — defensive
            raise SentinelMissing(
                "Sentinel row could not be created — check the users table schema."
            )
        return sentinel

    @staticmethod
    async def anonymize_user(
        db: AsyncSession,
        user_id: int,
        *,
        reason: str,
        requested_by: int,
    ) -> AnonymizationResult:
        """Fulfil GDPR Art. 17 for a user (workforce data subject).

        Overwrites every PII column on the target `users` row with
        sentinel values, rewrites every FK reference across the
        registered tables to the global sentinel user, and records a
        `gdpr_requests` row for audit. The target row is **never**
        hard-deleted — its `id` and `role` survive so that RESTRICT FKs
        (enforced from Slice 1 onward) continue to resolve.

        Args:
            db: Async SQLAlchemy session. A single transaction wraps all
                writes so partial anonymisation is impossible.
            user_id: Id of the user to anonymise.
            reason: Non-PII free-text reason. Logged in `gdpr_requests.notes`.
            requested_by: Id of the admin (or the user themselves) who
                initiated the request. Stored for audit.

        Returns:
            AnonymizationResult summarising the operation. When the user
            was already anonymised, `already_anonymized=True` and
            `fk_updates == {}` — no exception is raised (idempotency).

        Raises:
            UserNotFound: `user_id` does not exist.
            LastAdminError: The target is the only active ADMIN.
            SentinelMissing: Sentinel row could not be resolved or created.
        """
        # ── 1. Load the target user. ────────────────────────────────
        result = await db.execute(select(UserModel).filter(UserModel.id == user_id))
        target = result.scalar_one_or_none()
        if target is None:
            raise UserNotFound(f"User {user_id} not found")

        # ── 2. Resolve the sentinel first — also guards against the
        #        self-anonymise-sentinel case: if the caller hands us the
        #        sentinel's own id, we bail out before touching FKs.
        sentinel = await UserService._get_or_create_sentinel(db)

        if target.id == sentinel.id:
            raise LastAdminError("Refusing to anonymise the global sentinel user.")

        # ── 3. Idempotency check. A previously anonymised row has
        #        `is_deleted=True` and a matching tracking hash. On a
        #        re-call we return the same tracking HMAC and a zero-
        #        count fk_updates map without touching anything.
        if target.is_deleted:
            tracking_hmac = _compute_tracking_hmac(target.id)
            # Look up the original gdpr_requests row by HMAC so callers
            # can correlate; this is best-effort.
            gdpr_row = await db.execute(
                select(GDPRRequest)
                .filter(GDPRRequest.notes.like(f"%{tracking_hmac}%"))
                .filter(GDPRRequest.request_type == "erasure_user")
                .order_by(GDPRRequest.requested_at.desc())
            )
            existing_request = gdpr_row.scalars().first()
            return AnonymizationResult(
                user_id=target.id,
                sentinel_user_id=sentinel.id,
                fk_updates={},
                tracking_hmac=tracking_hmac,
                gdpr_request_id=existing_request.id if existing_request else 0,
                already_anonymized=True,
            )

        # ── 4. Last-admin guard. ────────────────────────────────────
        if target.role == UserRole.ADMIN and target.is_active:
            admin_count_row = await db.execute(
                select(UserModel)
                .filter(UserModel.role == UserRole.ADMIN)
                .filter(UserModel.is_active.is_(True))
                .filter(UserModel.id != target.id)
                .filter(UserModel.is_deleted.is_(False))
            )
            other_admins = admin_count_row.scalars().all()
            if not other_admins:
                raise LastAdminError(
                    f"Refusing to anonymise the last active ADMIN (user {target.id})."
                )

        tracking_hmac = _compute_tracking_hmac(target.id)
        fk_updates: Dict[str, int] = {}

        # ── 5. Transactional rewrite of all FKs + PII overwrite. ────
        try:
            # Rewrite every registered FK column to the sentinel id.
            # Raw `text()` UPDATEs are used because the registry is by
            # table/column name, not mapped classes; this also keeps
            # the service independent of future ORM refactors.
            for table_name, column_name in ANONYMIZABLE_FK_TARGETS:
                stmt = text(
                    f"UPDATE {table_name} "  # nosec B608 — identifiers from registry, not user input
                    f"SET {column_name} = :sentinel_id "
                    f"WHERE {column_name} = :target_id"
                )
                res = await db.execute(
                    stmt,
                    {"sentinel_id": sentinel.id, "target_id": target.id},
                )
                # rowcount is -1 on some drivers; coerce to 0 in that case.
                fk_updates[f"{table_name}.{column_name}"] = max(res.rowcount or 0, 0)

            # Overwrite PII on the target row itself.
            now = datetime.utcnow()
            await db.execute(
                update(UserModel)
                .where(UserModel.id == target.id)
                .values(
                    email=f"deleted_{target.id}@anonymized.local",
                    hashed_password=SENTINEL_PASSWORD_HASH,
                    first_name=SENTINEL_FIRST_NAME,
                    last_name=None,
                    is_active=False,
                    is_deleted=True,
                    deleted_at=now,
                    anonymization_hash=tracking_hmac,
                )
            )

            # Record the GDPR request. `requested_by` is rewritten to
            # the sentinel when the requester was the subject themselves
            # (self-erasure), so the row survives post-anonymisation.
            effective_requested_by = (
                sentinel.id if requested_by == target.id else requested_by
            )
            gdpr_request = GDPRRequest(
                customer_id=None,
                request_type="erasure_user",
                status="completed",
                requested_at=now,
                completed_at=now,
                requested_by=effective_requested_by,
                notes=(
                    f"anonymize_user(user_id={target.id}) "
                    f"hmac={tracking_hmac} "
                    f"reason={reason}"
                ),
            )
            db.add(gdpr_request)

            await db.commit()
            await db.refresh(gdpr_request)
        except SQLAlchemyError:
            await db.rollback()
            logger.exception(
                "anonymize_user failed — transaction rolled back",
                extra={
                    "audit": True,
                    "action": "anonymize_user_failed",
                    "tracking_hmac": tracking_hmac,
                    "requested_by": requested_by,
                },
            )
            raise

        # Structured audit log. Uses the HMAC token instead of the raw
        # user id to keep log aggregators free of re-identifiable data.
        logger.info(
            "User anonymised (GDPR Art. 17)",
            extra={
                "audit": True,
                "action": "anonymize_user",
                "tracking_hmac": tracking_hmac,
                "sentinel_user_id": sentinel.id,
                "requested_by": requested_by,
                "self_erasure": requested_by == target.id,
                "fk_updates": fk_updates,
                "gdpr_request_id": gdpr_request.id,
            },
        )

        return AnonymizationResult(
            user_id=target.id,
            sentinel_user_id=sentinel.id,
            fk_updates=fk_updates,
            tracking_hmac=tracking_hmac,
            gdpr_request_id=gdpr_request.id,
            already_anonymized=False,
        )

    @staticmethod
    async def activate_user(db: AsyncSession, user_id: int) -> Optional[UserModel]:
        """
        Aktiviert einen deaktivierten Benutzer.

        Args:
            db: Datenbank-Session
            user_id: ID des zu aktivierenden Benutzers

        Returns:
            Aktiviertes User-Objekt oder None
        """
        user = await UserService.get_user_by_id(db, user_id)
        if not user:
            return None

        await db.execute(
            update(UserModel).where(UserModel.id == user_id).values(is_active=True)
        )
        await db.commit()

        # Aktualisiertes Objekt holen
        activated_user = await UserService.get_user_by_id(db, user_id)
        return activated_user
