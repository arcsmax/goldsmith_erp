"""ORM models, split by domain (ARCH-09).

Every public name is re-exported here, so ``from goldsmith_erp.db.models
import X`` keeps working and importing this package registers every table
on ``Base.metadata`` (Alembic autogenerate relies on that). Domain modules
must not import services or routers (see ``.importlinter``).
"""

# isort: skip_file
# Import order matters: ``time_tracking`` imports ``goldsmith_erp.models``
# (pydantic), which imports enums back from this package, so every other
# domain module must already be bound here when it runs.

from goldsmith_erp.db.models.base import (
    AlloyType,
    Base,
    CostingMethod,
    FingerPosition,
    HandSide,
    InvoiceLineType,
    InvoiceStatus,
    MONEY_NUMERIC,
    MeasurementType,
    MetalType,
    OrderStatusEnum,
    PERCENT_NUMERIC,
    PRICE_PER_GRAM_NUMERIC,
    SAEnum,
    ScrapGoldStatus,
    UserRole,
    WEIGHT_NUMERIC,
)
from goldsmith_erp.db.models.users import (
    User,
)
from goldsmith_erp.db.models.customers import (
    Customer,
    CustomerAuditLog,
    CustomerConsent,
    CustomerMeasurement,
    GDPRRequest,
)
from goldsmith_erp.db.models.orders import (
    FinishTypeEnum,
    Gemstone,
    HallmarkStatus,
    HallmarkType,
    HandoffStatusEnum,
    HandoffTypeEnum,
    Order,
    OrderComment,
    OrderEvent,
    OrderHallmark,
    OrderHandoff,
    OrderItem,
    OrderPhoto,
    OrderStatusHistory,
    OrderTypeEnum,
    ValuationCertificate,
)
from goldsmith_erp.db.models.materials import (
    InventoryAdjustment,
    Material,
    MaterialUsage,
    order_materials,
)
from goldsmith_erp.db.models.metals import (
    CustomMetalType,
    MetalPriceHistory,
    MetalPriceSource,
    MetalPurchase,
)
from goldsmith_erp.db.models.scrap_gold import (
    ScrapGold,
    ScrapGoldItem,
)
from goldsmith_erp.db.models.system import (
    BarcodeAlias,
    CalendarEvent,
    CalendarEventType,
    LabelTemplate,
    ScanLog,
)
from goldsmith_erp.db.models.invoices import (
    Invoice,
    InvoiceLineItem,
    NumberSequence,
    WorkshopSettings,
)
from goldsmith_erp.db.models.quotes import (
    Quote,
    QuoteLineItem,
    QuoteLineType,
    QuoteStatus,
)
from goldsmith_erp.db.models.comms import (
    CostChangeRequest,
    CostChangeResponseMethod,
    CostChangeStatus,
    CustomerUpdate,
    CustomerUpdateKind,
    CustomerUpdateStatus,
    Notification,
    NotificationPreference,
    NotificationSeverityEnum,
    NotificationTypeEnum,
    OUTBOX_STATUS_VALUES,
    OutboxMessage,
    OutboxStatus,
    UpdateDeliveryMethod,
)
from goldsmith_erp.db.models.repairs import (
    RepairItemType,
    RepairJob,
    RepairJobStatus,
    RepairPhoto,
    RepairPhotoPhase,
)
from goldsmith_erp.db.models.consultations import (
    Consultation,
    ConsultationOccasion,
    ConsultationPhoto,
    ConsultationPhotoKind,
    ConsultationStatus,
    CustomerNoGo,
    NoGoCategory,
)
from goldsmith_erp.db.models.media import (
    MEDIA_KIND_VALUES,
    MEDIA_OWNER_TYPE_VALUES,
    MediaAsset,
    MediaKind,
    MediaOwnerType,
)
from goldsmith_erp.db.models.time_tracking import (
    Activity,
    EstimateAccuracy,
    Interruption,
    LocationHistory,
    TimeEntry,
    _validate_time_entry_metadata,
)
from goldsmith_erp.db.models._coercion import (
    _install_numeric_coercion,
    _install_utc_coercion,
)

# Must run after every model module is imported: both walk Base.registry.
_install_numeric_coercion()
_install_utc_coercion()

__all__ = [
    "Activity",
    "AlloyType",
    "BarcodeAlias",
    "Base",
    "CalendarEvent",
    "CalendarEventType",
    "Consultation",
    "ConsultationOccasion",
    "ConsultationPhoto",
    "ConsultationPhotoKind",
    "ConsultationStatus",
    "CostChangeRequest",
    "CostChangeResponseMethod",
    "CostChangeStatus",
    "CostingMethod",
    "CustomMetalType",
    "Customer",
    "CustomerAuditLog",
    "CustomerConsent",
    "CustomerMeasurement",
    "CustomerNoGo",
    "CustomerUpdate",
    "CustomerUpdateKind",
    "CustomerUpdateStatus",
    "EstimateAccuracy",
    "FingerPosition",
    "FinishTypeEnum",
    "GDPRRequest",
    "Gemstone",
    "HallmarkStatus",
    "HallmarkType",
    "HandSide",
    "HandoffStatusEnum",
    "HandoffTypeEnum",
    "Interruption",
    "InventoryAdjustment",
    "Invoice",
    "InvoiceLineItem",
    "InvoiceLineType",
    "InvoiceStatus",
    "LabelTemplate",
    "LocationHistory",
    "MEDIA_KIND_VALUES",
    "MEDIA_OWNER_TYPE_VALUES",
    "MONEY_NUMERIC",
    "Material",
    "MaterialUsage",
    "MeasurementType",
    "MediaAsset",
    "MediaKind",
    "MediaOwnerType",
    "MetalPriceHistory",
    "MetalPriceSource",
    "MetalPurchase",
    "MetalType",
    "NoGoCategory",
    "Notification",
    "NotificationPreference",
    "NotificationSeverityEnum",
    "NotificationTypeEnum",
    "NumberSequence",
    "OUTBOX_STATUS_VALUES",
    "Order",
    "OrderComment",
    "OrderEvent",
    "OrderHallmark",
    "OrderHandoff",
    "OrderItem",
    "OrderPhoto",
    "OrderStatusEnum",
    "OrderStatusHistory",
    "OrderTypeEnum",
    "OutboxMessage",
    "OutboxStatus",
    "PERCENT_NUMERIC",
    "PRICE_PER_GRAM_NUMERIC",
    "Quote",
    "QuoteLineItem",
    "QuoteLineType",
    "QuoteStatus",
    "RepairItemType",
    "RepairJob",
    "RepairJobStatus",
    "RepairPhoto",
    "RepairPhotoPhase",
    "SAEnum",
    "ScanLog",
    "ScrapGold",
    "ScrapGoldItem",
    "ScrapGoldStatus",
    "TimeEntry",
    "UpdateDeliveryMethod",
    "User",
    "UserRole",
    "ValuationCertificate",
    "WEIGHT_NUMERIC",
    "WorkshopSettings",
    "_validate_time_entry_metadata",
    "order_materials",
]
