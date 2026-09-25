# ORM models package (ARCH-09)

`src/goldsmith_erp/db/models.py` (3,700 lines, every model and enum) became the
package `src/goldsmith_erp/db/models/` on 2026-09-25. It was a pure move: table,
column, index, constraint and relationship definitions are unchanged, and no
migration was needed.

## Layout

| Module | Contents |
|---|---|
| `base.py` | `Base`, `SAEnum`, the `*_NUMERIC` column types, enums shared across domains (`OrderStatusEnum`, `UserRole`, `MetalType`, `CostingMethod`, `ScrapGoldStatus`, `InvoiceStatus`, `InvoiceLineType`, `MeasurementType`, `HandSide`, `FingerPosition`, `AlloyType`) |
| `users.py` | `User` |
| `customers.py` | `Customer`, `CustomerMeasurement`, `CustomerAuditLog`, `GDPRRequest`, `CustomerConsent` |
| `orders.py` | `Order`, `OrderEvent`, `OrderComment`, `OrderItem`, `OrderStatusHistory`, `OrderPhoto`, `Gemstone`, `OrderHallmark`, `ValuationCertificate`, `OrderHandoff` and their enums |
| `materials.py` | `order_materials`, `Material`, `MaterialUsage`, `InventoryAdjustment` |
| `metals.py` | `MetalPurchase`, `MetalPriceHistory`, `MetalPriceSource`, `CustomMetalType` |
| `time_tracking.py` | `Activity`, `TimeEntry`, `Interruption`, `LocationHistory`, `EstimateAccuracy` |
| `scrap_gold.py` | `ScrapGold`, `ScrapGoldItem` |
| `invoices.py` | `Invoice`, `InvoiceLineItem`, `WorkshopSettings`, `NumberSequence` |
| `quotes.py` | `Quote`, `QuoteLineItem`, `QuoteStatus`, `QuoteLineType` |
| `repairs.py` | `RepairJob`, `RepairPhoto` and their enums |
| `consultations.py` | `Consultation`, `ConsultationPhoto`, `CustomerNoGo` and their enums |
| `comms.py` | `Notification`, `NotificationPreference`, `CustomerUpdate`, `CostChangeRequest`, `OutboxMessage` and their enums |
| `system.py` | `CalendarEvent`, `BarcodeAlias`, `ScanLog`, `LabelTemplate` |
| `_coercion.py` | Assignment-time Decimal and aware-UTC coercion |

## Rules

- Import models from the package: `from goldsmith_erp.db.models import Order`.
  `__init__.py` re-exports every public name (`__all__`), so existing imports
  keep working. Importing a domain module directly also works.
- `__init__.py` imports every module. That registers every table on
  `Base.metadata`, which Alembic autogenerate (`alembic/env.py`) needs. It then
  installs the Decimal/UTC coercion listeners, which walk `Base.registry` and
  so must run after the last model is defined. A new domain module has to be
  added to `__init__.py`, or its tables are invisible to autogenerate and its
  columns miss the coercion.
- Relationships between domains use string class names
  (`relationship("Order")`), so modules import each other only for enums and
  the `order_materials` table. The dependency graph has no cycles: every
  module depends on `base`, `orders` on `materials`, `consultations` on `orders`.
- Module-level `Index(...)` declarations live in the module of the model they
  index.
- Columns still use `Column(...)`, not `Mapped[]`/`mapped_column`. Converting
  them is a per-module follow-up.

## Layering contracts

`.importlinter` defines two contracts, checked by `lint-imports` (part of
`make lint-local`):

1. `goldsmith_erp.db.models` does not import `goldsmith_erp.services` or
   `goldsmith_erp.api`.
2. `goldsmith_erp.services` does not import `goldsmith_erp.api.routers`. It
   forbids only the routers because `core.permissions` imports `api.deps`
   lazily (inside `require_permission`), so services reach `api.deps` through
   it. Once that edge is removed, the contract can forbid all of `api`.

Both contracts also count indirect imports. grimp (the engine behind
import-linter) skips implicit namespace packages, so `core/`, `db/` and
`services/` got empty `__init__.py` files; without them the graph did not
include those packages.
