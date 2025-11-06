"""Database repositories."""
from goldsmith_erp.db.repositories.base import BaseRepository
from goldsmith_erp.db.repositories.customer import CustomerRepository
from goldsmith_erp.db.repositories.material import MaterialRepository
from goldsmith_erp.db.repositories.order import OrderRepository

__all__ = [
    "BaseRepository",
    "CustomerRepository",
    "MaterialRepository",
    "OrderRepository",
]
