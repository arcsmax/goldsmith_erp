"""
Unit tests for OrderService

Tests cover:
- Order creation with validation
- Order creation with materials, metal types, and cost fields
- Order retrieval (by ID, listing, pagination)
- Order updates (status transitions, fields, relationships)
- Order deletion
- Material validation and relationships
- Metal inventory integration
- Cost calculation field updates
- Error handling and edge cases
"""
import pytest
from datetime import datetime, timedelta

from goldsmith_erp.services.order_service import OrderService
from goldsmith_erp.models.order import OrderCreate, OrderUpdate
from goldsmith_erp.db.models import (
    Order, OrderStatusEnum, MetalType, CostingMethod, Material
)


@pytest.mark.asyncio
class TestOrderCreation:
    """Test order creation and validation"""

    async def test_create_basic_order_success(self, db_session, sample_customer):
        """Test creating a basic order with required fields"""
        order_data = OrderCreate(
            title="Gold Wedding Ring",
            description="18K gold wedding ring, 5mm width",
            customer_id=sample_customer.id,
            price=1200.00
        )

        order = await OrderService.create_order(db_session, order_data)

        assert order.id is not None
        assert order.title == "Gold Wedding Ring"
        assert order.description == "18K gold wedding ring, 5mm width"
        assert order.customer_id == sample_customer.id
        assert order.price == 1200.00
        assert order.status == OrderStatusEnum.NEW
        assert order.created_at is not None

    async def test_create_order_with_deadline(self, db_session, sample_customer):
        """Test creating order with deadline"""
        deadline = datetime.utcnow() + timedelta(days=14)
        order_data = OrderCreate(
            title="Custom Necklace",
            description="Silver necklace",
            customer_id=sample_customer.id,
            deadline=deadline
        )

        order = await OrderService.create_order(db_session, order_data)

        assert order.deadline is not None
        assert order.deadline.date() == deadline.date()

    async def test_create_order_with_materials(self, db_session, sample_customer, sample_material):
        """Test creating order with linked materials"""
        order_data = OrderCreate(
            title="Bracelet with Gemstone",
            description="Gold bracelet with ruby",
            customer_id=sample_customer.id,
            materials=[sample_material.id]
        )

        order = await OrderService.create_order(db_session, order_data)

        assert len(order.materials) == 1
        assert order.materials[0].id == sample_material.id

    async def test_create_order_with_multiple_materials(self, db_session, sample_customer):
        """Test creating order with multiple materials"""
        # Create multiple materials
        materials = []
        for i in range(3):
            material = Material(
                name=f"Material {i}",
                description=f"Description {i}",
                unit_price=10.0 * (i + 1),
                stock=100.0,
                unit="g"
            )
            db_session.add(material)
        await db_session.commit()
        await db_session.flush()

        material_ids = [m.id for m in materials]

        order_data = OrderCreate(
            title="Complex Piece",
            description="Piece with multiple materials",
            customer_id=sample_customer.id,
            materials=[m.id for m in materials]
        )

        order = await OrderService.create_order(db_session, order_data)

        assert len(order.materials) >= 3

    async def test_create_order_with_invalid_material_raises_error(self, db_session, sample_customer):
        """Test that creating order with non-existent material raises error"""
        order_data = OrderCreate(
            title="Invalid Order",
            description="Order with invalid material",
            customer_id=sample_customer.id,
            materials=[99999]  # Non-existent material
        )

        with pytest.raises(ValueError, match="Materials not found"):
            await OrderService.create_order(db_session, order_data)

    async def test_create_order_with_metal_type(self, db_session, sample_customer):
        """Test creating order with metal type"""
        order_data = OrderCreate(
            title="Gold Ring",
            description="18K gold ring",
            customer_id=sample_customer.id,
            metal_type=MetalType.GOLD_18K,
            estimated_weight_g=15.0,
            scrap_percentage=5.0
        )

        order = await OrderService.create_order(db_session, order_data)

        assert order.metal_type == MetalType.GOLD_18K
        assert order.estimated_weight_g == 15.0
        assert order.scrap_percentage == 5.0

    async def test_create_order_with_cost_fields(self, db_session, sample_customer):
        """Test creating order with cost calculation fields"""
        order_data = OrderCreate(
            title="Custom Ring",
            description="Complex ring design",
            customer_id=sample_customer.id,
            metal_type=MetalType.GOLD_18K,
            estimated_weight_g=20.0,
            labor_hours=5.0,
            hourly_rate=80.00,
            profit_margin_percent=45.0,
            vat_rate=19.0,
            costing_method=CostingMethod.FIFO
        )

        order = await OrderService.create_order(db_session, order_data)

        assert order.labor_hours == 5.0
        assert order.hourly_rate == 80.00
        assert order.profit_margin_percent == 45.0
        assert order.vat_rate == 19.0
        assert order.costing_method_used == CostingMethod.FIFO

    async def test_create_order_with_specific_metal_purchase(self, db_session, sample_customer, sample_metal_purchase):
        """Test creating order with specific metal purchase"""
        order_data = OrderCreate(
            title="Ring from specific batch",
            description="Ring from premium gold batch",
            customer_id=sample_customer.id,
            metal_type=MetalType.GOLD_18K,
            costing_method=CostingMethod.SPECIFIC,
            specific_metal_purchase_id=sample_metal_purchase.id,
            estimated_weight_g=10.0
        )

        order = await OrderService.create_order(db_session, order_data)

        assert order.costing_method_used == CostingMethod.SPECIFIC
        assert order.specific_metal_purchase_id == sample_metal_purchase.id

    async def test_create_order_defaults(self, db_session, sample_customer):
        """Test order creation with default values"""
        order_data = OrderCreate(
            title="Simple Order",
            description="Order with defaults",
            customer_id=sample_customer.id
        )

        order = await OrderService.create_order(db_session, order_data)

        # Verify defaults
        assert order.status == OrderStatusEnum.NEW
        assert order.scrap_percentage == 5.0  # Default from model
        assert order.hourly_rate == 75.00  # Default
        assert order.profit_margin_percent == 40.0  # Default
        assert order.vat_rate == 19.0  # Default


@pytest.mark.asyncio
class TestOrderRetrieval:
    """Test order retrieval operations"""

    async def test_get_order_by_id_success(self, db_session, sample_order):
        """Test getting order by ID"""
        order = await OrderService.get_order(db_session, sample_order.id)

        assert order is not None
        assert order.id == sample_order.id
        assert order.title == sample_order.title

    async def test_get_order_by_id_not_found(self, db_session):
        """Test getting non-existent order returns None"""
        order = await OrderService.get_order(db_session, 99999)

        assert order is None

    async def test_get_order_eager_loads_customer(self, db_session, sample_order):
        """Test that get_order eager loads customer relationship"""
        order = await OrderService.get_order(db_session, sample_order.id)

        # Should not cause N+1 query
        assert order.customer is not None
        assert order.customer.id == sample_order.customer_id

    async def test_get_order_eager_loads_materials(self, db_session, sample_customer, sample_material):
        """Test that get_order eager loads materials relationship"""
        order_data = OrderCreate(
            title="Order with materials",
            description="Test order",
            customer_id=sample_customer.id,
            materials=[sample_material.id]
        )
        order = await OrderService.create_order(db_session, order_data)

        # Retrieve order
        retrieved = await OrderService.get_order(db_session, order.id)

        # Should not cause N+1 query
        assert retrieved.materials is not None
        assert len(retrieved.materials) == 1
        assert retrieved.materials[0].id == sample_material.id

    async def test_get_orders_all(self, db_session, sample_order):
        """Test getting all orders"""
        orders = await OrderService.get_orders(db_session)

        assert len(orders) >= 1
        order_ids = [o.id for o in orders]
        assert sample_order.id in order_ids

    async def test_get_orders_pagination(self, db_session, sample_customer):
        """Test order pagination"""
        # Create 5 orders
        for i in range(5):
            order_data = OrderCreate(
                title=f"Order {i}",
                description=f"Description {i}",
                customer_id=sample_customer.id
            )
            await OrderService.create_order(db_session, order_data)

        # Get first 2
        page1 = await OrderService.get_orders(db_session, skip=0, limit=2)
        assert len(page1) == 2

        # Get next 2
        page2 = await OrderService.get_orders(db_session, skip=2, limit=2)
        assert len(page2) == 2

        # Ensure different orders
        assert page1[0].id != page2[0].id

    async def test_get_orders_ordered_by_created_at_desc(self, db_session, sample_customer):
        """Test that orders are returned newest first"""
        # Create 3 orders with slight delays
        order_ids = []
        for i in range(3):
            order_data = OrderCreate(
                title=f"Order {i}",
                description=f"Created at time {i}",
                customer_id=sample_customer.id
            )
            order = await OrderService.create_order(db_session, order_data)
            order_ids.append(order.id)

        # Get all orders
        orders = await OrderService.get_orders(db_session)

        # Newest should be first (last created)
        # Note: This may not always be reliable in tests without actual time delays
        assert orders[0].created_at >= orders[-1].created_at


@pytest.mark.asyncio
class TestOrderUpdate:
    """Test order update operations"""

    async def test_update_order_basic_fields(self, db_session, sample_order):
        """Test updating basic order fields"""
        update_data = OrderUpdate(
            title="Updated Title",
            description="Updated description",
            price=1500.00
        )

        updated = await OrderService.update_order(db_session, sample_order.id, update_data)

        assert updated.title == "Updated Title"
        assert updated.description == "Updated description"
        assert updated.price == 1500.00

    async def test_update_order_status(self, db_session, sample_order):
        """Test updating order status"""
        update_data = OrderUpdate(status=OrderStatusEnum.IN_PROGRESS)

        updated = await OrderService.update_order(db_session, sample_order.id, update_data)

        assert updated.status == OrderStatusEnum.IN_PROGRESS

    async def test_update_order_status_transitions(self, db_session, sample_order):
        """Test full status workflow"""
        # NEW -> IN_PROGRESS
        await OrderService.update_order(
            db_session, sample_order.id, OrderUpdate(status=OrderStatusEnum.IN_PROGRESS)
        )
        order = await OrderService.get_order(db_session, sample_order.id)
        assert order.status == OrderStatusEnum.IN_PROGRESS

        # IN_PROGRESS -> COMPLETED
        await OrderService.update_order(
            db_session, sample_order.id, OrderUpdate(status=OrderStatusEnum.COMPLETED)
        )
        order = await OrderService.get_order(db_session, sample_order.id)
        assert order.status == OrderStatusEnum.COMPLETED

        # COMPLETED -> DELIVERED
        await OrderService.update_order(
            db_session, sample_order.id, OrderUpdate(status=OrderStatusEnum.DELIVERED)
        )
        order = await OrderService.get_order(db_session, sample_order.id)
        assert order.status == OrderStatusEnum.DELIVERED

    async def test_update_order_deadline(self, db_session, sample_order):
        """Test updating order deadline"""
        new_deadline = datetime.utcnow() + timedelta(days=30)
        update_data = OrderUpdate(deadline=new_deadline)

        updated = await OrderService.update_order(db_session, sample_order.id, update_data)

        assert updated.deadline is not None
        assert updated.deadline.date() == new_deadline.date()

    async def test_update_order_location(self, db_session, sample_order):
        """Test updating current location"""
        update_data = OrderUpdate(current_location="Werkbank 2")

        updated = await OrderService.update_order(db_session, sample_order.id, update_data)

        assert updated.current_location == "Werkbank 2"

    async def test_update_order_weight_fields(self, db_session, sample_order):
        """Test updating weight-related fields"""
        update_data = OrderUpdate(
            estimated_weight_g=25.0,
            actual_weight_g=24.5,
            scrap_percentage=6.0
        )

        updated = await OrderService.update_order(db_session, sample_order.id, update_data)

        assert updated.estimated_weight_g == 25.0
        assert updated.actual_weight_g == 24.5
        assert updated.scrap_percentage == 6.0

    async def test_update_order_metal_type(self, db_session, sample_order):
        """Test updating metal type"""
        update_data = OrderUpdate(
            metal_type=MetalType.SILVER_925,
            costing_method=CostingMethod.LIFO
        )

        updated = await OrderService.update_order(db_session, sample_order.id, update_data)

        assert updated.metal_type == MetalType.SILVER_925
        assert updated.costing_method_used == CostingMethod.LIFO

    async def test_update_order_cost_fields(self, db_session, sample_order):
        """Test updating cost calculation fields"""
        update_data = OrderUpdate(
            labor_hours=8.0,
            hourly_rate=90.00,
            profit_margin_percent=50.0,
            vat_rate=21.0,
            material_cost_override=1000.00
        )

        updated = await OrderService.update_order(db_session, sample_order.id, update_data)

        assert updated.labor_hours == 8.0
        assert updated.hourly_rate == 90.00
        assert updated.profit_margin_percent == 50.0
        assert updated.vat_rate == 21.0
        assert updated.material_cost_override == 1000.00

    async def test_update_order_partial_update(self, db_session, sample_order):
        """Test partial update (only some fields)"""
        original_title = sample_order.title
        original_price = sample_order.price

        update_data = OrderUpdate(description="New description only")

        updated = await OrderService.update_order(db_session, sample_order.id, update_data)

        # Changed field
        assert updated.description == "New description only"
        # Unchanged fields
        assert updated.title == original_title
        assert updated.price == original_price

    async def test_update_non_existent_order(self, db_session):
        """Test updating non-existent order returns None"""
        update_data = OrderUpdate(title="New Title")

        result = await OrderService.update_order(db_session, 99999, update_data)

        assert result is None

    async def test_update_timestamp_is_updated(self, db_session, sample_order):
        """Test that updated_at timestamp is updated"""
        original_updated_at = sample_order.updated_at

        update_data = OrderUpdate(title="New Title")

        updated = await OrderService.update_order(db_session, sample_order.id, update_data)

        assert updated.updated_at > original_updated_at


@pytest.mark.asyncio
class TestOrderDeletion:
    """Test order deletion operations"""

    async def test_delete_order_success(self, db_session, sample_order):
        """Test successful order deletion"""
        order_id = sample_order.id

        result = await OrderService.delete_order(db_session, order_id)

        assert result["success"] is True

        # Verify order no longer exists
        deleted_order = await OrderService.get_order(db_session, order_id)
        assert deleted_order is None

    async def test_delete_non_existent_order(self, db_session):
        """Test deleting non-existent order"""
        result = await OrderService.delete_order(db_session, 99999)

        assert result["success"] is False
        assert "not found" in result["message"].lower()

    async def test_delete_order_with_materials(self, db_session, sample_customer, sample_material):
        """Test deleting order that has materials linked"""
        # Create order with materials
        order_data = OrderCreate(
            title="Order with materials",
            description="Will be deleted",
            customer_id=sample_customer.id,
            materials=[sample_material.id]
        )
        order = await OrderService.create_order(db_session, order_data)

        # Delete order
        result = await OrderService.delete_order(db_session, order.id)

        assert result["success"] is True

        # Verify material still exists (cascade shouldn't delete materials)
        await db_session.refresh(sample_material)
        assert sample_material.id is not None


@pytest.mark.asyncio
class TestOrderValidation:
    """Test order validation and error handling"""

    async def test_create_order_sql_injection_prevention(self, db_session, sample_customer):
        """Test that SQL injection attempts are blocked"""
        malicious_data = OrderCreate(
            title="'; DROP TABLE orders; --",
            description="Normal description",
            customer_id=sample_customer.id
        )

        # Should raise validation error
        with pytest.raises(ValueError, match="dangerous SQL keyword"):
            await OrderService.create_order(db_session, malicious_data)

    async def test_create_order_empty_title_fails(self, db_session, sample_customer):
        """Test that empty title (after stripping) fails"""
        with pytest.raises(ValueError, match="cannot be empty"):
            order_data = OrderCreate(
                title="   ",  # Only whitespace
                description="Valid description",
                customer_id=sample_customer.id
            )

    async def test_create_order_negative_price_fails(self, db_session, sample_customer):
        """Test that negative price fails validation"""
        with pytest.raises(ValueError, match="cannot be negative"):
            order_data = OrderCreate(
                title="Valid title",
                description="Valid description",
                customer_id=sample_customer.id,
                price=-100.00
            )

    async def test_create_order_excessive_price_fails(self, db_session, sample_customer):
        """Test that excessive price fails validation"""
        with pytest.raises(ValueError, match="exceeds maximum"):
            order_data = OrderCreate(
                title="Valid title",
                description="Valid description",
                customer_id=sample_customer.id,
                price=2_000_000.00  # Over 1 million limit
            )

    async def test_create_order_duplicate_materials_fails(self, db_session, sample_customer, sample_material):
        """Test that duplicate material IDs fail validation"""
        with pytest.raises(ValueError, match="Duplicate material"):
            order_data = OrderCreate(
                title="Valid title",
                description="Valid description",
                customer_id=sample_customer.id,
                materials=[sample_material.id, sample_material.id]  # Duplicate!
            )

    async def test_create_order_invalid_material_id_fails(self, db_session, sample_customer):
        """Test that invalid material ID fails validation"""
        with pytest.raises(ValueError, match="Invalid material ID"):
            order_data = OrderCreate(
                title="Valid title",
                description="Valid description",
                customer_id=sample_customer.id,
                materials=[-1, 0]  # Invalid IDs
            )

    async def test_create_order_far_future_deadline_fails(self, db_session, sample_customer):
        """Test that deadline too far in future fails"""
        far_future = datetime(2040, 1, 1)  # More than 10 years

        with pytest.raises(ValueError, match="more than 10 years"):
            order_data = OrderCreate(
                title="Valid title",
                description="Valid description",
                customer_id=sample_customer.id,
                deadline=far_future
            )


@pytest.mark.asyncio
class TestOrderRelationships:
    """Test order relationship integrity"""

    async def test_order_customer_relationship(self, db_session, sample_order):
        """Test Order.customer relationship"""
        order = await OrderService.get_order(db_session, sample_order.id)

        assert order.customer is not None
        assert order.customer.id == sample_order.customer_id
        assert order.customer.email is not None

    async def test_order_materials_relationship(self, db_session, sample_customer):
        """Test Order.materials relationship"""
        # Create materials
        material1 = Material(name="Gold", unit_price=45.0, stock=100.0, unit="g", description="18K Gold")
        material2 = Material(name="Ruby", unit_price=200.0, stock=10.0, unit="ct", description="Ruby gemstone")
        db_session.add(material1)
        db_session.add(material2)
        await db_session.commit()

        # Create order with materials
        order_data = OrderCreate(
            title="Ring with gemstone",
            description="Gold ring with ruby",
            customer_id=sample_customer.id,
            materials=[material1.id, material2.id]
        )
        order = await OrderService.create_order(db_session, order_data)

        # Verify relationship
        assert len(order.materials) == 2
        material_names = {m.name for m in order.materials}
        assert "Gold" in material_names
        assert "Ruby" in material_names

    async def test_order_metal_purchase_relationship(self, db_session, sample_customer, sample_metal_purchase):
        """Test Order.specific_metal_purchase relationship"""
        order_data = OrderCreate(
            title="Ring from specific batch",
            description="Ring from premium batch",
            customer_id=sample_customer.id,
            metal_type=MetalType.GOLD_18K,
            costing_method=CostingMethod.SPECIFIC,
            specific_metal_purchase_id=sample_metal_purchase.id
        )
        order = await OrderService.create_order(db_session, order_data)

        # Retrieve and verify relationship
        retrieved = await OrderService.get_order(db_session, order.id)
        assert retrieved.specific_metal_purchase_id == sample_metal_purchase.id
        # Note: specific_metal_purchase relationship not eager loaded in current service
