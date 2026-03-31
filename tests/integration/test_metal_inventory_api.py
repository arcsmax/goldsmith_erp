"""
Integration tests for Metal Inventory API endpoints.

Tests cover:
- Metal purchase creation, listing, and updates
- Material consumption and usage tracking
- Inventory statistics and reporting
- Material allocation preview
- Permission-based access control
"""
import pytest
from httpx import AsyncClient
from datetime import datetime

from goldsmith_erp.db.models import MetalType, CostingMethod


class TestMetalPurchaseEndpoints:
    """Test metal purchase API endpoints"""

    @pytest.mark.asyncio
    async def test_create_purchase_success(self, client: AsyncClient, admin_auth_headers):
        """Test creating a new metal purchase"""
        purchase_data = {
            "metal_type": "gold_18k",
            "weight_g": 100.0,
            "price_total": 4500.00,
            "supplier": "Metalor Technologies",
            "invoice_number": "INV-2025-001"
        }

        response = await client.post(
            "/api/v1/metal-inventory/purchases",
            json=purchase_data,
            headers=admin_auth_headers
        )

        assert response.status_code == 201
        data = response.json()
        assert data["metal_type"] == "gold_18k"
        assert data["weight_g"] == 100.0
        assert data["remaining_weight_g"] == 100.0
        assert data["price_per_gram"] == 45.00  # Auto-calculated
        assert data["is_depleted"] is False

    @pytest.mark.asyncio
    async def test_create_purchase_auto_calculates_price_per_gram(
        self, client: AsyncClient, admin_auth_headers
    ):
        """Test that price_per_gram is automatically calculated"""
        purchase_data = {
            "metal_type": "silver_925",
            "weight_g": 500.0,
            "price_total": 400.00,
            "supplier": "Silver Supplier"
        }

        response = await client.post(
            "/api/v1/metal-inventory/purchases",
            json=purchase_data,
            headers=admin_auth_headers
        )

        assert response.status_code == 201
        data = response.json()
        assert data["price_per_gram"] == 0.80  # 400 / 500

    @pytest.mark.asyncio
    async def test_list_purchases_all(
        self, client: AsyncClient, admin_auth_headers, sample_metal_purchase
    ):
        """Test listing all metal purchases"""
        response = await client.get(
            "/api/v1/metal-inventory/purchases",
            headers=admin_auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["metal_type"] == "gold_18k"

    @pytest.mark.asyncio
    async def test_list_purchases_filter_by_metal_type(
        self, client: AsyncClient, admin_auth_headers, sample_metal_purchase, silver_purchase
    ):
        """Test filtering purchases by metal type"""
        response = await client.get(
            "/api/v1/metal-inventory/purchases?metal_type=gold_18k",
            headers=admin_auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert all(p["metal_type"] == "gold_18k" for p in data)

    @pytest.mark.asyncio
    async def test_list_purchases_exclude_depleted(
        self, client: AsyncClient, admin_auth_headers, db_session, sample_metal_purchase
    ):
        """Test excluding depleted batches from list"""
        # Deplete the purchase
        sample_metal_purchase.remaining_weight_g = 0.0
        await db_session.commit()

        response = await client.get(
            "/api/v1/metal-inventory/purchases?include_depleted=false",
            headers=admin_auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert all(p["remaining_weight_g"] > 0 for p in data)

    @pytest.mark.asyncio
    async def test_get_purchase_by_id(
        self, client: AsyncClient, admin_auth_headers, sample_metal_purchase
    ):
        """Test getting a specific purchase by ID"""
        response = await client.get(
            f"/api/v1/metal-inventory/purchases/{sample_metal_purchase.id}",
            headers=admin_auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == sample_metal_purchase.id
        assert data["metal_type"] == "gold_18k"
        assert data["supplier"] == "Test Supplier"

    @pytest.mark.asyncio
    async def test_get_purchase_not_found(
        self, client: AsyncClient, admin_auth_headers
    ):
        """Test getting non-existent purchase returns 404"""
        response = await client.get(
            "/api/v1/metal-inventory/purchases/99999",
            headers=admin_auth_headers
        )

        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_update_purchase_metadata(
        self, client: AsyncClient, admin_auth_headers, sample_metal_purchase
    ):
        """Test updating purchase metadata"""
        update_data = {
            "supplier": "Updated Supplier",
            "notes": "Updated notes"
        }

        response = await client.patch(
            f"/api/v1/metal-inventory/purchases/{sample_metal_purchase.id}",
            json=update_data,
            headers=admin_auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["supplier"] == "Updated Supplier"
        assert data["notes"] == "Updated notes"
        # Weight and price should not change
        assert data["weight_g"] == 100.0
        assert data["price_per_gram"] == 45.00


class TestMaterialUsageEndpoints:
    """Test material consumption API endpoints"""

    @pytest.mark.asyncio
    async def test_consume_material_fifo(
        self, client: AsyncClient, admin_auth_headers,
        sample_metal_purchase, sample_order, db_session
    ):
        """Test consuming material using FIFO method"""
        usage_data = {
            "order_id": sample_order.id,
            "weight_used_g": 25.0,
            "costing_method": "fifo",
            "notes": "Test consumption"
        }

        response = await client.post(
            "/api/v1/metal-inventory/usage?metal_type=gold_18k",
            json=usage_data,
            headers=admin_auth_headers
        )

        assert response.status_code == 201
        data = response.json()
        assert data["order_id"] == sample_order.id
        assert data["weight_used_g"] == 25.0
        assert data["cost_at_time"] == pytest.approx(1125.00, rel=0.01)  # 25 * 45
        assert data["costing_method"] == "fifo"

        # Verify inventory was reduced
        await db_session.refresh(sample_metal_purchase)
        assert sample_metal_purchase.remaining_weight_g == 75.0

    @pytest.mark.asyncio
    async def test_consume_material_specific_batch(
        self, client: AsyncClient, admin_auth_headers,
        sample_metal_purchase, sample_order
    ):
        """Test consuming material from specific batch"""
        usage_data = {
            "order_id": sample_order.id,
            "weight_used_g": 30.0,
            "costing_method": "specific",
            "metal_purchase_id": sample_metal_purchase.id,
            "notes": "Specific batch selection"
        }

        response = await client.post(
            "/api/v1/metal-inventory/usage?metal_type=gold_18k",
            json=usage_data,
            headers=admin_auth_headers
        )

        assert response.status_code == 201
        data = response.json()
        assert data["metal_purchase_id"] == sample_metal_purchase.id

    @pytest.mark.asyncio
    async def test_consume_material_insufficient_inventory(
        self, client: AsyncClient, admin_auth_headers, sample_metal_purchase, sample_order
    ):
        """Test error when insufficient inventory"""
        usage_data = {
            "order_id": sample_order.id,
            "weight_used_g": 200.0,  # More than available
            "costing_method": "fifo"
        }

        response = await client.post(
            "/api/v1/metal-inventory/usage?metal_type=gold_18k",
            json=usage_data,
            headers=admin_auth_headers
        )

        assert response.status_code == 400
        assert "Insufficient inventory" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_consume_material_no_inventory_available(
        self, client: AsyncClient, admin_auth_headers, sample_order
    ):
        """Test error when no inventory exists"""
        usage_data = {
            "order_id": sample_order.id,
            "weight_used_g": 10.0,
            "costing_method": "fifo"
        }

        response = await client.post(
            "/api/v1/metal-inventory/usage?metal_type=gold_24k",  # No inventory
            json=usage_data,
            headers=admin_auth_headers
        )

        assert response.status_code == 400
        assert "No inventory available" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_get_usage_history(
        self, client: AsyncClient, admin_auth_headers,
        sample_metal_purchase, sample_order, db_session
    ):
        """Test getting material usage history"""
        # First consume some material
        from goldsmith_erp.models.metal_inventory import MaterialUsageCreate
        from goldsmith_erp.services.metal_inventory_service import MetalInventoryService

        usage_data = MaterialUsageCreate(
            order_id=sample_order.id,
            weight_used_g=20.0,
            costing_method=CostingMethod.FIFO
        )
        await MetalInventoryService.consume_material(db_session, usage_data, MetalType.GOLD_18K)

        # Now fetch usage history
        response = await client.get(
            "/api/v1/metal-inventory/usage",
            headers=admin_auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert data[0]["order_id"] == sample_order.id

    @pytest.mark.asyncio
    async def test_get_usage_history_filter_by_order(
        self, client: AsyncClient, admin_auth_headers,
        sample_metal_purchase, sample_order, db_session
    ):
        """Test filtering usage history by order ID"""
        # Consume material
        from goldsmith_erp.models.metal_inventory import MaterialUsageCreate
        from goldsmith_erp.services.metal_inventory_service import MetalInventoryService

        usage_data = MaterialUsageCreate(
            order_id=sample_order.id,
            weight_used_g=15.0,
            costing_method=CostingMethod.FIFO
        )
        await MetalInventoryService.consume_material(db_session, usage_data, MetalType.GOLD_18K)

        # Filter by order
        response = await client.get(
            f"/api/v1/metal-inventory/usage?order_id={sample_order.id}",
            headers=admin_auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert all(u["order_id"] == sample_order.id for u in data)


class TestInventoryStatistics:
    """Test inventory statistics endpoint"""

    @pytest.mark.asyncio
    async def test_get_inventory_statistics(
        self, client: AsyncClient, admin_auth_headers,
        sample_metal_purchase, silver_purchase
    ):
        """Test getting inventory statistics"""
        response = await client.get(
            "/api/v1/metal-inventory/statistics",
            headers=admin_auth_headers
        )

        assert response.status_code == 200
        data = response.json()

        # Check overall statistics
        assert data["total_value"] == pytest.approx(4900.00, rel=0.01)  # 4500 + 400
        assert data["total_weight_g"] == pytest.approx(600.0, rel=0.01)  # 100 + 500

        # Check metal type breakdown
        assert len(data["metal_types"]) == 2
        gold_stats = next((m for m in data["metal_types"] if m["metal_type"] == "gold_18k"), None)
        assert gold_stats is not None
        assert gold_stats["total_weight_g"] == 100.0
        assert gold_stats["average_price_per_gram"] == 45.00

    @pytest.mark.asyncio
    async def test_get_inventory_statistics_low_stock_alert(
        self, client: AsyncClient, admin_auth_headers, db_session
    ):
        """Test low stock alerts in statistics"""
        from goldsmith_erp.db.models import MetalPurchase

        # Create low stock purchase
        low_stock = MetalPurchase(
            date_purchased=datetime.utcnow(),
            metal_type=MetalType.PLATINUM_950,
            weight_g=25.0,  # Below 50g threshold
            remaining_weight_g=25.0,
            price_total=2500.00,
            price_per_gram=100.00,
            supplier="Platinum Supplier"
        )
        db_session.add(low_stock)
        await db_session.commit()

        response = await client.get(
            "/api/v1/metal-inventory/statistics",
            headers=admin_auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["low_stock_alerts"]) > 0
        assert any("platinum_950" in alert for alert in data["low_stock_alerts"])


class TestMaterialAllocationPreview:
    """Test material allocation preview endpoint"""

    @pytest.mark.asyncio
    async def test_preview_allocation_fifo(
        self, client: AsyncClient, admin_auth_headers, sample_metal_purchase
    ):
        """Test previewing material allocation without consuming"""
        response = await client.post(
            "/api/v1/metal-inventory/allocate-preview"
            "?metal_type=gold_18k&required_weight_g=25.0&costing_method=fifo",
            headers=admin_auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["required_weight_g"] == 25.0
        assert data["total_cost"] == pytest.approx(1125.00, rel=0.01)
        assert data["costing_method"] == "fifo"
        assert len(data["allocations"]) >= 1

    @pytest.mark.asyncio
    async def test_preview_allocation_multiple_batches(
        self, client: AsyncClient, admin_auth_headers, multiple_metal_purchases
    ):
        """Test preview with allocation across multiple batches"""
        response = await client.post(
            "/api/v1/metal-inventory/allocate-preview"
            "?metal_type=gold_18k&required_weight_g=150.0&costing_method=fifo",
            headers=admin_auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert len(data["allocations"]) == 2  # Uses 2 batches
        # FIFO: 100g @ 44 + 50g @ 45 = 6650
        assert data["total_cost"] == pytest.approx(6650.00, rel=0.01)

    @pytest.mark.asyncio
    async def test_preview_allocation_insufficient_inventory(
        self, client: AsyncClient, admin_auth_headers, sample_metal_purchase
    ):
        """Test preview error when insufficient inventory"""
        response = await client.post(
            "/api/v1/metal-inventory/allocate-preview"
            "?metal_type=gold_18k&required_weight_g=200.0&costing_method=fifo",
            headers=admin_auth_headers
        )

        assert response.status_code == 400
        assert "Insufficient inventory" in response.json()["detail"]

    @pytest.mark.asyncio
    async def test_preview_allocation_average_cost(
        self, client: AsyncClient, admin_auth_headers, multiple_metal_purchases
    ):
        """Test preview with average cost method"""
        response = await client.post(
            "/api/v1/metal-inventory/allocate-preview"
            "?metal_type=gold_18k&required_weight_g=60.0&costing_method=average",
            headers=admin_auth_headers
        )

        assert response.status_code == 200
        data = response.json()
        # Average: (4400 + 4500 + 4600) / 300g = 45 EUR/g
        # 60g * 45 = 2700
        assert data["total_cost"] == pytest.approx(2700.00, rel=0.01)


class TestPermissions:
    """Test permission-based access control"""

    @pytest.mark.asyncio
    async def test_create_purchase_requires_material_create_permission(
        self, client: AsyncClient, auth_headers
    ):
        """Test that regular users cannot create purchases"""
        purchase_data = {
            "metal_type": "gold_18k",
            "weight_g": 100.0,
            "price_total": 4500.00,
            "supplier": "Test"
        }

        response = await client.post(
            "/api/v1/metal-inventory/purchases",
            json=purchase_data,
            headers=auth_headers  # Regular user, not admin
        )

        # Should fail without permission
        # Note: Actual status code depends on permission implementation
        assert response.status_code in [401, 403]

    @pytest.mark.asyncio
    async def test_view_purchases_requires_material_view_permission(
        self, client: AsyncClient
    ):
        """Test that unauthenticated users cannot view purchases"""
        response = await client.get("/api/v1/metal-inventory/purchases")

        assert response.status_code in [401, 403]
