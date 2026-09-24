"""VIEWER-role leak sweep for financial data and design IP.

Findings: SEC-01, SEC-09 (docs/review/2026-09-25/02-security.md) and
GDPR-03, GDPR-04, GDPR-09 (docs/review/2026-09-25/07-gdpr-privacy.md).

CLAUDE.md "Data Privacy Rules":
- Pricing, payment info, material costs -> ADMIN and GOLDSMITH only.
- Custom jewelry designs / design descriptions -> GOLDSMITH or ADMIN only.
- Insurance valuations -> exportable only by ADMIN.

Every endpoint named in those findings is listed in ``ENDPOINTS``. Each entry
is one of two kinds:

``gated``     the endpoint is financial / design IP by nature. VIEWER must get
              403; GOLDSMITH must NOT get 401/403 (no regression).
``projected`` the endpoint serves legitimate non-sensitive data to VIEWER.
              VIEWER must get 200 and the JSON body (walked recursively) must
              contain none of the entry's sensitive keys. GOLDSMITH must get
              200 and see those keys (no over-stripping for financial roles).

The valuation PDF is special-cased (GDPR-09): ADMIN only, so GOLDSMITH is
deliberately denied and ADMIN is the reverse check.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Iterator

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import (
    Customer,
    Material,
    MetalPurchase,
    MetalType,
    Order,
    OrderPhoto,
    OrderStatusEnum,
    RepairItemType,
    RepairJob,
    RepairJobStatus,
    RepairPhoto,
    RepairPhotoPhase,
    User,
)

API = "/api/v1"

# Financial keys that must never reach a VIEWER, wherever they sit in the body.
ORDER_FINANCIAL = frozenset(
    {
        "price",
        "material_cost_calculated",
        "material_cost_override",
        "labor_cost",
        "hourly_rate",
        "profit_margin_percent",
        "calculated_price",
        "unit_price",  # nested OrderRead.materials[] (GDPR-03)
    }
)
ORDER_DESIGN = frozenset({"description", "special_instructions"})
REPAIR_FINANCIAL = frozenset({"estimated_cost", "actual_cost", "estimated_value"})
MATERIAL_FINANCIAL = frozenset({"unit_price", "stock_value"})


@dataclass(frozen=True)
class Endpoint:
    name: str
    url: str  # may contain {order_id}, {repair_id}, ... placeholders
    mode: str  # "gated" | "projected"
    method: str = "GET"
    forbidden_keys: frozenset[str] = field(default_factory=frozenset)
    # Keys GOLDSMITH must still see on projected endpoints.
    goldsmith_keys: frozenset[str] = field(default_factory=frozenset)


ENDPOINTS: list[Endpoint] = [
    # ── analytics (REPORTS_VIEW was granted to VIEWER) ─────────────────────
    Endpoint("analytics_order_comparison", "/orders/{order_id}/comparison", "gated"),
    Endpoint("analytics_workshop_stats", "/analytics/workshop-stats", "gated"),
    Endpoint(
        "analytics_goldsmith_accuracy",
        "/analytics/goldsmith-accuracy/{goldsmith_id}",
        "gated",
    ),
    # ── metal inventory (purchase prices, costs) ───────────────────────────
    Endpoint("metal_purchases_list", "/metal-inventory/purchases", "gated"),
    Endpoint(
        "metal_purchase_detail", "/metal-inventory/purchases/{purchase_id}", "gated"
    ),
    Endpoint("metal_usage", "/metal-inventory/usage", "gated"),
    Endpoint("metal_statistics", "/metal-inventory/statistics", "gated"),
    Endpoint(
        "metal_allocate_preview",
        "/metal-inventory/allocate-preview"
        "?metal_type=gold_18k&required_weight_g=1&costing_method=fifo",
        "gated",
        method="POST",
    ),
    # ── materials ──────────────────────────────────────────────────────────
    Endpoint("materials_stock_value", "/materials/analytics/stock-value", "gated"),
    Endpoint(
        "materials_list",
        "/materials/",
        "projected",
        forbidden_keys=MATERIAL_FINANCIAL,
        goldsmith_keys=frozenset({"unit_price"}),
    ),
    Endpoint(
        "material_detail",
        "/materials/{material_id}",
        "projected",
        forbidden_keys=MATERIAL_FINANCIAL,
        goldsmith_keys=frozenset({"unit_price"}),
    ),
    Endpoint(
        "materials_low_stock",
        "/materials/low-stock/alert?threshold=1000000",
        "projected",
        forbidden_keys=MATERIAL_FINANCIAL,
        goldsmith_keys=frozenset({"unit_price", "stock_value"}),
    ),
    # ── customers (revenue) ────────────────────────────────────────────────
    Endpoint("customers_top_revenue", "/customers/top?by=revenue", "gated"),
    Endpoint(
        "customer_stats",
        "/customers/{customer_id}/stats",
        "projected",
        forbidden_keys=frozenset({"total_spent"}),
        goldsmith_keys=frozenset({"total_spent"}),
    ),
    # ── repairs ────────────────────────────────────────────────────────────
    Endpoint(
        "repairs_list",
        "/repairs/",
        "projected",
        forbidden_keys=REPAIR_FINANCIAL,
        goldsmith_keys=frozenset({"estimated_cost"}),
    ),
    Endpoint(
        "repair_detail",
        "/repairs/{repair_id}",
        "projected",
        forbidden_keys=REPAIR_FINANCIAL | {"photos"},
        goldsmith_keys=REPAIR_FINANCIAL | {"photos"},
    ),
    Endpoint("repair_photos_list", "/repairs/{repair_id}/photos", "gated"),
    Endpoint("repair_photo_file", "/repairs/photos/{repair_photo_id}", "gated"),
    Endpoint(
        "repair_photo_thumbnail",
        "/repairs/photos/{repair_photo_id}/thumbnail",
        "gated",
    ),
    # ── orders: design text + nested material prices ───────────────────────
    Endpoint(
        "orders_list",
        "/orders/",
        "projected",
        forbidden_keys=ORDER_FINANCIAL | ORDER_DESIGN,
        goldsmith_keys=ORDER_FINANCIAL | ORDER_DESIGN,
    ),
    Endpoint(
        "order_detail",
        "/orders/{order_id}",
        "projected",
        forbidden_keys=ORDER_FINANCIAL | ORDER_DESIGN,
        goldsmith_keys=ORDER_FINANCIAL | ORDER_DESIGN,
    ),
    # ── order photos (design IP) ───────────────────────────────────────────
    Endpoint("order_photos_list", "/orders/{order_id}/photos", "gated"),
    Endpoint("order_photo_file", "/photos/{order_photo_id}/file", "gated"),
    Endpoint("order_photo_thumbnail", "/photos/{order_photo_id}/thumbnail", "gated"),
]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


def _walk_keys(body: Any) -> Iterator[str]:
    """Yield every dict key anywhere in a JSON body."""
    if isinstance(body, dict):
        for key, value in body.items():
            yield key
            yield from _walk_keys(value)
    elif isinstance(body, list):
        for item in body:
            yield from _walk_keys(item)


def _keys_in(body: Any) -> set[str]:
    return set(_walk_keys(body))


async def _call(
    client: AsyncClient, ep: Endpoint, ids: dict[str, Any], headers: dict
) -> Any:
    url = API + ep.url.format(**ids)
    return await client.request(ep.method, url, headers=headers)


# --------------------------------------------------------------------------- #
# Seed data: every sensitive field populated with a non-null value so a
# projection that forgets a field is visible, not masked by a null.
# --------------------------------------------------------------------------- #


@pytest_asyncio.fixture
async def seeded(
    db_session: AsyncSession,
    test_customer: Customer,
    goldsmith_user: User,
) -> dict[str, Any]:
    material = Material(
        name=f"Leak-Sweep Feingold {uuid.uuid4().hex[:6]}",
        description="Feingold 999 Granulat",
        unit_price=62.5,
        stock=5.0,
        unit="g",
    )
    db_session.add(material)
    await db_session.flush()

    order = Order(
        title="Leak-Sweep Auftrag",
        description="Entwurf: Ring mit floralem Relief, CAD-Datei ring_v3.3dm",
        special_instructions="Gravur innen, Motiv streng vertraulich",
        customer_id=test_customer.id,
        status=OrderStatusEnum.COMPLETED,
        deadline=datetime.utcnow() + timedelta(days=7),
        price=1500.0,
        material_cost_calculated=400.0,
        material_cost_override=420.0,
        labor_cost=300.0,
        hourly_rate=80.0,
        profit_margin_percent=35.0,
        calculated_price=1600.0,
    )
    order.materials = [material]
    db_session.add(order)

    repair = RepairJob(
        repair_number=f"REP-{uuid.uuid4().hex[:6]}",
        bag_number=f"BAG-{uuid.uuid4().hex[:4]}",
        customer_id=test_customer.id,
        received_by=goldsmith_user.id,
        item_description="Goldkette 585, Verschluss defekt",
        item_type=RepairItemType.CHAIN,
        status=RepairJobStatus.RECEIVED,
        estimated_value=2500.0,
        estimated_cost=90.0,
        actual_cost=85.0,
    )
    db_session.add(repair)

    purchase = MetalPurchase(
        date_purchased=datetime.utcnow(),
        metal_type=MetalType.GOLD_18K,
        weight_g=50.0,
        remaining_weight_g=50.0,
        price_total=2250.0,
        price_per_gram=45.0,
        supplier="Leak-Sweep Scheideanstalt",
        invoice_number=f"LS-{uuid.uuid4().hex[:6]}",
    )
    db_session.add(purchase)
    await db_session.flush()

    order_photo = OrderPhoto(
        order_id=order.id,
        file_path="orders/leak-sweep/design.jpg",
        taken_by=goldsmith_user.id,
    )
    repair_photo = RepairPhoto(
        repair_job_id=repair.id,
        phase=RepairPhotoPhase.INTAKE,
        file_path="repairs/leak-sweep/intake.jpg",
        taken_by=goldsmith_user.id,
    )
    db_session.add_all([order_photo, repair_photo])
    await db_session.commit()

    return {
        "order_id": order.id,
        "repair_id": repair.id,
        "purchase_id": purchase.id,
        "material_id": material.id,
        "customer_id": test_customer.id,
        "goldsmith_id": goldsmith_user.id,
        "order_photo_id": order_photo.id,
        "repair_photo_id": repair_photo.id,
    }


# --------------------------------------------------------------------------- #
# VIEWER — no financial / design data
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize("ep", ENDPOINTS, ids=[e.name for e in ENDPOINTS])
async def test_viewer_gets_no_financial_or_design_data(
    ep: Endpoint,
    client: AsyncClient,
    viewer_auth_headers: dict,
    seeded: dict[str, Any],
):
    resp = await _call(client, ep, seeded, viewer_auth_headers)

    if ep.mode == "gated":
        assert resp.status_code == 403, (
            f"{ep.name}: VIEWER must be denied (403), got {resp.status_code}: "
            f"{resp.text[:300]}"
        )
        return

    assert resp.status_code == 200, f"{ep.name}: {resp.status_code} {resp.text[:300]}"
    leaked = ep.forbidden_keys & _keys_in(resp.json())
    assert not leaked, f"{ep.name}: VIEWER response leaked {sorted(leaked)}"


# --------------------------------------------------------------------------- #
# GOLDSMITH — unchanged behaviour (reverse assertion)
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
@pytest.mark.parametrize("ep", ENDPOINTS, ids=[e.name for e in ENDPOINTS])
async def test_goldsmith_keeps_access(
    ep: Endpoint,
    client: AsyncClient,
    goldsmith_auth_headers: dict,
    seeded: dict[str, Any],
):
    resp = await _call(client, ep, seeded, goldsmith_auth_headers)

    # Photo files are seeded as DB rows only (no bytes on disk), so the file
    # routes answer 404 past the permission check. 401/403 would be a
    # regression.
    assert resp.status_code not in (401, 403), (
        f"{ep.name}: GOLDSMITH was denied ({resp.status_code}): " f"{resp.text[:300]}"
    )

    if ep.mode == "projected":
        assert resp.status_code == 200, f"{ep.name}: {resp.text[:300]}"
        missing = ep.goldsmith_keys - _keys_in(resp.json())
        assert not missing, f"{ep.name}: GOLDSMITH response lost {sorted(missing)}"


# --------------------------------------------------------------------------- #
# Specific value checks that the recursive key walk cannot express
# --------------------------------------------------------------------------- #


@pytest.mark.asyncio
async def test_viewer_order_detail_keeps_operational_fields(
    client: AsyncClient, viewer_auth_headers: dict, seeded: dict[str, Any]
):
    """Projection strips sensitive keys only; VIEWER still sees the order."""
    resp = await client.get(
        f"{API}/orders/{seeded['order_id']}", headers=viewer_auth_headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    for key in ("id", "title", "status", "customer_id", "deadline"):
        assert key in body, f"over-stripped: {key} missing"
    # Nested materials keep their identity, lose their price.
    assert body["materials"], "materials list should still be present"
    assert body["materials"][0]["id"] == seeded["material_id"]


@pytest.mark.asyncio
async def test_viewer_repair_detail_keeps_status_fields(
    client: AsyncClient, viewer_auth_headers: dict, seeded: dict[str, Any]
):
    resp = await client.get(
        f"{API}/repairs/{seeded['repair_id']}", headers=viewer_auth_headers
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    for key in ("id", "repair_number", "bag_number", "status", "item_description"):
        assert key in body, f"over-stripped: {key} missing"


@pytest.mark.asyncio
async def test_viewer_customers_top_by_orders_still_allowed(
    client: AsyncClient, viewer_auth_headers: dict, seeded: dict[str, Any]
):
    """Only the revenue ranking is financial; order-count ranking is not."""
    resp = await client.get(
        f"{API}/customers/top?by=orders", headers=viewer_auth_headers
    )
    assert resp.status_code == 200, resp.text


# --------------------------------------------------------------------------- #
# GDPR-09 — valuation PDF export is ADMIN only
# --------------------------------------------------------------------------- #


@pytest_asyncio.fixture
async def valuation_id(
    client: AsyncClient,
    admin_auth_headers: dict,
    seeded: dict[str, Any],
) -> int:
    resp = await client.post(
        f"{API}/valuations",
        json={
            "order_id": seeded["order_id"],
            "customer_id": seeded["customer_id"],
            "item_description": "Brillantring 750 Gelbgold",
            "metal_type": "Gelbgold 750 (18K)",
            "metal_weight_g": 4.8,
            "metal_purity": "750",
            "appraised_value": 3500.00,
            "goldsmith_name": "Leak Sweep",
            "goldsmith_qualification": "Goldschmiedemeisterin",
        },
        headers=admin_auth_headers,
    )
    assert resp.status_code == 201, resp.text
    return int(resp.json()["id"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "role, expected_denied",
    [("viewer", True), ("goldsmith", True), ("admin", False)],
)
async def test_valuation_pdf_is_admin_only(
    role: str,
    expected_denied: bool,
    client: AsyncClient,
    viewer_auth_headers: dict,
    goldsmith_auth_headers: dict,
    admin_auth_headers: dict,
    valuation_id: int,
):
    headers = {
        "viewer": viewer_auth_headers,
        "goldsmith": goldsmith_auth_headers,
        "admin": admin_auth_headers,
    }[role]
    resp = await client.get(f"{API}/valuations/{valuation_id}/pdf", headers=headers)
    if expected_denied:
        assert resp.status_code == 403, resp.text[:300]
    else:
        assert resp.status_code == 200, resp.text[:300]
        assert "application/pdf" in resp.headers.get("content-type", "")
