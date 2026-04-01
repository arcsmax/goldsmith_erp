"""API Router for Scrap Gold (Altgold) management."""
import io
import logging
import uuid
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.api.deps import get_current_user
from goldsmith_erp.core.config import settings
from goldsmith_erp.core.permissions import Permission, require_permission
from goldsmith_erp.db.models import Customer, ScrapGoldItem as ScrapGoldItemModel, User
from goldsmith_erp.db.session import get_db
from goldsmith_erp.models.scrap_gold import (
    AlloyCalculation,
    ALLOY_RATIOS,
    ScrapGoldCreate,
    ScrapGoldItemCreate,
    ScrapGoldItemRead,
    ScrapGoldRead,
    ScrapGoldSignRequest,
)
from goldsmith_erp.services.pdf_service import PDFService
from goldsmith_erp.services.scrap_gold_service import ScrapGoldService

logger = logging.getLogger(__name__)

router = APIRouter()

# Upload directory for scrap-gold item photos (relative to process cwd / project root)
_UPLOAD_ROOT = Path("./uploads/scrap-gold")


def _detect_image_extension(header: bytes) -> Optional[str]:
    """
    Return the canonical file extension for an allowed image type by
    inspecting magic bytes.

    Supports JPEG, PNG, and WEBP.  Returns None when the header does not
    match any of those types.
    """
    if header[:3] == b"\xff\xd8\xff":
        return "jpg"
    if header[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    # WEBP: bytes 0-3 == RIFF  AND  bytes 8-12 == WEBP
    if header[:4] == b"RIFF" and len(header) >= 12 and header[8:12] == b"WEBP":
        return "webp"
    return None


@router.get("/orders/{order_id}/scrap-gold", response_model=Optional[ScrapGoldRead])
@require_permission(Permission.ORDER_VIEW)
async def get_scrap_gold(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Altgold-Eintrag fuer einen Auftrag abrufen."""
    return await ScrapGoldService.get_for_order(db, order_id)


@router.post("/orders/{order_id}/scrap-gold", response_model=ScrapGoldRead, status_code=201)
@require_permission(Permission.ORDER_EDIT)
async def create_scrap_gold(
    order_id: int,
    data: ScrapGoldCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Neuen Altgold-Eintrag fuer einen Auftrag anlegen."""
    existing = await ScrapGoldService.get_for_order(db, order_id)
    if existing:
        raise HTTPException(status_code=409, detail="Altgold-Eintrag existiert bereits fuer diesen Auftrag")
    data.order_id = order_id
    scrap_gold = await ScrapGoldService.create(db, current_user.id, data)
    return await ScrapGoldService.get_by_id(db, scrap_gold.id)


@router.post("/scrap-gold/{scrap_gold_id}/items", response_model=ScrapGoldItemRead, status_code=201)
@require_permission(Permission.ORDER_EDIT)
async def add_item(
    scrap_gold_id: int,
    item_data: ScrapGoldItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Position zum Altgold-Eintrag hinzufuegen."""
    scrap_gold = await ScrapGoldService.get_by_id(db, scrap_gold_id)
    if not scrap_gold:
        raise HTTPException(status_code=404, detail="Altgold-Eintrag nicht gefunden")
    return await ScrapGoldService.add_item(db, scrap_gold_id, item_data)


@router.delete("/scrap-gold/{scrap_gold_id}/items/{item_id}", status_code=204)
@require_permission(Permission.ORDER_EDIT)
async def remove_item(
    scrap_gold_id: int,
    item_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Position aus Altgold-Eintrag entfernen."""
    deleted = await ScrapGoldService.remove_item(db, scrap_gold_id, item_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Position nicht gefunden")


@router.post(
    "/scrap-gold/{scrap_gold_id}/items/{item_id}/photo",
    response_model=ScrapGoldItemRead,
    status_code=200,
)
@require_permission(Permission.ORDER_EDIT)
async def upload_item_photo(
    scrap_gold_id: int,
    item_id: int,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Foto fuer eine Altgold-Position hochladen.

    Akzeptiert JPEG, PNG und WEBP (Validierung per Magic Bytes).
    Speichert die Datei unter uploads/scrap-gold/{scrap_gold_id}/{item_id}_{uuid}.{ext},
    aktualisiert ScrapGoldItem.photo_path und gibt die aktualisierte Position zurueck.
    """
    # Verify the item belongs to this scrap gold record
    result = await db.execute(
        select(ScrapGoldItemModel).where(
            ScrapGoldItemModel.id == item_id,
            ScrapGoldItemModel.scrap_gold_id == scrap_gold_id,
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(status_code=404, detail="Position nicht gefunden")

    # Read the first 12 bytes for magic-byte validation (enough for all three types)
    header = await file.read(12)
    ext = _detect_image_extension(header)
    if ext is None:
        raise HTTPException(
            status_code=415,
            detail="Nur JPEG, PNG und WEBP Bilder sind erlaubt.",
        )

    # Read remainder and reassemble full content
    body = await file.read()
    full_content = header + body

    # Prepare destination directory and unique filename
    dest_dir = _UPLOAD_ROOT / str(scrap_gold_id)
    dest_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{item_id}_{uuid.uuid4().hex}.{ext}"
    dest_path = dest_dir / filename

    # Remove previous photo file to avoid orphaned files on disk
    if item.photo_path:
        old_file = Path(item.photo_path)
        if old_file.exists():
            try:
                old_file.unlink()
            except OSError:
                logger.warning(
                    "Could not delete old scrap-gold item photo",
                    extra={"path": str(old_file), "item_id": item_id},
                )

    dest_path.write_bytes(full_content)

    item.photo_path = str(dest_path)
    await db.commit()
    await db.refresh(item)

    logger.info(
        "Scrap gold item photo uploaded",
        extra={
            "scrap_gold_id": scrap_gold_id,
            "item_id": item_id,
            "path": str(dest_path),
            "user_id": current_user.id,
        },
    )
    return item


@router.get(
    "/scrap-gold/{scrap_gold_id}/items/{item_id}/photo",
    response_class=FileResponse,
)
@require_permission(Permission.ORDER_VIEW)
async def get_item_photo(
    scrap_gold_id: int,
    item_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Foto einer Altgold-Position ausliefern.

    Gibt die Datei als binaere FileResponse zurueck.
    """
    result = await db.execute(
        select(ScrapGoldItemModel).where(
            ScrapGoldItemModel.id == item_id,
            ScrapGoldItemModel.scrap_gold_id == scrap_gold_id,
        )
    )
    item = result.scalar_one_or_none()
    if item is None or not item.photo_path:
        raise HTTPException(status_code=404, detail="Kein Foto fuer diese Position vorhanden")

    photo_path = Path(item.photo_path)
    if not photo_path.exists():
        raise HTTPException(
            status_code=404,
            detail="Foto-Datei nicht gefunden. Bitte erneut hochladen.",
        )

    return FileResponse(
        path=str(photo_path),
        media_type="image/*",
        filename=photo_path.name,
    )


@router.post("/scrap-gold/{scrap_gold_id}/calculate", response_model=ScrapGoldRead)
@require_permission(Permission.ORDER_EDIT)
async def calculate_totals(
    scrap_gold_id: int,
    gold_price_per_g: Optional[float] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Feingold-Gehalt und Wert berechnen."""
    result = await ScrapGoldService.calculate_and_update(db, scrap_gold_id, gold_price_per_g)
    if not result:
        raise HTTPException(status_code=404, detail="Altgold-Eintrag nicht gefunden")
    return await ScrapGoldService.get_by_id(db, scrap_gold_id)


@router.post("/scrap-gold/{scrap_gold_id}/sign", response_model=ScrapGoldRead)
@require_permission(Permission.ORDER_EDIT)
async def sign_receipt(
    scrap_gold_id: int,
    sign_data: ScrapGoldSignRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Digitale Unterschrift des Kunden erfassen."""
    result = await ScrapGoldService.sign(db, scrap_gold_id, sign_data.signature_data)
    if not result:
        raise HTTPException(status_code=404, detail="Altgold-Eintrag nicht gefunden")
    return await ScrapGoldService.get_by_id(db, scrap_gold_id)


@router.get("/scrap-gold/alloy-calculator", response_model=AlloyCalculation)
@require_permission(Permission.ORDER_VIEW)
async def calculate_alloy(
    alloy: str,
    weight_g: float,
    current_user: User = Depends(get_current_user)
):
    """Feingold-Gehalt einer Legierung berechnen (Hilfstool)."""
    if alloy not in ALLOY_RATIOS:
        raise HTTPException(status_code=400, detail=f"Unbekannte Legierung: {alloy}")
    if weight_g <= 0:
        raise HTTPException(status_code=400, detail="Gewicht muss positiv sein")
    fine_content = ScrapGoldService.calculate_fine_content(alloy, weight_g)
    return AlloyCalculation(
        alloy=alloy,
        weight_g=weight_g,
        fine_content_g=fine_content,
        fine_content_percent=ALLOY_RATIOS[alloy] * 100
    )


@router.get("/scrap-gold/{scrap_gold_id}/receipt.pdf")
@require_permission(Permission.ORDER_VIEW)
async def download_scrap_gold_receipt(
    scrap_gold_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Ankaufsbeleg als PDF herunterladen (Download scrap gold receipt as PDF).

    Generates a German Ankaufsbeleg including all Altgold items, Feingold
    calculations, Gesamtwert, customer signature, and legal Geldwäschegesetz text.

    The signature image (if present) is embedded as a PNG in the PDF.

    Returns a streaming PDF response (application/pdf).
    """
    scrap_gold = await ScrapGoldService.get_by_id(db, scrap_gold_id)
    if not scrap_gold:
        raise HTTPException(
            status_code=404,
            detail=f"Altgold-Eintrag {scrap_gold_id} nicht gefunden",
        )

    customer_result = await db.execute(
        select(Customer).where(Customer.id == scrap_gold.customer_id)
    )
    customer = customer_result.scalar_one_or_none()
    if not customer:
        raise HTTPException(
            status_code=404,
            detail=f"Kunde {scrap_gold.customer_id} nicht gefunden",
        )

    class _CustomerAdapter:
        def __init__(self, c: Customer) -> None:
            self.name = f"{c.first_name} {c.last_name}".strip()
            self.address = c.street or ""
            city_parts = []
            if c.postal_code:
                city_parts.append(c.postal_code)
            if c.city:
                city_parts.append(c.city)
            self.city = " ".join(city_parts)
            self.phone = c.phone or ""

    # Extract base64 signature data (strip data URI prefix if present)
    sig_b64: Optional[str] = None
    raw_sig = getattr(scrap_gold, "signature_data", None)
    if raw_sig:
        if "," in raw_sig:
            sig_b64 = raw_sig.split(",", 1)[1]
        else:
            sig_b64 = raw_sig

    try:
        pdf_bytes = PDFService.render_scrap_gold_receipt(
            scrap_gold=scrap_gold,
            items=scrap_gold.items,
            customer=_CustomerAdapter(customer),
            workshop_name=settings.WORKSHOP_NAME,
            signature_base64=sig_b64,
        )
    except Exception:
        logger.exception(
            "PDF generation failed for scrap gold receipt",
            extra={"scrap_gold_id": scrap_gold_id},
        )
        raise HTTPException(
            status_code=500,
            detail="PDF-Generierung fehlgeschlagen. Bitte versuchen Sie es später erneut.",
        )

    filename = f"ankaufsbeleg_AG-{scrap_gold_id:05d}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )
