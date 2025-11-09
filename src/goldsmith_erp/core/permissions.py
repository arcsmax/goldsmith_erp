# src/goldsmith_erp/core/permissions.py
"""
Role-Based Access Control (RBAC) system for Goldsmith ERP.

Defines user roles, permissions, and decorators for protecting endpoints.
"""

from enum import Enum
from functools import wraps
from typing import Callable, List
from fastapi import HTTPException, Depends, status

from goldsmith_erp.db.models import User as UserModel, UserRole


class Permission(str, Enum):
    """Granular permissions for different operations."""

    # Order permissions
    ORDER_VIEW = "order:view"
    ORDER_CREATE = "order:create"
    ORDER_EDIT = "order:edit"
    ORDER_DELETE = "order:delete"

    # User management permissions
    USER_VIEW = "user:view"
    USER_CREATE = "user:create"
    USER_EDIT = "user:edit"
    USER_DELETE = "user:delete"
    USER_MANAGE = "user:manage"  # Full user management

    # Material permissions
    MATERIAL_VIEW = "material:view"
    MATERIAL_CREATE = "material:create"
    MATERIAL_EDIT = "material:edit"
    MATERIAL_DELETE = "material:delete"
    MATERIAL_ADJUST_STOCK = "material:adjust_stock"

    # Time tracking permissions
    TIME_TRACK = "time:track"
    TIME_VIEW_OWN = "time:view_own"
    TIME_VIEW_ALL = "time:view_all"
    TIME_EDIT = "time:edit"
    TIME_DELETE = "time:delete"

    # Activity permissions
    ACTIVITY_VIEW = "activity:view"
    ACTIVITY_CREATE = "activity:create"
    ACTIVITY_EDIT = "activity:edit"
    ACTIVITY_DELETE = "activity:delete"

    # Customer permissions
    CUSTOMER_VIEW = "customer:view"
    CUSTOMER_CREATE = "customer:create"
    CUSTOMER_EDIT = "customer:edit"
    CUSTOMER_DELETE = "customer:delete"

    # Report permissions
    REPORTS_VIEW = "reports:view"
    REPORTS_EXPORT = "reports:export"

    # System permissions
    SYSTEM_CONFIG = "system:config"


# Role-Permission mapping
ROLE_PERMISSIONS: dict[UserRole, List[Permission]] = {
    UserRole.ADMIN: [
        # Admins have all permissions
        p for p in Permission
    ],
    UserRole.GOLDSMITH: [
        # Orders
        Permission.ORDER_VIEW,
        Permission.ORDER_CREATE,
        Permission.ORDER_EDIT,
        # Materials (view and adjust stock)
        Permission.MATERIAL_VIEW,
        Permission.MATERIAL_ADJUST_STOCK,
        # Time tracking
        Permission.TIME_TRACK,
        Permission.TIME_VIEW_OWN,
        Permission.TIME_EDIT,
        # Activities
        Permission.ACTIVITY_VIEW,
        Permission.ACTIVITY_CREATE,  # Can create custom activities
        # Customers
        Permission.CUSTOMER_VIEW,
        Permission.CUSTOMER_CREATE,
        Permission.CUSTOMER_EDIT,
        # Reports
        Permission.REPORTS_VIEW,
    ],
    UserRole.VIEWER: [
        # View-only access
        Permission.ORDER_VIEW,
        Permission.MATERIAL_VIEW,
        Permission.TIME_VIEW_OWN,
        Permission.ACTIVITY_VIEW,
        Permission.CUSTOMER_VIEW,
        Permission.REPORTS_VIEW,
    ],
}


def has_permission(user: UserModel, permission: Permission) -> bool:
    """
    Check if a user has a specific permission based on their role.

    Args:
        user: The user to check
        permission: The permission to check for

    Returns:
        True if user has the permission, False otherwise
    """
    if not user or not hasattr(user, 'role'):
        return False

    user_permissions = ROLE_PERMISSIONS.get(user.role, [])
    return permission in user_permissions


def require_permission(permission: Permission):
    """
    Decorator to require a specific permission for an endpoint.

    Usage:
        @router.delete("/{order_id}")
        @require_permission(Permission.ORDER_DELETE)
        async def delete_order(order_id: int, current_user: User = Depends()):
            ...

    Args:
        permission: The permission required to access the endpoint

    Returns:
        Decorator function

    Raises:
        HTTPException: 403 Forbidden if user doesn't have permission
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Extract current_user from kwargs
            current_user = kwargs.get('current_user')

            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required"
                )

            # Check permission
            if not has_permission(current_user, permission):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission denied: {permission.value}. Required role: {', '.join([role.value for role, perms in ROLE_PERMISSIONS.items() if permission in perms])}"
                )

            # Call the original function
            return await func(*args, **kwargs)

        return wrapper
    return decorator


def require_any_permission(*permissions: Permission):
    """
    Decorator to require ANY of the specified permissions (OR logic).

    Usage:
        @router.get("/reports")
        @require_any_permission(Permission.REPORTS_VIEW, Permission.REPORTS_EXPORT)
        async def get_reports(current_user: User = Depends()):
            ...

    Args:
        *permissions: Variable number of permissions (user needs at least one)

    Returns:
        Decorator function

    Raises:
        HTTPException: 403 Forbidden if user doesn't have any of the permissions
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_user = kwargs.get('current_user')

            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required"
                )

            # Check if user has ANY of the permissions
            has_any = any(has_permission(current_user, perm) for perm in permissions)

            if not has_any:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission denied. Required one of: {', '.join([p.value for p in permissions])}"
                )

            return await func(*args, **kwargs)

        return wrapper
    return decorator


def require_all_permissions(*permissions: Permission):
    """
    Decorator to require ALL of the specified permissions (AND logic).

    Usage:
        @router.post("/system/backup")
        @require_all_permissions(Permission.SYSTEM_CONFIG, Permission.REPORTS_EXPORT)
        async def create_backup(current_user: User = Depends()):
            ...

    Args:
        *permissions: Variable number of permissions (user needs all of them)

    Returns:
        Decorator function

    Raises:
        HTTPException: 403 Forbidden if user doesn't have all permissions
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_user = kwargs.get('current_user')

            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required"
                )

            # Check if user has ALL permissions
            missing_permissions = [
                perm for perm in permissions
                if not has_permission(current_user, perm)
            ]

            if missing_permissions:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission denied. Missing permissions: {', '.join([p.value for p in missing_permissions])}"
                )

            return await func(*args, **kwargs)

        return wrapper
    return decorator


def require_role(role: UserRole):
    """
    Decorator to require a specific role (simpler than permission-based).

    Usage:
        @router.post("/admin/settings")
        @require_role(UserRole.ADMIN)
        async def update_settings(current_user: User = Depends()):
            ...

    Args:
        role: The role required to access the endpoint

    Returns:
        Decorator function

    Raises:
        HTTPException: 403 Forbidden if user doesn't have the role
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            current_user = kwargs.get('current_user')

            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required"
                )

            if not hasattr(current_user, 'role') or current_user.role != role:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Access denied. Required role: {role.value}"
                )

            return await func(*args, **kwargs)

        return wrapper
    return decorator


def check_ownership_or_permission(
    resource_user_id: int,
    current_user: UserModel,
    fallback_permission: Permission
) -> bool:
    """
    Helper to check if user owns a resource OR has a fallback permission.

    Useful for operations like "view your own time entries OR view all time entries".

    Args:
        resource_user_id: The user_id who owns the resource
        current_user: The current authenticated user
        fallback_permission: Permission to check if user doesn't own resource

    Returns:
        True if user owns resource or has fallback permission
    """
    # User owns the resource
    if current_user.id == resource_user_id:
        return True

    # User has permission to access others' resources
    return has_permission(current_user, fallback_permission)
