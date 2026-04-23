"""H9 — Explicit ``ON DELETE RESTRICT`` on pre-V1.1 user FKs.

Anna Becker's post-wave-5 compliance audit (2026-04-17, see
`docs/superpowers/plans/qr-barcode-workflow/V1.1-POST-WAVE5-COMPLIANCE-AUDIT.md`
§4 finding **H9**) flagged a consistency gap: 11 pre-V1.1 user-FK columns
declare `ForeignKey("users.id")` without an explicit `ondelete=` clause.
PostgreSQL interprets that as `NO ACTION`, which is **semantically
equivalent** to `RESTRICT` for the anonymisation invariant (the hard-delete
path fails noisily instead of cascading), but the V1.1 migrations all use
`ON DELETE RESTRICT` explicitly. Normalising the legacy FKs to the same
clause makes the security invariant visible in schema-level tooling
(``\\d+ users`` in psql, ORM introspection, SchemaSpy) and prevents future
developers from copy-pasting a plain `ForeignKey("users.id")` into a
security-sensitive column and assuming the default is `CASCADE`.

The 11 FK columns touched here:

    customers.deleted_by                   (line 264 in db/models.py)
    order_comments.user_id                 (line 545)
    activities.created_by                  (line 596)
    time_entries.user_id                   (line 618)
    location_history.changed_by            (line 760)
    order_photos.taken_by                  (line 781)
    inventory_adjustments.adjusted_by_user_id   (line 1024)
    scrap_gold.created_by                  (line 1056)
    invoices.created_by                    (line 1251)
    quotes.created_by                      (line 1383)
    gdpr_requests.requested_by             (line 2172)

All 11 already appear in
``UserService.ANONYMIZABLE_FK_TARGETS`` — the anonymisation machinery was
correct before this migration. The migration is defence-in-depth only: it
makes the **DB-level** contract match the **service-level** one.

**Intentional exceptions** (NOT modified here — kept as-is):
  * `calendar_events.user_id`, `notifications.user_id`,
    `notification_preferences.user_id` — already `ON DELETE CASCADE`. These
    are *user-owned ephemera* (personal notification preferences, not
    audit trail); auto-cleanup when a user is hard-deleted is the intended
    semantic. `anonymize_user` doesn't touch these three.
  * `customer_measurements.measured_by`, `order_handoffs.from_user_id` /
    `.to_user_id`, `repair_jobs.received_by`, `repair_photos.taken_by`,
    `order_hallmarks.created_by`, `valuation_certificates.created_by`,
    `customer_audit_logs.user_id`, `order_status_history.changed_by` —
    already `ON DELETE SET NULL`. These carry an *intentional deletion
    contract*: the audit row survives user deletion with the user slot
    blanked. `anonymize_user` rewrites them to the sentinel user_id; the
    SET NULL path is the "belt" and the sentinel-rewrite is the
    "braces". Not changed to RESTRICT because that would break the
    audit-row-survives contract for code paths that legitimately
    hard-delete.

Migration semantics
-------------------

On **PostgreSQL**: DROP the existing FK (whose name follows the
SQLAlchemy default `{table}_{column}_fkey`), then ADD a new constraint
with `ON DELETE RESTRICT`. Idempotent via introspection — re-running
after a fresh install (where `create_all` already emitted the RESTRICT
FK inline from the ORM class) is a no-op.

On **SQLite**: `ALTER TABLE DROP CONSTRAINT` / `ADD CONSTRAINT` is not
supported. Fresh SQLite DBs built from the ORM via `Base.metadata.
create_all()` already carry the new FK clause inline (the ORM was
updated in the same commit), so the test suite has the correct
behaviour without any schema change here. Legacy SQLite DBs would need
a full `batch_alter_table` table-copy to normalise — we skip that path
deliberately because (a) this project's production is PostgreSQL and
(b) SQLite's `NO ACTION` and `RESTRICT` are functionally identical at
runtime, so the legacy-SQLite user sees no behavioural change.

Revision ID: 20260420_h9_restrict
Revises: 20260419_security_floor
Create Date: 2026-04-20
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from goldsmith_erp.db.migration_helpers import foreign_key_exists

# revision identifiers, used by Alembic.
revision: str = "20260420_h9_restrict"
down_revision: Union[str, None] = "20260419_security_floor"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (table, column) pairs whose user-FK is being normalised to RESTRICT.
# Ordered as listed in the H9 docstring above.
_FK_TARGETS: list[tuple[str, str]] = [
    ("customers", "deleted_by"),
    ("order_comments", "user_id"),
    ("activities", "created_by"),
    ("time_entries", "user_id"),
    ("location_history", "changed_by"),
    ("order_photos", "taken_by"),
    ("inventory_adjustments", "adjusted_by_user_id"),
    ("scrap_gold", "created_by"),
    ("invoices", "created_by"),
    ("quotes", "created_by"),
    ("gdpr_requests", "requested_by"),
]


def _resolve_fk_name(inspector, table: str, column: str) -> str | None:
    """Return the current FK constraint name targeting ``users.id`` on
    (table, column), or None if no such FK is materialised.
    """
    if table not in inspector.get_table_names():
        return None
    try:
        fks = inspector.get_foreign_keys(table)
    except NotImplementedError:
        return None
    for fk in fks:
        if (
            fk.get("referred_table") == "users"
            and fk.get("constrained_columns") == [column]
        ):
            return fk.get("name")
    return None


def upgrade() -> None:
    """Drop + re-add each of the 11 user-FKs with ``ON DELETE RESTRICT``.

    SQLite: no-op (the ORM's inline FK on a fresh DB is already RESTRICT
    because ``db/models.py`` was updated in the same commit).
    PostgreSQL: introspect the current FK name, drop it, re-create with
    the explicit RESTRICT clause. Deterministic constraint name used on
    re-add so a subsequent downgrade can find it again.
    """
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        # Fresh DB: ORM's inline FK already carries RESTRICT.
        # Legacy DB: functional equivalent; ALTER path not supported.
        return

    from sqlalchemy import inspect as _inspect  # noqa: PLC0415

    inspector = _inspect(bind)
    for table, column in _FK_TARGETS:
        new_name = f"fk_{table}_{column}_users_restrict"
        # Idempotent: already run.
        if foreign_key_exists(table, new_name):
            continue
        existing_name = _resolve_fk_name(inspector, table, column)
        if existing_name is not None:
            op.drop_constraint(existing_name, table, type_="foreignkey")
        op.create_foreign_key(
            new_name,
            source_table=table,
            referent_table="users",
            local_cols=[column],
            remote_cols=["id"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    """Revert each FK to the unnamed default-``NO ACTION`` form.

    Downgrade restores the *original* clause semantics (`NO ACTION`),
    not the *original* FK name (which was an auto-generated SQLAlchemy
    default that we can't deterministically reconstruct without
    introspection of the source DB). The re-added FK uses a
    predictable compatibility name.

    F2a fix (2026-04-23) — idempotent drop-before-create
    ----------------------------------------------------
    A previous issue bit the CI smoke-test: on fresh PG 15 the
    ``customers.deleted_by`` column ended up carrying *two* FKs after
    ``upgrade()`` —

      * ``fk_customers_deleted_by_users`` (created by migration
        ``20260406_review`` via ``create_fk_if_not_exists`` **after**
        ``v1_initial``'s ``create_all()`` already added the ORM-level
        ``customers_deleted_by_fkey`` — the helper checks by NAME, not
        by column, so it happily added a duplicate) and
      * ``fk_customers_deleted_by_users_restrict`` (this migration).

    H9's ``upgrade()`` introspects by ``(referred_table, column)`` and
    drops the *first* match, leaving the second untouched. On
    ``downgrade()`` the attempt to ``op.create_foreign_key(
    "fk_customers_deleted_by_users", ...)`` then collided with the
    still-present sibling.

    The fix is a defensive sweep: for every ``(table, column)`` in
    ``_FK_TARGETS`` we enumerate *all* existing FKs on that column
    that reference ``users`` and drop them before re-creating the
    single deterministic compatibility constraint. This is idempotent
    for the healthy case (at most one ``_restrict`` FK to drop) and
    correctly heals the duplicate-FK case too.
    """
    bind = op.get_bind()
    if bind.dialect.name == "sqlite":
        return

    inspector = sa.inspect(bind)
    for table, column in _FK_TARGETS:
        new_name = f"fk_{table}_{column}_users_restrict"
        if not foreign_key_exists(table, new_name):
            continue

        # Drop ALL FKs on (table, column) that reference users — covers
        # both the `_restrict` FK we just created and any pre-existing
        # sibling whose name collides with the compatibility name we
        # are about to re-create (see docstring for the customers.deleted_by
        # case). Guarded with a None-name check because some dialects
        # report unnamed FKs.
        for fk in inspector.get_foreign_keys(table):
            if (
                fk.get("referred_table") == "users"
                and fk.get("constrained_columns") == [column]
                and fk.get("name")
            ):
                op.drop_constraint(fk["name"], table, type_="foreignkey")

        op.create_foreign_key(
            f"fk_{table}_{column}_users",
            source_table=table,
            referent_table="users",
            local_cols=[column],
            remote_cols=["id"],
        )
