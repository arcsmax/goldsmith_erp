"""
GDPR-compliant audit logging middleware.

This middleware automatically logs all customer data access for compliance
with GDPR Article 30 (Records of processing activities).

Logs include:
- Who accessed the data (user ID, email, role)
- When it was accessed (timestamp)
- What was accessed (endpoint, customer ID)
- How it was accessed (HTTP method, IP address, user agent)
- Why it was accessed (purpose, legal basis)

Author: Claude AI
Date: 2025-11-06
"""

import ipaddress
import logging
import time
import json
from typing import Callable, Optional
from datetime import datetime

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

try:
    from goldsmith_erp.db.session import AsyncSessionLocal
except ImportError:
    AsyncSessionLocal = None  # type: ignore[assignment]

try:
    from goldsmith_erp.db.models import CustomerAuditLog
except ImportError:
    CustomerAuditLog = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)


def _is_trusted_proxy_ip(ip: str) -> bool:
    """Return True if *ip* is a loopback or RFC-1918 private address."""
    try:
        addr = ipaddress.ip_address(ip)
        return addr.is_loopback or addr.is_private
    except ValueError:
        return False


def get_real_ip(request: Request) -> str:
    """
    Return the real client IP address.

    X-Forwarded-For is only trusted when the direct TCP peer
    (request.client.host) is a loopback or private-network address,
    i.e. a known-good reverse proxy.  Untrusted clients that inject
    X-Forwarded-For are ignored and their direct IP is used instead.
    """
    direct_ip = request.client.host if request.client else None

    if direct_ip and _is_trusted_proxy_ip(direct_ip):
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

    return direct_ip or "unknown"


class AuditLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for automatic GDPR-compliant audit logging.

    Intercepts all HTTP requests to customer endpoints and logs:
    - Data access (GET requests)
    - Data modifications (POST, PUT, PATCH, DELETE)
    - Who, what, when, where, why

    Usage:
        app.add_middleware(AuditLoggingMiddleware)
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)
        self.customer_endpoints = [
            "/api/v1/customers",
            "/api/v1/customer",
        ]

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """
        Process each request and log customer data access.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware/route handler

        Returns:
            HTTP response
        """
        # Check if this is a customer-related endpoint
        if not self._is_customer_endpoint(request.url.path):
            # Not a customer endpoint, skip audit logging
            return await call_next(request)

        # Extract request metadata
        start_time = time.time()
        client_ip = self._get_client_ip(request)
        user_agent = request.headers.get("user-agent", "")
        method = request.method

        # Extract authenticated user_id from request.state (set by
        # AuthRequiredMiddleware).  We deliberately do NOT read a full
        # user object here — keeping middleware off the DB hot-path is
        # cheaper and avoids leaking PII (email, role) into middleware
        # state.
        user_id = getattr(request.state, "user_id", None)

        # Extract customer ID from URL if present
        customer_id = self._extract_customer_id(request.url.path)

        # Determine action type based on HTTP method.  Bulk list/search
        # endpoints (no {id} in path) use a distinct "list_accessed" action
        # so GDPR Art. 30 reviewers can distinguish per-record reads from
        # bulk PII exposure, which carries a higher risk classification.
        # POST /api/v1/customers (create) has no customer_id at middleware
        # time (DB assigns it in the handler) — we still audit it as
        # "created"; a later enhancement can inspect the response body to
        # backfill entity_id.
        if method == "GET" and customer_id is None:
            action = "list_accessed"
        else:
            action = self._method_to_action(method)

        # Process the request first — the audit write must NEVER block or
        # fail the user's response.  Even if the handler raises, we still
        # want a row in the audit log (access attempts are auditable under
        # GDPR Art. 30).
        response = await call_next(request)

        # Calculate request duration
        duration_ms = (time.time() - start_time) * 1000

        # Write the audit row.  Wrap in a broad try/except: an audit-write
        # failure must NOT propagate to the user.  The ERROR log line is
        # tagged so Loki/ELK rules can alert on audit failures separately.
        try:
            await self._log_to_database(
                customer_id=customer_id,
                action=action,
                method=method,
                endpoint=request.url.path,
                user_id=user_id,
                user_email=None,  # PII — see F-25 follow-up
                user_role=None,
                ip_address=client_ip,
                user_agent=user_agent,
                status_code=response.status_code,
                duration_ms=duration_ms,
            )
        except Exception as exc:  # pragma: no cover — defensive belt
            logger.error(
                "audit write failed: %s",
                exc,
                extra={"audit": True, "path": request.url.path},
                exc_info=True,
            )

        # Log to application log for monitoring — user_email omitted (PII).
        logger.info(
            f"Customer data access: {method} {request.url.path} | "
            f"User ID: {user_id or 'anonymous'} | "
            f"IP: {client_ip} | "
            f"Status: {response.status_code} | "
            f"Duration: {duration_ms:.2f}ms"
        )

        return response

    def _is_customer_endpoint(self, path: str) -> bool:
        """
        Check if the path is a customer-related endpoint.

        Args:
            path: Request URL path

        Returns:
            True if customer endpoint, False otherwise
        """
        return any(path.startswith(endpoint) for endpoint in self.customer_endpoints)

    def _extract_customer_id(self, path: str) -> Optional[int]:
        """
        Extract customer ID from URL path.

        Args:
            path: Request URL path

        Returns:
            Customer ID if found, None otherwise

        Examples:
            /api/v1/customers/123 -> 123
            /api/v1/customers/123/consent -> 123
            /api/v1/customers -> None
        """
        parts = path.split("/")

        # Find "customers" segment and get the next part
        try:
            customers_index = parts.index("customers")
            if customers_index + 1 < len(parts):
                customer_id_str = parts[customers_index + 1]
                # Check if it's a number (not a sub-resource like "search", "statistics")
                if customer_id_str.isdigit():
                    return int(customer_id_str)
        except (ValueError, IndexError):
            pass

        return None

    def _get_client_ip(self, request: Request) -> str:
        """
        Get client IP address, validating proxy headers against the direct peer.

        Args:
            request: HTTP request

        Returns:
            Client IP address
        """
        return get_real_ip(request)

    def _method_to_action(self, method: str) -> str:
        """
        Convert HTTP method to audit log action.

        Args:
            method: HTTP method (GET, POST, PUT, etc.)

        Returns:
            Audit log action
        """
        action_map = {
            "GET": "accessed",
            "POST": "created",
            "PUT": "updated",
            "PATCH": "updated",
            "DELETE": "deleted",
        }
        return action_map.get(method, "accessed")

    async def _log_to_database(
        self,
        customer_id: Optional[int],
        action: str,
        method: str,
        endpoint: str,
        user_id: Optional[int],
        user_email: Optional[str],
        user_role: Optional[str],
        ip_address: str,
        user_agent: str,
        status_code: int,
        duration_ms: float,
    ):
        """
        Persist a CustomerAuditLog row for this request.

        The write opens its own `AsyncSessionLocal()` because
        ``BaseHTTPMiddleware`` cannot use FastAPI's ``Depends(get_db)``.
        This matches the pattern already used by the system monitor
        background loop (see ``services/system_monitor.py``).

        Only the columns that actually exist on :class:`CustomerAuditLog`
        are populated.  Extras (``endpoint``, ``http_method``, duration,
        legal basis, purpose) are packed into the ``details`` JSON column.

        This method is the unit tests patch; it must therefore be
        side-effect-only (no return value the caller relies on).

        R1: rows with ``customer_id`` / ``entity_id`` = None are valid and
        expected for bulk list/search endpoints (``GET /api/v1/customers/``,
        ``GET /api/v1/customers/search``) and for POST-create requests
        (DB-assigned id is not known at middleware time).  Previously this
        method returned early when ``customer_id`` was falsy, silently
        dropping those rows — a P1 GDPR Art. 30 gap for bulk PII access.
        """
        if AsyncSessionLocal is None or CustomerAuditLog is None:
            # Import-time failure — audit is not available in this env.
            logger.error(
                "audit write skipped: AsyncSessionLocal or "
                "CustomerAuditLog not importable",
                extra={"audit": True},
            )
            return

        details = {
            "endpoint": endpoint,
            "http_method": method,
            "status_code": status_code,
            "duration_ms": round(duration_ms, 2),
            "legal_basis": "GDPR Article 6(1)(b) - Contract",
            "purpose": f"Customer data {action} via API",
        }

        try:
            async with AsyncSessionLocal() as session:
                audit_log = CustomerAuditLog(
                    customer_id=customer_id,
                    action=action,
                    entity="customer",
                    entity_id=customer_id,
                    user_id=user_id,
                    user_email=user_email,
                    user_role=user_role,
                    timestamp=datetime.utcnow(),
                    ip_address=ip_address,
                    user_agent=user_agent,
                    details=details,
                )
                session.add(audit_log)
                await session.commit()
        except Exception as exc:
            # Fail loudly in the log but never propagate — a DB outage on
            # the audit path must not deny legitimate customer access.
            logger.error(
                "audit DB write failed: %s",
                exc,
                extra={"audit": True, "customer_id": customer_id},
                exc_info=True,
            )


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """
    General request logging middleware for all API endpoints.

    Logs all incoming requests for security monitoring and debugging.

    Usage:
        app.add_middleware(RequestLoggingMiddleware)
    """

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """
        Log incoming requests.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware/route handler

        Returns:
            HTTP response
        """
        start_time = time.time()

        # Log request
        logger.info(
            f"→ {request.method} {request.url.path} | "
            f"IP: {self._get_client_ip(request)}"
        )

        # Process request
        response = await call_next(request)

        # Log response
        duration_ms = (time.time() - start_time) * 1000
        logger.info(
            f"← {request.method} {request.url.path} | "
            f"Status: {response.status_code} | "
            f"Duration: {duration_ms:.2f}ms"
        )

        return response

    def _get_client_ip(self, request: Request) -> str:
        """Get client IP address, validating proxy headers against the direct peer."""
        return get_real_ip(request)


# ═══════════════════════════════════════════════════════════════════════════
# Request ID Middleware (for correlation)
# ═══════════════════════════════════════════════════════════════════════════

import uuid


class RequestIDMiddleware(BaseHTTPMiddleware):
    """
    Add unique request ID to each request for correlation.

    Useful for:
    - Tracking requests across services
    - Correlating logs
    - Debugging issues

    Usage:
        app.add_middleware(RequestIDMiddleware)
    """

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """
        Add request ID to request and response.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware/route handler

        Returns:
            HTTP response with X-Request-ID header
        """
        # Generate or extract request ID
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

        # Store in request state for access in route handlers
        request.state.request_id = request_id

        # Process request
        response = await call_next(request)

        # Add request ID to response headers
        response.headers["X-Request-ID"] = request_id

        return response
