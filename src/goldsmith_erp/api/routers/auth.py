import logging
from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from jose import JWTError
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from goldsmith_erp.core.security import (
    verify_password,
    create_access_token,
    decode_token_allowing_grace_window,
)
from goldsmith_erp.core.config import settings
from goldsmith_erp.db.session import get_db
from goldsmith_erp.db.models import User

logger = logging.getLogger(__name__)

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

@router.post("/login/access-token")
@limiter.limit("5/minute")  # Max 5 login attempts per minute per IP
async def login_access_token(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    form_data: OAuth2PasswordRequestForm = Depends()
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

    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=access_token_expires
    )

    # Set HttpOnly cookie for enhanced security
    response.set_cookie(
        key="access_token",
        value=token,
        httponly=True,  # Prevents JavaScript access (XSS protection)
        secure=not settings.DEBUG,  # HTTPS only in production
        samesite="lax",  # CSRF protection
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,  # Convert to seconds
    )

    return {
        "access_token": token,
        "token_type": "bearer"
    }


@router.post("/logout")
async def logout(response: Response):
    """
    Logout by clearing the HttpOnly cookie.
    """
    response.delete_cookie(
        key="access_token",
        httponly=True,
        secure=not settings.DEBUG,
        samesite="lax"
    )
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
    # Extract token — mirror auth_required.py extraction logic
    token: str | None = None
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header[7:]
    if not token:
        token = request.cookies.get("access_token")

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

    # Issue a fresh token with the standard expiry
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    new_token = create_access_token(
        data={"sub": str(user.id)},
        expires_delta=access_token_expires,
    )

    # Refresh the HttpOnly cookie (same settings as login)
    response.set_cookie(
        key="access_token",
        value=new_token,
        httponly=True,
        secure=not settings.DEBUG,
        samesite="lax",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

    logger.info("Token refreshed for user", extra={"user_id": user_id})

    return {
        "access_token": new_token,
        "token_type": "bearer",
    }