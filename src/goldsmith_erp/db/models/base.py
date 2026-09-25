"""Declarative base, column-type helpers and enums shared across domains."""

import enum

from sqlalchemy import Enum as _SAEnum
from sqlalchemy import Numeric
from sqlalchemy.ext.declarative import declarative_base

# Exact decimal column types (BE-14, ADR-2026-09-25-numeric-and-tz). Money is
# stored to the cent, weights and quantities to the milligram / thousandth,
# per-gram metal prices to 4 dp (a 2 dp rate times 1 kg is off by up to 5 EUR),
# and percentages (VAT, margin, scrap loss) to 2 dp. The ORM returns Decimal.
MONEY_NUMERIC = Numeric(12, 2)
WEIGHT_NUMERIC = Numeric(12, 3)
PRICE_PER_GRAM_NUMERIC = Numeric(12, 4)
PERCENT_NUMERIC = Numeric(5, 2)


def SAEnum(enum_class, **kwargs):
    """Wrapper that ensures Python enum .value (lowercase) is stored in PostgreSQL."""
    return _SAEnum(enum_class, values_callable=lambda e: [x.value for x in e], **kwargs)


Base = declarative_base()


class OrderStatusEnum(str, enum.Enum):
    """Enumerated order statuses for consistency and validation.

    Follows the goldsmith production pipeline:
    Auftrag -> Entwurf -> Guss -> Montage -> Fassung -> Oberflaeche -> QK -> Auslieferung
    """

    DRAFT = "draft"
    CONFIRMED = "confirmed"
    IN_PROGRESS = "in_progress"
    WAITING_FOR_FITTING = "waiting_for_fitting"
    FITTING_DONE = "fitting_done"
    READY_FOR_SETTING = "ready_for_setting"
    QUALITY_CHECK = "quality_check"
    COMPLETED = "completed"
    DELIVERED = "delivered"
    # W2-07 / DOM-13: paused (waiting for stone, customer, casting service)
    # with Order.hold_reason + Order.resume_date; out of deadline alarms.
    ON_HOLD = "on_hold"
    # W2-07 / DOM-13: Storniert, with Order.cancel_reason; out of all
    # active counts. Terminal except for a reopen to DRAFT.
    CANCELLED = "cancelled"
    # Legacy (DOM-46): display only, never set by new code. The W2-07 data
    # migration maps existing rows to draft/confirmed. Transitions live in
    # services/order_workflow.py.
    NEW = "new"


class UserRole(str, enum.Enum):
    """User roles for RBAC (Role-Based Access Control)."""

    ADMIN = "admin"  # Full system access
    GOLDSMITH = "goldsmith"  # Production workers (orders, time tracking, materials)
    VIEWER = "viewer"  # View-only access    # Standard user access


class MetalType(str, enum.Enum):
    """Standard metal types used in goldsmith workshop"""

    GOLD_24K = "gold_24k"  # 999.9 Feingold
    GOLD_22K = "gold_22k"  # 916 Gold
    GOLD_18K = "gold_18k"  # 750 Gold
    GOLD_14K = "gold_14k"  # 585 Gold
    GOLD_9K = "gold_9k"  # 375 Gold
    SILVER_999 = "silver_999"  # Feinsilber
    SILVER_925 = "silver_925"  # Sterling Silber
    SILVER_800 = "silver_800"  # Altsilber
    PLATINUM_950 = "platinum_950"
    PLATINUM_900 = "platinum_900"
    PALLADIUM = "palladium"
    WHITE_GOLD_18K = "white_gold_18k"
    WHITE_GOLD_14K = "white_gold_14k"
    ROSE_GOLD_18K = "rose_gold_18k"
    ROSE_GOLD_14K = "rose_gold_14k"


class CostingMethod(str, enum.Enum):
    """Inventory costing method for material consumption"""

    FIFO = "fifo"  # First In, First Out
    LIFO = "lifo"  # Last In, First Out
    AVERAGE = "average"  # Weighted Average Cost
    SPECIFIC = "specific"  # Specific Identification (manual selection)


class ScrapGoldStatus(str, enum.Enum):
    """Status of scrap gold processing."""

    RECEIVED = "received"  # Items documented
    CALCULATED = "calculated"  # Fine content calculated
    SIGNED = "signed"  # Customer signed receipt
    CREDITED = "credited"  # Applied to invoice


class InvoiceStatus(str, enum.Enum):
    """Invoice lifecycle status (Rechnungsstatus)."""

    DRAFT = "draft"  # Entwurf - not yet sent
    SENT = "sent"  # Versendet - sent to customer
    PAID = "paid"  # Bezahlt - payment received
    OVERDUE = "overdue"  # Ueberfaellig - past due date
    CANCELLED = "cancelled"  # Storniert - voided


class InvoiceLineType(str, enum.Enum):
    """Type of invoice line item (Rechnungspositionstyp)."""

    MATERIAL = "material"  # Metal material (e.g. Gold 18K)
    LABOR = "labor"  # Labor/Arbeitszeit
    GEMSTONE = "gemstone"  # Edelstein
    OTHER = "other"  # Sonstiges


class MeasurementType(str, enum.Enum):
    """Types of body measurements stored in the customer Massbibliothek."""

    RING_SIZE = "ring_size"  # Ring inner circumference (EU mm or EU size)
    CHAIN_LENGTH = "chain_length"  # Necklace/chain length in cm
    WRIST_CIRCUMFERENCE = "wrist_circumference"  # Wrist for bracelets
    FINGER_CIRCUMFERENCE = "finger_circumference"  # Exact finger circumference in mm
    NECK_CIRCUMFERENCE = "neck_circumference"  # Neck circumference in cm
    ANKLE_CIRCUMFERENCE = "ankle_circumference"  # Ankle for anklets


class HandSide(str, enum.Enum):
    """Hand side for ring and bracelet measurements."""

    LEFT = "left"
    RIGHT = "right"


class FingerPosition(str, enum.Enum):
    """Finger position for ring measurements (Fingerposition)."""

    THUMB = "thumb"  # Daumen
    INDEX = "index"  # Zeigefinger
    MIDDLE = "middle"  # Mittelfinger
    RING = "ring"  # Ringfinger
    PINKY = "pinky"  # Kleiner Finger


class AlloyType(str, enum.Enum):
    """Standard gold/silver alloy types with fine content ratio."""

    GOLD_999 = "999"  # 99.9% Feingold
    GOLD_900 = "900"  # 90.0%
    GOLD_750 = "750"  # 75.0% (18K)
    GOLD_585 = "585"  # 58.5% (14K)
    GOLD_375 = "375"  # 37.5% (9K)
    GOLD_333 = "333"  # 33.3% (8K)
    SILVER_999 = "ag999"  # 99.9% Feinsilber
    SILVER_925 = "ag925"  # 92.5% Sterling
    SILVER_800 = "ag800"  # 80.0%
    PLATINUM_950 = "pt950"  # 95.0%
