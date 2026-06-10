"""E1 — Drop gdpr_requests.customer_id FK so Art. 30 audit rows can be written
on the 404-erasure path.

Issue #7. The original FK constraint (`gdpr_requests_customer_id_fkey`,
ON DELETE SET NULL) rejected any insert with a non-existent customer_id —
including the deliberate "audit before action" path in
`customers.py::_write_pending_gdpr_request` for the 404 case
(`test_customer_not_found_writes_failed_row`). SQLite hid this for the
whole life of the codebase; the PG integration job's first end-to-end
run (after the lint-decouple in PR #6) caught it.

Conceptual fix: an audit log of GDPR erasure requests must outlive its
subject (CLAUDE.md "Anonymize audit logs when user requests erasure")
and must accept requests for IDs that never existed (the Art. 30 404
case). FK enforcement contradicts both. Drop it; the column stays
`Integer NULL` so the existing test contract (`_all_gdpr_rows` queries
by the requested customer_id) keeps working.
"""
from typing import Sequence, Union

from alembic import op  # noqa: F401  (kept for symmetry; helpers wrap it)

from goldsmith_erp.db.migration_helpers import (
    create_fk_if_not_exists,
    drop_constraint_if_exists,
)

# revision identifiers, used by Alembic.
revision: str = "20260610_e1_gdpr_audit_nofk"
down_revision: Union[str, None] = "20260527_d1_activity_billable"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Idempotent. SQLite is a silent no-op inside the helper (ALTER TABLE
    # DROP CONSTRAINT isn't supported there, and SQLite never enforced
    # the FK anyway). v1_initial builds the schema via
    # `Base.metadata.create_all` from the live ORM — after this migration
    # lands, that ORM no longer declares the FK, so fresh PG installs
    # don't get the constraint either.
    drop_constraint_if_exists(
        "gdpr_requests_customer_id_fkey",
        "gdpr_requests",
        type_="foreignkey",
    )


def downgrade() -> None:
    # Best-effort restore. If the audit log already contains orphan
    # customer_ids (likely, once this fix is in production), the FK
    # creation will fail — that's the operator's signal that the
    # downgrade would lose Art. 30 audit semantics. See issue #7.
    create_fk_if_not_exists(
        "gdpr_requests_customer_id_fkey",
        "gdpr_requests",
        "customers",
        ["customer_id"],
        ["id"],
        ondelete="SET NULL",
    )
