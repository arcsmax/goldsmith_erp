# src/goldsmith_erp/api/routers/users.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List

from goldsmith_erp.api.deps import get_current_user
from goldsmith_erp.db.session import get_db
from goldsmith_erp.db.models import User as UserModel
from goldsmith_erp.models.user import UserCreate, User, UserUpdate
from goldsmith_erp.services.user_service import UserService
from goldsmith_erp.core.permissions import require_admin

router = APIRouter()


# ==================== DEPENDENCY HELPERS ====================

async def get_admin_user(
    current_user: UserModel = Depends(get_current_user)
) -> UserModel:
    """Dependency that ensures the current user is an admin."""
    return await require_admin(current_user)


# ==================== PUBLIC ENDPOINTS ====================

@router.post("/register", response_model=User, status_code=status.HTTP_201_CREATED)
async def register_user(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    **Self-Registration**: Benutzer registriert sich selbst.

    - **Öffentlicher Endpoint** (keine Authentifizierung erforderlich)
    - Erstellt einen neuen Benutzer-Account
    - E-Mail muss eindeutig sein

    **Use Case**: Neuer Benutzer möchte sich selbst im System registrieren.
    """
    # Prüfen ob E-Mail bereits existiert
    existing_user = await UserService.get_user_by_email(db, user_in.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Benutzer erstellen
    user = await UserService.create_user(db, user_in)
    return user


# ==================== AUTHENTICATED ENDPOINTS ====================

@router.get("/me", response_model=User)
async def get_current_user_profile(
    current_user: UserModel = Depends(get_current_user)
):
    """
    Eigenes Benutzer-Profil abrufen.

    - **Authentifizierung erforderlich**
    - Gibt das Profil des eingeloggten Benutzers zurück

    **Use Case**: Benutzer möchte seine eigenen Profil-Daten sehen.
    """
    return current_user


@router.put("/me", response_model=User)
async def update_current_user_profile(
    user_in: UserUpdate,
    current_user: UserModel = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Eigenes Benutzer-Profil aktualisieren.

    - **Authentifizierung erforderlich**
    - Benutzer kann nur sein eigenes Profil bearbeiten
    - E-Mail, Name und Passwort können geändert werden

    **Use Case**: Benutzer möchte seine Profil-Daten aktualisieren.
    """
    # Prüfen ob neue E-Mail bereits existiert (falls geändert)
    if user_in.email and user_in.email != current_user.email:
        existing_user = await UserService.get_user_by_email(db, user_in.email)
        if existing_user:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already in use"
            )

    # Profil aktualisieren
    updated_user = await UserService.update_user(db, current_user.id, user_in)
    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return updated_user


# ==================== ADMIN-ONLY ENDPOINTS ====================

@router.post("/", response_model=User, status_code=status.HTTP_201_CREATED)
async def create_user_by_admin(
    user_in: UserCreate,
    db: AsyncSession = Depends(get_db),
    admin: UserModel = Depends(get_admin_user)
):
    """
    **Admin-Registration**: Goldschmied (Admin) trägt einen neuen Benutzer ein.

    - **Admin-Berechtigung erforderlich**
    - Erstellt einen neuen Benutzer-Account
    - E-Mail muss eindeutig sein

    **Use Case**: Goldschmied trägt einen neuen Mitarbeiter oder Kunden ein.
    """
    # Prüfen ob E-Mail bereits existiert
    existing_user = await UserService.get_user_by_email(db, user_in.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Benutzer erstellen
    user = await UserService.create_user(db, user_in)
    return user


@router.get("/", response_model=List[User])
async def list_all_users(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    admin: UserModel = Depends(get_admin_user)
):
    """
    Alle Benutzer auflisten.

    - **Admin-Berechtigung erforderlich**
    - Gibt eine Liste aller Benutzer zurück (mit Pagination)

    **Use Case**: Admin möchte alle registrierten Benutzer sehen.
    """
    users = await UserService.get_users(db, skip, limit)
    return users


@router.get("/{user_id}", response_model=User)
async def get_user_by_id(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: UserModel = Depends(get_admin_user)
):
    """
    Benutzer über ID abrufen.

    - **Admin-Berechtigung erforderlich**
    - Gibt einen spezifischen Benutzer zurück

    **Use Case**: Admin möchte Details eines bestimmten Benutzers sehen.
    """
    user = await UserService.get_user_by_id(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )
    return user


@router.put("/{user_id}", response_model=User)
async def update_user_by_admin(
    user_id: int,
    user_in: UserUpdate,
    db: AsyncSession = Depends(get_db),
    admin: UserModel = Depends(get_admin_user)
):
    """
    Benutzer durch Admin aktualisieren.

    - **Admin-Berechtigung erforderlich**
    - Admin kann beliebige Benutzer-Daten ändern
    - Inkl. Aktivierungs-Status (is_active)

    **Use Case**: Admin möchte Benutzer-Daten korrigieren oder Status ändern.
    """
    # Prüfen ob neue E-Mail bereits existiert (falls geändert)
    if user_in.email:
        user = await UserService.get_user_by_id(db, user_id)
        if user and user_in.email != user.email:
            existing_user = await UserService.get_user_by_email(db, user_in.email)
            if existing_user:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Email already in use"
                )

    # Benutzer aktualisieren
    updated_user = await UserService.update_user(db, user_id, user_in)
    if not updated_user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return updated_user


@router.delete("/{user_id}")
async def deactivate_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: UserModel = Depends(get_admin_user)
):
    """
    Benutzer deaktivieren (Soft Delete).

    - **Admin-Berechtigung erforderlich**
    - Setzt is_active auf False
    - Benutzer kann sich nicht mehr einloggen
    - Daten bleiben erhalten

    **Use Case**: Admin möchte einen Benutzer sperren, aber Daten behalten.
    """
    result = await UserService.delete_user(db, user_id)
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result["message"]
        )

    return result


@router.post("/{user_id}/activate", response_model=User)
async def activate_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    admin: UserModel = Depends(get_admin_user)
):
    """
    Benutzer reaktivieren.

    - **Admin-Berechtigung erforderlich**
    - Setzt is_active auf True
    - Benutzer kann sich wieder einloggen

    **Use Case**: Admin möchte einen gesperrten Benutzer wieder aktivieren.
    """
    user = await UserService.activate_user(db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found"
        )

    return user
