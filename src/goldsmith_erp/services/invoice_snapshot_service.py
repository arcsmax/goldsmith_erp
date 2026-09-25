# src/goldsmith_erp/services/invoice_snapshot_service.py
"""
Immutable invoice snapshot and frozen PDF (W1-10: GDPR-01 part a, BE-23).

Decision D-06 / assumption A4 (docs/review/2026-09-25/MASTER-FIX-PLAN.md):

1. **Snapshot at creation.** ``Invoice.snapshot`` holds a JSON document with
   everything the Rechnung shows: recipient (name + postal address only,
   minimum data), seller, order reference, lines, totals, service date. It
   is encrypted at rest (``EncryptedString``) because it carries the
   recipient's name and address.
2. **DRAFT follows its own edits, never the customer row.** While DRAFT,
   ``due_date``/``notes``/``payment_method`` edits are synced into the
   snapshot; the recipient block stays as captured.
3. **Frozen PDF at issue.** On DRAFT -> SENT (or DRAFT -> PAID) the PDF is
   rendered once from the snapshot; its bytes (base64, encrypted) and the
   SHA-256 of the raw bytes are stored, write-once. Every later download
   of a non-DRAFT invoice serves exactly these bytes after an integrity
   check.
4. **Legacy rows.** Invoices created before W1-10 get a snapshot from the
   then-current data (``backfilled: true``) — by the migration for issued
   invoices, lazily here for anything the migration did not cover.
5. **Seller (W2-04, §14 Abs. 4 Nr. 1/2 UStG).** The seller block is the
   Werkstatt-Stammdaten (``WorkshopSettingsService.seller_block``). A DRAFT
   picks up the current settings when it is issued (and in the DRAFT
   preview); from then on the frozen PDF never changes. Version 2 adds the
   seller address/tax/bank fields, ``service_date`` (Leistungsdatum) and,
   on a Stornorechnung, the cancelled invoice's number and date. Version 1
   snapshots still render (missing fields are simply not printed).

§14 Abs. 4 UStG / §146 Abs. 4 AO: an issued invoice must not change after
the fact; GDPR Art. 17(3)(b) lets it be retained after an erasure request.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from goldsmith_erp.core.config import settings
from goldsmith_erp.core.timeutil import ensure_utc
from goldsmith_erp.db.models import Customer as CustomerModel
from goldsmith_erp.db.models import Invoice as InvoiceModel
from goldsmith_erp.db.models import InvoiceLineItem as InvoiceLineItemModel
from goldsmith_erp.db.models import InvoiceStatus
from goldsmith_erp.db.models import Order as OrderModel
from goldsmith_erp.models._common import dec, money
from goldsmith_erp.services.pdf_service import PDFService
from goldsmith_erp.services.workshop_settings_service import (
    WorkshopSettingsService,
    missing_fields,
)

logger = logging.getLogger(__name__)

SNAPSHOT_VERSION = 2

# The ORM models use legacy ``Column()`` declarations, which mypy types as
# ``Column[...]`` rather than the runtime value; handle rows as ``Any``.
InvoiceRow = Any
CustomerRow = Any
OrderRow = Any
# Invoice-level fields a DRAFT may still change (InvoiceUpdate / mark-paid).
_DRAFT_EDITABLE_FIELDS = ("due_date", "notes", "payment_method")


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value is not None else None


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    return ensure_utc(datetime.fromisoformat(value)) if value else None


def _money(value: Any) -> float:
    return float(value) if value is not None else 0.0


def _recipient(customer: Optional[CustomerRow]) -> Dict[str, Optional[str]]:
    """Recipient block per §14 Abs. 4 Nr. 1 UStG: name and postal address."""
    if customer is None:
        return {
            "name": "",
            "company_name": None,
            "street": None,
            "postal_code": None,
            "city": None,
            "country": None,
        }
    return {
        "name": f"{customer.first_name or ''} {customer.last_name or ''}".strip(),
        "company_name": customer.company_name,
        "street": customer.street,
        "postal_code": customer.postal_code,
        "city": customer.city,
        "country": customer.country,
    }


def _legacy_seller() -> Dict[str, Any]:
    """Seller block when no settings were passed (pure callers, tests)."""
    return {"name": settings.WORKSHOP_NAME, "contact": settings.WORKSHOP_CONTACT}


def _service_date(invoice: InvoiceRow, order: Optional[OrderRow]) -> Optional[str]:
    """Leistungsdatum: explicit, else the order's completion, else issue date."""
    value = getattr(invoice, "service_date", None)
    if value is None and order is not None:
        value = getattr(order, "completed_at", None)
    return _iso(value or invoice.issue_date)


def _warn_if_seller_incomplete(invoice: InvoiceRow, seller: Dict[str, Any]) -> None:
    """Log loudly when an invoice is issued without the §14 seller data."""
    missing = missing_fields(seller)
    if missing:
        logger.warning(
            "Invoice issued with incomplete Werkstatt-Stammdaten (§14 UStG)",
            extra={"invoice_id": invoice.id, "missing_fields": missing},
        )


def _lines(line_items: Iterable[Any]) -> List[Dict[str, Any]]:
    return [
        {
            "line_type": getattr(item.line_type, "value", str(item.line_type)),
            "description": item.description,
            "quantity": _money(item.quantity),
            "unit_price": _money(item.unit_price),
            "total": _money(item.total),
        }
        for item in line_items
    ]


class InvoiceSnapshotService:
    """Build, persist and render the immutable invoice snapshot."""

    # ------------------------------------------------------------------
    # Building / (de)serialising
    # ------------------------------------------------------------------

    @staticmethod
    def build(
        invoice: InvoiceRow,
        line_items: Iterable[Any],
        customer: Optional[CustomerRow],
        order: Optional[OrderRow],
        *,
        scrap_gold_credit: Decimal | float = 0.0,
        backfilled: bool = False,
        seller: Optional[Dict[str, Any]] = None,
        cancels: Optional[InvoiceRow] = None,
        storno_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return the snapshot document for ``invoice`` (pure, no I/O).

        ``seller``: the Werkstatt-Stammdaten block (W2-04); ``cancels``: the
        original invoice when ``invoice`` is its Stornorechnung.
        """
        credit = float(scrap_gold_credit)
        total = _money(invoice.total)
        return {
            "version": SNAPSHOT_VERSION,
            "backfilled": backfilled,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "recipient": _recipient(customer),
            "seller": dict(seller) if seller is not None else _legacy_seller(),
            "invoice": {
                "invoice_number": invoice.invoice_number,
                "order_id": invoice.order_id,
                "order_title": order.title if order is not None else None,
                "issue_date": _iso(invoice.issue_date),
                "due_date": _iso(invoice.due_date),
                "service_date": _service_date(invoice, order),
                "notes": invoice.notes,
                "payment_method": invoice.payment_method,
                "cancels_invoice_number": (
                    cancels.invoice_number if cancels is not None else None
                ),
                "cancels_invoice_date": (
                    _iso(cancels.issue_date) if cancels is not None else None
                ),
                "storno_reason": storno_reason,
            },
            "lines": _lines(line_items),
            "totals": {
                "subtotal": _money(invoice.subtotal),
                "tax_rate": _money(invoice.tax_rate),
                "tax_amount": _money(invoice.tax_amount),
                "total": total,
                "scrap_gold_credit": credit,
                # Decimal, not float round() (BE-14); JSON keeps numbers.
                "amount_due": float(money(dec(invoice.total) - dec(scrap_gold_credit))),
            },
        }

    @staticmethod
    def dump(snapshot: Dict[str, Any]) -> str:
        return json.dumps(snapshot, ensure_ascii=False, sort_keys=True)

    @staticmethod
    def load(invoice: InvoiceRow) -> Optional[Dict[str, Any]]:
        """Decoded snapshot of ``invoice`` or None for a legacy row."""
        raw = invoice.snapshot
        if not raw:
            return None
        return dict(json.loads(raw))

    # ------------------------------------------------------------------
    # Persisting
    # ------------------------------------------------------------------

    @staticmethod
    def is_frozen(invoice: InvoiceRow) -> bool:
        return bool(invoice.issued_pdf)

    @staticmethod
    def sync_draft_fields(invoice: InvoiceRow) -> None:
        """Copy the invoice's own editable fields into a DRAFT snapshot.

        No-op once frozen: the issued document is write-once.
        """
        snapshot = InvoiceSnapshotService.load(invoice)
        if snapshot is None or InvoiceSnapshotService.is_frozen(invoice):
            return
        header = dict(snapshot["invoice"])
        header["due_date"] = _iso(invoice.due_date)
        header["notes"] = invoice.notes
        header["payment_method"] = invoice.payment_method
        invoice.snapshot = InvoiceSnapshotService.dump({**snapshot, "invoice": header})

    @staticmethod
    def refresh_draft_seller(invoice: InvoiceRow, seller: Dict[str, Any]) -> None:
        """Put the current seller block into a DRAFT snapshot (W2-04).

        No-op once frozen: an issued invoice keeps the seller it was issued
        with, whatever the settings say later.
        """
        snapshot = InvoiceSnapshotService.load(invoice)
        if snapshot is None or InvoiceSnapshotService.is_frozen(invoice):
            return
        invoice.snapshot = InvoiceSnapshotService.dump(
            {**snapshot, "seller": dict(seller)}
        )

    @staticmethod
    async def ensure_snapshot(db: AsyncSession, invoice: InvoiceRow) -> None:
        """Give a legacy invoice a snapshot from current data (backfilled).

        Only flushes; the caller owns the transaction.
        """
        if invoice.snapshot:
            return
        # Late import: invoice_service imports this module.
        from goldsmith_erp.services.invoice_service import (  # noqa: PLC0415
            InvoiceService,
        )

        customer = (
            await db.execute(
                select(CustomerModel).where(CustomerModel.id == invoice.customer_id)
            )
        ).scalar_one_or_none()
        order = (
            await db.execute(
                select(OrderModel).where(OrderModel.id == invoice.order_id)
            )
        ).scalar_one_or_none()
        # Explicit query: callers may hold the invoice without line_items
        # eagerly loaded (a lazy load would fail under AsyncSession).
        line_items = (
            (
                await db.execute(
                    select(InvoiceLineItemModel)
                    .where(InvoiceLineItemModel.invoice_id == invoice.id)
                    .order_by(InvoiceLineItemModel.id)
                )
            )
            .scalars()
            .all()
        )
        credit = (
            Decimal("0.00")
            if invoice.status == InvoiceStatus.CANCELLED
            else InvoiceService._scrap_gold_credit_amount(
                await InvoiceService._get_scrap_gold_credit(db, invoice.order_id)
            )
        )
        snapshot = InvoiceSnapshotService.build(
            invoice,
            line_items,
            customer,
            order,
            scrap_gold_credit=credit,
            backfilled=True,
            seller=await WorkshopSettingsService.seller_block(db),
        )
        invoice.snapshot = InvoiceSnapshotService.dump(snapshot)
        logger.warning(
            "Invoice snapshot backfilled from current data",
            extra={"invoice_id": invoice.id, "status": str(invoice.status)},
        )
        await db.flush()

    @staticmethod
    async def freeze(db: AsyncSession, invoice: InvoiceRow) -> None:
        """Render the PDF from the snapshot and store bytes + SHA-256 once.

        Only flushes; the caller owns the transaction. No-op when frozen.
        """
        if InvoiceSnapshotService.is_frozen(invoice):
            return
        await InvoiceSnapshotService.ensure_snapshot(db, invoice)
        InvoiceSnapshotService.sync_draft_fields(invoice)
        # W2-04: the issued document carries the seller data valid at issue.
        seller = await WorkshopSettingsService.seller_block(db)
        InvoiceSnapshotService.refresh_draft_seller(invoice, seller)
        _warn_if_seller_incomplete(invoice, seller)
        pdf_bytes = InvoiceSnapshotService.render(invoice)
        invoice.issued_pdf = base64.b64encode(pdf_bytes).decode("ascii")
        invoice.issued_pdf_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
        invoice.issued_at = datetime.now(timezone.utc)
        logger.info(
            "Invoice PDF frozen",
            extra={
                "audit": True,
                "invoice_id": invoice.id,
                "sha256": invoice.issued_pdf_sha256,
            },
        )
        await db.flush()

    # ------------------------------------------------------------------
    # Rendering / serving
    # ------------------------------------------------------------------

    @staticmethod
    def render(
        invoice: InvoiceRow, seller_override: Optional[Dict[str, Any]] = None
    ) -> bytes:
        """Render the invoice PDF from its snapshot (never the live customer).

        ``seller_override`` is used for the DRAFT preview only (current
        settings without writing them into the snapshot).
        """
        snapshot = InvoiceSnapshotService.load(invoice)
        if snapshot is None:
            raise ValueError(f"Invoice {invoice.id} has no snapshot")
        header = snapshot["invoice"]
        totals = snapshot["totals"]
        recipient = snapshot["recipient"]
        seller = dict(seller_override or snapshot.get("seller") or {})
        city = " ".join(
            part
            for part in (recipient.get("postal_code"), recipient.get("city"))
            if part
        )
        return PDFService.render_invoice_pdf(
            invoice=SimpleNamespace(
                invoice_number=header["invoice_number"],
                order_id=header["order_id"],
                issue_date=_parse_dt(header["issue_date"]),
                due_date=_parse_dt(header["due_date"]),
                service_date=_parse_dt(header.get("service_date")),
                notes=header["notes"],
                payment_method=header["payment_method"],
                cancels_invoice_number=header.get("cancels_invoice_number"),
                cancels_invoice_date=_parse_dt(header.get("cancels_invoice_date")),
                storno_reason=header.get("storno_reason"),
                subtotal=totals["subtotal"],
                tax_rate=totals["tax_rate"],
                tax_amount=totals["tax_amount"],
                total=totals["total"],
            ),
            customer=SimpleNamespace(
                name=recipient.get("name") or "",
                company_name=recipient.get("company_name") or "",
                address=recipient.get("street") or "",
                city=city,
                country=recipient.get("country") or "",
            ),
            line_items=[SimpleNamespace(**line) for line in snapshot["lines"]],
            workshop_name=seller.get("name") or settings.WORKSHOP_NAME,
            seller=seller,
            altgold_credit=float(totals.get("scrap_gold_credit") or 0.0),
        )

    @staticmethod
    async def pdf_for_download(db: AsyncSession, invoice: InvoiceRow) -> bytes:
        """PDF bytes for ``GET /invoices/{id}/pdf``.

        DRAFT: rendered fresh from the snapshot. Any other status: the frozen
        bytes; an issued legacy invoice without them (or a cancelled draft)
        is frozen on first download so every later download is identical.
        Commits only when it had to write.
        """
        if invoice.status == InvoiceStatus.DRAFT:
            if not invoice.snapshot:
                await InvoiceSnapshotService.ensure_snapshot(db, invoice)
                await db.commit()
            return InvoiceSnapshotService.render(
                invoice, seller_override=await WorkshopSettingsService.seller_block(db)
            )

        if not InvoiceSnapshotService.is_frozen(invoice):
            await InvoiceSnapshotService.freeze(db, invoice)
            await db.commit()
        return InvoiceSnapshotService.frozen_pdf(invoice)

    @staticmethod
    def frozen_pdf(invoice: InvoiceRow) -> bytes:
        """Return the frozen PDF bytes after verifying their SHA-256.

        Raises:
            ValueError: no frozen PDF, or the bytes do not match the hash.
        """
        if not invoice.issued_pdf:
            raise ValueError(f"Invoice {invoice.id} has no frozen PDF")
        pdf_bytes = base64.b64decode(invoice.issued_pdf)
        digest = hashlib.sha256(pdf_bytes).hexdigest()
        if digest != invoice.issued_pdf_sha256:
            logger.error(
                "Frozen invoice PDF failed SHA-256 integrity check",
                extra={"invoice_id": invoice.id},
            )
            raise ValueError(
                f"Invoice {invoice.id}: frozen PDF does not match its SHA-256"
            )
        return pdf_bytes
