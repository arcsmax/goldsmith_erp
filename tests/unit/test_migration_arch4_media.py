"""Migration tests for 20260925_arch4_media (ARCH phase 4, media_assets).

Runs the migration in isolation on a scratch SQLite DB that carries minimal
copies of the three legacy photo tables, then checks the data copy: rows
counted, sha256 recomputed for files that exist, missing files logged (not
fatal), redacted rows skipped, idempotent re-run, and up/down/up.
"""

from __future__ import annotations

import hashlib
import importlib.util
import logging
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError

from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory

_ROOT = Path(__file__).resolve().parents[2]
_PATH = _ROOT / "alembic" / "versions" / "20260925_arch4_media_assets.py"
_REVISION = "20260925_arch4_media"

_LEGACY_DDL = (
    "CREATE TABLE users (id INTEGER PRIMARY KEY)",
    "CREATE TABLE order_photos (id VARCHAR(36) PRIMARY KEY, order_id INTEGER,"
    " time_entry_id VARCHAR(36), file_path VARCHAR(500), timestamp DATETIME,"
    " taken_by INTEGER, notes TEXT)",
    "CREATE TABLE repair_photos (id INTEGER PRIMARY KEY, repair_job_id INTEGER,"
    " phase VARCHAR(20), file_path VARCHAR(500), timestamp DATETIME,"
    " taken_by INTEGER, notes TEXT)",
    "CREATE TABLE consultation_photos (id VARCHAR(36) PRIMARY KEY,"
    " consultation_id INTEGER, order_id INTEGER, kind VARCHAR(20),"
    " file_path VARCHAR(500), timestamp DATETIME, taken_by INTEGER, notes TEXT)",
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("arch4_media", str(_PATH))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def media_root(tmp_path, monkeypatch):
    root = tmp_path / "photos"
    root.mkdir()
    monkeypatch.setattr(
        "goldsmith_erp.core.config.settings.PHOTO_STORAGE_PATH", str(root)
    )
    return root.resolve()


@pytest.fixture
def engine(tmp_path, media_root):
    eng = create_engine(f"sqlite:///{tmp_path / 'arch4.db'}", future=True)
    with eng.begin() as conn:
        for ddl in _LEGACY_DDL:
            conn.execute(text(ddl))
    yield eng
    eng.dispose()


def _run(engine, fn_name: str) -> None:
    module = _load_migration()
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            getattr(module, fn_name)()
        conn.commit()


def _write_png(path: Path) -> bytes:
    from PIL import Image

    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (40, 30), color=(200, 10, 10)).save(path, format="PNG")
    return path.read_bytes()


def _seed(engine, media_root: Path) -> dict:
    order_file = media_root / "7" / "a.png"
    repair_file = media_root / "repairs" / "3" / "b.png"
    order_bytes = _write_png(order_file)
    repair_bytes = _write_png(repair_file)
    missing = media_root / "consultations" / "5" / "gone.jpg"
    with engine.begin() as conn:
        conn.execute(text("INSERT INTO users (id) VALUES (1)"))
        conn.execute(
            text(
                "INSERT INTO order_photos VALUES "
                "('11111111-1111-1111-1111-111111111111', 7, NULL, :p,"
                " '2026-09-01 10:00:00', 1, 'Vorderseite'),"
                "('22222222-2222-2222-2222-222222222222', 7, NULL, '[REDACTED_PATH]',"
                " '2026-09-02 10:00:00', 1, NULL)"
            ),
            {"p": str(order_file)},
        )
        conn.execute(
            text(
                "INSERT INTO repair_photos VALUES "
                "(1, 3, 'intake', :p, '2026-09-03 10:00:00', 1, NULL),"
                "(2, 3, 'completed', '/etc/passwd', '2026-09-04 10:00:00', NULL, NULL)"
            ),
            {"p": str(repair_file)},
        )
        conn.execute(
            text(
                "INSERT INTO consultation_photos VALUES "
                "('33333333-3333-3333-3333-333333333333', 5, NULL, 'sketch', :p,"
                " '2026-09-05 10:00:00', 1, 'Skizze')"
            ),
            {"p": str(missing)},
        )
    return {
        "order_sha": hashlib.sha256(order_bytes).hexdigest(),
        "repair_sha": hashlib.sha256(repair_bytes).hexdigest(),
        "order_file": str(order_file),
    }


def _assets(engine) -> list:
    with engine.connect() as conn:
        return list(
            conn.execute(
                text("SELECT * FROM media_assets ORDER BY owner_type, sort_order")
            ).mappings()
        )


def test_revision_is_the_single_head_on_top_of_be15():
    module = _load_migration()
    assert module.revision == _REVISION
    assert module.down_revision == "20260925_be15_tz"
    script = ScriptDirectory.from_config(Config(str(_ROOT / "alembic.ini")))
    # Later revisions build on arch4; it must be in the single head's history.
    heads = script.get_heads()
    assert len(heads) == 1
    assert _REVISION in {r.revision for r in script.iterate_revisions(heads[0], "base")}


def test_upgrade_copies_rows_and_recomputes_sha256(engine, media_root, caplog):
    seeded = _seed(engine, media_root)

    with caplog.at_level(logging.WARNING, logger="alembic.runtime.migration"):
        _run(engine, "upgrade")

    rows = _assets(engine)
    by_legacy = {(r["owner_type"], r["legacy_id"]): r for r in rows}
    # 1 order (1 redacted skipped) + 2 repairs + 1 consultation.
    assert len(rows) == 4
    order = by_legacy[("order", "11111111-1111-1111-1111-111111111111")]
    assert order["id"] == "11111111-1111-1111-1111-111111111111"
    assert order["sha256"] == seeded["order_sha"]
    assert (order["width"], order["height"]) == (40, 30)
    assert order["mime"] == "image/png"
    assert order["storage_key"] == seeded["order_file"]
    assert order["caption"] == "Vorderseite"
    assert order["customer_visible"] in (0, False)
    assert order["kind"] == "photo"

    intake = by_legacy[("repair", "1")]
    assert intake["sha256"] == seeded["repair_sha"]
    assert intake["tag"] == "intake"
    assert len(intake["id"]) == 36  # fresh uuid for integer legacy ids

    outside = by_legacy[("repair", "2")]
    assert outside["sha256"] is None  # outside the root: never read
    assert outside["uploaded_by"] is None

    sketch = by_legacy[("consultation", "33333333-3333-3333-3333-333333333333")]
    assert sketch["sha256"] is None and sketch["bytes"] is None
    assert sketch["tag"] == "sketch"

    # Missing / outside files are logged by id, never fatal.
    messages = [
        r.getMessage() for r in caplog.records if r.name == "alembic.runtime.migration"
    ]
    assert sum("file missing or outside" in m for m in messages) == 2
    assert all("/etc/passwd" not in m for m in messages)


def test_copy_counts_and_is_idempotent(engine, media_root):
    _seed(engine, media_root)
    _run(engine, "upgrade")
    module = _load_migration()

    with engine.begin() as conn:
        counts = module.copy_legacy_photos(conn, media_root)

    assert counts["order_photos"] == 0
    assert counts["order_photos_skipped"] == 2  # already copied + redacted
    assert counts["repair_photos_skipped"] == 2
    assert counts["consultation_photos_skipped"] == 1
    assert len(_assets(engine)) == 4


def test_first_run_counts(engine, media_root):
    _seed(engine, media_root)
    module = _load_migration()
    _run(engine, "downgrade")  # no table yet: guarded no-op
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            from goldsmith_erp.db.migration_helpers import create_table_if_not_exists

            create_table_if_not_exists("media_assets", *module._columns())
        counts = module.copy_legacy_photos(conn, media_root)

    assert counts == {
        "missing_files": 2,
        "hashed_files": 2,
        "order_photos": 1,
        "order_photos_skipped": 1,
        "repair_photos": 2,
        "repair_photos_skipped": 0,
        "consultation_photos": 1,
        "consultation_photos_skipped": 0,
    }


def test_check_constraints_reject_unknown_values(engine, media_root):
    _run(engine, "upgrade")
    with engine.connect() as conn:
        with pytest.raises(IntegrityError):
            conn.execute(
                text(
                    "INSERT INTO media_assets (id, owner_type, owner_id, kind,"
                    " storage_key, mime) VALUES ('x', 'invoice', 1, 'photo', 'k',"
                    " 'image/png')"
                )
            )


def test_round_trip_keeps_legacy_rows(engine, media_root):
    _seed(engine, media_root)
    _run(engine, "upgrade")
    _run(engine, "downgrade")
    assert "media_assets" not in inspect(engine).get_table_names()
    with engine.connect() as conn:
        assert conn.execute(text("SELECT COUNT(*) FROM order_photos")).scalar() == 2
    _run(engine, "upgrade")
    assert len(_assets(engine)) == 4
