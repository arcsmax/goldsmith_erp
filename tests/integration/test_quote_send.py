# tests/integration/test_quote_send.py
"""
DOM-11 / W2-05: "Versenden" on a Kostenvoranschlag really sends it.

- SMTP configured and the customer has an email: exactly one email with
  the quote PDF attached; status SENT; a CustomerUpdate record with
  delivery_method EMAIL and sent_at.
- SMTP not configured: no email; a PDF_MANUAL record; status SENT (the
  frontend downloads the PDF so staff can hand it over).
- SMTP configured but the send fails: status stays DRAFT, the API returns
  502 with a German message, and the failure is recorded (SEND_FAILED).

SMTP is mocked at the same boundary as the other Kundeninfo tests
(``email_service_module.aiosmtplib.send``).
"""

from email.message import Message

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.core.config import settings
from goldsmith_erp.db.models import (
    Customer,
    CustomerAuditLog,
    CustomerUpdate,
    CustomerUpdateStatus,
    Quote,
    QuoteLineType,
    QuoteStatus,
    UpdateDeliveryMethod,
)
from goldsmith_erp.services import email_service as email_service_module
from goldsmith_erp.services.customer_message_service import CustomerMessageService

pytestmark = pytest.mark.asyncio

QUOTES_URL = "/api/v1/quotes/"


class _CapturingSend:
    def __init__(self, should_raise: bool = False) -> None:
        self.should_raise = should_raise
        self.sent_messages: list[Message] = []
        self.calls = 0

    async def __call__(self, msg: Message, **kwargs: object) -> None:
        self.calls += 1
        if self.should_raise:
            raise ConnectionRefusedError("SMTP unreachable (test double)")
        self.sent_messages.append(msg)


def _enable_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "EMAIL_NOTIFICATIONS_ENABLED", True)
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test.local")
    monkeypatch.setattr(settings, "SMTP_FROM", "werkstatt@test.local")
    monkeypatch.setattr(settings, "SMTP_USER", None)
    monkeypatch.setattr(settings, "SMTP_PASSWORD", None)


def _disable_smtp(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "EMAIL_NOTIFICATIONS_ENABLED", False)
    monkeypatch.setattr(settings, "SMTP_HOST", None)


def _install_smtp_double(
    monkeypatch: pytest.MonkeyPatch, should_raise: bool = False
) -> _CapturingSend:
    capture = _CapturingSend(should_raise=should_raise)
    monkeypatch.setattr(email_service_module.aiosmtplib, "send", capture)
    return capture


async def _create_quote(client: AsyncClient, headers: dict, customer_id: int) -> dict:
    resp = await client.post(
        QUOTES_URL,
        json={
            "customer_id": customer_id,
            "tax_rate": 19.0,
            "valid_days": 14,
            "additional_line_items": [
                {
                    "line_type": QuoteLineType.LABOR.value,
                    "description": "Fertigung Ring",
                    "quantity": 2.0,
                    "unit_price": 75.0,
                }
            ],
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _records_for(db: AsyncSession, quote_number: str) -> list[CustomerUpdate]:
    db.expire_all()
    rows = (
        (
            await db.execute(
                select(CustomerUpdate)
                .where(CustomerUpdate.subject.contains(quote_number))
                .order_by(CustomerUpdate.id)
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


def _pdf_attachments(msg: Message) -> list[Message]:
    return [
        part
        for part in msg.walk()
        if (part.get_filename() or "").lower().endswith(".pdf")
    ]


async def test_send_with_smtp_emails_pdf_and_marks_sent(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_auth_headers: dict,
    test_customer: Customer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_smtp(monkeypatch)
    capture = _install_smtp_double(monkeypatch)
    quote = await _create_quote(client, admin_auth_headers, test_customer.id)

    resp = await client.post(
        f"{QUOTES_URL}{quote['id']}/send", headers=admin_auth_headers
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "sent"
    assert body["delivery_method"] == "email"
    assert body["sent_at"] is not None

    assert capture.calls == 1
    msg = capture.sent_messages[0]
    assert msg["To"] == test_customer.email
    assert quote["quote_number"] in msg["Subject"]
    assert "KV-KV-" not in msg["Subject"]
    attachments = _pdf_attachments(msg)
    assert len(attachments) == 1
    payload = attachments[0].get_payload(decode=True)
    assert isinstance(payload, bytes) and payload.startswith(b"%PDF")

    records = await _records_for(db_session, quote["quote_number"])
    assert len(records) == 1
    assert records[0].status == CustomerUpdateStatus.SENT
    assert records[0].delivery_method == UpdateDeliveryMethod.EMAIL
    assert records[0].sent_at is not None


async def test_send_without_smtp_records_pdf_manual(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_auth_headers: dict,
    test_customer: Customer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_smtp(monkeypatch)
    capture = _install_smtp_double(monkeypatch)
    quote = await _create_quote(client, admin_auth_headers, test_customer.id)

    resp = await client.post(
        f"{QUOTES_URL}{quote['id']}/send", headers=admin_auth_headers
    )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "sent"
    assert body["delivery_method"] == "pdf_manual"
    assert body["sent_at"] is not None
    assert capture.calls == 0

    records = await _records_for(db_session, quote["quote_number"])
    assert len(records) == 1
    assert records[0].status == CustomerUpdateStatus.SENT
    assert records[0].delivery_method == UpdateDeliveryMethod.PDF_MANUAL

    # GET keeps reporting how and when the quote went out.
    got = await client.get(f"{QUOTES_URL}{quote['id']}", headers=admin_auth_headers)
    assert got.json()["delivery_method"] == "pdf_manual"
    assert got.json()["sent_at"] is not None


async def test_send_with_failing_smtp_keeps_draft_and_surfaces_error(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_auth_headers: dict,
    test_customer: Customer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_smtp(monkeypatch)
    capture = _install_smtp_double(monkeypatch, should_raise=True)
    quote = await _create_quote(client, admin_auth_headers, test_customer.id)

    resp = await client.post(
        f"{QUOTES_URL}{quote['id']}/send", headers=admin_auth_headers
    )

    assert resp.status_code == 502, resp.text
    assert "E-Mail" in resp.json()["detail"]
    assert capture.calls == 1

    db_session.expire_all()
    stored = (
        await db_session.execute(select(Quote).where(Quote.id == quote["id"]))
    ).scalar_one()
    assert stored.status == QuoteStatus.DRAFT

    records = await _records_for(db_session, quote["quote_number"])
    assert [r.status for r in records] == [CustomerUpdateStatus.SEND_FAILED]

    # Staff can retry once SMTP works again.
    capture.should_raise = False
    retry = await client.post(
        f"{QUOTES_URL}{quote['id']}/send", headers=admin_auth_headers
    )
    assert retry.status_code == 200, retry.text
    assert retry.json()["status"] == "sent"
    assert retry.json()["delivery_method"] == "email"


async def test_send_with_smtp_but_customer_without_email_falls_back_to_pdf(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_auth_headers: dict,
    test_customer: Customer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _enable_smtp(monkeypatch)
    capture = _install_smtp_double(monkeypatch)
    quote = await _create_quote(client, admin_auth_headers, test_customer.id)
    monkeypatch.setattr(
        "goldsmith_erp.services.quote_delivery.customer_email",
        lambda customer: None,
    )

    resp = await client.post(
        f"{QUOTES_URL}{quote['id']}/send", headers=admin_auth_headers
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["delivery_method"] == "pdf_manual"
    assert capture.calls == 0


async def test_send_twice_is_rejected(
    client: AsyncClient,
    admin_auth_headers: dict,
    test_customer: Customer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_smtp(monkeypatch)
    quote = await _create_quote(client, admin_auth_headers, test_customer.id)
    first = await client.post(
        f"{QUOTES_URL}{quote['id']}/send", headers=admin_auth_headers
    )
    assert first.status_code == 200
    second = await client.post(
        f"{QUOTES_URL}{quote['id']}/send", headers=admin_auth_headers
    )
    assert second.status_code == 422


async def _audit_rows_for(
    db: AsyncSession, order_by: str = "id"
) -> list[CustomerAuditLog]:
    db.expire_all()
    rows = (
        (
            await db.execute(
                select(CustomerAuditLog)
                .where(CustomerAuditLog.action == "customer_message_sent")
                .order_by(getattr(CustomerAuditLog, order_by))
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


async def test_send_with_smtp_writes_quote_sent_audit_row(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_auth_headers: dict,
    test_customer: Customer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """W6B-01: quote mail is routed through CustomerMessageService (kind
    quote_sent, contractual basis, prices allowed) and produces the same
    CustomerAuditLog row every other customer-facing message produces."""
    _enable_smtp(monkeypatch)
    _install_smtp_double(monkeypatch)
    customer_id = test_customer.id
    quote = await _create_quote(client, admin_auth_headers, customer_id)

    resp = await client.post(
        f"{QUOTES_URL}{quote['id']}/send", headers=admin_auth_headers
    )
    assert resp.status_code == 200, resp.text

    rows = await _audit_rows_for(db_session)
    assert len(rows) == 1
    row = rows[0]
    assert row.customer_id == customer_id
    assert row.entity == "customer_update"
    assert row.details["message_kind"] == "quote_sent"
    assert row.details["delivery_method"] == "email"
    assert row.details["legal_basis"].startswith("Art. 6(1)(b)")
    assert quote["quote_number"] not in str(row.details)  # ids only, no body


async def test_send_without_smtp_writes_pdf_manual_audit_row(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_auth_headers: dict,
    test_customer: Customer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _disable_smtp(monkeypatch)
    _install_smtp_double(monkeypatch)
    quote = await _create_quote(client, admin_auth_headers, test_customer.id)

    resp = await client.post(
        f"{QUOTES_URL}{quote['id']}/send", headers=admin_auth_headers
    )
    assert resp.status_code == 200, resp.text

    rows = await _audit_rows_for(db_session)
    assert len(rows) == 1
    assert rows[0].details["delivery_method"] == "pdf_manual"
    assert rows[0].details["message_kind"] == "quote_sent"


async def test_send_with_failing_smtp_writes_no_audit_row(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_auth_headers: dict,
    test_customer: Customer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed attempt never reached the customer: no audit row (matches
    the generic CustomerMessageService.send_update behaviour)."""
    _enable_smtp(monkeypatch)
    _install_smtp_double(monkeypatch, should_raise=True)
    quote = await _create_quote(client, admin_auth_headers, test_customer.id)

    resp = await client.post(
        f"{QUOTES_URL}{quote['id']}/send", headers=admin_auth_headers
    )
    assert resp.status_code == 502, resp.text

    rows = await _audit_rows_for(db_session)
    assert rows == []


async def test_send_with_email_opt_out_falls_back_to_pdf_manual(
    client: AsyncClient,
    db_session: AsyncSession,
    admin_auth_headers: dict,
    admin_user,
    test_customer: Customer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Art. 21 objection ("Keine E-Mail-Updates") blocks quote mail too, the
    same as every other message kind through CustomerMessageService."""
    _enable_smtp(monkeypatch)
    capture = _install_smtp_double(monkeypatch)
    await CustomerMessageService.set_email_opt_out(
        db_session, test_customer.id, opted_out=True, user_id=admin_user.id
    )
    quote = await _create_quote(client, admin_auth_headers, test_customer.id)

    resp = await client.post(
        f"{QUOTES_URL}{quote['id']}/send", headers=admin_auth_headers
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["delivery_method"] == "pdf_manual"
    assert capture.calls == 0

    rows = await _audit_rows_for(db_session)
    assert len(rows) == 1
    assert rows[0].details["delivery_method"] == "pdf_manual"


async def test_approve_requires_response_method(
    client: AsyncClient,
    admin_auth_headers: dict,
    test_customer: Customer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DOM-11d: approval records how the customer agreed."""
    _disable_smtp(monkeypatch)
    quote = await _create_quote(client, admin_auth_headers, test_customer.id)

    missing = await client.post(
        f"{QUOTES_URL}{quote['id']}/approve", json={}, headers=admin_auth_headers
    )
    assert missing.status_code == 422

    ok = await client.post(
        f"{QUOTES_URL}{quote['id']}/approve",
        json={"response_method": "phone"},
        headers=admin_auth_headers,
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["status"] == "approved"
    assert "telefonisch" in (ok.json()["notes"] or "")
