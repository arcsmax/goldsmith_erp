"""API routers for Goldsmith ERP."""

from goldsmith_erp.api.routers import auth, orders, materials, customers

__all__ = ["auth", "orders", "materials", "customers"]
