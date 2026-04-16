"""Unit tests for `UserService.anonymize_user` (Slice 0).

Covers the 6-test minimum from
`docs/superpowers/plans/qr-barcode-workflow/V1.1-ANONYMIZE-USER-CONTRACT.md §8`
plus four additional targeted tests:

  1. test_anonymize_user_clears_pii
  2. test_anonymize_user_rewrites_registered_fks
  3. test_anonymize_user_idempotent
  4. test_gdpr_request_row_created
  5. test_last_admin_blocked
  6. test_sentinel_cannot_be_anonymized
  7. test_fk_registry_is_extensible (Slice 1 forward-compat check)
  8. test_self_erasure_rewrites_requested_by_to_sentinel
  9. test_anonymize_nonexistent_user_raises
 10. test_tracking_hmac_is_deterministic_per_user_id

The test DB is the in-memory SQLite session from `tests/conftest.py`, so
Postgres-specific FK semantics (ON DELETE RESTRICT, true hard-delete
blocking) are NOT exercised here — those live in the Slice 1 integration
tests. This file pins the service-layer contract only.
"""

from __future__ import annotations

import uuid
from datetime import datetime

import pytest
import pytest_asyncio
from sqlalchemy import select, text

from goldsmith_erp.core.security import get_password_hash
from goldsmith_erp.db.models import (
    Activity,
    GDPRRequest,
    Order,
    OrderComment,
    TimeEntry,
    User,
    UserRole,
)
from goldsmith_erp.models.user import (
    AnonymizationResult,
    LastAdminError,
    UserNotFound,
)
from goldsmith_erp.services.user_service import (
    ANONYMIZABLE_FK_TARGETS,
    SENTINEL_EMAIL,
    SENTINEL_FIRST_NAME,
    UserService,
    _compute_tracking_hmac,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers / fixtures
# ─────────────────────────────────────────────────────────────────────────────


def _uid() -> str:
    return uuid.uuid4().hex[:8]


@pytest_asyncio.fixture
async def goldsmith_user(db_session) -> User:
    """A plain GOLDSMITH user (safe to anonymise — not an admin)."""
    user = User(
        email=f"gs_{_uid()}@example.com",
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
async def second_admin(db_session) -> User:
    """A second ADMIN so the last-admin guard is not tripped accidentally."""
    user = User(
        email=f"admin2_{_uid()}@example.com",
        hashed_password=get_password_hash("Password123"),
        first_name="Second",
        last_name="Admin",
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


# ─────────────────────────────────────────────────────────────────────────────
# Tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_anonymize_user_clears_pii(db_session, goldsmith_user, second_admin):
    """PII fields are overwritten; id and role are preserved."""
    original_id = goldsmith_user.id
    original_role = goldsmith_user.role

    result = await UserService.anonymize_user(
        db_session,
        original_id,
        reason="unit-test",
        requested_by=second_admin.id,
    )

    assert isinstance(result, AnonymizationResult)
    assert result.user_id == original_id
    assert result.already_anonymized is False
    assert len(result.tracking_hmac) == 16

    # Reload and verify PII state.
    reloaded = (
        await db_session.execute(select(User).filter(User.id == original_id))
    ).scalar_one()
    assert reloaded.id == original_id
    assert reloaded.role == original_role  # preserved for audit
    assert reloaded.is_deleted is True
    assert reloaded.is_active is False
    assert reloaded.first_name == SENTINEL_FIRST_NAME
    assert reloaded.last_name is None
    assert reloaded.email == f"deleted_{original_id}@anonymized.local"
    assert reloaded.hashed_password == "!"
    assert reloaded.deleted_at is not None
    assert reloaded.anonymization_hash == result.tracking_hmac


@pytest.mark.asyncio
async def test_anonymize_user_rewrites_registered_fks(
    db_session, goldsmith_user, second_admin, sample_customer
):
    """Every FK in ANONYMIZABLE_FK_TARGETS is rewritten to the sentinel."""
    # Seed a few FK-bearing rows so we can observe rewrites.
    activity = Activity(
        name=f"Filing_{_uid()}",
        category="fabrication",
        icon="hammer",
        color="#aaaaaa",
        usage_count=0,
        is_custom=False,
        created_by=goldsmith_user.id,  # FK target
        created_at=datetime.utcnow(),
    )
    db_session.add(activity)

    order = Order(
        title="Test Order",
        description="Test",
        customer_id=sample_customer.id,
    )
    db_session.add(order)
    await db_session.flush()

    te = TimeEntry(
        id=str(uuid.uuid4()),
        order_id=order.id,
        user_id=goldsmith_user.id,  # FK target
        activity_id=activity.id,
        start_time=datetime.utcnow(),
        created_at=datetime.utcnow(),
    )
    db_session.add(te)

    oc = OrderComment(
        order_id=order.id,
        user_id=goldsmith_user.id,  # FK target (NOT NULL)
        text="Fine-tuning polish pass",
        created_at=datetime.utcnow(),
    )
    db_session.add(oc)
    await db_session.commit()

    result = await UserService.anonymize_user(
        db_session,
        goldsmith_user.id,
        reason="fk-rewrite-test",
        requested_by=second_admin.id,
    )

    # All three rows we seeded must now point at the sentinel.
    sentinel_id = result.sentinel_user_id
    assert sentinel_id != goldsmith_user.id

    # Raw `text()` UPDATEs bypass the ORM identity map, so re-select via
    # raw SQL to guarantee a fresh view of the column values.
    activity_fk = (
        await db_session.execute(
            text("SELECT created_by FROM activities WHERE id = :aid"),
            {"aid": activity.id},
        )
    ).scalar_one()
    te_fk = (
        await db_session.execute(
            text("SELECT user_id FROM time_entries WHERE id = :tid"),
            {"tid": te.id},
        )
    ).scalar_one()
    oc_fk = (
        await db_session.execute(
            text("SELECT user_id FROM order_comments WHERE id = :oid"),
            {"oid": oc.id},
        )
    ).scalar_one()

    assert activity_fk == sentinel_id
    assert te_fk == sentinel_id
    assert oc_fk == sentinel_id

    # fk_updates must report a positive count on every table we touched.
    assert result.fk_updates["activities.created_by"] >= 1
    assert result.fk_updates["time_entries.user_id"] >= 1
    assert result.fk_updates["order_comments.user_id"] >= 1


@pytest.mark.asyncio
async def test_anonymize_user_idempotent(db_session, goldsmith_user, second_admin):
    """A second call returns already_anonymized=True and no fresh FK updates."""
    first = await UserService.anonymize_user(
        db_session,
        goldsmith_user.id,
        reason="first-call",
        requested_by=second_admin.id,
    )
    assert first.already_anonymized is False

    second = await UserService.anonymize_user(
        db_session,
        goldsmith_user.id,
        reason="second-call",
        requested_by=second_admin.id,
    )

    assert second.already_anonymized is True
    assert second.fk_updates == {}
    assert second.user_id == first.user_id
    assert second.sentinel_user_id == first.sentinel_user_id
    assert second.tracking_hmac == first.tracking_hmac


@pytest.mark.asyncio
async def test_gdpr_request_row_created(db_session, goldsmith_user, second_admin):
    """A `gdpr_requests` row is written with the expected shape."""
    result = await UserService.anonymize_user(
        db_session,
        goldsmith_user.id,
        reason="audit-row-test",
        requested_by=second_admin.id,
    )

    gdpr_row = (
        await db_session.execute(
            select(GDPRRequest).filter(GDPRRequest.id == result.gdpr_request_id)
        )
    ).scalar_one()

    assert gdpr_row.request_type == "erasure_user"
    assert gdpr_row.status == "completed"
    assert gdpr_row.completed_at is not None
    assert gdpr_row.requested_by == second_admin.id
    assert result.tracking_hmac in (gdpr_row.notes or "")
    assert "audit-row-test" in (gdpr_row.notes or "")


@pytest.mark.asyncio
async def test_last_admin_blocked(db_session):
    """Anonymising the only active ADMIN raises LastAdminError."""
    lone_admin = User(
        email=f"lone_{_uid()}@example.com",
        hashed_password=get_password_hash("Password123"),
        first_name="Lone",
        last_name="Admin",
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add(lone_admin)
    await db_session.commit()
    await db_session.refresh(lone_admin)

    with pytest.raises(LastAdminError):
        await UserService.anonymize_user(
            db_session,
            lone_admin.id,
            reason="should-not-proceed",
            requested_by=lone_admin.id,
        )

    # Row must remain untouched.
    reloaded = (
        await db_session.execute(select(User).filter(User.id == lone_admin.id))
    ).scalar_one()
    assert reloaded.is_deleted is False
    assert reloaded.email == lone_admin.email


@pytest.mark.asyncio
async def test_sentinel_cannot_be_anonymized(db_session, second_admin):
    """Feeding the sentinel's own id to the service is rejected."""
    # Trigger lazy sentinel creation by calling the helper directly.
    sentinel = await UserService._get_or_create_sentinel(db_session)
    await db_session.commit()

    with pytest.raises(LastAdminError):
        await UserService.anonymize_user(
            db_session,
            sentinel.id,
            reason="tried-to-scrub-sentinel",
            requested_by=second_admin.id,
        )


@pytest.mark.asyncio
async def test_fk_registry_is_extensible(db_session, goldsmith_user, second_admin):
    """Slice 1 must be able to append new FKs to the registry.

    We simulate the Slice 1 extension in-process: patch the registry,
    invoke the service, and assert that the patched entries are queried
    (not an older frozen copy). This pins the contract that
    `ANONYMIZABLE_FK_TARGETS` is read at call-time, not captured at
    import-time.
    """
    from goldsmith_erp.services import user_service as _svc

    original_registry = list(_svc.ANONYMIZABLE_FK_TARGETS)
    try:
        # Create an ad-hoc table that pretends to be `scan_logs` from Slice 1.
        await db_session.execute(
            text(
                "CREATE TABLE mock_scan_logs ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "user_id INTEGER NOT NULL)"
            )
        )
        await db_session.execute(
            text("INSERT INTO mock_scan_logs (user_id) VALUES (:uid)"),
            {"uid": goldsmith_user.id},
        )
        await db_session.commit()

        # Slice 1 extension (simulated).
        _svc.ANONYMIZABLE_FK_TARGETS.append(("mock_scan_logs", "user_id"))

        result = await UserService.anonymize_user(
            db_session,
            goldsmith_user.id,
            reason="registry-extensibility",
            requested_by=second_admin.id,
        )

        assert "mock_scan_logs.user_id" in result.fk_updates
        assert result.fk_updates["mock_scan_logs.user_id"] == 1
    finally:
        _svc.ANONYMIZABLE_FK_TARGETS[:] = original_registry
        await db_session.execute(text("DROP TABLE IF EXISTS mock_scan_logs"))
        await db_session.commit()


@pytest.mark.asyncio
async def test_self_erasure_rewrites_requested_by_to_sentinel(
    db_session, goldsmith_user
):
    """Self-erasure: `gdpr_requests.requested_by` must point at the sentinel.

    Otherwise the GDPR row's own FK would dangle once the subject's row
    is anonymised — or worse, leak the subject id back into the audit
    trail. The service re-targets `requested_by` to the sentinel when
    the requester *is* the subject.
    """
    result = await UserService.anonymize_user(
        db_session,
        goldsmith_user.id,
        reason="self-erasure",
        requested_by=goldsmith_user.id,
    )

    gdpr_row = (
        await db_session.execute(
            select(GDPRRequest).filter(GDPRRequest.id == result.gdpr_request_id)
        )
    ).scalar_one()
    assert gdpr_row.requested_by == result.sentinel_user_id


@pytest.mark.asyncio
async def test_anonymize_nonexistent_user_raises(db_session, second_admin):
    """Unknown user id → UserNotFound (not a silent no-op)."""
    with pytest.raises(UserNotFound):
        await UserService.anonymize_user(
            db_session,
            999_999,
            reason="bogus",
            requested_by=second_admin.id,
        )


@pytest.mark.asyncio
async def test_tracking_hmac_is_deterministic_per_user_id():
    """Same user id → same HMAC; different ids → different HMACs."""
    h1 = _compute_tracking_hmac(42)
    h2 = _compute_tracking_hmac(42)
    h3 = _compute_tracking_hmac(43)
    assert h1 == h2
    assert h1 != h3
    assert len(h1) == 16
