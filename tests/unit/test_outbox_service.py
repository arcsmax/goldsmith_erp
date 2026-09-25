# tests/unit/test_outbox_service.py
"""
Outbox (ARCH-04 / ARCH-05, ADR-2026-09-25-outbox).

- enqueue joins the caller's transaction (rollback removes the row)
- dedupe_key returns the existing row
- lease_due: only due rows, attempts incremented, leased rows invisible
- exponential backoff, dead-lettering after OUTBOX_MAX_ATTEMPTS + on_dead
- log lines carry ids only (no address, subject, body)
- worker mode: a customer message leaves a pending row and no SMTP call;
  one worker run sends it exactly once
- admin retry of dead rows
"""

import logging
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from goldsmith_erp.core.config import settings
from goldsmith_erp.db.models import (
    CustomerAuditLog,
    CustomerUpdate,
    CustomerUpdateStatus,
    NotificationTypeEnum,
    OutboxMessage,
    OutboxStatus,
    UpdateDeliveryMethod,
)
from goldsmith_erp.services import automated_customer_email
from goldsmith_erp.services import email_service as email_service_module
from goldsmith_erp.services import outbox_service as outbox_module
from goldsmith_erp.services.customer_message_service import (
    CustomerMessageService,
    MessageKind,
)
from goldsmith_erp.services.outbox_service import (
    OutboxHandler,
    OutboxNotRetryableError,
    OutboxService,
    backoff_seconds,
)
from tests.conftest import TestSessionLocal

SUBJECT = "Ihr Ring ist fertig"
BODY = "Sie können ihn ab morgen abholen."


class _CapturingSend:
    def __init__(self) -> None:
        self.sent_messages: list = []
        self.fail = False

    async def __call__(self, msg, **kwargs):
        if self.fail:
            raise ConnectionError("smtp down")
        self.sent_messages.append(msg)


@pytest.fixture
def smtp(monkeypatch: pytest.MonkeyPatch) -> _CapturingSend:
    monkeypatch.setattr(settings, "EMAIL_NOTIFICATIONS_ENABLED", True)
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test.local")
    monkeypatch.setattr(settings, "SMTP_FROM", "werkstatt@test.local")
    monkeypatch.setattr(settings, "SMTP_USER", None)
    monkeypatch.setattr(settings, "SMTP_PASSWORD", None)
    capture = _CapturingSend()
    monkeypatch.setattr(email_service_module.aiosmtplib, "send", capture)
    return capture


@pytest.fixture
def worker_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "OUTBOX_MODE", "worker")


@pytest.fixture
def fake_handler(monkeypatch: pytest.MonkeyPatch):
    """Register a 'test' kind whose outcome the test controls."""
    state = {"result": True, "calls": 0, "dead": 0}

    async def send(db, payload):
        state["calls"] += 1
        if isinstance(state["result"], Exception):
            raise state["result"]
        return state["result"]

    async def on_dead(db, payload):
        state["dead"] += 1

    real = outbox_module._handlers

    def handlers():
        return {**real(), "test": OutboxHandler(send=send, on_dead=on_dead)}

    monkeypatch.setattr(outbox_module, "_handlers", handlers)
    return state


async def _rows(db) -> list[OutboxMessage]:
    return list((await db.execute(select(OutboxMessage))).scalars().all())


# ---------------------------------------------------------------------------
# Enqueue
# ---------------------------------------------------------------------------


class TestEnqueue:
    async def test_rollback_removes_the_row(self, db_session):
        await OutboxService.enqueue(db_session, kind="test", payload={"id": 1})
        await db_session.rollback()
        assert await _rows(db_session) == []

    async def test_commit_keeps_a_pending_row(self, db_session):
        await OutboxService.enqueue(db_session, kind="test", payload={"id": 1})
        await db_session.commit()
        (row,) = await _rows(db_session)
        assert row.status == OutboxStatus.PENDING.value
        assert row.attempts == 0

    async def test_same_dedupe_key_returns_existing_row(self, db_session):
        first = await OutboxService.enqueue(
            db_session, kind="test", payload={}, dedupe_key="k"
        )
        second = await OutboxService.enqueue(
            db_session, kind="test", payload={}, dedupe_key="k"
        )
        await db_session.commit()
        assert first.id == second.id
        assert len(await _rows(db_session)) == 1


# ---------------------------------------------------------------------------
# Leasing, backoff, dead-lettering
# ---------------------------------------------------------------------------


class TestLeasing:
    async def test_lease_takes_due_rows_and_hides_them(self, db_session):
        due = await OutboxService.enqueue(db_session, kind="test", payload={})
        later = await OutboxService.enqueue(db_session, kind="test", payload={})
        later.next_attempt_at = datetime.utcnow() + timedelta(hours=1)
        await db_session.commit()

        ids = await OutboxService.lease_due(db_session, limit=10)
        assert ids == [due.id]
        await db_session.refresh(due)
        assert due.attempts == 1
        assert due.next_attempt_at > datetime.utcnow()
        # Leased: a second worker sees nothing.
        assert await OutboxService.lease_due(db_session, limit=10) == []

    async def test_limit_is_respected(self, db_session):
        for _ in range(3):
            await OutboxService.enqueue(db_session, kind="test", payload={})
        await db_session.commit()
        assert len(await OutboxService.lease_due(db_session, limit=2)) == 2

    def test_backoff_is_exponential_and_capped(self, monkeypatch):
        monkeypatch.setattr(settings, "OUTBOX_BACKOFF_BASE_SECONDS", 10.0)
        monkeypatch.setattr(settings, "OUTBOX_BACKOFF_MAX_SECONDS", 50.0)
        assert [backoff_seconds(n) for n in (1, 2, 3, 4)] == [10, 20, 40, 50]

    async def test_failure_schedules_retry_with_backoff(
        self, db_session, fake_handler, monkeypatch
    ):
        monkeypatch.setattr(settings, "OUTBOX_BACKOFF_BASE_SECONDS", 60.0)
        fake_handler["result"] = False
        msg = await OutboxService.enqueue(db_session, kind="test", payload={})
        await db_session.commit()

        before = datetime.utcnow()
        await OutboxService.run_once(TestSessionLocal)
        await db_session.refresh(msg)
        assert msg.status == OutboxStatus.FAILED.value
        assert msg.attempts == 1
        assert msg.last_error == "delivery_failed"
        assert msg.next_attempt_at >= before + timedelta(seconds=59)
        # Not due yet: a second run does not call the handler.
        await OutboxService.run_once(TestSessionLocal)
        assert fake_handler["calls"] == 1

    async def test_exception_is_recorded_as_class_name(self, db_session, fake_handler):
        fake_handler["result"] = RuntimeError("secret@customer.example")
        msg = await OutboxService.enqueue(db_session, kind="test", payload={})
        await db_session.commit()
        await OutboxService.run_once(TestSessionLocal)
        await db_session.refresh(msg)
        assert msg.status == OutboxStatus.FAILED.value
        assert msg.last_error == "RuntimeError"

    async def test_dead_after_max_attempts_and_on_dead_runs(
        self, db_session, fake_handler, monkeypatch
    ):
        monkeypatch.setattr(settings, "OUTBOX_MAX_ATTEMPTS", 2)
        fake_handler["result"] = False
        msg = await OutboxService.enqueue(db_session, kind="test", payload={})
        await db_session.commit()

        for _ in range(2):
            await OutboxService.run_once(TestSessionLocal)
            await db_session.refresh(msg)
            msg.next_attempt_at = datetime.utcnow() - timedelta(seconds=1)
            await db_session.commit()

        await db_session.refresh(msg)
        assert msg.status == OutboxStatus.DEAD.value
        assert msg.attempts == 2
        assert fake_handler["dead"] == 1
        # Dead rows are never leased again.
        assert await OutboxService.lease_due(db_session, limit=10) == []

    async def test_unknown_kind_is_dead_lettered(self, db_session):
        msg = await OutboxService.enqueue(db_session, kind="nope", payload={})
        await db_session.commit()
        await OutboxService.run_once(TestSessionLocal)
        await db_session.refresh(msg)
        assert msg.status == OutboxStatus.DEAD.value
        assert msg.last_error == "unknown_kind"

    async def test_admin_retry_revives_dead_row(self, db_session, fake_handler):
        msg = await OutboxService.enqueue(db_session, kind="test", payload={})
        msg.status = OutboxStatus.DEAD.value
        msg.attempts = 6
        await db_session.commit()

        await OutboxService.retry(db_session, msg.id)
        await db_session.refresh(msg)
        assert (msg.status, msg.attempts) == (OutboxStatus.PENDING.value, 0)
        await OutboxService.run_once(TestSessionLocal)
        await db_session.refresh(msg)
        assert msg.status == OutboxStatus.SENT.value

    async def test_retry_refuses_pending_or_sent(self, db_session):
        msg = await OutboxService.enqueue(db_session, kind="test", payload={})
        await db_session.commit()
        with pytest.raises(OutboxNotRetryableError):
            await OutboxService.retry(db_session, msg.id)


# ---------------------------------------------------------------------------
# Worker mode end-to-end (SMTP mocked)
# ---------------------------------------------------------------------------


class TestWorkerModeCustomerMessages:
    async def test_inline_mode_sends_immediately_and_writes_no_outbox_row(
        self, db_session, sample_order, sample_user, smtp, monkeypatch
    ):
        monkeypatch.setattr(settings, "OUTBOX_MODE", "inline")
        result = await CustomerMessageService.send_message(
            db_session,
            kind=MessageKind.STATUS_UPDATE,
            order_id=sample_order.id,
            subject=SUBJECT,
            body=BODY,
            user_id=sample_user.id,
        )
        assert result.delivered is True and result.reason is None
        assert len(smtp.sent_messages) == 1
        assert await _rows(db_session) == []

    async def test_message_is_queued_then_sent_exactly_once(
        self, db_session, sample_order, sample_user, smtp, worker_mode
    ):
        result = await CustomerMessageService.send_message(
            db_session,
            kind=MessageKind.STATUS_UPDATE,
            order_id=sample_order.id,
            subject=SUBJECT,
            body=BODY,
            user_id=sample_user.id,
        )
        assert result.reason == "queued"
        assert smtp.sent_messages == []
        (row,) = await _rows(db_session)
        assert row.status == OutboxStatus.PENDING.value
        assert row.kind == "customer_update"
        # Payload carries ids only.
        assert set(row.payload) == {"update_id", "user_id", "message_kind"}

        assert await OutboxService.run_once(TestSessionLocal) == 1
        assert await OutboxService.run_once(TestSessionLocal) == 0
        assert len(smtp.sent_messages) == 1

        await db_session.refresh(row)
        assert row.status == OutboxStatus.SENT.value
        update = (await db_session.execute(select(CustomerUpdate))).scalar_one()
        await db_session.refresh(update)
        assert update.status == CustomerUpdateStatus.SENT
        assert update.delivery_method == UpdateDeliveryMethod.EMAIL
        audits = (await db_session.execute(select(CustomerAuditLog))).scalars().all()
        assert len([a for a in audits if a.action == "customer_message_sent"]) == 1

    async def test_status_change_pickup_mail_leaves_pending_row(
        self, db_session, sample_order, sample_user, admin_user, smtp, worker_mode
    ):
        """Order completed -> pickup scan -> customer message -> outbox row."""
        sample_order.status = "completed"
        sample_order.completed_at = datetime.utcnow()
        await db_session.commit()

        sent = await automated_customer_email.send_customer_mail_once(
            db_session, sample_order, NotificationTypeEnum.PICKUP_READY
        )
        assert sent is True
        assert smtp.sent_messages == []
        (row,) = await _rows(db_session)
        assert row.status == OutboxStatus.PENDING.value

        await OutboxService.run_once(TestSessionLocal)
        await OutboxService.run_once(TestSessionLocal)
        assert len(smtp.sent_messages) == 1

    async def test_rollback_of_the_claim_leaves_no_row(
        self, db_session, sample_order, sample_user, smtp, worker_mode, monkeypatch
    ):
        async def boom(*args, **kwargs):
            raise RuntimeError("enqueue failed")

        monkeypatch.setattr(OutboxService, "enqueue", staticmethod(boom))
        with pytest.raises(RuntimeError):
            await CustomerMessageService.send_message(
                db_session,
                kind=MessageKind.STATUS_UPDATE,
                order_id=sample_order.id,
                subject=SUBJECT,
                body=BODY,
                user_id=sample_user.id,
            )
        update = (await db_session.execute(select(CustomerUpdate))).scalar_one()
        await db_session.refresh(update)
        # The claim rolled back with the failed enqueue: still claimable.
        assert update.status == CustomerUpdateStatus.DRAFT
        assert await _rows(db_session) == []

    async def test_dead_letter_marks_update_send_failed(
        self, db_session, sample_order, sample_user, smtp, worker_mode, monkeypatch
    ):
        monkeypatch.setattr(settings, "OUTBOX_MAX_ATTEMPTS", 1)
        smtp.fail = True
        await CustomerMessageService.send_message(
            db_session,
            kind=MessageKind.STATUS_UPDATE,
            order_id=sample_order.id,
            subject=SUBJECT,
            body=BODY,
            user_id=sample_user.id,
        )
        await OutboxService.run_once(TestSessionLocal)
        (row,) = await _rows(db_session)
        await db_session.refresh(row)
        assert row.status == OutboxStatus.DEAD.value
        update = (await db_session.execute(select(CustomerUpdate))).scalar_one()
        await db_session.refresh(update)
        assert update.status == CustomerUpdateStatus.SEND_FAILED

    async def test_worker_logs_carry_no_pii(
        self,
        db_session,
        sample_order,
        sample_customer,
        sample_user,
        smtp,
        worker_mode,
        caplog,
    ):
        caplog.set_level(logging.DEBUG)
        await CustomerMessageService.send_message(
            db_session,
            kind=MessageKind.STATUS_UPDATE,
            order_id=sample_order.id,
            subject=SUBJECT,
            body=BODY,
            user_id=sample_user.id,
        )
        await OutboxService.run_once(TestSessionLocal)
        outbox_records = [
            r for r in caplog.records if r.name.endswith("outbox_service")
        ]
        assert outbox_records
        forbidden = [SUBJECT, BODY, str(sample_customer.email)]
        for record in outbox_records:
            text = record.getMessage() + " " + repr(record.__dict__)
            for value in forbidden:
                assert value not in text
