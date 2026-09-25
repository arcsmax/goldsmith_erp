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

from datetime import date, datetime, timedelta, timezone

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


# Sentinel values used to prove design-IP fields never leak into the export
# (see test_export_never_leaks_consultation_design_ip and
# test_export_never_leaks_order_description below).
# D-13 (GDPR-05): wishes and source_material are what the CUSTOMER told us —
# disclosed, but only in the ``consultation_statements`` section.
_SENTINEL_WISHES = "SENTINEL_CUSTOMER_WISHES_DISCLOSED"
_SENTINEL_NOTES = "SENTINEL_NOTES_MUST_NOT_LEAK"
_SENTINEL_SOURCE_MATERIAL = "SENTINEL_CUSTOMER_SOURCE_MATERIAL_DISCLOSED"
_SENTINEL_MATERIALS_DISCUSSED = "SENTINEL_MATERIALS_DISCUSSED_MUST_NOT_LEAK"
# order.description is the design brief for a custom piece — design IP
# (CLAUDE.md: "Design descriptions in orders are business-confidential"),
# excluded from the Art. 15 export exactly like the consultation fields.
_SENTINEL_ORDER_DESCRIPTION = "SENTINEL_ORDER_DESIGN_BRIEF_MUST_NOT_LEAK"


@pytest.fixture
async def customer_with_order(
    db_session: AsyncSession, test_customer: Customer
) -> Customer:
    """
    Attach an order to the integration-test customer so that export tests
    can verify the 'orders' key contains data.

    ``description`` carries a distinctive sentinel so export tests can assert
    the design brief never appears anywhere in the serialized response — see
    CLAUDE.md "Design IP" data-privacy rule and finding 2.11.
    """
    order = Order(
        title="Trauringe",
        description=_SENTINEL_ORDER_DESCRIPTION,
        customer_id=test_customer.id,
        status=OrderStatusEnum.IN_PROGRESS,
        price=1200.00,
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(test_customer)
    return test_customer


@pytest.fixture
async def customer_with_v11_personal_data(
    db_session: AsyncSession, test_customer: Customer, admin_user: User
) -> Customer:
    """
    Attach V1.1 personal-data surfaces (a no-go, a style profile, and a
    consultation) to the integration-test customer.

    The consultation's fields are populated with distinctive sentinel values
    so export tests can assert that design IP (notes/materials_discussed)
    never appears and that customer-supplied facts (wishes/source_material)
    appear only where D-13 puts them.
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
        # Non-IP order fields survive the export.
        assert "id" in order
        assert "status" in order
        assert "price" in order
        assert order["price"] == 1200.00
        assert "created_at" in order
        assert "deadline" in order
        # Design-IP exclusion (finding 2.11): the design brief
        # (order.description) must NOT be present in the export.
        assert "description" not in order

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
        """Design-IP rule (CLAUDE.md, binding) as refined by decision D-13:
        the goldsmith's own work (notes, materials_discussed, photos) never
        appears; what the customer told us (wishes, source_material) is
        disclosed ONLY in ``consultation_statements``."""
        response = await client.get(
            _export_url(customer_with_v11_personal_data.id),
            headers=admin_auth_headers,
        )
        body = response.json()
        body_text = str(body)

        assert _SENTINEL_NOTES not in body_text
        assert _SENTINEL_MATERIALS_DISCUSSED not in body_text
        # Customer-supplied facts: present, but not on the consultation items.
        assert _SENTINEL_WISHES not in str(body["consultations"])
        assert _SENTINEL_SOURCE_MATERIAL not in str(body["consultations"])
        statements = body["consultation_statements"]
        assert [s["wishes"] for s in statements] == [_SENTINEL_WISHES]
        assert [s["source_material"] for s in statements] == [_SENTINEL_SOURCE_MATERIAL]
        assert set(statements[0]) == {"consultation_id", "wishes", "source_material"}

    @pytest.mark.asyncio
    async def test_export_never_leaks_order_description(
        self,
        client: AsyncClient,
        customer_with_order: Customer,
        admin_auth_headers: dict,
    ):
        """Design-IP rule (CLAUDE.md, binding; finding 2.11): the order
        description (the design brief for a custom piece) must NEVER appear
        anywhere in the GDPR export, even though the order row has it
        populated — mirrors the consultation design-IP exclusion."""
        response = await client.get(
            _export_url(customer_with_order.id),
            headers=admin_auth_headers,
        )
        body = response.json()

        # The design brief must not appear as a key on any exported order...
        assert body["orders"]
        for order in body["orders"]:
            assert "description" not in order
        # ...nor anywhere else in the serialized payload.
        assert _SENTINEL_ORDER_DESCRIPTION not in str(body)

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

        expected_date = (datetime.now(timezone.utc) + timedelta(days=30)).date()
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
        min_expected = datetime.now(timezone.utc) + timedelta(days=29)
        max_expected = datetime.now(timezone.utc) + timedelta(days=31)
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


# ---------------------------------------------------------------------------
# GDPR-05 — completeness of the Art. 15 export
# ---------------------------------------------------------------------------

_SENTINEL_DIAGNOSIS = "SENTINEL_REPAIR_DIAGNOSIS_WITHHELD"
_SENTINEL_SIGNATURE = "data:image/png;base64,SENTINEL_SIGNATURE_BYTES"


@pytest.fixture
async def customer_with_every_record(
    db_session: AsyncSession, customer_with_order: Customer, admin_user: User
) -> Customer:
    """One row in every customer-linked table the export must cover."""
    from goldsmith_erp.db.models import (
        AlloyType,
        CostChangeRequest,
        CostChangeStatus,
        CustomerConsent,
        CustomerUpdate,
        CustomerUpdateKind,
        CustomerUpdateStatus,
        Invoice,
        InvoiceLineItem,
        InvoiceStatus,
        OrderEvent,
        OrderPhoto,
        Quote,
        QuoteLineItem,
        QuoteStatus,
        RepairItemType,
        RepairJob,
        RepairJobStatus,
        RepairPhoto,
        RepairPhotoPhase,
        ScrapGold,
        ScrapGoldItem,
        ScrapGoldStatus,
        ValuationCertificate,
    )

    customer = customer_with_order
    order = (
        await db_session.execute(select(Order).where(Order.customer_id == customer.id))
    ).scalar_one()

    invoice = Invoice(
        invoice_number="RE-2026-EXP1",
        order_id=order.id,
        customer_id=customer.id,
        created_by=admin_user.id,
        status=InvoiceStatus.PAID,
        due_date=datetime.now(timezone.utc) + timedelta(days=14),
        subtotal=100.0,
        tax_amount=19.0,
        total=119.0,
    )
    quote = Quote(
        quote_number="KV-2026-EXP1",
        order_id=order.id,
        customer_id=customer.id,
        created_by=admin_user.id,
        status=QuoteStatus.APPROVED,
        valid_until=datetime.now(timezone.utc) + timedelta(days=14),
        customer_signature_data=_SENTINEL_SIGNATURE,
    )
    scrap = ScrapGold(
        order_id=order.id,
        customer_id=customer.id,
        created_by=admin_user.id,
        status=ScrapGoldStatus.RECEIVED,
        total_fine_gold_g=2.925,
        total_value_eur=150.0,
        signature_data=_SENTINEL_SIGNATURE,
    )
    valuation = ValuationCertificate(
        certificate_number="WG-2026-EXP1",
        order_id=order.id,
        customer_id=customer.id,
        created_by=admin_user.id,
        item_description="Solitärring",
        appraised_value=1500.0,
        valuation_date=datetime.now(timezone.utc),
        valid_until=datetime.now(timezone.utc) + timedelta(days=730),
        goldsmith_name="Export Test",
    )
    repair = RepairJob(
        repair_number="REP-2026-EXP1",
        bag_number="EXP-1",
        customer_id=customer.id,
        received_by=admin_user.id,
        item_description="Kette gerissen",
        item_type=RepairItemType.CHAIN,
        status=RepairJobStatus.RECEIVED,
        diagnosis_notes=_SENTINEL_DIAGNOSIS,
    )
    db_session.add_all([invoice, quote, scrap, valuation, repair])
    await db_session.flush()

    db_session.add_all(
        [
            InvoiceLineItem(
                invoice_id=invoice.id,
                description="Ring weiten",
                quantity=1.0,
                unit_price=100.0,
                total=100.0,
            ),
            QuoteLineItem(
                quote_id=quote.id,
                description="Ring weiten",
                quantity=1.0,
                unit_price=100.0,
                total=100.0,
            ),
            ScrapGoldItem(
                scrap_gold_id=scrap.id,
                description="Alter Ehering",
                alloy=AlloyType.GOLD_585,
                weight_g=5.0,
                fine_content_g=2.925,
            ),
            RepairPhoto(
                repair_job_id=repair.id,
                phase=RepairPhotoPhase.INTAKE,
                file_path="repairs/exp1.jpg",
                taken_by=admin_user.id,
            ),
            OrderPhoto(
                order_id=order.id,
                file_path="orders/exp1.jpg",
                taken_by=admin_user.id,
            ),
            OrderEvent(order_id=order.id, from_status="new", to_status="in_progress"),
            CustomerUpdate(
                order_id=order.id,
                kind=CustomerUpdateKind.PROGRESS,
                subject="Ihr Ring ist in Arbeit",
                body="Guten Tag, Ihr Ring ist in Arbeit.",
                status=CustomerUpdateStatus.SENT,
                sent_at=datetime.now(timezone.utc),
                sent_by=admin_user.id,
            ),
            CustomerUpdate(
                repair_job_id=repair.id,
                kind=CustomerUpdateKind.PROGRESS,
                subject="Ihre Kette ist angekommen",
                body="Wir haben Ihre Kette erhalten.",
                status=CustomerUpdateStatus.SENT,
                sent_by=admin_user.id,
            ),
            CostChangeRequest(
                order_id=order.id,
                original_amount=100.0,
                new_amount=130.0,
                delta_percent=30.0,
                reason="Zusätzliche Lötstelle",
                status=CostChangeStatus.SENT,
                created_by=admin_user.id,
            ),
            CustomerConsent(
                customer_id=customer.id,
                purpose="email_contact",
                method="written",
                granted_at=datetime.now(timezone.utc),
                recorded_by_user_id=admin_user.id,
            ),
        ]
    )
    await db_session.commit()
    return customer


class TestGdprExportCompleteness:
    @pytest.mark.asyncio
    async def test_export_covers_every_customer_linked_table(
        self,
        client: AsyncClient,
        customer_with_every_record: Customer,
        admin_auth_headers: dict,
    ):
        response = await client.get(
            _export_url(customer_with_every_record.id), headers=admin_auth_headers
        )
        assert response.status_code == 200
        body = response.json()

        assert [i["invoice_number"] for i in body["invoices"]] == ["RE-2026-EXP1"]
        assert body["invoices"][0]["line_items"][0]["description"] == "Ring weiten"
        assert [q["quote_number"] for q in body["quotes"]] == ["KV-2026-EXP1"]
        assert body["quotes"][0]["customer_signature_present"] is True
        assert body["scrap_gold"][0]["items"][0]["description"] == "Alter Ehering"
        assert body["valuations"][0]["appraised_value"] == 1500.0
        assert body["repairs"][0]["repair_number"] == "REP-2026-EXP1"
        subjects = {u["subject"] for u in body["customer_updates"]}
        assert subjects == {"Ihr Ring ist in Arbeit", "Ihre Kette ist angekommen"}
        assert body["cost_changes"][0]["reason"] == "Zusätzliche Lötstelle"
        assert {p["source"] for p in body["photos"]} == {"order", "repair"}
        assert body["order_events"][0]["to_status"] == "in_progress"
        assert [c["purpose"] for c in body["consents"]] == ["email_contact"]
        assert body["meta"]["rights"]
        assert body["meta"]["recipients"]

    @pytest.mark.asyncio
    async def test_export_withholds_design_work_signatures_and_staff(
        self,
        client: AsyncClient,
        customer_with_every_record: Customer,
        admin_auth_headers: dict,
        admin_user: User,
    ):
        response = await client.get(
            _export_url(customer_with_every_record.id), headers=admin_auth_headers
        )
        body_text = str(response.json())

        assert _SENTINEL_DIAGNOSIS not in body_text  # goldsmith's work notes
        assert "SENTINEL_SIGNATURE_BYTES" not in body_text  # copy on request
        assert _SENTINEL_ORDER_DESCRIPTION not in body_text
        assert admin_user.email not in body_text  # employee identity
        assert "file_path" not in body_text

    @pytest.mark.asyncio
    async def test_export_writes_gdpr_request_row(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_customer: Customer,
        admin_auth_headers: dict,
    ):
        from goldsmith_erp.db.models import GDPRRequest

        response = await client.get(
            _export_url(test_customer.id), headers=admin_auth_headers
        )
        assert response.status_code == 200

        rows = (
            (
                await db_session.execute(
                    select(GDPRRequest).where(
                        GDPRRequest.customer_id == test_customer.id,
                        GDPRRequest.request_type == "export",
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].status == "completed"
        # The request history is itself part of the next export.
        second = await client.get(
            _export_url(test_customer.id), headers=admin_auth_headers
        )
        assert {"export"} <= {r["request_type"] for r in second.json()["gdpr_requests"]}
