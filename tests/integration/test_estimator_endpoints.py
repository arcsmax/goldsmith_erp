"""
Integration tests for the V1.3 statistical labor estimator endpoints
(Phase 1, Task 5): ``POST /api/v1/estimates/labor`` and
``GET /api/v1/estimates/accuracy``.

Covers:
- POST /estimates/labor as GOLDSMITH -> 200 with a p50 hours + labor cost.
- POST /estimates/labor as VIEWER -> 403 (financial/pricing data).
- GET /estimates/accuracy as ADMIN -> 200 with a calibration payload.
- GET /estimates/accuracy as VIEWER -> 403.
- A DB-backed CustomerAuditLog row is written for both a financial POST
  (router-level write_financial_audit_row) and a financial GET
  (AuditLoggingMiddleware's `_RESOURCE_ROUTES["estimates"]` entry) — same
  audit mechanism exercised by TestFinancialAuditRows in
  test_customer_updates.py.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import (
    Activity,
    CustomerAuditLog,
    Gemstone,
    Order,
    OrderStatusEnum,
    TimeEntry,
    User,
)


# ---------------------------------------------------------------------------
# Fixture: redirect the middleware's AsyncSessionLocal at the test DB factory
# ---------------------------------------------------------------------------
#
# BaseHTTPMiddleware cannot consume FastAPI's ``Depends(get_db)``, so
# AuditLoggingMiddleware opens its own ``AsyncSessionLocal()`` — which
# defaults to production Postgres, not this test's SQLite/engine. Patch it
# to the conftest's session factory for the duration of each test, same as
# test_financial_audit.py / test_audit_logging_middleware.py, so the GET
# /estimates/accuracy audit row (written via the middleware, not the
# router) lands in the DB `db_session` reads from.
@pytest.fixture(autouse=True)
def _patch_middleware_session(monkeypatch, db_session: AsyncSession):
    from sqlalchemy.orm import sessionmaker

    from goldsmith_erp.middleware import audit_logging

    factory = sessionmaker(
        bind=db_session.bind, class_=AsyncSession, expire_on_commit=False
    )
    monkeypatch.setattr(audit_logging, "AsyncSessionLocal", factory)


def _make_order(customer_id: int, **overrides) -> Order:
    defaults = dict(
        title="Estimator Endpoint Test Order",
        customer_id=customer_id,
        status=OrderStatusEnum.COMPLETED,
        order_type="ring",
        finish_type="high_polish",
        complexity_rating=3,
        alloy="585",
        completed_at=datetime.utcnow(),
    )
    defaults.update(overrides)
    return Order(**defaults)


def _make_entry(
    order_id: int, user_id: int, activity_id: int, duration_minutes: int
) -> TimeEntry:
    start_time = datetime.utcnow() - timedelta(minutes=duration_minutes)
    return TimeEntry(
        id=str(uuid.uuid4()),
        order_id=order_id,
        user_id=user_id,
        activity_id=activity_id,
        start_time=start_time,
        end_time=start_time + timedelta(minutes=duration_minutes),
        duration_minutes=duration_minutes,
    )


@pytest_asyncio.fixture
async def rated_activity(db_session: AsyncSession) -> Activity:
    activity = Activity(
        name="Polieren",
        category="fabrication",
        is_billable=True,
        is_custom=False,
        hourly_rate=Decimal("80.00"),
        created_at=datetime.utcnow(),
    )
    db_session.add(activity)
    await db_session.commit()
    await db_session.refresh(activity)
    return activity


@pytest_asyncio.fixture
async def seeded_ring_corpus(
    db_session: AsyncSession,
    test_customer,
    goldsmith_user: User,
    rated_activity: Activity,
):
    """5 completed 'ring'/'high_polish'/stone-setting orders with billable
    time entries of 2/4/6/8/10 hours -- enough to clear MIN_SAMPLE=5 at
    the most specific ("exact") similarity tier."""
    orders = []
    for hours in (2, 4, 6, 8, 10):
        order = _make_order(test_customer.id)
        db_session.add(order)
        await db_session.commit()
        await db_session.refresh(order)
        db_session.add(
            _make_entry(order.id, goldsmith_user.id, rated_activity.id, int(hours * 60))
        )
        db_session.add(
            Gemstone(
                order_id=order.id, type="diamond", carat=0.3, cost=100.0, quantity=1
            )
        )
        await db_session.commit()
        orders.append(order)
    return orders


# ---------------------------------------------------------------------------
# POST /estimates/labor
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestPostLaborEstimate:
    async def test_goldsmith_gets_200_with_p50(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        seeded_ring_corpus,
    ):
        resp = await client.post(
            "/api/v1/estimates/labor",
            json={
                "order_type": "ring",
                "finish_type": "high_polish",
                "has_stone_setting": True,
            },
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["insufficient_data"] is False
        # The 2h order falls below the tier's P10 corpus-exclusion
        # threshold (Task 3) and is dropped, leaving 4 orders: median=7.0.
        assert body["hours_p50"] == pytest.approx(7.0)
        assert body["labor_cost_p50"] == pytest.approx(560.0)
        assert body["sample_size"] == 4
        # Raw hourly_rate must never be exposed on this response.
        assert "hourly_rate" not in body

    async def test_viewer_gets_403(
        self,
        client: AsyncClient,
        viewer_auth_headers: dict,
        seeded_ring_corpus,
    ):
        resp = await client.post(
            "/api/v1/estimates/labor",
            json={"order_type": "ring"},
            headers=viewer_auth_headers,
        )
        assert resp.status_code == 403

    async def test_unauthenticated_is_rejected(self, client: AsyncClient):
        resp = await client.post("/api/v1/estimates/labor", json={"order_type": "ring"})
        assert resp.status_code in (401, 403)

    async def test_insufficient_data_returns_null_numbers(
        self, client: AsyncClient, goldsmith_auth_headers: dict
    ):
        """No seeded corpus at all for this order_type -> honest nulls,
        not a fabricated estimate."""
        resp = await client.post(
            "/api/v1/estimates/labor",
            json={"order_type": "unseen_order_type_xyz"},
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["insufficient_data"] is True
        assert body["hours_p50"] is None
        assert body["labor_cost_p50"] is None


# ---------------------------------------------------------------------------
# GET /estimates/accuracy
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetEstimateAccuracy:
    async def test_admin_gets_200(self, client: AsyncClient, admin_auth_headers: dict):
        resp = await client.get(
            "/api/v1/estimates/accuracy", headers=admin_auth_headers
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "mape" in body
        assert "bias_by_order_type" in body
        assert body["rows_loaded"] == 0

    async def test_viewer_gets_403(
        self, client: AsyncClient, viewer_auth_headers: dict
    ):
        resp = await client.get(
            "/api/v1/estimates/accuracy", headers=viewer_auth_headers
        )
        assert resp.status_code == 403

    async def test_goldsmith_gets_200(
        self, client: AsyncClient, goldsmith_auth_headers: dict
    ):
        resp = await client.get(
            "/api/v1/estimates/accuracy", headers=goldsmith_auth_headers
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# DB-backed financial audit rows (same mechanism as
# TestFinancialAuditRows in test_customer_updates.py)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestFinancialAuditRows:
    async def test_post_labor_estimate_writes_audit_row(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        goldsmith_user: User,
        db_session: AsyncSession,
    ):
        """POST /estimates/labor is a non-GET on a financial family, which
        AuditLoggingMiddleware structurally skips -- the router writes its
        own CustomerAuditLog row via write_financial_audit_row."""
        resp = await client.post(
            "/api/v1/estimates/labor",
            json={"order_type": "ring"},
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 200

        rows = (
            (
                await db_session.execute(
                    select(CustomerAuditLog).where(
                        CustomerAuditLog.entity == "labor_estimate",
                        CustomerAuditLog.action == "financial_read",
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
        assert rows[0].details["http_method"] == "POST"

    async def test_get_accuracy_writes_audit_row_via_middleware(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        db_session: AsyncSession,
    ):
        """GET /estimates/accuracy is audited by AuditLoggingMiddleware's
        `_RESOURCE_ROUTES["estimates"]` entry (list_accessed_financial —
        no numeric id in the path)."""
        resp = await client.get(
            "/api/v1/estimates/accuracy", headers=admin_auth_headers
        )
        assert resp.status_code == 200

        rows = (
            (
                await db_session.execute(
                    select(CustomerAuditLog).where(
                        CustomerAuditLog.entity == "estimate",
                        CustomerAuditLog.action == "list_accessed_financial",
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(rows) == 1
