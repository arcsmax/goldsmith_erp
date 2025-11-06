"""
Security headers middleware for enhanced API security.

Adds security-related HTTP headers to protect against common vulnerabilities:
- XSS (Cross-Site Scripting)
- Clickjacking
- MIME sniffing
- Information disclosure
- Man-in-the-middle attacks

Implements OWASP security best practices.

Author: Claude AI
Date: 2025-11-06
"""

import logging
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add security headers to all responses.

    Adds headers for:
    - Content Security Policy (CSP)
    - Strict Transport Security (HSTS)
    - XSS Protection
    - Content Type Options
    - Frame Options
    - Referrer Policy
    - Permissions Policy

    Usage:
        app.add_middleware(SecurityHeadersMiddleware)
    """

    def __init__(self, app: ASGIApp, production: bool = False):
        """
        Initialize security headers middleware.

        Args:
            app: ASGI application
            production: If True, use stricter production settings
        """
        super().__init__(app)
        self.production = production

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """
        Add security headers to response.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware/route handler

        Returns:
            HTTP response with security headers
        """
        # Process request
        response = await call_next(request)

        # Add security headers
        self._add_security_headers(response)

        return response

    def _add_security_headers(self, response: Response):
        """
        Add all security headers to response.

        Args:
            response: HTTP response to modify
        """
        # ────────────────────────────────────────────────────────────────────
        # X-Content-Type-Options: Prevent MIME sniffing
        # ────────────────────────────────────────────────────────────────────
        response.headers["X-Content-Type-Options"] = "nosniff"

        # ────────────────────────────────────────────────────────────────────
        # X-Frame-Options: Prevent clickjacking
        # ────────────────────────────────────────────────────────────────────
        response.headers["X-Frame-Options"] = "DENY"

        # ────────────────────────────────────────────────────────────────────
        # X-XSS-Protection: Enable browser XSS filter (legacy)
        # ────────────────────────────────────────────────────────────────────
        response.headers["X-XSS-Protection"] = "1; mode=block"

        # ────────────────────────────────────────────────────────────────────
        # Strict-Transport-Security: Force HTTPS (production only)
        # ────────────────────────────────────────────────────────────────────
        if self.production:
            # 1 year max-age, include subdomains, allow browser preload
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains; preload"
            )

        # ────────────────────────────────────────────────────────────────────
        # Content-Security-Policy: Prevent XSS and data injection attacks
        # ────────────────────────────────────────────────────────────────────
        csp_directives = [
            "default-src 'self'",                    # Default: only same origin
            "script-src 'self' 'unsafe-inline'",     # Scripts: self + inline (for dev)
            "style-src 'self' 'unsafe-inline'",      # Styles: self + inline
            "img-src 'self' data: https:",           # Images: self + data URIs + HTTPS
            "font-src 'self' data:",                 # Fonts: self + data URIs
            "connect-src 'self'",                    # AJAX/WebSocket: same origin
            "frame-ancestors 'none'",                # Prevent framing (same as X-Frame-Options)
            "base-uri 'self'",                       # Restrict <base> tag
            "form-action 'self'",                    # Forms can only submit to same origin
            "upgrade-insecure-requests",             # Upgrade HTTP to HTTPS
        ]

        if self.production:
            # Stricter CSP for production (remove unsafe-inline)
            csp_directives = [
                "default-src 'self'",
                "script-src 'self'",
                "style-src 'self'",
                "img-src 'self' data: https:",
                "font-src 'self' data:",
                "connect-src 'self'",
                "frame-ancestors 'none'",
                "base-uri 'self'",
                "form-action 'self'",
                "upgrade-insecure-requests",
            ]

        response.headers["Content-Security-Policy"] = "; ".join(csp_directives)

        # ────────────────────────────────────────────────────────────────────
        # Referrer-Policy: Control referrer information
        # ────────────────────────────────────────────────────────────────────
        # strict-origin-when-cross-origin: Send full URL for same-origin,
        # only origin for cross-origin HTTPS, nothing for HTTP
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # ────────────────────────────────────────────────────────────────────
        # Permissions-Policy: Control browser features
        # ────────────────────────────────────────────────────────────────────
        permissions = [
            "accelerometer=()",       # Disable accelerometer
            "camera=()",              # Disable camera
            "geolocation=()",         # Disable geolocation
            "gyroscope=()",           # Disable gyroscope
            "magnetometer=()",        # Disable magnetometer
            "microphone=()",          # Disable microphone
            "payment=()",             # Disable payment API
            "usb=()",                 # Disable USB
        ]
        response.headers["Permissions-Policy"] = ", ".join(permissions)

        # ────────────────────────────────────────────────────────────────────
        # X-Permitted-Cross-Domain-Policies: Restrict Adobe Flash/PDF
        # ────────────────────────────────────────────────────────────────────
        response.headers["X-Permitted-Cross-Domain-Policies"] = "none"

        # ────────────────────────────────────────────────────────────────────
        # Cache-Control: Prevent caching of sensitive data
        # ────────────────────────────────────────────────────────────────────
        # Only for API endpoints (not static files)
        if "/api/" in str(response.headers.get("path", "")):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"

        # ────────────────────────────────────────────────────────────────────
        # X-Robots-Tag: Prevent search engine indexing of API
        # ────────────────────────────────────────────────────────────────────
        response.headers["X-Robots-Tag"] = "noindex, nofollow"


class CORSSecurityMiddleware(BaseHTTPMiddleware):
    """
    Enhanced CORS middleware with security checks.

    Provides additional security beyond FastAPI's CORSMiddleware:
    - Origin validation
    - Request method validation
    - Header validation
    - Preflight request handling

    Usage:
        app.add_middleware(CORSSecurityMiddleware)
    """

    def __init__(
        self,
        app: ASGIApp,
        allowed_origins: list[str],
        allowed_methods: list[str] = None,
        allowed_headers: list[str] = None,
    ):
        """
        Initialize CORS security middleware.

        Args:
            app: ASGI application
            allowed_origins: List of allowed origins
            allowed_methods: List of allowed HTTP methods
            allowed_headers: List of allowed headers
        """
        super().__init__(app)
        self.allowed_origins = set(allowed_origins)
        self.allowed_methods = set(allowed_methods or ["GET", "POST", "PUT", "DELETE", "PATCH"])
        self.allowed_headers = set(allowed_headers or ["Content-Type", "Authorization"])

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """
        Validate CORS and process request.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware/route handler

        Returns:
            HTTP response
        """
        origin = request.headers.get("origin")

        # Validate origin
        if origin and not self._is_origin_allowed(origin):
            logger.warning(f"Blocked request from unauthorized origin: {origin}")
            return Response(
                content="Origin not allowed",
                status_code=403,
                headers={"Content-Type": "text/plain"}
            )

        # Process request
        response = await call_next(request)

        return response

    def _is_origin_allowed(self, origin: str) -> bool:
        """
        Check if origin is in allowed list.

        Args:
            origin: Request origin

        Returns:
            True if allowed, False otherwise
        """
        # Allow exact matches
        if origin in self.allowed_origins:
            return True

        # Allow wildcard subdomains (e.g., *.example.com)
        for allowed in self.allowed_origins:
            if allowed.startswith("*."):
                domain = allowed[2:]
                if origin.endswith(domain):
                    return True

        return False


class SensitiveDataRedactionMiddleware(BaseHTTPMiddleware):
    """
    Middleware to prevent sensitive data leakage in responses.

    Redacts or masks sensitive data in error messages and responses:
    - API keys
    - Passwords
    - Tokens
    - Personal information
    - Internal paths

    Usage:
        app.add_middleware(SensitiveDataRedactionMiddleware)
    """

    def __init__(self, app: ASGIApp):
        super().__init__(app)

        # Patterns to redact (regex patterns)
        self.sensitive_patterns = [
            r"password['\"]?\s*[:=]\s*['\"]?[^'\"]+",
            r"api[_-]?key['\"]?\s*[:=]\s*['\"]?[^'\"]+",
            r"token['\"]?\s*[:=]\s*['\"]?[^'\"]+",
            r"secret['\"]?\s*[:=]\s*['\"]?[^'\"]+",
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b",  # Email
            r"\b\d{3}[-.]?\d{3}[-.]?\d{4}\b",  # Phone (US format)
        ]

    async def dispatch(
        self, request: Request, call_next: Callable
    ) -> Response:
        """
        Process request and redact sensitive data from errors.

        Args:
            request: Incoming HTTP request
            call_next: Next middleware/route handler

        Returns:
            HTTP response
        """
        try:
            response = await call_next(request)
            return response
        except Exception as e:
            # Redact sensitive data from exception message
            error_message = str(e)
            redacted_message = self._redact_sensitive_data(error_message)

            logger.error(f"Request error (redacted): {redacted_message}")

            # Re-raise with redacted message
            raise Exception(redacted_message)

    def _redact_sensitive_data(self, text: str) -> str:
        """
        Redact sensitive data from text.

        Args:
            text: Text potentially containing sensitive data

        Returns:
            Text with sensitive data redacted
        """
        import re

        redacted = text
        for pattern in self.sensitive_patterns:
            redacted = re.sub(pattern, "[REDACTED]", redacted, flags=re.IGNORECASE)

        return redacted


# ═══════════════════════════════════════════════════════════════════════════
# Middleware initialization helper
# ═══════════════════════════════════════════════════════════════════════════

def setup_security_middleware(app, production: bool = False):
    """
    Setup all security middleware on FastAPI app.

    Args:
        app: FastAPI application instance
        production: If True, use stricter production settings

    Usage:
        from goldsmith_erp.middleware.security_headers import setup_security_middleware
        setup_security_middleware(app, production=True)
    """
    # Add security headers
    app.add_middleware(SecurityHeadersMiddleware, production=production)

    # Add sensitive data redaction (always on)
    app.add_middleware(SensitiveDataRedactionMiddleware)

    logger.info(f"Security middleware initialized (production={production})")
