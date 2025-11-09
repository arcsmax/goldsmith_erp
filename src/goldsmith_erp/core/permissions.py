# src/goldsmith_erp/core/permissions.py

from enum import Enum
from typing import List
from fastapi import HTTPException, status, Depends
from goldsmith_erp.db.models import User


class UserRole(str, Enum):
    """
    Benutzerrollen im System.

    ADMIN: Voller Zugriff, kann andere Benutzer verwalten
    GOLDSMITH: Kann Aufträge und Materialien verwalten
    USER: Basis-Berechtigungen, kann eigene Aufträge sehen
    """
    ADMIN = "admin"
    GOLDSMITH = "goldsmith"
    USER = "user"


class PermissionChecker:
    """
    Helper-Klasse für Berechtigungs-Prüfungen.
    """

    @staticmethod
    def check_is_admin(current_user: User) -> None:
        """
        Prüft ob der aktuelle Benutzer Admin ist.

        Args:
            current_user: Aktuell eingeloggter Benutzer

        Raises:
            HTTPException: Wenn Benutzer kein Admin ist
        """
        # Für jetzt: Prüfen ob Email eine Admin-Email ist
        # TODO: Später durch echtes Role-System in DB ersetzen
        admin_emails = [
            "admin@goldsmith.local",
            "admin@example.com"
        ]

        if current_user.email not in admin_emails:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions. Admin role required."
            )

    @staticmethod
    def check_is_active(current_user: User) -> None:
        """
        Prüft ob der Benutzer aktiv ist.

        Args:
            current_user: Aktuell eingeloggter Benutzer

        Raises:
            HTTPException: Wenn Benutzer nicht aktiv ist
        """
        if not current_user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is deactivated"
            )

    @staticmethod
    def check_is_owner_or_admin(
        current_user: User,
        resource_owner_id: int
    ) -> None:
        """
        Prüft ob Benutzer Owner der Ressource oder Admin ist.

        Args:
            current_user: Aktuell eingeloggter Benutzer
            resource_owner_id: ID des Ressourcen-Owners

        Raises:
            HTTPException: Wenn Benutzer weder Owner noch Admin ist
        """
        admin_emails = [
            "admin@goldsmith.local",
            "admin@example.com"
        ]

        is_admin = current_user.email in admin_emails
        is_owner = current_user.id == resource_owner_id

        if not (is_admin or is_owner):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not enough permissions. Must be owner or admin."
            )


async def require_admin(current_user: User) -> User:
    """
    Dependency für Admin-only Endpoints.

    Hinweis: Diese Funktion muss manuell mit get_current_user kombiniert werden:

    Usage in routers:
        from goldsmith_erp.api.deps import get_current_user
        from functools import partial

        async def get_admin_user(
            current_user: User = Depends(get_current_user)
        ) -> User:
            return await require_admin(current_user)

        @router.get("/admin-only")
        async def admin_route(admin: User = Depends(get_admin_user)):
            ...

    Oder direkter:
        @router.get("/admin-only")
        async def admin_route(
            current_user: User = Depends(get_current_user)
        ):
            await require_admin(current_user)
            # ... rest of endpoint logic

    Args:
        current_user: Aktuell eingeloggter Benutzer

    Returns:
        User-Objekt wenn Admin

    Raises:
        HTTPException: Wenn kein Admin
    """
    PermissionChecker.check_is_admin(current_user)
    return current_user


async def require_active(current_user: User) -> User:
    """
    Dependency für Endpoints die aktive Benutzer erfordern.

    Args:
        current_user: Aktuell eingeloggter Benutzer

    Returns:
        User-Objekt wenn aktiv

    Raises:
        HTTPException: Wenn nicht aktiv
    """
    PermissionChecker.check_is_active(current_user)
    return current_user
