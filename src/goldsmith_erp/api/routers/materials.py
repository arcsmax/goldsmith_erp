# src/goldsmith_erp/api/routers/materials.py

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from pydantic import BaseModel

from goldsmith_erp.api.deps import get_current_user
from goldsmith_erp.db.session import get_db
from goldsmith_erp.db.models import User as UserModel
from goldsmith_erp.models.material import MaterialCreate, MaterialRead, MaterialUpdate, MaterialWithStock
from goldsmith_erp.services.material_service import MaterialService

router = APIRouter()


# ==================== PYDANTIC SCHEMAS ====================

class StockAdjustment(BaseModel):
    """Schema für Bestandsanpassungen."""
    quantity: float
    operation: str = "add"  # "add" oder "subtract"


class StockValueResponse(BaseModel):
    """Response für Gesamtbestandswert."""
    total_value: float
    currency: str = "EUR"


# ==================== MATERIAL CRUD ENDPOINTS ====================

@router.get("/", response_model=List[MaterialRead])
async def list_materials(
    skip: int = 0,
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    """
    Alle Materialien auflisten.

    - **Authentifizierung erforderlich**
    - Gibt eine Liste aller Materialien zurück (mit Pagination)
    - Sortiert alphabetisch nach Namen

    **Use Case**: Übersicht über alle verfügbaren Materialien.
    """
    materials = await MaterialService.get_materials(db, skip, limit)
    return materials


@router.post("/", response_model=MaterialRead, status_code=status.HTTP_201_CREATED)
async def create_material(
    material_in: MaterialCreate,
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    """
    Neues Material anlegen.

    - **Authentifizierung erforderlich**
    - Erstellt ein neues Material im System
    - Name muss eindeutig sein

    **Use Case**: Goldschmied fügt neues Edelmetall oder Edelstein hinzu.
    """
    # Prüfen ob Material mit diesem Namen bereits existiert
    existing_material = await MaterialService.get_material_by_name(db, material_in.name)
    if existing_material:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Material with name '{material_in.name}' already exists"
        )

    # Material erstellen
    material = await MaterialService.create_material(db, material_in)
    return material


@router.get("/{material_id}", response_model=MaterialRead)
async def get_material(
    material_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    """
    Material über ID abrufen.

    - **Authentifizierung erforderlich**
    - Gibt Details eines spezifischen Materials zurück

    **Use Case**: Details zu einem bestimmten Material anzeigen.
    """
    material = await MaterialService.get_material_by_id(db, material_id)
    if not material:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Material not found"
        )
    return material


@router.put("/{material_id}", response_model=MaterialRead)
async def update_material(
    material_id: int,
    material_in: MaterialUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    """
    Material aktualisieren.

    - **Authentifizierung erforderlich**
    - Aktualisiert Preis, Bestand, Name oder Beschreibung
    - Nur gesetzte Felder werden aktualisiert

    **Use Case**: Preis anpassen, Bestand korrigieren, Beschreibung ändern.
    """
    # Prüfen ob neuer Name bereits existiert (falls geändert)
    if material_in.name:
        material = await MaterialService.get_material_by_id(db, material_id)
        if material and material_in.name != material.name:
            existing_material = await MaterialService.get_material_by_name(db, material_in.name)
            if existing_material:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Material with name '{material_in.name}' already exists"
                )

    # Material aktualisieren
    updated_material = await MaterialService.update_material(db, material_id, material_in)
    if not updated_material:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Material not found"
        )

    return updated_material


@router.delete("/{material_id}")
async def delete_material(
    material_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    """
    Material löschen.

    - **Authentifizierung erforderlich**
    - Löscht Material permanent aus der Datenbank
    - ACHTUNG: Kann nicht rückgängig gemacht werden!

    **Use Case**: Material wird nicht mehr verwendet und soll entfernt werden.
    """
    result = await MaterialService.delete_material(db, material_id)
    if not result["success"]:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=result["message"]
        )

    return result


# ==================== STOCK MANAGEMENT ENDPOINTS ====================

@router.post("/{material_id}/adjust-stock", response_model=MaterialRead)
async def adjust_material_stock(
    material_id: int,
    adjustment: StockAdjustment,
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    """
    Bestand eines Materials anpassen.

    - **Authentifizierung erforderlich**
    - Fügt Bestand hinzu oder zieht ab
    - operation: "add" oder "subtract"

    **Use Cases:**
    - Wareneingang: operation="add"
    - Materialverbrauch: operation="subtract"
    """
    try:
        material = await MaterialService.adjust_stock(
            db,
            material_id,
            adjustment.quantity,
            adjustment.operation
        )
        if not material:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Material not found"
            )
        return material
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )


@router.get("/low-stock/alert", response_model=List[MaterialWithStock])
async def get_low_stock_materials(
    threshold: float = 10.0,
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    """
    Materialien mit niedrigem Bestand anzeigen.

    - **Authentifizierung erforderlich**
    - Gibt alle Materialien zurück, deren Bestand <= threshold
    - Standard-Schwellwert: 10.0
    - Sortiert nach Bestand (aufsteigend)

    **Use Case**: Warnung bei niedrigem Lagerbestand, Nachbestellungen planen.
    """
    materials = await MaterialService.get_low_stock_materials(db, threshold)

    # Konvertiere zu MaterialWithStock mit Wertberechnung
    materials_with_value = [
        MaterialWithStock.from_material(m) for m in materials
    ]

    return materials_with_value


@router.get("/analytics/stock-value", response_model=StockValueResponse)
async def get_total_stock_value(
    db: AsyncSession = Depends(get_db),
    current_user: UserModel = Depends(get_current_user)
):
    """
    Gesamtwert aller Materialien im Lager berechnen.

    - **Authentifizierung erforderlich**
    - Berechnet: Summe(Bestand × Preis) für alle Materialien
    - Nützlich für Bilanzierung und Reporting

    **Use Case**: Lagerwert für Buchhaltung ermitteln.
    """
    total_value = await MaterialService.calculate_total_stock_value(db)
    return StockValueResponse(total_value=total_value)
