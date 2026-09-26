"""Art. 15 export helpers: the customer-linked tables beyond the core record.

GDPR-05 (docs/review/2026-09-25/07-gdpr-privacy.md): the export used to omit
invoices, quotes, Altgold, valuations, repairs, customer updates, §649 cost
changes, photos and the order history. ``collect_export_sections`` loads all
of them (one query per table, related rows eager-loaded with
``selectinload``) and returns plain dicts matching
``models/gdpr_export.py``. What is withheld and why is documented there.

Only called from the ADMIN-only export endpoint; nothing here logs PII.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any, Dict, List, Optional, Sequence

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from goldsmith_erp.db.models import (
    Consultation,
    CostChangeRequest,
    CustomerAuditLog,
    CustomerUpdate,
    GDPRRequest,
    Invoice,
    OrderEvent,
    OrderPhoto,
    Quote,
    RepairJob,
    RepairPhoto,
    ScrapGold,
    ValuationCertificate,
)

# Art. 15 Abs. 1 lit. a-h DSGVO. Static text; the workshop's name and
# address are filled in by whoever sends the answer letter (placeholders
# match docs/legal/DATENSCHUTZHINWEISE-KUNDEN.md).
EXPORT_META: Dict[str, Any] = {
    "controller": "[Name und Anschrift der Goldschmiede]",
    "purposes": [
        "Beratung, Angebot und Durchführung von Anfertigungs- und "
        "Reparaturaufträgen (Art. 6 Abs. 1 lit. b DSGVO)",
        "Rechnungsstellung und gesetzliche Aufbewahrung (Art. 6 Abs. 1 lit. c "
        "DSGVO; §147 AO, §257 HGB, §14b UStG)",
        "Altgold-Ankauf und Identifizierung nach dem Geldwäschegesetz "
        "(Art. 6 Abs. 1 lit. c DSGVO; GwG)",
        "Allergien und Unverträglichkeiten nur mit ausdrücklicher Einwilligung "
        "(Art. 9 Abs. 2 lit. a DSGVO)",
    ],
    "recipients": [
        "Steuerberater (eigener Verantwortlicher)",
        "E-Mail-Anbieter der Goldschmiede (Auftragsverarbeiter, nur beim "
        "Versand von Kundeninformationen)",
        "Betreiber/Hosting des Systems (Auftragsverarbeiter)",
        "Finanzbehörden und Prüfstellen nur auf gesetzlicher Grundlage",
    ],
    "third_country_transfer": "keine",
    "storage_period": (
        "Rechnungen und Buchungsbelege 8-10 Jahre, Handelsbriefe und "
        "angenommene Angebote 6 Jahre, übrige Daten bis zum Ende der "
        "Geschäftsbeziehung bzw. der Gewährleistung; Details im Löschkonzept "
        "der Goldschmiede"
    ),
    "rights": [
        "Berichtigung (Art. 16)",
        "Löschung (Art. 17)",
        "Einschränkung der Verarbeitung (Art. 18)",
        "Datenübertragbarkeit (Art. 20)",
        "Widerspruch (Art. 21)",
        "Widerruf einer Einwilligung mit Wirkung für die Zukunft (Art. 7 Abs. 3)",
        "Beschwerde bei einer Datenschutz-Aufsichtsbehörde (Art. 77)",
    ],
    "source": "Angaben der betroffenen Person selbst",
    "automated_decision_making": "keine (Art. 22 DSGVO)",
    "withheld": [
        "Entwurfsarbeit der Goldschmiede (Auftragsbeschreibung, "
        "Beratungsnotizen, Skizzen, Diagnosenotizen) — Art. 15 Abs. 4 DSGVO",
        "Namen und Kennungen von Mitarbeitenden — Rechte Dritter",
        "Interne Kalkulation (Materialkosten, Stundensätze, Marge)",
    ],
    "copies_on_request": (
        "Fotos, Rechnungs-/Angebots-PDFs und Unterschriften sind hier als "
        "Metadaten aufgeführt; eine Kopie wird auf Wunsch ausgehändigt "
        "(Art. 15 Abs. 3 DSGVO)"
    ),
}


def _iso(value: Optional[Any]) -> Optional[str]:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return None


def _enum(value: Optional[Any]) -> Optional[str]:
    if value is None:
        return None
    return str(getattr(value, "value", value))


def _num(value: Optional[Any]) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


def _line_items(items: Sequence[Any]) -> List[Dict[str, Any]]:
    return [
        {
            "description": item.description,
            "quantity": float(item.quantity or 0),
            "unit_price": float(item.unit_price or 0),
            "total": float(item.total or 0),
        }
        for item in items
    ]


async def _invoices(db: AsyncSession, customer_id: int) -> List[Dict[str, Any]]:
    rows: Sequence[Any] = (
        (
            await db.execute(
                select(Invoice)
                .options(selectinload(Invoice.line_items))
                .where(Invoice.customer_id == customer_id)
                .order_by(Invoice.issue_date.asc())
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": inv.id,
            "invoice_number": inv.invoice_number,
            "order_id": inv.order_id,
            "status": _enum(inv.status),
            "issue_date": _iso(inv.issue_date),
            "due_date": _iso(inv.due_date),
            "paid_date": _iso(inv.paid_date),
            "issued_at": _iso(inv.issued_at),
            "subtotal": float(inv.subtotal or 0),
            "tax_rate": float(inv.tax_rate or 0),
            "tax_amount": float(inv.tax_amount or 0),
            "total": float(inv.total or 0),
            "payment_method": inv.payment_method,
            "line_items": _line_items(inv.line_items),
        }
        for inv in rows
    ]


async def _quotes(db: AsyncSession, customer_id: int) -> List[Dict[str, Any]]:
    rows: Sequence[Any] = (
        (
            await db.execute(
                select(Quote)
                .options(selectinload(Quote.line_items))
                .where(Quote.customer_id == customer_id)
                .order_by(Quote.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": q.id,
            "quote_number": q.quote_number,
            "order_id": q.order_id,
            "status": _enum(q.status),
            "valid_until": _iso(q.valid_until),
            "approved_at": _iso(q.approved_at),
            "rejected_at": _iso(q.rejected_at),
            "converted_at": _iso(q.converted_at),
            "subtotal": float(q.subtotal or 0),
            "tax_rate": float(q.tax_rate or 0),
            "tax_amount": float(q.tax_amount or 0),
            "total": float(q.total or 0),
            "customer_signature_present": bool(q.customer_signature_data),
            "created_at": _iso(q.created_at),
            "line_items": _line_items(q.line_items),
        }
        for q in rows
    ]


async def _scrap_gold(db: AsyncSession, customer_id: int) -> List[Dict[str, Any]]:
    rows: Sequence[Any] = (
        (
            await db.execute(
                select(ScrapGold)
                .options(selectinload(ScrapGold.items))
                .where(ScrapGold.customer_id == customer_id)
                .order_by(ScrapGold.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": sg.id,
            "order_id": sg.order_id,
            "status": _enum(sg.status),
            "total_fine_gold_g": _num(sg.total_fine_gold_g),
            "total_value_eur": _num(sg.total_value_eur),
            "gold_price_per_g": _num(sg.gold_price_per_g),
            "signed_at": _iso(sg.signed_at),
            "signature_present": bool(sg.signature_data),
            "receipt_pdf_present": bool(sg.receipt_pdf_path),
            # W2-16 (GwG identification duty, decision D-16): the seller's
            # own identification data, captured on purchases above the
            # threshold — it is the customer's data (Art. 15), not
            # workshop-internal, so it belongs in their export. The
            # internal "who checked it" staff reference (id_checked_by) is
            # deliberately omitted — it is our own audit trail, not theirs.
            "id_document_type": sg.id_document_type,
            "id_document_number": sg.id_document_number,
            "id_issuing_authority": sg.id_issuing_authority,
            "id_checked_at": _iso(sg.id_checked_at),
            "created_at": _iso(sg.created_at),
            "items": [
                {
                    "description": item.description,
                    "alloy": _enum(item.alloy),
                    "weight_g": float(item.weight_g or 0),
                    "fine_content_g": float(item.fine_content_g or 0),
                    "photo_present": bool(item.photo_path),
                }
                for item in sg.items
            ],
        }
        for sg in rows
    ]


async def _valuations(db: AsyncSession, customer_id: int) -> List[Dict[str, Any]]:
    rows: Sequence[Any] = (
        (
            await db.execute(
                select(ValuationCertificate)
                .where(ValuationCertificate.customer_id == customer_id)
                .order_by(ValuationCertificate.valuation_date.asc())
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": v.id,
            "certificate_number": v.certificate_number,
            "order_id": v.order_id,
            "item_description": v.item_description,
            "metal_type": v.metal_type,
            "metal_weight_g": _num(v.metal_weight_g),
            "metal_purity": v.metal_purity,
            "gemstones_description": v.gemstones_description,
            "appraised_value": _num(v.appraised_value),
            "valuation_date": _iso(v.valuation_date),
            "valid_until": _iso(v.valid_until),
            "pdf_present": bool(v.pdf_path),
        }
        for v in rows
    ]


async def _repairs(db: AsyncSession, customer_id: int) -> List[Any]:
    rows: Sequence[Any] = (
        (
            await db.execute(
                select(RepairJob)
                .options(selectinload(RepairJob.photos))
                .where(RepairJob.customer_id == customer_id)
                .order_by(RepairJob.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    return list(rows)


def _repair_dict(r: Any) -> Dict[str, Any]:
    return {
        "id": r.id,
        "repair_number": r.repair_number,
        "bag_number": r.bag_number,
        "item_description": r.item_description,
        "item_type": _enum(r.item_type),
        "metal_type": r.metal_type,
        "estimated_value": _num(r.estimated_value),
        "status": _enum(r.status),
        "estimated_cost": _num(r.estimated_cost),
        "actual_cost": _num(r.actual_cost),
        "estimated_completion_date": _iso(r.estimated_completion_date),
        "actual_completion_date": _iso(r.actual_completion_date),
        "customer_notified_at": _iso(r.customer_notified_at),
        "picked_up_at": _iso(r.picked_up_at),
        "created_at": _iso(r.created_at),
    }


async def _customer_updates(
    db: AsyncSession, order_ids: Sequence[int], repair_ids: Sequence[int]
) -> List[Dict[str, Any]]:
    if not order_ids and not repair_ids:
        return []
    rows: Sequence[Any] = (
        (
            await db.execute(
                select(CustomerUpdate)
                .where(
                    or_(
                        CustomerUpdate.order_id.in_(order_ids),
                        CustomerUpdate.repair_job_id.in_(repair_ids),
                    )
                )
                .order_by(CustomerUpdate.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": u.id,
            "order_id": u.order_id,
            "repair_job_id": u.repair_job_id,
            "kind": _enum(u.kind),
            "subject": u.subject,
            "body": u.body,
            "status": _enum(u.status),
            "delivery_method": _enum(u.delivery_method),
            "photo_count": len(u.photo_ids or []),
            "sent_at": _iso(u.sent_at),
            "created_at": _iso(u.created_at),
        }
        for u in rows
    ]


async def _cost_changes(
    db: AsyncSession, order_ids: Sequence[int]
) -> List[Dict[str, Any]]:
    if not order_ids:
        return []
    rows: Sequence[Any] = (
        (
            await db.execute(
                select(CostChangeRequest)
                .where(CostChangeRequest.order_id.in_(order_ids))
                .order_by(CostChangeRequest.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "id": c.id,
            "order_id": c.order_id,
            "quote_id": c.quote_id,
            "original_amount": float(c.original_amount or 0),
            "new_amount": float(c.new_amount or 0),
            "delta_percent": float(c.delta_percent or 0),
            "reason": c.reason,
            "status": _enum(c.status),
            "response_method": _enum(c.response_method),
            "response_evidence": c.response_evidence,
            "responded_at": _iso(c.responded_at),
            "created_at": _iso(c.created_at),
        }
        for c in rows
    ]


async def _photos(
    db: AsyncSession, order_ids: Sequence[int], repairs: Sequence[Any]
) -> List[Dict[str, Any]]:
    photos: List[Dict[str, Any]] = []
    if order_ids:
        order_photos: Sequence[Any] = (
            (
                await db.execute(
                    select(OrderPhoto)
                    .where(OrderPhoto.order_id.in_(order_ids))
                    .order_by(OrderPhoto.timestamp.asc())
                )
            )
            .scalars()
            .all()
        )
        photos.extend(
            {
                "id": str(p.id),
                "source": "order",
                "order_id": p.order_id,
                "repair_job_id": None,
                "phase": None,
                "taken_at": _iso(p.timestamp),
            }
            for p in order_photos
        )
    for repair in repairs:
        repair_photos: Sequence[RepairPhoto] = repair.photos
        photos.extend(
            {
                "id": str(p.id),
                "source": "repair",
                "order_id": None,
                "repair_job_id": repair.id,
                "phase": _enum(p.phase),
                "taken_at": _iso(p.timestamp),
            }
            for p in repair_photos
        )
    return photos


async def _order_events(
    db: AsyncSession, order_ids: Sequence[int]
) -> List[Dict[str, Any]]:
    if not order_ids:
        return []
    rows: Sequence[Any] = (
        (
            await db.execute(
                select(OrderEvent)
                .where(OrderEvent.order_id.in_(order_ids))
                .order_by(OrderEvent.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "order_id": e.order_id,
            "from_status": e.from_status,
            "to_status": e.to_status,
            "created_at": _iso(e.created_at),
        }
        for e in rows
    ]


async def _consultation_statements(
    db: AsyncSession, customer_id: int
) -> List[Dict[str, Any]]:
    rows: Sequence[Any] = (
        (
            await db.execute(
                select(Consultation)
                .where(Consultation.customer_id == customer_id)
                .order_by(Consultation.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "consultation_id": c.id,
            "wishes": c.wishes,
            "source_material": c.source_material,
        }
        for c in rows
        if c.wishes or c.source_material
    ]


async def _gdpr_requests(db: AsyncSession, customer_id: int) -> List[Dict[str, Any]]:
    rows: Sequence[Any] = (
        (
            await db.execute(
                select(GDPRRequest)
                .where(GDPRRequest.customer_id == customer_id)
                .order_by(GDPRRequest.requested_at.asc())
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "request_type": r.request_type,
            "status": r.status,
            "requested_at": _iso(r.requested_at),
            "completed_at": _iso(r.completed_at),
        }
        for r in rows
    ]


async def _access_log(db: AsyncSession, customer_id: int) -> List[Dict[str, Any]]:
    rows: Sequence[Any] = (
        (
            await db.execute(
                select(CustomerAuditLog)
                .where(CustomerAuditLog.customer_id == customer_id)
                .order_by(CustomerAuditLog.created_at.asc())
            )
        )
        .scalars()
        .all()
    )
    return [
        {
            "action": r.action,
            "entity": r.entity,
            "entity_id": r.entity_id,
            "timestamp": _iso(r.timestamp or r.created_at),
        }
        for r in rows
    ]


async def collect_export_sections(
    db: AsyncSession, customer_id: int, order_ids: Sequence[int]
) -> Dict[str, Any]:
    """Return the GDPR-05 export sections for one customer."""
    repairs = await _repairs(db, customer_id)
    repair_ids = [r.id for r in repairs]
    return {
        "invoices": await _invoices(db, customer_id),
        "quotes": await _quotes(db, customer_id),
        "scrap_gold": await _scrap_gold(db, customer_id),
        "valuations": await _valuations(db, customer_id),
        "repairs": [_repair_dict(r) for r in repairs],
        "customer_updates": await _customer_updates(db, order_ids, repair_ids),
        "cost_changes": await _cost_changes(db, order_ids),
        "photos": await _photos(db, order_ids, repairs),
        "order_events": await _order_events(db, order_ids),
        "consultation_statements": await _consultation_statements(db, customer_id),
        "gdpr_requests": await _gdpr_requests(db, customer_id),
        "access_log": await _access_log(db, customer_id),
        "meta": EXPORT_META,
    }
