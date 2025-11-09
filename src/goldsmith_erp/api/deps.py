from fastapi import Cookie, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from typing import Generator, Optional, Callable
from enum import Enum
from functools import wraps

from goldsmith_erp.core.config import settings
from goldsmith_erp.core.security import ALGORITHM
from goldsmith_erp.db.session import get_db
from goldsmith_erp.db.models import User, UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.API_V1_STR}/login/access-token", auto_error=False)


async def get_token_from_cookie_or_header(
    request: Request,
    access_token: Optional[str] = Cookie(None),
    authorization: Optional[str] = Depends(oauth2_scheme)
) -> str:
    """
    Extract JWT token from HttpOnly cookie or Authorization header.

    Priority:
    1. HttpOnly cookie (more secure)
    2. Authorization header (backward compatibility)

    Raises:
        HTTPException: If no valid token is found
    """
    # Try to get token from cookie first (more secure)
    if access_token:
        return access_token

    # Fall back to Authorization header
    if authorization:
        return authorization

    # No token found
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated",
        headers={"WWW-Authenticate": "Bearer"},
    )

async def get_current_user(
    db: AsyncSession = Depends(get_db),
    token: str = Depends(get_token_from_cookie_or_header)
) -> User:
    """
    Returns the current user based on JWT token from cookie or header.

    Supports both HttpOnly cookies (recommended) and Authorization header
    (backward compatibility).
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        user_id: Optional[int] = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    result = await db.execute(select(User).filter(User.id == user_id))
    user = result.scalar_one_or_none()

    if user is None:
        raise credentials_exception
    if not user.is_active:
        raise HTTPException(status_code=400, detail="Inactive user")

    return user


async def get_current_admin_user(
    current_user: User = Depends(get_current_user)
) -> User:
    """
    Dependency that ensures the current user has admin role.

    Raises:
        HTTPException: If user is not an admin
    """
    if current_user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not enough permissions. Admin role required."
        )
    return current_user


# ============================================================================
# Permission System for Fine-Grained Access Control
# ============================================================================

class Permission(str, Enum):
    """System permissions for fine-grained access control"""
    # Order permissions
    ORDER_VIEW = "order:view"
    ORDER_CREATE = "order:create"
    ORDER_EDIT = "order:edit"
    ORDER_DELETE = "order:delete"

    # Customer permissions
    CUSTOMER_VIEW = "customer:view"
    CUSTOMER_CREATE = "customer:create"
    CUSTOMER_EDIT = "customer:edit"
    CUSTOMER_DELETE = "customer:delete"

    # Time tracking permissions
    TIME_TRACK = "time:track"
    TIME_VIEW_OWN = "time:view_own"
    TIME_VIEW_ALL = "time:view_all"
    TIME_EDIT = "time:edit"

    # Material permissions
    MATERIAL_VIEW = "material:view"
    MATERIAL_EDIT = "material:edit"

    # Reports & Analytics
    REPORTS_VIEW = "reports:view"

    # Admin permissions
    USER_MANAGE = "user:manage"
    SYSTEM_CONFIG = "system:config"


# Role to Permission mapping
ROLE_PERMISSIONS = {
    UserRole.ADMIN: [p for p in Permission],  # Admin has all permissions
    UserRole.USER: [
        # Orders
        Permission.ORDER_VIEW,
        Permission.ORDER_CREATE,
        Permission.ORDER_EDIT,
        # Customers
        Permission.CUSTOMER_VIEW,
        Permission.CUSTOMER_CREATE,
        Permission.CUSTOMER_EDIT,
        # Time tracking
        Permission.TIME_TRACK,
        Permission.TIME_VIEW_OWN,
        # Materials
        Permission.MATERIAL_VIEW,
        # Reports (limited)
        Permission.REPORTS_VIEW,
    ],
}


def has_permission(user: User, permission: Permission) -> bool:
    """
    Check if user has a specific permission based on their role.

    Args:
        user: The user to check
        permission: The required permission

    Returns:
        bool: True if user has permission, False otherwise
    """
    if not user.is_active:
        return False

    allowed_permissions = ROLE_PERMISSIONS.get(user.role, [])
    return permission in allowed_permissions


def require_permission(permission: Permission) -> Callable:
    """
    Dependency factory that creates a permission checker.

    Usage:
        @router.get("/customers")
        async def list_customers(
            current_user: User = Depends(require_permission(Permission.CUSTOMER_VIEW))
        ):
            ...

    Args:
        permission: The required permission

    Returns:
        Callable: Dependency function that checks permission
    """
    async def permission_checker(
        current_user: User = Depends(get_current_user)
    ) -> User:
        """Check if current user has required permission"""
        if not has_permission(current_user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission.value} required"
            )
        return current_user

    return permission_checker