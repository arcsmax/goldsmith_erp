# tests/unit/test_customer_update_service.py
"""
Unit tests for CustomerUpdateService (V1.2 Task 5).

Covers:
- create_draft: target existence (order/repair), exactly-one enforcement,
  photo ownership validation, repair-targeted photo rejection, template
  prefill (progress/ready_for_pickup) vs kind='custom' requiring explicit
  content.
- send: happy path (mocked aiosmtplib), send-failure path (status +
  Notification to sender + 200-shaped result), SMTP-unset degradation
  (no attempt, no notification), no-customer-email degradation (attempted,
  treated as a failure), re-sending a SENT update -> 409, cost_change-kind
  branching to EmailService.send_cost_change with the linked
  CostChangeRequest's fields.
- render_pdf: pure read (no status mutation), 404 on missing update.
- mark_delivered: sets SENT + delivery_method=pdf_manual, blocks re-mark
  of an already-SENT update (409).

aiosmtplib is mocked at the boundary test_email_customer_update.py
established: ``email_service_module.aiosmtplib.send``.
"""
import uuid

import pytest
from PIL import Image

from goldsmith_erp.core.config import settings
from goldsmith_erp.db.models import (
    CostChangeRequest,
    CostChangeStatus,
    CustomerUpdate,
    CustomerUpdateKind,
    CustomerUpdateStatus,
    Notification,
    NotificationTypeEnum,
    Order,
    OrderPhoto,
    RepairItemType,
    RepairJob,
    RepairJobStatus,
    UpdateDeliveryMethod,
)
from goldsmith_erp.models.customer_update import CustomerUpdateCreate
from goldsmith_erp.services import email_service as email_service_module
from goldsmith_erp.services.customer_update_service import (
    CostChangeKindNotAllowedError,
    CustomerUpdateNotFoundError,
    CustomerUpdateService,
    CustomerUpdateValidationError,
    InvalidUpdateStateError,
    MissingCustomerUpdateContentError,
    PhotosNotAllowedForRepairError,
)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _enable_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "EMAIL_NOTIFICATIONS_ENABLED", True)
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test.local")
    monkeypatch.setattr(settings, "SMTP_FROM", "werkstatt@test.local")
    monkeypatch.setattr(settings, "SMTP_USER", None)
    monkeypatch.setattr(settings, "SMTP_PASSWORD", None)


class _CapturingSend:
    def __init__(self, should_raise: bool = False) -> None:
        self.should_raise = should_raise
        self.sent_messages: list = []

    async def __call__(self, msg, **kwargs):
        if self.should_raise:
            raise ConnectionRefusedError("SMTP unreachable (test double)")
        self.sent_messages.append(msg)
        return None


async def _make_order_photo(db_session, tmp_path, order: Order, user) -> OrderPhoto:
    photo_dir = tmp_path / str(order.id)
    photo_dir.mkdir(parents=True, exist_ok=True)
    photo_path = photo_dir / f"{uuid.uuid4().hex}.jpg"
    Image.new("RGB", (200, 100), color=(10, 20, 30)).save(photo_path, format="JPEG")

    photo = OrderPhoto(
        id=str(uuid.uuid4()),
        order_id=order.id,
        file_path=str(photo_path),
        taken_by=user.id,
    )
    db_session.add(photo)
    await db_session.commit()
    await db_session.refresh(photo)
    return photo


async def _make_repair_job(db_session, sample_customer) -> RepairJob:
    repair = RepairJob(
        repair_number=f"REP-TEST-{uuid.uuid4().hex[:8]}",
        bag_number=f"TU-TEST-{uuid.uuid4().hex[:8]}",
        customer_id=sample_customer.id,
        item_description="Goldring, Stein lose",
        item_type=RepairItemType.RING,
        status=RepairJobStatus.RECEIVED,
    )
    db_session.add(repair)
    await db_session.commit()
    await db_session.refresh(repair)
    return repair


# ---------------------------------------------------------------------------
# create_draft
# ---------------------------------------------------------------------------


class TestCreateDraft:
    async def test_raises_when_order_not_found(self, db_session):
        with pytest.raises(ValueError, match="nicht gefunden"):
            await CustomerUpdateService.create_draft(
                db_session,
                order_id=999_999,
                repair_job_id=None,
                data=CustomerUpdateCreate(kind=CustomerUpdateKind.PROGRESS),
                user_id=1,
            )

    async def test_raises_when_both_targets_set(self, db_session, sample_order):
        with pytest.raises(ValueError, match="Exakt eines"):
            await CustomerUpdateService.create_draft(
                db_session,
                order_id=sample_order.id,
                repair_job_id=1,
                data=CustomerUpdateCreate(kind=CustomerUpdateKind.PROGRESS),
                user_id=1,
            )

    async def test_raises_when_neither_target_set(self, db_session):
        with pytest.raises(ValueError, match="Exakt eines"):
            await CustomerUpdateService.create_draft(
                db_session,
                order_id=None,
                repair_job_id=None,
                data=CustomerUpdateCreate(kind=CustomerUpdateKind.PROGRESS),
                user_id=1,
            )

    async def test_prefills_subject_and_body_for_progress_kind(
        self, db_session, sample_order, sample_user
    ):
        update = await CustomerUpdateService.create_draft(
            db_session,
            order_id=sample_order.id,
            repair_job_id=None,
            data=CustomerUpdateCreate(kind=CustomerUpdateKind.PROGRESS),
            user_id=sample_user.id,
        )
        assert update.subject
        assert update.body
        assert update.status == CustomerUpdateStatus.DRAFT
        assert update.sent_by == sample_user.id
        assert update.token and len(update.token) == 32

    async def test_prefills_subject_and_body_for_ready_for_pickup_kind(
        self, db_session, sample_order, sample_user
    ):
        update = await CustomerUpdateService.create_draft(
            db_session,
            order_id=sample_order.id,
            repair_job_id=None,
            data=CustomerUpdateCreate(kind=CustomerUpdateKind.READY_FOR_PICKUP),
            user_id=sample_user.id,
        )
        assert (
            "abholung" in update.subject.lower()
            or "abholbereit" in update.subject.lower()
        )
        assert update.body

    async def test_cost_change_kind_is_rejected_on_generic_endpoint(
        self, db_session, sample_order, sample_user
    ):
        """Fix round 1: kind=cost_change updates are only created
        internally by CostChangeService.send() — the generic create path
        must reject them with the typed validation error (422)."""
        with pytest.raises(CostChangeKindNotAllowedError):
            await CustomerUpdateService.create_draft(
                db_session,
                order_id=sample_order.id,
                repair_job_id=None,
                data=CustomerUpdateCreate(
                    kind=CustomerUpdateKind.COST_CHANGE,
                    subject="Handgebaute Kostenaenderung",
                    body="Sollte nie akzeptiert werden.",
                ),
                user_id=sample_user.id,
            )

    async def test_custom_kind_requires_explicit_subject_and_body(
        self, db_session, sample_order, sample_user
    ):
        with pytest.raises(MissingCustomerUpdateContentError):
            await CustomerUpdateService.create_draft(
                db_session,
                order_id=sample_order.id,
                repair_job_id=None,
                data=CustomerUpdateCreate(kind=CustomerUpdateKind.CUSTOM),
                user_id=sample_user.id,
            )

    async def test_custom_kind_succeeds_with_explicit_content(
        self, db_session, sample_order, sample_user
    ):
        update = await CustomerUpdateService.create_draft(
            db_session,
            order_id=sample_order.id,
            repair_job_id=None,
            data=CustomerUpdateCreate(
                kind=CustomerUpdateKind.CUSTOM,
                subject="Individuelle Nachricht",
                body="Freitext-Inhalt fuer diesen Kunden.",
            ),
            user_id=sample_user.id,
        )
        assert update.subject == "Individuelle Nachricht"
        assert update.body == "Freitext-Inhalt fuer diesen Kunden."

    async def test_explicit_subject_and_body_override_template(
        self, db_session, sample_order, sample_user
    ):
        update = await CustomerUpdateService.create_draft(
            db_session,
            order_id=sample_order.id,
            repair_job_id=None,
            data=CustomerUpdateCreate(
                kind=CustomerUpdateKind.PROGRESS,
                subject="Eigener Betreff",
                body="Eigener Text.",
            ),
            user_id=sample_user.id,
        )
        assert update.subject == "Eigener Betreff"
        assert update.body == "Eigener Text."

    async def test_accepts_valid_photo_ids_of_this_order(
        self, db_session, sample_order, sample_user, tmp_path
    ):
        photo = await _make_order_photo(db_session, tmp_path, sample_order, sample_user)

        update = await CustomerUpdateService.create_draft(
            db_session,
            order_id=sample_order.id,
            repair_job_id=None,
            data=CustomerUpdateCreate(
                kind=CustomerUpdateKind.PROGRESS, photo_ids=[photo.id]
            ),
            user_id=sample_user.id,
        )
        assert update.photo_ids == [photo.id]

    async def test_rejects_photo_ids_not_belonging_to_this_order(
        self, db_session, sample_order, sample_user, tmp_path
    ):
        with pytest.raises(CustomerUpdateValidationError):
            await CustomerUpdateService.create_draft(
                db_session,
                order_id=sample_order.id,
                repair_job_id=None,
                data=CustomerUpdateCreate(
                    kind=CustomerUpdateKind.PROGRESS, photo_ids=["not-a-real-photo-id"]
                ),
                user_id=sample_user.id,
            )

    async def test_rejects_photo_ids_belonging_to_a_different_order(
        self, db_session, sample_order, sample_user, sample_customer, tmp_path
    ):
        other_order = Order(
            title="Other order",
            customer_id=sample_customer.id,
        )
        db_session.add(other_order)
        await db_session.commit()
        await db_session.refresh(other_order)
        photo = await _make_order_photo(db_session, tmp_path, other_order, sample_user)

        with pytest.raises(CustomerUpdateValidationError):
            await CustomerUpdateService.create_draft(
                db_session,
                order_id=sample_order.id,
                repair_job_id=None,
                data=CustomerUpdateCreate(
                    kind=CustomerUpdateKind.PROGRESS, photo_ids=[photo.id]
                ),
                user_id=sample_user.id,
            )

    async def test_raises_when_repair_not_found(self, db_session):
        with pytest.raises(ValueError, match="nicht gefunden"):
            await CustomerUpdateService.create_draft(
                db_session,
                order_id=None,
                repair_job_id=999_999,
                data=CustomerUpdateCreate(kind=CustomerUpdateKind.PROGRESS),
                user_id=1,
            )

    async def test_repair_targeted_draft_succeeds_without_photos(
        self, db_session, sample_customer, sample_user
    ):
        repair = await _make_repair_job(db_session, sample_customer)

        update = await CustomerUpdateService.create_draft(
            db_session,
            order_id=None,
            repair_job_id=repair.id,
            data=CustomerUpdateCreate(kind=CustomerUpdateKind.PROGRESS),
            user_id=sample_user.id,
        )
        assert update.repair_job_id == repair.id
        assert update.order_id is None

    async def test_repair_targeted_draft_rejects_photo_ids(
        self, db_session, sample_customer, sample_user
    ):
        repair = await _make_repair_job(db_session, sample_customer)

        with pytest.raises(PhotosNotAllowedForRepairError):
            await CustomerUpdateService.create_draft(
                db_session,
                order_id=None,
                repair_job_id=repair.id,
                data=CustomerUpdateCreate(
                    kind=CustomerUpdateKind.PROGRESS, photo_ids=["whatever"]
                ),
                user_id=sample_user.id,
            )


# ---------------------------------------------------------------------------
# send
# ---------------------------------------------------------------------------


class TestSend:
    async def test_raises_not_found(self, db_session):
        with pytest.raises(CustomerUpdateNotFoundError):
            await CustomerUpdateService.send(db_session, 999_999, user_id=1)

    async def test_happy_path_marks_sent_and_delivers(
        self, db_session, sample_order, sample_user, sample_customer, monkeypatch
    ):
        _enable_smtp(monkeypatch)
        capture = _CapturingSend()
        monkeypatch.setattr(email_service_module.aiosmtplib, "send", capture)

        draft = await CustomerUpdateService.create_draft(
            db_session,
            order_id=sample_order.id,
            repair_job_id=None,
            data=CustomerUpdateCreate(kind=CustomerUpdateKind.PROGRESS),
            user_id=sample_user.id,
        )

        result = await CustomerUpdateService.send(db_session, draft.id, sample_user.id)

        assert result.delivered is True
        assert result.method == UpdateDeliveryMethod.EMAIL
        assert result.update.status == CustomerUpdateStatus.SENT
        assert len(capture.sent_messages) == 1

    async def test_smtp_unset_skips_send_without_notification(
        self, db_session, sample_order, sample_user
    ):
        draft = await CustomerUpdateService.create_draft(
            db_session,
            order_id=sample_order.id,
            repair_job_id=None,
            data=CustomerUpdateCreate(kind=CustomerUpdateKind.PROGRESS),
            user_id=sample_user.id,
        )

        result = await CustomerUpdateService.send(db_session, draft.id, sample_user.id)

        assert result.delivered is False
        assert result.method is None
        # SMTP-unset is expected PDF-only-mode behaviour, not a failure —
        # no sender notification, status left as-is (DRAFT).
        assert result.update.status == CustomerUpdateStatus.DRAFT

        from sqlalchemy import select

        notifications = (await db_session.execute(select(Notification))).scalars().all()
        assert notifications == []

    async def test_smtp_failure_marks_send_failed_and_notifies_sender(
        self, db_session, sample_order, sample_user, sample_customer, monkeypatch
    ):
        _enable_smtp(monkeypatch)
        capture = _CapturingSend(should_raise=True)
        monkeypatch.setattr(email_service_module.aiosmtplib, "send", capture)

        draft = await CustomerUpdateService.create_draft(
            db_session,
            order_id=sample_order.id,
            repair_job_id=None,
            data=CustomerUpdateCreate(kind=CustomerUpdateKind.PROGRESS),
            user_id=sample_user.id,
        )

        result = await CustomerUpdateService.send(db_session, draft.id, sample_user.id)

        assert result.delivered is False
        assert result.method is None
        assert result.update.status == CustomerUpdateStatus.SEND_FAILED

        from sqlalchemy import select

        notifications = (
            (
                await db_session.execute(
                    select(Notification).where(
                        Notification.notification_type == NotificationTypeEnum.SYSTEM,
                        Notification.user_id == sample_user.id,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(notifications) == 1

    async def test_missing_customer_email_is_treated_as_failure(
        self, db_session, sample_user, monkeypatch
    ):
        _enable_smtp(monkeypatch)
        orphan_order = Order(title="No customer order", customer_id=None)
        db_session.add(orphan_order)
        await db_session.commit()
        await db_session.refresh(orphan_order)

        draft = await CustomerUpdateService.create_draft(
            db_session,
            order_id=orphan_order.id,
            repair_job_id=None,
            data=CustomerUpdateCreate(kind=CustomerUpdateKind.PROGRESS),
            user_id=sample_user.id,
        )

        result = await CustomerUpdateService.send(db_session, draft.id, sample_user.id)

        assert result.delivered is False
        assert result.update.status == CustomerUpdateStatus.SEND_FAILED

    async def test_resending_a_sent_update_raises_invalid_state(
        self, db_session, sample_order, sample_user, monkeypatch
    ):
        _enable_smtp(monkeypatch)
        capture = _CapturingSend()
        monkeypatch.setattr(email_service_module.aiosmtplib, "send", capture)

        draft = await CustomerUpdateService.create_draft(
            db_session,
            order_id=sample_order.id,
            repair_job_id=None,
            data=CustomerUpdateCreate(kind=CustomerUpdateKind.PROGRESS),
            user_id=sample_user.id,
        )
        await CustomerUpdateService.send(db_session, draft.id, sample_user.id)

        with pytest.raises(InvalidUpdateStateError):
            await CustomerUpdateService.send(db_session, draft.id, sample_user.id)

    async def test_send_failed_update_can_be_retried(
        self, db_session, sample_order, sample_user, monkeypatch
    ):
        _enable_smtp(monkeypatch)
        failing = _CapturingSend(should_raise=True)
        monkeypatch.setattr(email_service_module.aiosmtplib, "send", failing)

        draft = await CustomerUpdateService.create_draft(
            db_session,
            order_id=sample_order.id,
            repair_job_id=None,
            data=CustomerUpdateCreate(kind=CustomerUpdateKind.PROGRESS),
            user_id=sample_user.id,
        )
        first = await CustomerUpdateService.send(db_session, draft.id, sample_user.id)
        assert first.delivered is False

        working = _CapturingSend()
        monkeypatch.setattr(email_service_module.aiosmtplib, "send", working)
        second = await CustomerUpdateService.send(db_session, draft.id, sample_user.id)

        assert second.delivered is True
        assert second.update.status == CustomerUpdateStatus.SENT

    async def test_send_forwards_only_explicit_photo_attachments(
        self, db_session, sample_order, sample_user, tmp_path, monkeypatch
    ):
        _enable_smtp(monkeypatch)
        monkeypatch.setattr(
            "goldsmith_erp.core.config.settings.PHOTO_STORAGE_PATH", str(tmp_path)
        )
        capture = _CapturingSend()
        monkeypatch.setattr(email_service_module.aiosmtplib, "send", capture)

        photo = await _make_order_photo(db_session, tmp_path, sample_order, sample_user)
        draft = await CustomerUpdateService.create_draft(
            db_session,
            order_id=sample_order.id,
            repair_job_id=None,
            data=CustomerUpdateCreate(
                kind=CustomerUpdateKind.PROGRESS, photo_ids=[photo.id]
            ),
            user_id=sample_user.id,
        )

        await CustomerUpdateService.send(db_session, draft.id, sample_user.id)

        msg = capture.sent_messages[0]
        mixed_parts = msg.get_payload()
        assert len(mixed_parts) == 2  # alternative + one photo attachment

    async def test_send_skips_photo_with_path_outside_storage_root(
        self, db_session, sample_order, sample_user, tmp_path, monkeypatch, caplog
    ):
        """Security (fix round 1, V1.1 resolve_within_root precedent):
        an OrderPhoto row whose file_path escapes the storage root (e.g.
        '/etc/passwd' injected directly into the DB) must be skipped with
        a warning — the send still proceeds with the remaining valid
        photos, no exception, and the hostile path never appears in log
        records or the response."""
        import logging

        _enable_smtp(monkeypatch)
        monkeypatch.setattr(
            "goldsmith_erp.core.config.settings.PHOTO_STORAGE_PATH", str(tmp_path)
        )
        capture = _CapturingSend()
        monkeypatch.setattr(email_service_module.aiosmtplib, "send", capture)

        good_photo = await _make_order_photo(
            db_session, tmp_path, sample_order, sample_user
        )
        evil_photo = OrderPhoto(
            id=str(uuid.uuid4()),
            order_id=sample_order.id,
            file_path="/etc/passwd",  # direct-insert hostile path
            taken_by=sample_user.id,
        )
        db_session.add(evil_photo)
        await db_session.commit()
        await db_session.refresh(evil_photo)

        draft = await CustomerUpdateService.create_draft(
            db_session,
            order_id=sample_order.id,
            repair_job_id=None,
            data=CustomerUpdateCreate(
                kind=CustomerUpdateKind.PROGRESS,
                photo_ids=[good_photo.id, evil_photo.id],
            ),
            user_id=sample_user.id,
        )

        # caplog accumulates from test start — clear the setup phase's own
        # SQLAlchemy INSERT echo (which necessarily carries the seeded
        # file_path parameter) so the assertion below scopes to what the
        # send() code path itself logs.
        caplog.clear()
        with caplog.at_level(logging.DEBUG):
            result = await CustomerUpdateService.send(
                db_session, draft.id, sample_user.id
            )

        # Delivery proceeds with the one valid photo only.
        assert result.delivered is True
        msg = capture.sent_messages[0]
        mixed_parts = msg.get_payload()
        assert len(mixed_parts) == 2  # alternative + ONE photo attachment

        # The hostile path never reaches logs or the response body.
        for record in caplog.records:
            assert "/etc/passwd" not in record.getMessage()
            assert "/etc/passwd" not in str(record.__dict__)
        assert "/etc/passwd" not in result.model_dump_json()

    async def test_cost_change_kind_uses_cost_change_template(
        self, db_session, sample_order, sample_user, monkeypatch
    ):
        _enable_smtp(monkeypatch)
        capture = _CapturingSend()
        monkeypatch.setattr(email_service_module.aiosmtplib, "send", capture)

        cost_change = CostChangeRequest(
            order_id=sample_order.id,
            original_amount=1000.0,
            new_amount=1200.0,
            delta_percent=20.0,
            reason="Zusaetzliche Fassung fuer Stein erforderlich",
            status=CostChangeStatus.SENT,
            created_by=sample_user.id,
        )
        db_session.add(cost_change)
        await db_session.commit()
        await db_session.refresh(cost_change)

        update = CustomerUpdate(
            order_id=sample_order.id,
            kind=CustomerUpdateKind.COST_CHANGE,
            subject="Kostenaenderung",
            body="Kostenaenderung Zusammenfassung",
            cost_change_request_id=cost_change.id,
            status=CustomerUpdateStatus.DRAFT,
            sent_by=sample_user.id,
        )
        db_session.add(update)
        await db_session.commit()
        await db_session.refresh(update)

        result = await CustomerUpdateService.send(db_session, update.id, sample_user.id)

        assert result.delivered is True
        html = (
            capture.sent_messages[0]
            .get_payload()[0]
            .get_payload()[1]
            .get_payload(decode=True)
            .decode("utf-8")
        )
        assert "649" in html
        assert "20,0 %" in html or "20.0" in html


# ---------------------------------------------------------------------------
# render_pdf
# ---------------------------------------------------------------------------


class TestRenderPdf:
    async def test_raises_not_found(self, db_session):
        with pytest.raises(CustomerUpdateNotFoundError):
            await CustomerUpdateService.render_pdf(db_session, 999_999)

    async def test_returns_nonempty_bytes_and_does_not_mutate_status(
        self, db_session, sample_order, sample_user
    ):
        draft = await CustomerUpdateService.create_draft(
            db_session,
            order_id=sample_order.id,
            repair_job_id=None,
            data=CustomerUpdateCreate(kind=CustomerUpdateKind.PROGRESS),
            user_id=sample_user.id,
        )

        pdf_bytes = await CustomerUpdateService.render_pdf(db_session, draft.id)

        assert isinstance(pdf_bytes, bytes)
        assert len(pdf_bytes) > 0

        from sqlalchemy import select

        refetched = (
            await db_session.execute(
                select(CustomerUpdate).where(CustomerUpdate.id == draft.id)
            )
        ).scalar_one()
        assert refetched.status == CustomerUpdateStatus.DRAFT
        assert refetched.delivery_method is None


# ---------------------------------------------------------------------------
# mark_delivered
# ---------------------------------------------------------------------------


class TestMarkDelivered:
    async def test_raises_not_found(self, db_session):
        with pytest.raises(CustomerUpdateNotFoundError):
            await CustomerUpdateService.mark_delivered(db_session, 999_999, user_id=1)

    async def test_marks_sent_with_pdf_manual_delivery_method(
        self, db_session, sample_order, sample_user
    ):
        draft = await CustomerUpdateService.create_draft(
            db_session,
            order_id=sample_order.id,
            repair_job_id=None,
            data=CustomerUpdateCreate(kind=CustomerUpdateKind.PROGRESS),
            user_id=sample_user.id,
        )

        updated = await CustomerUpdateService.mark_delivered(
            db_session, draft.id, sample_user.id
        )

        assert updated.status == CustomerUpdateStatus.SENT
        assert updated.delivery_method == UpdateDeliveryMethod.PDF_MANUAL
        assert updated.sent_at is not None

    async def test_raises_invalid_state_when_already_sent(
        self, db_session, sample_order, sample_user
    ):
        draft = await CustomerUpdateService.create_draft(
            db_session,
            order_id=sample_order.id,
            repair_job_id=None,
            data=CustomerUpdateCreate(kind=CustomerUpdateKind.PROGRESS),
            user_id=sample_user.id,
        )
        await CustomerUpdateService.mark_delivered(db_session, draft.id, sample_user.id)

        with pytest.raises(InvalidUpdateStateError):
            await CustomerUpdateService.mark_delivered(
                db_session, draft.id, sample_user.id
            )


# ---------------------------------------------------------------------------
# list_for_order
# ---------------------------------------------------------------------------


class TestListForOrder:
    async def test_returns_updates_newest_first(
        self, db_session, sample_order, sample_user
    ):
        first = await CustomerUpdateService.create_draft(
            db_session,
            order_id=sample_order.id,
            repair_job_id=None,
            data=CustomerUpdateCreate(kind=CustomerUpdateKind.PROGRESS),
            user_id=sample_user.id,
        )
        second = await CustomerUpdateService.create_draft(
            db_session,
            order_id=sample_order.id,
            repair_job_id=None,
            data=CustomerUpdateCreate(kind=CustomerUpdateKind.READY_FOR_PICKUP),
            user_id=sample_user.id,
        )

        updates = await CustomerUpdateService.list_for_order(
            db_session, sample_order.id, sample_user.id
        )

        assert [u.id for u in updates] == [second.id, first.id]

    async def test_returns_empty_list_for_order_without_updates(
        self, db_session, sample_order, sample_user
    ):
        updates = await CustomerUpdateService.list_for_order(
            db_session, sample_order.id, sample_user.id
        )
        assert updates == []
