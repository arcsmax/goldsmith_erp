"""Invoice a repair (ARCH-02, ARCH phase 5, ADR-2026-09-25-jobs-spine).

A repair is billed through the same :class:`InvoiceService` path as an
order: gap-free RE number, §14 UStG seller block and Leistungsdatum, VAT
default from the Werkstatt-Stammdaten, immutable snapshot and the
one-live-invoice rule (per job, ``uq_invoices_one_active_per_job``). The
invoice has no ``order_id``; ``job_id`` names the repair's job.

Net price: the repair's agreed price, ``actual_cost`` after completion,
else the ``estimated_cost`` of the accepted Kostenvoranschlag (see the ADR
open item on net vs gross).
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, List, Optional, cast

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from goldsmith_erp.core.errors import (
    ConflictError,
    DomainValidationError,
    NotFoundError,
)
from goldsmith_erp.db.models import Invoice as InvoiceModel
from goldsmith_erp.db.models import (
    InvoiceLineType,
    InvoiceStatus,
    RepairJob,
    RepairJobStatus,
)
from goldsmith_erp.db.models import User as UserModel
from goldsmith_erp.models.invoice import InvoiceLineItemCreate, RepairInvoiceCreate
from goldsmith_erp.services.invoice_service import (
    InvoiceService,
    InvoiceSubject,
    _log_financial_access,
    _role,
    _to_cents,
)
from goldsmith_erp.services.job_service import JobService
from goldsmith_erp.services.workshop_settings_service import WorkshopSettingsService

logger = logging.getLogger(__name__)

#: A repair can be invoiced once the work is done.
INVOICEABLE_REPAIR_STATUSES = frozenset(
    {RepairJobStatus.READY, RepairJobStatus.PICKED_UP}
)


def repair_net_price(repair: Any) -> Decimal:
    """Agreed NET price of ``repair`` or 422 when none was recorded."""
    for value in (repair.actual_cost, repair.estimated_cost):
        if value is not None and Decimal(str(value)) > 0:
            return _to_cents(value)
    raise DomainValidationError(
        f"Reparatur {repair.repair_number} hat keinen vereinbarten Preis "
        "(tatsächliche Kosten oder Kostenvoranschlag). Bitte zuerst einen "
        "Preis erfassen.",
        code="invoice.repair_price_missing",
    )


def repair_line_items(repair: Any) -> List[InvoiceLineItemCreate]:
    return [
        InvoiceLineItemCreate(
            line_type=InvoiceLineType.LABOR,
            description=f"Reparatur {repair.repair_number}",
            quantity=Decimal("1"),
            unit_price=repair_net_price(repair),
        )
    ]


async def _load_repair(db: AsyncSession, repair_id: int) -> Optional[RepairJob]:
    result = await db.execute(
        select(RepairJob)
        .options(selectinload(RepairJob.customer))
        .where(RepairJob.id == repair_id, RepairJob.is_deleted.is_(False))
    )
    return result.scalar_one_or_none()


def _check_invoiceable(repair: Any) -> None:
    if repair.status not in INVOICEABLE_REPAIR_STATUSES:
        raise DomainValidationError(
            "Rechnung kann erst für eine fertige oder abgeholte Reparatur "
            f"erstellt werden. Aktueller Status: {repair.status.value}",
            code="invoice.repair_not_completed",
        )
    if repair.customer_id is None or repair.customer is None:
        raise DomainValidationError(
            "Für eine Rechnung muss der Reparatur ein Kunde zugeordnet sein "
            "(Rechnungsempfänger, §14 UStG).",
            code="invoice.repair_customer_missing",
        )


async def _has_live_invoice(db: AsyncSession, job_id: Optional[int]) -> bool:
    if job_id is None:
        return False
    existing = await db.execute(
        select(InvoiceModel.id).where(
            InvoiceModel.job_id == job_id,
            InvoiceModel.status != InvoiceStatus.CANCELLED,
            InvoiceModel.cancels_invoice_id.is_(None),
        )
    )
    return existing.scalar_one_or_none() is not None


def _duplicate(repair: Any) -> ConflictError:
    return ConflictError(
        f"Für Reparatur {repair.repair_number} existiert bereits eine aktive "
        "Rechnung",
        code="invoice.duplicate_active",
    )


class RepairInvoiceService:
    """Static-method service; every method takes the AsyncSession first."""

    @staticmethod
    async def create_invoice_for_repair(
        db: AsyncSession,
        repair_id: int,
        invoice_in: RepairInvoiceCreate,
        current_user: UserModel,
    ) -> InvoiceModel:
        """Create the Rechnung for a finished repair (404 / 409 / 422)."""
        repair: Any = await _load_repair(db, repair_id)
        if repair is None:
            raise NotFoundError(
                f"Reparaturauftrag #{repair_id} nicht gefunden",
                code="invoice.repair_not_found",
            )
        _check_invoiceable(repair)
        if await _has_live_invoice(db, repair.job_id):
            raise _duplicate(repair)

        lines = repair_line_items(repair) + list(invoice_in.additional_line_items or [])
        tax_rate = await WorkshopSettingsService.vat_rate_for_new_invoice(
            db, float(invoice_in.tax_rate) if invoice_in.tax_rate is not None else None
        )
        seller = await WorkshopSettingsService.seller_block(db)
        totals = InvoiceService.calculate_totals(lines, tax_rate)
        subject = InvoiceSubject(
            order_id=None,
            customer_id=int(repair.customer_id),
            customer=repair.customer,
            title=f"Reparatur {repair.repair_number}",
            completed_at=repair.actual_completion_date or repair.picked_up_at,
            reference=str(repair.repair_number),
            reference_label="Reparaturnummer:",
        )

        async def sync_job(session: AsyncSession) -> Any:
            return await JobService.sync_repair(session, repair)

        try:
            invoice = await InvoiceService._persist_new_invoice(
                db,
                invoice_in,
                subject,
                current_user,
                lines,
                totals,
                tax_rate,
                seller,
                [],
                sync_job=sync_job,
            )
        except IntegrityError as exc:
            logger.warning(
                "Concurrent invoice create for the same repair rejected",
                extra={"repair_id": repair_id},
            )
            raise _duplicate(repair) from exc

        _log_financial_access(
            action="created",
            invoice_id=cast(int, invoice.id),
            user_id=cast(int, current_user.id),
            user_role=_role(current_user),
            extra={
                "invoice_number": invoice.invoice_number,
                "repair_id": repair_id,
                "job_id": invoice.job_id,
                "total": totals["total"],
            },
        )
        created = await InvoiceService.get_invoice(db, int(invoice.id), current_user)
        if created is None:  # pragma: no cover - just committed
            raise NotFoundError("Rechnung nicht gefunden", code="invoice.not_found")
        return created


__all__ = ["INVOICEABLE_REPAIR_STATUSES", "RepairInvoiceService", "repair_net_price"]
