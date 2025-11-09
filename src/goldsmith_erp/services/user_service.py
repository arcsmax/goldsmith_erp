# src/goldsmith_erp/services/user_service.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update, delete
from typing import List, Optional, Dict, Any

from goldsmith_erp.db.models import User as UserModel
from goldsmith_erp.models.user import UserCreate, UserUpdate
from goldsmith_erp.core.security import get_password_hash


class UserService:
    """Service für User-Management mit CRUD-Operationen."""

    @staticmethod
    async def get_users(
        db: AsyncSession,
        skip: int = 0,
        limit: int = 100
    ) -> List[UserModel]:
        """
        Holt alle Benutzer mit Pagination.

        Args:
            db: Datenbank-Session
            skip: Anzahl zu überspringender Einträge
            limit: Maximum Anzahl zurückzugebender Einträge

        Returns:
            Liste von User-Objekten
        """
        result = await db.execute(
            select(UserModel)
            .order_by(UserModel.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        return result.scalars().all()

    @staticmethod
    async def get_user_by_id(
        db: AsyncSession,
        user_id: int
    ) -> Optional[UserModel]:
        """
        Holt einen einzelnen Benutzer über seine ID.

        Args:
            db: Datenbank-Session
            user_id: ID des Benutzers

        Returns:
            User-Objekt oder None
        """
        result = await db.execute(
            select(UserModel).filter(UserModel.id == user_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_user_by_email(
        db: AsyncSession,
        email: str
    ) -> Optional[UserModel]:
        """
        Holt einen Benutzer über seine E-Mail-Adresse.

        Args:
            db: Datenbank-Session
            email: E-Mail-Adresse des Benutzers

        Returns:
            User-Objekt oder None
        """
        result = await db.execute(
            select(UserModel).filter(UserModel.email == email)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create_user(
        db: AsyncSession,
        user_in: UserCreate
    ) -> UserModel:
        """
        Erstellt einen neuen Benutzer.

        Args:
            db: Datenbank-Session
            user_in: User-Erstellungsdaten

        Returns:
            Erstelltes User-Objekt
        """
        # Hash das Passwort
        hashed_password = get_password_hash(user_in.password)

        # Erstelle User-Objekt
        db_user = UserModel(
            email=user_in.email,
            hashed_password=hashed_password,
            first_name=user_in.first_name,
            last_name=user_in.last_name,
            is_active=True  # Neue Benutzer sind standardmäßig aktiv
        )

        db.add(db_user)
        await db.commit()
        await db.refresh(db_user)

        return db_user

    @staticmethod
    async def update_user(
        db: AsyncSession,
        user_id: int,
        user_in: UserUpdate
    ) -> Optional[UserModel]:
        """
        Aktualisiert einen bestehenden Benutzer.

        Args:
            db: Datenbank-Session
            user_id: ID des zu aktualisierenden Benutzers
            user_in: Update-Daten

        Returns:
            Aktualisiertes User-Objekt oder None
        """
        # Prüfen ob Benutzer existiert
        user = await UserService.get_user_by_id(db, user_id)
        if not user:
            return None

        # Update-Daten vorbereiten
        update_data = user_in.model_dump(exclude_unset=True)

        # Passwort hashen, falls vorhanden
        if "password" in update_data:
            hashed_password = get_password_hash(update_data["password"])
            update_data["hashed_password"] = hashed_password
            del update_data["password"]

        # Update durchführen
        if update_data:
            await db.execute(
                update(UserModel)
                .where(UserModel.id == user_id)
                .values(**update_data)
            )
            await db.commit()

        # Aktualisiertes Objekt holen
        updated_user = await UserService.get_user_by_id(db, user_id)
        return updated_user

    @staticmethod
    async def delete_user(
        db: AsyncSession,
        user_id: int
    ) -> Dict[str, Any]:
        """
        Löscht einen Benutzer (soft delete durch is_active=False).

        Args:
            db: Datenbank-Session
            user_id: ID des zu löschenden Benutzers

        Returns:
            Dict mit Erfolgs-Status
        """
        # Prüfen ob Benutzer existiert
        user = await UserService.get_user_by_id(db, user_id)
        if not user:
            return {"success": False, "message": "User not found"}

        # Soft delete: setze is_active auf False
        await db.execute(
            update(UserModel)
            .where(UserModel.id == user_id)
            .values(is_active=False)
        )
        await db.commit()

        return {
            "success": True,
            "message": f"User {user_id} deactivated successfully"
        }

    @staticmethod
    async def hard_delete_user(
        db: AsyncSession,
        user_id: int
    ) -> Dict[str, Any]:
        """
        Löscht einen Benutzer permanent aus der Datenbank.
        ACHTUNG: Diese Operation kann nicht rückgängig gemacht werden!

        Args:
            db: Datenbank-Session
            user_id: ID des zu löschenden Benutzers

        Returns:
            Dict mit Erfolgs-Status
        """
        # Prüfen ob Benutzer existiert
        user = await UserService.get_user_by_id(db, user_id)
        if not user:
            return {"success": False, "message": "User not found"}

        # Hard delete: Benutzer permanent löschen
        await db.execute(
            delete(UserModel).where(UserModel.id == user_id)
        )
        await db.commit()

        return {
            "success": True,
            "message": f"User {user_id} permanently deleted"
        }

    @staticmethod
    async def activate_user(
        db: AsyncSession,
        user_id: int
    ) -> Optional[UserModel]:
        """
        Aktiviert einen deaktivierten Benutzer.

        Args:
            db: Datenbank-Session
            user_id: ID des zu aktivierenden Benutzers

        Returns:
            Aktiviertes User-Objekt oder None
        """
        user = await UserService.get_user_by_id(db, user_id)
        if not user:
            return None

        await db.execute(
            update(UserModel)
            .where(UserModel.id == user_id)
            .values(is_active=True)
        )
        await db.commit()

        # Aktualisiertes Objekt holen
        activated_user = await UserService.get_user_by_id(db, user_id)
        return activated_user
