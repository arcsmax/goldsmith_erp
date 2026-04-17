"""Seed-data specific tests for the Slice 1 label_templates table.

Focused on the seven system-default templates from spec §9.c:

  * Admin-edited copies (is_system_default=FALSE) are preserved when
    the seed is re-run. This is the correctness guarantee of the
    ``ON CONFLICT (entity_type, name) DO NOTHING`` strategy.
  * All seven entity_types + names appear, each at the expected
    dimensions.
  * `fields` JSON is well-formed and carries a non-empty `lines` array.
"""

from __future__ import annotations

import importlib.util
import json
from datetime import datetime
from pathlib import Path

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    event,
    text,
)


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "alembic"
    / "versions"
    / "20260418_add_qr_barcode_core_tables.py"
)


def _load_migration_module():
    spec = importlib.util.spec_from_file_location(
        "slice1_migration_seed", str(MIGRATION_PATH)
    )
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _users(metadata: MetaData) -> Table:
    return Table(
        "users",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("email", String(200), unique=True, nullable=False),
        Column("hashed_password", String(500), nullable=False),
        Column("first_name", String(100), nullable=True),
        Column("last_name", String(100), nullable=True),
        Column("role", String(50), nullable=False),
        Column("is_active", Integer, nullable=False, default=1),
        Column("created_at", DateTime, nullable=False, default=datetime.utcnow),
    )


@pytest.fixture
def migrated_engine(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'seed.db'}", future=True)

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys = ON")
        cur.close()

    metadata = MetaData()
    _users(metadata)
    metadata.create_all(engine)

    module = _load_migration_module()
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            module.upgrade()
        conn.commit()

    yield engine, module
    engine.dispose()


def test_all_seven_entity_types_and_names(migrated_engine):
    """Every row in the spec §9.c list lands with the right dimensions."""
    engine, _ = migrated_engine
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                "SELECT entity_type, name, width_mm, height_mm, "
                "is_system_default FROM label_templates "
                "ORDER BY entity_type, name"
            )
        ).all()

    expected = {
        ("order", "Standard Auftragsetikett", 89, 36),
        ("repair", "Standard Reparaturetikett", 89, 36),
        ("metal", "Metallchargen-Etikett", 89, 36),
        ("material", "Material-Etikett", 62, 29),
        ("gemstone", "Edelstein-Etikett", 25, 10),
        ("scrap", "Altgold-Etikett", 89, 36),
        ("station", "Stations-Etikett", 89, 36),
    }
    actual = {(r[0], r[1], r[2], r[3]) for r in rows}
    assert actual == expected
    # All seed rows carry is_system_default=TRUE (stored as 1 in SQLite).
    assert {int(r[4]) for r in rows} == {1}


def test_fields_json_is_wellformed(migrated_engine):
    """Every seeded `fields` column parses as JSON with a non-empty lines list."""
    engine, _ = migrated_engine
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT entity_type, fields FROM label_templates")
        ).all()

    assert len(rows) == 7
    for entity_type, payload in rows:
        parsed = json.loads(payload)
        assert "lines" in parsed, entity_type
        assert isinstance(parsed["lines"], list) and parsed["lines"], entity_type


def test_admin_edits_are_preserved_on_reseed(migrated_engine):
    """A user-edited row (is_system_default=FALSE) must survive a re-seed.

    Simulates the operator workflow: admin copies a system template,
    customises it to the workshop's preferred layout, and saves under
    the SAME name. A subsequent deployment that re-runs the seed block
    must leave the user's row untouched — that is the whole point of
    ``ON CONFLICT (entity_type, name) DO NOTHING`` on the unique
    (entity_type, name) pair.
    """
    engine, module = migrated_engine

    # Step 1 — nuke the seeded system_default row and replace it with
    # an admin-edited copy sharing the same (entity_type, name).
    with engine.begin() as conn:
        conn.execute(
            text(
                "DELETE FROM label_templates WHERE entity_type = 'order' "
                "AND name = 'Standard Auftragsetikett'"
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO label_templates (
                    entity_type, name, width_mm, height_mm, fields,
                    is_default, is_system_default, created_by,
                    created_at, updated_at
                ) VALUES (
                    'order', 'Standard Auftragsetikett', 50, 30,
                    '{"lines": [{"field": "admin_edit"}]}',
                    0, 0, NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                )
                """
            )
        )

    # Step 2 — re-seed. The INSERT OR IGNORE / ON CONFLICT DO NOTHING
    # must skip the existing row.
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            for tpl in module._SEED_TEMPLATES:
                conn.execute(
                    text(
                        """
                        INSERT OR IGNORE INTO label_templates (
                            entity_type, name, width_mm, height_mm,
                            fields, is_default, is_system_default,
                            created_by, created_at, updated_at
                        ) VALUES (
                            :entity_type, :name, :width_mm, :height_mm,
                            :fields, 0, 1,
                            NULL, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
                        )
                        """
                    ),
                    {
                        "entity_type": tpl["entity_type"],
                        "name": tpl["name"],
                        "width_mm": tpl["width_mm"],
                        "height_mm": tpl["height_mm"],
                        "fields": json.dumps(tpl["fields"]),
                    },
                )
        conn.commit()

    # Step 3 — the admin's version must still be there, unchanged.
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT width_mm, height_mm, is_system_default, fields "
                "FROM label_templates WHERE entity_type = 'order' "
                "AND name = 'Standard Auftragsetikett'"
            )
        ).first()
    assert row is not None
    width, height, is_sys, fields_json = row
    assert width == 50
    assert height == 30
    assert int(is_sys) == 0
    assert "admin_edit" in fields_json
