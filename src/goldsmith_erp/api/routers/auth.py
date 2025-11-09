from datetime import timedelta
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from goldsmith_erp.core.security import verify_password, create_access_token
from goldsmith_erp.core.config import settings
from goldsmith_erp.db.session import get_db
from goldsmith_erp.db.models import User

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