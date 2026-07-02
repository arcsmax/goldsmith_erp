# tests/integration/test_gdpr_endpoints.py
"""
Integration tests for GDPR-specific customer endpoints.

Covers:
  GET    /api/v1/customers/{id}/export       — GDPR Art. 15 data export
  DELETE /api/v1/customers/{id}/gdpr-erase  — GDPR Art. 17 erasure request

Permission matrix:
  - ADMIN    — allowed on both endpoints (CUSTOMER_DELETE permission)
  - GOLDSMITH — 403 on both endpoints
  - No auth  — 401

Business logic:
  - Export returns all customer data (customer fields, orders, measurements)
  - Erasure sets deletion_scheduled_at to now + 30 days and deactivates is_active
  - Duplicate erasure request returns 409
"""
from datetime import date, datetime, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import (
    Consultation,
    ConsultationOccasion,
    ConsultationStatus,
    Customer,
    CustomerNoGo,
    NoGoCategory,
    Order,
    OrderStatusEnum,
    User,
)

# ---------------------------------------------------------------------------
# URL helpers
# ---------------------------------------------------------------------------


def _export_url(customer_id: int) -> str:
    return f"/api/v1/customers/{customer_id}/export"


def _erase_url(customer_id: int) -> str:
    return f"/api/v1/customers/{customer_id}/gdpr-erase"


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def customer_with_order(
    db_session: AsyncSession, test_customer: Customer
) -> Customer:
    """
    Attach an order to the integration-test customer so that export tests
    can verify the 'orders' key contains data.
    """
    order = Order(
        title="Trauringe",
        description="Paar Trauringe 750er Gelbgold",
        customer_id=test_customer.id,
        status=OrderStatusEnum.IN_PROGRESS,
        price=1200.00,
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(test_customer)
    return test_customer


# Sentinel values used to prove design-IP fields never leak into the export
# (see test_export_never_leaks_consultation_design_ip below).
_SENTINEL_WISHES = "SENTINEL_WISHES_MUST_NOT_LEAK"
_SENTINEL_NOTES = "SENTINEL_NOTES_MUST_NOT_LEAK"
_SENTINEL_SOURCE_MATERIAL = "SENTINEL_SOURCE_MATERIAL_MUST_NOT_LEAK"
_SENTINEL_MATERIALS_DISCUSSED = "SENTINEL_MATERIALS_DISCUSSED_MUST_NOT_LEAK"


@pytest.fixture
async def customer_with_v11_personal_data(
    db_session: AsyncSession, test_customer: Customer, admin_user: User
) -> Customer:
    """
    Attach V1.1 personal-data surfaces (a no-go, a style profile, and a
    consultation) to the integration-test customer.

    The consultation's design-IP fields (wishes/notes/source_material/
    materials_discussed) are populated with distinctive sentinel values so
    export tests can assert they never appear anywhere in the serialized
    response — see CLAUDE.md "Design IP" data-privacy rule.
    """
    consultation = Consultation(
        customer_id=test_customer.id,
        conducted_by=admin_user.id,
        occasion=ConsultationOccasion.WEDDING,
        occasion_date=date(2026, 9, 1),
        budget_min=1000.0,
        budget_max=2000.0,
        status=ConsultationStatus.COMPLETED,
        wishes=_SENTINEL_WISHES,
        notes=_SENTINEL_NOTES,
        source_material=_SENTINEL_SOURCE_MATERIAL,
        materials_discussed=[{"metal": _SENTINEL_MATERIALS_DISCUSSED}],
    )
    db_session.add(consultation)

    no_go = CustomerNoGo(
        customer_id=test_customer.id,
        category=NoGoCategory.ALLERGY,
        value="Nickel",
        note="Schwere Reaktion",
    )
    db_session.add(no_go)

    test_customer.style_profile = {
        "metal_tones": ["gelb"],
        "style_words": ["klassisch"],
    }

    await db_session.commit()
    await db_session.refresh(test_customer)
    return test_customer


# ---------------------------------------------------------------------------
# GDPR Export — GET /api/v1/customers/{id}/export
# ---------------------------------------------------------------------------


class TestGdprExport:

    @pytest.mark.asyncio
    async def test_export_returns_200_for_admin(
        self,
        client: AsyncClient,
        test_customer: Customer,
        admin_auth_headers: dict,
    ):
        response = await client.get(
            _export_url(test_customer.id),
            headers=admin_auth_headers,
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_export_contains_required_top_level_keys(
        self,
        client: AsyncClient,
        test_customer: Customer,
        admin_auth_headers: dict,
    ):
        response = await client.get(
            _export_url(test_customer.id),
            headers=admin_auth_headers,
        )
        body = response.json()

        assert "export_date" in body
        assert "customer" in body
        assert "orders" in body
        assert "measurements" in body

    @pytest.mark.asyncio
    async def test_export_customer_section_contains_pii_fields(
        self,
        client: AsyncClient,
        test_customer: Customer,
        admin_auth_headers: dict,
    ):
        """All PII fields the router serialises must be present in the export."""
        response = await client.get(
            _export_url(test_customer.id),
            headers=admin_auth_headers,
        )
        customer_data = response.json()["customer"]

        assert customer_data["id"] == test_customer.id
        assert customer_data["first_name"] == test_customer.first_name
        assert customer_data["last_name"] == test_customer.last_name
        assert customer_data["email"] == test_customer.email

    @pytest.mark.asyncio
    async def test_export_includes_linked_orders(
        self,
        client: AsyncClient,
        customer_with_order: Customer,
        admin_auth_headers: dict,
    ):
        response = await client.get(
            _export_url(customer_with_order.id),
            headers=admin_auth_headers,
        )
        body = response.json()

        assert len(body["orders"]) >= 1
        order = body["orders"][0]
        # Verify order data shape
        assert "id" in order
        assert "status" in order
        assert "created_at" in order
        assert "deadline" in order

    @pytest.mark.asyncio
    async def test_export_measurements_list_is_present(
        self,
        client: AsyncClient,
        test_customer: Customer,
        admin_auth_headers: dict,
    ):
        """measurements key must be a list (empty if no measurements exist)."""
        response = await client.get(
            _export_url(test_customer.id),
            headers=admin_auth_headers,
        )
        body = response.json()
        assert isinstance(body["measurements"], list)

    @pytest.mark.asyncio
    async def test_export_contains_v11_top_level_keys(
        self,
        client: AsyncClient,
        test_customer: Customer,
        admin_auth_headers: dict,
    ):
        """V1.1 personal-data surfaces (issue #14) must always be present,
        even when the customer has none of them yet."""
        response = await client.get(
            _export_url(test_customer.id),
            headers=admin_auth_headers,
        )
        body = response.json()

        assert "no_gos" in body
        assert isinstance(body["no_gos"], list)
        assert "style_profile" in body
        assert "consultations" in body
        assert isinstance(body["consultations"], list)
        assert "design_data_excluded" in body
        assert body["design_data_excluded"] is True

    @pytest.mark.asyncio
    async def test_export_style_profile_is_empty_dict_when_null(
        self,
        client: AsyncClient,
        test_customer: Customer,
        admin_auth_headers: dict,
    ):
        response = await client.get(
            _export_url(test_customer.id),
            headers=admin_auth_headers,
        )
        body = response.json()
        assert body["style_profile"] == {}

    @pytest.mark.asyncio
    async def test_export_includes_no_go_and_consultation_metadata(
        self,
        client: AsyncClient,
        customer_with_v11_personal_data: Customer,
        admin_auth_headers: dict,
    ):
        response = await client.get(
            _export_url(customer_with_v11_personal_data.id),
            headers=admin_auth_headers,
        )
        body = response.json()

        assert len(body["no_gos"]) >= 1
        no_go = body["no_gos"][0]
        assert no_go["category"] == "allergy"
        assert no_go["value"] == "Nickel"
        assert no_go["note"] == "Schwere Reaktion"
        assert "created_at" in no_go

        assert body["style_profile"] == {
            "metal_tones": ["gelb"],
            "style_words": ["klassisch"],
        }

        assert len(body["consultations"]) >= 1
        consultation = body["consultations"][0]
        assert "id" in consultation
        assert consultation["occasion"] == "wedding"
        assert consultation["occasion_date"] == "2026-09-01"
        assert consultation["budget_min"] == 1000.0
        assert consultation["budget_max"] == 2000.0
        assert consultation["status"] == "completed"
        assert "created_at" in consultation
        assert "converted_order_id" in consultation
        assert "converted_quote_id" in consultation

    @pytest.mark.asyncio
    async def test_export_never_leaks_consultation_design_ip(
        self,
        client: AsyncClient,
        customer_with_v11_personal_data: Customer,
        admin_auth_headers: dict,
    ):
        """Design-IP rule (CLAUDE.md, binding): wishes/notes/source_material/
        materials_discussed/photos must NEVER appear anywhere in the GDPR
        export, even though the consultation row has them populated."""
        response = await client.get(
            _export_url(customer_with_v11_personal_data.id),
            headers=admin_auth_headers,
        )
        body_text = str(response.json())

        assert _SENTINEL_WISHES not in body_text
        assert _SENTINEL_NOTES not in body_text
        assert _SENTINEL_SOURCE_MATERIAL not in body_text
        assert _SENTINEL_MATERIALS_DISCUSSED not in body_text

    @pytest.mark.asyncio
    async def test_export_is_forbidden_for_goldsmith(
        self,
        client: AsyncClient,
        test_customer: Customer,
        goldsmith_auth_headers: dict,
    ):
        """GOLDSMITH role must receive 403 — CUSTOMER_DELETE permission is ADMIN-only."""
        response = await client.get(
            _export_url(test_customer.id),
            headers=goldsmith_auth_headers,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_export_is_forbidden_without_auth(
        self,
        client: AsyncClient,
        test_customer: Customer,
    ):
        response = await client.get(_export_url(test_customer.id))
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_export_returns_404_for_nonexistent_customer(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
    ):
        response = await client.get(
            _export_url(999999),
            headers=admin_auth_headers,
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# GDPR Erasure — DELETE /api/v1/customers/{id}/gdpr-erase
# ---------------------------------------------------------------------------


class TestGdprErasure:

    @pytest.mark.asyncio
    async def test_erasure_returns_200_for_admin(
        self,
        client: AsyncClient,
        test_customer: Customer,
        admin_auth_headers: dict,
    ):
        response = await client.delete(
            _erase_url(test_customer.id),
            headers=admin_auth_headers,
        )
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_erasure_schedules_deletion_30_days_in_future(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_customer: Customer,
        admin_auth_headers: dict,
    ):
        """
        After a successful erasure request the deletion_date in the response
        body must be 30 days from today, and the DB row must reflect this.
        """
        response = await client.delete(
            _erase_url(test_customer.id),
            headers=admin_auth_headers,
        )
        body = response.json()

        expected_date = (datetime.utcnow() + timedelta(days=30)).date()
        returned_date = date.fromisoformat(body["deletion_date"])

        assert returned_date == expected_date
        assert body["customer_id"] == test_customer.id

    @pytest.mark.asyncio
    async def test_erasure_sets_is_active_false(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_customer: Customer,
        admin_auth_headers: dict,
    ):
        """Erased customer must be deactivated immediately."""
        await client.delete(
            _erase_url(test_customer.id),
            headers=admin_auth_headers,
        )

        # Re-query the customer from the DB
        result = await db_session.execute(
            select(Customer).filter(Customer.id == test_customer.id)
        )
        customer = result.scalar_one()
        assert customer.is_active is False

    @pytest.mark.asyncio
    async def test_erasure_sets_deletion_scheduled_at_in_db(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_customer: Customer,
        admin_auth_headers: dict,
    ):
        """deletion_scheduled_at must be written to the DB row."""
        await client.delete(
            _erase_url(test_customer.id),
            headers=admin_auth_headers,
        )

        result = await db_session.execute(
            select(Customer).filter(Customer.id == test_customer.id)
        )
        customer = result.scalar_one()

        assert customer.deletion_scheduled_at is not None
        min_expected = datetime.utcnow() + timedelta(days=29)
        max_expected = datetime.utcnow() + timedelta(days=31)
        assert min_expected < customer.deletion_scheduled_at < max_expected

    @pytest.mark.asyncio
    async def test_duplicate_erasure_request_returns_409(
        self,
        client: AsyncClient,
        test_customer: Customer,
        admin_auth_headers: dict,
    ):
        """
        Calling gdpr-erase twice for the same customer must return 409 Conflict
        on the second call, because deletion_scheduled_at is already set.
        """
        # First request — must succeed
        first = await client.delete(
            _erase_url(test_customer.id),
            headers=admin_auth_headers,
        )
        assert first.status_code == 200

        # Second request — must be rejected
        second = await client.delete(
            _erase_url(test_customer.id),
            headers=admin_auth_headers,
        )
        assert second.status_code == 409

    @pytest.mark.asyncio
    async def test_erasure_is_forbidden_for_goldsmith(
        self,
        client: AsyncClient,
        test_customer: Customer,
        goldsmith_auth_headers: dict,
    ):
        """GOLDSMITH role must receive 403 — CUSTOMER_DELETE permission is ADMIN-only."""
        response = await client.delete(
            _erase_url(test_customer.id),
            headers=goldsmith_auth_headers,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_erasure_is_forbidden_without_auth(
        self,
        client: AsyncClient,
        test_customer: Customer,
    ):
        response = await client.delete(_erase_url(test_customer.id))
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_erasure_returns_404_for_nonexistent_customer(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
    ):
        response = await client.delete(
            _erase_url(999999),
            headers=admin_auth_headers,
        )
        assert response.status_code == 404
