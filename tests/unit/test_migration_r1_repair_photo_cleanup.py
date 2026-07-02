"""Migration tests for R1 — repair photo cleanup + unanchored-path quarantine.

Exercises ``20260703_r1_repair_photo_cleanup`` against an isolated SQLite
database (same file-path-import harness as ``test_migration_qr_core.py``),
seeding rows via raw connection to simulate the legacy client-supplied
``file_path`` data the old JSON endpoint accepted without validation.

Coverage:

  * blob: placeholder rows are hard-deleted.
  * Unanchored paths (absolute escape ``/etc/passwd``, relative traversal
    ``../../outside.txt``) are quarantined (deleted).
  * Anchored paths (absolute under PHOTO_STORAGE_PATH, relative that
    anchors under it) are KEPT.
  * GDPR ``[REDACTED_PATH]`` sentinel rows are KEPT (Art. 30 retention).
  * Idempotency — a second upgrade() run changes nothing.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, select

from alembic.migration import MigrationContext
from alembic.operations import Operations
from goldsmith_erp.services.file_erasure_service import REDACTED_PATH_SENTINEL

MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "20260703_r1_repair_photo_cleanup.py"
)


def _load_migration_module():
    spec = importlib.util.spec_from_file_location("r1_migration", str(MIGRATION_PATH))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _minimal_repair_photos_table(metadata: MetaData) -> Table:
    """Bare-bones ``repair_photos`` stand-in — only the columns R1 touches."""
    return Table(
        "repair_photos",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("file_path", String(500), nullable=False),
    )


@pytest.fixture
def sqlite_engine(tmp_path):
    db_file = tmp_path / "r1.db"
    engine = create_engine(f"sqlite:///{db_file}", future=True)
    yield engine
    engine.dispose()


def _run_upgrade(engine, module) -> None:
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            module.upgrade()
        conn.commit()


def test_r1_purges_blob_and_quarantines_unanchored_rows(
    sqlite_engine, tmp_path, monkeypatch
):
    storage_root = tmp_path / "photos"
    monkeypatch.setattr(
        "goldsmith_erp.core.config.settings.PHOTO_STORAGE_PATH", str(storage_root)
    )

    metadata = MetaData()
    photos_t = _minimal_repair_photos_table(metadata)
    metadata.create_all(sqlite_engine)

    anchored_abs = str(storage_root / "repairs" / "1" / "abc.jpg")
    rows = {
        1: "blob:http://localhost/deadbeef",  # legacy placeholder → purged
        2: "/etc/passwd",  # absolute escape → quarantined
        3: "../../outside.txt",  # relative traversal → quarantined
        4: anchored_abs,  # anchored absolute → kept
        5: "repairs/1/rel.jpg",  # anchored relative → kept
        6: REDACTED_PATH_SENTINEL,  # GDPR-redacted → kept
    }
    with sqlite_engine.connect() as conn:
        conn.execute(
            photos_t.insert(),
            [{"id": pk, "file_path": fp} for pk, fp in rows.items()],
        )
        conn.commit()

    module = _load_migration_module()
    _run_upgrade(sqlite_engine, module)

    with sqlite_engine.connect() as conn:
        remaining = dict(
            conn.execute(select(photos_t.c.id, photos_t.c.file_path)).fetchall()
        )
    assert remaining == {4: anchored_abs, 5: "repairs/1/rel.jpg", 6: rows[6]}

    # Idempotency — second run is a no-op.
    _run_upgrade(sqlite_engine, module)
    with sqlite_engine.connect() as conn:
        remaining_after_rerun = dict(
            conn.execute(select(photos_t.c.id, photos_t.c.file_path)).fetchall()
        )
    assert remaining_after_rerun == remaining


def test_r1_noop_when_table_missing(sqlite_engine):
    """A bare DB without repair_photos must not error (table_exists guard)."""
    module = _load_migration_module()
    _run_upgrade(sqlite_engine, module)  # must not raise
