"""
Integration tests for financial-data audit logging (fix item C6).

CLAUDE.md (Data Privacy Rules → Financial Data) requires:
    "All financial data access MUST be audit-logged"

A1 (commit 38229c0) added an ``AuditLoggingMiddleware`` that writes a
``CustomerAuditLog`` row for every authenticated ``/api/v1/customers/*``
access.  R1 (commit 071d542) extended it to log bulk list access.  This
file (C6) verifies that the SAME middleware now covers the three
financial resource families:

* ``/api/v1/invoices/*``      -> entity_type="invoice"
* ``/api/v1/valuations/*``    -> entity_type="valuation"
* ``/api/v1/scrap-gold/*``    -> entity_type="scrap_gold"  (hyphen in URL,
                                underscore in audit row — consistent with
                                Python identifier conventions, easier to
                                group in reporting queries).
* ``/api/v1/consultations/*`` -> entity_type="consultation" (final-review
                                fix — consultations return budget_min/
                                budget_max, financial data of the erased
                                person; CLAUDE.md requires every financial
                                data access to be audit-logged).

Single-record reads produce ``action="financial_read"``.
List / aggregate reads (no integer id in second segment) produce
``action="list_accessed_financial"``.

The test authenticates as ADMIN, issues a GET, and asserts that a row
with the expected ``entity`` + ``entity_id`` + ``action`` lands in
``customer_audit_logs``.  Status-code assertions are deliberately
loose (202/200/404 are all acceptable — C6 is about auditing the
*attempt*, not the handler's business logic).  What matters is the row.

Fixtures:
    * ``test_invoice``       — minimal Invoice row
    * ``test_valuation``     — minimal ValuationCertificate row
    * ``test_scrap_gold``    — minimal ScrapGold row with one Item

All fixtures are defined locally in this file (minimal, just enough to
exercise the audit path; no factory library needed).

Ref: docs/fix-plan/2026-04-23/C6-financial-audit.md
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import (
    AlloyType,
    Consultation,
    ConsultationOccasion,
    Customer,
    CustomerAuditLog,
    Invoice,
    InvoiceStatus,
    Order,
    OrderStatusEnum,
    ScrapGold,
    ScrapGoldItem,
    ScrapGoldStatus,
    User,
    ValuationCertificate,
)


# ---------------------------------------------------------------------------
# Fixture: redirect the middleware's AsyncSessionLocal at the test DB factory
# ---------------------------------------------------------------------------
#
# Same rationale as tests/integration/test_audit_logging_middleware.py:
# BaseHTTPMiddleware cannot consume FastAPI's ``Depends(get_db)``, so the
# audit middleware opens its own ``AsyncSessionLocal()``.  In integration
# tests that factory is bound to production Postgres which we don't run
# here.  Patch it to the conftest's SQLite-backed session factory for the
# duration of each test.

@pytest.fixture(autouse=True)
def _patch_middleware_session(monkeypatch, db_session):
    # Bind the middleware's AsyncSessionLocal to the SAME engine db_session
    # uses, so its audit writes land in the DB the test reads. Resolving the
    # conftest's TestSessionLocal by module name was fragile: under pytest's
    # prepend import mode a second, table-less copy of the conftest engine
    # could be picked, making the middleware write to a DB without a
    # customer_audit_logs table (error swallowed) — green in isolation, red in
    # the full suite. See the matching fixture in test_audit_logging_middleware.py.
    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import sessionmaker

    from goldsmith_erp.middleware import audit_logging

    factory = sessionmaker(
        bind=db_session.bind, class_=AsyncSession, expire_on_commit=False
    )
    monkeypatch.setattr(audit_logging, "AsyncSessionLocal", factory)


# ---------------------------------------------------------------------------
# Local DB fixtures — minimal rows; just enough to have an ID to GET.
# ---------------------------------------------------------------------------


async def _create_order(db_session: AsyncSession, customer: Customer) -> Order:
    order = Order(
        title="Financial audit test order",
        description="Seed order for invoice/valuation/scrap-gold tests",
        customer_id=customer.id,
        status=OrderStatusEnum.COMPLETED,
        actual_weight_g=5.0,
        alloy="750",
        is_deleted=False,
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)
    return order


@pytest_asyncio.fixture
async def test_invoice(
    db_session: AsyncSession, test_customer: Customer, admin_user: User
) -> Invoice:
    order = await _create_order(db_session, test_customer)
    now = datetime.utcnow()
    invoice = Invoice(
        invoice_number=f"RE-{now.year}-C6T1",
        order_id=order.id,
        customer_id=test_customer.id,
        created_by=admin_user.id,
        status=InvoiceStatus.DRAFT,
        issue_date=now,
        due_date=now + timedelta(days=30),
        subtotal=100.0,
        tax_rate=19.0,
        tax_amount=19.0,
        total=119.0,
    )
    db_session.add(invoice)
    await db_session.commit()
    await db_session.refresh(invoice)
    return invoice


@pytest_asyncio.fixture
async def test_valuation(
    db_session: AsyncSession, test_customer: Customer, admin_user: User
) -> ValuationCertificate:
    order = await _create_order(db_session, test_customer)
    now = datetime.utcnow()
    cert = ValuationCertificate(
        certificate_number=f"WG-{now.year}-C6T1",
        order_id=order.id,
        customer_id=test_customer.id,
        created_by=admin_user.id,
        item_description="Brillantring 750 Gelbgold (C6 audit fixture)",
        metal_type="Gelbgold 750",
        metal_weight_g=4.8,
        metal_purity="750",
        appraised_value=3500.0,
        valuation_date=now,
        valid_until=now + timedelta(days=365 * 2),
        goldsmith_name="Test Goldsmith",
    )
    db_session.add(cert)
    await db_session.commit()
    await db_session.refresh(cert)
    return cert


@pytest_asyncio.fixture
async def test_scrap_gold(
    db_session: AsyncSession, test_customer: Customer, admin_user: User
) -> ScrapGold:
    order = await _create_order(db_session, test_customer)
    scrap = ScrapGold(
        order_id=order.id,
        customer_id=test_customer.id,
        created_by=admin_user.id,
        status=ScrapGoldStatus.RECEIVED,
        total_fine_gold_g=3.5,
        total_value_eur=220.0,
        gold_price_per_g=62.86,
        price_source="fixed_rate",
    )
    db_session.add(scrap)
    await db_session.commit()
    await db_session.refresh(scrap)

    item = ScrapGoldItem(
        scrap_gold_id=scrap.id,
        description="Alter Ehering",
        alloy=AlloyType.GOLD_750,
        weight_g=4.67,
        fine_content_g=3.5,
    )
    db_session.add(item)
    await db_session.commit()
    await db_session.refresh(scrap)
    return scrap


@pytest_asyncio.fixture
async def test_consultation(
    db_session: AsyncSession, test_customer: Customer, admin_user: User
) -> Consultation:
    consultation = Consultation(
        customer_id=test_customer.id,
        conducted_by=admin_user.id,
        occasion=ConsultationOccasion.OTHER,
        budget_min=500.0,
        budget_max=900.0,
    )
    db_session.add(consultation)
    await db_session.commit()
    await db_session.refresh(consultation)
    return consultation


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


async def _latest_audit_row(
    db_session: AsyncSession, *, entity: str, entity_id: int | None
):
    q = (
        select(CustomerAuditLog)
        .where(CustomerAuditLog.entity == entity)
        .order_by(CustomerAuditLog.timestamp.desc())
    )
    if entity_id is None:
        q = q.where(CustomerAuditLog.entity_id.is_(None))
    else:
        q = q.where(CustomerAuditLog.entity_id == entity_id)
    result = await db_session.execute(q.limit(1))
    return result.scalar_one_or_none()


# ===========================================================================
# Invoices
# ===========================================================================


@pytest.mark.asyncio
async def test_invoice_get_writes_audit_row(
    authenticated_client: AsyncClient,
    db_session: AsyncSession,
    admin_user: User,
    test_invoice: Invoice,
):
    """GET /api/v1/invoices/{id} must produce an audit row."""
    resp = await authenticated_client.get(f"/api/v1/invoices/{test_invoice.id}")
    # Permission / handler may 200 or 404 — either way, the ATTEMPT is audited.
    assert resp.status_code in (200, 404), resp.text

    row = await _latest_audit_row(
        db_session, entity="invoice", entity_id=test_invoice.id
    )
    assert row is not None, (
        "GET /api/v1/invoices/{id} must write a CustomerAuditLog row with "
        "entity='invoice' — none found"
    )
    assert row.action == "financial_read", (
        f"single-record financial read must use action='financial_read', "
        f"got '{row.action}'"
    )
    assert row.user_id == admin_user.id
    assert row.ip_address


@pytest.mark.asyncio
async def test_invoice_list_writes_audit_row(
    authenticated_client: AsyncClient,
    db_session: AsyncSession,
    admin_user: User,
    test_invoice: Invoice,
):
    """GET /api/v1/invoices/ (list) must produce an audit row with no entity_id."""
    _ = test_invoice  # ensure the list has content, not strictly required

    resp = await authenticated_client.get("/api/v1/invoices/")
    assert resp.status_code in (200, 404), resp.text

    row = await _latest_audit_row(db_session, entity="invoice", entity_id=None)
    assert row is not None, (
        "GET /api/v1/invoices/ must write an audit row (bulk financial "
        "access is a higher-risk event under GDPR Art. 30)"
    )
    assert row.action == "list_accessed_financial", (
        f"bulk financial list must use action='list_accessed_financial', "
        f"got '{row.action}'"
    )
    assert row.user_id == admin_user.id


# ===========================================================================
# Valuations
# ===========================================================================


@pytest.mark.asyncio
async def test_valuation_get_writes_audit_row(
    authenticated_client: AsyncClient,
    db_session: AsyncSession,
    admin_user: User,
    test_valuation: ValuationCertificate,
):
    """GET /api/v1/valuations/{id} must produce an audit row."""
    resp = await authenticated_client.get(
        f"/api/v1/valuations/{test_valuation.id}"
    )
    assert resp.status_code in (200, 404), resp.text

    row = await _latest_audit_row(
        db_session, entity="valuation", entity_id=test_valuation.id
    )
    assert row is not None, (
        "GET /api/v1/valuations/{id} must write a CustomerAuditLog row"
    )
    assert row.action == "financial_read"
    assert row.user_id == admin_user.id


@pytest.mark.asyncio
async def test_valuation_list_writes_audit_row(
    authenticated_client: AsyncClient,
    db_session: AsyncSession,
    admin_user: User,
    test_valuation: ValuationCertificate,
):
    """GET /api/v1/valuations (list) must produce a bulk-access audit row."""
    _ = test_valuation

    resp = await authenticated_client.get("/api/v1/valuations")
    assert resp.status_code in (200, 404, 307), resp.text

    row = await _latest_audit_row(db_session, entity="valuation", entity_id=None)
    assert row is not None, (
        "GET /api/v1/valuations must write an audit row for bulk access"
    )
    assert row.action == "list_accessed_financial"
    assert row.user_id == admin_user.id


# ===========================================================================
# Scrap gold
# ===========================================================================


@pytest.mark.asyncio
async def test_scrap_gold_get_writes_audit_row(
    authenticated_client: AsyncClient,
    db_session: AsyncSession,
    admin_user: User,
    test_scrap_gold: ScrapGold,
):
    """
    GET /api/v1/scrap-gold/{id}/receipt.pdf must produce an audit row.

    Scrap-gold has no ``GET /scrap-gold/{id}`` endpoint — the closest
    single-record read is the PDF receipt download.  That path still
    matches the ``/api/v1/scrap-gold/<int>/...`` pattern so the audit
    middleware must tag it with ``entity_id=<id>``, ``action="financial_read"``.

    The handler may fail on PDF rendering in the test environment; the
    middleware writes its row regardless.
    """
    resp = await authenticated_client.get(
        f"/api/v1/scrap-gold/{test_scrap_gold.id}/receipt.pdf"
    )
    # 200 (PDF returned), 404 (not found), 500 (PDF render glitch in test env)
    # are all acceptable — we only care that the audit row was written.
    assert resp.status_code in (200, 404, 500), resp.text

    row = await _latest_audit_row(
        db_session, entity="scrap_gold", entity_id=test_scrap_gold.id
    )
    assert row is not None, (
        "GET /api/v1/scrap-gold/{id}/... must write a CustomerAuditLog row "
        "with entity='scrap_gold'"
    )
    assert row.action == "financial_read"
    assert row.user_id == admin_user.id


@pytest.mark.asyncio
async def test_scrap_gold_list_style_write_audit_row(
    authenticated_client: AsyncClient,
    db_session: AsyncSession,
    admin_user: User,
    test_scrap_gold: ScrapGold,
):
    """
    GET /api/v1/scrap-gold/alloy-calculator?alloy=...&weight_g=... — a
    non-id sub-resource under /scrap-gold/ — must be audited as a
    bulk/aggregate financial read (entity_id=None, action=
    list_accessed_financial).  This proves the path-parser correctly
    distinguishes "second segment is digits" (single) from "second
    segment is a word" (list/aggregate).
    """
    _ = test_scrap_gold

    resp = await authenticated_client.get(
        "/api/v1/scrap-gold/alloy-calculator?alloy=750&weight_g=5.0"
    )
    assert resp.status_code in (200, 400, 404, 422), resp.text

    row = await _latest_audit_row(db_session, entity="scrap_gold", entity_id=None)
    assert row is not None, (
        "GET /api/v1/scrap-gold/alloy-calculator must still be audited — "
        "every financial-resource read is in scope for GDPR Art. 30"
    )
    assert row.action == "list_accessed_financial"
    assert row.user_id == admin_user.id


# ===========================================================================
# Consultations (final-review fix — Fix 1)
# ===========================================================================
#
# Consultations return budget_min/budget_max on every read — financial data
# of the erased person — but were missing from _RESOURCE_ROUTES entirely, so
# neither single-record nor list reads produced an audit row. Mirrors the
# invoice tests above exactly.


@pytest.mark.asyncio
async def test_consultation_get_writes_audit_row(
    authenticated_client: AsyncClient,
    db_session: AsyncSession,
    admin_user: User,
    test_consultation: Consultation,
):
    """GET /api/v1/consultations/{id} must produce an audit row."""
    resp = await authenticated_client.get(
        f"/api/v1/consultations/{test_consultation.id}"
    )
    assert resp.status_code in (200, 404), resp.text

    row = await _latest_audit_row(
        db_session, entity="consultation", entity_id=test_consultation.id
    )
    assert row is not None, (
        "GET /api/v1/consultations/{id} must write a CustomerAuditLog row "
        "with entity='consultation' — none found"
    )
    assert row.action == "financial_read", (
        f"single-record financial read must use action='financial_read', "
        f"got '{row.action}'"
    )
    assert row.user_id == admin_user.id
    assert row.ip_address


@pytest.mark.asyncio
async def test_consultation_list_writes_audit_row(
    authenticated_client: AsyncClient,
    db_session: AsyncSession,
    admin_user: User,
    test_consultation: Consultation,
):
    """GET /api/v1/consultations/ (list) must produce a bulk-access audit row."""
    _ = test_consultation  # ensure the list has content, not strictly required

    resp = await authenticated_client.get("/api/v1/consultations/")
    assert resp.status_code in (200, 404), resp.text

    row = await _latest_audit_row(db_session, entity="consultation", entity_id=None)
    assert row is not None, (
        "GET /api/v1/consultations/ must write an audit row (bulk financial "
        "access is a higher-risk event under GDPR Art. 30)"
    )
    assert row.action == "list_accessed_financial", (
        f"bulk financial list must use action='list_accessed_financial', "
        f"got '{row.action}'"
    )
    assert row.user_id == admin_user.id


# ===========================================================================
# Regression: the customer audit path is unchanged by C6
# ===========================================================================


@pytest.mark.asyncio
async def test_customer_audit_still_uses_customer_action(
    authenticated_client: AsyncClient,
    db_session: AsyncSession,
    test_customer: Customer,
):
    """
    Regression: C6 must not leak the ``financial_read`` action into the
    customer audit path.  ``GET /api/v1/customers/{id}`` must still use
    ``entity='customer'`` and ``action='accessed'`` (from A1/R1).
    """
    resp = await authenticated_client.get(f"/api/v1/customers/{test_customer.id}")
    assert resp.status_code == 200, resp.text

    row = await _latest_audit_row(
        db_session, entity="customer", entity_id=test_customer.id
    )
    assert row is not None
    assert row.action == "accessed", (
        f"customer single-record GET must still use 'accessed' action, "
        f"got '{row.action}' — C6 accidentally rerouted customers to "
        "financial_read?"
    )
