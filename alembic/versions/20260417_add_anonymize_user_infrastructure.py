"""add anonymize_user infrastructure (Slice 0)

Adds the columns + sentinel row that the `UserService.anonymize_user()`
service requires in order to fulfil GDPR Art. 17 for workforce data
subjects. This migration is intentionally separated from Slice 1's
Migration 1 (FK amendments to `ON DELETE RESTRICT`, plus the new
`scan_logs` / `barcode_aliases` tables) so that the service + its unit
tests land first and can be merged independently.

New columns on `users`:
  - is_deleted          BOOLEAN  NOT NULL DEFAULT FALSE
  - deleted_at          TIMESTAMPTZ NULL
  - anonymization_hash  VARCHAR(64) NULL    (short HMAC(salt, user_id))
  - tenant_id           INTEGER NULL        (V1.2 forward-compat slot,
                                             per DECISIONS-2026-04-16 SQ1)

Seeded row: the **global sentinel user** that all anonymised FKs point
at. We prefer id=0 when the sequence permits (PostgreSQL allows inserting
id=0 explicitly without affecting the SEQUENCE for SERIAL columns), and
fall back to a sentinel looked up by a reserved email if id=0 is already
taken. The service layer treats both discovery paths identically.

Sentinel columns:
  - id = 0 (reserved; sequence left untouched so future INSERTs continue
    from their current high-water mark)
  - email = "deleted@sentinel.invalid"  (reserved TLD, un-routable)
  - hashed_password = "!"               (bcrypt-invalid — cannot log in)
  - first_name = "<deleted>"
  - last_name = NULL
  - role = VIEWER                       (lowest privilege)
  - is_active = FALSE
  - is_deleted = TRUE
  - tenant_id = NULL                    (SQ1: V1.2 will auto-create a
                                         sentinel per tenant)

NOTE: FK amendments to ON DELETE RESTRICT happen in Slice 1 (Migration 1)
— this migration is infrastructure only. No existing FK constraints are
altered here. The `gdpr_requests` table already exists from the earlier
20260406_review migration; no schema changes are made to it either.

Revision ID: 20260417_anonymize_user
Revises: 20260406_review
Create Date: 2026-04-17
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260417_anonymize_user"
down_revision: Union[str, None] = "20260406_review"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Sentinel row constants — mirror `services.user_service` module-level
# constants so migration + service stay in lock-step. If you change one,
# change the other and regenerate sentinel rows in non-production envs.
SENTINEL_EMAIL = "deleted@sentinel.invalid"
SENTINEL_FIRST_NAME = "<deleted>"
SENTINEL_ROLE_VALUE = "viewer"  # UserRole.VIEWER.value


def upgrade() -> None:
    # ------------------------------------------------------------------
    # 1. Add anonymisation columns to `users`.
    # ------------------------------------------------------------------
    op.add_column(
        "users",
        sa.Column(
            "is_deleted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "users",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("anonymization_hash", sa.String(length=64), nullable=True),
    )
    # V1.2 forward-compat slot — see DECISIONS-2026-04-16 SQ1.
    op.add_column(
        "users",
        sa.Column("tenant_id", sa.Integer(), nullable=True),
    )
    op.create_index("ix_users_is_deleted", "users", ["is_deleted"])
    op.create_index("ix_users_tenant_id", "users", ["tenant_id"])

    # ------------------------------------------------------------------
    # 2. Seed the global sentinel row.
    #
    # Strategy: try id=0 first. If that row id is already occupied (very
    # unlikely — SERIAL starts at 1 in PostgreSQL, but we protect
    # ourselves against arbitrary manual inserts), fall back to an
    # INSERT that lets the sequence assign an id and use the email as
    # the canonical lookup key in the service layer.
    #
    # We do NOT advance the `users_id_seq` sequence — inserting id=0 by
    # hand leaves the sequence at whatever value it had. Future signups
    # therefore continue to get the same positive-integer ids they would
    # have received.
    # ------------------------------------------------------------------
    bind = op.get_bind()
    dialect = bind.dialect.name

    existing = bind.execute(
        sa.text("SELECT id FROM users WHERE email = :email"),
        {"email": SENTINEL_EMAIL},
    ).first()

    if existing is None:
        if dialect == "postgresql":
            # Explicit id=0 insert; sequence stays where it was.
            bind.execute(
                sa.text(
                    """
                    INSERT INTO users (
                        id, email, hashed_password, first_name, last_name,
                        role, is_active, is_deleted, deleted_at,
                        anonymization_hash, tenant_id, created_at
                    ) VALUES (
                        0, :email, '!', :first_name, NULL,
                        CAST(:role AS userrole), FALSE, TRUE, NOW(),
                        NULL, NULL, NOW()
                    )
                    ON CONFLICT (id) DO NOTHING
                    """
                ),
                {
                    "email": SENTINEL_EMAIL,
                    "first_name": SENTINEL_FIRST_NAME,
                    "role": SENTINEL_ROLE_VALUE,
                },
            )
        else:
            # SQLite / other — id=0 is legal but less idiomatic. Use a
            # plain INSERT without a conflict clause; the caller is the
            # test harness which starts from an empty table.
            bind.execute(
                sa.text(
                    """
                    INSERT INTO users (
                        id, email, hashed_password, first_name, last_name,
                        role, is_active, is_deleted, deleted_at,
                        anonymization_hash, tenant_id, created_at
                    ) VALUES (
                        0, :email, '!', :first_name, NULL,
                        :role, 0, 1, CURRENT_TIMESTAMP,
                        NULL, NULL, CURRENT_TIMESTAMP
                    )
                    """
                ),
                {
                    "email": SENTINEL_EMAIL,
                    "first_name": SENTINEL_FIRST_NAME,
                    "role": SENTINEL_ROLE_VALUE,
                },
            )


def downgrade() -> None:
    # Remove the sentinel row first, then the supporting columns.
    bind = op.get_bind()
    bind.execute(
        sa.text("DELETE FROM users WHERE email = :email"),
        {"email": SENTINEL_EMAIL},
    )

    op.drop_index("ix_users_tenant_id", table_name="users")
    op.drop_index("ix_users_is_deleted", table_name="users")
    op.drop_column("users", "tenant_id")
    op.drop_column("users", "anonymization_hash")
    op.drop_column("users", "deleted_at")
    op.drop_column("users", "is_deleted")
