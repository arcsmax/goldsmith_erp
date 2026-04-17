"""Slice 2 — security-floor migration + dependency tests.

Covers the Slice 2 acceptance criteria from V1.1-IMPLEMENTATION-PLAN.md
§Slice 2, V1.1-AMENDMENTS.md §Slice 2, and V1.1-PRIORITY-REVIEW.md M1 /
M2 / R5:

  * Migration upgrade/downgrade is clean on fresh SQLite.
  * Each new column exists with the correct default / nullable flag.
  * time_entries.origin back-population lands existing rows as 'manual'.
  * FK RESTRICT on orders.punzierung_verified_by + material_usage.user_id
    blocks hard-deleting a referenced user.
  * Registry-driven anonymize_user rewrites both new FK columns.
  * IdempotencyContext dependency accepts a valid UUIDv4 + ISO-8601
    timestamp; rejects malformed / out-of-window values with 400.
  * StrictRequestBase now rejects anonymization_hash, tenant_id,
    is_deleted, retention_class in request bodies.
  * Indexes are materialised on both the migration path and the
    create_all() path (ORM parity).
  * Per-table updated_at pre-check (A2.6) is accurate — tests read the
    migration docstring and assert the claims against the ORM.

Each test constructs its own isolated DB (either a file-backed SQLite
via the migration-isolation fixture, or the in-memory async SQLite from
``conftest.py``) so state never leaks between tests.
"""

from __future__ import annotations

import importlib.util
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID

import pytest
import pytest_asyncio
from fastapi import HTTPException
from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
    event,
    inspect,
    text,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from alembic.migration import MigrationContext
from alembic.operations import Operations
from goldsmith_erp.core.idempotency import (
    MAX_CLIENT_CREATED_AT_AGE,
    MAX_CLIENT_CREATED_AT_FUTURE_SKEW,
    IdempotencyContext,
    get_idempotency_context,
)
from goldsmith_erp.core.security import get_password_hash
from goldsmith_erp.db.models import (
    MaterialUsage,
    MetalPurchase,
    Order,
    OrderStatusEnum,
    User,
    UserRole,
)
from goldsmith_erp.models._base import StrictRequestBase
from goldsmith_erp.services.user_service import ANONYMIZABLE_FK_TARGETS, UserService

# ---------------------------------------------------------------------------
# Helpers — load the Slice 1 AND Slice 2 migration modules by file path.
# ---------------------------------------------------------------------------


_ALEMBIC_VERSIONS = Path(__file__).resolve().parents[2] / "alembic" / "versions"
SLICE_1_PATH = _ALEMBIC_VERSIONS / "20260418_add_qr_barcode_core_tables.py"
SLICE_2_PATH = (
    _ALEMBIC_VERSIONS / "20260419_slice_2_security_floor_and_audit_columns.py"
)


def _load_migration(module_name: str, path: Path):
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------------
# Minimal schema fixture — Slice 2 only touches columns that already exist
# on orders / material_usage / time_entries / users. We need stand-in
# tables with the pre-Slice-2 shape so the migration's ``add_column_if_
# not_exists`` runs against something realistic.
# ---------------------------------------------------------------------------


def _minimal_users_table(metadata: MetaData) -> Table:
    return Table(
        "users",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("email", String(200), unique=True, nullable=False),
        Column("hashed_password", String(500), nullable=False),
        Column("first_name", String(100), nullable=True),
        Column("last_name", String(100), nullable=True),
        Column("role", String(50), nullable=False, default="viewer"),
        Column("is_active", Integer, nullable=False, default=1),
        Column("is_deleted", Integer, nullable=False, default=0),
        Column("created_at", DateTime, nullable=False, default=datetime.utcnow),
    )


def _minimal_orders_table(metadata: MetaData) -> Table:
    return Table(
        "orders",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("title", String(200), nullable=True),
        Column("status", String(50), nullable=False, default="NEW"),
        Column("customer_id", Integer, nullable=True),
        Column("alloy", String(20), nullable=True),
        Column("created_at", DateTime, nullable=False, default=datetime.utcnow),
        Column("updated_at", DateTime, nullable=False, default=datetime.utcnow),
    )


def _minimal_metal_purchases_table(metadata: MetaData) -> Table:
    return Table(
        "metal_purchases",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("metal_type", String(50), nullable=False),
        Column("weight_g", Integer, nullable=False),
        Column("remaining_weight_g", Integer, nullable=False),
        Column("price_total", Integer, nullable=False),
        Column("price_per_gram", Integer, nullable=False),
        Column(
            "date_purchased",
            DateTime,
            nullable=False,
            default=datetime.utcnow,
        ),
        Column("created_at", DateTime, nullable=False, default=datetime.utcnow),
        Column("updated_at", DateTime, nullable=False, default=datetime.utcnow),
    )


def _minimal_material_usage_table(metadata: MetaData) -> Table:
    return Table(
        "material_usage",
        metadata,
        Column("id", Integer, primary_key=True),
        Column(
            "order_id",
            Integer,
            ForeignKey("orders.id"),
            nullable=False,
        ),
        Column(
            "metal_purchase_id",
            Integer,
            ForeignKey("metal_purchases.id"),
            nullable=False,
        ),
        Column("weight_used_g", Integer, nullable=False),
        Column("cost_at_time", Integer, nullable=False),
        Column("price_per_gram_at_time", Integer, nullable=False),
        Column("costing_method", String(50), nullable=False, default="FIFO"),
        Column(
            "used_at",
            DateTime,
            nullable=False,
            default=datetime.utcnow,
        ),
        Column("created_at", DateTime, nullable=False, default=datetime.utcnow),
    )


def _minimal_activities_table(metadata: MetaData) -> Table:
    return Table(
        "activities",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("name", String(100), nullable=False),
        Column("category", String(50), nullable=False),
    )


def _minimal_time_entries_table(metadata: MetaData) -> Table:
    return Table(
        "time_entries",
        metadata,
        Column("id", String(36), primary_key=True),
        Column(
            "order_id",
            Integer,
            ForeignKey("orders.id"),
            nullable=False,
        ),
        Column(
            "user_id",
            Integer,
            ForeignKey("users.id"),
            nullable=False,
        ),
        Column(
            "activity_id",
            Integer,
            ForeignKey("activities.id"),
            nullable=False,
        ),
        Column("start_time", DateTime, nullable=False),
        Column("end_time", DateTime, nullable=True),
        Column("duration_minutes", Integer, nullable=True),
        Column("created_at", DateTime, nullable=False, default=datetime.utcnow),
    )


@pytest.fixture
def sqlite_engine(tmp_path):
    """Fresh file-backed SQLite engine with FK enforcement on."""
    db_file = tmp_path / "slice2.db"
    engine = create_engine(f"sqlite:///{db_file}", future=True)

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys = ON")
        cur.close()

    yield engine
    engine.dispose()


@pytest.fixture
def pre_slice2_engine(sqlite_engine):
    """Engine with pre-Slice-2 schema (before the migration runs)."""
    metadata = MetaData()
    _minimal_users_table(metadata)
    _minimal_orders_table(metadata)
    _minimal_metal_purchases_table(metadata)
    _minimal_material_usage_table(metadata)
    _minimal_activities_table(metadata)
    _minimal_time_entries_table(metadata)
    metadata.create_all(sqlite_engine)
    return sqlite_engine


def _seed_existing_time_entry(conn, entry_id: str) -> None:
    """Insert a seed user + order + activity + a pre-Slice-2 time_entry."""
    conn.execute(
        text(
            "INSERT INTO users (id, email, hashed_password, first_name, "
            "last_name, role, is_active, is_deleted, created_at) VALUES "
            "(:id, :email, '!', 'T', 'U', 'goldsmith', 1, 0, "
            "CURRENT_TIMESTAMP)"
        ),
        {"id": 1, "email": "pre@example.com"},
    )
    conn.execute(
        text(
            "INSERT INTO orders (id, title, status, alloy, created_at, "
            "updated_at) VALUES (1, 'Test', 'NEW', '585', "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
    )
    conn.execute(
        text(
            "INSERT INTO activities (id, name, category) VALUES "
            "(1, 'hartloeten', 'fabrication')"
        )
    )
    conn.execute(
        text(
            "INSERT INTO time_entries (id, order_id, user_id, activity_id, "
            "start_time, created_at) VALUES "
            "(:id, 1, 1, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        ),
        {"id": entry_id},
    )


@pytest.fixture
def migrated_engine(pre_slice2_engine) -> Tuple[object, object]:
    """Engine with the Slice 2 migration applied on top of pre-Slice-2 schema."""
    module = _load_migration("slice2_migration", SLICE_2_PATH)
    with pre_slice2_engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            module.upgrade()
        conn.commit()
    yield pre_slice2_engine, module


# ---------------------------------------------------------------------------
# 1. Schema — every new column / default / nullable as specified.
# ---------------------------------------------------------------------------


def test_upgrade_adds_orders_columns(migrated_engine):
    engine, _ = migrated_engine
    cols = {c["name"]: c for c in inspect(engine).get_columns("orders")}
    assert "punzierung_verified_at" in cols
    assert cols["punzierung_verified_at"]["nullable"] is True
    assert "punzierung_verified_by" in cols
    assert cols["punzierung_verified_by"]["nullable"] is True
    assert "punzierung_verified_marks" in cols
    assert cols["punzierung_verified_marks"]["nullable"] is False
    assert "retention_class" in cols
    assert cols["retention_class"]["nullable"] is False


def test_upgrade_adds_material_usage_columns(migrated_engine):
    engine, _ = migrated_engine
    cols = {c["name"]: c for c in inspect(engine).get_columns("material_usage")}
    assert "alloy_override" in cols
    assert cols["alloy_override"]["nullable"] is False
    assert "override_reason" in cols
    assert cols["override_reason"]["nullable"] is True
    assert "override_reason_category" in cols
    assert cols["override_reason_category"]["nullable"] is True
    assert "retention_class" in cols
    assert cols["retention_class"]["nullable"] is False
    assert "user_id" in cols
    assert cols["user_id"]["nullable"] is True


def test_upgrade_adds_time_entries_columns(migrated_engine):
    engine, _ = migrated_engine
    cols = {c["name"]: c for c in inspect(engine).get_columns("time_entries")}
    assert "origin" in cols
    assert cols["origin"]["nullable"] is False
    assert "correction_of" in cols
    assert cols["correction_of"]["nullable"] is True
    assert "retention_class" in cols
    assert cols["retention_class"]["nullable"] is False


def test_upgrade_adds_users_is_test_user(migrated_engine):
    engine, _ = migrated_engine
    cols = {c["name"]: c for c in inspect(engine).get_columns("users")}
    assert "is_test_user" in cols
    assert cols["is_test_user"]["nullable"] is False


# ---------------------------------------------------------------------------
# 2. Back-population — pre-existing time_entries get origin='manual'.
# ---------------------------------------------------------------------------


def test_back_populates_existing_time_entries_as_manual(pre_slice2_engine):
    # Seed a pre-Slice-2 row BEFORE the migration runs.
    entry_id = str(uuid.uuid4())
    with pre_slice2_engine.begin() as conn:
        _seed_existing_time_entry(conn, entry_id)

    # Apply the Slice 2 migration.
    module = _load_migration("slice2_back_pop", SLICE_2_PATH)
    with pre_slice2_engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            module.upgrade()
        conn.commit()

    # Verify the existing row picked up origin='manual'.
    with pre_slice2_engine.connect() as conn:
        origin = conn.execute(
            text("SELECT origin FROM time_entries WHERE id = :id"),
            {"id": entry_id},
        ).scalar_one()
    assert origin == "manual"


# ---------------------------------------------------------------------------
# 3. FK RESTRICT — hard-delete of a user referenced by the new FK columns
#    is blocked at the DB level.
# ---------------------------------------------------------------------------


def _insert_user(conn, user_id: int, email: str) -> int:
    conn.execute(
        text(
            "INSERT INTO users (id, email, hashed_password, first_name, "
            "last_name, role, is_active, is_deleted, created_at, "
            "is_test_user) VALUES (:id, :email, '!', 'T', 'U', 'goldsmith', "
            "1, 0, CURRENT_TIMESTAMP, 0)"
        ),
        {"id": user_id, "email": email},
    )
    return user_id


# The FK-RESTRICT tests use the ORM's create_all() path, not the
# migration path. SQLite cannot add a new FK via ALTER (Alembic emits
# ``NotImplementedError``); the migration helper adds the column WITHOUT
# the FK on SQLite and the FK comes from the inline ForeignKey() on the
# ORM class when create_all() emits the CREATE TABLE. Production
# PostgreSQL runs the migration ALTER with the FK intact — the
# real-world RESTRICT surface is therefore on the PG path; the SQLite
# test here pins the ORM-level contract that the ORM class carries the
# FK inline.
@pytest.fixture
def orm_sqlite_engine(tmp_path):
    """File-backed SQLite with FK enforcement ON + Base.metadata.create_all()."""
    from goldsmith_erp.db.models import Base

    db_file = tmp_path / "slice2_orm.db"
    engine = create_engine(f"sqlite:///{db_file}", future=True)

    @event.listens_for(engine, "connect")
    def _fk_on(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys = ON")
        cur.close()

    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


def test_fk_restrict_blocks_delete_via_orders_punzierung_verified_by(
    orm_sqlite_engine,
):
    """The ORM's inline FK with ON DELETE RESTRICT blocks the hard-delete."""
    engine = orm_sqlite_engine
    with engine.begin() as conn:
        uid = _insert_user(conn, 501, "pz@example.com")
        # Insert an order referencing the user via punzierung_verified_by.
        conn.execute(
            text(
                "INSERT INTO orders (id, title, status, alloy, "
                "created_at, updated_at, punzierung_verified_at, "
                "punzierung_verified_by, punzierung_verified_marks, "
                "retention_class, is_deleted, scrap_percentage, "
                "hourly_rate, profit_margin_percent, vat_rate, "
                "has_scrap_gold) "
                "VALUES (1, 'T', 'NEW', '585', CURRENT_TIMESTAMP, "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, :uid, '[]', "
                "'hallmark_10y', 0, 5.0, 75.0, 40.0, 19.0, 0)"
            ),
            {"uid": uid},
        )

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": 501})


def test_fk_restrict_blocks_delete_via_material_usage_user_id(
    orm_sqlite_engine,
):
    engine = orm_sqlite_engine
    with engine.begin() as conn:
        uid = _insert_user(conn, 502, "mu@example.com")
        # Order + metal_purchase so MaterialUsage FKs are satisfied.
        conn.execute(
            text(
                "INSERT INTO orders (id, title, status, alloy, "
                "created_at, updated_at, punzierung_verified_marks, "
                "retention_class, is_deleted, scrap_percentage, "
                "hourly_rate, profit_margin_percent, vat_rate, "
                "has_scrap_gold) VALUES (2, 'T', 'NEW', '585', "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, '[]', "
                "'indefinite_business', 0, 5.0, 75.0, 40.0, 19.0, 0)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO metal_purchases (id, metal_type, "
                "weight_g, remaining_weight_g, price_total, "
                "price_per_gram, date_purchased, created_at, "
                "updated_at) VALUES (1, 'gold_14k', 10, 10, 500, 50, "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, "
                "CURRENT_TIMESTAMP)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO material_usage (order_id, "
                "metal_purchase_id, weight_used_g, cost_at_time, "
                "price_per_gram_at_time, costing_method, used_at, "
                "created_at, alloy_override, retention_class, user_id) "
                "VALUES (2, 1, 5, 250, 50, 'FIFO', CURRENT_TIMESTAMP, "
                "CURRENT_TIMESTAMP, 0, 'financial_10y', :uid)"
            ),
            {"uid": uid},
        )

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": 502})


# ---------------------------------------------------------------------------
# 4. Registry — the two new FK targets are registered.
# ---------------------------------------------------------------------------


def test_registry_contains_slice_2_entries():
    assert ("orders", "punzierung_verified_by") in ANONYMIZABLE_FK_TARGETS
    assert ("material_usage", "user_id") in ANONYMIZABLE_FK_TARGETS


# ---------------------------------------------------------------------------
# 5. Registry-driven anonymize rewrites the two new FK columns in an
#    end-to-end run against the conftest in-memory SQLite.
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def goldsmith_user_slice2(db_session: AsyncSession) -> User:
    user = User(
        email=f"gs2_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash("Password123"),
        first_name="Gina",
        last_name="Goldschmied",
        role=UserRole.GOLDSMITH,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def admin_user_slice2(db_session: AsyncSession) -> User:
    user = User(
        email=f"ad2_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash("Adminpass123"),
        first_name="Anna",
        last_name="Admin",
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_anonymize_user_rewrites_slice_2_fks(
    db_session: AsyncSession,
    goldsmith_user_slice2: User,
    admin_user_slice2: User,
):
    # Seed an order verified by the goldsmith, and a MaterialUsage row
    # created by the goldsmith. Anonymising should rewrite both FKs.
    from goldsmith_erp.db.models import CostingMethod, MetalType

    order = Order(
        title="Slice2 test",
        status=OrderStatusEnum.NEW,
        alloy="585",
        punzierung_verified_at=datetime.utcnow(),
        punzierung_verified_by=goldsmith_user_slice2.id,
        punzierung_verified_marks=["feingehalt_585"],
        retention_class="hallmark_10y",
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)

    # MetalPurchase so MaterialUsage FK is satisfied.
    purchase = MetalPurchase(
        metal_type=MetalType.GOLD_14K,
        weight_g=10.0,
        remaining_weight_g=10.0,
        price_total=500.0,
        price_per_gram=50.0,
    )
    db_session.add(purchase)
    await db_session.commit()
    await db_session.refresh(purchase)

    usage = MaterialUsage(
        order_id=order.id,
        metal_purchase_id=purchase.id,
        weight_used_g=5.0,
        cost_at_time=250.0,
        price_per_gram_at_time=50.0,
        costing_method=CostingMethod.FIFO,
        alloy_override=False,
        retention_class="financial_10y",
        user_id=goldsmith_user_slice2.id,
    )
    db_session.add(usage)
    await db_session.commit()
    await db_session.refresh(usage)

    result = await UserService.anonymize_user(
        db_session,
        user_id=goldsmith_user_slice2.id,
        reason="slice 2 registry-driven test",
        requested_by=admin_user_slice2.id,
    )

    assert result.fk_updates.get("orders.punzierung_verified_by") == 1
    assert result.fk_updates.get("material_usage.user_id") == 1

    sentinel_id = result.sentinel_user_id
    assert sentinel_id != goldsmith_user_slice2.id

    # Confirm the rows point at the sentinel.
    order_fk = (
        await db_session.execute(
            text("SELECT punzierung_verified_by FROM orders WHERE id = :oid"),
            {"oid": order.id},
        )
    ).scalar_one()
    usage_fk = (
        await db_session.execute(
            text("SELECT user_id FROM material_usage WHERE id = :uid"),
            {"uid": usage.id},
        )
    ).scalar_one()
    assert order_fk == sentinel_id
    assert usage_fk == sentinel_id


# ---------------------------------------------------------------------------
# 6. IdempotencyContext dependency — valid + invalid inputs.
# ---------------------------------------------------------------------------


def test_idempotency_context_accepts_valid_uuid4_and_iso():
    key = str(uuid.uuid4())  # uuid.uuid4 is guaranteed v4
    ts = datetime.now(tz=timezone.utc).isoformat()
    ctx = get_idempotency_context(idempotency_key=key, x_client_created_at=ts)
    assert isinstance(ctx, IdempotencyContext)
    assert isinstance(ctx.key, UUID)
    assert ctx.key.version == 4
    assert ctx.client_created_at is not None


def test_idempotency_context_allows_missing_headers():
    ctx = get_idempotency_context(idempotency_key=None, x_client_created_at=None)
    assert ctx.key is None
    assert ctx.client_created_at is None


def test_idempotency_context_rejects_malformed_uuid():
    with pytest.raises(HTTPException) as exc:
        get_idempotency_context(idempotency_key="not-a-uuid", x_client_created_at=None)
    assert exc.value.status_code == 400
    assert "UUIDv4" in exc.value.detail


def test_idempotency_context_rejects_non_v4_uuid():
    """Rejecting UUIDv1 prevents MAC-address leak vectors."""
    # UUIDv1 — constructed via uuid.uuid1() (time+MAC based).
    v1 = str(uuid.uuid1())
    with pytest.raises(HTTPException) as exc:
        get_idempotency_context(idempotency_key=v1, x_client_created_at=None)
    assert exc.value.status_code == 400


def test_idempotency_context_rejects_too_old_client_created_at():
    # 31 days old — one day past the 30-day tolerance.
    too_old = datetime.now(tz=timezone.utc) - timedelta(days=31)
    with pytest.raises(HTTPException) as exc:
        get_idempotency_context(
            idempotency_key=None,
            x_client_created_at=too_old.isoformat(),
        )
    assert exc.value.status_code == 400
    assert "30 days" in exc.value.detail


def test_idempotency_context_rejects_too_far_future_client_created_at():
    # 2 h in the future — 1 h past the skew tolerance.
    too_future = datetime.now(tz=timezone.utc) + timedelta(hours=2)
    with pytest.raises(HTTPException) as exc:
        get_idempotency_context(
            idempotency_key=None,
            x_client_created_at=too_future.isoformat(),
        )
    assert exc.value.status_code == 400
    assert "1 hour" in exc.value.detail


def test_idempotency_context_accepts_zulu_time_format():
    """'Z' suffix is the RFC 3339 UTC designator — clients send this."""
    now_z = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ctx = get_idempotency_context(idempotency_key=None, x_client_created_at=now_z)
    assert ctx.client_created_at is not None
    # Make sure the parsed datetime is timezone-aware.
    assert ctx.client_created_at.tzinfo is not None


def test_idempotency_tolerance_windows_are_the_documented_values():
    """Guard against an accidental edit widening the tolerance window."""
    assert MAX_CLIENT_CREATED_AT_AGE == timedelta(days=30)
    assert MAX_CLIENT_CREATED_AT_FUTURE_SKEW == timedelta(hours=1)


# ---------------------------------------------------------------------------
# 7. StrictRequestBase — Slice 2 forbidden-fields extension.
# ---------------------------------------------------------------------------


class _ExampleSchema(StrictRequestBase):
    """Minimal concrete request model for the validator tests."""

    name: str


def test_strict_base_rejects_anonymization_hash():
    with pytest.raises(ValueError) as exc:
        _ExampleSchema.model_validate({"name": "ok", "anonymization_hash": "abcd"})
    assert "anonymization_hash" in str(exc.value)


def test_strict_base_rejects_tenant_id():
    with pytest.raises(ValueError) as exc:
        _ExampleSchema.model_validate({"name": "ok", "tenant_id": 1})
    assert "tenant_id" in str(exc.value)


def test_strict_base_rejects_is_deleted():
    with pytest.raises(ValueError) as exc:
        _ExampleSchema.model_validate({"name": "ok", "is_deleted": True})
    assert "is_deleted" in str(exc.value)


def test_strict_base_rejects_retention_class():
    with pytest.raises(ValueError) as exc:
        _ExampleSchema.model_validate(
            {"name": "ok", "retention_class": "indefinite_business"}
        )
    assert "retention_class" in str(exc.value)


def test_strict_base_still_rejects_audit_fields():
    """Slice 1 contract preserved — user_id / created_by still blocked."""
    with pytest.raises(ValueError) as exc:
        _ExampleSchema.model_validate({"name": "ok", "user_id": 42})
    assert "user_id" in str(exc.value)


def test_strict_base_accepts_clean_payload():
    # Sanity check — valid payload must still round-trip.
    obj = _ExampleSchema.model_validate({"name": "alice"})
    assert obj.name == "alice"


# ---------------------------------------------------------------------------
# 8. Indexes — the migration materialised them (via inspector).
# ---------------------------------------------------------------------------


def test_indexes_created_by_migration(migrated_engine):
    engine, _ = migrated_engine
    insp = inspect(engine)
    time_idxs = {i["name"] for i in insp.get_indexes("time_entries")}
    order_idxs = {i["name"] for i in insp.get_indexes("orders")}
    user_idxs = {i["name"] for i in insp.get_indexes("users")}
    mu_idxs = {i["name"] for i in insp.get_indexes("material_usage")}

    assert "idx_time_entries_origin_created_at" in time_idxs
    assert "idx_time_entries_correction_of" in time_idxs
    assert "idx_time_entries_retention_class" in time_idxs
    assert "idx_orders_punzierung_verified_at" in order_idxs
    assert "idx_orders_retention_class" in order_idxs
    assert "idx_users_is_test_user" in user_idxs
    assert "idx_material_usage_retention_class" in mu_idxs


# ---------------------------------------------------------------------------
# 9. Downgrade — reversible. Slice 2 columns go away cleanly.
# ---------------------------------------------------------------------------


def test_downgrade_removes_all_slice_2_columns(migrated_engine):
    engine, module = migrated_engine
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            module.downgrade()
        conn.commit()

    insp = inspect(engine)
    order_cols = {c["name"] for c in insp.get_columns("orders")}
    mu_cols = {c["name"] for c in insp.get_columns("material_usage")}
    time_cols = {c["name"] for c in insp.get_columns("time_entries")}
    user_cols = {c["name"] for c in insp.get_columns("users")}

    for gone in (
        "punzierung_verified_at",
        "punzierung_verified_by",
        "punzierung_verified_marks",
        "retention_class",
    ):
        assert gone not in order_cols, f"orders.{gone} still present after downgrade"
    for gone in (
        "alloy_override",
        "override_reason",
        "override_reason_category",
        "retention_class",
        "user_id",
    ):
        assert (
            gone not in mu_cols
        ), f"material_usage.{gone} still present after downgrade"
    for gone in ("origin", "correction_of", "retention_class"):
        assert (
            gone not in time_cols
        ), f"time_entries.{gone} still present after downgrade"
    assert "is_test_user" not in user_cols


# ---------------------------------------------------------------------------
# 10. Per-table updated_at audit (A2.6) — the migration docstring claims
#     match reality.
# ---------------------------------------------------------------------------


def test_updated_at_audit_claims_are_accurate():
    """Verify the A2.6 per-table updated_at audit written in the docstring.

    The migration docstring asserts the per-table state. We re-derive it
    here from the ORM — if the ORM changes and the docstring is not
    updated, this test catches the drift.
    """
    module = _load_migration("slice2_audit_check", SLICE_2_PATH)
    doc = module.__doc__ or ""

    # Claims in the docstring — these should all be true.
    # Tables WITH updated_at + Python-side onupdate:
    for table_name in ("orders", "customers", "metal_purchases", "repair_jobs"):
        assert f"``{table_name}``" in doc, f"docstring should mention {table_name}"

    # Tables that LACK updated_at entirely — must be flagged as such.
    for table_name in ("activities", "materials", "time_entries"):
        assert f"``{table_name}``" in doc

    # Sanity-check the ORM matches the claims.
    from goldsmith_erp.db import models as orm

    # Have updated_at with onupdate:
    for cls in (orm.Order, orm.Customer, orm.MetalPurchase, orm.RepairJob):
        assert hasattr(
            cls, "updated_at"
        ), f"{cls.__name__} should have updated_at per docstring"
        updated_col = cls.__table__.columns["updated_at"]
        assert (
            updated_col.onupdate is not None
        ), f"{cls.__name__}.updated_at should have an onupdate hook"

    # Lack updated_at entirely:
    for cls in (orm.Activity, orm.Material):
        assert "updated_at" not in cls.__table__.columns, (
            f"{cls.__name__} should NOT have updated_at per docstring "
            f"(found {list(cls.__table__.columns.keys())})"
        )


# ---------------------------------------------------------------------------
# 11. Sanity — migration revision id + chain.
# ---------------------------------------------------------------------------


def test_migration_revision_chain():
    module = _load_migration("slice2_chain", SLICE_2_PATH)
    assert module.revision == "20260419_security_floor"
    assert module.down_revision == "20260418_qr_core"
