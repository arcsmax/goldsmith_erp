"""
Integration tests for the Orders API.

Endpoint coverage:
  GET    /api/v1/orders/           — list orders
  POST   /api/v1/orders/           — create order
  GET    /api/v1/orders/{id}       — get single order
  PUT    /api/v1/orders/{id}       — update order
  DELETE /api/v1/orders/{id}       — delete order

Permission matrix tested:
  - ADMIN    — full CRUD
  - GOLDSMITH — create, view, edit (no delete)
  - VIEWER   — view only
  - No auth  — 401
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import Customer, Order, OrderStatusEnum, User, UserRole


ORDERS_URL = "/api/v1/orders/"


def _order_url(order_id: int) -> str:
    return f"{ORDERS_URL}{order_id}"


# ---------------------------------------------------------------------------
# Payload helpers
# ---------------------------------------------------------------------------

def _create_payload(customer_id: int, title: str = "Test Order") -> dict:
    return {
        "title": title,
        "description": "A test order for the goldsmith workshop",
        "price": 500.00,
        "customer_id": customer_id,
    }


# ---------------------------------------------------------------------------
# GET /api/v1/orders/ — list orders
# ---------------------------------------------------------------------------

class TestListOrders:

    @pytest.mark.asyncio
    async def test_list_orders_unauthenticated_returns_401(
        self, client: AsyncClient
    ):
        """Unauthenticated request is blocked by deny-by-default middleware."""
        response = await client.get(ORDERS_URL)
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_list_orders_as_admin_returns_200(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        """ADMIN can list orders."""
        response = await client.get(ORDERS_URL, headers=admin_auth_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    @pytest.mark.asyncio
    async def test_list_orders_as_goldsmith_returns_200(
        self, client: AsyncClient, goldsmith_auth_headers: dict
    ):
        """GOLDSMITH can list orders."""
        response = await client.get(ORDERS_URL, headers=goldsmith_auth_headers)
        assert response.status_code == 200
        assert isinstance(response.json(), list)

    @pytest.mark.asyncio
    async def test_list_orders_as_viewer_returns_200(
        self, client: AsyncClient, viewer_auth_headers: dict
    ):
        """VIEWER has ORDER_VIEW permission and can list orders."""
        response = await client.get(ORDERS_URL, headers=viewer_auth_headers)
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_list_orders_returns_created_order(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        """An order created via POST appears in the GET list."""
        payload = _create_payload(test_customer.id, title="Listed Order")
        post_resp = await client.post(ORDERS_URL, json=payload, headers=admin_auth_headers)
        assert post_resp.status_code == 200

        get_resp = await client.get(ORDERS_URL, headers=admin_auth_headers)
        assert get_resp.status_code == 200
        titles = [o["title"] for o in get_resp.json()]
        assert "Listed Order" in titles

    @pytest.mark.asyncio
    async def test_list_orders_pagination(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        """skip and limit query parameters are accepted without errors."""
        response = await client.get(
            ORDERS_URL,
            params={"skip": 0, "limit": 5},
            headers=admin_auth_headers,
        )
        assert response.status_code == 200
        assert isinstance(response.json(), list)
        assert len(response.json()) <= 5


# ---------------------------------------------------------------------------
# POST /api/v1/orders/ — create order
# ---------------------------------------------------------------------------

class TestCreateOrder:

    @pytest.mark.asyncio
    async def test_create_order_as_admin_returns_200(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        """ADMIN can create an order; response contains expected fields."""
        payload = _create_payload(test_customer.id, title="Admin Created Order")
        response = await client.post(ORDERS_URL, json=payload, headers=admin_auth_headers)

        assert response.status_code == 200
        body = response.json()
        assert body["title"] == "Admin Created Order"
        assert body["status"] == OrderStatusEnum.NEW.value
        assert body["customer_id"] == test_customer.id
        assert "id" in body
        assert "created_at" in body

    @pytest.mark.asyncio
    async def test_create_order_as_goldsmith_returns_200(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        test_customer: Customer,
    ):
        """GOLDSMITH has ORDER_CREATE permission and can create orders."""
        payload = _create_payload(test_customer.id, title="Goldsmith Order")
        response = await client.post(
            ORDERS_URL, json=payload, headers=goldsmith_auth_headers
        )
        assert response.status_code == 200
        assert response.json()["title"] == "Goldsmith Order"

    @pytest.mark.asyncio
    async def test_create_order_as_viewer_returns_403(
        self,
        client: AsyncClient,
        viewer_auth_headers: dict,
        test_customer: Customer,
    ):
        """VIEWER lacks ORDER_CREATE permission; returns 403."""
        payload = _create_payload(test_customer.id)
        response = await client.post(
            ORDERS_URL, json=payload, headers=viewer_auth_headers
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_create_order_missing_title_returns_422(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        """Payload without required 'title' field fails Pydantic validation."""
        payload = {
            "description": "Missing title",
            "customer_id": test_customer.id,
        }
        response = await client.post(
            ORDERS_URL, json=payload, headers=admin_auth_headers
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_order_missing_customer_id_returns_422(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
    ):
        """Payload without required 'customer_id' fails Pydantic validation."""
        payload = {
            "title": "No Customer",
            "description": "This order has no customer_id",
        }
        response = await client.post(
            ORDERS_URL, json=payload, headers=admin_auth_headers
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_order_negative_price_returns_422(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        """Negative price is rejected by the Pydantic validator."""
        payload = _create_payload(test_customer.id)
        payload["price"] = -100.0
        response = await client.post(
            ORDERS_URL, json=payload, headers=admin_auth_headers
        )
        assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_create_order_unauthenticated_returns_401(
        self,
        client: AsyncClient,
        test_customer: Customer,
    ):
        """Unauthenticated order creation is blocked."""
        payload = _create_payload(test_customer.id)
        response = await client.post(ORDERS_URL, json=payload)
        assert response.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/v1/orders/{id} — get single order
# ---------------------------------------------------------------------------

class TestGetOrder:

    @pytest.mark.asyncio
    async def test_get_order_returns_correct_data(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        """GET /{id} returns the order that was previously created."""
        # Create the order first
        payload = _create_payload(test_customer.id, title="Fetchable Order")
        post_resp = await client.post(
            ORDERS_URL, json=payload, headers=admin_auth_headers
        )
        assert post_resp.status_code == 200
        order_id = post_resp.json()["id"]

        # Fetch it by ID
        get_resp = await client.get(_order_url(order_id), headers=admin_auth_headers)
        assert get_resp.status_code == 200
        body = get_resp.json()
        assert body["id"] == order_id
        assert body["title"] == "Fetchable Order"

    @pytest.mark.asyncio
    async def test_get_order_not_found_returns_404(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
    ):
        """Requesting a non-existent order ID returns 404."""
        response = await client.get(_order_url(999999), headers=admin_auth_headers)
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_get_order_unauthenticated_returns_401(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        """Unauthenticated request for a specific order is blocked."""
        # Create an order first (authenticated)
        payload = _create_payload(test_customer.id)
        post_resp = await client.post(
            ORDERS_URL, json=payload, headers=admin_auth_headers
        )
        order_id = post_resp.json()["id"]

        # Fetch without token
        response = await client.get(_order_url(order_id))
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_get_order_as_viewer_returns_200(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        viewer_auth_headers: dict,
        test_customer: Customer,
    ):
        """VIEWER can read a single order."""
        payload = _create_payload(test_customer.id, title="Viewer Can See")
        post_resp = await client.post(
            ORDERS_URL, json=payload, headers=admin_auth_headers
        )
        order_id = post_resp.json()["id"]

        response = await client.get(_order_url(order_id), headers=viewer_auth_headers)
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# PUT /api/v1/orders/{id} — update order
# ---------------------------------------------------------------------------

class TestUpdateOrder:

    @pytest.mark.asyncio
    async def test_update_order_title_as_admin(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        """ADMIN can update an order's title via PUT."""
        payload = _create_payload(test_customer.id, title="Original Title")
        post_resp = await client.post(
            ORDERS_URL, json=payload, headers=admin_auth_headers
        )
        order_id = post_resp.json()["id"]

        update_payload = {"title": "Updated Title", "description": "Updated description text"}
        put_resp = await client.put(
            _order_url(order_id),
            json=update_payload,
            headers=admin_auth_headers,
        )
        assert put_resp.status_code == 200
        assert put_resp.json()["title"] == "Updated Title"

    @pytest.mark.asyncio
    async def test_update_order_status_to_in_progress(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        """ADMIN can change order status to 'in_progress'."""
        payload = _create_payload(test_customer.id, title="Status Change Order")
        post_resp = await client.post(
            ORDERS_URL, json=payload, headers=admin_auth_headers
        )
        order_id = post_resp.json()["id"]

        update_payload = {"status": OrderStatusEnum.IN_PROGRESS.value}
        put_resp = await client.put(
            _order_url(order_id),
            json=update_payload,
            headers=admin_auth_headers,
        )
        assert put_resp.status_code == 200
        assert put_resp.json()["status"] == OrderStatusEnum.IN_PROGRESS.value

    @pytest.mark.asyncio
    async def test_update_order_as_goldsmith_returns_200(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        goldsmith_auth_headers: dict,
        test_customer: Customer,
    ):
        """GOLDSMITH has ORDER_EDIT permission and can update orders."""
        payload = _create_payload(test_customer.id, title="Goldsmith Editable")
        post_resp = await client.post(
            ORDERS_URL, json=payload, headers=admin_auth_headers
        )
        order_id = post_resp.json()["id"]

        update_payload = {"title": "Goldsmith Edited", "description": "Goldsmith updated this order"}
        put_resp = await client.put(
            _order_url(order_id),
            json=update_payload,
            headers=goldsmith_auth_headers,
        )
        assert put_resp.status_code == 200

    @pytest.mark.asyncio
    async def test_update_order_as_viewer_returns_403(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        viewer_auth_headers: dict,
        test_customer: Customer,
    ):
        """VIEWER lacks ORDER_EDIT permission; PUT returns 403."""
        payload = _create_payload(test_customer.id, title="Viewer Cannot Edit")
        post_resp = await client.post(
            ORDERS_URL, json=payload, headers=admin_auth_headers
        )
        order_id = post_resp.json()["id"]

        update_payload = {"title": "Viewer Tried To Edit", "description": "Attempt"}
        put_resp = await client.put(
            _order_url(order_id),
            json=update_payload,
            headers=viewer_auth_headers,
        )
        assert put_resp.status_code == 403

    @pytest.mark.asyncio
    async def test_update_nonexistent_order_returns_404(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
    ):
        """Updating an order that does not exist returns 404."""
        update_payload = {"title": "Ghost Order", "description": "Does not exist"}
        response = await client.put(
            _order_url(999999),
            json=update_payload,
            headers=admin_auth_headers,
        )
        assert response.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /api/v1/orders/{id} — delete order
# ---------------------------------------------------------------------------

class TestDeleteOrder:

    @pytest.mark.asyncio
    async def test_delete_order_as_admin_returns_200(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        test_customer: Customer,
    ):
        """ADMIN can delete an order; subsequent GET returns 404."""
        payload = _create_payload(test_customer.id, title="To Be Deleted")
        post_resp = await client.post(
            ORDERS_URL, json=payload, headers=admin_auth_headers
        )
        order_id = post_resp.json()["id"]

        delete_resp = await client.delete(
            _order_url(order_id), headers=admin_auth_headers
        )
        assert delete_resp.status_code == 200

        # Verify the order is gone
        get_resp = await client.get(_order_url(order_id), headers=admin_auth_headers)
        assert get_resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_order_as_goldsmith_returns_403(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
        goldsmith_auth_headers: dict,
        test_customer: Customer,
    ):
        """GOLDSMITH lacks ORDER_DELETE permission; returns 403."""
        payload = _create_payload(test_customer.id, title="Goldsmith Cannot Delete")
        post_resp = await client.post(
            ORDERS_URL, json=payload, headers=admin_auth_headers
        )
        order_id = post_resp.json()["id"]

        delete_resp = await client.delete(
            _order_url(order_id), headers=goldsmith_auth_headers
        )
        assert delete_resp.status_code == 403

    @pytest.mark.asyncio
    async def test_delete_nonexistent_order_returns_404(
        self,
        client: AsyncClient,
        admin_auth_headers: dict,
    ):
        """Deleting a non-existent order returns 404."""
        response = await client.delete(
            _order_url(999999), headers=admin_auth_headers
        )
        assert response.status_code == 404
