"""
Seed script for development data.

Run this script to populate the database with sample data for development.

Usage:
    poetry run python scripts/seed_data.py
"""
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from src.goldsmith_erp.core.config import settings
from src.goldsmith_erp.db.models import User, Material, Order
from src.goldsmith_erp.core.security import get_password_hash


async def seed_users(session: AsyncSession):
    """Create sample users."""
    print("Creating users...")

    users_data = [
        {
            "email": "admin@goldsmith.local",
            "hashed_password": get_password_hash("admin123"),
            "first_name": "Admin",
            "last_name": "User",
            "role": "admin",
            "is_active": True,
        },
        {
            "email": "goldsmith@goldsmith.local",
            "hashed_password": get_password_hash("goldsmith123"),
            "first_name": "Johann",
            "last_name": "Schmidt",
            "role": "goldsmith",
            "is_active": True,
        },
        {
            "email": "receptionist@goldsmith.local",
            "hashed_password": get_password_hash("reception123"),
            "first_name": "Maria",
            "last_name": "Klein",
            "role": "receptionist",
            "is_active": True,
        },
    ]

    for user_data in users_data:
        user = User(**user_data)
        session.add(user)

    await session.commit()
    print(f"✓ Created {len(users_data)} users")


async def seed_materials(session: AsyncSession):
    """Create sample materials."""
    print("Creating materials...")

    materials_data = [
        # Gold
        {
            "name": "Gold 333 (8kt)",
            "material_type": "gold",
            "description": "333er Gold, 8 Karat",
            "unit_price": 30.50,
            "stock": 150.0,
            "unit": "g",
            "min_stock": 50.0,
            "properties": {"purity": 333, "color": "yellow"},
        },
        {
            "name": "Gold 585 (14kt)",
            "material_type": "gold",
            "description": "585er Gold, 14 Karat",
            "unit_price": 45.80,
            "stock": 200.0,
            "unit": "g",
            "min_stock": 100.0,
            "properties": {"purity": 585, "color": "yellow"},
        },
        {
            "name": "Gold 750 (18kt)",
            "material_type": "gold",
            "description": "750er Gold, 18 Karat",
            "unit_price": 58.00,
            "stock": 100.0,
            "unit": "g",
            "min_stock": 50.0,
            "properties": {"purity": 750, "color": "yellow"},
        },
        {
            "name": "Weißgold 585",
            "material_type": "gold",
            "description": "585er Weißgold",
            "unit_price": 48.50,
            "stock": 75.0,
            "unit": "g",
            "min_stock": 30.0,
            "properties": {"purity": 585, "color": "white"},
        },
        # Silver
        {
            "name": "Silber 925 (Sterling)",
            "material_type": "silver",
            "description": "925er Sterlingsilber",
            "unit_price": 0.85,
            "stock": 500.0,
            "unit": "g",
            "min_stock": 200.0,
            "properties": {"purity": 925},
        },
        # Stones
        {
            "name": "Diamant 3.5mm VS",
            "material_type": "stone",
            "description": "Brillant 3.5mm, VS Qualität",
            "unit_price": 120.00,
            "stock": 5.0,
            "unit": "pcs",
            "min_stock": 2.0,
            "properties": {
                "size": 3.5,
                "color": "white",
                "quality": "VS",
                "shape": "brilliant",
            },
        },
        {
            "name": "Diamant 4.0mm VS",
            "material_type": "stone",
            "description": "Brillant 4.0mm, VS Qualität",
            "unit_price": 150.00,
            "stock": 3.0,
            "unit": "pcs",
            "min_stock": 2.0,
            "properties": {
                "size": 4.0,
                "color": "white",
                "quality": "VS",
                "shape": "brilliant",
            },
        },
        {
            "name": "Saphir 6mm blau",
            "material_type": "stone",
            "description": "Blauer Saphir 6mm",
            "unit_price": 350.00,
            "stock": 2.0,
            "unit": "pcs",
            "min_stock": 1.0,
            "properties": {
                "size": 6.0,
                "color": "blue",
                "quality": "AA",
                "shape": "oval",
            },
        },
        {
            "name": "Zirkonia 4mm",
            "material_type": "stone",
            "description": "Kubischer Zirkonia 4mm",
            "unit_price": 15.00,
            "stock": 20.0,
            "unit": "pcs",
            "min_stock": 10.0,
            "properties": {
                "size": 4.0,
                "color": "white",
                "shape": "brilliant",
            },
        },
        # Tools
        {
            "name": "Graviermaschine Spezial",
            "material_type": "tool",
            "description": "Spezial-Graviermaschine für Feinarbeit",
            "unit_price": 0.0,  # Tools don't have per-use price
            "stock": 1.0,
            "unit": "pcs",
            "min_stock": 1.0,
            "properties": {"type": "engraving", "model": "GX-2000"},
        },
    ]

    for material_data in materials_data:
        material = Material(**material_data)
        session.add(material)

    await session.commit()
    print(f"✓ Created {len(materials_data)} materials")


async def seed_orders(session: AsyncSession):
    """Create sample orders."""
    print("Creating orders...")

    # Get users and materials for relationships
    from sqlalchemy import select

    result = await session.execute(select(User).where(User.role == "admin"))
    admin = result.scalar_one()

    result = await session.execute(select(Material).where(Material.material_type == "gold"))
    gold_585 = result.scalars().first()

    result = await session.execute(select(Material).where(Material.name.like("%Diamant 4.0mm%")))
    diamond = result.scalar_one_or_none()

    orders_data = [
        {
            "title": "Goldring Reparatur",
            "description": "Ring reinigen und Stein ersetzen",
            "price": 180.00,
            "status": "new",
            "customer_id": admin.id,
            "notes": "Kunde möchte Express-Service",
        },
        {
            "title": "Kette anfertigen",
            "description": "Goldkette 585er, 50cm",
            "price": 450.00,
            "status": "in_progress",
            "customer_id": admin.id,
        },
        {
            "title": "Ohrringe Paar",
            "description": "Goldohrringe mit kleinen Diamanten",
            "price": 320.00,
            "status": "completed",
            "customer_id": admin.id,
        },
    ]

    for order_data in orders_data:
        order = Order(**order_data)

        # Add materials to first order
        if order_data["title"] == "Goldring Reparatur" and gold_585 and diamond:
            order.materials.append(gold_585)
            order.materials.append(diamond)

        session.add(order)

    await session.commit()
    print(f"✓ Created {len(orders_data)} orders")


async def main():
    """Main seed function."""
    print("=" * 50)
    print("Starting database seeding...")
    print("=" * 50)

    # Create async engine
    engine = create_async_engine(
        settings.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://"),
        echo=False,
    )

    # Create session
    async_session = async_sessionmaker(
        engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )

    async with async_session() as session:
        try:
            await seed_users(session)
            await seed_materials(session)
            await seed_orders(session)

            print("=" * 50)
            print("✓ Database seeding completed successfully!")
            print("=" * 50)
            print("\nSample credentials:")
            print("  Admin:        admin@goldsmith.local / admin123")
            print("  Goldsmith:    goldsmith@goldsmith.local / goldsmith123")
            print("  Receptionist: receptionist@goldsmith.local / reception123")

        except Exception as e:
            print(f"\n✗ Error during seeding: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
