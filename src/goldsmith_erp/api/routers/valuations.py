# src/goldsmith_erp/api/routers/valuations.py
"""
Insurance valuation certificate endpoints (Wertgutachten).

POST /valuations               — Create certificate (from order or manual)
GET  /valuations               — List certificates (optional filters)
GET  /valuations/{id}          — Certificate detail
GET  /valuations/{id}/pdf      — Download PDF

SECURITY: Valuation data (appraised_value) is financial data.
- GOLDSMITH and ADMIN can create and view certificates.
- ADMIN only can export (download) PDFs via VALUATION_EXPORT permission.
  (In practice goldsmiths also need to print them — the router grants PDF
  download to VALUATION_VIEW holders so goldsmiths can hand them to customers.
  Change to VALUATION_EXPORT to restrict to ADMIN only if required.)
- Customer PII in the PDF is handled by accessing the Customer object
  through the existing encrypted field pipeline — no raw PII is logged.
"""

import logging
import types
from io import BytesIO
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, validator
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.api.deps import get_current_user
from goldsmith_erp.core.config import settings
from goldsmith_erp.core.permissions import Permission, require_permission
from goldsmith_erp.db.models import User
from goldsmith_erp.db.session import get_db
from goldsmith_erp.services.pdf_service import PDFService
from goldsmith_erp.services.valuation_service import ValuationService

router = APIRouter()
logger = logging.getLogger(__name__)


# ============================================================================
# Pydantic schemas
# ============================================================================


class ValuationCreate(BaseModel):
    """Request body for creating a valuation certificate directly."""

    order_id: int = Field(..., gt=0)
    customer_id: int = Field(..., gt=0)
    item_description: str = Field(..., min_length=5, max_length=2000)
    metal_type: Optional[str] = Field(None, max_length=100)
    metal_weight_g: Optional[float] = Field(None, gt=0)
    metal_purity: Optional[str] = Field(None, max_length=20)
    gemstones_description: Optional[str] = Field(None, max_length=2000)
    appraised_value: float = Field(..., gt=0, description="Gutachtenwert in EUR")
    goldsmith_name: str = Field(..., min_length=2, max_length=200)
    goldsmith_qualification: Optional[str] = Field(None, max_length=200)


class ValuationCreateFromOrder(BaseModel):
    """
    Request body for auto-filling a certificate from an existing order.

    The service reads order.title, order.alloy, order.metal_type,
    order.actual_weight_g, and linked Gemstone rows.  The goldsmith
    provides the appraised value and their own credentials.
    """

    appraised_value: float = Field(..., gt=0, description="Gutachtenwert in EUR")
    goldsmith_name: str = Field(..., min_length=2, max_length=200)
    goldsmith_qualification: Optional[str] = Field(
        None,
        max_length=200,
        description="z.B. 'Goldschmiedemeister' oder 'Staatlich anerkannter Gutachter'",
    )


class ValuationRead(BaseModel):
    """Response schema for a valuation certificate."""

    id: int
    certificate_number: str
    order_id: int
    customer_id: int
    item_description: str
    metal_type: Optional[str]
    metal_weight_g: Optional[float]
    metal_purity: Optional[str]
    gemstones_description: Optional[str]
    appraised_value: float
    valuation_date: str
    valid_until: str
    goldsmith_name: str
    goldsmith_qualification: Optional[str]
    pdf_path: Optional[str]
    created_at: str
    created_by: Optional[int]

    class Config:
        from_attributes = True

    @classmethod
    def from_orm_model(cls, obj) -> "ValuationRead":
        def _dt(val) -> str:
            return val.isoformat() if val else ""

        return cls(
            id=obj.id,
            certificate_number=obj.certificate_number,
            order_id=obj.order_id,
            customer_id=obj.customer_id,
            item_description=obj.item_description,
            metal_type=obj.metal_type,
            metal_weight_g=obj.metal_weight_g,
            metal_purity=obj.metal_purity,
            gemstones_description=obj.gemstones_description,
            appraised_value=obj.appraised_value,
            valuation_date=_dt(obj.valuation_date),
            valid_until=_dt(obj.valid_until),
            goldsmith_name=obj.goldsmith_name,
            goldsmith_qualification=obj.goldsmith_qualification,
            pdf_path=obj.pdf_path,
            created_at=_dt(obj.created_at),
            created_by=obj.created_by,
        )


# ============================================================================
# Endpoints
# ============================================================================


@router.get(
    "/valuations",
    response_model=List[ValuationRead],
    summary="Wertgutachten auflisten",
)
@require_permission(Permission.VALUATION_VIEW)
async def list_valuations(
    order_id: Optional[int] = Query(None, gt=0, description="Nach Auftrag filtern"),
    customer_id: Optional[int] = Query(None, gt=0, description="Nach Kunde filtern"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[ValuationRead]:
    """
    Liste aller Wertgutachten.

    Finanzielle Daten — nur GOLDSMITH und ADMIN haben Zugriff.
    Alle Zugriffe werden im Audit-Log erfasst.
    """
    logger.info(
        "Valuation certificate list accessed",
        extra={
            "user_id": current_user.id,
            "filter_order_id": order_id,
            "filter_customer_id": customer_id,
        },
    )
    certs = await ValuationService.list_certificates(
        db,
        order_id=order_id,
        customer_id=customer_id,
        skip=skip,
        limit=limit,
    )
    return [ValuationRead.from_orm_model(c) for c in certs]


@router.post(
    "/valuations",
    response_model=ValuationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Wertgutachten erstellen",
)
@require_permission(Permission.VALUATION_CREATE)
async def create_valuation(
    body: ValuationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ValuationRead:
    """
    Erstellt ein neues Wertgutachten mit manuell eingegebenen Daten.

    Fuer automatisches Befllen aus einem bestehenden Auftrag:
    POST /orders/{order_id}/valuations
    """
    try:
        cert = await ValuationService.create_certificate(
            db=db,
            order_id=body.order_id,
            customer_id=body.customer_id,
            item_description=body.item_description,
            appraised_value=body.appraised_value,
            goldsmith_name=body.goldsmith_name,
            created_by_id=current_user.id,
            metal_type=body.metal_type,
            metal_weight_g=body.metal_weight_g,
            metal_purity=body.metal_purity,
            gemstones_description=body.gemstones_description,
            goldsmith_qualification=body.goldsmith_qualification,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    logger.info(
        "Valuation certificate created via API",
        extra={
            "certificate_id": cert.id,
            "certificate_number": cert.certificate_number,
            "user_id": current_user.id,
            # Never log appraised_value
        },
    )
    return ValuationRead.from_orm_model(cert)


@router.post(
    "/orders/{order_id}/valuations",
    response_model=ValuationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Wertgutachten aus Auftrag erstellen",
)
@require_permission(Permission.VALUATION_CREATE)
async def create_valuation_from_order(
    order_id: int,
    body: ValuationCreateFromOrder,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ValuationRead:
    """
    Erstellt ein Wertgutachten und befuellt Metal- und Edelsteinfelder
    automatisch aus den Auftragsdaten.

    Der Goldschmied gibt nur den Gutachtenwert und seine Qualifikation an.
    """
    try:
        cert = await ValuationService.create_from_order(
            db=db,
            order_id=order_id,
            appraised_value=body.appraised_value,
            goldsmith_name=body.goldsmith_name,
            created_by_id=current_user.id,
            goldsmith_qualification=body.goldsmith_qualification,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))

    logger.info(
        "Valuation certificate auto-created from order",
        extra={
            "certificate_id": cert.id,
            "certificate_number": cert.certificate_number,
            "order_id": order_id,
            "user_id": current_user.id,
        },
    )
    return ValuationRead.from_orm_model(cert)


@router.get(
    "/valuations/{certificate_id}",
    response_model=ValuationRead,
    summary="Wertgutachten Detailansicht",
)
@require_permission(Permission.VALUATION_VIEW)
async def get_valuation(
    certificate_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ValuationRead:
    cert = await ValuationService.get_certificate(db, certificate_id)
    if cert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Wertgutachten {certificate_id} nicht gefunden",
        )
    logger.info(
        "Valuation certificate detail accessed",
        extra={"certificate_id": certificate_id, "user_id": current_user.id},
    )
    return ValuationRead.from_orm_model(cert)


@router.get(
    "/valuations/{certificate_id}/pdf",
    summary="Wertgutachten als PDF herunterladen",
    response_class=StreamingResponse,
)
@require_permission(Permission.VALUATION_VIEW)
async def download_valuation_pdf(
    certificate_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """
    Generiert das Wertgutachten als PDF und liefert es direkt aus.

    Das PDF wird on-the-fly erzeugt (kein Caching).  Der Dateiname
    enthaelt die Zertifikatsnummer fuer einfache Ablage.
    Finanzielle Daten — Zugriff wird im Audit-Log erfasst.
    """
    cert = await ValuationService.get_certificate(db, certificate_id)
    if cert is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Wertgutachten {certificate_id} nicht gefunden",
        )

    logger.info(
        "Valuation certificate PDF downloaded",
        extra={
            "certificate_id": certificate_id,
            "certificate_number": cert.certificate_number,
            "user_id": current_user.id,
        },
    )

    # Build a minimal customer-like namespace for the PDF renderer.
    # We only expose non-PII fields to the PDF layer here; the ORM Customer
    # object already has encrypted fields — just pass it directly.
    customer = cert.customer

    # Build a simple namespace so the PDF renderer can call getattr()
    customer_ns = types.SimpleNamespace(
        name=(
            f"{getattr(customer, 'first_name', '')} "
            f"{getattr(customer, 'last_name', '')}"
        ).strip() or "Kunde",
        address=getattr(customer, "street", None),
        city=(
            f"{getattr(customer, 'postal_code', '') or ''} "
            f"{getattr(customer, 'city', '') or ''}"
        ).strip() or None,
    )

    pdf_bytes = PDFService.render_valuation_certificate_pdf(
        certificate=cert,
        customer=customer_ns,
        workshop_name=settings.WORKSHOP_NAME,
    )

    filename = f"Wertgutachten_{cert.certificate_number}.pdf"
    return StreamingResponse(
        BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length": str(len(pdf_bytes)),
        },
    )
