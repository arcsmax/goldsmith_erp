"""R1 — purge blob: placeholder rows + quarantine unanchored paths in repair_photos.

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

Step 1 hard-deletes those rows.

Step 2 (security quarantine): the legacy endpoint imposed NO validation on
``file_path`` beyond ``max_length=500`` — a hostile or accidental client
value like ``/etc/passwd`` or ``../../.env`` would survive the blob purge
and, once the new serve/delete endpoints exist, would be an arbitrary file
read/delete primitive if it reached filesystem I/O. The service layer now
anchors every stored path to ``PHOTO_STORAGE_PATH``
(``image_validation.resolve_within_root``) as the primary defense; this
step removes the tainted rows at the source so they don't linger as
permanent 404s. Any row whose ``file_path``, resolved with the SAME
anchoring rule, does not land under ``PHOTO_STORAGE_PATH`` is deleted.
Rows already redacted to ``[REDACTED_PATH]`` by a GDPR Art. 17 file-erasure
sweep are explicitly KEPT (Art. 30 retention — the sentinel intentionally
references no file).

Safe by construction: at the time this migration runs, no service-written
rows can exist yet — the multipart endpoint that writes real
``PHOTO_STORAGE_PATH``-anchored paths ships in the SAME release as this
migration, so every row surviving the blob purge is a legacy
client-supplied string with no server-side file behind it.

This migration is data cleanup, not a schema change:
``repair_photos.file_path`` keeps its existing ``String(500) NOT NULL``
definition.

Idempotency
-----------
A fresh DB (``v1_initial`` via ``create_all()``) has no ``repair_photos``
rows at all, so both the blob ``DELETE`` and the quarantine loop are
no-ops there. Re-running against an already-cleaned DB finds no matching
rows and is likewise a no-op. Guarded by ``table_exists`` so a
hypothetical bare-metadata DB without the table does not error.

Downgrade
---------
Deliberately a no-op. The deleted rows never referenced a real server file
(browser-local blob URLs / unanchored client strings) — there is nothing
to restore, matching this repo's precedent for destructive cleanup
migrations (e.g. I12's ``_dedupe_no_gos_by_value_hash``) not attempting to
resurrect removed rows.

Revision ID: 20260703_r1_repair_photo_cleanup
Revises: 20260703_i12_no_go_unique_idx
Create Date: 2026-07-03
"""

from __future__ import annotations

from pathlib import Path
from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "20260703_r1_repair_photo_cleanup"
down_revision: Union[str, None] = "20260703_i12_no_go_unique_idx"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Keep in sync with file_erasure_service.REDACTED_PATH_SENTINEL (imported
# locally in upgrade() — mirrored here in the docstring for readability).


def _quarantine_unanchored_rows(bind: sa.engine.Connection) -> None:
    """Delete rows whose ``file_path`` does not resolve under the storage root.

    Uses the SAME anchoring rule as the service layer
    (``image_validation.resolve_within_root``: relative paths anchored under
    the root, absolute paths resolved as-is, symlinks followed,
    ``is_relative_to`` check) so migration and runtime agree on what
    "inside the root" means. Sentinel rows from GDPR erasure are kept.
    """
    from goldsmith_erp.core.config import settings  # noqa: PLC0415
    from goldsmith_erp.services.file_erasure_service import (  # noqa: PLC0415
        REDACTED_PATH_SENTINEL,
    )
    from goldsmith_erp.services.image_validation import (  # noqa: PLC0415
        resolve_within_root,
    )

    root = Path(settings.PHOTO_STORAGE_PATH)

    photos_t = sa.table(
        "repair_photos",
        sa.column("id", sa.Integer),
        sa.column("file_path", sa.String),
    )
    rows = bind.execute(sa.select(photos_t.c.id, photos_t.c.file_path)).fetchall()

    quarantined_ids = []
    for row in rows:
        if row.file_path == REDACTED_PATH_SENTINEL:
            # Redacted by a prior Art. 17 file-erasure sweep — the row is
            # retained for Art. 30 record-keeping and intentionally
            # references no file. Keep.
            continue
        if resolve_within_root(row.file_path, root) is None:
            quarantined_ids.append(row.id)

    if quarantined_ids:
        bind.execute(sa.delete(photos_t).where(photos_t.c.id.in_(quarantined_ids)))


def upgrade() -> None:
    from goldsmith_erp.db.migration_helpers import table_exists  # noqa: PLC0415

    if not table_exists("repair_photos"):
        return

    # Step 1 — purge blob: placeholder rows (never had a server file).
    op.execute("DELETE FROM repair_photos WHERE file_path LIKE 'blob:%'")

    # Step 2 — quarantine any remaining legacy client-supplied path that
    # does not anchor under PHOTO_STORAGE_PATH (see module docstring).
    _quarantine_unanchored_rows(op.get_bind())


def downgrade() -> None:
    # No-op — see module docstring "Downgrade" section. The purged rows
    # referenced no real server file; there is nothing to restore.
    pass
