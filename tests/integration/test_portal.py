"""
Integration tests for the Customer Self-Service Portal (/api/v1/portal).

Endpoint coverage:
  POST  /api/v1/portal/lookup           - look up status by reference + email
  GET   /api/v1/portal/status/{token}   - status lookup by previously issued token

Key properties:
  - Public endpoint — no authentication required.
  - Wrong email for a valid order returns 404 (no enumeration attack surface).
  - Non-existent reference number returns 404.
  - Token-based lookup requires Redis; when Redis is unavailable the token
    endpoint returns 404 (token not found).
  - Rate-limited at 10 req/min per IP via slowapi.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import AsyncMock, patch

from goldsmith_erp.db.models import (
    Customer,
    Order,
    OrderStatusEnum,
    RepairItemType,
    RepairJob,
    RepairJobStatus,
    User,
)

PORTAL_BASE = "/api/v1/portal"
LOOKUP_URL = f"{PORTAL_BASE}/lookup"


def _lookup_payload(reference: str, email: str) -> dict:
    return {"reference_number": reference, "email": email}


# ---------------------------------------------------------------------------
# Fixtures: create an order and a repair with a known email for lookup tests
# ---------------------------------------------------------------------------

async def _create_order_with_customer(
    db_session: AsyncSession,
    email: str | None = None,
) -> tuple[Order, Customer]:
    """Create a customer + order directly in the DB for portal lookup tests."""
    if email is None:
        import uuid
        email = f"portal_{uuid.uuid4().hex[:8]}@example.com"

    customer = Customer(
        first_name="Portal",
        last_name="Testkunde",
        email=email,
        customer_type="private",
        is_active=True,
    )
    db_session.add(customer)
    await db_session.flush()

    order = Order(
        title="Portal Test Order",
        description="Test order for portal lookup",
        customer_id=customer.id,
        status=OrderStatusEnum.IN_PROGRESS,
        is_deleted=False,
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(customer)
    await db_session.refresh(order)
    return order, customer


async def _create_repair_with_customer(
    db_session: AsyncSession,
    email: str | None = None,
) -> tuple[RepairJob, Customer]:
    """Create a customer + repair directly in the DB for portal lookup tests."""
    if email is None:
        import uuid
        email = f"portal_repair_{uuid.uuid4().hex[:8]}@example.com"

    customer = Customer(
        first_name="Repair",
        last_name="Kunde",
        email=email,
        customer_type="private",
        is_active=True,
    )
    db_session.add(customer)
    await db_session.flush()

    repair = RepairJob(
        repair_number="REP-2026-9901",
        bag_number="TU-2026-9901",
        customer_id=customer.id,
        item_description="Ehering — Stein lose",
        item_type=RepairItemType.RING,
        status=RepairJobStatus.IN_REPAIR,
        is_deleted=False,
    )
    db_session.add(repair)
    await db_session.commit()
    await db_session.refresh(customer)
    await db_session.refresh(repair)
    return repair, customer


# ===========================================================================
# POST /api/v1/portal/lookup — public lookup
# ===========================================================================

class TestPortalLookup:

    @pytest.mark.asyncio
    async def test_lookup_with_valid_order_id_and_email(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Valid order number + matching email returns status 200 with order info."""
        order, customer = await _create_order_with_customer(db_session)

        with patch(
            "goldsmith_erp.api.routers.customer_portal._store_token",
            new=AsyncMock(return_value=None),
        ):
            resp = await client.post(
                LOOKUP_URL,
                json=_lookup_payload(str(order.id), customer.email),
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["record_type"] == "order"
        assert data["reference_number"] == str(order.id)
        assert "status_label" in data
        assert "current_step" in data
        assert "pipeline_labels" in data
        assert isinstance(data["pipeline_labels"], list)

    @pytest.mark.asyncio
    async def test_lookup_with_valid_repair_number_and_email(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Valid REP- reference + matching email returns repair status."""
        repair, customer = await _create_repair_with_customer(db_session)

        with patch(
            "goldsmith_erp.api.routers.customer_portal._store_token",
            new=AsyncMock(return_value=None),
        ):
            resp = await client.post(
                LOOKUP_URL,
                json=_lookup_payload(repair.repair_number, customer.email),
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["record_type"] == "repair"
        assert data["reference_number"] == repair.repair_number

    @pytest.mark.asyncio
    async def test_lookup_with_wrong_email_returns_404(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """
        Generic 404 when email does not match — prevents enumeration attacks.
        No indication of whether the reference number exists.
        """
        order, _ = await _create_order_with_customer(db_session)

        resp = await client.post(
            LOOKUP_URL,
            json=_lookup_payload(str(order.id), "wrong@email.example.com"),
        )

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_lookup_with_nonexistent_order_returns_404(
        self,
        client: AsyncClient,
    ):
        """Non-existent order ID returns 404."""
        resp = await client.post(
            LOOKUP_URL,
            json=_lookup_payload("99999999", "someone@example.com"),
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_lookup_with_nonexistent_rep_number_returns_404(
        self,
        client: AsyncClient,
    ):
        """Non-existent REP- reference returns 404."""
        resp = await client.post(
            LOOKUP_URL,
            json=_lookup_payload("REP-9999-9999", "someone@example.com"),
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_lookup_response_contains_lookup_token(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Successful lookup returns a one-time token for email-link access."""
        order, customer = await _create_order_with_customer(db_session)

        with patch(
            "goldsmith_erp.api.routers.customer_portal._store_token",
            new=AsyncMock(return_value=None),
        ):
            resp = await client.post(
                LOOKUP_URL,
                json=_lookup_payload(str(order.id), customer.email),
            )

        assert resp.status_code == 200
        data = resp.json()
        # Token must be present and non-empty on successful lookup
        assert "lookup_token" in data
        assert data["lookup_token"]

    @pytest.mark.asyncio
    async def test_lookup_is_case_insensitive_for_email(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """Email comparison is case-insensitive (UPPER vs lower)."""
        order, customer = await _create_order_with_customer(
            db_session, email="case.test@example.com"
        )

        with patch(
            "goldsmith_erp.api.routers.customer_portal._store_token",
            new=AsyncMock(return_value=None),
        ):
            resp = await client.post(
                LOOKUP_URL,
                json=_lookup_payload(str(order.id), "CASE.TEST@EXAMPLE.COM"),
            )

        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_lookup_does_not_require_authentication(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """
        Portal is a public endpoint — must succeed without an Authorization header.
        This test deliberately does NOT use any auth headers.
        """
        order, customer = await _create_order_with_customer(db_session)

        with patch(
            "goldsmith_erp.api.routers.customer_portal._store_token",
            new=AsyncMock(return_value=None),
        ):
            resp = await client.post(
                LOOKUP_URL,
                json=_lookup_payload(str(order.id), customer.email),
                # No headers= argument — unauthenticated
            )

        # Must NOT return 401 — portal is public
        assert resp.status_code != 401
        assert resp.status_code == 200


# ===========================================================================
# GET /api/v1/portal/status/{token} — token-based lookup
# ===========================================================================

class TestPortalTokenLookup:

    TOKEN_URL = f"{PORTAL_BASE}/status"

    @pytest.mark.asyncio
    async def test_token_lookup_with_invalid_token_returns_404(
        self,
        client: AsyncClient,
    ):
        """
        An invalid or expired token returns 404.
        Redis is unavailable in tests so _fetch_token always returns None.
        """
        with patch(
            "goldsmith_erp.api.routers.customer_portal._fetch_token",
            new=AsyncMock(return_value=None),
        ):
            resp = await client.get(f"{self.TOKEN_URL}/invalid-token-xyz")

        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_token_lookup_with_valid_token_returns_status(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
    ):
        """When Redis returns a valid payload the status is served correctly."""
        order, customer = await _create_order_with_customer(db_session)

        fake_payload = {
            "reference_number": str(order.id),
            "email": customer.email,
            "issued_at": 1700000000,
        }

        with patch(
            "goldsmith_erp.api.routers.customer_portal._fetch_token",
            new=AsyncMock(return_value=fake_payload),
        ):
            resp = await client.get(f"{self.TOKEN_URL}/some-valid-token")

        assert resp.status_code == 200
        data = resp.json()
        assert data["record_type"] == "order"
        assert data["reference_number"] == str(order.id)
        # Token-based responses do NOT include a new lookup_token
        assert data.get("lookup_token") is None
