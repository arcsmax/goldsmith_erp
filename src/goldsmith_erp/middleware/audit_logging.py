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

import logging
import time
import json
from typing import Callable, Optional
from datetime import datetime

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from goldsmith_erp.db.session import get_session
from goldsmith_erp.db.models import CustomerAuditLog

logger = logging.getLogger(__name__)


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

        # Extract user info from request state (set by auth middleware)
        current_user = getattr(request.state, "user", None)
        user_id = current_user.id if current_user else None
        user_email = current_user.email if current_user else None
        user_role = current_user.role if current_user else None

        # Extract customer ID from URL if present
        customer_id = self._extract_customer_id(request.url.path)

        # Determine action type based on HTTP method
        action = self._method_to_action(method)

        # Process the request
        response = await call_next(request)

        # Calculate request duration
        duration_ms = (time.time() - start_time) * 1000

        # Log only successful requests (2xx, 3xx)
        if 200 <= response.status_code < 400:
            # Log to database asynchronously (don't block response)
            try:
                await self._log_to_database(
                    customer_id=customer_id,
                    action=action,
                    method=method,
                    endpoint=request.url.path,
                    user_id=user_id,
                    user_email=user_email,
                    user_role=user_role,
                    ip_address=client_ip,
                    user_agent=user_agent,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                )
            except Exception as e:
                # Don't fail the request if logging fails
                logger.error(f"Failed to log audit entry: {e}")

        # Log to application log for monitoring
        logger.info(
            f"Customer data access: {method} {request.url.path} | "
            f"User: {user_email or 'anonymous'} | "
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
        Get client IP address, handling proxies.

        Args:
            request: HTTP request

        Returns:
            Client IP address
        """
        # Check for forwarded IP (behind proxy)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Take the first IP if multiple
            return forwarded_for.split(",")[0].strip()

        # Check for real IP header
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        # Fall back to direct client
        if request.client:
            return request.client.host

        return "unknown"

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
        Log audit entry to database.

        Args:
            customer_id: Customer ID (if applicable)
            action: Action performed (accessed, created, updated, deleted)
            method: HTTP method
            endpoint: API endpoint
            user_id: ID of user who made the request
            user_email: Email of user
            user_role: Role of user
            ip_address: Client IP address
            user_agent: User agent string
            status_code: HTTP response status code
            duration_ms: Request duration in milliseconds
        """
        # Only log if we have a customer ID
        if not customer_id:
            return

        async for session in get_session():
            try:
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
                    endpoint=endpoint,
                    http_method=method,
                    legal_basis="GDPR Article 6(1)(b) - Contract",
                    purpose=f"Customer data {action} via API",
                )

                session.add(audit_log)
                await session.commit()

            except Exception as e:
                logger.error(f"Failed to write audit log to database: {e}")
                await session.rollback()
            finally:
                await session.close()


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
        """Get client IP address."""
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip

        if request.client:
            return request.client.host

        return "unknown"


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
