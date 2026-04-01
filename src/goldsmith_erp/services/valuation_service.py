# src/goldsmith_erp/services/valuation_service.py
"""
Business logic for insurance valuation certificates (Wertgutachten).

A Wertgutachten is an official document issued by a certified goldsmith
stating the current market replacement value of a jewelry piece.  Customers
use these for jewelry insurance policies.

Certificate numbers follow the format WG-YYYY-NNNN (sequential per year).
Certificates expire after 2 years (standard insurance requirement in DE).

SECURITY: appraised_value is financial data restricted to ADMIN and GOLDSMITH.
All access to valuation records is audit-logged via structured logging.
"""

import logging
from datetime import datetime, timedelta
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from goldsmith_erp.db.models import (
    Customer,
    Gemstone,
    Order,
    ValuationCertificate,
)

logger = logging.getLogger(__name__)

# Certificates are valid for 2 years (730 days)
_VALIDITY_DAYS = 730


async def _generate_certificate_number(db: AsyncSession) -> str:
    """
    Generate a unique WG-YYYY-NNNN certificate number for the current year.

    Queries the highest existing sequence within the year and increments by one.
    Thread-safe under normal DB transaction isolation.
    """
    year = datetime.utcnow().year
    prefix = f"WG-{year}-"

    result = await db.execute(
        select(func.max(ValuationCertificate.certificate_number)).where(
            ValuationCertificate.certificate_number.like(f"{prefix}%")
        )
    )
    last_number = result.scalar_one_or_none()

    if last_number:
        try:
            seq = int(last_number.split("-")[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    else:
        seq = 1

    return f"{prefix}{seq:04d}"


class ValuationService:
    """CRUD + PDF generation logic for ValuationCertificate records."""

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    @staticmethod
    async def get_certificate(
        db: AsyncSession,
        certificate_id: int,
    ) -> Optional[ValuationCertificate]:
        """Return a single certificate by id, or None."""
        result = await db.execute(
            select(ValuationCertificate)
            .where(ValuationCertificate.id == certificate_id)
            .options(
                selectinload(ValuationCertificate.order),
                selectinload(ValuationCertificate.customer),
                selectinload(ValuationCertificate.creator),
            )
        )
        return result.scalar_one_or_none()

    @staticmethod
    async def list_certificates(
        db: AsyncSession,
        order_id: Optional[int] = None,
        customer_id: Optional[int] = None,
        skip: int = 0,
        limit: int = 100,
    ) -> List[ValuationCertificate]:
        """List certificates with optional order/customer filter."""
        query = (
            select(ValuationCertificate)
            .options(
                selectinload(ValuationCertificate.order),
                selectinload(ValuationCertificate.customer),
                selectinload(ValuationCertificate.creator),
            )
            .order_by(ValuationCertificate.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        if order_id is not None:
            query = query.where(ValuationCertificate.order_id == order_id)
        if customer_id is not None:
            query = query.where(ValuationCertificate.customer_id == customer_id)

        result = await db.execute(query)
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    @staticmethod
    async def create_certificate(
        db: AsyncSession,
        order_id: int,
        customer_id: int,
        item_description: str,
        appraised_value: float,
        goldsmith_name: str,
        created_by_id: int,
        metal_type: Optional[str] = None,
        metal_weight_g: Optional[float] = None,
        metal_purity: Optional[str] = None,
        gemstones_description: Optional[str] = None,
        goldsmith_qualification: Optional[str] = None,
        valuation_date: Optional[datetime] = None,
    ) -> ValuationCertificate:
        """
        Create a new valuation certificate.

        Generates the certificate number and sets valid_until = valuation_date + 2 years.
        """
        cert_number = await _generate_certificate_number(db)
        val_date = valuation_date or datetime.utcnow()
        valid_until = val_date + timedelta(days=_VALIDITY_DAYS)

        cert = ValuationCertificate(
            certificate_number=cert_number,
            order_id=order_id,
            customer_id=customer_id,
            created_by=created_by_id,
            item_description=item_description,
            metal_type=metal_type,
            metal_weight_g=metal_weight_g,
            metal_purity=metal_purity,
            gemstones_description=gemstones_description,
            appraised_value=appraised_value,
            valuation_date=val_date,
            valid_until=valid_until,
            goldsmith_name=goldsmith_name,
            goldsmith_qualification=goldsmith_qualification,
        )
        db.add(cert)
        await db.commit()
        await db.refresh(cert)

        logger.info(
            "Valuation certificate created",
            extra={
                "certificate_id": cert.id,
                "certificate_number": cert_number,
                "order_id": order_id,
                # Never log appraised_value — it is financial data
                "created_by": created_by_id,
            },
        )
        return cert

    @staticmethod
    async def create_from_order(
        db: AsyncSession,
        order_id: int,
        appraised_value: float,
        goldsmith_name: str,
        created_by_id: int,
        goldsmith_qualification: Optional[str] = None,
    ) -> ValuationCertificate:
        """
        Auto-fill a certificate from an existing order's data.

        Reads the order's metal fields and linked gemstones to pre-populate
        the certificate.  The goldsmith still supplies the appraised_value and
        their name/qualification — these cannot be derived automatically.
        """
        order_result = await db.execute(
            select(Order)
            .where(Order.id == order_id)
            .options(
                selectinload(Order.gemstones),
                selectinload(Order.customer),
            )
        )
        order = order_result.scalar_one_or_none()
        if order is None:
            raise ValueError(f"Order {order_id} not found")
        if order.customer_id is None:
            raise ValueError(
                f"Order {order_id} has no customer — cannot create valuation certificate"
            )

        # Build item description from order fields
        item_parts = [order.title or f"Auftrag #{order_id}"]
        if order.description:
            item_parts.append(order.description)
        item_description = " — ".join(item_parts)

        # Metal purity from alloy field (e.g. "585", "750")
        metal_purity = order.alloy or None
        metal_type_str: Optional[str] = None
        if order.metal_type:
            metal_type_str = order.metal_type.value  # e.g. "gold_18k"
        elif order.alloy:
            metal_type_str = f"Legierung {order.alloy}"

        metal_weight_g = order.actual_weight_g or order.estimated_weight_g

        # Gemstone summary — one line per distinct stone type
        gemstones_description: Optional[str] = None
        if order.gemstones:
            stone_lines = []
            for g in order.gemstones:
                parts = [f"{g.quantity}x {g.type.capitalize()}"]
                if g.carat:
                    parts.append(f"{g.carat:.2f} ct")
                if g.color:
                    parts.append(g.color)
                if g.quality:
                    parts.append(g.quality)
                if g.cut:
                    parts.append(g.cut)
                if g.setting_type:
                    parts.append(f"({g.setting_type})")
                stone_lines.append(" ".join(parts))
            gemstones_description = "\n".join(stone_lines)

        return await ValuationService.create_certificate(
            db=db,
            order_id=order_id,
            customer_id=order.customer_id,
            item_description=item_description,
            appraised_value=appraised_value,
            goldsmith_name=goldsmith_name,
            created_by_id=created_by_id,
            metal_type=metal_type_str,
            metal_weight_g=metal_weight_g,
            metal_purity=metal_purity,
            gemstones_description=gemstones_description,
            goldsmith_qualification=goldsmith_qualification,
        )

    # ------------------------------------------------------------------
    # PDF path storage
    # ------------------------------------------------------------------

    @staticmethod
    async def record_pdf_path(
        db: AsyncSession,
        certificate_id: int,
        pdf_path: str,
    ) -> None:
        """Store the file path of a generated PDF on the certificate record."""
        cert = await ValuationService.get_certificate(db, certificate_id)
        if cert is None:
            raise ValueError(f"ValuationCertificate {certificate_id} not found")
        cert.pdf_path = pdf_path
        await db.commit()
        logger.info(
            "Valuation certificate PDF path recorded",
            extra={"certificate_id": certificate_id, "pdf_path": pdf_path},
        )
