# src/goldsmith_erp/services/material_service.py

import json
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import update, delete
from sqlalchemy.orm import selectinload
from typing import List, Optional, Dict, Any

from goldsmith_erp.core.cache import MATERIALS_TTL, get_cached, invalidate
from goldsmith_erp.db.models import Material as MaterialModel
from goldsmith_erp.models.material import MaterialCreate, MaterialUpdate

# Stable cache key for the default (unpaginated) materials list.
_MATERIALS_LIST_KEY = "materials:list"


class MaterialService:
    """Service für Material-Management mit CRUD-Operationen."""

    @staticmethod
    async def get_materials(
        db: AsyncSession,
        skip: int = 0,
        limit: int = 100
    ) -> List[MaterialModel]:
        """
        Holt alle Materialien mit Pagination.

        The default call (skip=0, limit=100) is served from the Redis cache
        (TTL: MATERIALS_TTL seconds).  Parameterised calls bypass the cache so
        paginated or restricted results are never incorrectly shared.

        Args:
            db: Datenbank-Session
            skip: Anzahl zu überspringender Einträge
            limit: Maximum Anzahl zurückzugebender Einträge

        Returns:
            Liste von Material-Objekten
        """
        async def _fetch() -> List[MaterialModel]:
            result = await db.execute(
                select(MaterialModel)
                .order_by(MaterialModel.name.asc())
                .offset(skip)
                .limit(limit)
            )
            return list(result.scalars().all())

        # Only cache the canonical default query.
        if skip == 0 and limit == 100:
            def _serialise(materials: List[MaterialModel]) -> str:
                return json.dumps([
                    {
                        "id": m.id,
                        "name": m.name,
                        "description": m.description,
                        "unit_price": m.unit_price,
                        "stock": m.stock,
                        "unit": m.unit,
                    }
                    for m in materials
                ])

            # Deserialisation returns plain dicts; callers that need ORM
            # objects with parameterised pagination go directly to the DB.
            # For the list endpoint the dict representation is sufficient.
            return await get_cached(  # type: ignore[return-value]
                key=_MATERIALS_LIST_KEY,
                ttl=MATERIALS_TTL,
                fetch_fn=_fetch,
                serialise=_serialise,
                deserialise=json.loads,
            )

        return await _fetch()

    @staticmethod
    async def get_material_by_id(
        db: AsyncSession,
        material_id: int
    ) -> Optional[MaterialModel]:
        """
        Holt ein einzelnes Material über seine ID.

        Args:
            db: Datenbank-Session
            material_id: ID des Materials

        Returns:
            Material-Objekt oder None
        """
        result = await db.execute(
            select(MaterialModel)
            .options(
                selectinload(MaterialModel.orders)  # FIXED: Added orders eager loading
            )
            .filter(MaterialModel.id == material_id)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def get_material_by_name(
        db: AsyncSession,
        name: str
    ) -> Optional[MaterialModel]:
        """
        Holt ein Material über seinen Namen.

        Args:
            db: Datenbank-Session
            name: Name des Materials

        Returns:
            Material-Objekt oder None
        """
        result = await db.execute(
            select(MaterialModel).filter(MaterialModel.name == name)
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def create_material(
        db: AsyncSession,
        material_in: MaterialCreate
    ) -> MaterialModel:
        """
        Erstellt ein neues Material.

        Args:
            db: Datenbank-Session
            material_in: Material-Erstellungsdaten

        Returns:
            Erstelltes Material-Objekt
        """
        db_material = MaterialModel(
            name=material_in.name,
            description=material_in.description,
            unit_price=material_in.unit_price,
            stock=material_in.stock,
            unit=material_in.unit
        )

        db.add(db_material)
        await db.commit()
        await db.refresh(db_material)

        await invalidate(_MATERIALS_LIST_KEY)
        return db_material

    @staticmethod
    async def update_material(
        db: AsyncSession,
        material_id: int,
        material_in: MaterialUpdate
    ) -> Optional[MaterialModel]:
        """
        Aktualisiert ein bestehendes Material.

        Args:
            db: Datenbank-Session
            material_id: ID des zu aktualisierenden Materials
            material_in: Update-Daten

        Returns:
            Aktualisiertes Material-Objekt oder None
        """
        # Prüfen ob Material existiert
        material = await MaterialService.get_material_by_id(db, material_id)
        if not material:
            return None

        # Update-Daten vorbereiten (nur gesetzte Felder)
        update_data = material_in.model_dump(exclude_unset=True)

        # Update durchführen
        if update_data:
            await db.execute(
                update(MaterialModel)
                .where(MaterialModel.id == material_id)
                .values(**update_data)
            )
            await db.commit()
            await invalidate(_MATERIALS_LIST_KEY)

        # Aktualisiertes Objekt holen
        updated_material = await MaterialService.get_material_by_id(db, material_id)
        return updated_material

    @staticmethod
    async def delete_material(
        db: AsyncSession,
        material_id: int
    ) -> Dict[str, Any]:
        """
        Löscht ein Material aus der Datenbank.

        Args:
            db: Datenbank-Session
            material_id: ID des zu löschenden Materials

        Returns:
            Dict mit Erfolgs-Status
        """
        # Prüfen ob Material existiert
        material = await MaterialService.get_material_by_id(db, material_id)
        if not material:
            return {"success": False, "message": "Material not found"}

        # Material löschen
        await db.execute(
            delete(MaterialModel).where(MaterialModel.id == material_id)
        )
        await db.commit()
        await invalidate(_MATERIALS_LIST_KEY)

        return {
            "success": True,
            "message": f"Material {material_id} deleted successfully"
        }

    @staticmethod
    async def adjust_stock(
        db: AsyncSession,
        material_id: int,
        quantity: float,
        operation: str = "add"
    ) -> Optional[MaterialModel]:
        """
        Passt den Bestand eines Materials an.

        Args:
            db: Datenbank-Session
            material_id: ID des Materials
            quantity: Menge zum Hinzufügen/Entfernen
            operation: "add" oder "subtract"

        Returns:
            Aktualisiertes Material-Objekt oder None
        """
        material = await MaterialService.get_material_by_id(db, material_id)
        if not material:
            return None

        # Neuen Bestand berechnen
        if operation == "add":
            new_stock = material.stock + quantity
        elif operation == "subtract":
            new_stock = material.stock - quantity
            if new_stock < 0:
                raise ValueError("Stock cannot be negative")
        else:
            raise ValueError(f"Invalid operation: {operation}")

        # Bestand aktualisieren
        await db.execute(
            update(MaterialModel)
            .where(MaterialModel.id == material_id)
            .values(stock=new_stock)
        )
        await db.commit()
        await invalidate(_MATERIALS_LIST_KEY)

        # Aktualisiertes Objekt holen
        updated_material = await MaterialService.get_material_by_id(db, material_id)
        return updated_material

    @staticmethod
    async def get_low_stock_materials(
        db: AsyncSession,
        threshold: float = 10.0
    ) -> List[MaterialModel]:
        """
        Holt alle Materialien mit niedrigem Bestand.

        Args:
            db: Datenbank-Session
            threshold: Bestandsschwellwert

        Returns:
            Liste von Material-Objekten mit niedrigem Bestand
        """
        result = await db.execute(
            select(MaterialModel)
            .filter(MaterialModel.stock <= threshold)
            .order_by(MaterialModel.stock.asc())
        )
        return result.scalars().all()

    @staticmethod
    async def calculate_total_stock_value(
        db: AsyncSession
    ) -> float:
        """
        Berechnet den Gesamtwert aller Materialien im Lager.

        Args:
            db: Datenbank-Session

        Returns:
            Gesamtwert (Summe von stock * unit_price)
        """
        materials = await MaterialService.get_materials(db, skip=0, limit=10000)
        total_value = sum(m.stock * m.unit_price for m in materials)
        return total_value
