"""
Integration test for Bug #7 — GET /api/v1/materials/ must accept materials
with ``unit_price == 0`` (legitimate for tools / equipment that don't have
a per-use cost).

Pre-fix the Pydantic ``MaterialRead`` schema declared
``unit_price: float = Field(gt=0, ...)``. The seeder creates a tool record
("Graviermaschine Spezial") with ``unit_price=0.0`` because tools have no
per-use price — the strict ``gt=0`` validator then rejected serialisation
and the list endpoint returned 500 with ``ResponseValidationError``.

Post-fix expectation:
    * ``unit_price`` accepts ``>= 0`` on read (zero is fine; negative isn't).
    * ``GET /api/v1/materials/`` returns 200 even when the list contains
      a material with ``unit_price == 0``.
    * Negative prices are still rejected (data-integrity floor).
"""
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from goldsmith_erp.db.models import Material as MaterialModel

pytestmark = pytest.mark.asyncio


MATERIALS_PATH = "/api/v1/materials/"


async def _bypass_cache_fetch(key, ttl, fetch_fn, **_kw):
    """Skip Redis entirely; always go to the DB.

    The integration suite shares a real Redis instance with the running
    dev stack — without bypassing the cache, ``materials:list`` returns
    a stale snapshot from the dev Postgres DB instead of the per-test
    SQLite session.
    """
    return await fetch_fn()


@pytest.fixture
def bypass_materials_cache():
    """Patch the materials service's `get_cached` to skip Redis."""
    with patch(
        "goldsmith_erp.services.material_service.get_cached",
        new=AsyncMock(side_effect=_bypass_cache_fetch),
    ):
        yield


async def _seed_zero_price_tool(db_session) -> MaterialModel:
    """Insert a tool-style material with ``unit_price=0`` directly into the DB."""
    tool = MaterialModel(
        name="Graviermaschine Spezial (test)",
        description="Tool — no per-use cost",
        unit_price=0.0,
        stock=1.0,
        unit="pcs",
        min_stock=1.0,
    )
    db_session.add(tool)
    await db_session.commit()
    await db_session.refresh(tool)
    return tool


class TestMaterialsListZeroPrice:
    """``GET /materials/`` must tolerate ``unit_price=0`` on tool records."""

    async def test_list_returns_200_when_tool_has_zero_price(
        self,
        bypass_materials_cache,
        authenticated_client: AsyncClient,
        db_session,
    ):
        """Pre-fix: response validator rejects unit_price=0.0 (gt=0) → 500.
        Post-fix: list returns 200 and includes the tool record."""
        await _seed_zero_price_tool(db_session)

        resp = await authenticated_client.get(MATERIALS_PATH)

        assert resp.status_code == 200, (
            f"Expected 200 (zero-price tool tolerated), got "
            f"{resp.status_code}: {resp.text}"
        )

    async def test_zero_price_tool_appears_in_response(
        self,
        bypass_materials_cache,
        authenticated_client: AsyncClient,
        db_session,
    ):
        tool = await _seed_zero_price_tool(db_session)

        resp = await authenticated_client.get(MATERIALS_PATH)
        assert resp.status_code == 200
        payload = resp.json()

        names = {m["name"] for m in payload}
        assert tool.name in names, (
            f"Zero-price tool not in response: {payload}"
        )

        # Find the tool entry and assert its unit_price is exactly 0.0.
        tool_entry = next(m for m in payload if m["name"] == tool.name)
        assert tool_entry["unit_price"] == 0.0
