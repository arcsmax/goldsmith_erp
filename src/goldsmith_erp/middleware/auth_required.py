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
    # /users/register is NOT public — locked to ADMIN-invitation-only
    # (fix A3, 2026-04-23). Handler guarded by
    # @require_permission(Permission.USER_CREATE); unauthenticated POSTs
    # now hit this middleware first and return 401, closing the email-
    # enumeration oracle that the 400 "Email already registered" branch
    # previously exposed.
]

# Prefixes that do NOT require authentication
PUBLIC_PREFIXES = [
    "/docs",
    "/redoc",
    "/static",
    # "/uploads" removed — photos served via authenticated router endpoints
    f"{settings.API_V1_STR}/login",
    f"{settings.API_V1_STR}/auth/mfa",
    # The refresh endpoint must bypass the middleware's strict expiry check so that
    # recently-expired tokens can reach the handler, which applies its own grace
    # window logic and all other security checks (signature, user existence, etc.).
    # Note: the auth router is mounted at /api/v1 (no /auth sub-prefix), so the
    # actual path is /api/v1/refresh, not /api/v1/auth/refresh.
    f"{settings.API_V1_STR}/refresh",
    # Customer self-service portal — public, no login required.
    # Customers look up their order/repair status by reference number + email.
    # The router itself is rate-limited (10/minute per IP) against enumeration.
    f"{settings.API_V1_STR}/portal",
    # Theme GET is public — needed before login for branding.
    # The PUT endpoint is guarded at router level via @require_permission.
    f"{settings.API_V1_STR}/theme",
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
            payload = jwt.decode(
                token, settings.SECRET_KEY, algorithms=[ALGORITHM]
            )
        except JWTError as e:
            logger.warning(
                "Invalid JWT token",
                extra={"path": path, "error": str(e)},
            )
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or expired token"},
            )

        # Populate request.state so downstream middleware (audit logging,
        # rate limiting) can attribute the request to a user without
        # re-parsing the token.  We store only the user_id — fetching the
        # full User row would add a per-request DB hit and leak PII (email,
        # role) into middleware state.
        #
        # Downstream consumers:
        #   - middleware/audit_logging.py reads request.state.user_id
        #     for the CustomerAuditLog.user_id FK.
        #   - middleware/rate_limiting.py reads request.state.user as a
        #     full user object — it already tolerates a missing value
        #     (falls back to the IP-based key), so leaving .user unset
        #     here is safe.
        sub = payload.get("sub")
        if sub is not None:
            try:
                request.state.user_id = int(sub)
            except (TypeError, ValueError):
                # Malformed `sub` — do not populate user_id.  The request
                # proceeds (the token's signature was valid) but audit rows
                # will be written with user_id=None, which is honest.
                logger.warning(
                    "JWT sub claim is not an integer",
                    extra={"path": path},
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
