"""
Schema-level tests for models/customer_update.py.

Covers the validator matrix (reason too short, evidence too short,
photo_ids > 20 items, line_items kind literal, stripped-empty rejection)
plus a from_attributes roundtrip of CustomerUpdateRead / CostChangeRead
against the Task 1 ORM models.
"""

from datetime import datetime

import pytest
from pydantic import ValidationError

from goldsmith_erp.db.models import (
    CostChangeRequest,
    CostChangeResponseMethod,
    CostChangeStatus,
    CustomerUpdate,
    CustomerUpdateKind,
    CustomerUpdateStatus,
    UpdateDeliveryMethod,
)
from goldsmith_erp.models.customer_update import (
    CostChangeCreate,
    CostChangeLineItem,
    CostChangeRead,
    CostChangeRecordResponse,
    CustomerUpdateCreate,
    CustomerUpdateRead,
    CustomerUpdateSendResult,
    ProjectedCost,
)

# ═══════════════════════════════════════════════════════════════════════════
# CustomerUpdateCreate
# ═══════════════════════════════════════════════════════════════════════════


def test_customer_update_create_allows_omitted_subject_and_body():
    """subject/body are optional — the service prefills from template."""
    update = CustomerUpdateCreate(kind=CustomerUpdateKind.PROGRESS)
    assert update.subject is None
    assert update.body is None
    assert update.photo_ids is None


def test_customer_update_create_strips_subject_and_body():
    update = CustomerUpdateCreate(
        kind=CustomerUpdateKind.CUSTOM,
        subject="  Fortschritt  ",
        body="  Der Ring ist fertig.  ",
    )
    assert update.subject == "Fortschritt"
    assert update.body == "Der Ring ist fertig."


def test_customer_update_create_rejects_blank_subject():
    """Stripped-empty rejection: whitespace-only override is ambiguous with
    'omitted' (which triggers template prefill) — must raise, not silently
    become None."""
    with pytest.raises(ValidationError):
        CustomerUpdateCreate(kind=CustomerUpdateKind.PROGRESS, subject="   ")


def test_customer_update_create_rejects_blank_body():
    with pytest.raises(ValidationError):
        CustomerUpdateCreate(kind=CustomerUpdateKind.PROGRESS, body="   ")


def test_customer_update_create_rejects_more_than_20_photo_ids():
    with pytest.raises(ValidationError):
        CustomerUpdateCreate(
            kind=CustomerUpdateKind.PROGRESS,
            photo_ids=[f"photo-{i}" for i in range(21)],
        )


def test_customer_update_create_allows_exactly_20_photo_ids():
    update = CustomerUpdateCreate(
        kind=CustomerUpdateKind.PROGRESS,
        photo_ids=[f"photo-{i}" for i in range(20)],
    )
    assert len(update.photo_ids) == 20


def test_customer_update_create_has_no_target_fields():
    """Contract: order_id/repair_job_id are path-supplied (Task 5), never
    part of the request body — so this schema must not accept them as
    validated fields at all."""
    assert "order_id" not in CustomerUpdateCreate.model_fields
    assert "repair_job_id" not in CustomerUpdateCreate.model_fields


# ═══════════════════════════════════════════════════════════════════════════
# CustomerUpdateRead — from_attributes roundtrip vs the ORM model
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_customer_update_read_roundtrip_from_orm(
    db_session, sample_order, sample_user
):
    update = CustomerUpdate(
        order_id=sample_order.id,
        kind=CustomerUpdateKind.PROGRESS,
        subject="Fortschritt zu Ihrem Auftrag",
        body="Der Ring ist in Arbeit.",
        sent_by=sample_user.id,
    )
    db_session.add(update)
    await db_session.flush()
    await db_session.refresh(update)

    read = CustomerUpdateRead.model_validate(update)
    assert read.id == update.id
    assert read.order_id == sample_order.id
    assert read.repair_job_id is None
    assert read.kind is CustomerUpdateKind.PROGRESS
    assert read.status is CustomerUpdateStatus.DRAFT
    assert read.photo_ids == []  # NULL JSON column defaults to []
    assert read.cost_change_request_id is None
    assert read.delivery_method is None
    assert isinstance(read.created_at, datetime)


@pytest.mark.asyncio
async def test_customer_update_read_preserves_photo_ids(
    db_session, sample_order, sample_user
):
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
    await db_session.refresh(update)

    read = CustomerUpdateRead.model_validate(update)
    assert read.photo_ids == ["photo-uuid-1", "photo-uuid-2"]
    assert read.status is CustomerUpdateStatus.SENT
    assert read.delivery_method is UpdateDeliveryMethod.EMAIL


def test_customer_update_send_result_defaults_method_none():
    read_kwargs = dict(
        id=1,
        order_id=1,
        repair_job_id=None,
        kind=CustomerUpdateKind.PROGRESS,
        subject="s",
        body="b",
        cost_change_request_id=None,
        token="a" * 32,
        status=CustomerUpdateStatus.SEND_FAILED,
        sent_by=1,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    result = CustomerUpdateSendResult(
        update=CustomerUpdateRead(**read_kwargs), delivered=False
    )
    assert result.delivered is False
    assert result.method is None


# ═══════════════════════════════════════════════════════════════════════════
# CostChangeCreate / CostChangeLineItem
# ═══════════════════════════════════════════════════════════════════════════


def test_cost_change_create_requires_new_amount_gt_zero():
    with pytest.raises(ValidationError):
        CostChangeCreate(new_amount=0, reason="Materialpreis gestiegen deutlich.")
    with pytest.raises(ValidationError):
        CostChangeCreate(new_amount=-5, reason="Materialpreis gestiegen deutlich.")


def test_cost_change_create_rejects_reason_too_short():
    with pytest.raises(ValidationError, match="mindestens 10 Zeichen"):
        CostChangeCreate(new_amount=100.0, reason="zu kurz")


def test_cost_change_create_rejects_reason_blank_after_strip():
    """A reason that clears 10 raw characters via padding but not after
    stripping must still be rejected (stripped-empty / stripped-short
    rejection, not a raw-length check)."""
    with pytest.raises(ValidationError, match="mindestens 10 Zeichen"):
        CostChangeCreate(new_amount=100.0, reason="   kurz   ")


def test_cost_change_create_strips_and_accepts_valid_reason():
    change = CostChangeCreate(
        new_amount=1200.0, reason="  Zusaetzlicher Steinbesatz gewuenscht.  "
    )
    assert change.reason == "Zusaetzlicher Steinbesatz gewuenscht."


def test_cost_change_create_accepts_valid_line_items():
    change = CostChangeCreate(
        new_amount=1200.0,
        reason="Zusaetzlicher Steinbesatz vom Kunden gewuenscht.",
        line_items=[{"label": "Zusatzstein", "amount": 200.0, "kind": "add"}],
    )
    assert change.line_items[0].kind == "add"
    assert isinstance(change.line_items[0], CostChangeLineItem)


def test_cost_change_line_item_rejects_invalid_kind_literal():
    with pytest.raises(ValidationError):
        CostChangeLineItem(label="Zusatzstein", amount=200.0, kind="modify")


def test_cost_change_create_rejects_invalid_line_item_kind():
    with pytest.raises(ValidationError):
        CostChangeCreate(
            new_amount=1200.0,
            reason="Zusaetzlicher Steinbesatz vom Kunden gewuenscht.",
            line_items=[{"label": "Zusatzstein", "amount": 200.0, "kind": "invalid"}],
        )


def test_cost_change_create_has_no_order_id_field():
    """order_id is path-supplied (Task 5); original_amount is derived from
    the order's quote, not client input."""
    assert "order_id" not in CostChangeCreate.model_fields
    assert "original_amount" not in CostChangeCreate.model_fields


# ═══════════════════════════════════════════════════════════════════════════
# CostChangeRead — from_attributes roundtrip vs the ORM model
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_cost_change_read_roundtrip_from_orm(
    db_session, sample_order, sample_user
):
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
    await db_session.refresh(change)

    read = CostChangeRead.model_validate(change)
    assert read.id == change.id
    assert read.order_id == sample_order.id
    assert read.status is CostChangeStatus.DRAFT
    assert read.delta_percent == 20.0
    assert read.line_items[0].kind == "add"
    assert read.response_method is None
    assert read.responded_at is None


@pytest.mark.asyncio
async def test_cost_change_read_defaults_null_line_items_to_empty_list(
    db_session, sample_order, sample_user
):
    change = CostChangeRequest(
        order_id=sample_order.id,
        original_amount=1000.0,
        new_amount=1150.0,
        delta_percent=15.0,
        reason="Materialpreis gestiegen.",
        created_by=sample_user.id,
    )
    db_session.add(change)
    await db_session.flush()
    await db_session.refresh(change)

    read = CostChangeRead.model_validate(change)
    assert read.line_items == []


# ═══════════════════════════════════════════════════════════════════════════
# CostChangeRecordResponse
# ═══════════════════════════════════════════════════════════════════════════


def test_cost_change_record_response_rejects_evidence_too_short():
    with pytest.raises(ValidationError, match="mindestens 5 Zeichen"):
        CostChangeRecordResponse(
            status="approved",
            response_method=CostChangeResponseMethod.EMAIL_REPLY,
            response_evidence="ok",
        )


def test_cost_change_record_response_rejects_evidence_blank_after_strip():
    with pytest.raises(ValidationError, match="mindestens 5 Zeichen"):
        CostChangeRecordResponse(
            status="approved",
            response_method=CostChangeResponseMethod.PHONE,
            response_evidence="     ",
        )


def test_cost_change_record_response_accepts_valid_payload():
    result = CostChangeRecordResponse(
        status="declined",
        response_method=CostChangeResponseMethod.IN_PERSON,
        response_evidence="  Kundin hat vor Ort abgelehnt.  ",
    )
    assert result.response_evidence == "Kundin hat vor Ort abgelehnt."
    assert result.status == "declined"


def test_cost_change_record_response_rejects_invalid_status_literal():
    with pytest.raises(ValidationError):
        CostChangeRecordResponse(
            status="pending",
            response_method=CostChangeResponseMethod.EMAIL_REPLY,
            response_evidence="Ausreichend langer Text.",
        )


# ═══════════════════════════════════════════════════════════════════════════
# ProjectedCost
# ═══════════════════════════════════════════════════════════════════════════


def test_projected_cost_allows_no_quote():
    projected = ProjectedCost(
        material_cost=100.0,
        gemstone_cost=50.0,
        labor_minutes_billable=120.0,
        labor_cost=150.0,
        projected_total=300.0,
        over_threshold=False,
    )
    assert projected.quote_id is None
    assert projected.quote_total is None
    assert projected.delta_percent is None
    assert projected.delta_abs is None
    assert projected.over_threshold is False


def test_projected_cost_with_quote_and_over_threshold():
    projected = ProjectedCost(
        material_cost=200.0,
        gemstone_cost=100.0,
        labor_minutes_billable=240.0,
        labor_cost=300.0,
        projected_total=600.0,
        quote_id=7,
        quote_total=500.0,
        delta_percent=20.0,
        delta_abs=100.0,
        over_threshold=True,
    )
    assert projected.over_threshold is True
    assert projected.delta_percent == 20.0


def test_projected_cost_rejects_negative_material_cost():
    with pytest.raises(ValidationError):
        ProjectedCost(
            material_cost=-1.0,
            gemstone_cost=0.0,
            labor_minutes_billable=0.0,
            labor_cost=0.0,
            projected_total=0.0,
            over_threshold=False,
        )


def test_projected_cost_allows_negative_delta():
    """Deltas are signed — actuals can run under the quote."""
    projected = ProjectedCost(
        material_cost=50.0,
        gemstone_cost=0.0,
        labor_minutes_billable=60.0,
        labor_cost=75.0,
        projected_total=125.0,
        quote_id=3,
        quote_total=200.0,
        delta_percent=-37.5,
        delta_abs=-75.0,
        over_threshold=False,
    )
    assert projected.delta_percent == -37.5
    assert projected.delta_abs == -75.0
