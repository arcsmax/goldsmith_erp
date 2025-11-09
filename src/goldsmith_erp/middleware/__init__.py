"""Middleware package for Goldsmith ERP."""
from goldsmith_erp.middleware.logging import RequestLoggingMiddleware

__all__ = ["RequestLoggingMiddleware"]
