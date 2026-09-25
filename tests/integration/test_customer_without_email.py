"""W2-10 (DOM-02, decision D-11): customers without an email address.

Walk-in and older repair customers often have only a phone number. Email is
now optional; uniqueness on the ``email_hash`` blind index only applies when
an email is present (partial unique index). A customer needs at least one
contact channel (email, phone or mobile). Customer updates for a customer
without an address are not emailed: delivery falls back to PDF (method
``pdf_manual``), the draft stays open and no send failure is raised.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from email.message import Message

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.core.config import settings
from goldsmith_erp.db.models import (
    Customer,
    CustomerUpdate,
    CustomerUpdateKind,
    CustomerUpdateStatus,
    Order,
    OrderStatusEnum,
    UpdateDeliveryMethod,
    User,
)
from goldsmith_erp.models.customer_update import CustomerUpdateCreate
from goldsmith_erp.services import email_service as email_service_module
from goldsmith_erp.services.customer_update_service import CustomerUpdateService

pytestmark = pytest.mark.asyncio

CUSTOMERS_URL = "/api/v1/customers/"


class _CapturingSend:
    def __init__(self) -> None:
        self.calls = 0

    async def __call__(self, msg: Message, **kwargs: object) -> None:
        self.calls += 1


def _enable_smtp(monkeypatch: pytest.MonkeyPatch) -> _CapturingSend:
    monkeypatch.setattr(settings, "EMAIL_NOTIFICATIONS_ENABLED", True)
    monkeypatch.setattr(settings, "SMTP_HOST", "smtp.test.local")
    monkeypatch.setattr(settings, "SMTP_FROM", "werkstatt@test.local")
    monkeypatch.setattr(settings, "SMTP_USER", None)
    monkeypatch.setattr(settings, "SMTP_PASSWORD", None)
    capture = _CapturingSend()
    monkeypatch.setattr(email_service_module.aiosmtplib, "send", capture)
    return capture


def _payload(**overrides: object) -> dict:
    body: dict = {
        "first_name": "Erika",
        "last_name": "Walk-in",
        "customer_type": "private",
    }
    body.update(overrides)
    return body


async def test_phone_only_customer_can_be_created(
    client: AsyncClient, admin_auth_headers: dict, db_session: AsyncSession
) -> None:
    resp = await client.post(
        CUSTOMERS_URL, json=_payload(phone="+49 89 111222"), headers=admin_auth_headers
    )

    assert resp.status_code == 201, resp.text
    assert resp.json()["email"] is None
    row = (
        await db_session.execute(
            select(Customer).where(Customer.id == resp.json()["id"])
        )
    ).scalar_one()
    assert row.email is None
    assert row.email_hash is None


async def test_two_customers_without_email_do_not_collide(
    client: AsyncClient, admin_auth_headers: dict
) -> None:
    first = await client.post(
        CUSTOMERS_URL, json=_payload(phone="+49 89 1"), headers=admin_auth_headers
    )
    second = await client.post(
        CUSTOMERS_URL,
        json=_payload(first_name="Hans", mobile="+49 170 2"),
        headers=admin_auth_headers,
    )

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text


async def test_customer_without_any_contact_is_rejected(
    client: AsyncClient, admin_auth_headers: dict
) -> None:
    resp = await client.post(CUSTOMERS_URL, json=_payload(), headers=admin_auth_headers)

    assert resp.status_code == 422, resp.text
    assert "Telefon" in resp.text


async def test_duplicate_email_is_still_rejected(
    client: AsyncClient, admin_auth_headers: dict
) -> None:
    email = f"dup_{uuid.uuid4().hex[:8]}@example.com"
    first = await client.post(
        CUSTOMERS_URL, json=_payload(email=email), headers=admin_auth_headers
    )
    second = await client.post(
        CUSTOMERS_URL,
        json=_payload(first_name="Zweite", email=email),
        headers=admin_auth_headers,
    )

    assert first.status_code == 201, first.text
    assert second.status_code == 400, second.text


async def test_email_can_be_removed_when_a_phone_remains(
    client: AsyncClient, admin_auth_headers: dict, db_session: AsyncSession
) -> None:
    created = await client.post(
        CUSTOMERS_URL,
        json=_payload(email=f"rm_{uuid.uuid4().hex[:8]}@example.com", phone="+49 1"),
        headers=admin_auth_headers,
    )
    customer_id = created.json()["id"]

    resp = await client.patch(
        f"{CUSTOMERS_URL}{customer_id}",
        json={"email": None},
        headers=admin_auth_headers,
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["email"] is None
    db_session.expire_all()
    row = (
        await db_session.execute(select(Customer).where(Customer.id == customer_id))
    ).scalar_one()
    assert row.email_hash is None


async def test_removing_the_last_contact_is_rejected(
    client: AsyncClient, admin_auth_headers: dict
) -> None:
    created = await client.post(
        CUSTOMERS_URL,
        json=_payload(email=f"last_{uuid.uuid4().hex[:8]}@example.com"),
        headers=admin_auth_headers,
    )
    customer_id = created.json()["id"]

    resp = await client.patch(
        f"{CUSTOMERS_URL}{customer_id}",
        json={"email": None},
        headers=admin_auth_headers,
    )

    assert resp.status_code == 400, resp.text
    assert "Telefon" in resp.text


async def test_list_and_export_handle_missing_email(
    client: AsyncClient, admin_auth_headers: dict
) -> None:
    created = await client.post(
        CUSTOMERS_URL, json=_payload(phone="+49 30 5"), headers=admin_auth_headers
    )
    customer_id = created.json()["id"]

    listed = await client.get(CUSTOMERS_URL, headers=admin_auth_headers)
    exported = await client.get(
        f"{CUSTOMERS_URL}{customer_id}/export", headers=admin_auth_headers
    )

    assert listed.status_code == 200, listed.text
    assert exported.status_code == 200, exported.text
    assert exported.json()["customer"]["email"] is None


async def _phone_only_order(db_session: AsyncSession) -> Order:
    customer = Customer(
        first_name="Otto",
        last_name="Telefon",
        phone="+49 89 999",
        customer_type="private",
        is_active=True,
    )
    db_session.add(customer)
    await db_session.flush()
    order = Order(
        title="Reparatur Kette",
        customer_id=customer.id,
        status=OrderStatusEnum.IN_PROGRESS,
        deadline=datetime.utcnow() + timedelta(days=7),
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)
    return order


async def test_update_for_customer_without_email_falls_back_to_pdf(
    db_session: AsyncSession, admin_user: User, monkeypatch: pytest.MonkeyPatch
) -> None:
    capture = _enable_smtp(monkeypatch)
    order = await _phone_only_order(db_session)
    draft = await CustomerUpdateService.create_draft(
        db_session,
        order_id=order.id,
        repair_job_id=None,
        data=CustomerUpdateCreate(kind=CustomerUpdateKind.PROGRESS),
        user_id=admin_user.id,
    )

    result = await CustomerUpdateService.send(db_session, draft.id, admin_user.id)

    assert capture.calls == 0
    assert result.delivered is False
    assert result.method == UpdateDeliveryMethod.PDF_MANUAL
    # Not a failure: the draft stays open for the manual PDF hand-over.
    assert result.update.status == CustomerUpdateStatus.DRAFT

    delivered = await CustomerUpdateService.mark_delivered(
        db_session, draft.id, admin_user.id
    )
    assert delivered.status == CustomerUpdateStatus.SENT
    assert delivered.delivery_method == UpdateDeliveryMethod.PDF_MANUAL
    stored = (
        await db_session.execute(
            select(CustomerUpdate).where(CustomerUpdate.id == draft.id)
        )
    ).scalar_one()
    assert stored.delivery_method == UpdateDeliveryMethod.PDF_MANUAL
