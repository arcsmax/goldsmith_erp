#!/usr/bin/env python3
"""
Seed data for the Goldsmith ERP system.

Creates realistic sample data for development and testing:
- 3 users (admin, goldsmith, viewer)
- 15 standard activities across 3 categories
- 5 sample customers
- 6 sample materials
- 3 sample orders with different statuses
- 2 sample metal purchases

DEVELOPMENT ONLY — do not run in production.
"""

import os
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from .models import (
    Activity, User, UserRole, Customer, Material, Order, OrderStatusEnum,
    MetalPurchase, MetalType,
)
from goldsmith_erp.core.security import get_password_hash


# ============================================================================
# STANDARD ACTIVITIES (15 across 3 categories)
# ============================================================================

STANDARD_ACTIVITIES = [
    # Fabrication (Fertigung) — 7
    {"name": "Sägen", "category": "fabrication", "icon": "🪚", "color": "#FF6B6B"},
    {"name": "Feilen", "category": "fabrication", "icon": "⚒️", "color": "#4ECDC4"},
    {"name": "Löten", "category": "fabrication", "icon": "🔥", "color": "#FF8C42"},
    {"name": "Polieren", "category": "fabrication", "icon": "✨", "color": "#95E1D3"},
    {"name": "Fassen (Steine)", "category": "fabrication", "icon": "💎", "color": "#A8E6CF"},
    {"name": "Gravieren", "category": "fabrication", "icon": "✍️", "color": "#FFD3B6"},
    {"name": "Emaillieren", "category": "fabrication", "icon": "🎨", "color": "#FFAAA5"},
    # Administration — 4
    {"name": "Kundenberatung", "category": "administration", "icon": "👥", "color": "#667EEA"},
    {"name": "Angebot erstellen", "category": "administration", "icon": "📝", "color": "#764BA2"},
    {"name": "Dokumentation", "category": "administration", "icon": "📋", "color": "#5C6AC4"},
    {"name": "Qualitätskontrolle", "category": "administration", "icon": "🔍", "color": "#006BA6"},
    # Waiting — 4
    {"name": "Warten auf Material", "category": "waiting", "icon": "⏳", "color": "#A0AEC0"},
    {"name": "Warten auf Kundenfeedback", "category": "waiting", "icon": "💬", "color": "#718096"},
    {"name": "Pause", "category": "waiting", "icon": "☕", "color": "#CBD5E0"},
    {"name": "Unterbrechung", "category": "waiting", "icon": "⚠️", "color": "#E2E8F0"},
]


# ============================================================================
# USERS (3 roles)
# ============================================================================

# Seed user credentials are NOT hardcoded. Each role's password is read from an
# env var; the fallback is a deliberately weak, low-entropy placeholder that must
# never be relied on outside local development (this script is DEVELOPMENT ONLY).
# Override in any shared environment via SEED_ADMIN_PASSWORD / SEED_GOLDSMITH_PASSWORD
# / SEED_VIEWER_PASSWORD, or set SEED_FALLBACK_PASSWORD to change the shared default.
_SEED_PW_FALLBACK = os.getenv("SEED_FALLBACK_PASSWORD", "dev-only-change-me")

STANDARD_USERS = [
    {
        "email": "admin@goldschmiede.de",
        "password": os.getenv("SEED_ADMIN_PASSWORD", _SEED_PW_FALLBACK),
        "first_name": "Thomas",
        "last_name": "Brenner",
        "role": UserRole.ADMIN,
    },
    {
        "email": "goldschmied@goldschmiede.de",
        "password": os.getenv("SEED_GOLDSMITH_PASSWORD", _SEED_PW_FALLBACK),
        "first_name": "Maria",
        "last_name": "Hofmann",
        "role": UserRole.GOLDSMITH,
    },
    {
        "email": "empfang@goldschmiede.de",
        "password": os.getenv("SEED_VIEWER_PASSWORD", _SEED_PW_FALLBACK),
        "first_name": "Lisa",
        "last_name": "Weber",
        "role": UserRole.VIEWER,
    },
]


# ============================================================================
# CUSTOMERS (5 realistic German customers)
# ============================================================================

SAMPLE_CUSTOMERS = [
    {
        "first_name": "Sophie",
        "last_name": "Müller",
        "email": "sophie.mueller@example.de",
        "phone": "+49 89 12345678",
        "street": "Maximilianstraße 42",
        "city": "München",
        "postal_code": "80539",
        "country": "Deutschland",
        "customer_type": "private",
        "source": "Empfehlung",
        "notes": "Stammkundin, bevorzugt Gelbgold 750",
    },
    {
        "first_name": "Dr. Michael",
        "last_name": "Schmidt",
        "email": "m.schmidt@example.de",
        "phone": "+49 89 98765432",
        "street": "Leopoldstraße 15",
        "city": "München",
        "postal_code": "80802",
        "country": "Deutschland",
        "customer_type": "private",
        "source": "Website",
        "notes": "Verlobungsring bestellt, Budget ca. 3.000€",
    },
    {
        "first_name": "Elena",
        "last_name": "Petrova",
        "email": "elena.p@example.de",
        "phone": "+49 176 55512345",
        "street": "Sendlinger Straße 8",
        "city": "München",
        "postal_code": "80331",
        "country": "Deutschland",
        "customer_type": "private",
        "source": "Instagram",
        "notes": "Interessiert an modernem Schmuckdesign",
    },
    {
        "first_name": "Hans",
        "last_name": "Gruber",
        "company_name": "Juwelier Gruber GmbH",
        "email": "h.gruber@juwelier-gruber.de",
        "phone": "+49 89 44332211",
        "street": "Theatinerstraße 22",
        "city": "München",
        "postal_code": "80333",
        "country": "Deutschland",
        "customer_type": "business",
        "source": "Messe",
        "notes": "Großhändler, bestellt regelmäßig Trauringe",
    },
    {
        "first_name": "Claudia",
        "last_name": "Bergmann",
        "email": "c.bergmann@example.de",
        "phone": "+49 151 22233344",
        "street": "Nymphenburger Straße 90",
        "city": "München",
        "postal_code": "80636",
        "country": "Deutschland",
        "customer_type": "private",
        "source": "Google",
        "notes": "Erbstück umarbeiten lassen",
    },
]


# ============================================================================
# MATERIALS (6 common goldsmith materials)
# ============================================================================

SAMPLE_MATERIALS = [
    {
        "name": "Gelbgold 750 (18K)",
        "description": "Legierung 750/000 Gelbgold, Standardlegierung für Schmuck",
        "unit_price": 58.50,
        "stock": 50.0,
        "unit": "g",
        "min_stock": 20.0,
        "supplier": "C. Hafner",
    },
    {
        "name": "Weißgold 750 (18K)",
        "description": "Legierung 750/000 Weißgold mit Palladium",
        "unit_price": 62.00,
        "stock": 30.0,
        "unit": "g",
        "min_stock": 15.0,
        "supplier": "C. Hafner",
    },
    {
        "name": "Silber 925 (Sterling)",
        "description": "Sterlingsilber 925/000 für Schmuck und Accessoires",
        "unit_price": 1.20,
        "stock": 200.0,
        "unit": "g",
        "min_stock": 50.0,
        "supplier": "Heimerle + Meule",
    },
    {
        "name": "Platin 950",
        "description": "Platin 950/000, hypoallergen, für hochwertige Trauringe",
        "unit_price": 38.00,
        "stock": 20.0,
        "unit": "g",
        "min_stock": 10.0,
        "supplier": "Heraeus",
    },
    {
        "name": "Brillant 0.25ct",
        "description": "Brillant rund, 0.25 Karat, Farbe G, Reinheit VS1",
        "unit_price": 850.00,
        "stock": 5.0,
        "unit": "Stück",
        "min_stock": 2.0,
        "supplier": "Schachermayer",
    },
    {
        "name": "Saphir blau 0.5ct",
        "description": "Blauer Ceylon-Saphir, oval geschliffen, 0.5 Karat",
        "unit_price": 420.00,
        "stock": 3.0,
        "unit": "Stück",
        "min_stock": 1.0,
        "supplier": "Schachermayer",
    },
]


# ============================================================================
# ORDERS (3 sample orders in different statuses)
# ============================================================================

def _build_sample_orders(customer_ids: dict, user_id: int) -> list:
    """Build sample orders referencing created customer IDs."""
    now = datetime.utcnow()
    return [
        {
            "title": "Verlobungsring Solitär",
            "description": "Solitär-Verlobungsring in Weißgold 750 mit 0.5ct Brillant. "
                           "Ringweite 54, klassisches 6-Krappen-Design.",
            "status": OrderStatusEnum.IN_PROGRESS,
            "customer_id": customer_ids.get("Schmidt", 1),
            "price": 3200.00,
            "deadline": now + timedelta(days=14),
            "metal_type": MetalType.GOLD_18K,
            "order_type": "ring",
            "ring_size_mm": 17.2,
            "estimated_weight_g": 5.5,
            "complexity_rating": 3,
            "hourly_rate": 75.0,
            "labor_hours": 8.0,
            "profit_margin_percent": 40.0,
            "vat_rate": 19.0,
            "current_location": "Werkstatt",
            "created_at": now - timedelta(days=3),
        },
        {
            "title": "Trauringe Classic Paar",
            "description": "Klassische Trauringe in Gelbgold 750, Breite 5mm, "
                           "Damenring mit 3 Brillanten à 0.03ct.",
            "status": OrderStatusEnum.NEW,
            "customer_id": customer_ids.get("Gruber", 1),
            "price": 2800.00,
            "deadline": now + timedelta(days=28),
            "metal_type": MetalType.GOLD_18K,
            "order_type": "ring",
            "estimated_weight_g": 14.0,
            "complexity_rating": 2,
            "hourly_rate": 75.0,
            "labor_hours": 12.0,
            "profit_margin_percent": 35.0,
            "vat_rate": 19.0,
            "current_location": "Eingang",
            "created_at": now - timedelta(days=1),
        },
        {
            "title": "Erbstück Umarbeitung",
            "description": "Alte Brosche (Gelbgold) in modernen Anhänger umarbeiten. "
                           "Steine übernehmen, neues Design nach Kundenskizze.",
            "status": OrderStatusEnum.CONFIRMED,
            "customer_id": customer_ids.get("Bergmann", 1),
            "price": 1500.00,
            "deadline": now + timedelta(days=21),
            "metal_type": MetalType.GOLD_14K,
            "order_type": "custom",
            "estimated_weight_g": 8.0,
            "complexity_rating": 4,
            "hourly_rate": 75.0,
            "labor_hours": 6.0,
            "has_scrap_gold": True,
            "profit_margin_percent": 45.0,
            "vat_rate": 19.0,
            "current_location": "Werkstatt",
            "created_at": now - timedelta(days=5),
        },
    ]


# ============================================================================
# METAL PURCHASES (2 sample inventory batches)
# ============================================================================

def _build_metal_purchases() -> list:
    now = datetime.utcnow()
    return [
        {
            "metal_type": MetalType.GOLD_18K,
            "weight_g": 100.0,
            "remaining_weight_g": 85.0,
            "price_total": 5850.00,
            "price_per_gram": 58.50,
            "supplier": "C. Hafner",
            "invoice_number": "CHF-2026-0412",
            "date_purchased": now - timedelta(days=30),
        },
        {
            "metal_type": MetalType.SILVER_925,
            "weight_g": 500.0,
            "remaining_weight_g": 480.0,
            "price_total": 600.00,
            "price_per_gram": 1.20,
            "supplier": "Heimerle + Meule",
            "invoice_number": "HM-2026-0398",
            "date_purchased": now - timedelta(days=15),
        },
    ]


# ============================================================================
# SEED FUNCTIONS
# ============================================================================

def seed_users(db: Session) -> dict:
    """Create standard users. Returns dict of name→id for reference."""
    created = 0
    skipped = 0
    user_ids = {}

    for data in STANDARD_USERS:
        existing = db.query(User).filter(User.email == data["email"]).first()
        if existing:
            user_ids[data["last_name"]] = existing.id
            skipped += 1
            continue

        user = User(
            email=data["email"],
            hashed_password=get_password_hash(data["password"]),
            first_name=data["first_name"],
            last_name=data["last_name"],
            role=data["role"],
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db.add(user)
        db.flush()
        user_ids[data["last_name"]] = user.id
        created += 1

    db.commit()
    print(f"  Users: {created} created, {skipped} skipped")
    return user_ids


def seed_activities(db: Session) -> None:
    """Create standard workshop activities."""
    created = 0
    skipped = 0

    for data in STANDARD_ACTIVITIES:
        existing = db.query(Activity).filter(
            Activity.name == data["name"],
            Activity.category == data["category"],
        ).first()
        if existing:
            skipped += 1
            continue

        activity = Activity(
            name=data["name"],
            category=data["category"],
            icon=data["icon"],
            color=data["color"],
            usage_count=0,
            is_custom=False,
            created_at=datetime.utcnow(),
        )
        db.add(activity)
        created += 1

    db.commit()
    print(f"  Activities: {created} created, {skipped} skipped")


def seed_customers(db: Session) -> dict:
    """Create sample customers. Returns dict of last_name→id."""
    created = 0
    skipped = 0
    customer_ids = {}

    for data in SAMPLE_CUSTOMERS:
        existing = db.query(Customer).filter(Customer.email == data["email"]).first()
        if existing:
            customer_ids[data["last_name"]] = existing.id
            skipped += 1
            continue

        customer = Customer(
            first_name=data["first_name"],
            last_name=data["last_name"],
            company_name=data.get("company_name"),
            email=data["email"],
            phone=data.get("phone"),
            street=data.get("street"),
            city=data.get("city"),
            postal_code=data.get("postal_code"),
            country=data.get("country", "Deutschland"),
            customer_type=data.get("customer_type", "private"),
            source=data.get("source"),
            notes=data.get("notes"),
            is_active=True,
            created_at=datetime.utcnow(),
        )
        db.add(customer)
        db.flush()
        customer_ids[data["last_name"]] = customer.id
        created += 1

    db.commit()
    print(f"  Customers: {created} created, {skipped} skipped")
    return customer_ids


def seed_materials(db: Session) -> None:
    """Create sample materials."""
    created = 0
    skipped = 0

    for data in SAMPLE_MATERIALS:
        existing = db.query(Material).filter(Material.name == data["name"]).first()
        if existing:
            skipped += 1
            continue

        material = Material(
            name=data["name"],
            description=data.get("description"),
            unit_price=data["unit_price"],
            stock=data["stock"],
            unit=data["unit"],
            min_stock=data.get("min_stock", 10.0),
            supplier=data.get("supplier"),
        )
        db.add(material)
        created += 1

    db.commit()
    print(f"  Materials: {created} created, {skipped} skipped")


def seed_orders(db: Session, customer_ids: dict, admin_id: int) -> None:
    """Create sample orders."""
    existing_count = db.query(Order).count()
    if existing_count > 0:
        print(f"  Orders: skipped ({existing_count} already exist)")
        return

    orders = _build_sample_orders(customer_ids, admin_id)
    for data in orders:
        order = Order(**data)
        db.add(order)

    db.commit()
    print(f"  Orders: {len(orders)} created")


def seed_metal_purchases(db: Session) -> None:
    """Create sample metal purchase batches."""
    existing_count = db.query(MetalPurchase).count()
    if existing_count > 0:
        print(f"  Metal purchases: skipped ({existing_count} already exist)")
        return

    purchases = _build_metal_purchases()
    for data in purchases:
        purchase = MetalPurchase(**data)
        db.add(purchase)

    db.commit()
    print(f"  Metal purchases: {len(purchases)} created")


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Standalone execution for seed data."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    import os

    database_url = os.getenv(
        "DATABASE_URL",
        "postgresql://user:pass@localhost:5432/goldsmith",
    )
    # Convert async URL to sync if needed
    database_url = database_url.replace("+asyncpg", "")

    engine = create_engine(database_url)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        print("Seeding Goldsmith ERP database...")
        user_ids = seed_users(db)
        seed_activities(db)
        customer_ids = seed_customers(db)
        seed_materials(db)

        admin_id = user_ids.get("Brenner", 1)
        seed_orders(db, customer_ids, admin_id)
        seed_metal_purchases(db)

        print("Seed complete.")
    except Exception as e:
        print(f"Error: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
