"""Model-level tests for the V1.2 CustomerUpdate + CostChangeRequest tables.

Covers: model roundtrips (incl. order vs. repair-job attachment, the
CustomerUpdate <-> CostChangeRequest link, and JSON columns), enum values,
the new email-notification settings validator, and the customer-update /
cost-change permission matrix (financial + design-adjacent data — GOLDSMITH
+ ADMIN only, VIEWER gets nothing per CLAUDE.md)."""

from __future__ import annotations

from datetime import datetime

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from goldsmith_erp.core.config import Settings
from goldsmith_erp.core.permissions import ROLE_PERMISSIONS, Permission
from goldsmith_erp.db.models import (
    CostChangeRequest,
    CostChangeResponseMethod,
    CostChangeStatus,
    CustomerUpdate,
    CustomerUpdateKind,
    CustomerUpdateStatus,
    NotificationTypeEnum,
    RepairJob,
    RepairJobStatus,
    UpdateDeliveryMethod,
    UserRole,
)

# ═══════════════════════════════════════════════════════════════════════════
# Model roundtrips
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_customer_update_roundtrip_order_linked(
    db_session, sample_order, sample_user
):
    """CustomerUpdate attaches to an Order, defaults to draft, and gets an
    auto-generated unique token."""
    update = CustomerUpdate(
        order_id=sample_order.id,
        kind=CustomerUpdateKind.PROGRESS,
        subject="Fortschritt zu Ihrem Auftrag",
        body="Der Ring ist in Arbeit.",
        sent_by=sample_user.id,
    )
    db_session.add(update)
    await db_session.flush()

    row = (
        await db_session.execute(select(CustomerUpdate).filter_by(id=update.id))
    ).scalar_one()
    assert row.status is CustomerUpdateStatus.DRAFT
    assert row.kind is CustomerUpdateKind.PROGRESS
    assert row.order_id == sample_order.id
    assert row.repair_job_id is None
    assert row.token is not None and len(row.token) == 32  # uuid4().hex
    assert row.created_at is not None
    assert row.sent_at is None
    assert row.delivery_method is None


@pytest.mark.asyncio
async def test_customer_update_repair_job_linked(db_session, sample_user):
    """CustomerUpdate can attach to a RepairJob instead of an Order."""
    repair_job = RepairJob(
        repair_number="REP-2026-9001",
        bag_number="B-9001",
        item_description="Ring mit lockerem Stein",
        status=RepairJobStatus.RECEIVED,
    )
    db_session.add(repair_job)
    await db_session.flush()

    update = CustomerUpdate(
        repair_job_id=repair_job.id,
        kind=CustomerUpdateKind.READY_FOR_PICKUP,
        subject="Abholbereit",
        body="Ihre Reparatur ist fertig.",
        sent_by=sample_user.id,
    )
    db_session.add(update)
    await db_session.flush()

    row = (
        await db_session.execute(select(CustomerUpdate).filter_by(id=update.id))
    ).scalar_one()
    assert row.order_id is None
    assert row.repair_job_id == repair_job.id
    assert row.kind is CustomerUpdateKind.READY_FOR_PICKUP


@pytest.mark.asyncio
async def test_customer_update_photo_ids_and_delivery_method(
    db_session, sample_order, sample_user
):
    """photo_ids (JSON list) and delivery_method round-trip correctly."""
    update = CustomerUpdate(
        order_id=sample_order.id,
        kind=CustomerUpdateKind.CUSTOM,
        subject="Update mit Fotos",
        body="Zwei Fotos ausgewaehlt.",
        photo_ids=["photo-uuid-1", "photo-uuid-2"],
        sent_by=sample_user.id,
        status=CustomerUpdateStatus.SENT,
        sent_at=datetime.utcnow(),
        delivery_method=UpdateDeliveryMethod.EMAIL,
    )
    db_session.add(update)
    await db_session.flush()

    row = (
        await db_session.execute(select(CustomerUpdate).filter_by(id=update.id))
    ).scalar_one()
    assert row.photo_ids == ["photo-uuid-1", "photo-uuid-2"]
    assert row.delivery_method is UpdateDeliveryMethod.EMAIL
    assert row.status is CustomerUpdateStatus.SENT


@pytest.mark.asyncio
async def test_cost_change_request_roundtrip(db_session, sample_order, sample_user):
    """CostChangeRequest round-trips with computed delta and default status."""
    change = CostChangeRequest(
        order_id=sample_order.id,
        original_amount=1000.0,
        new_amount=1200.0,
        delta_percent=20.0,
        reason="Zusaetzlicher Steinbesatz vom Kunden gewuenscht.",
        line_items=[{"label": "Zusatzstein", "amount": 200.0, "kind": "add"}],
        created_by=sample_user.id,
    )
    db_session.add(change)
    await db_session.flush()

    row = (
        await db_session.execute(select(CostChangeRequest).filter_by(id=change.id))
    ).scalar_one()
    assert row.status is CostChangeStatus.DRAFT
    assert row.delta_percent == 20.0
    assert row.line_items[0]["kind"] == "add"
    assert row.response_method is None
    assert row.responded_at is None
    assert row.created_at is not None


@pytest.mark.asyncio
async def test_cost_change_request_response_recorded(
    db_session, sample_order, sample_user
):
    """Recording a response sets method/evidence/responded_at/recorded_by."""
    change = CostChangeRequest(
        order_id=sample_order.id,
        original_amount=1000.0,
        new_amount=1150.0,
        delta_percent=15.0,
        reason="Materialpreis gestiegen.",
        created_by=sample_user.id,
        status=CostChangeStatus.SENT,
    )
    db_session.add(change)
    await db_session.flush()

    change.status = CostChangeStatus.APPROVED
    change.response_method = CostChangeResponseMethod.EMAIL_REPLY
    change.response_evidence = "Kundin hat per Email zugestimmt am 2026-07-05."
    change.responded_at = datetime.utcnow()
    change.recorded_by = sample_user.id
    await db_session.flush()

    row = (
        await db_session.execute(select(CostChangeRequest).filter_by(id=change.id))
    ).scalar_one()
    assert row.status is CostChangeStatus.APPROVED
    assert row.response_method is CostChangeResponseMethod.EMAIL_REPLY
    assert row.responded_at is not None
    assert row.recorded_by == sample_user.id


@pytest.mark.asyncio
async def test_customer_update_cost_change_link(db_session, sample_order, sample_user):
    """A CustomerUpdate can reference the CostChangeRequest it announces."""
    change = CostChangeRequest(
        order_id=sample_order.id,
        original_amount=1000.0,
        new_amount=1200.0,
        delta_percent=20.0,
        reason="Zusaetzlicher Steinbesatz.",
        created_by=sample_user.id,
    )
    db_session.add(change)
    await db_session.flush()

    update = CustomerUpdate(
        order_id=sample_order.id,
        kind=CustomerUpdateKind.COST_CHANGE,
        subject="Kostenaenderung",
        body="Die Kosten haben sich geaendert.",
        cost_change_request_id=change.id,
        sent_by=sample_user.id,
    )
    db_session.add(update)
    await db_session.flush()

    row = (
        await db_session.execute(
            select(CustomerUpdate)
            .options(selectinload(CustomerUpdate.cost_change_request))
            .filter_by(id=update.id)
        )
    ).scalar_one()
    assert row.cost_change_request_id == change.id
    assert row.cost_change_request.new_amount == 1200.0


# ═══════════════════════════════════════════════════════════════════════════
# Enum values
# ═══════════════════════════════════════════════════════════════════════════


def test_customer_update_kind_values():
    assert CustomerUpdateKind.PROGRESS.value == "progress"
    assert CustomerUpdateKind.COST_CHANGE.value == "cost_change"
    assert CustomerUpdateKind.READY_FOR_PICKUP.value == "ready_for_pickup"
    assert CustomerUpdateKind.CUSTOM.value == "custom"


def test_customer_update_status_values():
    assert CustomerUpdateStatus.DRAFT.value == "draft"
    assert CustomerUpdateStatus.SENT.value == "sent"
    assert CustomerUpdateStatus.SEND_FAILED.value == "send_failed"


def test_update_delivery_method_values():
    assert UpdateDeliveryMethod.EMAIL.value == "email"
    assert UpdateDeliveryMethod.PDF_MANUAL.value == "pdf_manual"


def test_cost_change_status_values():
    assert CostChangeStatus.DRAFT.value == "draft"
    assert CostChangeStatus.SENT.value == "sent"
    assert CostChangeStatus.APPROVED.value == "approved"
    assert CostChangeStatus.DECLINED.value == "declined"
    assert CostChangeStatus.SUPERSEDED.value == "superseded"


def test_cost_change_response_method_values():
    assert CostChangeResponseMethod.EMAIL_REPLY.value == "email_reply"
    assert CostChangeResponseMethod.IN_PERSON.value == "in_person"
    assert CostChangeResponseMethod.PHONE.value == "phone"


def test_notification_type_enum_has_cost_alert():
    assert NotificationTypeEnum.COST_ALERT.value == "cost_alert"


# ═══════════════════════════════════════════════════════════════════════════
# Settings validator — email-notification / SMTP fail-loud check
# ═══════════════════════════════════════════════════════════════════════════


def _valid_settings_kwargs(**overrides) -> dict:
    """Baseline kwargs that satisfy the encryption/anonymization validators
    so only the email-notification validator under test can fail."""
    kwargs: dict = dict(
        ENCRYPTION_KEY=Fernet.generate_key().decode(),
        ANONYMIZATION_SALT="a-non-empty-test-salt-value",
    )
    kwargs.update(overrides)
    return kwargs


def test_email_notification_validator_raises_in_prod_when_smtp_missing():
    """DEBUG=False + EMAIL_NOTIFICATIONS_ENABLED=True + no SMTP_HOST/SMTP_FROM
    must fail loudly at startup (CLAUDE.md: never silent)."""
    with pytest.raises(ValueError, match="SMTP_HOST"):
        Settings(
            **_valid_settings_kwargs(
                DEBUG=False,
                EMAIL_NOTIFICATIONS_ENABLED=True,
                SMTP_HOST=None,
                SMTP_FROM=None,
            )
        )


def test_email_notification_validator_raises_when_only_smtp_host_set():
    """Both SMTP_HOST and SMTP_FROM are required — half-configured still fails."""
    with pytest.raises(ValueError, match="SMTP_HOST"):
        Settings(
            **_valid_settings_kwargs(
                DEBUG=False,
                EMAIL_NOTIFICATIONS_ENABLED=True,
                SMTP_HOST="smtp.example.com",
                SMTP_FROM=None,
            )
        )


def test_email_notification_validator_warns_not_raises_in_debug():
    """DEBUG=True must warn, not raise — local/dev PDF-only mode stays usable."""
    settings = Settings(
        **_valid_settings_kwargs(
            DEBUG=True,
            EMAIL_NOTIFICATIONS_ENABLED=True,
            SMTP_HOST=None,
            SMTP_FROM=None,
        )
    )
    assert settings.EMAIL_NOTIFICATIONS_ENABLED is True


def test_email_notification_validator_passes_with_full_smtp_config():
    """Fully configured SMTP + enabled notifications never raises, even in prod."""
    settings = Settings(
        **_valid_settings_kwargs(
            DEBUG=False,
            EMAIL_NOTIFICATIONS_ENABLED=True,
            SMTP_HOST="smtp.example.com",
            SMTP_FROM="noreply@example.com",
        )
    )
    assert settings.SMTP_HOST == "smtp.example.com"


def test_email_notification_validator_skipped_when_disabled():
    """EMAIL_NOTIFICATIONS_ENABLED=False never triggers the SMTP check, even
    in prod with no SMTP_* configured — PDF-only mode is a valid deployment."""
    settings = Settings(
        **_valid_settings_kwargs(
            DEBUG=False,
            EMAIL_NOTIFICATIONS_ENABLED=False,
            SMTP_HOST=None,
            SMTP_FROM=None,
        )
    )
    assert settings.EMAIL_NOTIFICATIONS_ENABLED is False


def test_cost_alert_threshold_defaults():
    """Default §649 thresholds match the spec (15% / EUR 150) plus the
    fallback hourly rate used by the projected-cost watcher."""
    settings = Settings(**_valid_settings_kwargs(DEBUG=True))
    assert settings.COST_ALERT_THRESHOLD_PERCENT == 15.0
    assert settings.COST_ALERT_THRESHOLD_ABS_EUR == 150.0
    assert settings.DEFAULT_HOURLY_RATE == 75.0


# ═══════════════════════════════════════════════════════════════════════════
# Permission matrix
# ═══════════════════════════════════════════════════════════════════════════


def test_goldsmith_has_customer_update_and_cost_change_permissions():
    perms = ROLE_PERMISSIONS[UserRole.GOLDSMITH]
    assert Permission.CUSTOMER_UPDATE_VIEW in perms
    assert Permission.CUSTOMER_UPDATE_SEND in perms
    assert Permission.COST_CHANGE_VIEW in perms
    assert Permission.COST_CHANGE_MANAGE in perms


def test_admin_has_customer_update_and_cost_change_permissions():
    perms = ROLE_PERMISSIONS[UserRole.ADMIN]
    assert Permission.CUSTOMER_UPDATE_VIEW in perms
    assert Permission.CUSTOMER_UPDATE_SEND in perms
    assert Permission.COST_CHANGE_VIEW in perms
    assert Permission.COST_CHANGE_MANAGE in perms


def test_viewer_has_no_customer_update_or_cost_change_permissions():
    """Financial + design-adjacent data — VIEWER gets nothing (CLAUDE.md)."""
    perms = ROLE_PERMISSIONS[UserRole.VIEWER]
    assert not any(p.value.startswith("customer_update:") for p in perms)
    assert not any(p.value.startswith("cost_change:") for p in perms)
