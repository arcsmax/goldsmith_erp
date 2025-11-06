"""Security and monitoring middleware for Goldsmith ERP."""

from goldsmith_erp.middleware.audit_logging import (
    AuditLoggingMiddleware,
    RequestLoggingMiddleware,
    RequestIDMiddleware,
)
from goldsmith_erp.middleware.rate_limiting import (
    RateLimitMiddleware,
    EndpointRateLimitMiddleware,
)
from goldsmith_erp.middleware.security_headers import (
    SecurityHeadersMiddleware,
    CORSSecurityMiddleware,
    SensitiveDataRedactionMiddleware,
    setup_security_middleware,
)

__all__ = [
    # Audit logging
    "AuditLoggingMiddleware",
    "RequestLoggingMiddleware",
    "RequestIDMiddleware",
    # Rate limiting
    "RateLimitMiddleware",
    "EndpointRateLimitMiddleware",
    # Security headers
    "SecurityHeadersMiddleware",
    "CORSSecurityMiddleware",
    "SensitiveDataRedactionMiddleware",
    "setup_security_middleware",
]
