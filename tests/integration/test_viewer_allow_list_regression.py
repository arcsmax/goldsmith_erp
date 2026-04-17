"""VIEWER allow-list regression test (Slice 6 / R9).

Purpose
-------
Assert that ``POST /api/v1/scan/resolve`` returns an ``entity`` dict
whose key set is EXACTLY the ``*_FIELDS_BY_ROLE[VIEWER]`` allow-list
for every scannable entity type. This is the R9 mitigation: if an
ORM column is added without updating the allow-list, this test
breaks and the offending key leaks to the VIEWER role.

Why assertEqual, not assertNotIn
--------------------------------
A deny-list style check (``assert 'price' not in keys``) would miss
newly-introduced sensitive columns. An exact-set assertion
(``assertEqual(set(keys), expected)``) fails the moment the ORM
grows a new column the developer forgot to classify. This is the
test's entire reason to exist.

Entity coverage
---------------
  * order          — ORDER_FIELDS_VIEWER         {id, status, deadline}
  * repair         — REPAIR_FIELDS_VIEWER        {id, repair_number,
                                                   bag_number, status,
                                                   estimated_completion_date}
  * metal_purchase — METAL_FIELDS_VIEWER         frozenset()  (empty — no access)
  * material       — MATERIAL_FIELDS_VIEWER      {id, name, unit,
                                                   stock, min_stock}

Related tests that each cover a facet — this file closes the
cross-entity gap.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import (
    Material,
    MetalPurchase,
    MetalType,
    Order,
    OrderStatusEnum,
    RepairItemType,
    RepairJob,
    RepairJobStatus,
)
from goldsmith_erp.services.scanner_service import (
    MATERIAL_FIELDS_VIEWER,
    METAL_FIELDS_VIEWER,
    ORDER_FIELDS_VIEWER,
    REPAIR_FIELDS_VIEWER,
)


RESOLVE_URL = "/api/v1/scan/resolve"


# --------------------------------------------------------------------------- #
# Fixtures — one entity of each scannable type
# --------------------------------------------------------------------------- #


@pytest_asyncio.fixture
async def regression_order(db_session: AsyncSession, test_customer) -> Order:
    order = Order(
        title="R9 Regression Order",
        description="exact-key-set VIEWER assertion",
        customer_id=test_customer.id,
        status=OrderStatusEnum.IN_PROGRESS,
        alloy="750",
        price=1234.56,
        deadline=datetime.utcnow() + timedelta(days=14),
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)
    return order


@pytest_asyncio.fixture
async def regression_repair(db_session: AsyncSession, test_customer) -> RepairJob:
    repair = RepairJob(
        repair_number=f"REP-2026-{uuid.uuid4().hex[:4].upper()}",
        bag_number=f"BAG-{uuid.uuid4().hex[:4].upper()}",
        customer_id=test_customer.id,
        item_description="Kettchen gerissen",
        item_type=RepairItemType.CHAIN,
        metal_type="585 Gelbgold",
        estimated_value=150.0,
        status=RepairJobStatus.RECEIVED,
        diagnosis_notes="loeten",
        estimated_cost=35.0,
        estimated_completion_date=datetime.utcnow() + timedelta(days=7),
    )
    db_session.add(repair)
    await db_session.commit()
    await db_session.refresh(repair)
    return repair


@pytest_asyncio.fixture
async def regression_metal_purchase(db_session: AsyncSession) -> MetalPurchase:
    purchase = MetalPurchase(
        date_purchased=datetime.utcnow(),
        metal_type=MetalType.GOLD_18K,
        weight_g=100.0,
        remaining_weight_g=100.0,
        price_total=4500.00,
        price_per_gram=45.00,
        supplier="R9 Supplier",
        lot_number=f"R9-LOT-{uuid.uuid4().hex[:4].upper()}",
    )
    db_session.add(purchase)
    await db_session.commit()
    await db_session.refresh(purchase)
    return purchase


@pytest_asyncio.fixture
async def regression_material(db_session: AsyncSession) -> Material:
    material = Material(
        name=f"R9 Material {uuid.uuid4().hex[:4]}",
        description="R9 regression material",
        unit_price=12.50,
        stock=200.0,
        min_stock=50.0,
        unit="g",
    )
    db_session.add(material)
    await db_session.commit()
    await db_session.refresh(material)
    return material


# --------------------------------------------------------------------------- #
# ORDER — VIEWER projection
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
class TestViewerOrderAllowList:
    async def test_viewer_order_exact_key_set(
        self,
        client: AsyncClient,
        viewer_auth_headers: dict,
        regression_order: Order,
    ):
        resp = await client.post(
            RESOLVE_URL,
            json={"raw_payload": f"ORDER:{regression_order.id}"},
            headers=viewer_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["resolved"] is True
        assert body["entity_type"] == "order"

        actual = set(body["entity"].keys())
        expected = set(ORDER_FIELDS_VIEWER)
        # R9 core assertion — exact match, not subset.
        assert actual == expected, (
            f"VIEWER order projection drift. "
            f"Extra: {actual - expected}. Missing: {expected - actual}. "
            f"If you added a new Order column, update "
            f"ORDER_FIELDS_BY_ROLE in scanner_service.py."
        )


# --------------------------------------------------------------------------- #
# REPAIR — VIEWER projection
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
class TestViewerRepairAllowList:
    async def test_viewer_repair_exact_key_set(
        self,
        client: AsyncClient,
        viewer_auth_headers: dict,
        regression_repair: RepairJob,
    ):
        resp = await client.post(
            RESOLVE_URL,
            json={"raw_payload": f"REPAIR:{regression_repair.id}"},
            headers=viewer_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["resolved"] is True
        assert body["entity_type"] == "repair"

        actual = set(body["entity"].keys())
        expected = set(REPAIR_FIELDS_VIEWER)
        assert actual == expected, (
            f"VIEWER repair projection drift. "
            f"Extra: {actual - expected}. Missing: {expected - actual}. "
            f"If you added a new RepairJob column, update "
            f"REPAIR_FIELDS_BY_ROLE in scanner_service.py."
        )


# --------------------------------------------------------------------------- #
# METAL — VIEWER has ZERO access (deliberately empty allow-list)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
class TestViewerMetalAllowList:
    async def test_viewer_metal_exact_empty_projection(
        self,
        client: AsyncClient,
        viewer_auth_headers: dict,
        regression_metal_purchase: MetalPurchase,
    ):
        """METAL is a financial entity — VIEWER allow-list is ``frozenset()``.
        The endpoint must still return ``resolved=True`` so the UI
        can render a "kein Zugriff" hint, but ``entity`` must be {}."""
        resp = await client.post(
            RESOLVE_URL,
            json={"raw_payload": f"METAL:{regression_metal_purchase.id}"},
            headers=viewer_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["entity_type"] == "metal_purchase"

        actual = set(body["entity"].keys())
        expected = set(METAL_FIELDS_VIEWER)  # frozenset() — empty
        assert actual == expected == set(), (
            f"VIEWER metal projection must be empty (financial lockout). "
            f"Got: {actual}. If METAL_FIELDS_VIEWER is no longer empty, "
            f"revisit the CLAUDE.md Data Privacy Rules — financial data "
            f"is ADMIN/GOLDSMITH only."
        )


# --------------------------------------------------------------------------- #
# MATERIAL — VIEWER projection
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
class TestViewerMaterialAllowList:
    async def test_viewer_material_exact_key_set(
        self,
        client: AsyncClient,
        viewer_auth_headers: dict,
        regression_material: Material,
    ):
        resp = await client.post(
            RESOLVE_URL,
            json={"raw_payload": f"MATERIAL:{regression_material.id}"},
            headers=viewer_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["resolved"] is True
        assert body["entity_type"] == "material"

        actual = set(body["entity"].keys())
        expected = set(MATERIAL_FIELDS_VIEWER)
        assert actual == expected, (
            f"VIEWER material projection drift. "
            f"Extra: {actual - expected}. Missing: {expected - actual}. "
            f"If you added a new Material column, update "
            f"MATERIAL_FIELDS_BY_ROLE in scanner_service.py. Be "
            f"especially careful with pricing fields."
        )


# --------------------------------------------------------------------------- #
# Cross-entity sweep — summary assertion
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
class TestViewerAllowListCrossEntitySweep:
    """Belt-and-braces: loops through all four entity types in one
    test so a single assertion failure surface flags the regression
    clearly. Duplicates the per-entity assertions above intentionally
    — this is the test that CI will most visibly fail on drift."""

    async def test_all_entities_viewer_projection_equals_allow_list(
        self,
        client: AsyncClient,
        viewer_auth_headers: dict,
        regression_order: Order,
        regression_repair: RepairJob,
        regression_metal_purchase: MetalPurchase,
        regression_material: Material,
    ):
        cases = [
            (
                f"ORDER:{regression_order.id}",
                "order",
                set(ORDER_FIELDS_VIEWER),
            ),
            (
                f"REPAIR:{regression_repair.id}",
                "repair",
                set(REPAIR_FIELDS_VIEWER),
            ),
            (
                f"METAL:{regression_metal_purchase.id}",
                "metal_purchase",
                set(METAL_FIELDS_VIEWER),
            ),
            (
                f"MATERIAL:{regression_material.id}",
                "material",
                set(MATERIAL_FIELDS_VIEWER),
            ),
        ]
        drift: list[str] = []
        for raw_payload, entity_type, expected in cases:
            resp = await client.post(
                RESOLVE_URL,
                json={"raw_payload": raw_payload},
                headers=viewer_auth_headers,
            )
            assert resp.status_code == 200, f"{raw_payload}: {resp.text}"
            body = resp.json()
            # METAL for VIEWER has empty allow-list but H13 guards drop the
            # projection in an empty state — still resolved=True.
            assert body["entity_type"] == entity_type
            actual = set((body["entity"] or {}).keys())
            if actual != expected:
                drift.append(
                    f"{entity_type}: extra={actual - expected}, "
                    f"missing={expected - actual}"
                )
        assert not drift, (
            "VIEWER allow-list drift detected — a new ORM column leaked "
            "past the scanner projection. Update "
            "*_FIELDS_BY_ROLE[VIEWER] in scanner_service.py. Drift: "
            + "; ".join(drift)
        )
