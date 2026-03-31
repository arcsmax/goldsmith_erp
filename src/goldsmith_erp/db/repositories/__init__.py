"""Database repositories.

Note: CustomerRepository and OrderRepository depend on models (CustomerAuditLog,
GDPRRequest, OrderItem, OrderStatusHistory) that will be added in a future
migration. They are imported lazily to avoid breaking the rest of the app.
"""
from goldsmith_erp.db.repositories.base import BaseRepository
from goldsmith_erp.db.repositories.material import MaterialRepository

try:
    from goldsmith_erp.db.repositories.customer import CustomerRepository
except ImportError:
    CustomerRepository = None  # type: ignore[assignment,misc]

try:
    from goldsmith_erp.db.repositories.order import OrderRepository
except ImportError:
    OrderRepository = None  # type: ignore[assignment,misc]

__all__ = [
    "BaseRepository",
    "CustomerRepository",
    "MaterialRepository",
    "OrderRepository",
]
