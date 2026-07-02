"""R1 — purge blob: placeholder rows from repair_photos.

Part of the V1.1 repair photo-intake checklist prerequisite (make repair
photo upload real). Before this change, ``POST /repairs/{id}/photos``
accepted a client-supplied ``file_path`` string — the frontend sent
ephemeral ``blob:...`` object-URLs (browser-local, never a real server
path) because no multipart upload endpoint existed. Every ``repair_photos``
row created that way has ``file_path LIKE 'blob:%'``: it never had a
corresponding file on the server's filesystem, so there is nothing for
``RepairPhotoService`` (or ``FileErasureService``) to resolve, serve, or
erase — the row is pure noise that would 404 on every read attempt after
this branch flips the endpoint to real multipart storage.

This migration hard-deletes those rows. It is data cleanup, not a schema
change: ``repair_photos.file_path`` keeps its existing ``String(500)
NOT NULL`` definition.

Idempotency
-----------
A fresh DB (``v1_initial`` via ``create_all()``) has no ``repair_photos``
rows at all, so the ``DELETE ... WHERE file_path LIKE 'blob:%'`` is a
no-op there. Re-running this migration against an already-cleaned DB
(no more matching rows) is likewise a no-op. Guarded by ``table_exists``
so a hypothetical bare-metadata DB without the table does not error.

Downgrade
---------
Deliberately a no-op. The deleted rows never referenced a real file (no
filesystem artefact was lost) and their content was a browser-local blob
URL with zero server-side meaning — there is nothing to restore, matching
this repo's precedent for destructive dedupe migrations (e.g. I12's
``_dedupe_no_gos_by_value_hash``) not attempting to resurrect removed rows.

Revision ID: 20260703_r1_repair_photo_cleanup
Revises: 20260703_i12_no_go_unique_idx
Create Date: 2026-07-03
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260703_r1_repair_photo_cleanup"
down_revision: Union[str, None] = "20260703_i12_no_go_unique_idx"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    from goldsmith_erp.db.migration_helpers import table_exists  # noqa: PLC0415

    if not table_exists("repair_photos"):
        return

    op.execute("DELETE FROM repair_photos WHERE file_path LIKE 'blob:%'")


def downgrade() -> None:
    # No-op — see module docstring "Downgrade" section. The purged rows
    # referenced no real file; there is nothing to restore.
    pass
