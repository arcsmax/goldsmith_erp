# src/goldsmith_erp/core/permissions.py
"""
Role-Based Access Control (RBAC) system for Goldsmith ERP.

Defines user roles, permissions, and decorators for protecting endpoints.
"""

from enum import Enum
from functools import wraps
from typing import Callable, List

from fastapi import Depends, HTTPException, status

from goldsmith_erp.db.models import User as UserModel
from goldsmith_erp.db.models import UserRole


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

    # Invoice permissions (financial data - ADMIN and GOLDSMITH only)
    INVOICE_VIEW = "invoice:view"
    INVOICE_CREATE = "invoice:create"
    INVOICE_EDIT = "invoice:edit"
    INVOICE_DELETE = "invoice:delete"

    # Quote permissions (Kostenvoranschlag - ADMIN and GOLDSMITH only)
    QUOTE_VIEW = "quote:view"
    QUOTE_CREATE = "quote:create"
    QUOTE_EDIT = "quote:edit"
    QUOTE_DELETE = "quote:delete"

    # Report permissions
    REPORTS_VIEW = "reports:view"
    REPORTS_EXPORT = "reports:export"

    # System permissions
    SYSTEM_CONFIG = "system:config"

    # ML permissions
    ML_PREDICT = "ml:predict"  # Predict duration for orders (all authenticated users)
    ML_TRAIN = "ml:train"  # Trigger model training (ADMIN only)
    ML_VIEW_STATS = (
        "ml:view_stats"  # View model status, anomalies, activity stats (all)
    )

    # Notification permissions
    NOTIFICATION_VIEW = "notification:view"  # Read own notifications
    NOTIFICATION_CHECK_DEADLINES = (
        "notification:check_deadlines"  # Trigger deadline scan (ADMIN)
    )

    # Handoff permissions (Stabuebergabe)
    HANDOFF_CREATE = "handoff:create"  # Create a handoff (GOLDSMITH + ADMIN)
    HANDOFF_RESPOND = (
        "handoff:respond"  # Accept/decline incoming handoffs (GOLDSMITH + ADMIN)
    )
    HANDOFF_VIEW = "handoff:view"  # View handoffs on an order (all authenticated)

    # Repair permissions (Reparaturverwaltung)
    REPAIR_VIEW = "repair:view"  # View repair jobs
    REPAIR_CREATE = "repair:create"  # Create new repair intake
    REPAIR_EDIT = "repair:edit"  # Update repair status and notes

    # Consultation permissions (Beratung — Design-IP: GOLDSMITH/ADMIN only)
    CONSULTATION_VIEW = "consultation:view"
    CONSULTATION_CREATE = "consultation:create"
    CONSULTATION_EDIT = "consultation:edit"

    # Hallmark permissions (Punzierung)
    HALLMARK_VIEW = "hallmark:view"  # View hallmark records
    HALLMARK_CREATE = "hallmark:create"  # Create hallmark record
    HALLMARK_EDIT = "hallmark:edit"  # Update hallmark status

    # Valuation certificate permissions (Wertgutachten — financial data)
    VALUATION_VIEW = "valuation:view"  # View valuation certificates
    VALUATION_CREATE = "valuation:create"  # Create certificate (ADMIN + GOLDSMITH)
    VALUATION_EXPORT = "valuation:export"  # Download PDF (ADMIN only)

    # Customer update permissions (Kundeninfo — V1.2, GOLDSMITH + ADMIN only)
    CUSTOMER_UPDATE_VIEW = "customer_update:view"  # View update history/drafts
    CUSTOMER_UPDATE_SEND = "customer_update:send"  # Create + send updates

    # Cost change request permissions (§649 BGB Kostenfreigabe — financial
    # data, V1.2, GOLDSMITH + ADMIN only)
    COST_CHANGE_VIEW = "cost_change:view"  # View cost-change requests + projected cost
    COST_CHANGE_MANAGE = (
        "cost_change:manage"  # Create/send cost changes, record customer response
    )

    # Statistical labor estimator permissions (V1.3 Phase 1 — pricing data,
    # GOLDSMITH + ADMIN only, mirrors COST_CHANGE_*'s financial gating).
    # A single permission covers both endpoints: unlike COST_CHANGE_MANAGE
    # (which creates/sends a persisted CostChangeRequest), POST
    # /estimates/labor performs no persistent mutation — it is a stateless
    # financial computation over already-committed order/time-entry data,
    # so a separate *_MANAGE permission would grant no additional access
    # control today. Add ESTIMATE_MANAGE if/when Phase 3 persists an
    # accepted estimate onto a quote (a real "manage" action to gate).
    ESTIMATE_VIEW = "estimate:view"  # Request a labor estimate + view calibration

    # Scanner permissions (V1.1 QR/Barcode workflow)
    # Granted to all three roles — the service layer performs role-based
    # content projection, so VIEWER may call /scan/resolve but will never
    # see financial fields (cf. ORDER_FIELDS_BY_ROLE allow-lists in
    # services/scanner_service.py). Write operations (/scan/log,
    # /scan/log/batch) use the same permission because they write an
    # audit row, not a business mutation — the business mutation is a
    # separate endpoint guarded by its own permission.
    SCAN_READ = "scan:read"


# Role-Permission mapping
ROLE_PERMISSIONS: dict[UserRole, List[Permission]] = {
    UserRole.ADMIN: [
        # Admins have all permissions
        p
        for p in Permission
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
        # Invoices (financial data - goldsmith can view and create, not delete)
        Permission.INVOICE_VIEW,
        Permission.INVOICE_CREATE,
        Permission.INVOICE_EDIT,
        # Quotes (Kostenvoranschlag - goldsmith can view, create, edit, not delete)
        Permission.QUOTE_VIEW,
        Permission.QUOTE_CREATE,
        Permission.QUOTE_EDIT,
        # Reports
        Permission.REPORTS_VIEW,
        # ML — goldsmiths can run predictions and view stats
        Permission.ML_PREDICT,
        Permission.ML_VIEW_STATS,
        # Notifications — goldsmiths receive and read their own
        Permission.NOTIFICATION_VIEW,
        # Handoffs — goldsmiths create and respond to handoffs
        Permission.HANDOFF_CREATE,
        Permission.HANDOFF_RESPOND,
        Permission.HANDOFF_VIEW,
        # Repairs — goldsmiths handle all repair workflow steps
        Permission.REPAIR_VIEW,
        Permission.REPAIR_CREATE,
        Permission.REPAIR_EDIT,
        # Consultations — goldsmiths run the intake conversation
        Permission.CONSULTATION_VIEW,
        Permission.CONSULTATION_CREATE,
        Permission.CONSULTATION_EDIT,
        # Hallmarks — goldsmiths submit and track Punzierung
        Permission.HALLMARK_VIEW,
        Permission.HALLMARK_CREATE,
        Permission.HALLMARK_EDIT,
        # Valuation certificates — goldsmiths create and view Wertgutachten
        Permission.VALUATION_VIEW,
        Permission.VALUATION_CREATE,
        # Scanner (V1.1) — goldsmiths are the primary scanner users
        Permission.SCAN_READ,
        # Customer updates (V1.2) — goldsmiths draft and send Kundeninfo
        Permission.CUSTOMER_UPDATE_VIEW,
        Permission.CUSTOMER_UPDATE_SEND,
        # Cost change requests (V1.2) — financial data, goldsmiths manage them
        Permission.COST_CHANGE_VIEW,
        Permission.COST_CHANGE_MANAGE,
        # Statistical labor estimator (V1.3) — financial data, goldsmiths
        # can request estimates and view calibration
        Permission.ESTIMATE_VIEW,
    ],
    UserRole.VIEWER: [
        # View-only access
        Permission.ORDER_VIEW,
        Permission.MATERIAL_VIEW,
        Permission.TIME_VIEW_OWN,
        Permission.ACTIVITY_VIEW,
        Permission.CUSTOMER_VIEW,
        Permission.REPORTS_VIEW,
        # ML — viewers can see predictions and stats, not trigger training
        Permission.ML_PREDICT,
        Permission.ML_VIEW_STATS,
        # Notifications — viewers receive and read their own
        Permission.NOTIFICATION_VIEW,
        # Handoffs — viewers can see handoff history but not create/respond
        Permission.HANDOFF_VIEW,
        # Repairs — viewers can see repair status (e.g. front desk)
        Permission.REPAIR_VIEW,
        # Hallmarks — viewers can see hallmark status (informational)
        Permission.HALLMARK_VIEW,
        # Valuations — viewers cannot see financial valuation data
        # Scanner (V1.1) — viewers may scan; content projection ensures
        # no financial fields are returned to their role.
        Permission.SCAN_READ,
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
    if not user or not hasattr(user, "role"):
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
            current_user = kwargs.get("current_user")

            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required",
                )

            # Check permission
            if not has_permission(current_user, permission):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission denied: {permission.value}. Required role: {', '.join([role.value for role, perms in ROLE_PERMISSIONS.items() if permission in perms])}",
                )

            # Call the original function
            return await func(*args, **kwargs)

        return wrapper

    return decorator


def require_permission_dep(permission: Permission) -> Callable:
    """
    FastAPI ``Depends`` factory that enforces a permission at the DI layer.

    Companion to :func:`require_permission` (the decorator style). Use this
    form when you want the permission check expressed directly in the route
    signature rather than as a decorator above the function:

    Usage:
        @router.get("/customers")
        async def list_customers(
            current_user: User = Depends(require_permission_dep(Permission.CUSTOMER_VIEW)),
        ):
            ...

    Args:
        permission: The permission required to access the endpoint

    Returns:
        Callable: Async dependency that returns the ``User`` on success or
        raises ``HTTPException(403)`` on failure.

    Notes:
        Added as part of fix A2 (2026-04-23) so the four routers that were
        using the now-removed ``api.deps.require_permission`` factory can
        keep their existing signature style without a disruptive rewrite.
        See docs/fix-plan/2026-04-23/A2-permission-merge.md.
    """
    # Imported here (not at module top) to avoid a circular import with
    # api.deps, which imports from core.permissions via some call paths.
    from goldsmith_erp.api.deps import get_current_user

    async def permission_checker(
        current_user: UserModel = Depends(get_current_user),
    ) -> UserModel:
        if not has_permission(current_user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {permission.value} required",
            )
        return current_user

    return permission_checker


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
            current_user = kwargs.get("current_user")

            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required",
                )

            # Check if user has ANY of the permissions
            has_any = any(has_permission(current_user, perm) for perm in permissions)

            if not has_any:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission denied. Required one of: {', '.join([p.value for p in permissions])}",
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
            current_user = kwargs.get("current_user")

            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required",
                )

            # Check if user has ALL permissions
            missing_permissions = [
                perm for perm in permissions if not has_permission(current_user, perm)
            ]

            if missing_permissions:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Permission denied. Missing permissions: {', '.join([p.value for p in missing_permissions])}",
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
            current_user = kwargs.get("current_user")

            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required",
                )

            if not hasattr(current_user, "role") or current_user.role != role:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"Access denied. Required role: {role.value}",
                )

            return await func(*args, **kwargs)

        return wrapper

    return decorator


def check_ownership_or_permission(
    resource_user_id: int, current_user: UserModel, fallback_permission: Permission
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
