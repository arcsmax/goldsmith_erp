#!/usr/bin/env python3
"""
Goldsmith ERP -- Comprehensive Demo Data Seeder
================================================
Creates realistic workshop data showcasing ALL features of the system.

Run:
    cd src && poetry run python ../scripts/seed_demo.py

Or with explicit DB connection:
    DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5434/goldsmith \
    poetry run python ../scripts/seed_demo.py

The script is IDEMPOTENT: it checks for the sentinel user email
`demo-goldschmied@werkstatt.de` and skips seeding if demo data
already exists.

Entities created (in dependency order):
    - 3 Users (Admin/Owner, Goldsmith, Buerokraft)
    - 15 Activities (standard goldsmith activities)
    - 10 Customers (private + business mix)
    - 12 CustomerMeasurements (ring sizes, chain lengths, wrist)
    - 17 Materials (metals, gemstones, consumables)
    - 8 MetalPurchases (gold, silver, platinum batches)
    - 15 Orders (full lifecycle variety)
    - 8 Gemstones (on relevant orders)
    - 8 MaterialUsage records
    - 24 TimeEntries (spread across orders and activities)
    - 4 Interruptions
    - 6 RepairJobs
    - 4 Quotes + line items
    - 4 Invoices + line items
    - 3 ScrapGold + items
    - 6 CalendarEvents
    - 12 Notifications
    - 10 OrderComments
    - 4 OrderHandoffs
    - 3 OrderHallmarks
    - 2 ValuationCertificates
    - 15+ LocationHistory entries
"""

import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path

# Ensure the src directory is on sys.path so `goldsmith_erp` is importable.
_project_root = Path(__file__).resolve().parent.parent
_src_dir = _project_root / "src"
sys.path.insert(0, str(_src_dir))

from sqlalchemy import select  # noqa: E402

from goldsmith_erp.core.security import get_password_hash  # noqa: E402
from goldsmith_erp.db.models import (  # noqa: E402
    Activity,
    AlloyType,
    CalendarEvent,
    CalendarEventType,
    CostingMethod,
    Customer,
    CustomerMeasurement,
    FingerPosition,
    Gemstone,
    HandoffStatusEnum,
    HandoffTypeEnum,
    HandSide,
    HallmarkStatus,
    HallmarkType,
    Interruption,
    Invoice,
    InvoiceLineItem,
    InvoiceLineType,
    InvoiceStatus,
    LocationHistory,
    Material,
    MaterialUsage,
    MeasurementType,
    MetalPurchase,
    MetalType,
    Notification,
    NotificationSeverityEnum,
    NotificationTypeEnum,
    Order,
    OrderComment,
    OrderHandoff,
    OrderHallmark,
    OrderStatusEnum,
    Quote,
    QuoteLineItem,
    QuoteLineType,
    QuoteStatus,
    RepairJob,
    RepairJobStatus,
    RepairItemType,
    ScrapGold,
    ScrapGoldItem,
    ScrapGoldStatus,
    TimeEntry,
    User,
    UserRole,
    ValuationCertificate,
)
from goldsmith_erp.db.session import AsyncSessionLocal, engine  # noqa: E402

# ── Sentinel email used for idempotency check ─────────────────────────────
SENTINEL_EMAIL = "demo-goldschmied@werkstatt.de"

# ── Date helpers ───────────────────────────────────────────────────────────
NOW = datetime.utcnow()
TODAY = NOW.replace(hour=0, minute=0, second=0, microsecond=0)


def _days_ago(n: int) -> datetime:
    return NOW - timedelta(days=n)


def _days_from_now(n: int) -> datetime:
    return NOW + timedelta(days=n)


def _hours_ago(n: int) -> datetime:
    return NOW - timedelta(hours=n)


def _uuid() -> str:
    return str(uuid.uuid4())


# ═══════════════════════════════════════════════════════════════════════════
# SEED FUNCTIONS — one per entity group, called in dependency order
# ═══════════════════════════════════════════════════════════════════════════


async def seed_users(db) -> list:
    """Create 3 demo users: Admin/Owner, Goldsmith, Buerokraft."""
    users = [
        User(
            email=SENTINEL_EMAIL,
            hashed_password=get_password_hash("demo2026!"),
            first_name="Markus",
            last_name="Goldmann",
            role="goldsmith",
            is_active=True,
            created_at=_days_ago(365),
        ),
        User(
            email="demo-inhaber@werkstatt.de",
            hashed_password=get_password_hash("demo2026!"),
            first_name="Petra",
            last_name="Goldmann",
            role="admin",
            is_active=True,
            created_at=_days_ago(400),
        ),
        User(
            email="demo-buero@werkstatt.de",
            hashed_password=get_password_hash("demo2026!"),
            first_name="Lisa",
            last_name="Schreiber",
            role="viewer",
            is_active=True,
            created_at=_days_ago(200),
        ),
    ]
    for u in users:
        db.add(u)
    await db.flush()
    print(f"  Benutzer: {len(users)} erstellt")
    return users


async def seed_activities(db, goldsmith_user) -> list:
    """Create the 15 standard goldsmith activities."""
    # V1.3 Phase 3: is_billable and hourly_rate per-activity.
    # Rubric: CAD/Design=85, Saegen/Feilen/Loeten=75, Polieren=65,
    # Steinfassen=95, Galvanisieren=70, Endkontrolle=60 all billable.
    # Beratung/Auftragsannahme, Wartezeit/Pause, Verwaltung non-billable.
    activities_data = [
        # Fabrication (Fertigung) \u2014 Saegen/Feilen/Loeten: 75 EUR/h
        ("Saegen", "fabrication", "\u2702", "#FF6B6B", True, 75),
        ("Feilen", "fabrication", "\U0001F4A0", "#4ECDC4", True, 75),
        ("Loeten", "fabrication", "\U0001F525", "#FF8C42", True, 75),
        # Polieren: 65 EUR/h
        ("Polieren", "fabrication", "\u2728", "#95E1D3", True, 65),
        # Steinfassen: 95 EUR/h
        ("Fassen (Steine)", "fabrication", "\U0001F48E", "#A8E6CF", True, 95),
        # Gravieren \u2014 not in rubric, conservative: non-billable
        ("Gravieren", "fabrication", "\u270F", "#FFD3B6", False, None),
        # Emaillieren \u2014 not in rubric, conservative: non-billable
        ("Emaillieren", "fabrication", "\U0001F3A8", "#FFAAA5", False, None),
        # Schmieden \u2014 not in rubric, conservative: non-billable
        ("Schmieden", "fabrication", "\U0001F528", "#E07A5F", False, None),
        # Giessen \u2014 not in rubric, conservative: non-billable
        ("Giessen", "fabrication", "\U0001F3ED", "#3D405B", False, None),
        # Administration \u2014 non-billable
        ("Kundenberatung", "administration", "\U0001F4DE", "#d97706", False, None),
        ("Angebot erstellen", "administration", "\U0001F4DD", "#b45309", False, None),
        ("Dokumentation", "administration", "\U0001F4CB", "#92400e", False, None),
        # Endkontrolle: 60 EUR/h (Qualitaetskontrolle)
        ("Qualitaetskontrolle", "administration", "\U0001F50D", "#006BA6", True, 60),
        # Waiting \u2014 non-billable
        ("Warten auf Material", "waiting", "\u23F3", "#A0AEC0", False, None),
        ("Pause", "waiting", "\u2615", "#CBD5E0", False, None),
    ]
    activities = []
    for name, category, icon, color, is_billable, hourly_rate in activities_data:
        a = Activity(
            name=name,
            category=category,
            icon=icon,
            color=color,
            usage_count=0,
            is_custom=False,
            is_billable=is_billable,
            hourly_rate=hourly_rate,
            created_by=None,
            created_at=_days_ago(365),
        )
        db.add(a)
        activities.append(a)
    await db.flush()
    print(f"  Aktivitaeten: {len(activities)} erstellt")
    return activities


async def seed_customers(db) -> list:
    """Create 10 realistic customers (private + business mix)."""
    customers_data = [
        # 1 - Stammkundin, birthday in 2 weeks
        dict(
            first_name="Maria", last_name="Schneider",
            email="maria.schneider@example.de", phone="+49 711 1234567",
            mobile="+49 170 1234567",
            street="Koenigstrasse 42", city="Stuttgart", postal_code="70173",
            customer_type="private", source="walk-in",
            notes="Stammkundin seit 2019. Bevorzugt Gelbgold.",
            tags=["Stammkunde", "VIP"],
            ring_size=54.0, chain_length_cm=45.0,
            allergies=None,
            preferences={"bevorzugt": "Gelbgold", "style": "klassisch"},
            birthday=_days_from_now(14).replace(year=1978),
        ),
        # 2 - Thomas Weber (wedding couple - groom)
        dict(
            first_name="Thomas", last_name="Weber",
            email="thomas.weber@example.de", phone="+49 711 9876543",
            mobile="+49 171 9876543",
            street="Schillerplatz 8", city="Stuttgart", postal_code="70173",
            customer_type="private", source="referral",
            notes="Hochzeitspaar Weber. Trauung geplant August 2026.",
            tags=["Hochzeit"],
            ring_size=66.0, chain_length_cm=None,
            allergies=None,
            preferences={"bevorzugt": "Gelbgold 750", "style": "schlicht"},
            birthday=datetime(1991, 5, 15),
        ),
        # 3 - Anna Weber (wedding couple - bride)
        dict(
            first_name="Anna", last_name="Weber",
            email="anna.weber@example.de", phone="+49 711 9876544",
            mobile="+49 172 9876544",
            street="Schillerplatz 8", city="Stuttgart", postal_code="70173",
            customer_type="private", source="referral",
            notes="Verlobungsring bereits geliefert. Eheringe in Arbeit.",
            tags=["Hochzeit"],
            ring_size=54.0, chain_length_cm=42.0,
            allergies=None,
            preferences={"bevorzugt": "Gelbgold 750", "style": "schlicht-elegant"},
            birthday=datetime(1993, 9, 22),
        ),
        # 4 - Business customer: Juwelier Hoffmann
        dict(
            first_name="Elisabeth", last_name="Hoffmann",
            company_name="Juwelier Hoffmann GmbH",
            email="e.hoffmann@juwelier-hoffmann.de", phone="+49 721 5551234",
            street="Kaiserstrasse 15", city="Karlsruhe", postal_code="76131",
            customer_type="business", source="website",
            notes="Geschaeftskunde. Bestellt regelmaessig Reparaturen und Sonderanfertigungen.",
            tags=["Geschaeftskunde", "Reparaturen"],
            ring_size=None, chain_length_cm=None,
            allergies=None,
            preferences={"geschaeftsart": "Juwelier", "rabatt_vereinbart": "10%"},
            birthday=datetime(1970, 3, 8),
        ),
        # 5 - Nickel allergy customer
        dict(
            first_name="Stefan", last_name="Braun",
            email="stefan.braun@example.de", phone="+49 711 4445566",
            mobile="+49 173 4445566",
            street="Marienstrasse 23", city="Stuttgart", postal_code="70178",
            customer_type="private", source="referral",
            notes="Nickel-Allergie! Nur Platin, Palladium oder hochlegiertes Gold (750+).",
            tags=["Allergie"],
            ring_size=62.0, chain_length_cm=50.0,
            allergies="Nickel",
            preferences={"bevorzugt": "Platin 950", "style": "modern"},
            birthday=datetime(1985, 11, 30),
        ),
        # 6 - Repeat customer, elderly
        dict(
            first_name="Helga", last_name="Zimmermann",
            email="helga.zimmermann@example.de", phone="+49 711 7778899",
            street="Rosenbergstrasse 5", city="Stuttgart", postal_code="70176",
            customer_type="private", source="walk-in",
            notes="Langjahrige Kundin. Hat mehrere Erbstuecke umarbeiten lassen.",
            tags=["Stammkunde"],
            ring_size=56.0, chain_length_cm=40.0, bracelet_length_cm=18.0,
            allergies=None,
            preferences={"bevorzugt": "Gelbgold", "style": "traditionell"},
            birthday=datetime(1952, 7, 19),
        ),
        # 7 - Young customer, modern taste
        dict(
            first_name="Lena", last_name="Fischer",
            email="lena.fischer@example.de", mobile="+49 176 1112233",
            street="Tuebinger Strasse 17", city="Stuttgart", postal_code="70178",
            customer_type="private", source="instagram",
            notes="Entdeckt ueber Instagram. Mag minimalistische Designs.",
            tags=["Social Media"],
            ring_size=52.0, chain_length_cm=45.0,
            allergies=None,
            preferences={"bevorzugt": "Weissgold 750", "style": "minimalistisch"},
            birthday=datetime(1998, 2, 14),
        ),
        # 8 - Business customer: Zahnarztpraxis (dental crowns etc.)
        dict(
            first_name="Dr. Michael", last_name="Bauer",
            company_name="Zahnarztpraxis Dr. Bauer",
            email="praxis@dr-bauer.de", phone="+49 711 3334455",
            street="Friedrichstrasse 88", city="Stuttgart", postal_code="70174",
            customer_type="business", source="referral",
            notes="Bestellt gelegentlich Goldlegierungen fuer Dentalarbeiten.",
            tags=["Geschaeftskunde", "Dental"],
            ring_size=None, chain_length_cm=None,
            allergies=None,
            preferences={"geschaeftsart": "Dental"},
            birthday=None,
        ),
        # 9 - Customer with Altgold
        dict(
            first_name="Claudia", last_name="Richter",
            email="claudia.richter@example.de", phone="+49 711 6667788",
            mobile="+49 174 6667788",
            street="Heusteigstrasse 31", city="Stuttgart", postal_code="70180",
            customer_type="private", source="walk-in",
            notes="Bringt Altgold (alte Brosche der Grossmutter) zur Umarbeitung.",
            tags=[],
            ring_size=55.0, chain_length_cm=None,
            allergies=None,
            preferences={"bevorzugt": "Rotgold", "style": "vintage"},
            birthday=datetime(1980, 4, 25),
        ),
        # 10 - Occasional customer
        dict(
            first_name="Klaus", last_name="Mueller",
            email="klaus.mueller@example.de", mobile="+49 175 9990011",
            street="Hauptstaetter Strasse 60", city="Stuttgart", postal_code="70178",
            customer_type="private", source="website",
            notes="Sucht Geschenk fuer Ehefrau (Hochzeitstag).",
            tags=[],
            ring_size=None, chain_length_cm=None,
            allergies=None,
            preferences={},
            birthday=datetime(1975, 12, 1),
        ),
    ]
    customers = []
    for data in customers_data:
        c = Customer(**data, country="Deutschland", is_active=True, created_at=_days_ago(120))
        db.add(c)
        customers.append(c)
    await db.flush()
    print(f"  Kunden: {len(customers)} erstellt")
    return customers


async def seed_measurements(db, customers, goldsmith_user) -> list:
    """Create per-finger ring sizes and other body measurements."""
    # customers[0] = Maria Schneider
    # customers[1] = Thomas Weber
    # customers[2] = Anna Weber
    # customers[4] = Stefan Braun
    # customers[5] = Helga Zimmermann
    measurements = [
        # Maria Schneider - left ring finger
        CustomerMeasurement(
            customer_id=customers[0].id, measured_by=goldsmith_user.id,
            measurement_type=MeasurementType.RING_SIZE,
            value=54.0, unit="mm",
            hand=HandSide.LEFT, finger=FingerPosition.RING,
            notes="Standardmass, guter Sitz.",
            measured_at=_days_ago(90),
        ),
        # Maria Schneider - chain length
        CustomerMeasurement(
            customer_id=customers[0].id, measured_by=goldsmith_user.id,
            measurement_type=MeasurementType.CHAIN_LENGTH,
            value=45.0, unit="cm",
            notes="Bevorzugte Laenge fuer Anhaengerketten.",
            measured_at=_days_ago(90),
        ),
        # Thomas Weber - left ring finger
        CustomerMeasurement(
            customer_id=customers[1].id, measured_by=goldsmith_user.id,
            measurement_type=MeasurementType.RING_SIZE,
            value=66.0, unit="mm",
            hand=HandSide.LEFT, finger=FingerPosition.RING,
            notes="Knoechel etwas breiter, Weitungsring empfohlen.",
            measured_at=_days_ago(30),
        ),
        # Anna Weber - left ring finger
        CustomerMeasurement(
            customer_id=customers[2].id, measured_by=goldsmith_user.id,
            measurement_type=MeasurementType.RING_SIZE,
            value=54.0, unit="mm",
            hand=HandSide.LEFT, finger=FingerPosition.RING,
            notes="Schlanker Finger, guter Sitz bei 54mm.",
            measured_at=_days_ago(30),
        ),
        # Anna Weber - right ring finger (for engagement ring)
        CustomerMeasurement(
            customer_id=customers[2].id, measured_by=goldsmith_user.id,
            measurement_type=MeasurementType.RING_SIZE,
            value=53.5, unit="mm",
            hand=HandSide.RIGHT, finger=FingerPosition.RING,
            notes="Rechts etwas schmaler als links.",
            measured_at=_days_ago(60),
        ),
        # Stefan Braun - left ring finger
        CustomerMeasurement(
            customer_id=customers[4].id, measured_by=goldsmith_user.id,
            measurement_type=MeasurementType.RING_SIZE,
            value=62.0, unit="mm",
            hand=HandSide.LEFT, finger=FingerPosition.RING,
            notes="Nickel-Allergie beachten! Nur Platin/Palladium.",
            measured_at=_days_ago(60),
        ),
        # Stefan Braun - wrist circumference
        CustomerMeasurement(
            customer_id=customers[4].id, measured_by=goldsmith_user.id,
            measurement_type=MeasurementType.WRIST_CIRCUMFERENCE,
            value=19.5, unit="cm",
            notes="Fuer geplantes Armband.",
            measured_at=_days_ago(60),
        ),
        # Helga Zimmermann - left ring finger
        CustomerMeasurement(
            customer_id=customers[5].id, measured_by=goldsmith_user.id,
            measurement_type=MeasurementType.RING_SIZE,
            value=56.0, unit="mm",
            hand=HandSide.LEFT, finger=FingerPosition.RING,
            notes="Finger etwas geschwollen bei Waerme, 56mm als Kompromiss.",
            measured_at=_days_ago(180),
        ),
        # Helga Zimmermann - wrist
        CustomerMeasurement(
            customer_id=customers[5].id, measured_by=goldsmith_user.id,
            measurement_type=MeasurementType.WRIST_CIRCUMFERENCE,
            value=16.5, unit="cm",
            notes="Schmales Handgelenk, Armband 18cm mit Verlaengerung.",
            measured_at=_days_ago(180),
        ),
        # Helga Zimmermann - chain length
        CustomerMeasurement(
            customer_id=customers[5].id, measured_by=goldsmith_user.id,
            measurement_type=MeasurementType.CHAIN_LENGTH,
            value=40.0, unit="cm",
            notes="Kurze Kette, enganliegend bevorzugt.",
            measured_at=_days_ago(180),
        ),
        # Lena Fischer - left ring finger
        CustomerMeasurement(
            customer_id=customers[6].id, measured_by=goldsmith_user.id,
            measurement_type=MeasurementType.RING_SIZE,
            value=52.0, unit="mm",
            hand=HandSide.LEFT, finger=FingerPosition.RING,
            notes="Sehr schlanke Finger.",
            measured_at=_days_ago(45),
        ),
        # Claudia Richter - left ring finger
        CustomerMeasurement(
            customer_id=customers[8].id, measured_by=goldsmith_user.id,
            measurement_type=MeasurementType.RING_SIZE,
            value=55.0, unit="mm",
            hand=HandSide.LEFT, finger=FingerPosition.RING,
            measured_at=_days_ago(20),
        ),
    ]
    for m in measurements:
        db.add(m)
    await db.flush()
    print(f"  Messungen: {len(measurements)} erstellt")
    return measurements


async def seed_materials(db) -> list:
    """Create 17 materials: metals, gemstones, consumables."""
    materials_data = [
        # --- Metals ---
        dict(
            name="Gold 750 (18K) Barren",
            description="Gelbgold 750/000, 10g Barren, C.HAFNER",
            unit_price=62.50, stock=50.0, unit="g",
            image_url="/images/materials/gold_750_bar.jpg",
            supplier="C.HAFNER GmbH + Co. KG",
            webshop_url="https://www.c-hafner.de/edelmetalle/goldbarren",
            min_stock=20.0,
        ),
        dict(
            name="Gold 585 (14K) Draht 1.5mm",
            description="Gelbgold 585/000, Runddraht 1.5mm, fuer Ringschienen",
            unit_price=47.50, stock=30.0, unit="g",
            image_url="/images/materials/gold_585_wire.jpg",
            supplier="Heimerle + Meule GmbH",
            webshop_url="https://www.heimerle-meule.com",
            min_stock=15.0,
        ),
        dict(
            name="Silber 925 Draht 1.0mm",
            description="Sterlingsilber 925/000, Runddraht 1.0mm",
            unit_price=1.20, stock=200.0, unit="g",
            image_url="/images/materials/silver_925_wire.jpg",
            supplier="C.HAFNER GmbH + Co. KG",
            webshop_url="https://www.c-hafner.de",
            min_stock=50.0,
        ),
        dict(
            name="Silber 925 Blech 0.8mm",
            description="Sterlingsilber 925/000, Blech 0.8mm Staerke",
            unit_price=1.15, stock=150.0, unit="g",
            supplier="Heimerle + Meule GmbH",
            min_stock=40.0,
        ),
        dict(
            name="Platin 950 Draht 1.2mm",
            description="Platin 950/000, Runddraht 1.2mm fuer Ringschienen",
            unit_price=38.00, stock=15.0, unit="g",
            image_url="/images/materials/platin_950_wire.jpg",
            supplier="Heraeus Deutschland GmbH & Co. KG",
            webshop_url="https://www.heraeus.com",
            min_stock=5.0,
        ),
        dict(
            name="Weissgold 750 Legierung",
            description="Weissgold 750/000, Palladium-Legierung, nickelfrei",
            unit_price=68.00, stock=25.0, unit="g",
            supplier="C.HAFNER GmbH + Co. KG",
            min_stock=10.0,
        ),
        dict(
            name="Rotgold 750 Blech 1.0mm",
            description="Rotgold 750/000, Kupfer-betonte Legierung, Blech 1.0mm",
            unit_price=63.00, stock=20.0, unit="g",
            supplier="Heimerle + Meule GmbH",
            min_stock=10.0,
        ),
        # --- Gemstones ---
        dict(
            name="Brillant 0.50ct VS1/G",
            description="Diamant, Brillantschliff, 0.50ct, VS1, Farbe G, GIA-Zertifikat",
            unit_price=2850.00, stock=3.0, unit="Stueck",
            image_url="/images/materials/brillant_050.jpg",
            supplier="Schachter Diamonds",
            webshop_url="https://www.schachter.com",
            min_stock=1.0,
        ),
        dict(
            name="Brillant 0.10ct VS2/H (Melee)",
            description="Diamant, Brillantschliff, 0.10ct, VS2, Farbe H, Melee-Ware",
            unit_price=180.00, stock=20.0, unit="Stueck",
            supplier="Schachter Diamonds",
            min_stock=5.0,
        ),
        dict(
            name="Rubin oval 0.75ct",
            description="Rubin, ovaler Schliff, 0.75ct, rot, Birma-Qualitaet",
            unit_price=1200.00, stock=2.0, unit="Stueck",
            supplier="Kata-Stein GmbH",
            min_stock=1.0,
        ),
        dict(
            name="Saphir rund 0.60ct",
            description="Saphir, runder Schliff, 0.60ct, koenigsblau, Sri Lanka",
            unit_price=950.00, stock=2.0, unit="Stueck",
            supplier="Kata-Stein GmbH",
            min_stock=1.0,
        ),
        # --- Consumables ---
        dict(
            name="Saegeblaetter Gr. 3/0",
            description="Goldschmiedesaegeblaetter Groesse 3/0, 144 Stueck/Packung",
            unit_price=8.50, stock=288.0, unit="Stueck",
            image_url="/images/materials/saw_blades.jpg",
            supplier="Fischer Pforzheim",
            webshop_url="https://www.fischer-pforzheim.de",
            min_stock=72.0,
        ),
        dict(
            name="Polierpaste Rot (Eisenoxid)",
            description="Eisenoxid-Polierpaste fuer Hochglanzpolitur, 250g Dose",
            unit_price=12.00, stock=3.0, unit="Stueck",
            supplier="Pforzheimer Werkzeughandel",
            min_stock=1.0,
        ),
        dict(
            name="Hartlot 750 (Goldlot)",
            description="Hartlot fuer Gold 750, Schmelzbereich 780-800 Grad C",
            unit_price=95.00, stock=5.0, unit="g",
            supplier="C.HAFNER GmbH + Co. KG",
            min_stock=2.0,
        ),
        dict(
            name="Rhodium-Bad Loesung",
            description="Rhodinierungs-Loesung fuer Weissgold-Oberflaeche, 100ml",
            unit_price=185.00, stock=2.0, unit="Stueck",
            supplier="Wieland Dental + Technik",
            min_stock=1.0,
        ),
        dict(
            name="Feilen-Set Goldschmied (6-tlg)",
            description="Nadelfeilen-Set, 6 Stueck, diverse Schnitte (flach, rund, halbrund, dreieckig, messer, vierkant)",
            unit_price=42.00, stock=4.0, unit="Stueck",
            supplier="Fischer Pforzheim",
            min_stock=2.0,
        ),
        dict(
            name="Gusswachs Blau (Injektionswachs)",
            description="Injektionswachs fuer Wachsausschmelzverfahren, 500g Block",
            unit_price=28.00, stock=3.0, unit="Stueck",
            supplier="Hoben International",
            min_stock=1.0,
        ),
    ]
    materials = []
    for data in materials_data:
        m = Material(**data)
        db.add(m)
        materials.append(m)
    await db.flush()
    print(f"  Materialien: {len(materials)} erstellt")
    return materials


async def seed_metal_purchases(db) -> list:
    """Create 8 metal purchase batches with realistic prices."""
    purchases_data = [
        # Gold 18K batches
        dict(
            date_purchased=_days_ago(90),
            metal_type="gold_18k",
            weight_g=50.0, remaining_weight_g=32.5,
            price_total=3125.00, price_per_gram=62.50,
            supplier="C.HAFNER GmbH + Co. KG",
            invoice_number="CH-2026-04521",
            lot_number="AU750-2026-001",
            notes="Standardbestellung 50g Barren Gelbgold 750.",
        ),
        dict(
            date_purchased=_days_ago(30),
            metal_type="gold_18k",
            weight_g=30.0, remaining_weight_g=28.0,
            price_total=1920.00, price_per_gram=64.00,
            supplier="C.HAFNER GmbH + Co. KG",
            invoice_number="CH-2026-06183",
            lot_number="AU750-2026-002",
            notes="Nachbestellung, leicht erhoehter Goldpreis.",
        ),
        # Gold 14K batch
        dict(
            date_purchased=_days_ago(60),
            metal_type="gold_14k",
            weight_g=40.0, remaining_weight_g=35.0,
            price_total=1900.00, price_per_gram=47.50,
            supplier="Heimerle + Meule GmbH",
            invoice_number="HM-2026-09244",
            lot_number="AU585-2026-001",
            notes="Draht 1.5mm fuer Ringschienen.",
        ),
        # Silver 925 batches
        dict(
            date_purchased=_days_ago(120),
            metal_type="silver_925",
            weight_g=500.0, remaining_weight_g=320.0,
            price_total=600.00, price_per_gram=1.20,
            supplier="C.HAFNER GmbH + Co. KG",
            invoice_number="CH-2026-02109",
            lot_number="AG925-2026-001",
            notes="Grossbestellung Sterlingsilber, Draht und Blech.",
        ),
        dict(
            date_purchased=_days_ago(20),
            metal_type="silver_925",
            weight_g=200.0, remaining_weight_g=195.0,
            price_total=240.00, price_per_gram=1.20,
            supplier="Heimerle + Meule GmbH",
            invoice_number="HM-2026-10551",
            lot_number="AG925-2026-002",
        ),
        # Platinum 950
        dict(
            date_purchased=_days_ago(45),
            metal_type="platinum_950",
            weight_g=20.0, remaining_weight_g=14.0,
            price_total=760.00, price_per_gram=38.00,
            supplier="Heraeus Deutschland GmbH & Co. KG",
            invoice_number="HE-2026-07890",
            lot_number="PT950-2026-001",
            notes="Draht 1.2mm fuer Ehering Braun (Nickel-Allergie).",
        ),
        # White Gold 18K
        dict(
            date_purchased=_days_ago(50),
            metal_type="white_gold_18k",
            weight_g=25.0, remaining_weight_g=18.0,
            price_total=1700.00, price_per_gram=68.00,
            supplier="C.HAFNER GmbH + Co. KG",
            invoice_number="CH-2026-05712",
            lot_number="WG750-2026-001",
            notes="Palladium-Legierung, nickelfrei.",
        ),
        # Rose Gold 18K
        dict(
            date_purchased=_days_ago(40),
            metal_type="rose_gold_18k",
            weight_g=20.0, remaining_weight_g=16.0,
            price_total=1260.00, price_per_gram=63.00,
            supplier="Heimerle + Meule GmbH",
            invoice_number="HM-2026-09988",
            lot_number="RG750-2026-001",
            notes="Kupfer-betonte Legierung fuer Richter-Umarbeitung.",
        ),
    ]
    purchases = []
    for data in purchases_data:
        p = MetalPurchase(**data)
        db.add(p)
        purchases.append(p)
    await db.flush()
    print(f"  Metalleinkaeufe: {len(purchases)} erstellt")
    return purchases


async def seed_orders(db, customers, users, metal_purchases) -> list:
    """
    Create 15 orders spanning the full lifecycle.

    Order list:
     0  Verlobungsring Solitaer (IN_PROGRESS, gemstones, high complexity)
     1  Eheringe Weber (IN_PROGRESS, pair, fitting date)
     2  Kette Reparatur Verschluss (COMPLETED, simple)
     3  Altgold-Umarbeitung Brosche->Ring (IN_PROGRESS, scrap gold)
     4  Platinring Braun (IN_PROGRESS, allergy customer)
     5  Silber-Anhaenger Fisch (COMPLETED, delivered)
     6  Diamant-Ohrstecker (DELIVERED, with invoice)
     7  Gravur Trauring Auffrischung (COMPLETED)
     8  Goldkette 750 Anker 50cm (NEW, rush order)
     9  Armband Silber 925 (DRAFT)
    10  Perlenring Umarbeitung (COMPLETED, Soll/Ist deviation)
    11  Manschettenknuepfe Gold 585 (NEW)
    12  Saphir-Anhaenger (CONFIRMED)
    13  Brosche Art-Deco Stil (IN_PROGRESS)
    14  Charm-Armband Silber (DELIVERED)
    """
    goldsmith = users[0]  # Markus Goldmann
    admin = users[1]  # Petra Goldmann

    orders_data = [
        # 0 - Verlobungsring Solitaer
        dict(
            title="Verlobungsring Solitaer Weber",
            description="Solitaer-Verlobungsring fuer Anna Weber. Gelbgold 750, Brillant 0.50ct, Krappenfassung 6-fach.",
            price=4850.00,
            status="in_progress",
            customer_id=customers[2].id,  # Anna Weber
            deadline=_days_from_now(10),
            current_location="Werkbank 1",
            estimated_weight_g=5.5,
            actual_weight_g=None,
            scrap_percentage=8.0,
            metal_type="gold_18k",
            costing_method_used="fifo",
            material_cost_calculated=375.00,
            labor_hours=12.0,
            hourly_rate=85.00,
            labor_cost=1020.00,
            profit_margin_percent=45.0,
            vat_rate=19.0,
            calculated_price=4850.00,
            order_type="ring",
            finish_type="high_polish",
            complexity_rating=5,
            alloy="750",
            ring_size_mm=53.5,
            surface_finish="Hochglanz",
            has_scrap_gold=False,
            special_instructions="Krappenfassung 6-fach, Brillant muss GIA-zertifiziert sein. Innengravur: 'Fuer Anna'",
            created_at=_days_ago(15),
        ),
        # 1 - Eheringe Weber
        dict(
            title="Eheringe Weber (Paar)",
            description="Eheringe Gelbgold 750, Damenring 4mm mit 3 Brillanten, Herrenring 5mm schlicht. Innengravur: 'T&A 2026'.",
            price=3200.00,
            status="in_progress",
            customer_id=customers[1].id,  # Thomas Weber
            deadline=_days_from_now(25),
            current_location="Werkbank 1",
            estimated_weight_g=14.0,
            actual_weight_g=None,
            scrap_percentage=6.0,
            metal_type="gold_18k",
            costing_method_used="fifo",
            material_cost_calculated=875.00,
            labor_hours=16.0,
            hourly_rate=85.00,
            labor_cost=1360.00,
            profit_margin_percent=40.0,
            vat_rate=19.0,
            calculated_price=3200.00,
            order_type="ring",
            finish_type="mixed",
            complexity_rating=4,
            alloy="750",
            ring_size_mm=66.0,
            surface_finish="Matt aussen, Hochglanz innen",
            fitting_date=_days_from_now(12),
            has_scrap_gold=False,
            special_instructions="Innengravur 'T&A 2026' in Schreibschrift. Damenring: 3x Brillant 0.03ct in Kanalfassung.",
            created_at=_days_ago(20),
        ),
        # 2 - Kette Reparatur Verschluss (COMPLETED)
        dict(
            title="Kette Reparatur Verschluss",
            description="Silber 925 Ankerkette, Karabinerverschluss defekt. Neuen Verschluss anloeten.",
            price=45.00,
            status="completed",
            customer_id=customers[5].id,  # Helga Zimmermann
            deadline=_days_ago(5),
            current_location="Tresor",
            estimated_weight_g=12.0,
            actual_weight_g=12.2,
            scrap_percentage=0.5,
            metal_type="silver_925",
            material_cost_calculated=2.50,
            labor_hours=0.5,
            hourly_rate=75.00,
            labor_cost=37.50,
            profit_margin_percent=20.0,
            vat_rate=19.0,
            calculated_price=45.00,
            order_type="chain",
            finish_type="high_polish",
            complexity_rating=1,
            actual_hours=0.4,
            completed_at=_days_ago(6),
            alloy="ag925",
            surface_finish="Hochglanz",
            has_scrap_gold=False,
            special_instructions=None,
            created_at=_days_ago(12),
        ),
        # 3 - Altgold-Umarbeitung Brosche -> Ring
        dict(
            title="Altgold-Umarbeitung Brosche zu Ring",
            description="Alte Familienbrosche (585er, 8.5g) wird zu einem Ring umgearbeitet. Rotgold 750 Legierung mit Rubin aus Brosche.",
            price=1650.00,
            status="in_progress",
            customer_id=customers[8].id,  # Claudia Richter
            deadline=_days_from_now(18),
            current_location="Werkbank 2",
            estimated_weight_g=7.0,
            actual_weight_g=None,
            scrap_percentage=10.0,
            metal_type="rose_gold_18k",
            material_cost_calculated=280.00,
            labor_hours=8.0,
            hourly_rate=85.00,
            labor_cost=680.00,
            profit_margin_percent=35.0,
            vat_rate=19.0,
            calculated_price=1650.00,
            order_type="ring",
            finish_type="mixed",
            complexity_rating=4,
            alloy="750",
            ring_size_mm=55.0,
            surface_finish="Matt mit polierten Kanten",
            has_scrap_gold=True,
            special_instructions="Rubin aus alter Brosche uebernehmen, neue Zargenfassung. Altgold wird angerechnet.",
            created_at=_days_ago(10),
        ),
        # 4 - Platinring Braun (allergy customer)
        dict(
            title="Platinring schlicht Braun",
            description="Schlichter Bandring Platin 950, 4mm breit, gebuersted. Kunde hat Nickelallergie.",
            price=1250.00,
            status="in_progress",
            customer_id=customers[4].id,  # Stefan Braun
            deadline=_days_from_now(14),
            current_location="Werkbank 1",
            estimated_weight_g=8.0,
            actual_weight_g=None,
            scrap_percentage=7.0,
            metal_type="platinum_950",
            costing_method_used="specific",
            specific_metal_purchase_id=metal_purchases[5].id,  # PT950 batch
            material_cost_calculated=304.00,
            labor_hours=6.0,
            hourly_rate=85.00,
            labor_cost=510.00,
            profit_margin_percent=40.0,
            vat_rate=19.0,
            calculated_price=1250.00,
            order_type="ring",
            finish_type="brushed",
            complexity_rating=2,
            alloy="pt950",
            ring_size_mm=62.0,
            surface_finish="Laengs gebuerstet",
            has_scrap_gold=False,
            special_instructions="ACHTUNG: Nickelallergie! Nur Platin 950 verwenden. Keine Lot-Legierungen mit Nickel.",
            created_at=_days_ago(8),
        ),
        # 5 - Silber-Anhaenger Fisch (COMPLETED + DELIVERED)
        dict(
            title="Silberanhaenger Fisch",
            description="Handgefertigter Fisch-Anhaenger, Silber 925, gesaegt und gefeilt, matt mit polierten Details.",
            price=180.00,
            status="delivered",
            customer_id=customers[6].id,  # Lena Fischer
            deadline=_days_ago(15),
            current_location="Ausgang",
            estimated_weight_g=8.0,
            actual_weight_g=7.5,
            scrap_percentage=12.0,
            metal_type="silver_925",
            material_cost_calculated=9.60,
            labor_hours=3.0,
            hourly_rate=75.00,
            labor_cost=225.00,
            profit_margin_percent=30.0,
            vat_rate=19.0,
            calculated_price=180.00,
            order_type="pendant",
            finish_type="mixed",
            complexity_rating=3,
            actual_hours=3.2,
            completed_at=_days_ago(16),
            alloy="ag925",
            surface_finish="Matt mit polierten Details",
            has_scrap_gold=False,
            created_at=_days_ago(30),
        ),
        # 6 - Diamant-Ohrstecker (DELIVERED with invoice)
        dict(
            title="Diamant-Ohrstecker Paar",
            description="Ohrstecker Weissgold 750, je 1x Brillant 0.10ct, Krappenfassung 4-fach.",
            price=890.00,
            status="delivered",
            customer_id=customers[0].id,  # Maria Schneider
            deadline=_days_ago(20),
            current_location="Ausgang",
            estimated_weight_g=3.0,
            actual_weight_g=2.8,
            scrap_percentage=5.0,
            metal_type="white_gold_18k",
            material_cost_calculated=204.00,
            labor_hours=4.0,
            hourly_rate=85.00,
            labor_cost=340.00,
            profit_margin_percent=40.0,
            vat_rate=19.0,
            calculated_price=890.00,
            order_type="earrings",
            finish_type="high_polish",
            complexity_rating=3,
            actual_hours=3.8,
            completed_at=_days_ago(22),
            alloy="750",
            surface_finish="Hochglanz, rhodiniert",
            has_scrap_gold=False,
            created_at=_days_ago(35),
        ),
        # 7 - Gravur Trauring Auffrischung (COMPLETED)
        dict(
            title="Gravur Trauring Auffrischung",
            description="Bestehender Trauring Gold 585, Gravur auffrischen und neu polieren.",
            price=65.00,
            status="completed",
            customer_id=customers[5].id,  # Helga Zimmermann
            deadline=_days_ago(8),
            current_location="Tresor",
            estimated_weight_g=4.0,
            actual_weight_g=4.0,
            scrap_percentage=0.0,
            metal_type="gold_14k",
            material_cost_calculated=0.00,
            labor_hours=1.0,
            hourly_rate=75.00,
            labor_cost=75.00,
            profit_margin_percent=15.0,
            vat_rate=19.0,
            calculated_price=65.00,
            order_type="ring",
            finish_type="high_polish",
            complexity_rating=1,
            actual_hours=0.8,
            completed_at=_days_ago(9),
            alloy="585",
            surface_finish="Hochglanz",
            has_scrap_gold=False,
            special_instructions="Gravur 'H+R 1975' nachstechen und Ring polieren.",
            created_at=_days_ago(14),
        ),
        # 8 - Goldkette 750 Anker 50cm (NEW / RUSH ORDER)
        dict(
            title="Goldkette 750 Anker 50cm EILAUFTRAG",
            description="Ankerkette Gelbgold 750, 50cm, 2mm Breite. EILAUFTRAG fuer Geschenk!",
            price=2100.00,
            status="new",
            customer_id=customers[9].id,  # Klaus Mueller
            deadline=_days_from_now(2),  # RUSH: only 2 days!
            current_location="Eingang",
            estimated_weight_g=18.0,
            actual_weight_g=None,
            scrap_percentage=3.0,
            metal_type="gold_18k",
            material_cost_calculated=1152.00,
            labor_hours=5.0,
            hourly_rate=95.00,  # Rush surcharge
            labor_cost=475.00,
            profit_margin_percent=35.0,
            vat_rate=19.0,
            calculated_price=2100.00,
            order_type="chain",
            finish_type="high_polish",
            complexity_rating=3,
            alloy="750",
            surface_finish="Hochglanz",
            has_scrap_gold=False,
            special_instructions="EILAUFTRAG! Muss bis Freitag fertig sein (Hochzeitstag-Geschenk).",
            created_at=_days_ago(1),
        ),
        # 9 - Armband Silber 925 (DRAFT)
        dict(
            title="Armband Silber 925 Glieder",
            description="Gliederarmband Silber 925, 19cm, Kastenverschluss. Entwurf noch nicht freigegeben.",
            price=None,
            status="draft",
            customer_id=customers[4].id,  # Stefan Braun
            deadline=None,
            current_location=None,
            estimated_weight_g=25.0,
            metal_type="silver_925",
            order_type="bracelet",
            finish_type="brushed",
            complexity_rating=3,
            alloy="ag925",
            has_scrap_gold=False,
            special_instructions="Kunde moechte erst Wachsmodell sehen. Nickelfrei!",
            created_at=_days_ago(3),
        ),
        # 10 - Perlenring Umarbeitung (COMPLETED with weight deviation)
        dict(
            title="Perlenring Umarbeitung",
            description="Bestehender Perlenring, neue Fassung in Gelbgold 750. Perle wird uebernommen.",
            price=750.00,
            status="completed",
            customer_id=customers[0].id,  # Maria Schneider
            deadline=_days_ago(3),
            current_location="Tresor",
            estimated_weight_g=4.5,
            actual_weight_g=5.2,  # Deviation: more than estimated
            scrap_percentage=5.0,
            metal_type="gold_18k",
            material_cost_calculated=312.00,
            labor_hours=5.0,
            hourly_rate=85.00,
            labor_cost=425.00,
            profit_margin_percent=30.0,
            vat_rate=19.0,
            calculated_price=750.00,
            order_type="ring",
            finish_type="high_polish",
            complexity_rating=3,
            actual_hours=6.5,  # Took longer than estimated
            completed_at=_days_ago(4),
            alloy="750",
            ring_size_mm=54.0,
            surface_finish="Hochglanz",
            has_scrap_gold=False,
            special_instructions="Perle vorsichtig aus alter Fassung loesen. Neue Zargenfassung.",
            created_at=_days_ago(18),
        ),
        # 11 - Manschettenknuepfe Gold 585 (NEW)
        dict(
            title="Manschettenknopf-Paar Gold 585",
            description="Manschettenknuepfe Gold 585, rund, 15mm Durchmesser, mit Monogramm 'MB'.",
            price=980.00,
            status="new",
            customer_id=customers[7].id,  # Dr. Bauer
            deadline=_days_from_now(21),
            current_location="Eingang",
            estimated_weight_g=12.0,
            metal_type="gold_14k",
            order_type="custom",
            finish_type="high_polish",
            complexity_rating=3,
            alloy="585",
            has_scrap_gold=False,
            special_instructions="Monogramm 'MB' in Schreibschrift gravieren. Klappmechanismus muss leichtgaengig sein.",
            created_at=_days_ago(2),
        ),
        # 12 - Saphir-Anhaenger (CONFIRMED)
        dict(
            title="Saphir-Anhaenger Tropfenform",
            description="Anhaenger Weissgold 750 mit ovalem Saphir 0.60ct in Zargenfassung. Tropfenfoermiges Design.",
            price=1450.00,
            status="confirmed",
            customer_id=customers[6].id,  # Lena Fischer
            deadline=_days_from_now(16),
            current_location="Werkbank 2",
            estimated_weight_g=4.0,
            metal_type="white_gold_18k",
            material_cost_calculated=272.00,
            labor_hours=6.0,
            hourly_rate=85.00,
            labor_cost=510.00,
            profit_margin_percent=40.0,
            vat_rate=19.0,
            calculated_price=1450.00,
            order_type="pendant",
            finish_type="high_polish",
            complexity_rating=4,
            alloy="750",
            surface_finish="Hochglanz, rhodiniert",
            has_scrap_gold=False,
            special_instructions="Minimalistisches Design, Oese fuer 1.5mm Kette. Saphir muss zentriert sitzen.",
            created_at=_days_ago(5),
        ),
        # 13 - Brosche Art-Deco Stil (IN_PROGRESS)
        dict(
            title="Brosche Art-Deco Stil",
            description="Art-Deco Brosche Gelbgold 750, geometrisches Design, mit Onyx-Einlagen und 4x Melee-Brillanten.",
            price=2800.00,
            status="in_progress",
            customer_id=customers[3].id,  # Juwelier Hoffmann
            deadline=_days_from_now(30),
            current_location="Werkbank 1",
            estimated_weight_g=15.0,
            metal_type="gold_18k",
            material_cost_calculated=937.50,
            labor_hours=20.0,
            hourly_rate=85.00,
            labor_cost=1700.00,
            profit_margin_percent=35.0,
            vat_rate=19.0,
            calculated_price=2800.00,
            order_type="brooch",
            finish_type="mixed",
            complexity_rating=5,
            alloy="750",
            surface_finish="Hochglanz und matt im Wechsel",
            has_scrap_gold=False,
            special_instructions="Geometrisches Art-Deco Muster nach Kundenzeichnung. Onyx muss passgenau eingearbeitet werden. Geschaeftskunde Hoffmann, 10% Rabatt.",
            created_at=_days_ago(7),
        ),
        # 14 - Charm-Armband Silber (DELIVERED)
        dict(
            title="Charm-Armband Silber 925",
            description="Bettelarmband Silber 925 mit 5 handgefertigten Charms (Stern, Herz, Anker, Schluessel, Kleeblatt).",
            price=320.00,
            status="delivered",
            customer_id=customers[6].id,  # Lena Fischer
            deadline=_days_ago(10),
            current_location="Ausgang",
            estimated_weight_g=28.0,
            actual_weight_g=26.5,
            scrap_percentage=8.0,
            metal_type="silver_925",
            material_cost_calculated=33.60,
            labor_hours=6.0,
            hourly_rate=75.00,
            labor_cost=450.00,
            profit_margin_percent=30.0,
            vat_rate=19.0,
            calculated_price=320.00,
            order_type="bracelet",
            finish_type="mixed",
            complexity_rating=3,
            actual_hours=5.5,
            completed_at=_days_ago(12),
            alloy="ag925",
            surface_finish="Hochglanz Charms, matt Kette",
            has_scrap_gold=False,
            special_instructions="5 Charms einzeln gefertigt: Stern, Herz, Anker, Schluessel, Kleeblatt.",
            created_at=_days_ago(25),
        ),
    ]
    orders = []
    for data in orders_data:
        o = Order(**data)
        db.add(o)
        orders.append(o)
    await db.flush()
    print(f"  Auftraege: {len(orders)} erstellt")
    return orders


async def seed_gemstones(db, orders) -> list:
    """Create gemstones on relevant orders."""
    gemstones_data = [
        # Order 0 - Verlobungsring: 1x Brillant 0.50ct
        dict(
            order_id=orders[0].id,
            type="diamond", carat=0.50, quality="VS1", color="G",
            cut="Excellent", shape="Round Brilliant",
            cost=2850.00, quantity=1, total_cost=2850.00,
            setting_type="Krappenfassung (6-fach)",
            certificate_number="GIA-2026-78451234",
            certificate_authority="GIA",
            notes="Hauptstein Verlobungsring Weber.",
        ),
        # Order 1 - Eheringe: 3x Melee Brillant 0.03ct
        dict(
            order_id=orders[1].id,
            type="diamond", carat=0.03, quality="VS2", color="H",
            cut="Very Good", shape="Round Brilliant",
            cost=45.00, quantity=3, total_cost=135.00,
            setting_type="Kanalfassung",
            notes="Melee-Brillanten fuer Damen-Ehering, in Kanalfassung.",
        ),
        # Order 3 - Altgold-Umarbeitung: Rubin aus Brosche
        dict(
            order_id=orders[3].id,
            type="ruby", carat=0.75, quality=None, color="deep red",
            cut="Good", shape="Oval",
            cost=0.00, quantity=1, total_cost=0.00,  # Customer's own stone
            setting_type="Zargenfassung",
            notes="Rubin aus alter Familienbrosche uebernommen. Fassung pruefen!",
        ),
        # Order 6 - Ohrstecker: 2x Brillant 0.10ct
        dict(
            order_id=orders[6].id,
            type="diamond", carat=0.10, quality="VS2", color="H",
            cut="Very Good", shape="Round Brilliant",
            cost=180.00, quantity=2, total_cost=360.00,
            setting_type="Krappenfassung (4-fach)",
            notes="Paar Ohrstecker, optisch identische Steine.",
        ),
        # Order 12 - Saphir-Anhaenger: Saphir 0.60ct
        dict(
            order_id=orders[12].id,
            type="sapphire", carat=0.60, quality=None, color="royal blue",
            cut="Very Good", shape="Oval",
            cost=950.00, quantity=1, total_cost=950.00,
            setting_type="Zargenfassung",
            notes="Koenigsblauer Sri-Lanka Saphir.",
        ),
        # Order 13 - Brosche Art-Deco: 4x Melee Brillant
        dict(
            order_id=orders[13].id,
            type="diamond", carat=0.02, quality="SI1", color="I",
            cut="Good", shape="Round Brilliant",
            cost=35.00, quantity=4, total_cost=140.00,
            setting_type="Pavee-Fassung",
            notes="Melee-Brillanten fuer Art-Deco Muster.",
        ),
        # Order 13 - Brosche Art-Deco: Onyx Einlagen
        dict(
            order_id=orders[13].id,
            type="onyx", carat=None, quality=None, color="black",
            cut=None, shape="Custom (geometrisch)",
            cost=25.00, quantity=3, total_cost=75.00,
            setting_type="Einlage (eingeklebt)",
            notes="Schwarzer Onyx, passgenau zugeschliffen fuer geometrisches Art-Deco Muster.",
        ),
        # Order 10 - Perlenring: Suesswasserperle
        dict(
            order_id=orders[10].id,
            type="pearl", carat=None, quality="AAA", color="creme-weiss",
            cut=None, shape="Rund (8mm)",
            cost=0.00, quantity=1, total_cost=0.00,  # Customer's own pearl
            setting_type="Zargenfassung",
            notes="Kundenperle aus altem Ring. 8mm Suesswasserperle, unbeschaedigt.",
        ),
    ]
    gemstones = []
    for data in gemstones_data:
        g = Gemstone(**data)
        db.add(g)
        gemstones.append(g)
    await db.flush()
    print(f"  Edelsteine: {len(gemstones)} erstellt")
    return gemstones


async def seed_material_usage(db, orders, metal_purchases) -> list:
    """Create material usage records linking orders to metal purchase batches."""
    usage_data = [
        # Order 0 (Verlobungsring) -> Gold 18K batch 1
        dict(
            order_id=orders[0].id, metal_purchase_id=metal_purchases[0].id,
            weight_used_g=5.9, cost_at_time=368.75, price_per_gram_at_time=62.50,
            costing_method="fifo", used_at=_days_ago(10),
        ),
        # Order 1 (Eheringe) -> Gold 18K batch 1
        dict(
            order_id=orders[1].id, metal_purchase_id=metal_purchases[0].id,
            weight_used_g=14.8, cost_at_time=925.00, price_per_gram_at_time=62.50,
            costing_method="fifo", used_at=_days_ago(12),
        ),
        # Order 2 (Kette Reparatur) -> Silver 925 batch 1
        dict(
            order_id=orders[2].id, metal_purchase_id=metal_purchases[3].id,
            weight_used_g=1.5, cost_at_time=1.80, price_per_gram_at_time=1.20,
            costing_method="fifo", used_at=_days_ago(8),
        ),
        # Order 4 (Platinring) -> Platinum batch
        dict(
            order_id=orders[4].id, metal_purchase_id=metal_purchases[5].id,
            weight_used_g=8.5, cost_at_time=323.00, price_per_gram_at_time=38.00,
            costing_method="specific", used_at=_days_ago(5),
        ),
        # Order 5 (Silberanhaenger) -> Silver 925 batch 1
        dict(
            order_id=orders[5].id, metal_purchase_id=metal_purchases[3].id,
            weight_used_g=9.0, cost_at_time=10.80, price_per_gram_at_time=1.20,
            costing_method="fifo", used_at=_days_ago(20),
        ),
        # Order 6 (Ohrstecker) -> White Gold batch
        dict(
            order_id=orders[6].id, metal_purchase_id=metal_purchases[6].id,
            weight_used_g=3.2, cost_at_time=217.60, price_per_gram_at_time=68.00,
            costing_method="fifo", used_at=_days_ago(25),
        ),
        # Order 10 (Perlenring) -> Gold 18K batch 1
        dict(
            order_id=orders[10].id, metal_purchase_id=metal_purchases[0].id,
            weight_used_g=5.5, cost_at_time=343.75, price_per_gram_at_time=62.50,
            costing_method="fifo", used_at=_days_ago(10),
        ),
        # Order 14 (Charm-Armband) -> Silver 925 batch 1
        dict(
            order_id=orders[14].id, metal_purchase_id=metal_purchases[3].id,
            weight_used_g=30.0, cost_at_time=36.00, price_per_gram_at_time=1.20,
            costing_method="fifo", used_at=_days_ago(18),
        ),
    ]
    records = []
    for data in usage_data:
        mu = MaterialUsage(**data)
        db.add(mu)
        records.append(mu)
    await db.flush()
    print(f"  Materialverbrauch: {len(records)} Eintraege erstellt")
    return records


async def seed_time_entries(db, orders, users, activities) -> list:
    """Create 24 time entries spread across orders and activities."""
    goldsmith = users[0]  # Markus
    admin = users[1]  # Petra

    # Map activity names to activity objects for convenience
    act_map = {a.name: a for a in activities}

    entries_data = [
        # ── Order 0: Verlobungsring (IN_PROGRESS) ──
        dict(
            order_id=orders[0].id, user_id=goldsmith.id,
            activity_id=act_map["Kundenberatung"].id,
            start_time=_days_ago(14).replace(hour=9), end_time=_days_ago(14).replace(hour=10),
            duration_minutes=60, location="Laden",
            complexity_rating=3, quality_rating=5,
            notes="Erstgespraech mit Thomas Weber. Entwurfsskizze angefertigt.",
        ),
        dict(
            order_id=orders[0].id, user_id=goldsmith.id,
            activity_id=act_map["Giessen"].id,
            start_time=_days_ago(10).replace(hour=8), end_time=_days_ago(10).replace(hour=11),
            duration_minutes=180, location="Werkbank 1",
            complexity_rating=5, quality_rating=4,
            notes="Wachsmodell erstellt und gegossen. Guss sauber, minimale Lunker.",
        ),
        dict(
            order_id=orders[0].id, user_id=goldsmith.id,
            activity_id=act_map["Feilen"].id,
            start_time=_days_ago(9).replace(hour=9), end_time=_days_ago(9).replace(hour=12),
            duration_minutes=180, location="Werkbank 1",
            complexity_rating=4, quality_rating=4,
            notes="Rohling ausgefeilt und Ringform herausgearbeitet.",
        ),
        dict(
            order_id=orders[0].id, user_id=goldsmith.id,
            activity_id=act_map["Loeten"].id,
            start_time=_days_ago(8).replace(hour=10), end_time=_days_ago(8).replace(hour=11),
            duration_minutes=60, location="Werkbank 1",
            complexity_rating=4, quality_rating=5,
            notes="Krappen angeloetet, saubere Loetstellen.",
        ),
        # ── Order 1: Eheringe (IN_PROGRESS) ──
        dict(
            order_id=orders[1].id, user_id=goldsmith.id,
            activity_id=act_map["Schmieden"].id,
            start_time=_days_ago(12).replace(hour=8), end_time=_days_ago(12).replace(hour=12),
            duration_minutes=240, location="Werkbank 1",
            complexity_rating=3, quality_rating=4,
            notes="Beide Ringschienen geschmiedet und auf Groesse gebracht.",
        ),
        dict(
            order_id=orders[1].id, user_id=goldsmith.id,
            activity_id=act_map["Feilen"].id,
            start_time=_days_ago(11).replace(hour=9), end_time=_days_ago(11).replace(hour=12, minute=30),
            duration_minutes=210, location="Werkbank 1",
            complexity_rating=3, quality_rating=4,
            notes="Ringe ausgefeilt, Profil geformt. Damenring Kanal fuer Steine vorbereitet.",
        ),
        # ── Order 2: Kette Reparatur (COMPLETED) ──
        dict(
            order_id=orders[2].id, user_id=goldsmith.id,
            activity_id=act_map["Loeten"].id,
            start_time=_days_ago(7).replace(hour=14), end_time=_days_ago(7).replace(hour=14, minute=25),
            duration_minutes=25, location="Werkbank 2",
            complexity_rating=1, quality_rating=5,
            notes="Neuen Karabiner angeloetet. Einfache Reparatur.",
        ),
        # ── Order 3: Altgold-Umarbeitung (IN_PROGRESS) ──
        dict(
            order_id=orders[3].id, user_id=goldsmith.id,
            activity_id=act_map["Qualitaetskontrolle"].id,
            start_time=_days_ago(9).replace(hour=8), end_time=_days_ago(9).replace(hour=8, minute=30),
            duration_minutes=30, location="Werkbank 2",
            complexity_rating=2, quality_rating=4,
            notes="Altgold geprueft. Brosche 585er bestaetigt (Saeurentest). Rubin intakt.",
        ),
        dict(
            order_id=orders[3].id, user_id=goldsmith.id,
            activity_id=act_map["Giessen"].id,
            start_time=_days_ago(6).replace(hour=8), end_time=_days_ago(6).replace(hour=10, minute=30),
            duration_minutes=150, location="Werkbank 2",
            complexity_rating=4, quality_rating=4,
            notes="Wachsmodell fuer neuen Ring erstellt und gegossen. Rotgold 750.",
        ),
        # ── Order 4: Platinring (IN_PROGRESS) ──
        dict(
            order_id=orders[4].id, user_id=goldsmith.id,
            activity_id=act_map["Schmieden"].id,
            start_time=_days_ago(5).replace(hour=8), end_time=_days_ago(5).replace(hour=11),
            duration_minutes=180, location="Werkbank 1",
            complexity_rating=3, quality_rating=5,
            notes="Platin geschmiedet. Haerteres Material als Gold, mehr Kraftaufwand.",
        ),
        # ── Order 5: Silberanhaenger (DELIVERED) ──
        dict(
            order_id=orders[5].id, user_id=goldsmith.id,
            activity_id=act_map["Saegen"].id,
            start_time=_days_ago(22).replace(hour=9), end_time=_days_ago(22).replace(hour=10, minute=30),
            duration_minutes=90, location="Werkbank 2",
            complexity_rating=3, quality_rating=4,
            notes="Fischform aus Silberblech ausgesaegt.",
        ),
        dict(
            order_id=orders[5].id, user_id=goldsmith.id,
            activity_id=act_map["Feilen"].id,
            start_time=_days_ago(21).replace(hour=9), end_time=_days_ago(21).replace(hour=10),
            duration_minutes=60, location="Werkbank 2",
            complexity_rating=3, quality_rating=5,
            notes="Kanten gefeilt und Flossen detailliert.",
        ),
        dict(
            order_id=orders[5].id, user_id=goldsmith.id,
            activity_id=act_map["Polieren"].id,
            start_time=_days_ago(20).replace(hour=14), end_time=_days_ago(20).replace(hour=14, minute=40),
            duration_minutes=40, location="Polierbereich",
            complexity_rating=2, quality_rating=5,
            notes="Details poliert, Koerper matt belassen.",
        ),
        # ── Order 6: Ohrstecker (DELIVERED) ──
        dict(
            order_id=orders[6].id, user_id=goldsmith.id,
            activity_id=act_map["Fassen (Steine)"].id,
            start_time=_days_ago(24).replace(hour=10), end_time=_days_ago(24).replace(hour=12),
            duration_minutes=120, location="Werkbank 1",
            complexity_rating=3, quality_rating=5,
            notes="Brillanten in Krappenfassung gesetzt. Symmetrie beider Stecker kontrolliert.",
        ),
        dict(
            order_id=orders[6].id, user_id=goldsmith.id,
            activity_id=act_map["Polieren"].id,
            start_time=_days_ago(23).replace(hour=14), end_time=_days_ago(23).replace(hour=14, minute=45),
            duration_minutes=45, location="Polierbereich",
            complexity_rating=2, quality_rating=5,
            notes="Rhodiniert und hochglanzpoliert.",
        ),
        # ── Order 7: Gravur Auffrischung (COMPLETED) ──
        dict(
            order_id=orders[7].id, user_id=goldsmith.id,
            activity_id=act_map["Gravieren"].id,
            start_time=_days_ago(10).replace(hour=15), end_time=_days_ago(10).replace(hour=15, minute=30),
            duration_minutes=30, location="Werkbank 1",
            complexity_rating=1, quality_rating=5,
            notes="Gravur 'H+R 1975' nachgestochen.",
        ),
        dict(
            order_id=orders[7].id, user_id=goldsmith.id,
            activity_id=act_map["Polieren"].id,
            start_time=_days_ago(10).replace(hour=15, minute=30), end_time=_days_ago(10).replace(hour=15, minute=50),
            duration_minutes=20, location="Polierbereich",
            complexity_rating=1, quality_rating=5,
            notes="Ring poliert, wie neu.",
        ),
        # ── Order 10: Perlenring (COMPLETED) ──
        dict(
            order_id=orders[10].id, user_id=goldsmith.id,
            activity_id=act_map["Loeten"].id,
            start_time=_days_ago(8).replace(hour=8), end_time=_days_ago(8).replace(hour=9, minute=30),
            duration_minutes=90, location="Werkbank 1",
            complexity_rating=3, quality_rating=4,
            notes="Neue Zargenfassung fuer Perle angeloetet. Vorsicht: Perle waermeempfindlich!",
        ),
        dict(
            order_id=orders[10].id, user_id=goldsmith.id,
            activity_id=act_map["Fassen (Steine)"].id,
            start_time=_days_ago(7).replace(hour=9), end_time=_days_ago(7).replace(hour=10, minute=30),
            duration_minutes=90, location="Werkbank 1",
            complexity_rating=3, quality_rating=5,
            notes="Perle in neue Zargen eingesetzt. Sitzt fest, kein Spiel.",
        ),
        dict(
            order_id=orders[10].id, user_id=goldsmith.id,
            activity_id=act_map["Polieren"].id,
            start_time=_days_ago(6).replace(hour=14), end_time=_days_ago(6).replace(hour=14, minute=30),
            duration_minutes=30, location="Polierbereich",
            complexity_rating=2, quality_rating=5,
            notes="Hochglanzpolitur. Perle abgeklebt.",
        ),
        # ── Order 13: Brosche Art-Deco (IN_PROGRESS) ──
        dict(
            order_id=orders[13].id, user_id=goldsmith.id,
            activity_id=act_map["Kundenberatung"].id,
            start_time=_days_ago(7).replace(hour=10), end_time=_days_ago(7).replace(hour=11, minute=30),
            duration_minutes=90, location="Laden",
            complexity_rating=4, quality_rating=5,
            notes="Ausfuehrliche Beratung mit Fr. Hoffmann. Kundenzeichnung besprochen und angepasst.",
        ),
        dict(
            order_id=orders[13].id, user_id=goldsmith.id,
            activity_id=act_map["Saegen"].id,
            start_time=_days_ago(4).replace(hour=8), end_time=_days_ago(4).replace(hour=12),
            duration_minutes=240, location="Werkbank 1",
            complexity_rating=5, quality_rating=4,
            notes="Geometrische Grundform ausgesaegt. Sehr detailreiche Arbeit.",
        ),
        # ── Order 14: Charm-Armband (DELIVERED) ──
        dict(
            order_id=orders[14].id, user_id=goldsmith.id,
            activity_id=act_map["Saegen"].id,
            start_time=_days_ago(18).replace(hour=8), end_time=_days_ago(18).replace(hour=11),
            duration_minutes=180, location="Werkbank 2",
            complexity_rating=3, quality_rating=4,
            notes="5 Charm-Formen ausgesaegt: Stern, Herz, Anker, Schluessel, Kleeblatt.",
        ),
        dict(
            order_id=orders[14].id, user_id=goldsmith.id,
            activity_id=act_map["Polieren"].id,
            start_time=_days_ago(15).replace(hour=14), end_time=_days_ago(15).replace(hour=15),
            duration_minutes=60, location="Polierbereich",
            complexity_rating=2, quality_rating=5,
            notes="Charms poliert, Armband-Glieder matt belassen.",
        ),
    ]
    entries = []
    for data in entries_data:
        te = TimeEntry(id=_uuid(), **data)
        db.add(te)
        entries.append(te)
    await db.flush()
    print(f"  Zeiteintraege: {len(entries)} erstellt")
    return entries


async def seed_interruptions(db, time_entries) -> list:
    """Create a few realistic interruptions."""
    interruptions = [
        Interruption(
            time_entry_id=time_entries[1].id,  # Giessen Verlobungsring
            reason="customer_call",
            duration_minutes=10,
            timestamp=_days_ago(10).replace(hour=9, minute=30),
        ),
        Interruption(
            time_entry_id=time_entries[4].id,  # Schmieden Eheringe
            reason="material_fetch",
            duration_minutes=5,
            timestamp=_days_ago(12).replace(hour=10),
        ),
        Interruption(
            time_entry_id=time_entries[9].id,  # Schmieden Platinring
            reason="customer_call",
            duration_minutes=15,
            timestamp=_days_ago(5).replace(hour=9, minute=30),
        ),
        Interruption(
            time_entry_id=time_entries[21].id,  # Saegen Brosche
            reason="material_fetch",
            duration_minutes=8,
            timestamp=_days_ago(4).replace(hour=10),
        ),
    ]
    for i in interruptions:
        db.add(i)
    await db.flush()
    print(f"  Unterbrechungen: {len(interruptions)} erstellt")
    return interruptions


async def seed_repair_jobs(db, customers, users) -> list:
    """Create 6 repair jobs in various statuses."""
    viewer = users[2]  # Lisa (Buerokraft receives items)
    goldsmith = users[0]  # Markus

    repairs_data = [
        # 0 - RECEIVED (just arrived)
        dict(
            repair_number="REP-2026-0001",
            bag_number="T-042",
            customer_id=customers[5].id,  # Helga Zimmermann
            received_by=viewer.id,
            item_description="Goldene Halskette, Gelbgold 585, Verschluss klemmt und oeffnet sich manchmal von selbst.",
            item_type=RepairItemType.CHAIN,
            metal_type="585 Gelbgold",
            estimated_value=450.00,
            status=RepairJobStatus.RECEIVED,
            created_at=_days_ago(1),
        ),
        # 1 - DIAGNOSED
        dict(
            repair_number="REP-2026-0002",
            bag_number="T-043",
            customer_id=customers[3].id,  # Juwelier Hoffmann
            received_by=viewer.id,
            item_description="Herrenring Gelbgold 750, Ringschiene an einer Stelle duenn geschliffen. Muss verstaerkt werden.",
            item_type=RepairItemType.RING,
            metal_type="750 Gelbgold",
            estimated_value=800.00,
            status=RepairJobStatus.DIAGNOSED,
            diagnosis_notes="Ringschiene auf 0.8mm abgenutzt (Soll: 1.5mm). Aufloeten einer Verstaerkung empfohlen. Alternativ neue Schiene.",
            estimated_cost=120.00,
            estimated_completion_date=_days_from_now(7),
            created_at=_days_ago(4),
        ),
        # 2 - IN_REPAIR
        dict(
            repair_number="REP-2026-0003",
            bag_number="T-044",
            customer_id=customers[0].id,  # Maria Schneider
            received_by=viewer.id,
            item_description="Silberarmband 925, Glieder locker, ein Glied gebrochen. Komplette Revision.",
            item_type=RepairItemType.BRACELET,
            metal_type="925 Silber",
            estimated_value=180.00,
            status=RepairJobStatus.IN_REPAIR,
            diagnosis_notes="Ein Glied gebrochen, drei weitere Glieder locker. Komplette Revision noetig: Glieder loeten, Verschluss pruefen.",
            estimated_cost=85.00,
            actual_cost=None,
            estimated_completion_date=_days_from_now(3),
            created_at=_days_ago(7),
        ),
        # 3 - READY (waiting for pickup)
        dict(
            repair_number="REP-2026-0004",
            bag_number="T-045",
            customer_id=customers[6].id,  # Lena Fischer
            received_by=viewer.id,
            item_description="Ohrringe Silber 925, Klappbuegel einer Creole verbogen.",
            item_type=RepairItemType.EARRING,
            metal_type="925 Silber",
            estimated_value=60.00,
            status=RepairJobStatus.READY,
            diagnosis_notes="Klappbuegel verbogen, laesst sich richten.",
            estimated_cost=25.00,
            actual_cost=20.00,
            estimated_completion_date=_days_ago(2),
            actual_completion_date=_days_ago(3),
            customer_notified_at=_days_ago(2),
            created_at=_days_ago(10),
        ),
        # 4 - PICKED_UP
        dict(
            repair_number="REP-2026-0005",
            bag_number="T-046",
            customer_id=customers[5].id,  # Helga Zimmermann
            received_by=viewer.id,
            item_description="Brosche Gelbgold 333, Nadelmechanismus defekt. Neue Nadelhalterung eingebaut.",
            item_type=RepairItemType.BROOCH,
            metal_type="333 Gelbgold",
            estimated_value=150.00,
            status=RepairJobStatus.PICKED_UP,
            diagnosis_notes="Nadelhalterung abgebrochen. Neue Halterung angeloetet.",
            estimated_cost=45.00,
            actual_cost=40.00,
            estimated_completion_date=_days_ago(12),
            actual_completion_date=_days_ago(14),
            customer_notified_at=_days_ago(13),
            picked_up_at=_days_ago(11),
            created_at=_days_ago(20),
        ),
        # 5 - QUALITY_CHECK
        dict(
            repair_number="REP-2026-0006",
            bag_number="T-047",
            customer_id=customers[4].id,  # Stefan Braun
            received_by=viewer.id,
            item_description="Platinkette 950, Karabinerverschluss Feder ausgeschlagen. Verschluss-Mechanismus ersetzen.",
            item_type=RepairItemType.CHAIN,
            metal_type="950 Platin",
            estimated_value=1200.00,
            status=RepairJobStatus.QUALITY_CHECK,
            diagnosis_notes="Karabiner-Feder defekt, nicht reparabel. Neuen Platin-Karabiner anfertigen und anloeten.",
            estimated_cost=95.00,
            actual_cost=90.00,
            estimated_completion_date=_days_from_now(1),
            actual_completion_date=NOW,
            created_at=_days_ago(8),
        ),
    ]
    repairs = []
    for data in repairs_data:
        r = RepairJob(**data)
        db.add(r)
        repairs.append(r)
    await db.flush()
    print(f"  Reparaturen: {len(repairs)} erstellt")
    return repairs


async def seed_quotes(db, orders, customers, users) -> list:
    """Create 4 quotes in different statuses."""
    admin = users[1]  # Petra

    quotes_data = [
        # 0 - DRAFT
        dict(
            quote_number="KV-2026-0001",
            order_id=orders[9].id,  # Armband DRAFT
            customer_id=customers[4].id,  # Stefan Braun
            created_by=admin.id,
            status=QuoteStatus.DRAFT,
            valid_until=_days_from_now(14),
            subtotal=380.00,
            tax_rate=19.0,
            tax_amount=72.20,
            total=452.20,
            notes="Entwurf fuer Gliederarmband Silber 925. Preis noch nicht final.",
            created_at=_days_ago(3),
        ),
        # 1 - SENT
        dict(
            quote_number="KV-2026-0002",
            order_id=orders[12].id,  # Saphir-Anhaenger
            customer_id=customers[6].id,  # Lena Fischer
            created_by=admin.id,
            status=QuoteStatus.SENT,
            valid_until=_days_from_now(10),
            subtotal=1218.49,
            tax_rate=19.0,
            tax_amount=231.51,
            total=1450.00,
            notes="Kostenvoranschlag fuer Saphir-Anhaenger in Tropfenform, Weissgold 750.",
            created_at=_days_ago(5),
        ),
        # 2 - APPROVED (with signature)
        dict(
            quote_number="KV-2026-0003",
            order_id=orders[0].id,  # Verlobungsring
            customer_id=customers[2].id,  # Anna Weber
            created_by=admin.id,
            status=QuoteStatus.APPROVED,
            valid_until=_days_from_now(0),
            approved_at=_days_ago(14),
            subtotal=4075.63,
            tax_rate=19.0,
            tax_amount=774.37,
            total=4850.00,
            customer_signature_data="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
            notes="Genehmigt durch Thomas Weber am Beratungstermin. Anzahlung 50% vereinbart.",
            created_at=_days_ago(15),
        ),
        # 3 - CONVERTED (became an order)
        dict(
            quote_number="KV-2026-0004",
            order_id=orders[1].id,  # Eheringe
            customer_id=customers[1].id,  # Thomas Weber
            created_by=admin.id,
            status=QuoteStatus.CONVERTED,
            valid_until=_days_ago(5),
            approved_at=_days_ago(20),
            converted_at=_days_ago(20),
            subtotal=2689.08,
            tax_rate=19.0,
            tax_amount=510.92,
            total=3200.00,
            customer_signature_data="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
            notes="Angebot fuer Eheringe-Paar, umgewandelt in Auftrag.",
            created_at=_days_ago(25),
        ),
    ]
    quotes = []
    for data in quotes_data:
        q = Quote(**data)
        db.add(q)
        quotes.append(q)
    await db.flush()

    # Line items for quotes
    line_items_data = [
        # Quote 0 (Armband DRAFT)
        dict(quote_id=quotes[0].id, line_type=QuoteLineType.MATERIAL,
             description="Silber 925, ca. 25g", quantity=25.0, unit_price=1.20, total=30.00),
        dict(quote_id=quotes[0].id, line_type=QuoteLineType.LABOR,
             description="Fertigung Gliederarmband, ca. 6h", quantity=6.0, unit_price=75.00, total=450.00),
        # Quote 1 (Saphir-Anhaenger SENT)
        dict(quote_id=quotes[1].id, line_type=QuoteLineType.MATERIAL,
             description="Weissgold 750, ca. 4g", quantity=4.0, unit_price=68.00, total=272.00),
        dict(quote_id=quotes[1].id, line_type=QuoteLineType.GEMSTONE,
             description="Saphir oval 0.60ct, koenigsblau", quantity=1.0, unit_price=950.00, total=950.00),
        dict(quote_id=quotes[1].id, line_type=QuoteLineType.LABOR,
             description="Fertigung Anhaenger mit Fassung, ca. 6h", quantity=6.0, unit_price=85.00, total=510.00),
        # Quote 2 (Verlobungsring APPROVED)
        dict(quote_id=quotes[2].id, line_type=QuoteLineType.MATERIAL,
             description="Gelbgold 750, ca. 5.5g (+ 8% Verschnitt)", quantity=5.9, unit_price=62.50, total=368.75),
        dict(quote_id=quotes[2].id, line_type=QuoteLineType.GEMSTONE,
             description="Brillant 0.50ct, VS1/G, GIA-Zertifikat", quantity=1.0, unit_price=2850.00, total=2850.00),
        dict(quote_id=quotes[2].id, line_type=QuoteLineType.LABOR,
             description="Fertigung Solitaerring inkl. Krappenfassung, ca. 12h", quantity=12.0, unit_price=85.00, total=1020.00),
        # Quote 3 (Eheringe CONVERTED)
        dict(quote_id=quotes[3].id, line_type=QuoteLineType.MATERIAL,
             description="Gelbgold 750, Paar ca. 14g (+ 6% Verschnitt)", quantity=14.8, unit_price=62.50, total=925.00),
        dict(quote_id=quotes[3].id, line_type=QuoteLineType.GEMSTONE,
             description="3x Brillant 0.03ct, VS2/H (Melee, Kanalfassung)", quantity=3.0, unit_price=45.00, total=135.00),
        dict(quote_id=quotes[3].id, line_type=QuoteLineType.LABOR,
             description="Fertigung Ehering-Paar inkl. Gravur, ca. 16h", quantity=16.0, unit_price=85.00, total=1360.00),
    ]
    for data in line_items_data:
        db.add(QuoteLineItem(**data))
    await db.flush()
    print(f"  Kostenvoranschlaege: {len(quotes)} erstellt (+ {len(line_items_data)} Positionen)")
    return quotes


async def seed_invoices(db, orders, customers, users) -> list:
    """Create 4 invoices in different statuses."""
    admin = users[1]  # Petra

    invoices_data = [
        # 0 - DRAFT
        dict(
            invoice_number="RE-2026-0001",
            order_id=orders[2].id,  # Kette Reparatur
            customer_id=customers[5].id,  # Helga Zimmermann
            created_by=admin.id,
            status=InvoiceStatus.DRAFT,
            issue_date=_days_ago(5),
            due_date=_days_from_now(9),
            subtotal=37.82,
            tax_rate=19.0,
            tax_amount=7.18,
            total=45.00,
            notes="Reparatur Kettenversschluss.",
            created_at=_days_ago(5),
        ),
        # 1 - SENT
        dict(
            invoice_number="RE-2026-0002",
            order_id=orders[5].id,  # Silberanhaenger
            customer_id=customers[6].id,  # Lena Fischer
            created_by=admin.id,
            status=InvoiceStatus.SENT,
            issue_date=_days_ago(14),
            due_date=_days_from_now(0),
            subtotal=151.26,
            tax_rate=19.0,
            tax_amount=28.74,
            total=180.00,
            notes="Silberanhaenger Fisch. Versand per Post.",
            payment_method=None,
            created_at=_days_ago(14),
        ),
        # 2 - PAID
        dict(
            invoice_number="RE-2026-0003",
            order_id=orders[6].id,  # Diamant-Ohrstecker
            customer_id=customers[0].id,  # Maria Schneider
            created_by=admin.id,
            status=InvoiceStatus.PAID,
            issue_date=_days_ago(20),
            due_date=_days_ago(6),
            paid_date=_days_ago(8),
            subtotal=747.90,
            tax_rate=19.0,
            tax_amount=142.10,
            total=890.00,
            notes="Diamant-Ohrstecker Paar. Bezahlt per Ueberweisung.",
            payment_method="Ueberweisung",
            created_at=_days_ago(20),
        ),
        # 3 - PAID (with Altgold credit, for Charm-Armband)
        dict(
            invoice_number="RE-2026-0004",
            order_id=orders[14].id,  # Charm-Armband
            customer_id=customers[6].id,  # Lena Fischer
            created_by=admin.id,
            status=InvoiceStatus.PAID,
            issue_date=_days_ago(10),
            due_date=_days_ago(0),
            paid_date=_days_ago(3),
            subtotal=268.91,
            tax_rate=19.0,
            tax_amount=51.09,
            total=320.00,
            notes="Charm-Armband Silber 925. Barzahlung bei Abholung.",
            payment_method="Bar",
            created_at=_days_ago(10),
        ),
    ]
    invoices = []
    for data in invoices_data:
        inv = Invoice(**data)
        db.add(inv)
        invoices.append(inv)
    await db.flush()

    # Line items
    line_items = [
        # Invoice 0 (Kette Reparatur DRAFT)
        dict(invoice_id=invoices[0].id, line_type=InvoiceLineType.MATERIAL,
             description="Silber 925 Karabinerverschluss", quantity=1.0, unit_price=2.50, total=2.50),
        dict(invoice_id=invoices[0].id, line_type=InvoiceLineType.LABOR,
             description="Reparatur Verschluss (Loeten), 0.5h", quantity=0.5, unit_price=75.00, total=37.50),
        # Invoice 1 (Silberanhaenger SENT)
        dict(invoice_id=invoices[1].id, line_type=InvoiceLineType.MATERIAL,
             description="Silber 925, 8g", quantity=8.0, unit_price=1.20, total=9.60),
        dict(invoice_id=invoices[1].id, line_type=InvoiceLineType.LABOR,
             description="Fertigung Anhaenger Fisch, 3.2h", quantity=3.2, unit_price=75.00, total=240.00),
        # Invoice 2 (Ohrstecker PAID)
        dict(invoice_id=invoices[2].id, line_type=InvoiceLineType.MATERIAL,
             description="Weissgold 750, 3.0g", quantity=3.0, unit_price=68.00, total=204.00),
        dict(invoice_id=invoices[2].id, line_type=InvoiceLineType.GEMSTONE,
             description="2x Brillant 0.10ct VS2/H", quantity=2.0, unit_price=180.00, total=360.00),
        dict(invoice_id=invoices[2].id, line_type=InvoiceLineType.LABOR,
             description="Fertigung Ohrstecker inkl. Fassung, 3.8h", quantity=3.8, unit_price=85.00, total=323.00),
        # Invoice 3 (Charm-Armband PAID)
        dict(invoice_id=invoices[3].id, line_type=InvoiceLineType.MATERIAL,
             description="Silber 925, 28g", quantity=28.0, unit_price=1.20, total=33.60),
        dict(invoice_id=invoices[3].id, line_type=InvoiceLineType.LABOR,
             description="Fertigung 5 Charms + Armband, 5.5h", quantity=5.5, unit_price=75.00, total=412.50),
    ]
    for data in line_items:
        db.add(InvoiceLineItem(**data))
    await db.flush()
    print(f"  Rechnungen: {len(invoices)} erstellt (+ {len(line_items)} Positionen)")
    return invoices


async def seed_scrap_gold(db, orders, customers, users) -> list:
    """Create 3 scrap gold records."""
    goldsmith = users[0]

    scrap_records = []

    # 0 - SIGNED (linked to Altgold-Umarbeitung order)
    sg1 = ScrapGold(
        order_id=orders[3].id,  # Altgold-Umarbeitung Brosche
        customer_id=customers[8].id,  # Claudia Richter
        created_by=goldsmith.id,
        status=ScrapGoldStatus.SIGNED,
        total_fine_gold_g=4.97,  # 8.5g * 0.585 = 4.9725
        total_value_eur=310.78,  # 4.97g * 62.50 EUR/g
        gold_price_per_g=62.50,
        price_source="fixed_rate",
        signature_data="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
        signed_at=_days_ago(9),
        notes="Alte Familienbrosche 585er Gold, 8.5g brutto. Rubin wird im neuen Ring weiterverwendet.",
        created_at=_days_ago(10),
    )
    db.add(sg1)
    await db.flush()
    scrap_records.append(sg1)

    # Items for scrap gold 1
    sg1_items = [
        ScrapGoldItem(
            scrap_gold_id=sg1.id,
            description="Alte Familienbrosche mit Rubin",
            alloy=AlloyType.GOLD_585,
            weight_g=8.5,
            fine_content_g=4.97,  # 8.5 * 0.585
        ),
    ]
    for item in sg1_items:
        db.add(item)

    # 1 - CREDITED (applied to invoice — from a previous customer)
    sg2 = ScrapGold(
        order_id=orders[10].id,  # Perlenring
        customer_id=customers[0].id,  # Maria Schneider
        created_by=goldsmith.id,
        status=ScrapGoldStatus.CREDITED,
        total_fine_gold_g=2.78,
        total_value_eur=173.75,
        gold_price_per_g=62.50,
        price_source="fixed_rate",
        signature_data="data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=",
        signed_at=_days_ago(17),
        notes="Alter Perlenring-Fassung (750er) wird gutgeschrieben.",
        created_at=_days_ago(18),
    )
    db.add(sg2)
    await db.flush()
    scrap_records.append(sg2)

    sg2_items = [
        ScrapGoldItem(
            scrap_gold_id=sg2.id,
            description="Alte Ringfassung vom Perlenring",
            alloy=AlloyType.GOLD_750,
            weight_g=3.7,
            fine_content_g=2.78,  # 3.7 * 0.75
        ),
    ]
    for item in sg2_items:
        db.add(item)

    # 2 - RECEIVED (just documented, mixed alloys)
    sg3 = ScrapGold(
        order_id=orders[11].id,  # Manschettenknuepfe (link to an order even though not yet used)
        customer_id=customers[7].id,  # Dr. Bauer
        created_by=goldsmith.id,
        status=ScrapGoldStatus.RECEIVED,
        total_fine_gold_g=0.0,  # Not yet calculated
        total_value_eur=0.0,
        gold_price_per_g=None,
        price_source="fixed_rate",
        notes="Diverse Altgold-Stuecke von Dr. Bauer. Noch nicht berechnet.",
        created_at=_days_ago(2),
    )
    db.add(sg3)
    await db.flush()
    scrap_records.append(sg3)

    sg3_items = [
        ScrapGoldItem(
            scrap_gold_id=sg3.id,
            description="Alte Goldfuellung (Dental)",
            alloy=AlloyType.GOLD_750,
            weight_g=2.1,
            fine_content_g=1.58,  # 2.1 * 0.75
        ),
        ScrapGoldItem(
            scrap_gold_id=sg3.id,
            description="Bruchstueck Kette",
            alloy=AlloyType.GOLD_333,
            weight_g=4.0,
            fine_content_g=1.33,  # 4.0 * 0.333
        ),
    ]
    for item in sg3_items:
        db.add(item)
    await db.flush()

    print(f"  Altgold: {len(scrap_records)} Eintraege erstellt")
    return scrap_records


async def seed_calendar_events(db, orders, users) -> list:
    """Create 6 calendar events."""
    goldsmith = users[0]
    admin = users[1]
    viewer = users[2]

    events_data = [
        # Fitting appointment for Eheringe Weber
        dict(
            title="Anprobe Eheringe Weber",
            description="Erste Anprobe der Eheringe mit Thomas und Anna Weber. Ringgroessen pruefen.",
            event_type=CalendarEventType.APPOINTMENT,
            start_datetime=_days_from_now(12).replace(hour=10),
            end_datetime=_days_from_now(12).replace(hour=11),
            all_day=False,
            order_id=orders[1].id,
            user_id=goldsmith.id,
            color="#667EEA",
        ),
        # Workshop task: rush order
        dict(
            title="EILAUFTRAG: Goldkette Mueller",
            description="Goldkette 750 Anker 50cm muss bis Freitag fertig sein!",
            event_type=CalendarEventType.WORKSHOP_TASK,
            start_datetime=_days_from_now(1).replace(hour=8),
            end_datetime=_days_from_now(2).replace(hour=17),
            all_day=False,
            order_id=orders[8].id,
            user_id=goldsmith.id,
            color="#FF6B6B",
        ),
        # Reminder: Maria Schneider birthday
        dict(
            title="Geburtstag: Maria Schneider (Stammkundin)",
            description="Glueckwuensche senden. Evtl. Gutschein als Aufmerksamkeit.",
            event_type=CalendarEventType.REMINDER,
            start_datetime=_days_from_now(14).replace(hour=9),
            all_day=True,
            user_id=viewer.id,
            color="#95E1D3",
        ),
        # Supplier meeting
        dict(
            title="Lieferantengespraech C.HAFNER",
            description="Jahreskonditionen fuer Goldankauf besprechen. Mengenrabatt verhandeln.",
            event_type=CalendarEventType.APPOINTMENT,
            start_datetime=_days_from_now(5).replace(hour=14),
            end_datetime=_days_from_now(5).replace(hour=15, minute=30),
            all_day=False,
            user_id=admin.id,
            color="#764BA2",
        ),
        # Workshop maintenance
        dict(
            title="Wartung Poliermaschine",
            description="Jaehrliche Wartung der Poliermaschine durch Techniker.",
            event_type=CalendarEventType.WORKSHOP_TASK,
            start_datetime=_days_from_now(8).replace(hour=8),
            end_datetime=_days_from_now(8).replace(hour=10),
            all_day=False,
            user_id=goldsmith.id,
            color="#A0AEC0",
        ),
        # Delivery date reminder
        dict(
            title="Abholung Ohrringe Fischer (Reparatur)",
            description="Lena Fischer kommt die reparierten Creolen abholen.",
            event_type=CalendarEventType.REMINDER,
            start_datetime=_days_from_now(1).replace(hour=11),
            all_day=False,
            order_id=None,
            user_id=viewer.id,
            color="#FF8C42",
        ),
    ]
    events = []
    for data in events_data:
        ev = CalendarEvent(**data)
        db.add(ev)
        events.append(ev)
    await db.flush()
    print(f"  Kalendereintraege: {len(events)} erstellt")
    return events


async def seed_notifications(db, orders, customers, users) -> list:
    """Create 12 notifications across users."""
    goldsmith = users[0]
    admin = users[1]
    viewer = users[2]

    notifs_data = [
        # Deadline warnings
        dict(
            user_id=goldsmith.id,
            title="Deadline in 2 Tagen: Goldkette Mueller",
            message="EILAUFTRAG Goldkette 750 Anker 50cm muss bis uebermorgen fertig sein. Bitte priorisieren!",
            notification_type=NotificationTypeEnum.DEADLINE_WARNING,
            severity=NotificationSeverityEnum.URGENT,
            related_order_id=orders[8].id,
            is_read=False,
            created_at=_hours_ago(2),
        ),
        dict(
            user_id=goldsmith.id,
            title="Deadline in 10 Tagen: Verlobungsring Weber",
            message="Verlobungsring Solitaer Weber — noch Fassen und Polieren offen.",
            notification_type=NotificationTypeEnum.DEADLINE_WARNING,
            severity=NotificationSeverityEnum.WARNING,
            related_order_id=orders[0].id,
            is_read=True,
            read_at=_hours_ago(1),
            created_at=_days_ago(1),
        ),
        # Pickup ready
        dict(
            user_id=viewer.id,
            title="Abholbereit: Reparatur Creolen Fischer",
            message="Reparatur REP-2026-0004 (Creolen Silber 925) ist fertig. Kundin Lena Fischer benachrichtigen.",
            notification_type=NotificationTypeEnum.PICKUP_READY,
            severity=NotificationSeverityEnum.INFO,
            related_customer_id=customers[6].id,
            is_read=True,
            read_at=_days_ago(2),
            created_at=_days_ago(3),
        ),
        # Low stock
        dict(
            user_id=admin.id,
            title="Mindestbestand unterschritten: Platin 950 Draht",
            message="Platin 950 Draht 1.2mm: Restbestand 14.0g, Mindestbestand 5.0g. Nachbestellen pruefen.",
            notification_type=NotificationTypeEnum.LOW_STOCK,
            severity=NotificationSeverityEnum.WARNING,
            is_read=False,
            created_at=_days_ago(1),
        ),
        # Fitting reminder
        dict(
            user_id=goldsmith.id,
            title="Anprobe-Erinnerung: Eheringe Weber",
            message="In 12 Tagen Anprobetermin fuer Eheringe Weber. Ringe muessen bis dahin anprobefertig sein!",
            notification_type=NotificationTypeEnum.FITTING_REMINDER,
            severity=NotificationSeverityEnum.WARNING,
            related_order_id=orders[1].id,
            is_read=False,
            created_at=_hours_ago(4),
        ),
        # Order status changes
        dict(
            user_id=viewer.id,
            title="Auftrag abgeschlossen: Perlenring Umarbeitung",
            message="Auftrag 'Perlenring Umarbeitung' wurde als abgeschlossen markiert. Rechnung erstellen.",
            notification_type=NotificationTypeEnum.ORDER_STATUS,
            severity=NotificationSeverityEnum.INFO,
            related_order_id=orders[10].id,
            is_read=True,
            read_at=_days_ago(3),
            created_at=_days_ago(4),
        ),
        dict(
            user_id=admin.id,
            title="Neuer Auftrag: Manschettenknuepfe Dr. Bauer",
            message="Neuer Auftrag 'Manschettenknopf-Paar Gold 585' eingegangen. Kostenvoranschlag erstellen?",
            notification_type=NotificationTypeEnum.ORDER_STATUS,
            severity=NotificationSeverityEnum.INFO,
            related_order_id=orders[11].id,
            is_read=False,
            created_at=_days_ago(2),
        ),
        # Comment notification
        dict(
            user_id=goldsmith.id,
            title="Neuer Kommentar: Brosche Art-Deco",
            message="Lisa hat einen Kommentar zum Auftrag 'Brosche Art-Deco Stil' hinzugefuegt.",
            notification_type=NotificationTypeEnum.COMMENT,
            severity=NotificationSeverityEnum.INFO,
            related_order_id=orders[13].id,
            is_read=False,
            created_at=_hours_ago(6),
        ),
        # Handoff notification
        dict(
            user_id=admin.id,
            title="Uebergabe: Kette Reparatur abgeschlossen",
            message="Markus hat die Reparatur 'Kette Reparatur Verschluss' als fertig markiert. Qualitaetskontrolle durchfuehren.",
            notification_type=NotificationTypeEnum.HANDOFF,
            severity=NotificationSeverityEnum.INFO,
            related_order_id=orders[2].id,
            is_read=True,
            read_at=_days_ago(5),
            created_at=_days_ago(6),
        ),
        # Repair notifications
        dict(
            user_id=viewer.id,
            title="Reparatur eingegangen: Halskette Zimmermann",
            message="Neue Reparatur REP-2026-0001 angenommen: Goldene Halskette, Verschluss klemmt.",
            notification_type=NotificationTypeEnum.REPAIR_RECEIVED,
            severity=NotificationSeverityEnum.INFO,
            related_customer_id=customers[5].id,
            is_read=True,
            read_at=_days_ago(1),
            created_at=_days_ago(1),
        ),
        dict(
            user_id=viewer.id,
            title="Reparatur fertig: Platinkette Braun",
            message="Reparatur REP-2026-0006 (Platinkette, Karabiner) ist in Qualitaetskontrolle. Bald abholbereit.",
            notification_type=NotificationTypeEnum.REPAIR_READY,
            severity=NotificationSeverityEnum.INFO,
            related_customer_id=customers[4].id,
            is_read=False,
            created_at=_hours_ago(3),
        ),
        # System notification
        dict(
            user_id=admin.id,
            title="Systemhinweis: Backup erfolgreich",
            message="Das taegliche Datenbank-Backup wurde erfolgreich um 02:00 Uhr durchgefuehrt.",
            notification_type=NotificationTypeEnum.SYSTEM,
            severity=NotificationSeverityEnum.INFO,
            is_read=True,
            read_at=_days_ago(0),
            created_at=_hours_ago(8),
        ),
    ]
    notifications = []
    for data in notifs_data:
        n = Notification(**data)
        db.add(n)
        notifications.append(n)
    await db.flush()
    print(f"  Benachrichtigungen: {len(notifications)} erstellt")
    return notifications


async def seed_comments(db, orders, users) -> list:
    """Create 10 realistic order comments."""
    goldsmith = users[0]  # Markus
    admin = users[1]  # Petra
    viewer = users[2]  # Lisa

    comments_data = [
        # Verlobungsring
        dict(order_id=orders[0].id, user_id=viewer.id,
             text="Kunde Thomas Weber hat angerufen. Mochte wissen, ob der Ring rechtzeitig fertig wird. Habe ihm versichert, dass wir im Zeitplan sind.",
             created_at=_days_ago(7)),
        dict(order_id=orders[0].id, user_id=goldsmith.id,
             text="Guss gut gelungen. Krappen werden morgen angeloetet. Brillant liegt bereit. Schaffe es bis Deadline.",
             created_at=_days_ago(6)),
        # Eheringe
        dict(order_id=orders[1].id, user_id=goldsmith.id,
             text="Beide Ringschienen geschmiedet. Herrenring auf 66mm, Damenring auf 54mm. Kanalfassung fuer Brillanten wird naechste Woche vorbereitet.",
             created_at=_days_ago(10)),
        dict(order_id=orders[1].id, user_id=admin.id,
             text="Anprobetermin mit Weber-Paar auf den 12. gelegt. Ringe muessen bis dahin mindestens anprobefertig sein!",
             created_at=_days_ago(5)),
        # Altgold-Umarbeitung
        dict(order_id=orders[3].id, user_id=goldsmith.id,
             text="Altgold-Brosche zerlegt. Rubin unbeschaedigt. Feingoldgehalt per Saeurentest bestaetigt: 585er. 8.5g brutto = 4.97g Feingold.",
             created_at=_days_ago(8)),
        dict(order_id=orders[3].id, user_id=viewer.id,
             text="Frau Richter hat nach dem Fortschritt gefragt. Bitte kurzes Update, wenn der Ring gegossen ist.",
             created_at=_days_ago(4)),
        # Rush order
        dict(order_id=orders[8].id, user_id=viewer.id,
             text="EILAUFTRAG! Herr Mueller braucht die Kette bis Freitag (Hochzeitstag). Zuschlag fuer Eilbearbeitung vereinbart (95 EUR/h statt 75 EUR/h).",
             created_at=_days_ago(1)),
        dict(order_id=orders[8].id, user_id=goldsmith.id,
             text="Schaffe ich, wenn Material heute reinkommt. Brauche 18g Gold 750 aus Bestand.",
             created_at=_hours_ago(5)),
        # Brosche Art-Deco
        dict(order_id=orders[13].id, user_id=viewer.id,
             text="Fr. Hoffmann (Juwelier Hoffmann) hat die Entwurfsskizze freigegeben. 10% Geschaeftskundenrabatt beruecksichtigen!",
             created_at=_days_ago(6)),
        dict(order_id=orders[13].id, user_id=goldsmith.id,
             text="Geometrische Grundform ausgesaegt. Sehr anspruchsvolle Arbeit. Onyx-Einlagen werden naechste Woche zugeschliffen.",
             created_at=_days_ago(3)),
    ]
    comments = []
    for data in comments_data:
        c = OrderComment(**data)
        db.add(c)
        comments.append(c)
    await db.flush()
    print(f"  Kommentare: {len(comments)} erstellt")
    return comments


async def seed_handoffs(db, orders, users) -> list:
    """Create 4 order handoffs."""
    goldsmith = users[0]  # Markus
    admin = users[1]  # Petra

    handoffs_data = [
        # ACCEPTED: Kette Reparatur -> office
        dict(
            order_id=orders[2].id,
            from_user_id=goldsmith.id,
            to_user_id=admin.id,
            handoff_type=HandoffTypeEnum.MARK_COMPLETE,
            status=HandoffStatusEnum.ACCEPTED,
            notes="Reparatur abgeschlossen. Neuer Verschluss sitzt fest. Bitte Rechnung erstellen.",
            responded_at=_days_ago(5),
            created_at=_days_ago(6),
        ),
        # PENDING: Verlobungsring -> Qualitaetskontrolle
        dict(
            order_id=orders[0].id,
            from_user_id=goldsmith.id,
            to_user_id=admin.id,
            handoff_type=HandoffTypeEnum.REQUEST_REVIEW,
            status=HandoffStatusEnum.PENDING,
            notes="Krappen angeloetet, Brillant noch nicht gefasst. Bitte Loetstellen pruefen.",
            created_at=_days_ago(2),
        ),
        # ACCEPTED: Ohrstecker -> office for delivery
        dict(
            order_id=orders[6].id,
            from_user_id=goldsmith.id,
            to_user_id=admin.id,
            handoff_type=HandoffTypeEnum.PASS_TO_NEXT,
            status=HandoffStatusEnum.ACCEPTED,
            notes="Ohrstecker fertig, rhodiniert und poliert. Bereit zur Auslieferung.",
            responded_at=_days_ago(20),
            created_at=_days_ago(21),
        ),
        # DECLINED: Perlenring rework
        dict(
            order_id=orders[10].id,
            from_user_id=goldsmith.id,
            to_user_id=admin.id,
            handoff_type=HandoffTypeEnum.MARK_COMPLETE,
            status=HandoffStatusEnum.DECLINED,
            notes="Perlenring fertig.",
            response_notes="Zargenrand ist an einer Stelle sichtbar unregelmaessig. Bitte nachpolieren, bevor wir es dem Kunden zeigen.",
            responded_at=_days_ago(5),
            created_at=_days_ago(5),
        ),
    ]
    handoffs = []
    for data in handoffs_data:
        h = OrderHandoff(**data)
        db.add(h)
        handoffs.append(h)
    await db.flush()
    print(f"  Uebergaben: {len(handoffs)} erstellt")
    return handoffs


async def seed_hallmarks(db, orders, users) -> list:
    """Create 3 hallmark records."""
    goldsmith = users[0]

    hallmarks_data = [
        # PENDING: Verlobungsring — not yet submitted
        dict(
            order_id=orders[0].id,
            hallmark_type=HallmarkType.FINENESS_MARK,
            status=HallmarkStatus.PENDING,
            assay_office="Pforzheim",
            notes="750er Punze nach Fertigstellung aufbringen.",
            created_by=goldsmith.id,
            created_at=_days_ago(5),
        ),
        # SUBMITTED: Platinring — sent to assay office
        dict(
            order_id=orders[4].id,
            hallmark_type=HallmarkType.FINENESS_MARK,
            status=HallmarkStatus.SUBMITTED,
            assay_office="Pforzheim",
            submitted_at=_days_ago(2),
            notes="Platin 950 Punze. Eingereicht bei Beschauamt Pforzheim.",
            created_by=goldsmith.id,
            created_at=_days_ago(4),
        ),
        # STAMPED: Ohrstecker — fully completed
        dict(
            order_id=orders[6].id,
            hallmark_type=HallmarkType.FINENESS_MARK,
            status=HallmarkStatus.STAMPED,
            assay_office="Pforzheim",
            certificate_number="PF-2026-08912",
            submitted_at=_days_ago(25),
            approved_at=_days_ago(23),
            stamped_at=_days_ago(22),
            notes="750er Weissgold Punze aufgebracht. Meisterpunze 'MG' daneben.",
            created_by=goldsmith.id,
            created_at=_days_ago(26),
        ),
    ]
    hallmarks = []
    for data in hallmarks_data:
        h = OrderHallmark(**data)
        db.add(h)
        hallmarks.append(h)
    await db.flush()
    print(f"  Punzierungen: {len(hallmarks)} erstellt")
    return hallmarks


async def seed_valuation_certificates(db, orders, customers, users) -> list:
    """Create 2 valuation certificates for completed high-value pieces."""
    goldsmith = users[0]  # Markus
    admin = users[1]  # Petra

    certs_data = [
        # Diamant-Ohrstecker
        dict(
            certificate_number="WG-2026-0001",
            order_id=orders[6].id,
            customer_id=customers[0].id,  # Maria Schneider
            created_by=goldsmith.id,
            item_description="Paar Ohrstecker, Weissgold 750/000, je 1x Brillant 0.10ct, VS2/H, Krappenfassung 4-fach, rhodiniert. Gewicht gesamt 2.8g (ohne Steine).",
            metal_type="Weissgold 750 (18K)",
            metal_weight_g=2.8,
            metal_purity="750",
            gemstones_description="2x Brillant (Diamant), je 0.10ct, Reinheit VS2, Farbe H, Schliff Very Good, rund. Ohne Zertifikat.",
            appraised_value=1100.00,
            valuation_date=_days_ago(19),
            valid_until=_days_ago(19) + timedelta(days=730),  # 2 years
            goldsmith_name="Markus Goldmann",
            goldsmith_qualification="Goldschmiedemeister, HWK Stuttgart",
            pdf_path="/documents/valuations/WG-2026-0001.pdf",
            created_at=_days_ago(19),
        ),
        # Charm-Armband (lower value)
        dict(
            certificate_number="WG-2026-0002",
            order_id=orders[14].id,
            customer_id=customers[6].id,  # Lena Fischer
            created_by=goldsmith.id,
            item_description="Bettelarmband (Charm-Armband), Silber 925/000, mit 5 handgefertigten Anhaengern (Stern, Herz, Anker, Schluessel, Kleeblatt). Gewicht gesamt 26.5g.",
            metal_type="Sterlingsilber 925",
            metal_weight_g=26.5,
            metal_purity="925",
            gemstones_description=None,
            appraised_value=420.00,
            valuation_date=_days_ago(9),
            valid_until=_days_ago(9) + timedelta(days=730),
            goldsmith_name="Markus Goldmann",
            goldsmith_qualification="Goldschmiedemeister, HWK Stuttgart",
            pdf_path="/documents/valuations/WG-2026-0002.pdf",
            created_at=_days_ago(9),
        ),
    ]
    certs = []
    for data in certs_data:
        vc = ValuationCertificate(**data)
        db.add(vc)
        certs.append(vc)
    await db.flush()
    print(f"  Wertgutachten: {len(certs)} erstellt")
    return certs


async def seed_location_history(db, orders, users) -> list:
    """Create location history for orders moving through the workshop."""
    goldsmith = users[0]
    viewer = users[2]

    # Typical locations: Eingang, Werkbank 1, Werkbank 2, Polierbereich, Tresor, Ausgang
    history_data = [
        # Order 0: Verlobungsring — Eingang -> Werkbank 1
        (orders[0].id, "Eingang", _days_ago(15), viewer.id),
        (orders[0].id, "Werkbank 1", _days_ago(14), goldsmith.id),
        # Order 1: Eheringe — Eingang -> Werkbank 1
        (orders[1].id, "Eingang", _days_ago(20), viewer.id),
        (orders[1].id, "Werkbank 1", _days_ago(18), goldsmith.id),
        # Order 2: Kette Reparatur — Eingang -> Werkbank 2 -> Tresor
        (orders[2].id, "Eingang", _days_ago(12), viewer.id),
        (orders[2].id, "Werkbank 2", _days_ago(8), goldsmith.id),
        (orders[2].id, "Tresor", _days_ago(6), goldsmith.id),
        # Order 3: Altgold — Eingang -> Werkbank 2
        (orders[3].id, "Eingang", _days_ago(10), viewer.id),
        (orders[3].id, "Werkbank 2", _days_ago(9), goldsmith.id),
        # Order 5: Silberanhaenger — Eingang -> Werkbank 2 -> Polierbereich -> Ausgang
        (orders[5].id, "Eingang", _days_ago(30), viewer.id),
        (orders[5].id, "Werkbank 2", _days_ago(25), goldsmith.id),
        (orders[5].id, "Polierbereich", _days_ago(20), goldsmith.id),
        (orders[5].id, "Ausgang", _days_ago(15), viewer.id),
        # Order 6: Ohrstecker — full path through workshop
        (orders[6].id, "Eingang", _days_ago(35), viewer.id),
        (orders[6].id, "Werkbank 1", _days_ago(30), goldsmith.id),
        (orders[6].id, "Polierbereich", _days_ago(23), goldsmith.id),
        (orders[6].id, "Tresor", _days_ago(22), goldsmith.id),
        (orders[6].id, "Ausgang", _days_ago(20), viewer.id),
        # Order 8: Rush order — just arrived
        (orders[8].id, "Eingang", _days_ago(1), viewer.id),
    ]
    entries = []
    for order_id, location, timestamp, user_id in history_data:
        lh = LocationHistory(
            order_id=order_id,
            location=location,
            timestamp=timestamp,
            changed_by=user_id,
        )
        db.add(lh)
        entries.append(lh)
    await db.flush()
    print(f"  Standortverlauf: {len(entries)} Eintraege erstellt")
    return entries


# ═══════════════════════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════════════════════


async def seed():
    """Main seeding function — creates all demo data in dependency order."""
    async with AsyncSessionLocal() as db:
        # ── Idempotency check ──────────────────────────────────────────
        result = await db.execute(
            select(User).where(User.email == SENTINEL_EMAIL)
        )
        if result.scalar_one_or_none():
            print("Demo-Daten sind bereits vorhanden. Seeding uebersprungen.")
            print(f"  (Sentinel-Email: {SENTINEL_EMAIL})")
            return

        print("=" * 60)
        print("  Goldsmith ERP — Demo-Daten werden erstellt")
        print("=" * 60)
        print()

        # ── Phase 1: Users & Activities (no FK dependencies) ──────────
        users = await seed_users(db)
        activities = await seed_activities(db, users[0])

        # ── Phase 2: Customers (referenced by orders) ─────────────────
        customers = await seed_customers(db)
        measurements = await seed_measurements(db, customers, users[0])

        # ── Phase 3: Materials & Metal Purchases ──────────────────────
        materials = await seed_materials(db)
        metal_purchases = await seed_metal_purchases(db)

        # ── Phase 4: Orders (depend on customers, metal_purchases) ────
        orders = await seed_orders(db, customers, users, metal_purchases)
        gemstones = await seed_gemstones(db, orders)
        material_usage = await seed_material_usage(db, orders, metal_purchases)

        # ── Phase 5: Time tracking ────────────────────────────────────
        time_entries = await seed_time_entries(db, orders, users, activities)
        interruptions = await seed_interruptions(db, time_entries)

        # ── Phase 6: Repair jobs ──────────────────────────────────────
        repairs = await seed_repair_jobs(db, customers, users)

        # ── Phase 7: Quotes & Invoices ────────────────────────────────
        quotes = await seed_quotes(db, orders, customers, users)
        invoices = await seed_invoices(db, orders, customers, users)

        # ── Phase 8: Scrap gold ───────────────────────────────────────
        scrap_gold = await seed_scrap_gold(db, orders, customers, users)

        # ── Phase 9: Calendar, Notifications, Comments ────────────────
        calendar_events = await seed_calendar_events(db, orders, users)
        notifications = await seed_notifications(db, orders, customers, users)
        comments = await seed_comments(db, orders, users)

        # ── Phase 10: Handoffs, Hallmarks, Valuations, Locations ──────
        handoffs = await seed_handoffs(db, orders, users)
        hallmarks = await seed_hallmarks(db, orders, users)
        valuations = await seed_valuation_certificates(db, orders, customers, users)
        location_history = await seed_location_history(db, orders, users)

        # ── Commit everything ─────────────────────────────────────────
        await db.commit()

        print()
        print("=" * 60)
        print("  Demo-Daten erfolgreich erstellt!")
        print("=" * 60)
        print()
        print("  Anmeldedaten:")
        print(f"    Goldschmied: {SENTINEL_EMAIL} / demo2026!")
        print("    Inhaber:     demo-inhaber@werkstatt.de / demo2026!")
        print("    Buero:       demo-buero@werkstatt.de / demo2026!")
        print()


if __name__ == "__main__":
    asyncio.run(seed())
