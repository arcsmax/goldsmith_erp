"""
Unit tests for MaterialService

Tests cover:
- Material creation with validation
- Material retrieval (by ID, by name, listing with pagination)
- Material updates (including stock adjustments)
- Material search and filtering
- Material deletion
- Stock value calculations
- Error handling and edge cases
"""
import pytest
from decimal import Decimal

from goldsmith_erp.services.material_service import MaterialService
from goldsmith_erp.models.material import MaterialCreate, MaterialUpdate
from goldsmith_erp.db.models import Material


@pytest.mark.asyncio
class TestMaterialCreation:
    """Test material creation and validation"""

    async def test_create_material_success(self, db_session):
        """Test creating a material with all fields"""
        material_data = MaterialCreate(
            name="Gold Ring Setting",
            description="18K gold ring setting for 1ct stone",
            unit_price=45.50,
            stock=25.5,
            unit="Stück"
        )

        material = await MaterialService.create_material(db_session, material_data)

        assert material.id is not None
        assert material.name == "Gold Ring Setting"
        assert material.description == "18K gold ring setting for 1ct stone"
        assert float(material.unit_price) == 45.50
        assert float(material.stock) == 25.5
        assert material.unit == "Stück"

    async def test_create_material_minimal_fields(self, db_session):
        """Test creating material with only required fields"""
        material_data = MaterialCreate(
            name="Simple Clasp",
            unit_price=2.50,
            stock=100,
            unit="Stück"
        )

        material = await MaterialService.create_material(db_session, material_data)

        assert material.id is not None
        assert material.name == "Simple Clasp"
        assert material.description is None
        assert float(material.unit_price) == 2.50

    async def test_create_material_duplicate_name_allowed(self, db_session):
        """Test that duplicate names are allowed (no unique constraint)"""
        # Create first material
        material_data_1 = MaterialCreate(
            name="Standard Clasp",
            unit_price=5.00,
            stock=50,
            unit="Stück"
        )
        await MaterialService.create_material(db_session, material_data_1)

        # Create second material with same name (should succeed)
        material_data_2 = MaterialCreate(
            name="Standard Clasp",
            unit_price=6.00,
            stock=30,
            unit="Stück"
        )
        material_2 = await MaterialService.create_material(db_session, material_data_2)

        assert material_2.id is not None
        assert material_2.name == "Standard Clasp"
        assert float(material_2.unit_price) == 6.00

    async def test_create_material_zero_stock_allowed(self, db_session):
        """Test that zero stock is allowed"""
        material_data = MaterialCreate(
            name="Out of Stock Item",
            unit_price=10.00,
            stock=0,
            unit="g"
        )

        material = await MaterialService.create_material(db_session, material_data)

        assert material.id is not None
        assert float(material.stock) == 0

    async def test_create_material_decimal_values(self, db_session):
        """Test creating material with decimal prices and stock"""
        material_data = MaterialCreate(
            name="Precious Stone",
            unit_price=123.456,
            stock=7.89,
            unit="Stück"
        )

        material = await MaterialService.create_material(db_session, material_data)

        assert material.id is not None
        assert float(material.unit_price) == pytest.approx(123.456, 0.001)
        assert float(material.stock) == pytest.approx(7.89, 0.001)

    async def test_create_material_different_units(self, db_session):
        """Test creating materials with different unit types"""
        units_to_test = ["Stück", "g", "kg", "ml", "l", "cm", "m"]

        for i, unit in enumerate(units_to_test):
            material_data = MaterialCreate(
                name=f"Material {unit}",
                unit_price=10.00,
                stock=50,
                unit=unit
            )

            material = await MaterialService.create_material(db_session, material_data)

            assert material.unit == unit


@pytest.mark.asyncio
class TestMaterialRetrieval:
    """Test material retrieval operations"""

    async def test_get_material_by_id_success(self, db_session, sample_material):
        """Test retrieving existing material by ID"""
        material = await MaterialService.get_material_by_id(db_session, sample_material.id)

        assert material is not None
        assert material.id == sample_material.id
        assert material.name == sample_material.name
        assert float(material.unit_price) == float(sample_material.unit_price)

    async def test_get_material_by_id_not_found(self, db_session):
        """Test retrieving non-existent material returns None"""
        material = await MaterialService.get_material_by_id(db_session, 99999)

        assert material is None

    async def test_get_material_by_name_success(self, db_session, sample_material):
        """Test retrieving material by name"""
        material = await MaterialService.get_material_by_name(db_session, sample_material.name)

        assert material is not None
        assert material.id == sample_material.id
        assert material.name == sample_material.name

    async def test_get_material_by_name_not_found(self, db_session):
        """Test retrieving non-existent material by name returns None"""
        material = await MaterialService.get_material_by_name(db_session, "Nonexistent Material")

        assert material is None

    async def test_get_all_materials_empty(self, db_session):
        """Test getting materials from empty database"""
        materials = await MaterialService.get_materials(db_session)

        assert materials == []
        assert len(materials) == 0

    async def test_get_all_materials_returns_all(self, db_session):
        """Test that all materials are returned"""
        # Create 5 materials
        for i in range(5):
            material_data = MaterialCreate(
                name=f"Material {i}",
                unit_price=10.00 + i,
                stock=50,
                unit="Stück"
            )
            await MaterialService.create_material(db_session, material_data)

        materials = await MaterialService.get_materials(db_session)

        assert len(materials) == 5
        # Materials should be sorted by name
        assert materials[0].name == "Material 0"
        assert materials[4].name == "Material 4"

    async def test_get_materials_with_pagination(self, db_session):
        """Test pagination with skip and limit"""
        # Create 10 materials
        for i in range(10):
            material_data = MaterialCreate(
                name=f"Material {i:02d}",  # Zero-padded for correct sorting
                unit_price=10.00,
                stock=50,
                unit="Stück"
            )
            await MaterialService.create_material(db_session, material_data)

        # Get first page (limit 5)
        page_1 = await MaterialService.get_materials(db_session, skip=0, limit=5)
        assert len(page_1) == 5
        assert page_1[0].name == "Material 00"

        # Get second page
        page_2 = await MaterialService.get_materials(db_session, skip=5, limit=5)
        assert len(page_2) == 5
        assert page_2[0].name == "Material 05"

        # Verify no overlap
        page_1_ids = {m.id for m in page_1}
        page_2_ids = {m.id for m in page_2}
        assert len(page_1_ids.intersection(page_2_ids)) == 0

    async def test_get_materials_ordered_by_name(self, db_session):
        """Test that materials are returned ordered by name"""
        # Create materials in random order
        names = ["Zebra", "Alpha", "Bravo", "Charlie"]
        for name in names:
            material_data = MaterialCreate(
                name=name,
                unit_price=10.00,
                stock=50,
                unit="Stück"
            )
            await MaterialService.create_material(db_session, material_data)

        materials = await MaterialService.get_materials(db_session)

        # Should be sorted alphabetically
        material_names = [m.name for m in materials]
        assert material_names == ["Alpha", "Bravo", "Charlie", "Zebra"]


@pytest.mark.asyncio
class TestMaterialUpdate:
    """Test material update operations"""

    async def test_update_material_name(self, db_session, sample_material):
        """Test updating material name"""
        original_price = sample_material.unit_price
        update_data = MaterialUpdate(name="Updated Material Name")

        updated = await MaterialService.update_material(
            db_session, sample_material.id, update_data
        )

        assert updated is not None
        assert updated.name == "Updated Material Name"
        assert updated.id == sample_material.id
        assert float(updated.unit_price) == float(original_price)  # Unchanged

    async def test_update_material_price(self, db_session, sample_material):
        """Test updating material price"""
        original_price = float(sample_material.unit_price)
        new_price = original_price + 10.00
        update_data = MaterialUpdate(unit_price=new_price)

        updated = await MaterialService.update_material(
            db_session, sample_material.id, update_data
        )

        assert updated is not None
        assert float(updated.unit_price) == new_price
        assert updated.name == sample_material.name  # Unchanged

    async def test_update_material_stock_directly(self, db_session, sample_material):
        """Test updating stock directly via update"""
        new_stock = 75.5
        update_data = MaterialUpdate(stock=new_stock)

        updated = await MaterialService.update_material(
            db_session, sample_material.id, update_data
        )

        assert updated is not None
        assert float(updated.stock) == new_stock

    async def test_update_material_multiple_fields(self, db_session, sample_material):
        """Test updating multiple fields at once"""
        update_data = MaterialUpdate(
            name="New Name",
            description="New Description",
            unit_price=99.99,
            stock=200
        )

        updated = await MaterialService.update_material(
            db_session, sample_material.id, update_data
        )

        assert updated is not None
        assert updated.name == "New Name"
        assert updated.description == "New Description"
        assert float(updated.unit_price) == 99.99
        assert float(updated.stock) == 200

    async def test_update_material_partial_update(self, db_session, sample_material):
        """Test that partial updates only change specified fields"""
        original_name = sample_material.name
        original_stock = sample_material.stock

        # Only update price
        update_data = MaterialUpdate(unit_price=555.55)

        updated = await MaterialService.update_material(
            db_session, sample_material.id, update_data
        )

        assert updated is not None
        assert float(updated.unit_price) == 555.55
        assert updated.name == original_name  # Unchanged
        assert float(updated.stock) == float(original_stock)  # Unchanged

    async def test_update_material_not_found(self, db_session):
        """Test updating non-existent material returns None"""
        update_data = MaterialUpdate(name="New Name")

        updated = await MaterialService.update_material(db_session, 99999, update_data)

        assert updated is None


@pytest.mark.asyncio
class TestStockAdjustment:
    """Test stock adjustment operations"""

    async def test_adjust_stock_add(self, db_session, sample_material):
        """Test adding stock"""
        original_stock = float(sample_material.stock)
        quantity_to_add = 10.0

        updated = await MaterialService.adjust_stock(
            db_session, sample_material.id, quantity_to_add, operation="add"
        )

        assert updated is not None
        assert float(updated.stock) == original_stock + quantity_to_add

    async def test_adjust_stock_subtract(self, db_session, sample_material):
        """Test subtracting stock"""
        # Ensure material has enough stock
        sample_material.stock = 50.0
        await db_session.commit()

        quantity_to_remove = 15.0

        updated = await MaterialService.adjust_stock(
            db_session, sample_material.id, quantity_to_remove, operation="subtract"
        )

        assert updated is not None
        assert float(updated.stock) == 35.0

    async def test_adjust_stock_prevent_negative(self, db_session, sample_material):
        """Test that stock cannot go negative"""
        # Set material stock to 10
        sample_material.stock = 10.0
        await db_session.commit()

        # Try to subtract 15 (would result in -5)
        with pytest.raises(ValueError, match="Stock cannot be negative"):
            await MaterialService.adjust_stock(
                db_session, sample_material.id, 15.0, operation="subtract"
            )

    async def test_adjust_stock_invalid_operation(self, db_session, sample_material):
        """Test that invalid operation raises error"""
        with pytest.raises(ValueError, match="Invalid operation"):
            await MaterialService.adjust_stock(
                db_session, sample_material.id, 10.0, operation="invalid"
            )

    async def test_adjust_stock_material_not_found(self, db_session):
        """Test adjusting stock for non-existent material returns None"""
        result = await MaterialService.adjust_stock(
            db_session, 99999, 10.0, operation="add"
        )

        assert result is None

    async def test_adjust_stock_to_exactly_zero(self, db_session, sample_material):
        """Test that stock can be adjusted to exactly zero"""
        # Set material stock to 25
        sample_material.stock = 25.0
        await db_session.commit()

        # Subtract exactly 25
        updated = await MaterialService.adjust_stock(
            db_session, sample_material.id, 25.0, operation="subtract"
        )

        assert updated is not None
        assert float(updated.stock) == 0.0


@pytest.mark.asyncio
class TestMaterialSearch:
    """Test material search and filtering"""

    async def test_get_low_stock_materials(self, db_session):
        """Test filtering materials by low stock threshold"""
        # Create materials with varying stock levels
        materials_data = [
            ("Low Stock 1", 5.0),
            ("Low Stock 2", 8.0),
            ("Normal Stock", 50.0),
            ("High Stock", 500.0)
        ]

        for name, stock in materials_data:
            material_data = MaterialCreate(
                name=name,
                unit_price=10.00,
                stock=stock,
                unit="Stück"
            )
            await MaterialService.create_material(db_session, material_data)

        # Get materials with stock <= 10
        low_stock = await MaterialService.get_low_stock_materials(db_session, threshold=10.0)

        assert len(low_stock) == 2
        assert all(float(m.stock) <= 10.0 for m in low_stock)
        # Should be ordered by stock ascending
        assert float(low_stock[0].stock) <= float(low_stock[1].stock)

    async def test_get_low_stock_materials_empty(self, db_session):
        """Test low stock filter with no results"""
        # Create material with high stock
        material_data = MaterialCreate(
            name="High Stock Item",
            unit_price=10.00,
            stock=1000.0,
            unit="Stück"
        )
        await MaterialService.create_material(db_session, material_data)

        low_stock = await MaterialService.get_low_stock_materials(db_session, threshold=5.0)

        assert len(low_stock) == 0

    async def test_get_low_stock_materials_custom_threshold(self, db_session):
        """Test low stock filter with custom threshold"""
        # Create materials
        for i in range(5):
            material_data = MaterialCreate(
                name=f"Material {i}",
                unit_price=10.00,
                stock=i * 10.0,  # 0, 10, 20, 30, 40
                unit="Stück"
            )
            await MaterialService.create_material(db_session, material_data)

        # Threshold 25 should return materials with stock 0, 10, 20
        low_stock = await MaterialService.get_low_stock_materials(db_session, threshold=25.0)

        assert len(low_stock) == 3
        assert all(float(m.stock) <= 25.0 for m in low_stock)

    async def test_get_low_stock_includes_equal_threshold(self, db_session):
        """Test that low stock filter includes materials exactly at threshold"""
        # Create material with stock exactly at threshold
        material_data = MaterialCreate(
            name="Exactly Threshold",
            unit_price=10.00,
            stock=10.0,
            unit="Stück"
        )
        material = await MaterialService.create_material(db_session, material_data)

        low_stock = await MaterialService.get_low_stock_materials(db_session, threshold=10.0)

        assert len(low_stock) == 1
        assert low_stock[0].id == material.id


@pytest.mark.asyncio
class TestMaterialDeletion:
    """Test material deletion operations"""

    async def test_delete_material_success(self, db_session, sample_material):
        """Test deleting an existing material"""
        material_id = sample_material.id

        result = await MaterialService.delete_material(db_session, material_id)

        assert result["success"] is True
        assert "deleted successfully" in result["message"]

        # Verify material is deleted
        deleted = await MaterialService.get_material_by_id(db_session, material_id)
        assert deleted is None

    async def test_delete_material_not_found(self, db_session):
        """Test deleting non-existent material"""
        result = await MaterialService.delete_material(db_session, 99999)

        assert result["success"] is False
        assert "not found" in result["message"]

    async def test_delete_material_multiple_times(self, db_session, sample_material):
        """Test that deleting same material twice returns not found"""
        material_id = sample_material.id

        # First deletion
        result_1 = await MaterialService.delete_material(db_session, material_id)
        assert result_1["success"] is True

        # Second deletion attempt
        result_2 = await MaterialService.delete_material(db_session, material_id)
        assert result_2["success"] is False
        assert "not found" in result_2["message"]

    async def test_delete_all_materials(self, db_session):
        """Test deleting multiple materials"""
        # Create 3 materials
        materials = []
        for i in range(3):
            material_data = MaterialCreate(
                name=f"Material {i}",
                unit_price=10.00,
                stock=50,
                unit="Stück"
            )
            material = await MaterialService.create_material(db_session, material_data)
            materials.append(material)

        # Delete all
        for material in materials:
            result = await MaterialService.delete_material(db_session, material.id)
            assert result["success"] is True

        # Verify all deleted
        remaining = await MaterialService.get_materials(db_session)
        assert len(remaining) == 0


@pytest.mark.asyncio
class TestStockCalculations:
    """Test stock value calculations"""

    async def test_calculate_total_stock_value(self, db_session):
        """Test calculating total stock value"""
        # Create materials with known values
        materials_data = [
            ("Material 1", 10.00, 5.0),    # Value: 50.00
            ("Material 2", 25.00, 10.0),   # Value: 250.00
            ("Material 3", 100.00, 2.0),   # Value: 200.00
        ]

        for name, price, stock in materials_data:
            material_data = MaterialCreate(
                name=name,
                unit_price=price,
                stock=stock,
                unit="Stück"
            )
            await MaterialService.create_material(db_session, material_data)

        total_value = await MaterialService.calculate_total_stock_value(db_session)

        # Total should be 50 + 250 + 200 = 500.00
        assert float(total_value) == pytest.approx(500.00, 0.01)

    async def test_calculate_total_stock_value_empty(self, db_session):
        """Test calculating total value with no materials"""
        total_value = await MaterialService.calculate_total_stock_value(db_session)

        assert float(total_value) == 0.0

    async def test_calculate_total_stock_value_with_zero_stock(self, db_session):
        """Test that materials with zero stock contribute zero value"""
        materials_data = [
            ("In Stock", 50.00, 10.0),     # Value: 500.00
            ("Out of Stock", 100.00, 0.0), # Value: 0.00
        ]

        for name, price, stock in materials_data:
            material_data = MaterialCreate(
                name=name,
                unit_price=price,
                stock=stock,
                unit="Stück"
            )
            await MaterialService.create_material(db_session, material_data)

        total_value = await MaterialService.calculate_total_stock_value(db_session)

        assert float(total_value) == pytest.approx(500.00, 0.01)

    async def test_calculate_individual_material_value(self, db_session, sample_material):
        """Test calculating value for individual material"""
        # Set known values
        sample_material.unit_price = 15.50
        sample_material.stock = 20.0
        await db_session.commit()

        # Expected value: 15.50 * 20 = 310.00
        expected_value = float(sample_material.unit_price) * float(sample_material.stock)

        assert expected_value == pytest.approx(310.00, 0.01)


@pytest.mark.asyncio
class TestEdgeCases:
    """Test edge cases and error scenarios"""

    async def test_large_stock_value(self, db_session):
        """Test handling large stock quantities"""
        material_data = MaterialCreate(
            name="Bulk Material",
            unit_price=1.00,
            stock=1000000.0,  # One million units
            unit="g"
        )

        material = await MaterialService.create_material(db_session, material_data)

        assert material is not None
        assert float(material.stock) == 1000000.0

    async def test_very_small_price(self, db_session):
        """Test handling very small prices"""
        material_data = MaterialCreate(
            name="Cheap Material",
            unit_price=0.01,  # 1 cent
            stock=100.0,
            unit="Stück"
        )

        material = await MaterialService.create_material(db_session, material_data)

        assert material is not None
        assert float(material.unit_price) == pytest.approx(0.01, 0.001)

    async def test_update_empty_fields(self, db_session, sample_material):
        """Test that updating with no fields returns unchanged material"""
        update_data = MaterialUpdate()

        updated = await MaterialService.update_material(
            db_session, sample_material.id, update_data
        )

        assert updated is not None
        assert updated.id == sample_material.id
        # All fields should be unchanged
        assert updated.name == sample_material.name
