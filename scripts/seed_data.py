"""
Seed script for development data with GDPR compliance.

Run this script to populate the database with sample data for development.

Usage:
    poetry run python scripts/seed_data.py

Author: Claude AI (Updated for GDPR)
Date: 2025-11-06
"""
import asyncio
import sys
from pathlib import Path
from datetime import datetime, timedelta

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import select
from src.goldsmith_erp.core.config import settings
from src.goldsmith_erp.db.models import (
    User, Customer, Material, Order,
    DataRetentionPolicy, CustomerAuditLog
)
from src.goldsmith_erp.core.security import get_password_hash


async def seed_users(session: AsyncSession):
    """Create sample users (staff members)."""
    print("Creating users (staff)...")

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
        {
            "email": "manager@goldsmith.local",
            "hashed_password": get_password_hash("manager123"),
            "first_name": "Thomas",
            "last_name": "Müller",
            "role": "manager",
            "is_active": True,
        },
    ]

    for user_data in users_data:
        user = User(**user_data)
        session.add(user)

    await session.commit()
    print(f"✓ Created {len(users_data)} users (staff)")

    # Return admin user for relationships
    result = await session.execute(select(User).where(User.role == "admin"))
    return result.scalar_one()


async def seed_data_retention_policies(session: AsyncSession, admin: User):
    """Create default data retention policies (GDPR compliant)."""
    print("Creating data retention policies...")

    policies_data = [
        {
            "category": "customer_active",
            "retention_period_days": 3650,  # 10 years from last order
            "legal_basis": "GDPR Art. 6(1)(b) Contract + §147 AO German Tax Law",
            "jurisdiction": "DE",
            "action_after_expiry": "anonymize",
            "auto_apply": False,
            "warning_days_before": 30,
            "description": "Active customers with orders. Retention period starts from last order date. Required for tax compliance and contract obligations.",
            "is_active": True,
            "created_by": admin.id,
        },
        {
            "category": "customer_inactive",
            "retention_period_days": 730,  # 2 years without orders
            "legal_basis": "GDPR Art. 6(1)(f) Legitimate Interest",
            "jurisdiction": "EU",
            "action_after_expiry": "review",
            "auto_apply": False,
            "warning_days_before": 60,
            "description": "Customers without orders for 2 years. Review before deletion to check for legitimate business interest.",
            "is_active": True,
            "created_by": admin.id,
        },
        {
            "category": "financial_records",
            "retention_period_days": 3650,  # 10 years minimum
            "legal_basis": "§147 AO German Tax Law",
            "jurisdiction": "DE",
            "action_after_expiry": "anonymize",
            "auto_apply": True,
            "warning_days_before": 30,
            "description": "Financial records (invoices, payments) must be kept for 10 years per German tax law. Customer names anonymized after retention period.",
            "is_active": True,
            "created_by": admin.id,
        },
        {
            "category": "marketing_consent",
            "retention_period_days": 730,  # 2 years without activity
            "legal_basis": "GDPR Art. 6(1)(a) Consent",
            "jurisdiction": "EU",
            "action_after_expiry": "delete",
            "auto_apply": True,
            "warning_days_before": 14,
            "description": "Marketing consent expires after 2 years of inactivity. Consent must be renewed.",
            "is_active": True,
            "created_by": admin.id,
        },
        {
            "category": "audit_logs",
            "retention_period_days": 1095,  # 3 years minimum for GDPR
            "legal_basis": "GDPR Art. 30 Records of Processing Activities",
            "jurisdiction": "EU",
            "action_after_expiry": "archive",
            "auto_apply": False,
            "warning_days_before": 30,
            "description": "Audit logs must be kept for minimum 3 years for GDPR accountability. After that, archived to cold storage.",
            "is_active": True,
            "created_by": admin.id,
        },
        {
            "category": "gdpr_requests",
            "retention_period_days": 2555,  # 7 years (statute of limitations)
            "legal_basis": "GDPR Art. 12 Data Subject Rights + Legal Defense",
            "jurisdiction": "EU",
            "action_after_expiry": "archive",
            "auto_apply": False,
            "warning_days_before": 60,
            "description": "GDPR request records kept for 7 years for legal defense purposes in case of disputes.",
            "is_active": True,
            "created_by": admin.id,
        },
    ]

    for policy_data in policies_data:
        policy = DataRetentionPolicy(**policy_data)
        session.add(policy)

    await session.commit()
    print(f"✓ Created {len(policies_data)} data retention policies")


async def seed_customers(session: AsyncSession, admin: User):
    """Create sample customers (GDPR compliant)."""
    print("Creating customers...")

    current_date = datetime.utcnow()

    customers_data = [
        {
            "customer_number": f"CUST-{current_date.strftime('%Y%m')}-0001",
            "first_name": "Max",
            "last_name": "Mustermann",
            "email": "max.mustermann@example.de",
            "phone": "+49 123 456789",
            "address_line1": "Hauptstraße 123",
            "postal_code": "10115",
            "city": "Berlin",
            "country": "DE",
            # GDPR
            "legal_basis": "contract",
            "consent_marketing": True,
            "consent_date": current_date,
            "consent_version": "1.0",
            "consent_ip_address": "192.168.1.100",
            "consent_method": "web_form",
            "data_retention_category": "active",
            "last_order_date": current_date - timedelta(days=30),
            "retention_deadline": current_date + timedelta(days=3650),
            # Preferences
            "data_processing_consent": True,
            "email_communication_consent": True,
            "phone_communication_consent": True,
            "sms_communication_consent": False,
            # Audit
            "created_by": admin.id,
            "is_active": True,
            "notes": "VIP-Kunde, bevorzugt Express-Service",
            "tags": ["vip", "frequent"],
        },
        {
            "customer_number": f"CUST-{current_date.strftime('%Y%m')}-0002",
            "first_name": "Anna",
            "last_name": "Schmidt",
            "email": "anna.schmidt@example.de",
            "phone": "+49 987 654321",
            "address_line1": "Lindenallee 45",
            "postal_code": "80331",
            "city": "München",
            "country": "DE",
            # GDPR
            "legal_basis": "contract",
            "consent_marketing": False,
            "consent_date": current_date - timedelta(days=60),
            "consent_version": "1.0",
            "consent_ip_address": "192.168.1.101",
            "consent_method": "in_person",
            "data_retention_category": "active",
            "last_order_date": current_date - timedelta(days=60),
            "retention_deadline": current_date + timedelta(days=3650),
            # Preferences
            "data_processing_consent": True,
            "email_communication_consent": False,
            "phone_communication_consent": True,
            "sms_communication_consent": False,
            # Audit
            "created_by": admin.id,
            "is_active": True,
            "notes": "Möchte keine Marketing-E-Mails",
        },
        {
            "customer_number": f"CUST-{current_date.strftime('%Y%m')}-0003",
            "first_name": "Peter",
            "last_name": "Wagner",
            "email": "peter.wagner@example.de",
            "phone": "+49 555 123456",
            "address_line1": "Parkstraße 88",
            "postal_code": "50667",
            "city": "Köln",
            "country": "DE",
            # GDPR
            "legal_basis": "contract",
            "consent_marketing": True,
            "consent_date": current_date - timedelta(days=120),
            "consent_version": "1.0",
            "consent_ip_address": "192.168.1.102",
            "consent_method": "web_form",
            "data_retention_category": "active",
            "last_order_date": current_date - timedelta(days=90),
            "retention_deadline": current_date + timedelta(days=3650),
            # Preferences
            "data_processing_consent": True,
            "email_communication_consent": True,
            "phone_communication_consent": False,
            "sms_communication_consent": True,
            # Audit
            "created_by": admin.id,
            "is_active": True,
            "notes": "Großhändler, regelmäßige Großbestellungen",
            "tags": ["wholesale", "frequent"],
            "custom_fields": {"discount_rate": 15, "payment_terms": "net_30"},
        },
        {
            "customer_number": f"CUST-{current_date.strftime('%Y%m')}-0004",
            "first_name": "Julia",
            "last_name": "Becker",
            "email": "julia.becker@example.de",
            "phone": "+49 666 789012",
            "address_line1": "Rosenweg 12",
            "postal_code": "60311",
            "city": "Frankfurt",
            "country": "DE",
            # GDPR
            "legal_basis": "contract",
            "consent_marketing": False,
            "consent_date": current_date - timedelta(days=180),
            "consent_version": "1.0",
            "consent_ip_address": "192.168.1.103",
            "consent_method": "phone",
            "data_retention_category": "inactive",
            "last_order_date": current_date - timedelta(days=400),
            "retention_deadline": current_date + timedelta(days=330),  # Almost expired
            # Preferences
            "data_processing_consent": True,
            "email_communication_consent": False,
            "phone_communication_consent": False,
            "sms_communication_consent": False,
            # Audit
            "created_by": admin.id,
            "is_active": False,
            "notes": "Inaktiver Kunde, letzte Bestellung vor über einem Jahr",
        },
    ]

    created_customers = []
    for customer_data in customers_data:
        customer = Customer(**customer_data)
        session.add(customer)
        created_customers.append(customer)

    await session.commit()
    print(f"✓ Created {len(customers_data)} customers")

    return created_customers


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
        # Platinum
        {
            "name": "Platin 950",
            "material_type": "platinum",
            "description": "950er Platin",
            "unit_price": 68.00,
            "stock": 25.0,
            "unit": "g",
            "min_stock": 10.0,
            "properties": {"purity": 950},
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

    created_materials = []
    for material_data in materials_data:
        material = Material(**material_data)
        session.add(material)
        created_materials.append(material)

    await session.commit()
    print(f"✓ Created {len(materials_data)} materials")

    return created_materials


async def seed_orders(session: AsyncSession, customers: list, materials: list, admin: User):
    """Create sample orders linked to customers."""
    print("Creating orders...")

    current_date = datetime.utcnow()

    # Get specific materials for orders
    gold_585 = next((m for m in materials if "585" in m.name and m.material_type == "gold"), None)
    diamond_4mm = next((m for m in materials if "4.0mm" in m.name), None)
    silver = next((m for m in materials if m.material_type == "silver"), None)

    # Get customers
    customer_max = customers[0]
    customer_anna = customers[1]
    customer_peter = customers[2]

    orders_data = [
        {
            "order_number": f"ORDER-{current_date.strftime('%Y%m')}-0001",
            "title": "Goldring Reparatur",
            "description": "Ring reinigen und Stein ersetzen",
            "customer_id": customer_max.id,
            "subtotal": 150.00,
            "tax_rate": 19.0,
            "tax_amount": 28.50,
            "total_amount": 178.50,
            "price": 178.50,  # Legacy field
            "status": "in_progress",
            "workflow_state": "in_progress",
            "priority": "high",
            "notes": "Kunde möchte Express-Service",
            "delivery_date": current_date + timedelta(days=3),
            "started_at": current_date,
            "assigned_to": admin.id,  # Assigned to goldsmith
        },
        {
            "order_number": f"ORDER-{current_date.strftime('%Y%m')}-0002",
            "title": "Silberkette anfertigen",
            "description": "Silberkette 925er, 60cm, Venezianerkette",
            "customer_id": customer_anna.id,
            "subtotal": 280.00,
            "tax_rate": 19.0,
            "tax_amount": 53.20,
            "total_amount": 333.20,
            "price": 333.20,
            "status": "confirmed",
            "workflow_state": "confirmed",
            "priority": "normal",
            "delivery_date": current_date + timedelta(days=7),
        },
        {
            "order_number": f"ORDER-{current_date.strftime('%Y%m')}-0003",
            "title": "Ohrringe Paar mit Diamanten",
            "description": "Goldohrringe 585 mit zwei 4mm Diamanten VS",
            "customer_id": customer_max.id,
            "subtotal": 520.00,
            "tax_rate": 19.0,
            "tax_amount": 98.80,
            "total_amount": 618.80,
            "price": 618.80,
            "status": "completed",
            "workflow_state": "completed",
            "priority": "normal",
            "delivery_date": current_date - timedelta(days=5),
            "started_at": current_date - timedelta(days=12),
            "completed_at": current_date - timedelta(days=5),
            "delivered_at": current_date - timedelta(days=3),
            "assigned_to": admin.id,
        },
        {
            "order_number": f"ORDER-{current_date.strftime('%Y%m')}-0004",
            "title": "Verlobungsring Maßanfertigung",
            "description": "Weißgold 585, zentraler Diamant 4mm, Seitensteine",
            "customer_id": customer_peter.id,
            "subtotal": 1250.00,
            "tax_rate": 19.0,
            "tax_amount": 237.50,
            "total_amount": 1487.50,
            "price": 1487.50,
            "status": "draft",
            "workflow_state": "draft",
            "priority": "urgent",
            "delivery_date": current_date + timedelta(days=14),
            "notes": "Wichtig: Kunde kommt für Anprobe am nächsten Mittwoch",
        },
    ]

    for order_data in orders_data:
        order = Order(**order_data)

        # Add materials to specific orders
        if order.title == "Goldring Reparatur" and gold_585 and diamond_4mm:
            order.materials.append(gold_585)
            order.materials.append(diamond_4mm)
        elif order.title == "Silberkette anfertigen" and silver:
            order.materials.append(silver)
        elif order.title == "Ohrringe Paar mit Diamanten" and gold_585 and diamond_4mm:
            order.materials.append(gold_585)
            order.materials.append(diamond_4mm)

        session.add(order)

    await session.commit()
    print(f"✓ Created {len(orders_data)} orders")


async def seed_audit_logs(session: AsyncSession, customers: list, admin: User):
    """Create sample audit log entries."""
    print("Creating audit log entries...")

    current_date = datetime.utcnow()

    # Create audit logs for customer creation
    for customer in customers[:2]:  # First two customers
        audit_log = CustomerAuditLog(
            customer_id=customer.id,
            action="created",
            entity="customer",
            entity_id=customer.id,
            user_id=admin.id,
            user_email=admin.email,
            user_role=admin.role,
            timestamp=customer.created_at,
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            endpoint="/api/v1/customers",
            http_method="POST",
            request_id=f"req-{customer.id:06d}",
            legal_basis="contract",
            purpose="order_fulfillment",
            description=f"Customer {customer.first_name} {customer.last_name} created via web form",
        )
        session.add(audit_log)

    # Create consent given log
    customer_max = customers[0]
    consent_log = CustomerAuditLog(
        customer_id=customer_max.id,
        action="consent_given",
        entity="consent",
        user_id=admin.id,
        user_email=admin.email,
        user_role=admin.role,
        timestamp=current_date,
        ip_address="192.168.1.100",
        endpoint="/api/v1/customers/consents",
        http_method="PATCH",
        legal_basis="consent",
        purpose="marketing",
        description="Customer gave consent for marketing communications",
        metadata={"consent_types": ["marketing", "email"], "version": "1.0"},
    )
    session.add(consent_log)

    await session.commit()
    print(f"✓ Created sample audit log entries")


async def main():
    """Main seed function."""
    print("=" * 70)
    print("Starting GDPR-compliant database seeding...")
    print("=" * 70)

    # Create async engine
    engine = create_async_engine(
        str(settings.DATABASE_URL),
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
            # Seed in correct order due to foreign key dependencies
            admin = await seed_users(session)
            await seed_data_retention_policies(session, admin)
            customers = await seed_customers(session, admin)
            materials = await seed_materials(session)
            await seed_orders(session, customers, materials, admin)
            await seed_audit_logs(session, customers, admin)

            print("=" * 70)
            print("✓ Database seeding completed successfully!")
            print("=" * 70)
            print("\n📋 Sample Credentials (Staff):")
            print("  Admin:        admin@goldsmith.local / admin123")
            print("  Goldsmith:    goldsmith@goldsmith.local / goldsmith123")
            print("  Receptionist: receptionist@goldsmith.local / reception123")
            print("  Manager:      manager@goldsmith.local / manager123")

            print("\n👥 Sample Customers:")
            print("  Max Mustermann   (CUST-202511-0001) - VIP, active")
            print("  Anna Schmidt     (CUST-202511-0002) - Active")
            print("  Peter Wagner     (CUST-202511-0003) - Wholesale")
            print("  Julia Becker     (CUST-202511-0004) - Inactive")

            print("\n📦 Materials:")
            print("  11 materials (Gold, Silver, Platinum, Stones, Tools)")

            print("\n📋 Orders:")
            print("  4 orders in various states (draft, confirmed, in_progress, completed)")

            print("\n🔒 GDPR Compliance:")
            print("  ✓ 6 Data retention policies")
            print("  ✓ Customer audit logs")
            print("  ✓ Consent tracking")
            print("  ✓ All customers have legal basis documented")

        except Exception as e:
            print(f"\n✗ Error during seeding: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)

    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
