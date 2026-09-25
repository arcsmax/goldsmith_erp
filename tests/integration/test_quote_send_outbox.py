# tests/integration/test_quote_send_outbox.py
"""
Quote "Versenden" in OUTBOX_MODE=worker (ARCH-04, ADR-2026-09-25-outbox).

- the request sends no mail; the quote is SENT and one outbox row exists
- one worker run emails the PDF exactly once and marks the record EMAIL
- a dead-lettered mail reverts the quote to DRAFT and marks SEND_FAILED
"""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.core.config import settings
from goldsmith_erp.db.models import (
    Customer,
    CustomerUpdateStatus,
    OutboxMessage,
    OutboxStatus,
    Quote,
    QuoteStatus,
    UpdateDeliveryMethod,
)
from goldsmith_erp.services.outbox_service import OutboxService
from tests.integration.conftest import TestSessionLocal
from tests.integration.test_quote_send import (
    QUOTES_URL,
    _create_quote,
    _enable_smtp,
    _install_smtp_double,
    _records_for,
)

pytestmark = pytest.mark.asyncio


async def _outbox(db: AsyncSession) -> list[OutboxMessage]:
    db.expire_all()
    return list((await db.execute(select(OutboxMessage))).scalars().all())


async def test_send_queues_then_worker_emails_exactly_once(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_auth_headers: dict,
    test_customer: Customer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "OUTBOX_MODE", "worker")
    _enable_smtp(monkeypatch)
    capture = _install_smtp_double(monkeypatch)
    quote = await _create_quote(client, admin_auth_headers, test_customer.id)

    resp = await client.post(
        f"{QUOTES_URL}{quote['id']}/send", headers=admin_auth_headers
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "sent"
    assert capture.calls == 0
    (row,) = await _outbox(db_session)
    assert (row.kind, row.status) == ("quote_email", OutboxStatus.PENDING.value)

    assert await OutboxService.run_once(TestSessionLocal) == 1
    assert await OutboxService.run_once(TestSessionLocal) == 0
    assert capture.calls == 1

    records = await _records_for(db_session, quote["quote_number"])
    assert len(records) == 1
    assert records[0].delivery_method == UpdateDeliveryMethod.EMAIL
    assert records[0].sent_at is not None


async def test_dead_letter_reverts_quote_to_draft(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_auth_headers: dict,
    test_customer: Customer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "OUTBOX_MODE", "worker")
    monkeypatch.setattr(settings, "OUTBOX_MAX_ATTEMPTS", 1)
    _enable_smtp(monkeypatch)
    _install_smtp_double(monkeypatch, should_raise=True)
    quote = await _create_quote(client, admin_auth_headers, test_customer.id)

    resp = await client.post(
        f"{QUOTES_URL}{quote['id']}/send", headers=admin_auth_headers
    )
    assert resp.status_code == 200, resp.text
    await OutboxService.run_once(TestSessionLocal)

    (row,) = await _outbox(db_session)
    assert row.status == OutboxStatus.DEAD.value
    stored = (
        await db_session.execute(select(Quote).where(Quote.id == quote["id"]))
    ).scalar_one()
    assert stored.status == QuoteStatus.DRAFT
    records = await _records_for(db_session, quote["quote_number"])
    assert [r.status for r in records] == [CustomerUpdateStatus.SEND_FAILED]
