"""
Unit tests for CustomerService

Tests cover:
- Customer creation with validation
- Customer updates (partial, email uniqueness)
- Customer retrieval (by ID, by email, listing)
- Customer search and filtering
- Customer deletion (soft delete)
- Customer statistics and analytics
- Error handling and edge cases
"""
import pytest
from datetime import datetime, timedelta

from goldsmith_erp.services.customer_service import CustomerService
from goldsmith_erp.models.customer import CustomerCreate, CustomerUpdate
from goldsmith_erp.db.models import Customer, Order, OrderStatusEnum


@pytest.mark.asyncio
class TestCustomerCreation:
    """Test customer creation and validation"""

    async def test_create_private_customer_success(self, db_session):
        """Test creating a private customer"""
        customer_data = CustomerCreate(
            first_name="John",
            last_name="Doe",
            email="john.doe@example.com",
            phone="+49 123 456789",
            customer_type="private",
            city="Munich",
            postal_code="80331",
            country="Germany"
        )

        customer = await CustomerService.create_customer(db_session, customer_data)

        assert customer.id is not None
        assert customer.first_name == "John"
        assert customer.last_name == "Doe"
        assert customer.email == "john.doe@example.com"
        assert customer.customer_type == "private"
        assert customer.is_active is True
        assert customer.created_at is not None

    async def test_create_business_customer_success(self, db_session):
        """Test creating a business customer with company name"""
        customer_data = CustomerCreate(
            first_name="Maria",
            last_name="Schmidt",
            company_name="Schmidt Jewelers GmbH",
            email="maria@schmidt-jewelers.de",
            phone="+49 89 12345678",
            customer_type="business",
            street="Maximilianstraße 1",
            city="Munich",
            postal_code="80539",
            country="Germany"
        )

        customer = await CustomerService.create_customer(db_session, customer_data)

        assert customer.company_name == "Schmidt Jewelers GmbH"
        assert customer.customer_type == "business"
        assert customer.email == "maria@schmidt-jewelers.de"

    async def test_create_customer_duplicate_email_fails(self, db_session, sample_customer):
        """Test that duplicate email raises ValueError"""
        duplicate_data = CustomerCreate(
            first_name="Different",
            last_name="Person",
            email=sample_customer.email,  # Same email!
            customer_type="private"
        )

        with pytest.raises(ValueError, match="already exists"):
            await CustomerService.create_customer(db_session, duplicate_data)

    async def test_create_customer_with_tags(self, db_session):
        """Test creating customer with tags"""
        customer_data = CustomerCreate(
            first_name="VIP",
            last_name="Customer",
            email="vip@example.com",
            customer_type="private",
            tags=["VIP", "Stammkunde", "Repeat Customer"]
        )

        customer = await CustomerService.create_customer(db_session, customer_data)

        assert "VIP" in customer.tags
        assert "Stammkunde" in customer.tags
        assert len(customer.tags) == 3

    async def test_create_customer_with_notes(self, db_session):
        """Test creating customer with notes"""
        customer_data = CustomerCreate(
            first_name="Special",
            last_name="Requests",
            email="special@example.com",
            customer_type="private",
            notes="Prefers email contact. Allergic to nickel."
        )

        customer = await CustomerService.create_customer(db_session, customer_data)

        assert customer.notes == "Prefers email contact. Allergic to nickel."


@pytest.mark.asyncio
class TestCustomerRetrieval:
    """Test customer retrieval operations"""

    async def test_get_customer_by_id_success(self, db_session, sample_customer):
        """Test getting customer by ID"""
        customer = await CustomerService.get_customer(db_session, sample_customer.id)

        assert customer is not None
        assert customer.id == sample_customer.id
        assert customer.email == sample_customer.email

    async def test_get_customer_by_id_not_found(self, db_session):
        """Test getting non-existent customer returns None"""
        customer = await CustomerService.get_customer(db_session, 99999)

        assert customer is None

    async def test_get_customer_by_email_success(self, db_session, sample_customer):
        """Test getting customer by email"""
        customer = await CustomerService.get_customer_by_email(
            db_session, sample_customer.email
        )

        assert customer is not None
        assert customer.id == sample_customer.id
        assert customer.email == sample_customer.email

    async def test_get_customer_by_email_not_found(self, db_session):
        """Test getting customer by non-existent email returns None"""
        customer = await CustomerService.get_customer_by_email(
            db_session, "nonexistent@example.com"
        )

        assert customer is None

    async def test_get_customers_all(self, db_session, sample_customer, business_customer):
        """Test getting all customers"""
        customers = await CustomerService.get_customers(db_session)

        assert len(customers) >= 2
        customer_emails = [c.email for c in customers]
        assert sample_customer.email in customer_emails
        assert business_customer.email in customer_emails

    async def test_get_customers_with_pagination(self, db_session):
        """Test customer pagination"""
        # Create 5 customers
        for i in range(5):
            customer_data = CustomerCreate(
                first_name=f"Test{i}",
                last_name="User",
                email=f"test{i}@example.com",
                customer_type="private"
            )
            await CustomerService.create_customer(db_session, customer_data)

        # Get first 2
        page1 = await CustomerService.get_customers(db_session, skip=0, limit=2)
        assert len(page1) == 2

        # Get next 2
        page2 = await CustomerService.get_customers(db_session, skip=2, limit=2)
        assert len(page2) == 2

        # Ensure different customers
        assert page1[0].id != page2[0].id


@pytest.mark.asyncio
class TestCustomerFiltering:
    """Test customer filtering and search"""

    async def test_filter_by_customer_type_private(
        self, db_session, sample_customer, business_customer
    ):
        """Test filtering by customer type (private)"""
        customers = await CustomerService.get_customers(
            db_session, customer_type="private"
        )

        assert all(c.customer_type == "private" for c in customers)
        assert sample_customer.id in [c.id for c in customers]

    async def test_filter_by_customer_type_business(
        self, db_session, sample_customer, business_customer
    ):
        """Test filtering by customer type (business)"""
        customers = await CustomerService.get_customers(
            db_session, customer_type="business"
        )

        assert all(c.customer_type == "business" for c in customers)
        assert business_customer.id in [c.id for c in customers]

    async def test_filter_by_is_active(self, db_session, sample_customer):
        """Test filtering by active status"""
        # Deactivate customer
        sample_customer.is_active = False
        await db_session.commit()

        # Get only active
        active = await CustomerService.get_customers(db_session, is_active=True)
        assert sample_customer.id not in [c.id for c in active]

        # Get only inactive
        inactive = await CustomerService.get_customers(db_session, is_active=False)
        assert sample_customer.id in [c.id for c in inactive]

    async def test_search_by_first_name(self, db_session, sample_customer):
        """Test searching by first name"""
        # sample_customer has first_name "Max"
        customers = await CustomerService.get_customers(db_session, search="Max")

        assert len(customers) >= 1
        assert sample_customer.id in [c.id for c in customers]

    async def test_search_by_last_name(self, db_session, sample_customer):
        """Test searching by last name"""
        # sample_customer has last_name "Mustermann"
        customers = await CustomerService.get_customers(db_session, search="Muster")

        assert len(customers) >= 1
        assert sample_customer.id in [c.id for c in customers]

    async def test_search_by_email(self, db_session, sample_customer):
        """Test searching by email"""
        customers = await CustomerService.get_customers(db_session, search="max.mustermann")

        assert len(customers) >= 1
        assert sample_customer.id in [c.id for c in customers]

    async def test_search_by_company_name(self, db_session, business_customer):
        """Test searching by company name"""
        customers = await CustomerService.get_customers(db_session, search="Edelmetall")

        assert len(customers) >= 1
        assert business_customer.id in [c.id for c in customers]

    async def test_filter_by_tag(self, db_session):
        """Test filtering by tag"""
        # Create customer with VIP tag
        vip_customer_data = CustomerCreate(
            first_name="VIP",
            last_name="Person",
            email="vip@example.com",
            customer_type="private",
            tags=["VIP", "Stammkunde"]
        )
        vip_customer = await CustomerService.create_customer(db_session, vip_customer_data)

        # Filter by VIP tag
        vips = await CustomerService.get_customers(db_session, tag="VIP")

        assert len(vips) >= 1
        assert vip_customer.id in [c.id for c in vips]

    async def test_combined_filters(self, db_session):
        """Test combining multiple filters"""
        # Create specific customer
        customer_data = CustomerCreate(
            first_name="Private",
            last_name="VIPCustomer",
            email="private.vip@example.com",
            customer_type="private",
            tags=["VIP"]
        )
        customer = await CustomerService.create_customer(db_session, customer_data)

        # Search with multiple filters
        results = await CustomerService.get_customers(
            db_session,
            search="VIP",
            customer_type="private",
            is_active=True,
            tag="VIP"
        )

        assert customer.id in [c.id for c in results]


@pytest.mark.asyncio
class TestCustomerUpdate:
    """Test customer update operations"""

    async def test_update_customer_contact_info(self, db_session, sample_customer):
        """Test updating customer contact information"""
        update_data = CustomerUpdate(
            phone="+49 89 NEW-PHONE",
            mobile="+49 176 MOBILE"
        )

        updated = await CustomerService.update_customer(
            db_session, sample_customer.id, update_data
        )

        assert updated.phone == "+49 89 NEW-PHONE"
        assert updated.mobile == "+49 176 MOBILE"
        # Other fields unchanged
        assert updated.email == sample_customer.email

    async def test_update_customer_address(self, db_session, sample_customer):
        """Test updating customer address"""
        update_data = CustomerUpdate(
            street="New Street 123",
            city="Berlin",
            postal_code="10115",
            country="Germany"
        )

        updated = await CustomerService.update_customer(
            db_session, sample_customer.id, update_data
        )

        assert updated.street == "New Street 123"
        assert updated.city == "Berlin"
        assert updated.postal_code == "10115"

    async def test_update_customer_tags(self, db_session, sample_customer):
        """Test updating customer tags"""
        update_data = CustomerUpdate(
            tags=["VIP", "Premium", "Gold Member"]
        )

        updated = await CustomerService.update_customer(
            db_session, sample_customer.id, update_data
        )

        assert len(updated.tags) == 3
        assert "VIP" in updated.tags
        assert "Premium" in updated.tags

    async def test_update_customer_notes(self, db_session, sample_customer):
        """Test updating customer notes"""
        update_data = CustomerUpdate(
            notes="Updated notes: Customer prefers SMS"
        )

        updated = await CustomerService.update_customer(
            db_session, sample_customer.id, update_data
        )

        assert updated.notes == "Updated notes: Customer prefers SMS"

    async def test_update_customer_type(self, db_session, sample_customer):
        """Test changing customer type"""
        update_data = CustomerUpdate(
            customer_type="business",
            company_name="Mustermann GmbH"
        )

        updated = await CustomerService.update_customer(
            db_session, sample_customer.id, update_data
        )

        assert updated.customer_type == "business"
        assert updated.company_name == "Mustermann GmbH"

    async def test_update_customer_email_unique_check(
        self, db_session, sample_customer, business_customer
    ):
        """Test that updating to existing email fails"""
        update_data = CustomerUpdate(
            email=business_customer.email  # Try to use business customer's email
        )

        with pytest.raises(ValueError, match="already exists"):
            await CustomerService.update_customer(
                db_session, sample_customer.id, update_data
            )

    async def test_update_customer_same_email_allowed(self, db_session, sample_customer):
        """Test that updating with same email is allowed"""
        update_data = CustomerUpdate(
            email=sample_customer.email,  # Same email
            phone="New phone"
        )

        updated = await CustomerService.update_customer(
            db_session, sample_customer.id, update_data
        )

        assert updated.email == sample_customer.email
        assert updated.phone == "New phone"

    async def test_update_non_existent_customer(self, db_session):
        """Test updating non-existent customer returns None"""
        update_data = CustomerUpdate(phone="123")

        result = await CustomerService.update_customer(db_session, 99999, update_data)

        assert result is None

    async def test_update_timestamp_is_updated(self, db_session, sample_customer):
        """Test that updated_at timestamp is updated"""
        original_updated_at = sample_customer.updated_at

        # Wait a moment then update
        update_data = CustomerUpdate(phone="New")

        updated = await CustomerService.update_customer(
            db_session, sample_customer.id, update_data
        )

        assert updated.updated_at > original_updated_at


@pytest.mark.asyncio
class TestCustomerDeletion:
    """Test customer deletion operations"""

    async def test_soft_delete_customer_no_orders(self, db_session, sample_customer):
        """Test soft deleting customer without orders"""
        result = await CustomerService.delete_customer(db_session, sample_customer.id)

        assert result is True

        # Verify customer is deactivated
        customer = await CustomerService.get_customer(db_session, sample_customer.id)
        assert customer.is_active is False

    async def test_delete_customer_with_orders_fails(self, db_session, sample_customer):
        """Test that deleting customer with orders raises error"""
        # Create an order for the customer
        from goldsmith_erp.db.models import Order

        order = Order(
            title="Test Order",
            customer_id=sample_customer.id,
            status=OrderStatusEnum.NEW
        )
        db_session.add(order)
        await db_session.commit()

        # Attempt to delete should fail
        with pytest.raises(ValueError, match="Cannot delete customer"):
            await CustomerService.delete_customer(db_session, sample_customer.id)

    async def test_delete_non_existent_customer(self, db_session):
        """Test deleting non-existent customer returns False"""
        result = await CustomerService.delete_customer(db_session, 99999)

        assert result is False


@pytest.mark.asyncio
class TestCustomerStatistics:
    """Test customer statistics and analytics"""

    async def test_get_customer_order_count_zero(self, db_session, sample_customer):
        """Test order count for customer with no orders"""
        count = await CustomerService.get_customer_order_count(
            db_session, sample_customer.id
        )

        assert count == 0

    async def test_get_customer_order_count_multiple(self, db_session, sample_customer):
        """Test order count for customer with multiple orders"""
        from goldsmith_erp.db.models import Order

        # Create 3 orders
        for i in range(3):
            order = Order(
                title=f"Order {i}",
                customer_id=sample_customer.id,
                status=OrderStatusEnum.NEW
            )
            db_session.add(order)
        await db_session.commit()

        count = await CustomerService.get_customer_order_count(
            db_session, sample_customer.id
        )

        assert count == 3

    async def test_get_customer_stats(self, db_session, sample_customer):
        """Test getting customer statistics"""
        from goldsmith_erp.db.models import Order

        # Create orders with prices
        orders = [
            Order(title="Order 1", customer_id=sample_customer.id, price=100.0, status=OrderStatusEnum.NEW),
            Order(title="Order 2", customer_id=sample_customer.id, price=200.0, status=OrderStatusEnum.NEW),
            Order(title="Order 3", customer_id=sample_customer.id, price=150.0, status=OrderStatusEnum.NEW),
        ]
        for order in orders:
            db_session.add(order)
        await db_session.commit()

        stats = await CustomerService.get_customer_stats(db_session, sample_customer.id)

        assert stats["customer_id"] == sample_customer.id
        assert stats["order_count"] == 3
        assert stats["total_spent"] == 450.0  # 100 + 200 + 150
        assert stats["last_order_date"] is not None


@pytest.mark.asyncio
class TestCustomerSearch:
    """Test customer search functionality"""

    async def test_search_customers_by_name(self, db_session):
        """Test fast search for autocomplete"""
        # Create searchable customer
        customer_data = CustomerCreate(
            first_name="Searchable",
            last_name="Customer",
            email="searchable@example.com",
            customer_type="private"
        )
        customer = await CustomerService.create_customer(db_session, customer_data)

        # Search
        results = await CustomerService.search_customers(db_session, "Search")

        assert len(results) >= 1
        assert customer.id in [c.id for c in results]

    async def test_search_customers_limit(self, db_session):
        """Test search respects limit parameter"""
        # Create 15 customers
        for i in range(15):
            customer_data = CustomerCreate(
                first_name=f"TestSearch{i}",
                last_name="User",
                email=f"testsearch{i}@example.com",
                customer_type="private"
            )
            await CustomerService.create_customer(db_session, customer_data)

        # Search with limit=5
        results = await CustomerService.search_customers(
            db_session, "TestSearch", limit=5
        )

        assert len(results) == 5

    async def test_search_only_active_customers(self, db_session, sample_customer):
        """Test search only returns active customers"""
        # Deactivate customer
        sample_customer.is_active = False
        await db_session.commit()

        # Search should not find inactive customer
        results = await CustomerService.search_customers(
            db_session, sample_customer.first_name
        )

        assert sample_customer.id not in [c.id for c in results]


@pytest.mark.asyncio
class TestTopCustomers:
    """Test top customers analytics"""

    async def test_get_top_customers_by_revenue(self, db_session):
        """Test getting top customers by revenue"""
        from goldsmith_erp.db.models import Order

        # Create customers with orders
        customers = []
        for i in range(3):
            customer_data = CustomerCreate(
                first_name=f"Revenue{i}",
                last_name="Customer",
                email=f"revenue{i}@example.com",
                customer_type="private"
            )
            customer = await CustomerService.create_customer(db_session, customer_data)
            customers.append(customer)

            # Add orders with different revenue
            for j in range(i + 1):
                order = Order(
                    title=f"Order {j}",
                    customer_id=customer.id,
                    price=1000.0 * (i + 1),  # More expensive for higher i
                    status=OrderStatusEnum.NEW
                )
                db_session.add(order)

        await db_session.commit()

        # Get top by revenue
        top = await CustomerService.get_top_customers(db_session, limit=3, by="revenue")

        assert len(top) >= 2
        # Customer with i=2 should be first (3 orders × 3000 = 9000)
        assert top[0]["customer"].email == "revenue2@example.com"

    async def test_get_top_customers_by_order_count(self, db_session):
        """Test getting top customers by order count"""
        from goldsmith_erp.db.models import Order

        # Create customer with most orders
        customer_data = CustomerCreate(
            first_name="ManyOrders",
            last_name="Customer",
            email="manyorders@example.com",
            customer_type="private"
        )
        customer = await CustomerService.create_customer(db_session, customer_data)

        # Add 10 orders
        for i in range(10):
            order = Order(
                title=f"Order {i}",
                customer_id=customer.id,
                price=100.0,
                status=OrderStatusEnum.NEW
            )
            db_session.add(order)
        await db_session.commit()

        # Get top by orders
        top = await CustomerService.get_top_customers(db_session, limit=5, by="orders")

        assert len(top) >= 1
        # Our customer should be in top
        emails = [t["customer"].email for t in top]
        assert "manyorders@example.com" in emails

    async def test_get_top_customers_by_recent(self, db_session):
        """Test getting customers by most recent order"""
        from goldsmith_erp.db.models import Order

        # Create customer with recent order
        customer_data = CustomerCreate(
            first_name="Recent",
            last_name="Customer",
            email="recent@example.com",
            customer_type="private"
        )
        customer = await CustomerService.create_customer(db_session, customer_data)

        # Add recent order
        order = Order(
            title="Recent Order",
            customer_id=customer.id,
            price=100.0,
            status=OrderStatusEnum.NEW,
            created_at=datetime.utcnow()
        )
        db_session.add(order)
        await db_session.commit()

        # Get top by recent
        top = await CustomerService.get_top_customers(db_session, limit=5, by="recent")

        assert len(top) >= 1
        # Our customer should be first
        assert top[0]["customer"].email == "recent@example.com"

    async def test_top_customers_only_active(self, db_session, sample_customer):
        """Test that top customers only includes active customers"""
        from goldsmith_erp.db.models import Order

        # Add order to sample customer
        order = Order(
            title="Order",
            customer_id=sample_customer.id,
            price=10000.0,
            status=OrderStatusEnum.NEW
        )
        db_session.add(order)
        await db_session.commit()

        # Deactivate customer
        sample_customer.is_active = False
        await db_session.commit()

        # Get top by revenue - should not include inactive customer
        top = await CustomerService.get_top_customers(db_session, limit=5, by="revenue")

        customer_ids = [t["customer"].id for t in top]
        assert sample_customer.id not in customer_ids
