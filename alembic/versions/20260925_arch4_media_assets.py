"""ARCH phase 4: ``media_assets`` table + copy of the three photo tables.

See docs/architecture/ADR-2026-09-25-media.md.

Schema
------
* ``owner_type`` (order / repair / consultation / customer_update) and
  ``kind`` (photo / signature / document) are String columns with CHECK
  constraints, not PG enums, so a new value needs no ``ALTER TYPE``.
* ``owner_id`` is a polymorphic reference (no FK); ``uploaded_by`` is a FK to
  ``users`` with ``ON DELETE SET NULL``.
* ``legacy_id`` / ``tag`` bridge a row to its deprecated source row
  (``order_photos.id``, ``repair_photos.id``, ``consultation_photos.id``) and
  that row's phase or kind.

Data copy
---------
Every row of ``order_photos``, ``repair_photos`` and ``consultation_photos``
is copied into ``media_assets`` (kind ``photo``, ``customer_visible`` false,
``storage_key`` = the old ``file_path``, which ``LocalMediaStore`` still
reads). Order and consultation rows keep their uuid as the media id; repair
rows (integer ids) get a fresh uuid. For files that exist inside the media
root the size, sha256 and pixel dimensions are recomputed; a missing file, or
a path outside the root, is logged by id and copied without them (never
fatal). Rows already erased under Art. 17 (``[REDACTED_PATH]``) are not
copied. The copy is idempotent: rows already bridged are skipped.

The legacy tables and rows are kept (deprecated, dual-written for one
release).

Idempotency: ``media_assets`` is on the ORM, so on a fresh DB
``v1_initial``'s ``create_all()`` has created it already; the DDL below is
guarded via the ``*_if_not_exists`` helpers. Works on SQLite and PostgreSQL.

Downgrade drops ``media_assets`` (the legacy rows still hold every photo; only
the ``customer_visible`` flags and captions edited after the upgrade are lost).

Revision ID: 20260925_arch4_media
Revises: 20260925_be15_tz
Create Date: 2026-09-25
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Sequence, Tuple, Union

import sqlalchemy as sa

from alembic import op

revision: str = "20260925_arch4_media"
down_revision: Union[str, None] = "20260925_be15_tz"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

logger = logging.getLogger("alembic.runtime.migration")

TABLE = "media_assets"
REDACTED_PATH_SENTINEL = "[REDACTED_PATH]"
_EXT_TO_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".pdf": "application/pdf",
}

# (legacy table, owner_type, owner column, tag column, id is uuid)
LEGACY_SOURCES: Tuple[Tuple[str, str, str, Optional[str], bool], ...] = (
    ("order_photos", "order", "order_id", None, True),
    ("repair_photos", "repair", "repair_job_id", "phase", False),
    ("consultation_photos", "consultation", "consultation_id", "kind", True),
)


def _columns() -> list:
    return [
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("owner_type", sa.String(length=20), nullable=False),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False, server_default="photo"),
        sa.Column("storage_key", sa.String(length=500), nullable=False),
        sa.Column("mime", sa.String(length=100), nullable=False),
        sa.Column("bytes", sa.Integer(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("sha256", sa.String(length=64), nullable=True),
        sa.Column(
            "customer_visible",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("caption", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("taken_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "uploaded_by",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("legacy_id", sa.String(length=36), nullable=True),
        sa.Column("tag", sa.String(length=32), nullable=True),
        sa.CheckConstraint(
            "owner_type IN ('order', 'repair', 'consultation', 'customer_update')",
            name="ck_media_assets_owner_type",
        ),
        sa.CheckConstraint(
            "kind IN ('photo', 'signature', 'document')",
            name="ck_media_assets_kind",
        ),
    ]


def _media_root() -> Path:
    from goldsmith_erp.core.config import settings  # noqa: PLC0415

    return Path(settings.PHOTO_STORAGE_PATH).resolve()


def _resolve_within(raw_path: str, root: Path) -> Optional[Path]:
    """Resolved path of ``raw_path`` if it lies inside ``root``, else None."""
    if not raw_path:
        return None
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        resolved = candidate.resolve(strict=False)
    except (OSError, RuntimeError):
        return None
    return resolved if resolved.is_relative_to(root) else None


def _file_facts(
    raw_path: str, root: Path
) -> Tuple[Optional[int], Optional[str], Optional[int], Optional[int]]:
    """(bytes, sha256, width, height) of a stored file; Nones if unusable."""
    resolved = _resolve_within(raw_path, root)
    if resolved is None or not resolved.is_file():
        return None, None, None, None
    data = resolved.read_bytes()
    width: Optional[int] = None
    height: Optional[int] = None
    try:
        import io  # noqa: PLC0415

        from PIL import Image  # noqa: PLC0415

        with Image.open(io.BytesIO(data)) as probe:
            width, height = int(probe.width), int(probe.height)
    except Exception:  # noqa: BLE001 - dimensions are informational
        pass
    return len(data), hashlib.sha256(data).hexdigest(), width, height


def _as_datetime(value: Any, naive_storage: bool) -> Optional[datetime]:
    """Legacy timestamp as UTC; naive on SQLite (how UtcDateTime stores it)."""
    if value is None:
        return None
    if not isinstance(value, datetime):
        try:
            value = datetime.fromisoformat(str(value))
        except ValueError:
            return None
    aware = (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )
    return aware.replace(tzinfo=None) if naive_storage else aware


def copy_legacy_photos(conn: sa.engine.Connection, root: Path) -> Dict[str, int]:
    """Copy the three legacy photo tables into ``media_assets``.

    Returns counters: ``<table>`` rows copied, ``<table>_skipped`` (already
    bridged or redacted), ``missing_files`` and ``hashed_files``.
    """
    counts: Dict[str, int] = {"missing_files": 0, "hashed_files": 0}
    existing_tables = set(sa.inspect(conn).get_table_names())
    media = sa.table(
        TABLE,
        *[sa.column(c.name, c.type) for c in _columns() if isinstance(c, sa.Column)],
    )
    already = {
        (row.owner_type, row.legacy_id)
        for row in conn.execute(sa.text(f"SELECT owner_type, legacy_id FROM {TABLE}"))
    }
    naive_storage = conn.dialect.name == "sqlite"
    now = _as_datetime(datetime.now(timezone.utc), naive_storage)
    for table, owner_type, owner_col, tag_col, uuid_ids in LEGACY_SOURCES:
        counts[table] = 0
        counts[f"{table}_skipped"] = 0
        if table not in existing_tables:
            continue
        tag_sql = f", {tag_col} AS tag" if tag_col else ", NULL AS tag"
        rows = conn.execute(
            sa.text(
                f'SELECT id, {owner_col} AS owner_id, file_path, "timestamp",'
                f" taken_by, notes{tag_sql} FROM {table}"
                f' ORDER BY {owner_col}, "timestamp", id'
            )
        ).fetchall()
        sort_by_owner: Dict[int, int] = {}
        batch = []
        for row in rows:
            legacy_id = str(row.id)
            if (owner_type, legacy_id) in already or (
                row.file_path == REDACTED_PATH_SENTINEL
            ):
                counts[f"{table}_skipped"] += 1
                continue
            size, digest, width, height = _file_facts(row.file_path, root)
            if digest is None:
                counts["missing_files"] += 1
                logger.warning(
                    "media copy: file missing or outside the media root",
                    extra={"table": table, "legacy_id": legacy_id},
                )
            else:
                counts["hashed_files"] += 1
            sort_order = sort_by_owner.get(row.owner_id, 0)
            sort_by_owner[row.owner_id] = sort_order + 1
            taken_at = _as_datetime(row.timestamp, naive_storage)
            tag = row.tag.lower() if isinstance(row.tag, str) else row.tag
            batch.append(
                {
                    "id": legacy_id if uuid_ids else str(uuid.uuid4()),
                    "owner_type": owner_type,
                    "owner_id": row.owner_id,
                    "kind": "photo",
                    "storage_key": row.file_path,
                    "mime": _EXT_TO_MIME.get(
                        Path(row.file_path).suffix.lower(), "application/octet-stream"
                    ),
                    "bytes": size,
                    "width": width,
                    "height": height,
                    "sha256": digest,
                    "customer_visible": False,
                    "caption": row.notes,
                    "sort_order": sort_order,
                    "taken_at": taken_at,
                    "uploaded_by": row.taken_by,
                    "created_at": taken_at or now,
                    "deleted_at": None,
                    "legacy_id": legacy_id,
                    "tag": tag,
                }
            )
        if batch:
            conn.execute(sa.insert(media), batch)
        counts[table] = len(batch)
    logger.info("media copy finished: %s", counts)
    return counts


def upgrade() -> None:
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        create_index_if_not_exists,
        create_table_if_not_exists,
    )

    create_table_if_not_exists(TABLE, *_columns())
    # Names match the ORM (MediaAsset + its Index() declarations).
    create_index_if_not_exists("ix_media_assets_sha256", TABLE, ["sha256"])
    create_index_if_not_exists(
        "ix_media_assets_owner", TABLE, ["owner_type", "owner_id"]
    )
    create_index_if_not_exists(
        "ix_media_assets_legacy", TABLE, ["owner_type", "legacy_id"]
    )
    copy_legacy_photos(op.get_bind(), _media_root())


def downgrade() -> None:
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        drop_index_if_exists,
        drop_table_if_exists,
    )

    drop_index_if_exists("ix_media_assets_legacy", TABLE)
    drop_index_if_exists("ix_media_assets_owner", TABLE)
    drop_index_if_exists("ix_media_assets_sha256", TABLE)
    drop_table_if_exists(TABLE)
