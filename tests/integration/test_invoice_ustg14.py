"""W2-04 (DOM-24, DOM-24b, BE-16): §14 Abs. 4 UStG invoice, workshop
settings, Storno and per-year numbering, end to end through the API.

§14 Abs. 4 UStG checklist asserted on the rendered PDF text:
  Nr. 1  seller name + address, recipient name + address
  Nr. 2  Steuernummer or USt-IdNr.
  Nr. 3  Ausstellungsdatum (Rechnungsdatum)
  Nr. 4  fortlaufende Rechnungsnummer
  Nr. 5  Menge und Art (quantity + description per line)
  Nr. 6  Zeitpunkt der Leistung (Leistungsdatum)
  Nr. 7  Entgelt nach Steuersätzen (net per rate)
  Nr. 8  Steuersatz + Steuerbetrag, or the §19 UStG note (Kleinunternehmer)
  plus the gross total.

fpdf2 embeds subset fonts, so the bytes are not greppable; the text that
reaches the page is captured by wrapping ``_GoldsmithPDF.cell`` /
``multi_cell`` (every string the renderer draws goes through them).
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import Any, List

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import (
    Customer,
    Invoice,
    InvoiceStatus,
    Order,
    OrderStatusEnum,
)
from goldsmith_erp.services import pdf_service
from goldsmith_erp.services.number_sequence_service import berlin_year

pytestmark = pytest.mark.asyncio

INVOICES_URL = "/api/v1/invoices"
SETTINGS_URL = "/api/v1/admin/workshop-settings"

SETTINGS = {
    "name": "Goldschmiede Anne Beispiel",
    "owner_name": "Anne Beispiel",
    "street": "Werkstattweg 5",
    "postal_code": "80331",
    "city": "München",
    "country": "Deutschland",
    "phone": "+49 89 7654321",
    "email": "werkstatt@example.com",
    "tax_number": "143/123/45678",
    "vat_id": "DE123456789",
    "iban": "DE89 3704 0044 0532 0130 00",
    "bic": "COBADEFFXXX",
    "bank_name": "Beispielbank",
    "is_kleinunternehmer": False,
    "default_vat_rate": 19.0,
    "invoice_footer": "Vielen Dank für Ihren Auftrag.",
}


@pytest.fixture
def pdf_text(monkeypatch) -> List[str]:
    """Every string drawn by the invoice renderer, in order."""
    drawn: List[str] = []
    cls = pdf_service._GoldsmithPDF
    original_cell = cls.cell
    original_multi = cls.multi_cell

    def _text(args: tuple, kwargs: dict) -> str:
        if "text" in kwargs:
            return str(kwargs["text"])
        return str(args[2]) if len(args) > 2 else ""

    def cell(self, *args: Any, **kwargs: Any):
        drawn.append(_text(args, kwargs))
        return original_cell(self, *args, **kwargs)

    def multi_cell(self, *args: Any, **kwargs: Any):
        drawn.append(_text(args, kwargs))
        return original_multi(self, *args, **kwargs)

    monkeypatch.setattr(cls, "cell", cell)
    monkeypatch.setattr(cls, "multi_cell", multi_cell)
    return drawn


def _joined(drawn: List[str]) -> str:
    return "\n".join(drawn)


async def _save_settings(client: AsyncClient, headers: dict, **overrides: Any) -> dict:
    resp = await client.put(
        SETTINGS_URL, json={**SETTINGS, **overrides}, headers=headers
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _completed_order(
    db: AsyncSession, customer: Customer, price: float = 1000.0
) -> Order:
    customer.street = "Kundenstraße 12"
    customer.postal_code = "10115"
    customer.city = "Berlin"
    order = Order(
        title="Trauring 585 Gelbgold",
        customer_id=customer.id,
        status=OrderStatusEnum.COMPLETED,
        price=price,
        completed_at=datetime(2026, 9, 20, 15, 0),
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)
    return order


async def _create_invoice(client: AsyncClient, headers: dict, order_id: int) -> dict:
    resp = await client.post(
        f"{INVOICES_URL}/",
        json={
            "order_id": order_id,
            "due_date": (datetime.utcnow() + timedelta(days=14)).isoformat(),
        },
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _send(client: AsyncClient, headers: dict, invoice_id: int) -> dict:
    resp = await client.post(f"{INVOICES_URL}/{invoice_id}/send", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _pdf(client: AsyncClient, headers: dict, invoice_id: int) -> bytes:
    resp = await client.get(f"{INVOICES_URL}/{invoice_id}/pdf", headers=headers)
    assert resp.status_code == 200, resp.text
    return resp.content


# --------------------------------------------------------------------------
# Workshop settings endpoints
# --------------------------------------------------------------------------


async def test_settings_default_to_config_and_report_missing_fields(
    client: AsyncClient, admin_auth_headers: dict
) -> None:
    resp = await client.get(SETTINGS_URL, headers=admin_auth_headers)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["is_complete"] is False
    assert "Steuernummer oder USt-IdNr." in body["missing_fields"]


async def test_admin_saves_settings_and_they_are_complete(
    client: AsyncClient, admin_auth_headers: dict
) -> None:
    body = await _save_settings(client, admin_auth_headers)

    assert body["is_complete"] is True
    assert body["missing_fields"] == []
    assert body["iban"] == "DE89370400440532013000"
    again = await client.get(SETTINGS_URL, headers=admin_auth_headers)
    assert again.json()["street"] == "Werkstattweg 5"


async def test_settings_are_admin_only(
    client: AsyncClient, goldsmith_auth_headers: dict
) -> None:
    read = await client.get(SETTINGS_URL, headers=goldsmith_auth_headers)
    write = await client.put(
        SETTINGS_URL, json=SETTINGS, headers=goldsmith_auth_headers
    )

    assert read.status_code == 403
    assert write.status_code == 403


async def test_settings_reject_invalid_iban(
    client: AsyncClient, admin_auth_headers: dict
) -> None:
    resp = await client.put(
        SETTINGS_URL,
        json={**SETTINGS, "iban": "keine-iban"},
        headers=admin_auth_headers,
    )

    assert resp.status_code == 422


async def test_settings_access_is_audit_logged(
    client: AsyncClient,
    admin_auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from sqlalchemy.orm import sessionmaker

    from goldsmith_erp.db.models import CustomerAuditLog
    from goldsmith_erp.middleware import audit_logging

    # The middleware opens its own session; point it at the test engine
    # (same approach as test_audit_logging_middleware.py).
    monkeypatch.setattr(
        audit_logging,
        "AsyncSessionLocal",
        sessionmaker(bind=db_session.bind, class_=AsyncSession, expire_on_commit=False),
    )
    await _save_settings(client, admin_auth_headers)
    await client.get(SETTINGS_URL, headers=admin_auth_headers)

    rows = (
        (
            await db_session.execute(
                select(CustomerAuditLog).where(
                    CustomerAuditLog.entity == "workshop_settings"
                )
            )
        )
        .scalars()
        .all()
    )
    assert len(rows) >= 2


# --------------------------------------------------------------------------
# §14 Abs. 4 UStG PDF content
# --------------------------------------------------------------------------


async def test_issued_invoice_pdf_contains_every_ustg14_element(
    client: AsyncClient,
    admin_auth_headers: dict,
    db_session: AsyncSession,
    test_customer: Customer,
    pdf_text: List[str],
) -> None:
    await _save_settings(client, admin_auth_headers)
    order = await _completed_order(db_session, test_customer)
    invoice = await _create_invoice(client, admin_auth_headers, order.id)
    pdf_text.clear()

    sent = await _send(client, admin_auth_headers, invoice["id"])
    text = _joined(pdf_text)

    year = berlin_year()
    assert sent["invoice_number"] == f"RE-{year}-0001"
    # Nr. 1: seller and recipient, name and address.
    assert "Goldschmiede Anne Beispiel" in text
    assert "Werkstattweg 5" in text
    assert "80331 München" in text
    assert "Maria Mustermann" in text
    assert "Kundenstraße 12" in text
    assert "10115 Berlin" in text
    # Nr. 2: tax number and VAT id.
    assert "Steuernummer: 143/123/45678" in text
    assert "USt-IdNr.: DE123456789" in text
    # Nr. 3 + 4: invoice date and sequential number.
    assert "Rechnungsdatum" in text
    assert datetime.utcnow().strftime("%d.%m.%Y") in text
    assert f"RE-{year}-0001" in text
    # Nr. 5: quantity and description.
    assert "Menge" in text
    assert "Auftrag: Trauring 585 Gelbgold" in text
    # Nr. 6: Leistungsdatum from the order's completion.
    assert "Leistungsdatum" in text
    assert "20.09.2026" in text
    # Nr. 7 + 8: net per rate, rate and VAT amount, gross.
    assert "Nettobetrag 19 %" in text
    assert "1.000,00 €" in text
    assert "Umsatzsteuer 19 %" in text
    assert "190,00 €" in text
    assert "Gesamtbetrag (brutto)" in text
    assert "1.190,00 €" in text
    # Payment details and footer from the settings.
    assert "DE89370400440532013000" in text
    assert "Vielen Dank für Ihren Auftrag." in text


async def test_kleinunternehmer_invoice_has_no_vat_and_the_section_19_note(
    client: AsyncClient,
    admin_auth_headers: dict,
    db_session: AsyncSession,
    test_customer: Customer,
    pdf_text: List[str],
) -> None:
    await _save_settings(client, admin_auth_headers, is_kleinunternehmer=True)
    order = await _completed_order(db_session, test_customer, price=500.0)
    invoice = await _create_invoice(client, admin_auth_headers, order.id)
    pdf_text.clear()

    await _send(client, admin_auth_headers, invoice["id"])
    text = _joined(pdf_text)

    assert invoice["tax_rate"] == 0.0
    assert invoice["tax_amount"] == 0.0
    assert invoice["total"] == 500.0
    assert "Gemäß § 19 UStG wird keine Umsatzsteuer berechnet." in text
    assert "Umsatzsteuer 19 %" not in text


async def test_draft_created_before_settings_gets_them_when_issued(
    client: AsyncClient,
    admin_auth_headers: dict,
    db_session: AsyncSession,
    test_customer: Customer,
    pdf_text: List[str],
) -> None:
    order = await _completed_order(db_session, test_customer)
    invoice = await _create_invoice(client, admin_auth_headers, order.id)
    await _save_settings(client, admin_auth_headers)
    pdf_text.clear()

    await _send(client, admin_auth_headers, invoice["id"])

    assert "Werkstattweg 5" in _joined(pdf_text)


async def test_settings_change_after_issue_does_not_change_the_pdf(
    client: AsyncClient,
    admin_auth_headers: dict,
    db_session: AsyncSession,
    test_customer: Customer,
) -> None:
    await _save_settings(client, admin_auth_headers)
    order = await _completed_order(db_session, test_customer)
    invoice = await _create_invoice(client, admin_auth_headers, order.id)
    await _send(client, admin_auth_headers, invoice["id"])
    before = await _pdf(client, admin_auth_headers, invoice["id"])

    await _save_settings(client, admin_auth_headers, street="Neue Straße 1")
    after = await _pdf(client, admin_auth_headers, invoice["id"])

    assert after == before
    row = (
        await db_session.execute(select(Invoice).where(Invoice.id == invoice["id"]))
    ).scalar_one()
    assert hashlib.sha256(after).hexdigest() == row.issued_pdf_sha256


async def test_invoice_numbers_are_sequential(
    client: AsyncClient,
    admin_auth_headers: dict,
    db_session: AsyncSession,
    test_customer: Customer,
) -> None:
    first_order = await _completed_order(db_session, test_customer)
    second_order = await _completed_order(db_session, test_customer)

    first = await _create_invoice(client, admin_auth_headers, first_order.id)
    second = await _create_invoice(client, admin_auth_headers, second_order.id)

    year = berlin_year()
    assert first["invoice_number"] == f"RE-{year}-0001"
    assert second["invoice_number"] == f"RE-{year}-0002"


# --------------------------------------------------------------------------
# Storno (DOM-24b)
# --------------------------------------------------------------------------


async def test_cancelling_an_issued_invoice_emits_a_linked_negative_storno(
    client: AsyncClient,
    admin_auth_headers: dict,
    db_session: AsyncSession,
    test_customer: Customer,
    pdf_text: List[str],
) -> None:
    await _save_settings(client, admin_auth_headers)
    order = await _completed_order(db_session, test_customer)
    original = await _create_invoice(client, admin_auth_headers, order.id)
    await _send(client, admin_auth_headers, original["id"])
    original_pdf = await _pdf(client, admin_auth_headers, original["id"])
    pdf_text.clear()

    resp = await client.post(
        f"{INVOICES_URL}/{original['id']}/cancel", headers=admin_auth_headers
    )

    assert resp.status_code == 200, resp.text
    cancelled = resp.json()
    assert cancelled["status"] == "cancelled"
    storno_id = cancelled["cancelled_by_invoice_id"]
    assert storno_id is not None

    storno = (
        await client.get(f"{INVOICES_URL}/{storno_id}", headers=admin_auth_headers)
    ).json()
    year = berlin_year()
    assert storno["invoice_number"] == f"RE-{year}-0002"
    assert storno["cancels_invoice_id"] == original["id"]
    assert storno["status"] == "sent"
    assert storno["subtotal"] == -1000.0
    assert storno["tax_amount"] == -190.0
    assert storno["total"] == -1190.0
    assert storno["scrap_gold_credit"] == 0.0
    assert all(line["total"] < 0 for line in storno["line_items"])

    # The Storno is issued (frozen) at once and says what it cancels.
    text = _joined(pdf_text)
    assert "STORNORECHNUNG" in text
    assert f"Storno zur Rechnung RE-{year}-0001" in text
    assert "-1.190,00 €" in text
    storno_pdf = await _pdf(client, admin_auth_headers, storno_id)
    assert storno_pdf.startswith(b"%PDF")

    # The original is not edited: same frozen bytes as before.
    assert await _pdf(client, admin_auth_headers, original["id"]) == original_pdf


async def test_paid_invoice_is_reversed_through_the_storno_endpoint(
    client: AsyncClient,
    admin_auth_headers: dict,
    db_session: AsyncSession,
    test_customer: Customer,
) -> None:
    order = await _completed_order(db_session, test_customer)
    original = await _create_invoice(client, admin_auth_headers, order.id)
    paid = await client.post(
        f"{INVOICES_URL}/{original['id']}/mark-paid",
        json={"payment_method": "Bar"},
        headers=admin_auth_headers,
    )
    assert paid.status_code == 200, paid.text

    refused = await client.post(
        f"{INVOICES_URL}/{original['id']}/cancel", headers=admin_auth_headers
    )
    storno = await client.post(
        f"{INVOICES_URL}/{original['id']}/storno",
        json={"reason": "Ware zurückgegeben"},
        headers=admin_auth_headers,
    )

    assert refused.status_code == 422
    assert storno.status_code == 201, storno.text
    body = storno.json()
    assert body["cancels_invoice_id"] == original["id"]
    assert body["total"] == pytest.approx(-original["total"])
    reread = await client.get(
        f"{INVOICES_URL}/{original['id']}", headers=admin_auth_headers
    )
    assert reread.json()["status"] == "cancelled"
    assert reread.json()["cancelled_by_invoice_id"] == body["id"]


async def test_storno_cannot_be_cancelled_paid_or_edited(
    client: AsyncClient,
    admin_auth_headers: dict,
    db_session: AsyncSession,
    test_customer: Customer,
) -> None:
    order = await _completed_order(db_session, test_customer)
    original = await _create_invoice(client, admin_auth_headers, order.id)
    await _send(client, admin_auth_headers, original["id"])
    storno = (
        await client.post(
            f"{INVOICES_URL}/{original['id']}/storno", headers=admin_auth_headers
        )
    ).json()

    again = await client.post(
        f"{INVOICES_URL}/{storno['id']}/storno", headers=admin_auth_headers
    )
    cancel = await client.post(
        f"{INVOICES_URL}/{storno['id']}/cancel", headers=admin_auth_headers
    )
    pay = await client.post(
        f"{INVOICES_URL}/{storno['id']}/mark-paid", json={}, headers=admin_auth_headers
    )
    edit = await client.put(
        f"{INVOICES_URL}/{storno['id']}",
        json={"notes": "x"},
        headers=admin_auth_headers,
    )
    twice = await client.post(
        f"{INVOICES_URL}/{original['id']}/storno", headers=admin_auth_headers
    )

    assert again.status_code == 422
    assert cancel.status_code == 422
    assert pay.status_code == 422
    assert edit.status_code == 409
    assert twice.status_code == 422


async def test_draft_cannot_be_reversed_by_storno(
    client: AsyncClient,
    admin_auth_headers: dict,
    db_session: AsyncSession,
    test_customer: Customer,
) -> None:
    order = await _completed_order(db_session, test_customer)
    draft = await _create_invoice(client, admin_auth_headers, order.id)

    resp = await client.post(
        f"{INVOICES_URL}/{draft['id']}/storno", headers=admin_auth_headers
    )

    assert resp.status_code == 422


async def test_after_storno_a_corrected_invoice_can_be_created(
    client: AsyncClient,
    admin_auth_headers: dict,
    db_session: AsyncSession,
    test_customer: Customer,
) -> None:
    order = await _completed_order(db_session, test_customer)
    original = await _create_invoice(client, admin_auth_headers, order.id)
    await _send(client, admin_auth_headers, original["id"])
    await client.post(
        f"{INVOICES_URL}/{original['id']}/cancel", headers=admin_auth_headers
    )

    corrected = await _create_invoice(client, admin_auth_headers, order.id)

    assert corrected["status"] == "draft"
    assert corrected["cancels_invoice_id"] is None
    year = berlin_year()
    assert corrected["invoice_number"] == f"RE-{year}-0003"


async def test_issued_invoice_cannot_be_edited(
    client: AsyncClient,
    admin_auth_headers: dict,
    db_session: AsyncSession,
    test_customer: Customer,
) -> None:
    order = await _completed_order(db_session, test_customer)
    invoice = await _create_invoice(client, admin_auth_headers, order.id)
    await _send(client, admin_auth_headers, invoice["id"])

    resp = await client.put(
        f"{INVOICES_URL}/{invoice['id']}",
        json={"notes": "nachträglich"},
        headers=admin_auth_headers,
    )

    assert resp.status_code == 409


async def test_storno_is_excluded_from_revenue_in_the_accounting_export(
    client: AsyncClient,
    admin_auth_headers: dict,
    db_session: AsyncSession,
    test_customer: Customer,
) -> None:
    order = await _completed_order(db_session, test_customer)
    original = await _create_invoice(client, admin_auth_headers, order.id)
    await _send(client, admin_auth_headers, original["id"])
    await client.post(
        f"{INVOICES_URL}/{original['id']}/cancel", headers=admin_auth_headers
    )

    resp = await client.get(
        f"{INVOICES_URL}/export/lexoffice", headers=admin_auth_headers
    )

    assert resp.status_code == 200, resp.text
    rows = [line for line in resp.text.splitlines()[1:] if line.strip()]
    # The cancelled original yields its reversal row (existing BE-13
    # semantics); the Storno document itself is not booked a second time.
    assert len(rows) == 1, rows
    assert "Storno Rechnung" in rows[0]
    storno_number = f"RE-{berlin_year()}-0002"
    assert storno_number not in resp.text
    stored = (
        (await db_session.execute(select(Invoice).where(Invoice.order_id == order.id)))
        .scalars()
        .all()
    )
    statuses = sorted(inv.status.value for inv in stored)
    assert statuses == [InvoiceStatus.CANCELLED.value, InvoiceStatus.SENT.value]
