"""
Deny-by-default authentication middleware.
Requires valid JWT for all endpoints except whitelisted paths.
"""
import logging
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from jose import jwt, JWTError

from goldsmith_erp.core.config import settings
from goldsmith_erp.core.security import ALGORITHM

logger = logging.getLogger(__name__)

# Paths that do NOT require authentication
PUBLIC_PATHS = [
    "/health",
    "/docs",
    "/redoc",
    "/openapi.json",
    f"{settings.API_V1_STR}/openapi.json",
    f"{settings.API_V1_STR}/login",
    f"{settings.API_V1_STR}/logout",
    f"{settings.API_V1_STR}/register",
]

# Prefixes that do NOT require authentication
PUBLIC_PREFIXES = [
    "/docs",
    "/redoc",
    "/static",
    f"{settings.API_V1_STR}/login",
    f"{settings.API_V1_STR}/auth/mfa",
    # The refresh endpoint must bypass the middleware's strict expiry check so that
    # recently-expired tokens can reach the handler, which applies its own grace
    # window logic and all other security checks (signature, user existence, etc.).
    f"{settings.API_V1_STR}/auth/refresh",
]


class AuthRequiredMiddleware(BaseHTTPMiddleware):
    """
    Global authentication middleware.
    Denies access by default — only whitelisted paths are public.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        path = request.url.path

        # Allow public paths
        if self._is_public(path):
            return await call_next(request)

        # Allow OPTIONS (CORS preflight)
        if request.method == "OPTIONS":
            return await call_next(request)

        # Check for JWT token
        token = self._extract_token(request)
        if not token:
            return JSONResponse(
                status_code=401,
                content={"detail": "Authentication required"},
            )

        # Validate token
        try:
            jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        except JWTError as e:
            logger.warning(
                "Invalid JWT token",
                extra={"path": path, "error": str(e)},
            )
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or expired token"},
            )

        return await call_next(request)

    def _is_public(self, path: str) -> bool:
        """Check if path is whitelisted as public."""
        if path in PUBLIC_PATHS:
            return True
        for prefix in PUBLIC_PREFIXES:
            if path.startswith(prefix):
                return True
        return False

    def _extract_token(self, request: Request) -> str | None:
        """Extract JWT from Authorization header or cookie."""
        # Check Authorization header first
        auth_header = request.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            return auth_header[7:]

        # Fall back to HttpOnly cookie
        return request.cookies.get("access_token")
