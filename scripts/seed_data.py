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
from goldsmith_erp.core.config import settings
from goldsmith_erp.db.models import (
    User,
    Customer,
    Material,
    Order,
    # Extended seeder coverage (2026-04-24):
    Activity,
    TimeEntry,
    MetalPurchase,
    CustomMetalType,
    Invoice,
    InvoiceLineItem,
    Quote,
    QuoteLineItem,
    RepairJob,
    ScrapGold,
    ScrapGoldItem,
    ValuationCertificate,
    Gemstone,
)
from goldsmith_erp.core.security import get_password_hash

# Optional GDPR models — present only after GDPR schema migration
try:
    from goldsmith_erp.db.models import DataRetentionPolicy, CustomerAuditLog
    _GDPR_MODELS_AVAILABLE = True
except ImportError:
    DataRetentionPolicy = None  # type: ignore[assignment,misc]
    CustomerAuditLog = None  # type: ignore[assignment,misc]
    _GDPR_MODELS_AVAILABLE = False


async def seed_users(session: AsyncSession):
    """Create sample users (staff members).

    Idempotent: skips users whose email already exists. Only the 3 canonical
    roles are used (admin / goldsmith / viewer) — the UserRole enum after
    the RBAC migration does not include the pre-V1 `receptionist` / `manager`
    values.
    """
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
            "email": "goldsmith2@goldsmith.local",
            "hashed_password": get_password_hash("goldsmith123"),
            "first_name": "Maria",
            "last_name": "Klein",
            "role": "goldsmith",
            "is_active": True,
        },
        {
            "email": "viewer@goldsmith.local",
            "hashed_password": get_password_hash("viewer123"),
            "first_name": "Thomas",
            "last_name": "Müller",
            "role": "viewer",
            "is_active": True,
        },
    ]

    created = 0
    for user_data in users_data:
        # Idempotency — skip if email already exists (seeder re-runs are normal)
        existing = await session.execute(
            select(User).where(User.email == user_data["email"])
        )
        if existing.scalar_one_or_none() is not None:
            continue
        session.add(User(**user_data))
        created += 1

    if created > 0:
        await session.commit()
    print(f"✓ Users: {created} new / {len(users_data) - created} already existed")

    # Return admin user for relationships
    result = await session.execute(
        select(User).where(User.email == "admin@goldsmith.local")
    )
    return result.scalar_one()


async def seed_data_retention_policies(session: AsyncSession, admin: User):
    """Create default data retention policies (GDPR compliant).

    NOTE: Skipped when GDPR models are not yet migrated (DataRetentionPolicy absent).
    """
    if not _GDPR_MODELS_AVAILABLE or DataRetentionPolicy is None:
        print("⚠ Skipping data retention policies (GDPR schema migration not applied)")
        return

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


def _filter_model_fields(model_cls, data: dict) -> dict:
    """Return only fields that exist as columns on the given ORM model.

    Forward-compatible seeding pattern: the seed data dict may include
    aspirational fields (GDPR consent columns, retention metadata, enum
    values that moved) that the live schema hasn't caught up with. We
    silently drop anything the model doesn't declare.
    """
    valid_columns = {col.key for col in model_cls.__table__.columns}
    return {k: v for k, v in data.items() if k in valid_columns}


def _filter_customer_fields(data: dict) -> dict:
    """Back-compat shim — use _filter_model_fields(Customer, data) for new code."""
    return _filter_model_fields(Customer, data)


async def seed_customers(session: AsyncSession, admin: User):
    """Create sample customers (GDPR compliant where schema supports it)."""
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
            # GDPR — present only after GDPR schema migration
            "legal_basis": "contract",
            "consent_marketing": True,
            "consent_date": current_date,
            "consent_version": "1.0",
            "consent_ip_address": "192.168.1.100",
            "consent_method": "web_form",
            "data_retention_category": "active",
            "last_order_date": current_date - timedelta(days=30),
            "retention_deadline": current_date + timedelta(days=3650),
            "data_processing_consent": True,
            "email_communication_consent": True,
            "phone_communication_consent": True,
            "sms_communication_consent": False,
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
            "legal_basis": "contract",
            "consent_marketing": False,
            "consent_date": current_date - timedelta(days=60),
            "consent_version": "1.0",
            "consent_ip_address": "192.168.1.101",
            "consent_method": "in_person",
            "data_retention_category": "active",
            "last_order_date": current_date - timedelta(days=60),
            "retention_deadline": current_date + timedelta(days=3650),
            "data_processing_consent": True,
            "email_communication_consent": False,
            "phone_communication_consent": True,
            "sms_communication_consent": False,
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
            "legal_basis": "contract",
            "consent_marketing": True,
            "consent_date": current_date - timedelta(days=120),
            "consent_version": "1.0",
            "consent_ip_address": "192.168.1.102",
            "consent_method": "web_form",
            "data_retention_category": "active",
            "last_order_date": current_date - timedelta(days=90),
            "retention_deadline": current_date + timedelta(days=3650),
            "data_processing_consent": True,
            "email_communication_consent": True,
            "phone_communication_consent": False,
            "sms_communication_consent": True,
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
            "legal_basis": "contract",
            "consent_marketing": False,
            "consent_date": current_date - timedelta(days=180),
            "consent_version": "1.0",
            "consent_ip_address": "192.168.1.103",
            "consent_method": "phone",
            "data_retention_category": "inactive",
            "last_order_date": current_date - timedelta(days=400),
            "retention_deadline": current_date + timedelta(days=330),
            "data_processing_consent": True,
            "email_communication_consent": False,
            "phone_communication_consent": False,
            "sms_communication_consent": False,
            "created_by": admin.id,
            "is_active": False,
            "notes": "Inaktiver Kunde, letzte Bestellung vor über einem Jahr",
        },
    ]

    # Import the HMAC blind-index helper so we can check existing rows by the
    # same hash the ORM event hooks will compute on insert. (C1 added this.)
    from goldsmith_erp.core.encryption import hmac_blind_index

    created_customers = []
    new_count = 0
    skip_count = 0
    for customer_data in customers_data:
        # Idempotency — lookup by email_hash (the only searchable PII column
        # post-C1 encryption; plaintext ilike on `email` cannot work against
        # Fernet ciphertext).
        if customer_data.get("email"):
            email_hash = hmac_blind_index(customer_data["email"])
            existing = await session.execute(
                select(Customer).where(Customer.email_hash == email_hash)
            )
            already = existing.scalar_one_or_none()
            if already is not None:
                created_customers.append(already)
                skip_count += 1
                continue

        # Filter to fields actually on the current Customer model
        filtered = _filter_model_fields(Customer, customer_data)
        customer = Customer(**filtered)
        session.add(customer)
        created_customers.append(customer)
        new_count += 1

    if new_count > 0:
        await session.commit()
    print(f"✓ Customers: {new_count} new / {skip_count} already existed")

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
    skipped = 0
    for material_data in materials_data:
        # Idempotency — materials are keyed by name (no explicit uniqueness, but
        # re-seeding with the same names is a mistake, not an upsert).
        existing = await session.execute(
            select(Material).where(Material.name == material_data["name"])
        )
        already = existing.scalar_one_or_none()
        if already is not None:
            created_materials.append(already)
            skipped += 1
            continue
        filtered = _filter_model_fields(Material, material_data)
        material = Material(**filtered)
        session.add(material)
        created_materials.append(material)

    if len(created_materials) - skipped > 0:
        await session.commit()
    print(
        f"✓ Materials: {len(created_materials) - skipped} new / {skipped} already existed"
    )

    return created_materials


async def seed_orders(session: AsyncSession, customers: list, materials: list, admin: User):
    """Create sample orders linked to customers."""
    print("Creating orders...")

    current_date = datetime.utcnow()

    # Get specific materials for orders.
    # Material model no longer has `material_type` — filter by name substring.
    gold_585 = next((m for m in materials if "585" in m.name and "Gold" in m.name), None)
    diamond_4mm = next((m for m in materials if "4.0mm" in m.name), None)
    silver = next((m for m in materials if "Silber" in m.name or "silver" in m.name.lower()), None)

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

    # Idempotency: if any orders already exist for these customers, skip.
    existing_q = await session.execute(
        select(Order).where(Order.customer_id.in_([c.id for c in customers[:3]])).limit(1)
    )
    if existing_q.scalar_one_or_none() is not None:
        print("✓ Orders: already seeded — skipping")
        return

    new_count = 0
    for order_data in orders_data:
        # Filter to fields the current Order model actually has.
        # Pre-V1 fields like `order_number`, `subtotal`, `tax_amount`,
        # `workflow_state`, `priority`, `delivery_date`, `started_at`,
        # `assigned_to`, `notes`, `total_amount` are silently dropped.
        filtered = _filter_model_fields(Order, order_data)
        order = Order(**filtered)

        # Add materials to specific orders (uses the post-filter title)
        if order.title == "Goldring Reparatur" and gold_585 and diamond_4mm:
            order.materials.append(gold_585)
            order.materials.append(diamond_4mm)
        elif order.title == "Silberkette anfertigen" and silver:
            order.materials.append(silver)
        elif order.title == "Ohrringe Paar mit Diamanten" and gold_585 and diamond_4mm:
            order.materials.append(gold_585)
            order.materials.append(diamond_4mm)

        session.add(order)
        new_count += 1

    await session.commit()
    print(f"✓ Orders: {new_count} new")


async def seed_audit_logs(session: AsyncSession, customers: list, admin: User):
    """Create sample audit log entries.

    NOTE: Skipped when GDPR models are not yet migrated (CustomerAuditLog absent).
    """
    if not _GDPR_MODELS_AVAILABLE or CustomerAuditLog is None:
        print("⚠ Skipping audit log entries (GDPR schema migration not applied)")
        return

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


# ---------------------------------------------------------------------------
# Extended seed coverage (added 2026-04-24)
# Each function is idempotent (no-op if already seeded), uses
# _filter_model_fields for forward/backward compatibility, and emits the
# same "✓ <entity>: N new / M existed" status line.
# ---------------------------------------------------------------------------

async def seed_activities(session: AsyncSession, admin: User):
    """Time-tracking activity presets used at the bench."""
    print("Creating activities...")
    presets = [
        {"name": "Löten", "category": "fabrication", "icon": "🔥", "color": "#FF6B6B"},
        {"name": "Polieren", "category": "fabrication", "icon": "✨", "color": "#FFD93D"},
        {"name": "Fassen", "category": "fabrication", "icon": "💎", "color": "#4ECDC4"},
        {"name": "Feilen", "category": "fabrication", "icon": "🛠", "color": "#95A5A6"},
        {"name": "Gravieren", "category": "fabrication", "icon": "✒", "color": "#6C5CE7"},
        {"name": "Kundengespräch", "category": "administration", "icon": "💬", "color": "#00B894"},
        {"name": "Dokumentation", "category": "administration", "icon": "📝", "color": "#74B9FF"},
        {"name": "Warten auf Material", "category": "waiting", "icon": "⏳", "color": "#A29BFE"},
    ]
    new_count = 0
    skipped = 0
    for data in presets:
        existing = await session.execute(select(Activity).where(Activity.name == data["name"]))
        if existing.scalar_one_or_none() is not None:
            skipped += 1
            continue
        session.add(Activity(**_filter_model_fields(Activity, {**data, "created_by": admin.id})))
        new_count += 1
    if new_count:
        await session.commit()
    print(f"✓ Activities: {new_count} new / {skipped} already existed")


async def seed_time_entries(session: AsyncSession, admin: User):
    """A handful of time entries attached to existing orders + activities."""
    print("Creating time entries...")
    from datetime import datetime, timedelta
    # Grab first 2 orders + first 3 activities
    orders_q = await session.execute(select(Order).order_by(Order.id).limit(2))
    orders = list(orders_q.scalars())
    activities_q = await session.execute(select(Activity).order_by(Activity.id).limit(3))
    activities = list(activities_q.scalars())
    if not orders or not activities:
        print("⚠ Skipping time entries (no orders/activities)")
        return

    # Idempotency — skip if any time_entry exists for the first order
    existing = await session.execute(select(TimeEntry).where(TimeEntry.order_id == orders[0].id).limit(1))
    if existing.scalar_one_or_none() is not None:
        print("✓ Time entries: already seeded — skipping")
        return

    now = datetime.utcnow()
    entries = [
        {"order_id": orders[0].id, "user_id": admin.id, "activity_id": activities[0].id,
         "start_time": now - timedelta(hours=3), "end_time": now - timedelta(hours=2, minutes=15),
         "duration_minutes": 45, "notes": "Ringreparatur — Löten + Anprobe"},
        {"order_id": orders[0].id, "user_id": admin.id, "activity_id": activities[1].id,
         "start_time": now - timedelta(hours=2), "end_time": now - timedelta(hours=1, minutes=30),
         "duration_minutes": 30, "notes": "Polieren Hochglanz"},
        {"order_id": orders[1].id, "user_id": admin.id, "activity_id": activities[2].id,
         "start_time": now - timedelta(days=1, hours=2),
         "end_time": now - timedelta(days=1, hours=1), "duration_minutes": 60,
         "notes": "Stein gefasst"},
    ]
    for data in entries:
        session.add(TimeEntry(**_filter_model_fields(TimeEntry, data)))
    await session.commit()
    print(f"✓ Time entries: {len(entries)} new")


async def seed_valuations(session: AsyncSession, admin: User):
    """Insurance valuation certificates — tests C3 encryption."""
    print("Creating valuations (tests C3 encryption)...")
    orders_q = await session.execute(select(Order).order_by(Order.id).limit(2))
    orders = list(orders_q.scalars())
    if not orders:
        print("⚠ Skipping valuations (no orders)")
        return

    from datetime import datetime, timedelta
    now = datetime.utcnow()
    certs = [
        {"certificate_number": "WG-2026-0001", "order_id": orders[0].id,
         "customer_id": orders[0].customer_id, "created_by": admin.id,
         "item_description": "Damenring, Gelbgold 750, 1 Brillant 0.35ct VS1",
         "metal_type": "Gelbgold 750", "metal_weight_g": 4.2, "metal_purity": "750",
         "appraised_value": 1850.00, "valuation_date": now,
         "valid_until": now + timedelta(days=730),
         "goldsmith_name": "Johann Schmidt", "goldsmith_qualification": "Goldschmiedemeister"},
        {"certificate_number": "WG-2026-0002", "order_id": orders[1].id,
         "customer_id": orders[1].customer_id, "created_by": admin.id,
         "item_description": "Silberkette 925, 60cm, Venezianermuster",
         "metal_type": "Sterlingsilber 925", "metal_weight_g": 18.5, "metal_purity": "925",
         "appraised_value": 420.00, "valuation_date": now,
         "valid_until": now + timedelta(days=730),
         "goldsmith_name": "Johann Schmidt", "goldsmith_qualification": "Goldschmiedemeister"},
    ]
    new_count = 0
    skipped = 0
    for data in certs:
        existing = await session.execute(
            select(ValuationCertificate).where(
                ValuationCertificate.certificate_number == data["certificate_number"]
            )
        )
        if existing.scalar_one_or_none() is not None:
            skipped += 1
            continue
        # ValuationCertificate uses a property-setter to populate cipher + hmac.
        # `appraised_value` is the @property alias — the column is bound as
        # `_appraised_value_cipher`, so _filter_model_fields would drop it.
        # Strip it from the dict and assign via the setter after construction.
        appraised = data.pop("appraised_value")
        filtered = _filter_model_fields(ValuationCertificate, data)
        cert = ValuationCertificate(**filtered)
        cert.appraised_value = appraised  # triggers EncryptedString + HMAC auto-populate
        session.add(cert)
        new_count += 1
    if new_count:
        await session.commit()
    print(f"✓ Valuations: {new_count} new / {skipped} already existed")


async def seed_invoices(session: AsyncSession, admin: User):
    """Sample invoices — tests C6 financial audit logging when fetched."""
    print("Creating invoices...")
    orders_q = await session.execute(select(Order).order_by(Order.id).limit(2))
    orders = list(orders_q.scalars())
    if not orders:
        print("⚠ Skipping invoices (no orders)")
        return

    from datetime import datetime, timedelta
    now = datetime.utcnow()
    invoices_data = [
        {"invoice_number": "RE-2026-0001", "order_id": orders[0].id,
         "customer_id": orders[0].customer_id, "created_by": admin.id,
         "status": "paid", "issue_date": now - timedelta(days=14),
         "due_date": now + timedelta(days=16), "paid_date": now - timedelta(days=2),
         "subtotal": 150.00, "tax_rate": 19.0, "tax_amount": 28.50, "total": 178.50,
         "payment_method": "Überweisung", "notes": "Dankeschön für den Auftrag."},
        {"invoice_number": "RE-2026-0002", "order_id": orders[1].id,
         "customer_id": orders[1].customer_id, "created_by": admin.id,
         "status": "sent", "issue_date": now - timedelta(days=3),
         "due_date": now + timedelta(days=27),
         "subtotal": 280.00, "tax_rate": 19.0, "tax_amount": 53.20, "total": 333.20,
         "payment_method": None},
    ]
    new_count = 0
    skipped = 0
    for data in invoices_data:
        existing = await session.execute(
            select(Invoice).where(Invoice.invoice_number == data["invoice_number"])
        )
        if existing.scalar_one_or_none() is not None:
            skipped += 1
            continue
        inv = Invoice(**_filter_model_fields(Invoice, data))
        session.add(inv)
        new_count += 1
    if new_count:
        await session.commit()
    print(f"✓ Invoices: {new_count} new / {skipped} already existed")


async def seed_metal_purchases(session: AsyncSession, admin: User):
    """Metal inventory purchases — stocks the workshop's precious-metal ledger."""
    print("Creating metal purchases...")
    from datetime import datetime, timedelta
    now = datetime.utcnow()
    # metaltype enum values per migration: gold_24k/22k/18k/14k/9k,
    # silver_999/925/800, platinum_950/900, palladium, white_gold_18k/14k,
    # rose_gold_18k/14k. Choose workshop-realistic purchases.
    # remaining_weight_g starts = weight_g (nothing consumed yet at purchase time).
    purchases = [
        {"metal_type": "gold_18k", "weight_g": 250.0, "remaining_weight_g": 250.0,
         "price_per_gram": 58.00, "price_total": 14500.00,
         "date_purchased": now - timedelta(days=30),
         "supplier": "Heimerle + Meule GmbH", "invoice_number": "HM-2026-1001"},
        {"metal_type": "silver_925", "weight_g": 1000.0, "remaining_weight_g": 1000.0,
         "price_per_gram": 0.85, "price_total": 850.00,
         "date_purchased": now - timedelta(days=45),
         "supplier": "Degussa Goldhandel AG", "invoice_number": "DG-2026-0412"},
        {"metal_type": "gold_14k", "weight_g": 500.0, "remaining_weight_g": 500.0,
         "price_per_gram": 45.80, "price_total": 22900.00,
         "date_purchased": now - timedelta(days=10),
         "supplier": "Heimerle + Meule GmbH", "invoice_number": "HM-2026-1052"},
    ]
    # Idempotency — skip if any purchase already exists for the first invoice number
    existing = await session.execute(
        select(MetalPurchase).where(MetalPurchase.invoice_number == purchases[0]["invoice_number"])
    )
    if existing.scalar_one_or_none() is not None:
        print("✓ Metal purchases: already seeded — skipping")
        return

    for data in purchases:
        session.add(MetalPurchase(**_filter_model_fields(MetalPurchase, data)))
    await session.commit()
    print(f"✓ Metal purchases: {len(purchases)} new")


async def seed_quotes(session: AsyncSession, admin: User):
    """Kostenvoranschläge (quotes/estimates) — tests the quote workflow + C6 audit."""
    print("Creating quotes...")
    orders_q = await session.execute(select(Order).order_by(Order.id).limit(2))
    orders = list(orders_q.scalars())
    if not orders:
        print("⚠ Skipping quotes (no orders)")
        return

    from datetime import datetime, timedelta
    now = datetime.utcnow()
    quotes_data = [
        {"quote_number": "KV-2026-0001", "order_id": orders[0].id,
         "customer_id": orders[0].customer_id, "created_by": admin.id,
         "status": "sent", "valid_until": now + timedelta(days=14),
         "subtotal": 1800.00, "tax_rate": 19.0, "tax_amount": 342.00, "total": 2142.00,
         "notes": "Anfertigung Verlobungsring"},
        {"quote_number": "KV-2026-0002", "order_id": None,
         "customer_id": orders[1].customer_id, "created_by": admin.id,
         "status": "approved", "valid_until": now + timedelta(days=30),
         "approved_at": now - timedelta(days=2),
         "subtotal": 450.00, "tax_rate": 19.0, "tax_amount": 85.50, "total": 535.50},
    ]
    new_count = 0
    skipped = 0
    for data in quotes_data:
        existing = await session.execute(
            select(Quote).where(Quote.quote_number == data["quote_number"])
        )
        if existing.scalar_one_or_none() is not None:
            skipped += 1
            continue
        session.add(Quote(**_filter_model_fields(Quote, data)))
        new_count += 1
    if new_count:
        await session.commit()
    print(f"✓ Quotes: {new_count} new / {skipped} already existed")


async def seed_repair_jobs(session: AsyncSession, admin: User):
    """Reparaturaufträge — repair tickets for existing pieces."""
    print("Creating repair jobs...")
    customers_q = await session.execute(select(Customer).order_by(Customer.id).limit(2))
    customers = list(customers_q.scalars())
    if not customers:
        print("⚠ Skipping repair jobs (no customers)")
        return

    from datetime import datetime, timedelta
    now = datetime.utcnow()
    repairs = [
        {"repair_number": "REP-2026-0001", "bag_number": "B-001",
         "customer_id": customers[0].id, "received_by": admin.id,
         "item_description": "Goldring 585, verbogen — Ringschiene muss gerichtet werden",
         "item_type": "ring", "metal_type": "585 Gelbgold",
         "estimated_value": 380.00},
        {"repair_number": "REP-2026-0002", "bag_number": "B-002",
         "customer_id": customers[1].id, "received_by": admin.id,
         "item_description": "Halskette gebrochen — Verschluss ersetzen, Glied löten",
         "item_type": "chain", "metal_type": "Silber 925",
         "estimated_value": 120.00},
    ]
    new_count = 0
    skipped = 0
    for data in repairs:
        existing = await session.execute(
            select(RepairJob).where(RepairJob.repair_number == data["repair_number"])
        )
        if existing.scalar_one_or_none() is not None:
            skipped += 1
            continue
        session.add(RepairJob(**_filter_model_fields(RepairJob, data)))
        new_count += 1
    if new_count:
        await session.commit()
    print(f"✓ Repair jobs: {new_count} new / {skipped} already existed")


async def seed_scrap_gold(session: AsyncSession, admin: User):
    """Altgold intake — tests the financial audit (scrap gold = financial data per CLAUDE.md)."""
    print("Creating scrap gold intakes...")
    orders_q = await session.execute(select(Order).order_by(Order.id).limit(2))
    orders = list(orders_q.scalars())
    if not orders:
        print("⚠ Skipping scrap gold (no orders)")
        return

    # Idempotency — skip if any already exists
    existing = await session.execute(select(ScrapGold).limit(1))
    if existing.scalar_one_or_none() is not None:
        print("✓ Scrap gold: already seeded — skipping")
        return

    intakes = [
        {"order_id": orders[0].id, "customer_id": orders[0].customer_id,
         "created_by": admin.id, "status": "received",
         "total_fine_gold_g": 12.5, "total_value_eur": 725.00,
         "gold_price_per_g": 58.00, "price_source": "fixed_rate",
         "notes": "Alter Ehering und zwei Ohrstecker"},
        {"order_id": orders[1].id, "customer_id": orders[1].customer_id,
         "created_by": admin.id, "status": "calculated",
         "total_fine_gold_g": 8.2, "total_value_eur": 475.60,
         "gold_price_per_g": 58.00, "price_source": "fixed_rate",
         "notes": "Kette mit beschädigtem Verschluss"},
    ]
    for data in intakes:
        session.add(ScrapGold(**_filter_model_fields(ScrapGold, data)))
    await session.commit()
    print(f"✓ Scrap gold: {len(intakes)} new")


async def seed_extended(session: AsyncSession, admin: User):
    """Run all extended seeders in dependency order (activities before time entries, etc.)."""
    await seed_activities(session, admin)
    await seed_metal_purchases(session, admin)
    await seed_time_entries(session, admin)
    await seed_valuations(session, admin)
    await seed_invoices(session, admin)
    await seed_quotes(session, admin)
    await seed_repair_jobs(session, admin)
    await seed_scrap_gold(session, admin)


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
            await seed_extended(session, admin)
            await seed_audit_logs(session, customers, admin)

            print("=" * 70)
            print("✓ Database seeding completed successfully!")
            print("=" * 70)
            print("\n📋 Sample Credentials (Staff):")
            print("  Admin:        admin@goldsmith.local / admin123")
            print("  Goldsmith:    goldsmith@goldsmith.local / goldsmith123")
            print("  Goldsmith 2:  goldsmith2@goldsmith.local / goldsmith123")
            print("  Viewer:       viewer@goldsmith.local / viewer123")

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
