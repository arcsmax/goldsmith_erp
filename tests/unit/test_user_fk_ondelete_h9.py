"""H9 — ON DELETE RESTRICT on the 11 pre-V1.1 user FKs.

Pins the contract that hard-deleting a user referenced by any of the
FK columns normalised in Alembic revision ``20260420_h9_restrict`` is
blocked at the DB level. Production (PostgreSQL) runs the ALTER-based
migration; tests (SQLite) get the same FK semantics via the inline
``ondelete="RESTRICT"`` clause on the ORM class, which ``create_all``
emits into the ``CREATE TABLE`` statement.

Each test inserts the minimal row needed to reference the user via the
targeted FK column, then asserts that ``DELETE FROM users WHERE id = :uid``
raises ``IntegrityError``. The foreign-key enforcement is switched on
explicitly for SQLite (off by default).
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import IntegrityError

from goldsmith_erp.db.models import Base


@pytest.fixture
def engine(tmp_path):
    """File-backed SQLite with FK enforcement + Base.metadata.create_all."""
    db_file = tmp_path / "h9_fk.db"
    eng = create_engine(f"sqlite:///{db_file}", future=True)

    @event.listens_for(eng, "connect")
    def _fk_on(dbapi_conn, _):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys = ON")
        cur.close()

    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


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


def _insert_customer(conn, cid: int, email: str) -> int:
    # ``email_hash`` (NOT NULL + UNIQUE) was added by the C1 migration.
    # Raw-SQL inserts bypass the ORM ``before_insert`` hook that
    # usually auto-populates it — compute it explicitly here.
    from goldsmith_erp.core.encryption import hmac_blind_index

    conn.execute(
        text(
            "INSERT INTO customers (id, first_name, last_name, email, "
            "email_hash, country, customer_type, tags, preferences, "
            "is_active, is_deleted, created_at) VALUES (:id, 'F', 'L', "
            ":email, :email_hash, 'Deutschland', 'private', '[]', '{}', "
            "1, 0, CURRENT_TIMESTAMP)"
        ),
        {"id": cid, "email": email, "email_hash": hmac_blind_index(email)},
    )
    return cid


def _insert_order(conn, order_id: int) -> int:
    """Minimal order row compatible with the post-Slice-2 schema."""
    conn.execute(
        text(
            "INSERT INTO orders (id, title, status, alloy, created_at, "
            "updated_at, punzierung_verified_marks, retention_class, "
            "is_deleted, scrap_percentage, hourly_rate, "
            "profit_margin_percent, vat_rate, has_scrap_gold) "
            "VALUES (:id, 'T', 'NEW', '585', CURRENT_TIMESTAMP, "
            "CURRENT_TIMESTAMP, '[]', 'indefinite_business', 0, 5.0, "
            "75.0, 40.0, 19.0, 0)"
        ),
        {"id": order_id},
    )
    return order_id


def _insert_activity(conn, aid: int, uid: int) -> int:
    conn.execute(
        text(
            "INSERT INTO activities (id, name, category, created_by) "
            "VALUES (:id, 'polieren', 'fabrication', :uid)"
        ),
        {"id": aid, "uid": uid},
    )
    return aid


# ---------------------------------------------------------------------------
# Per-FK delete-blocked tests — one per H9 target.
# ---------------------------------------------------------------------------


def test_customers_deleted_by_blocks_user_delete(engine):
    with engine.begin() as conn:
        uid = _insert_user(conn, 1001, "cd1@example.com")
        _insert_customer(conn, 5001, "cust1@example.com")
        conn.execute(
            text(
                "UPDATE customers SET deleted_by = :uid, is_deleted = 1, "
                "deleted_at = CURRENT_TIMESTAMP WHERE id = 5001"
            ),
            {"uid": uid},
        )

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": 1001})


def test_order_comments_user_id_blocks_user_delete(engine):
    with engine.begin() as conn:
        uid = _insert_user(conn, 1002, "oc@example.com")
        _insert_order(conn, 6001)
        conn.execute(
            text(
                "INSERT INTO order_comments (order_id, user_id, text, "
                "created_at, updated_at) VALUES (6001, :uid, 'hello', "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {"uid": uid},
        )

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": 1002})


def test_activities_created_by_blocks_user_delete(engine):
    with engine.begin() as conn:
        uid = _insert_user(conn, 1003, "ac@example.com")
        _insert_activity(conn, 7001, uid)

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": 1003})


def test_time_entries_user_id_blocks_user_delete(engine):
    with engine.begin() as conn:
        uid = _insert_user(conn, 1004, "te@example.com")
        _insert_order(conn, 6002)
        _insert_activity(conn, 7002, uid)
        conn.execute(
            text(
                "INSERT INTO time_entries (id, order_id, user_id, "
                "activity_id, start_time, created_at, origin, "
                "retention_class) VALUES ('te-h9-1', 6002, :uid, 7002, "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'manual', "
                "'financial_10y')"
            ),
            {"uid": uid},
        )

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": 1004})


def test_location_history_changed_by_blocks_user_delete(engine):
    with engine.begin() as conn:
        uid = _insert_user(conn, 1005, "lh@example.com")
        _insert_order(conn, 6003)
        conn.execute(
            text(
                "INSERT INTO location_history (order_id, location, "
                "timestamp, changed_by) VALUES (6003, 'Werkstatt', "
                "CURRENT_TIMESTAMP, :uid)"
            ),
            {"uid": uid},
        )

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": 1005})


def test_order_photos_taken_by_blocks_user_delete(engine):
    with engine.begin() as conn:
        uid = _insert_user(conn, 1006, "op@example.com")
        _insert_order(conn, 6004)
        conn.execute(
            text(
                "INSERT INTO order_photos (id, order_id, file_path, "
                "timestamp, taken_by) VALUES ('op-h9', 6004, "
                "'/tmp/photo.jpg', CURRENT_TIMESTAMP, :uid)"
            ),
            {"uid": uid},
        )

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": 1006})


def test_inventory_adjustments_adjusted_by_blocks_user_delete(engine):
    with engine.begin() as conn:
        uid = _insert_user(conn, 1007, "ia@example.com")
        conn.execute(
            text(
                "INSERT INTO metal_purchases (id, metal_type, weight_g, "
                "remaining_weight_g, price_total, price_per_gram, "
                "date_purchased, created_at, updated_at) VALUES "
                "(11, 'gold_14k', 10, 10, 500, 50, CURRENT_TIMESTAMP, "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO inventory_adjustments (metal_purchase_id, "
                "adjustment_type, weight_change_g, reason, "
                "adjusted_by_user_id, adjusted_at) VALUES "
                "(11, 'loss', -1.0, 'test', :uid, CURRENT_TIMESTAMP)"
            ),
            {"uid": uid},
        )

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": 1007})


def test_scrap_gold_created_by_blocks_user_delete(engine):
    with engine.begin() as conn:
        uid = _insert_user(conn, 1008, "sg@example.com")
        _insert_order(conn, 6005)
        conn.execute(
            text(
                "INSERT INTO scrap_gold (id, order_id, created_by, "
                "status, total_fine_gold_g, total_value_eur) VALUES "
                "(1, 6005, :uid, 'RECEIVED', 0, 0)"
            ),
            {"uid": uid},
        )

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": 1008})


def test_invoices_created_by_blocks_user_delete(engine):
    with engine.begin() as conn:
        uid = _insert_user(conn, 1009, "iv@example.com")
        cust = _insert_customer(conn, 5002, "ivcust@example.com")
        _insert_order(conn, 6006)
        conn.execute(
            text(
                "INSERT INTO invoices (id, invoice_number, order_id, "
                "customer_id, created_by, status, issue_date, due_date, "
                "subtotal, tax_rate, tax_amount, total, created_at, "
                "updated_at) VALUES (1, 'INV-H9', 6006, :cust, :uid, "
                "'DRAFT', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 100, "
                "19, 19, 119, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {"uid": uid, "cust": cust},
        )

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": 1009})


def test_quotes_created_by_blocks_user_delete(engine):
    with engine.begin() as conn:
        uid = _insert_user(conn, 1010, "qt@example.com")
        cust = _insert_customer(conn, 5003, "qtcust@example.com")
        conn.execute(
            text(
                "INSERT INTO quotes (id, quote_number, customer_id, "
                "created_by, status, valid_until, subtotal, tax_rate, "
                "tax_amount, total, created_at, updated_at) VALUES "
                "(1, 'QT-H9', :cust, :uid, 'DRAFT', CURRENT_TIMESTAMP, "
                "100, 19, 19, 119, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
            ),
            {"uid": uid, "cust": cust},
        )

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": 1010})


def test_gdpr_requests_requested_by_blocks_user_delete(engine):
    with engine.begin() as conn:
        uid = _insert_user(conn, 1011, "gr@example.com")
        conn.execute(
            text(
                "INSERT INTO gdpr_requests (request_type, status, "
                "requested_at, requested_by) VALUES ('erase', 'pending', "
                "CURRENT_TIMESTAMP, :uid)"
            ),
            {"uid": uid},
        )

    with pytest.raises(IntegrityError):
        with engine.begin() as conn:
            conn.execute(text("DELETE FROM users WHERE id = :id"), {"id": 1011})


# ---------------------------------------------------------------------------
# Registry coverage test — every H9 column is registered for anonymisation.
# ---------------------------------------------------------------------------


def test_all_h9_fk_targets_are_in_anonymizable_registry():
    """Every H9 FK target must appear in ANONYMIZABLE_FK_TARGETS so the
    service-layer anonymise path rewrites it."""
    from goldsmith_erp.services.user_service import ANONYMIZABLE_FK_TARGETS

    h9_targets = {
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
    }
    registry_set = set(ANONYMIZABLE_FK_TARGETS)
    missing = h9_targets - registry_set
    assert not missing, (
        f"H9 FK targets missing from ANONYMIZABLE_FK_TARGETS: {missing}"
    )
