"""
Customer Self-Service Portal — public endpoint, NO authentication required.

Customers can look up their order or repair status using only their
reference number (order ID, REP-..., or RE-...) and their email address.
No PII, no financial data, and no design details are ever returned.

Rate limiting: 10 requests/minute per IP to prevent enumeration attacks.
Token caching: one-time lookup tokens (1 hour TTL) stored in Redis for
email-link style access ("click here to check your status").
"""

import hashlib
import json
import logging
import secrets
import time
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from goldsmith_erp.core.pubsub import get_redis_client
from goldsmith_erp.db.models import (
    Customer,
    Invoice,
    Order,
    OrderStatusEnum,
    RepairJob,
    RepairJobStatus,
)
from goldsmith_erp.db.session import get_db

logger = logging.getLogger(__name__)

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)

# ─── Token settings ────────────────────────────────────────────────────────────
_TOKEN_TTL_SECONDS = 3600  # 1 hour
_TOKEN_PREFIX = "portal_token:"

# ─── German status labels ──────────────────────────────────────────────────────
_ORDER_STATUS_LABELS: dict[str, str] = {
    OrderStatusEnum.DRAFT: "Entwurf",
    OrderStatusEnum.NEW: "Neu",
    OrderStatusEnum.CONFIRMED: "Bestaetigt",
    OrderStatusEnum.IN_PROGRESS: "In Bearbeitung",
    OrderStatusEnum.WAITING_FOR_FITTING: "Wartet auf Anprobe",
    OrderStatusEnum.FITTING_DONE: "Anprobe abgeschlossen",
    OrderStatusEnum.READY_FOR_SETTING: "Bereit zur Fassung",
    OrderStatusEnum.QUALITY_CHECK: "Qualitaetskontrolle",
    OrderStatusEnum.COMPLETED: "Fertig",
    OrderStatusEnum.DELIVERED: "Abgeholt",
}

# Pipeline steps for orders — index = step number (1-based)
_ORDER_PIPELINE: list[str] = [
    "Auftragseingang",
    "Bestaetigung",
    "In Bearbeitung",
    "Qualitaetskontrolle",
    "Abholbereit",
    "Abgeholt",
]

_ORDER_STATUS_STEP: dict[str, int] = {
    OrderStatusEnum.DRAFT: 1,
    OrderStatusEnum.NEW: 1,
    OrderStatusEnum.CONFIRMED: 2,
    OrderStatusEnum.IN_PROGRESS: 3,
    OrderStatusEnum.WAITING_FOR_FITTING: 3,
    OrderStatusEnum.FITTING_DONE: 3,
    OrderStatusEnum.READY_FOR_SETTING: 3,
    OrderStatusEnum.QUALITY_CHECK: 4,
    OrderStatusEnum.COMPLETED: 5,
    OrderStatusEnum.DELIVERED: 6,
}

_REPAIR_STATUS_LABELS: dict[str, str] = {
    RepairJobStatus.RECEIVED: "Eingang",
    RepairJobStatus.DIAGNOSED: "Diagnose abgeschlossen",
    RepairJobStatus.QUOTED: "Angebot erstellt",
    RepairJobStatus.APPROVED: "Reparatur genehmigt",
    RepairJobStatus.IN_REPAIR: "In Reparatur",
    RepairJobStatus.QUALITY_CHECK: "Qualitaetskontrolle",
    RepairJobStatus.READY: "Abholbereit",
    RepairJobStatus.PICKED_UP: "Abgeholt",
    RepairJobStatus.CANCELLED: "Storniert",
}

_REPAIR_PIPELINE: list[str] = [
    "Eingang",
    "Diagnose",
    "Angebot",
    "Reparatur",
    "Qualitaetskontrolle",
    "Abholbereit",
    "Abgeholt",
]

_REPAIR_STATUS_STEP: dict[str, int] = {
    RepairJobStatus.RECEIVED: 1,
    RepairJobStatus.DIAGNOSED: 2,
    RepairJobStatus.QUOTED: 3,
    RepairJobStatus.APPROVED: 3,
    RepairJobStatus.IN_REPAIR: 4,
    RepairJobStatus.QUALITY_CHECK: 5,
    RepairJobStatus.READY: 6,
    RepairJobStatus.PICKED_UP: 7,
    RepairJobStatus.CANCELLED: 0,
}


# ─── Schemas ───────────────────────────────────────────────────────────────────


class PortalLookupRequest(BaseModel):
    """Public lookup request — reference number + email."""

    reference_number: str = Field(
        ...,
        min_length=1,
        max_length=50,
        description="Auftragsnummer, Reparaturnummer (REP-...) oder Rechnungsnummer (RE-...)",
    )
    email: str = Field(
        ...,
        min_length=3,
        max_length=255,
        description="E-Mail-Adresse des Kunden",
    )


class PortalStatusResponse(BaseModel):
    """Public status response — no PII, no financial data."""

    reference_number: str
    record_type: str  # "order" | "repair"
    status_key: str
    status_label: str  # German label
    item_title: str
    current_step: int
    total_steps: int
    step_label: str
    pipeline_labels: list[str]
    estimated_completion: Optional[str] = None  # ISO date string or None
    is_complete: bool
    lookup_token: Optional[str] = None  # Only present on initial lookup response


# ─── Internal helpers ──────────────────────────────────────────────────────────


def _normalize_email(email: str) -> str:
    """Lowercase and strip email for comparison."""
    return email.strip().lower()


def _anonymize_reference(reference: str) -> str:
    """Return a truncated hash for safe logging."""
    return hashlib.sha256(reference.encode()).hexdigest()[:8]


async def _store_token(token: str, payload: dict) -> None:
    """Store a lookup token in Redis with 1-hour TTL."""
    try:
        async with get_redis_client() as redis:
            await redis.setex(
                f"{_TOKEN_PREFIX}{token}",
                _TOKEN_TTL_SECONDS,
                json.dumps(payload),
            )
    except Exception as exc:
        # Redis unavailable — token-based access will not work, but direct
        # lookup still works.  Log but do not fail the request.
        logger.warning(
            "Failed to store portal token in Redis",
            extra={"error": str(exc)},
        )


async def _fetch_token(token: str) -> Optional[dict]:
    """Retrieve a lookup token payload from Redis, or None if missing/expired."""
    try:
        async with get_redis_client() as redis:
            raw = await redis.get(f"{_TOKEN_PREFIX}{token}")
            if raw:
                return json.loads(raw)
    except Exception as exc:
        logger.warning(
            "Failed to fetch portal token from Redis",
            extra={"error": str(exc)},
        )
    return None


def _build_order_response(order: Order, token: Optional[str] = None) -> PortalStatusResponse:
    status_key = order.status.value if order.status else OrderStatusEnum.NEW.value
    status_label = _ORDER_STATUS_LABELS.get(order.status, "Unbekannt")
    current_step = _ORDER_STATUS_STEP.get(order.status, 1)
    total_steps = len(_ORDER_PIPELINE)

    # Step label is the pipeline name for the current step (1-based index)
    step_index = max(0, min(current_step - 1, total_steps - 1))
    step_label = _ORDER_PIPELINE[step_index]

    is_complete = order.status in (OrderStatusEnum.COMPLETED, OrderStatusEnum.DELIVERED)

    estimated: Optional[str] = None
    if order.deadline and not is_complete:
        estimated = order.deadline.strftime("%d.%m.%Y")

    item_title = order.title or f"Auftrag #{order.id}"

    return PortalStatusResponse(
        reference_number=str(order.id),
        record_type="order",
        status_key=status_key,
        status_label=status_label,
        item_title=item_title,
        current_step=current_step,
        total_steps=total_steps,
        step_label=step_label,
        pipeline_labels=_ORDER_PIPELINE,
        estimated_completion=estimated,
        is_complete=is_complete,
        lookup_token=token,
    )


def _build_repair_response(repair: RepairJob, token: Optional[str] = None) -> PortalStatusResponse:
    status_key = repair.status.value if repair.status else RepairJobStatus.RECEIVED.value
    status_label = _REPAIR_STATUS_LABELS.get(repair.status, "Unbekannt")
    current_step = _REPAIR_STATUS_STEP.get(repair.status, 1)
    total_steps = len(_REPAIR_PIPELINE)

    if repair.status == RepairJobStatus.CANCELLED:
        # Cancelled — show step 0
        current_step = 0
        step_label = "Storniert"
    else:
        step_index = max(0, min(current_step - 1, total_steps - 1))
        step_label = _REPAIR_PIPELINE[step_index]

    is_complete = repair.status in (RepairJobStatus.PICKED_UP, RepairJobStatus.CANCELLED)

    estimated: Optional[str] = None
    if repair.estimated_completion_date and not is_complete:
        estimated = repair.estimated_completion_date.strftime("%d.%m.%Y")

    item_title = f"Reparatur {repair.repair_number} — {repair.item_description[:60]}"
    if len(repair.item_description) > 60:
        item_title += "..."

    return PortalStatusResponse(
        reference_number=repair.repair_number,
        record_type="repair",
        status_key=status_key,
        status_label=status_label,
        item_title=item_title,
        current_step=current_step,
        total_steps=total_steps,
        step_label=step_label,
        pipeline_labels=_REPAIR_PIPELINE,
        estimated_completion=estimated,
        is_complete=is_complete,
        lookup_token=token,
    )


async def _lookup_by_reference(
    reference: str, email: str, db: AsyncSession
) -> Optional[PortalStatusResponse]:
    """
    Resolve a reference number to an order, repair, or invoice.

    Returns None if not found or email does not match.
    Never raises — caller decides how to handle the miss.
    """
    normalized_email = _normalize_email(email)
    ref = reference.strip()

    # ── Repair: REP- prefix ────────────────────────────────────────────────────
    if ref.upper().startswith("REP-"):
        result = await db.execute(
            select(RepairJob)
            .options(selectinload(RepairJob.customer))
            .where(RepairJob.repair_number == ref.upper())
            .where(RepairJob.is_deleted.is_(False))
        )
        repair = result.scalar_one_or_none()
        if repair and repair.customer:
            customer_email = _normalize_email(repair.customer.email or "")
            if customer_email == normalized_email:
                return _build_repair_response(repair)
        return None

    # ── Invoice: RE- prefix ────────────────────────────────────────────────────
    if ref.upper().startswith("RE-"):
        result = await db.execute(
            select(Invoice)
            .options(
                selectinload(Invoice.customer),
                selectinload(Invoice.order),
            )
            .where(Invoice.invoice_number == ref.upper())
        )
        invoice = result.scalar_one_or_none()
        if invoice and invoice.customer:
            customer_email = _normalize_email(invoice.customer.email or "")
            if customer_email == normalized_email and invoice.order:
                # Re-use order status builder — invoice points to an order
                order = invoice.order
                # Eagerly load the customer on the order if needed
                if not order.customer:
                    order_result = await db.execute(
                        select(Order)
                        .options(selectinload(Order.customer))
                        .where(Order.id == order.id)
                    )
                    order = order_result.scalar_one_or_none() or order
                return _build_order_response(order)
        return None

    # ── Order: numeric ID ──────────────────────────────────────────────────────
    if ref.isdigit():
        order_id = int(ref)
        result = await db.execute(
            select(Order)
            .options(selectinload(Order.customer))
            .where(Order.id == order_id)
            .where(Order.is_deleted.is_(False))
        )
        order = result.scalar_one_or_none()
        if order and order.customer:
            customer_email = _normalize_email(order.customer.email or "")
            if customer_email == normalized_email:
                return _build_order_response(order)
        return None

    return None


# ─── Endpoints ─────────────────────────────────────────────────────────────────


@router.post(
    "/lookup",
    response_model=PortalStatusResponse,
    summary="Auftragsstatus pruefen (oeffentlich)",
    description=(
        "Oeffentlicher Endpunkt — kein Login erforderlich. "
        "Kunden geben ihre Auftragsnummer und E-Mail-Adresse an, "
        "um den aktuellen Status zu erhalten. "
        "Rate-limit: 10 Anfragen pro Minute pro IP."
    ),
)
@limiter.limit("10/minute")
async def portal_lookup(
    request: Request,
    body: PortalLookupRequest,
    db: AsyncSession = Depends(get_db),
) -> PortalStatusResponse:
    """
    Look up order or repair status by reference number + email.

    NEVER returns PII, financial data, or design details.
    Rate-limited at 10/minute per IP to prevent enumeration.
    """
    # Structured log without PII
    logger.info(
        "Portal lookup attempt",
        extra={
            "ref_hash": _anonymize_reference(body.reference_number),
            "path": request.url.path,
        },
    )

    data = await _lookup_by_reference(body.reference_number, body.email, db)

    if data is None:
        # Return a generic 404 — do not reveal whether the reference number
        # exists to prevent partial enumeration.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Auftrag nicht gefunden. Bitte pruefen Sie Auftragsnummer und E-Mail-Adresse.",
        )

    # Generate a one-time token for email-link access
    token = secrets.token_urlsafe(32)
    payload = {
        "reference_number": body.reference_number,
        "email": _normalize_email(body.email),
        "issued_at": int(time.time()),
    }
    await _store_token(token, payload)

    data.lookup_token = token
    return data


@router.get(
    "/status/{token}",
    response_model=PortalStatusResponse,
    summary="Auftragsstatus per Token (E-Mail-Link)",
    description=(
        "Gibt den Auftragsstatus anhand eines einmaligen Lookup-Tokens zurueck. "
        "Tokens werden vom /lookup-Endpunkt generiert und sind 1 Stunde gueltig. "
        "Nützlich fuer E-Mail-Links: 'Klicken Sie hier, um Ihren Status zu sehen'."
    ),
)
async def portal_status_by_token(
    token: str,
    db: AsyncSession = Depends(get_db),
) -> PortalStatusResponse:
    """
    Return status for a previously-issued lookup token.

    The token encodes the reference number and email so the customer
    does not have to re-enter them when following an email link.
    """
    payload = await _fetch_token(token)
    if payload is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Token ungueltig oder abgelaufen. Bitte suchen Sie erneut nach Ihrem Auftrag.",
        )

    data = await _lookup_by_reference(
        payload["reference_number"], payload["email"], db
    )
    if data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Auftrag nicht gefunden.",
        )

    # Do not include a new token on token-based lookups (use the same link again)
    return data
