"""Integration tests for the V1.1 scanner HTTP surface (Slice 4).

Endpoint coverage:
  POST /api/v1/scan/resolve       — role-filtered entity resolution
  POST /api/v1/scan/log           — single scan log with idempotency dedupe
  POST /api/v1/scan/log/batch     — up to 100 events, per-row dedupe
  GET  /api/v1/scan/search        — multi-entity role-filtered search

Test matrix (≥ 20 tests):

  Authentication
    * Unauthenticated resolve     → 401
    * Unauthenticated search      → 401
    * Unauthenticated log         → 401

  Role-based (allow-list, not deny-list — Anna A3.3):
    * ADMIN ORDER:1 resolve       → exact key set from ADMIN allow-list
    * GOLDSMITH ORDER:1 resolve   → exact GOLDSMITH key set
    * VIEWER ORDER:1 resolve      → exact VIEWER key set
    * VIEWER search metal_purchase → [] even when matches exist
    * VIEWER search order         → non-financial results only

  Validation
    * body.user_id smuggle        → 422 (StrictRequestBase)
    * Malformed Idempotency-Key   → 400
    * X-Client-Created-At 40d old → 400
    * raw_payload > 500 chars     → 422
    * raw_payload contains \\x00   → 422
    * log/batch 101 events        → 422
    * search q too short          → 422
    * search types empty          → 400
    * search types unknown        → 400

  Happy path + idempotency
    * POST /log twice same key    → both return same row (dedupe)
    * POST /log/batch mixed keys  → correct ingested / deduplicated counts
"""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import (
    MetalPurchase,
    MetalType,
    Order,
    OrderStatusEnum,
)
from goldsmith_erp.services.scanner_service import (
    METAL_FIELDS_GOLDSMITH,
    ORDER_FIELDS_ADMIN,
    ORDER_FIELDS_GOLDSMITH,
    ORDER_FIELDS_VIEWER,
)


RESOLVE_URL = "/api/v1/scan/resolve"
LOG_URL = "/api/v1/scan/log"
BATCH_URL = "/api/v1/scan/log/batch"
SEARCH_URL = "/api/v1/scan/search"


# --------------------------------------------------------------------------- #
# Fixtures specific to the scanner test suite
# --------------------------------------------------------------------------- #


@pytest_asyncio.fixture
async def resolve_order(db_session: AsyncSession, test_customer):
    """Order 'Maria Trauring' fixture — shared by resolve + search tests.

    Deliberately sets ``alloy='750'`` so that the Punzierungs-Check
    allow-list test has a realistic input; the router test does not
    depend on status.
    """
    order = Order(
        title="Maria Trauring",
        description="18K Gold Trauring",
        customer_id=test_customer.id,
        status=OrderStatusEnum.IN_PROGRESS,
        alloy="750",
        price=999.00,
    )
    db_session.add(order)
    await db_session.commit()
    await db_session.refresh(order)
    return order


@pytest_asyncio.fixture
async def rein_metal_purchase(db_session: AsyncSession):
    """Metal lot containing the substring 'REIN' in its lot_number.

    Used by the VIEWER-search-financial-lockout test. Substring match
    is how ``_search_metal`` looks up rows.
    """
    purchase = MetalPurchase(
        date_purchased=datetime.utcnow(),
        metal_type=MetalType.GOLD_18K,
        weight_g=100.0,
        remaining_weight_g=100.0,
        price_total=4500.00,
        price_per_gram=45.00,
        supplier="REIN Supplier",
        lot_number="REIN-LOT-2026-001",
    )
    db_session.add(purchase)
    await db_session.commit()
    await db_session.refresh(purchase)
    return purchase


def _new_uuid4_key() -> str:
    """Fresh UUIDv4 as a string — matches the Idempotency-Key contract."""
    return str(uuid.uuid4())


def _minimal_scan_log_body(raw_payload: str = "ORDER:1") -> dict:
    """Minimum valid ScanLogCreate body for POST /scan/log."""
    return {
        "raw_payload": raw_payload,
        "offline_queued": False,
    }


# --------------------------------------------------------------------------- #
# Authentication gate
# --------------------------------------------------------------------------- #


class TestAuthentication:
    """The global AuthRequiredMiddleware returns 401 on any /scan/* path."""

    @pytest.mark.asyncio
    async def test_resolve_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.post(RESOLVE_URL, json={"raw_payload": "ORDER:1"})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_log_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.post(LOG_URL, json=_minimal_scan_log_body())
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_search_unauthenticated_returns_401(self, client: AsyncClient):
        resp = await client.get(SEARCH_URL, params={"q": "test", "types": "order"})
        assert resp.status_code == 401


# --------------------------------------------------------------------------- #
# Role-based resolve — allow-list projection (Anna A3.3)
# --------------------------------------------------------------------------- #


class TestResolveRoleProjection:
    """Router returns a projection whose keys EXACTLY match the role's allow
    set — a deny-list would silently leak on new-column drift.
    """

    @pytest.mark.asyncio
    async def test_admin_sees_full_order_projection(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        resolve_order: Order,
    ):
        resp = await client.post(
            RESOLVE_URL,
            json={"raw_payload": f"ORDER:{resolve_order.id}"},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["resolved"] is True
        assert body["entity_type"] == "order"
        # ADMIN receives the full allow-list projection.
        actual_keys = set(body["entity"].keys())
        assert actual_keys == set(ORDER_FIELDS_ADMIN)

    @pytest.mark.asyncio
    async def test_goldsmith_sees_goldsmith_order_projection(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        resolve_order: Order,
    ):
        resp = await client.post(
            RESOLVE_URL,
            json={"raw_payload": f"ORDER:{resolve_order.id}"},
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        actual_keys = set(body["entity"].keys())
        # Exact-match on the GOLDSMITH allow-list — financial fields ABSENT,
        # production fields PRESENT.
        assert actual_keys == set(ORDER_FIELDS_GOLDSMITH)
        assert "price" not in actual_keys
        assert "material_cost_calculated" not in actual_keys

    @pytest.mark.asyncio
    async def test_viewer_sees_only_viewer_order_projection(
        self,
        client: AsyncClient,
        viewer_auth_headers: dict,
        resolve_order: Order,
    ):
        resp = await client.post(
            RESOLVE_URL,
            json={"raw_payload": f"ORDER:{resolve_order.id}"},
            headers=viewer_auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        actual_keys = set(body["entity"].keys())
        # The allow-list is the contract — assertEqual (Anna A3.3).
        assert actual_keys == set(ORDER_FIELDS_VIEWER)
        # Double-guard the two most dangerous leaks.
        assert "price" not in actual_keys
        assert "customer_id" not in actual_keys

    @pytest.mark.asyncio
    async def test_viewer_metal_purchase_projection_is_empty(
        self,
        client: AsyncClient,
        viewer_auth_headers: dict,
        rein_metal_purchase: MetalPurchase,
    ):
        """VIEWER on METAL:<id> — financial entity, all fields locked out.

        Service returns ``resolved=True`` + empty entity dict so the UI
        can render "kein Zugriff" rather than the unknown-code modal.
        """
        resp = await client.post(
            RESOLVE_URL,
            json={"raw_payload": f"METAL:{rein_metal_purchase.id}"},
            headers=viewer_auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["resolved"] is True
        assert body["entity_type"] == "metal_purchase"
        assert body["entity"] == {}

    @pytest.mark.asyncio
    async def test_goldsmith_metal_purchase_projection_is_non_empty(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        rein_metal_purchase: MetalPurchase,
    ):
        """GOLDSMITH gets inventory-relevant fields but NOT pricing."""
        resp = await client.post(
            RESOLVE_URL,
            json={"raw_payload": f"METAL:{rein_metal_purchase.id}"},
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        actual_keys = set(body["entity"].keys())
        assert actual_keys == set(METAL_FIELDS_GOLDSMITH)
        # Price must never leak to goldsmith.
        assert "price_total" not in actual_keys
        assert "price_per_gram" not in actual_keys


# --------------------------------------------------------------------------- #
# Search — role-based filtering + query validation
# --------------------------------------------------------------------------- #


class TestSearch:

    @pytest.mark.asyncio
    async def test_viewer_metal_search_returns_empty_list(
        self,
        client: AsyncClient,
        viewer_auth_headers: dict,
        rein_metal_purchase: MetalPurchase,
    ):
        """Even with a matching lot, VIEWER cannot search metal_purchase."""
        resp = await client.get(
            SEARCH_URL,
            params={"q": "REIN", "types": "metal_purchase"},
            headers=viewer_auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_viewer_order_search_returns_results(
        self,
        client: AsyncClient,
        viewer_auth_headers: dict,
        resolve_order: Order,
    ):
        """VIEWER CAN search orders; row projection strips financial fields."""
        resp = await client.get(
            SEARCH_URL,
            params={"q": "Maria", "types": "order"},
            headers=viewer_auth_headers,
        )
        assert resp.status_code == 200
        results = resp.json()
        assert len(results) >= 1
        hit = next(r for r in results if r.get("id") == resolve_order.id)
        # Every result row carries a `type` discriminator + VIEWER projection.
        assert hit["type"] == "order"
        actual_keys = set(hit.keys()) - {"type"}
        assert actual_keys == set(ORDER_FIELDS_VIEWER)

    @pytest.mark.asyncio
    async def test_admin_search_metal_returns_results(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        rein_metal_purchase: MetalPurchase,
    ):
        """ADMIN sees financial metal purchase fields in search results."""
        resp = await client.get(
            SEARCH_URL,
            params={"q": "REIN", "types": "metal_purchase"},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 200
        results = resp.json()
        assert any(r.get("id") == rein_metal_purchase.id for r in results)
        hit = next(r for r in results if r.get("id") == rein_metal_purchase.id)
        assert "price_per_gram" in hit  # admin-only field

    @pytest.mark.asyncio
    async def test_search_query_too_short_returns_422(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
    ):
        """Query min_length=2 — single char should 422."""
        resp = await client.get(
            SEARCH_URL,
            params={"q": "a", "types": "order"},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_search_types_empty_string_returns_400(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
    ):
        """types='' → router-level 400 (not a Pydantic 422)."""
        resp = await client.get(
            SEARCH_URL,
            params={"q": "test", "types": ""},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_search_types_unknown_returns_400(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
    ):
        """Unknown entity type → 400 with 'Unknown entity type(s)' message."""
        resp = await client.get(
            SEARCH_URL,
            params={"q": "test", "types": "customer"},
            headers=admin_auth_headers,
        )
        assert resp.status_code == 400
        assert "Unknown entity type" in resp.json()["detail"]


# --------------------------------------------------------------------------- #
# Request validation — StrictRequestBase + header + payload constraints
# --------------------------------------------------------------------------- #


class TestValidation:

    @pytest.mark.asyncio
    async def test_log_body_user_id_smuggle_rejected(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
    ):
        """user_id in body — StrictRequestBase rejects at the Pydantic layer."""
        body = _minimal_scan_log_body()
        body["user_id"] = 999  # attempted spoof
        resp = await client.post(LOG_URL, json=body, headers=goldsmith_auth_headers)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_log_malformed_idempotency_key_header_returns_400(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
    ):
        """Idempotency-Key header must be a UUIDv4 — bad shape → 400."""
        headers = {
            **goldsmith_auth_headers,
            "Idempotency-Key": "not-a-uuid",
        }
        resp = await client.post(LOG_URL, json=_minimal_scan_log_body(), headers=headers)
        assert resp.status_code == 400
        assert "Idempotency-Key" in resp.json()["detail"]

    @pytest.mark.asyncio
    async def test_log_x_client_created_at_40_days_old_returns_400(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
    ):
        """X-Client-Created-At older than 30 days rejected by idempotency dep."""
        old = datetime.now(tz=timezone.utc) - timedelta(days=40)
        headers = {
            **goldsmith_auth_headers,
            "X-Client-Created-At": old.isoformat(),
        }
        resp = await client.post(LOG_URL, json=_minimal_scan_log_body(), headers=headers)
        assert resp.status_code == 400

    @pytest.mark.asyncio
    async def test_log_raw_payload_over_500_chars_returns_422(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
    ):
        """Field max_length=500 on raw_payload."""
        body = _minimal_scan_log_body("A" * 501)
        resp = await client.post(LOG_URL, json=body, headers=goldsmith_auth_headers)
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_resolve_null_byte_in_payload_returns_422(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
    ):
        """NUL byte in raw_payload — rejected by the field validator."""
        resp = await client.post(
            RESOLVE_URL,
            json={"raw_payload": "ORDER:\x001"},
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_log_batch_101_events_returns_422(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
    ):
        """Batch upper bound is 100; 101 trips max_length."""
        events = [_minimal_scan_log_body(f"ORDER:{i}") for i in range(1, 102)]
        resp = await client.post(
            BATCH_URL,
            json={"events": events},
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 422


# --------------------------------------------------------------------------- #
# Happy paths: resolve, log, idempotency, batch
# --------------------------------------------------------------------------- #


class TestHappyPathAndIdempotency:

    @pytest.mark.asyncio
    async def test_resolve_valid_order_returns_200(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        resolve_order: Order,
    ):
        resp = await client.post(
            RESOLVE_URL,
            json={"raw_payload": f"ORDER:{resolve_order.id}"},
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["resolved"] is True
        assert body["entity_type"] == "order"
        assert body["entity_id"] == resolve_order.id
        assert isinstance(body["actions"], list)
        assert len(body["actions"]) > 0

    @pytest.mark.asyncio
    async def test_resolve_numeric_fallback_resolves_to_order(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        resolve_order: Order,
    ):
        """A purely numeric payload maps to ORDER:<n>."""
        resp = await client.post(
            RESOLVE_URL,
            json={"raw_payload": str(resolve_order.id)},
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["resolved"] is True
        assert body["entity_type"] == "order"
        assert body["resolution_path"] == "numeric_fallback"

    @pytest.mark.asyncio
    async def test_resolve_unknown_returns_resolved_false(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
    ):
        """Unrecognised prefix → resolved=False, resolution_path='unknown'."""
        resp = await client.post(
            RESOLVE_URL,
            json={"raw_payload": "FOO:bar"},
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["resolved"] is False
        assert body["resolution_path"] == "unknown"
        assert body["actions"] == []

    @pytest.mark.asyncio
    async def test_log_same_idempotency_key_twice_returns_same_row(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
    ):
        """Body-level idempotency_key dedupes — second POST returns same row."""
        key = _new_uuid4_key()
        body = _minimal_scan_log_body("ORDER:42")
        body["idempotency_key"] = key

        first = await client.post(LOG_URL, json=body, headers=goldsmith_auth_headers)
        assert first.status_code == 201
        first_row = first.json()

        second = await client.post(LOG_URL, json=body, headers=goldsmith_auth_headers)
        # The second call hits the dedupe path; service returns the same row.
        # FastAPI preserves the declared 201 status on the decorator either way.
        assert second.status_code == 201
        second_row = second.json()

        # Dedupe contract: same row id, same timestamp.
        assert first_row["id"] == second_row["id"]
        assert first_row["scanned_at"] == second_row["scanned_at"]
        assert first_row["raw_payload"] == second_row["raw_payload"]

    @pytest.mark.asyncio
    async def test_log_user_id_is_from_jwt_not_body(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        goldsmith_user,
    ):
        """Even without body.user_id, the persisted row links to JWT user."""
        resp = await client.post(
            LOG_URL,
            json=_minimal_scan_log_body("ORDER:7"),
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 201
        body = resp.json()
        assert body["user_id"] == goldsmith_user.id

    @pytest.mark.asyncio
    async def test_log_batch_mixed_keys_reports_correct_counts(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
    ):
        """Batch with duplicate + fresh keys: counts match expectation."""
        dup_key = _new_uuid4_key()

        # First call registers the duplicate key as a scan_logs row.
        pre = _minimal_scan_log_body("ORDER:100")
        pre["idempotency_key"] = dup_key
        seed = await client.post(LOG_URL, json=pre, headers=goldsmith_auth_headers)
        assert seed.status_code == 201

        # Batch: two fresh + one duplicate of the seed.
        fresh_1 = _minimal_scan_log_body("ORDER:101")
        fresh_1["idempotency_key"] = _new_uuid4_key()
        fresh_2 = _minimal_scan_log_body("ORDER:102")
        fresh_2["idempotency_key"] = _new_uuid4_key()
        dup = _minimal_scan_log_body("ORDER:100")
        dup["idempotency_key"] = dup_key

        resp = await client.post(
            BATCH_URL,
            json={"events": [fresh_1, fresh_2, dup]},
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ingested"] == 2
        assert body["deduplicated"] == 1
        assert body["rejected"] == 0
