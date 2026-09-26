"""Integration tests: allergy (Art. 9 health) data behind explicit consent.

GDPR-02 — allergies may only be stored once a HEALTH_DATA consent exists
(Art. 9(2)(a) DSGVO). Writing them without one is a 422 with a German
message.

GDPR-11 — health data is readable by GOLDSMITH/ADMIN only. A VIEWER sees
neither ``customers.allergies`` nor ALLERGY-category no-gos; the field is
absent from the response, not just null.

Consent endpoints: ``POST /customers/{id}/consents`` and
``DELETE /customers/{id}/consents/{purpose}`` (CONSENT_MANAGE, GOLDSMITH +
ADMIN), audited by the ``customers`` family of the audit middleware.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import (
    Customer,
    CustomerAuditLog,
    CustomerConsent,
    CustomerNoGo,
    NoGoCategory,
    Order,
    OrderStatusEnum,
)


def _url(customer_id: int) -> str:
    return f"/api/v1/customers/{customer_id}"


async def _grant_health_consent(client: AsyncClient, customer_id: int, headers):
    resp = await client.post(
        f"{_url(customer_id)}/consents",
        json={"purpose": "health_data", "method": "written", "note": "Bogen v1"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.mark.asyncio
async def test_allergy_write_without_consent_is_422(
    client: AsyncClient, goldsmith_auth_headers: dict, test_customer: Customer
):
    resp = await client.patch(
        _url(test_customer.id),
        json={"allergies": "Nickel"},
        headers=goldsmith_auth_headers,
    )
    assert resp.status_code == 422, resp.text
    assert "Einwilligung" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_customer_create_with_allergies_is_422(
    client: AsyncClient, goldsmith_auth_headers: dict
):
    resp = await client.post(
        "/api/v1/customers/",
        json={
            "first_name": "Erika",
            "last_name": "Muster",
            "email": "erika.allergy@example.com",
            "allergies": "Nickel",
        },
        headers=goldsmith_auth_headers,
    )
    assert resp.status_code == 422, resp.text
    assert "Einwilligung" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_allergy_write_with_consent_is_stored_and_shown(
    client: AsyncClient,
    db_session: AsyncSession,
    goldsmith_auth_headers: dict,
    test_customer: Customer,
):
    consent = await _grant_health_consent(
        client, test_customer.id, goldsmith_auth_headers
    )
    assert consent["purpose"] == "health_data"
    assert consent["revoked_at"] is None

    resp = await client.patch(
        _url(test_customer.id),
        json={"allergies": "Nickel"},
        headers=goldsmith_auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["allergies"] == "Nickel"

    got = await client.get(_url(test_customer.id), headers=goldsmith_auth_headers)
    assert got.status_code == 200
    assert got.json()["allergies"] == "Nickel"

    row = (
        await db_session.execute(
            select(Customer).filter(Customer.id == test_customer.id)
        )
    ).scalar_one()
    await db_session.refresh(row)
    assert row.allergies == "Nickel"


@pytest.mark.asyncio
async def test_clearing_allergies_needs_no_consent(
    client: AsyncClient, goldsmith_auth_headers: dict, test_customer: Customer
):
    resp = await client.patch(
        _url(test_customer.id),
        json={"allergies": None},
        headers=goldsmith_auth_headers,
    )
    assert resp.status_code == 200, resp.text


@pytest.mark.asyncio
async def test_viewer_read_has_no_allergy_field(
    client: AsyncClient,
    goldsmith_auth_headers: dict,
    viewer_auth_headers: dict,
    test_customer: Customer,
):
    await _grant_health_consent(client, test_customer.id, goldsmith_auth_headers)
    await client.patch(
        _url(test_customer.id),
        json={"allergies": "Nickel"},
        headers=goldsmith_auth_headers,
    )

    resp = await client.get(_url(test_customer.id), headers=viewer_auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert "allergies" not in body
    assert body["id"] == test_customer.id


@pytest.mark.asyncio
async def test_legacy_allergies_without_consent_are_hidden(
    client: AsyncClient,
    db_session: AsyncSession,
    goldsmith_auth_headers: dict,
    test_customer: Customer,
):
    """Pre-existing allergy text without a consent record is not displayed."""
    test_customer.allergies = "Kupfer"
    await db_session.commit()

    resp = await client.get(_url(test_customer.id), headers=goldsmith_auth_headers)
    assert resp.status_code == 200
    assert "allergies" not in resp.json()


@pytest.mark.asyncio
async def test_embedded_customer_in_order_never_carries_allergies(
    client: AsyncClient,
    db_session: AsyncSession,
    viewer_auth_headers: dict,
    test_customer: Customer,
):
    test_customer.allergies = "Nickel"
    order = Order(
        title="Ring",
        description="Ring 750",
        customer_id=test_customer.id,
        status=OrderStatusEnum.NEW,
    )
    db_session.add(order)
    await db_session.commit()

    resp = await client.get(f"/api/v1/orders/{order.id}", headers=viewer_auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["customer"]["id"] == test_customer.id
    assert "allergies" not in resp.json()["customer"]
    assert "Nickel" not in resp.text


@pytest.mark.asyncio
async def test_allergy_no_go_requires_consent(
    client: AsyncClient, goldsmith_auth_headers: dict, test_customer: Customer
):
    base = f"{_url(test_customer.id)}/no-gos"
    denied = await client.post(
        base,
        json={"category": "allergy", "value": "Nickel"},
        headers=goldsmith_auth_headers,
    )
    assert denied.status_code == 422, denied.text
    assert "Einwilligung" in denied.json()["detail"]

    # Non-health no-gos stay unaffected.
    ok = await client.post(
        base,
        json={"category": "metal", "value": "Rotgold"},
        headers=goldsmith_auth_headers,
    )
    assert ok.status_code == 201, ok.text

    await _grant_health_consent(client, test_customer.id, goldsmith_auth_headers)
    allowed = await client.post(
        base,
        json={"category": "allergy", "value": "Nickel"},
        headers=goldsmith_auth_headers,
    )
    assert allowed.status_code == 201, allowed.text


@pytest.mark.asyncio
async def test_viewer_no_go_list_excludes_allergy_category(
    client: AsyncClient,
    db_session: AsyncSession,
    viewer_auth_headers: dict,
    goldsmith_auth_headers: dict,
    test_customer: Customer,
):
    db_session.add_all(
        [
            CustomerNoGo(
                customer_id=test_customer.id,
                category=NoGoCategory.ALLERGY,
                value="Nickel",
            ),
            CustomerNoGo(
                customer_id=test_customer.id,
                category=NoGoCategory.METAL,
                value="Rotgold",
            ),
        ]
    )
    await db_session.commit()

    viewer = await client.get(
        f"{_url(test_customer.id)}/no-gos", headers=viewer_auth_headers
    )
    assert viewer.status_code == 200
    assert [n["category"] for n in viewer.json()] == ["metal"]

    goldsmith = await client.get(
        f"{_url(test_customer.id)}/no-gos", headers=goldsmith_auth_headers
    )
    assert sorted(n["category"] for n in goldsmith.json()) == ["allergy", "metal"]

    check = await client.get(
        f"{_url(test_customer.id)}/no-gos/check",
        params={"candidate": ["Nickel"]},
        headers=viewer_auth_headers,
    )
    assert check.status_code == 200
    assert check.json() == []


@pytest.mark.asyncio
async def test_viewer_cannot_manage_consents(
    client: AsyncClient, viewer_auth_headers: dict, test_customer: Customer
):
    resp = await client.post(
        f"{_url(test_customer.id)}/consents",
        json={"purpose": "health_data", "method": "written"},
        headers=viewer_auth_headers,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_revoke_health_consent_deletes_allergies(
    client: AsyncClient,
    db_session: AsyncSession,
    goldsmith_auth_headers: dict,
    test_customer: Customer,
):
    await _grant_health_consent(client, test_customer.id, goldsmith_auth_headers)
    await client.patch(
        _url(test_customer.id),
        json={"allergies": "Nickel"},
        headers=goldsmith_auth_headers,
    )

    resp = await client.delete(
        f"{_url(test_customer.id)}/consents/health_data",
        headers=goldsmith_auth_headers,
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["revoked_at"] is not None

    row = (
        await db_session.execute(
            select(Customer).filter(Customer.id == test_customer.id)
        )
    ).scalar_one()
    await db_session.refresh(row)
    assert row.allergies is None

    again = await client.delete(
        f"{_url(test_customer.id)}/consents/health_data",
        headers=goldsmith_auth_headers,
    )
    assert again.status_code == 404


@pytest.mark.asyncio
async def test_consent_endpoints_are_audit_logged(
    client: AsyncClient,
    db_session: AsyncSession,
    goldsmith_auth_headers: dict,
    test_customer: Customer,
):
    await _grant_health_consent(client, test_customer.id, goldsmith_auth_headers)

    rows = list(
        (
            await db_session.execute(
                select(CustomerAuditLog).filter(
                    CustomerAuditLog.customer_id == test_customer.id
                )
            )
        ).scalars()
    )
    assert any(r.action == "consent_granted" for r in rows), [r.action for r in rows]

    consents = list(
        (
            await db_session.execute(
                select(CustomerConsent).filter(
                    CustomerConsent.customer_id == test_customer.id
                )
            )
        ).scalars()
    )
    assert len(consents) == 1


@pytest.mark.asyncio
async def test_consultation_step4_quick_allergen_no_go_reproduces_bug_and_fix(
    client: AsyncClient, goldsmith_auth_headers: dict, test_customer: Customer
):
    """Reproduces the owner-reported bug at /consultations/{id}?step=4:
    clicking a "Schnellauswahl Allergien" chip (Nickel/Kupfer/Silber) posts
    ``POST /customers/{customer_id}/no-gos`` with
    ``{"category": "allergy", "value": <chip>}`` for the consultation's
    customer. Before the fix the frontend only showed a generic
    "No-Go konnte nicht angelegt werden" toast; the actual backend response
    is a 422 with a specific German consent message (asserted below) — the
    root cause is the missing HEALTH_DATA consent, not a server error.
    """
    consultation_resp = await client.post(
        "/api/v1/consultations/",
        json={"customer_id": test_customer.id},
        headers=goldsmith_auth_headers,
    )
    assert consultation_resp.status_code == 201, consultation_resp.text
    consultation = consultation_resp.json()
    assert consultation["customer_id"] == test_customer.id

    # Step 4, chip "Nickel", no HEALTH_DATA consent recorded yet for this
    # customer (the exact reported repro).
    denied = await client.post(
        f"{_url(consultation['customer_id'])}/no-gos",
        json={"category": "allergy", "value": "Nickel"},
        headers=goldsmith_auth_headers,
    )
    assert denied.status_code == 422, denied.text
    assert denied.json()["detail"] == (
        "Allergien sind Gesundheitsdaten (Art. 9 DSGVO) und dürfen nur mit "
        "ausdrücklicher Einwilligung der Kundin/des Kunden gespeichert werden. "
        "Bitte zuerst die Einwilligung 'Gesundheitsdaten' erfassen."
    )

    # Fix: confirming the wizard's "Einwilligung Gesundheitsdaten" block
    # grants the consent via the existing consent endpoint...
    await _grant_health_consent(
        client, consultation["customer_id"], goldsmith_auth_headers
    )

    # ...after which the SAME chip click succeeds.
    allowed = await client.post(
        f"{_url(consultation['customer_id'])}/no-gos",
        json={"category": "allergy", "value": "Nickel"},
        headers=goldsmith_auth_headers,
    )
    assert allowed.status_code == 201, allowed.text
    assert allowed.json()["category"] == "allergy"
    assert allowed.json()["value"] == "Nickel"


@pytest.mark.asyncio
async def test_gdpr_export_includes_consents(
    client: AsyncClient,
    admin_auth_headers: dict,
    test_customer: Customer,
):
    await _grant_health_consent(client, test_customer.id, admin_auth_headers)

    resp = await client.get(
        f"{_url(test_customer.id)}/export", headers=admin_auth_headers
    )
    assert resp.status_code == 200, resp.text
    consents = resp.json()["consents"]
    assert len(consents) == 1
    assert consents[0]["purpose"] == "health_data"
    assert consents[0]["method"] == "written"
    assert consents[0]["granted_at"]
