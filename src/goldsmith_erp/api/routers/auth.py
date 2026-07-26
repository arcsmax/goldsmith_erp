import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError, jwt
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from goldsmith_erp.core.config import settings
from goldsmith_erp.core.security import (
    ALGORITHM,
    create_access_token,
    decode_token_allowing_grace_window,
    verify_password,
)
from goldsmith_erp.core.token_revocation import (
    blocklist_jti,
    is_token_revoked,
    remaining_ttl_seconds,
)
from goldsmith_erp.db.models import User
from goldsmith_erp.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

# Login rate-limit tuning (finding 2.10). The whole workshop shares one NAT IP,
# so an IP-only limiter lets a single abuser lock everyone out. We bucket the
# primary brute-force control by (ip, normalized username), and keep a LOOSER
# per-IP ceiling so one host hammering many usernames is still capped. Both
# limits apply to every login; the tighter one wins. The ceiling must exceed the
# per-account limit, otherwise one account's failures would exhaust the shared
# IP bucket and throttle every colleague behind the same NAT.
_LOGIN_PER_ACCOUNT_LIMIT = "5/minute"  # per (ip, username)
_LOGIN_PER_IP_CEILING = "20/minute"  # per ip, across all usernames


async def _capture_login_identifier(
    request: Request, username: str = Form(default="")
) -> None:
    """Stash the normalized login username on ``request.state``.

    Runs as a FastAPI dependency (resolved before the slowapi wrapper), so the
    rate-limit key function can read it synchronously. Reuses FastAPI's already
    parsed-and-cached form body — it does not consume the request stream twice.
    """
    request.state.login_username = username.strip().lower()


def _login_ip_username_key(request: Request) -> str:
    """slowapi key: ``ip|normalized-username``. Called synchronously by slowapi."""
    ip = get_remote_address(request)
    username = getattr(request.state, "login_username", "") or ""
    return f"{ip}|{username}"


def _extract_token(request: Request) -> str | None:
    """Read the JWT from the Authorization Bearer header or the HttpOnly cookie."""
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.startswith("Bearer "):
        return auth_header[7:]
    return request.cookies.get("access_token")


@router.post("/login/access-token")
@limiter.limit(_LOGIN_PER_IP_CEILING)  # per-IP ceiling (shared-NAT safety)
@limiter.limit(_LOGIN_PER_ACCOUNT_LIMIT, key_func=_login_ip_username_key)  # per account
async def login_access_token(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends(),
    _login_key: None = Depends(_capture_login_identifier),
):
    """
    OAuth2 compatible token login with HttpOnly cookie.

    Sets a secure HttpOnly cookie to prevent XSS attacks.
    Also returns the token in the response for backward compatibility.
    """
    result = await db.execute(select(User).filter(User.email == form_data.username))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    if not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",  # Don't reveal account status
        )

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    token = create_access_token(
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )

    # Set HttpOnly cookie for enhanced security (XSS protection)
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,  # Prevents JavaScript access (XSS protection)
        secure=settings.COOKIE_SECURE,  # Controlled via COOKIE_SECURE env var
        samesite="strict",  # Strict same-site — browser will not send the
        # cookie on cross-site requests at all. This
        # is meaningful (though partial) CSRF
        # mitigation; full double-submit CSRF is
        # tracked as A7.1–A7.3. Safe because the app
        # has no email-link "land logged in" flows
        # that Strict would break (self-registration
        # was removed in A3).
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # seconds
        path="/",  # Cookie valid for all paths
    )

    # Token is set via HttpOnly cookie only — not exposed in response body.
    return {"message": "Login successful"}


@router.post("/logout")
async def logout(request: Request, response: Response):
    """
    Logout: blocklist the presented token's jti, then clear the HttpOnly cookie.

    Clearing the cookie alone left the token replayable via the Authorization
    header (finding 2.1). We now blocklist its jti in Redis for the remainder of
    its life (+refresh grace), so a captured Bearer token cannot be reused and
    cannot be exchanged at /refresh. Logout is best-effort and idempotent: a
    missing/invalid token or a Redis outage still clears the cookie and succeeds.
    """
    token = _extract_token(request)
    if token:
        try:
            # verify_exp=False so a just-expired token is still blocklisted
            # (it could otherwise be replayed inside the refresh grace window).
            payload = jwt.decode(
                token,
                settings.SECRET_KEY,
                algorithms=[ALGORITHM],
                options={"verify_exp": False},
            )
            jti = payload.get("jti")
            if jti:
                await blocklist_jti(str(jti), remaining_ttl_seconds(payload))
        except JWTError:
            pass  # not a valid token — nothing to revoke; still clear the cookie

    response.delete_cookie("access_token", path="/")
    return {"message": "Successfully logged out"}


@router.post("/refresh")
@limiter.limit("10/minute")  # Tighter than login; prevents refresh-loop abuse
async def refresh_access_token(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """
    Exchange a valid (or recently-expired, within the 5-minute grace window)
    access token for a fresh one.

    The endpoint reads the token from the Authorization header (Bearer) or the
    HttpOnly cookie — the same extraction logic used by the auth middleware.
    It does NOT accept credentials; callers must present an existing token.

    The endpoint is excluded from the deny-by-default middleware via PUBLIC_PREFIXES
    so that an expired token is not rejected before reaching this handler.
    All security checks (signature, grace window, user existence, user active state)
    are performed here.
    """
    # Extract token — Bearer header or HttpOnly cookie.
    token = _extract_token(request)

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No token provided",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Decode with grace-window logic (raises JWTError if too old or bad signature)
    try:
        payload = decode_token_allowing_grace_window(token)
    except JWTError as exc:
        logger.warning(
            "Token refresh rejected",
            extra={"reason": str(exc), "path": str(request.url)},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is invalid or has expired beyond the refresh window",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    # Revocation check (finding 2.1): a token blocklisted at logout, or issued
    # before the user's password-change mark, must not be exchanged for a fresh
    # one — otherwise refresh would be a revocation bypass.
    if await is_token_revoked(payload):
        logger.warning(
            "Token refresh rejected: token revoked",
            extra={"path": str(request.url)},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Verify the subject claim and that the user still exists and is active
    user_id: str | None = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload is missing subject claim",
        )

    result = await db.execute(select(User).filter(User.id == int(user_id)))
    user = result.scalar_one_or_none()

    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User no longer exists",
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated",
        )

    # Issue a fresh token (new jti/iat) with the standard expiry.
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    new_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=access_token_expires,
    )

    # Rotation (finding 2.1): blocklist the old jti so the just-replaced token
    # cannot be replayed after refresh. TTL covers its remaining life + grace.
    old_jti = payload.get("jti")
    if old_jti:
        await blocklist_jti(str(old_jti), remaining_ttl_seconds(payload))

    # Refresh the HttpOnly cookie (same settings as login)
    response.set_cookie(
        key="access_token",
        value=new_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite="strict",  # Matches login — see login handler for rationale.
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )

    logger.info("Token refreshed for user", extra={"user_id": user_id})

    # Token is set via HttpOnly cookie only — not exposed in response body.
    return {"message": "Token refreshed"}
