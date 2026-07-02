"""Customer/CRM API Endpoints"""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from goldsmith_erp.api.deps import get_db
from goldsmith_erp.core.config import settings
from goldsmith_erp.core.idempotency import IdempotencyContext, get_idempotency_context
from goldsmith_erp.core.permissions import Permission
from goldsmith_erp.core.permissions import require_permission_dep as require_permission
from goldsmith_erp.db.models import Consultation
from goldsmith_erp.db.models import Customer as CustomerModel
from goldsmith_erp.db.models import CustomerNoGo, GDPRRequest, User
from goldsmith_erp.db.transaction import transactional
from goldsmith_erp.models.consultation import (
    NoGoConflict,
    NoGoCreate,
    NoGoRead,
    StyleProfileRead,
    StyleProfileUpdate,
)
from goldsmith_erp.models.customer import (
    CustomerCreate,
    CustomerListItem,
    CustomerRead,
    CustomerUpdate,
    CustomerWithOrders,
)
from goldsmith_erp.services.customer_service import CustomerService
from goldsmith_erp.services.file_erasure_service import FileErasureService
from goldsmith_erp.services.no_go_service import DuplicateNoGoError, NoGoService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/customers", tags=["customers"])


@router.get("/", response_model=List[CustomerListItem])
async def list_customers(
    skip: int = Query(0, ge=0, description="Number of records to skip"),
    limit: int = Query(100, ge=1, le=100, description="Max records to return"),
    search: Optional[str] = Query(None, description="Search in name, company, email"),
    customer_type: Optional[str] = Query(None, description="Filter by customer type"),
    is_active: Optional[bool] = Query(None, description="Filter by active status"),
    tag: Optional[str] = Query(None, description="Filter by tag"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.CUSTOMER_VIEW)),
):
    """
    List all customers with optional filtering.

    Permissions: Requires CUSTOMER_VIEW permission.
    """
    try:
        customers = await CustomerService.get_customers(
            db,
            skip=skip,
            limit=limit,
            search=search,
            customer_type=customer_type,
            is_active=is_active,
            tag=tag,
        )
        return customers

    except Exception as e:
        logger.error("Error listing customers", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to retrieve customers",
        )


@router.get("/search", response_model=List[CustomerListItem])
async def search_customers(
    q: str = Query(..., min_length=2, description="Search query"),
    limit: int = Query(10, ge=1, le=50, description="Max results"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.CUSTOMER_VIEW)),
):
    """
    Fast customer search for autocomplete.

    Searches by name, company name, and email.

    Permissions: Requires CUSTOMER_VIEW permission.
    """
    try:
        customers = await CustomerService.search_customers(db, q, limit=limit)
        return customers

    except Exception as e:
        logger.error("Error searching customers", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Search failed"
        )


@router.get("/top", response_model=List[dict])
async def get_top_customers(
    limit: int = Query(10, ge=1, le=50, description="Number of top customers"),
    by: str = Query("revenue", description="Sort by: revenue, orders, recent"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.CUSTOMER_VIEW)),
):
    """
    Get top customers by different criteria.

    - revenue: Customers who spent the most
    - orders: Customers with most orders
    - recent: Customers with most recent orders

    Permissions: Requires CUSTOMER_VIEW permission.
    """
    if by not in ["revenue", "orders", "recent"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid 'by' parameter. Must be: revenue, orders, or recent",
        )

    try:
        top_customers = await CustomerService.get_top_customers(db, limit=limit, by=by)
        return top_customers

    except Exception as e:
        logger.error("Error getting top customers", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get top customers",
        )


@router.get("/{customer_id}", response_model=CustomerRead)
async def get_customer(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.CUSTOMER_VIEW)),
):
    """
    Get customer by ID.

    Permissions: Requires CUSTOMER_VIEW permission.
    """
    customer = await CustomerService.get_customer(db, customer_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer {customer_id} not found",
        )
    return customer


@router.get("/{customer_id}/stats", response_model=dict)
async def get_customer_statistics(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.CUSTOMER_VIEW)),
):
    """
    Get customer statistics (order count, total spent, last order).

    Permissions: Requires CUSTOMER_VIEW permission.
    """
    # Verify customer exists
    customer = await CustomerService.get_customer(db, customer_id)
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer {customer_id} not found",
        )

    try:
        stats = await CustomerService.get_customer_stats(db, customer_id)
        return stats

    except Exception as e:
        logger.error(f"Error getting customer stats for {customer_id}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get customer statistics",
        )


@router.post("/", response_model=CustomerRead, status_code=status.HTTP_201_CREATED)
async def create_customer(
    customer_in: CustomerCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.CUSTOMER_CREATE)),
):
    """
    Create a new customer.

    Permissions: Requires CUSTOMER_CREATE permission.
    """
    try:
        customer = await CustomerService.create_customer(db, customer_in)
        return customer

    except ValueError as e:
        # Email already exists or validation error
        logger.warning(f"Customer creation validation error: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error("Error creating customer", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create customer",
        )


@router.patch("/{customer_id}", response_model=CustomerRead)
async def update_customer(
    customer_id: int,
    customer_update: CustomerUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.CUSTOMER_EDIT)),
):
    """
    Update customer information.

    Only provided fields will be updated.

    Permissions: Requires CUSTOMER_EDIT permission.
    """
    try:
        customer = await CustomerService.update_customer(
            db, customer_id, customer_update
        )
        if not customer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Customer {customer_id} not found",
            )
        return customer

    except ValueError as e:
        # Email conflict or validation error
        logger.warning(f"Customer update validation error: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error updating customer {customer_id}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update customer",
        )


@router.get("/{customer_id}/export", response_model=Dict[str, Any])
async def gdpr_export_customer(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.CUSTOMER_DELETE)),
):
    """
    GDPR Art. 15 — Export all personal data held for a customer.

    Returns the customer record along with all related data (orders,
    measurements, no-gos, style profile, consultation metadata) as a JSON
    object.  Access is restricted to ADMIN role (CUSTOMER_DELETE
    permission) because the export contains raw PII.

    Design-IP exclusion (V1.1, issue #14): consultation ``wishes``,
    ``notes``, ``source_material``, ``materials_discussed``, and
    consultation photos (sketches/reference images) are the GOLDSMITH's
    design work product, not the data subject's personal data — CLAUDE.md
    "Design IP" rule restricts them to GOLDSMITH/ADMIN access and excludes
    them from data exports without explicit consent. They are deliberately
    left out of the ``consultations`` list below; the ``design_data_excluded``
    flag documents that omission for anyone auditing a DPO response.

    Permissions: Requires CUSTOMER_DELETE permission (Admin only).
    """
    # Load customer with all relationships using selectinload to avoid N+1
    result = await db.execute(
        select(CustomerModel)
        .options(
            selectinload(CustomerModel.orders),
            selectinload(CustomerModel.measurements),
        )
        .filter(CustomerModel.id == customer_id)
    )
    customer = result.scalar_one_or_none()

    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer {customer_id} not found",
        )

    # No-gos and consultations have no back-populated collection on Customer
    # (see db/models.py — only the forward `customer = relationship(...)`
    # exists), so they can't ride along on the selectinload above. Query
    # them directly. Consultations are loaded without a limit/offset — the
    # shared ConsultationService.list_consultations() paginates (default
    # limit=100), which would silently truncate a legal Art. 15 export for
    # a customer with more than 100 consultations.
    no_gos_result = await db.execute(
        select(CustomerNoGo)
        .filter(CustomerNoGo.customer_id == customer_id)
        .order_by(CustomerNoGo.created_at.asc())
    )
    no_gos = list(no_gos_result.scalars().all())

    consultations_result = await db.execute(
        select(Consultation)
        .filter(Consultation.customer_id == customer_id)
        .order_by(Consultation.created_at.asc())
    )
    consultations = list(consultations_result.scalars().all())

    # Audit log — financial/PII data export must be traceable
    logger.info(
        "GDPR data export",
        extra={
            "audit": True,
            "action": "gdpr_export",
            "customer_id": customer_id,
            "user_id": current_user.id,
            "user_role": current_user.role.value,
        },
    )

    # Serialize all data — omit relationship proxy objects and SQLAlchemy state
    orders_data = []
    for order in customer.orders:
        orders_data.append(
            {
                "id": order.id,
                "status": order.status,
                "description": order.description,
                "price": float(order.price) if order.price is not None else None,
                "created_at": (
                    order.created_at.isoformat() if order.created_at else None
                ),
                "deadline": order.deadline.isoformat() if order.deadline else None,
            }
        )

    measurements_data = []
    for m in customer.measurements:
        measurements_data.append(
            {
                "id": m.id,
                "measurement_type": (
                    m.measurement_type.value if m.measurement_type else None
                ),
                "value": m.value,
                "unit": m.unit,
                "hand": m.hand.value if m.hand else None,
                "finger": m.finger.value if m.finger else None,
                "notes": m.notes,
                "measured_at": m.measured_at.isoformat() if m.measured_at else None,
            }
        )

    no_gos_data = []
    for ng in no_gos:
        no_gos_data.append(
            {
                "category": ng.category.value if ng.category else None,
                "value": ng.value,
                "note": ng.note,
                "created_at": ng.created_at.isoformat() if ng.created_at else None,
            }
        )

    # Consultations: financial (budget) + life-event (occasion) data of the
    # data subject. EXPLICITLY EXCLUDED — design-IP rule (CLAUDE.md,
    # binding): wishes, notes, source_material, materials_discussed, and
    # consultation photos/sketches. Those fields are the GOLDSMITH's design
    # work product, not the customer's personal data, and are business-
    # confidential — see the docstring above and the "design_data_excluded"
    # flag on the returned payload. Do NOT add those fields here without
    # updating both.
    consultations_data = []
    for c in consultations:
        consultations_data.append(
            {
                "id": c.id,
                "occasion": c.occasion.value if c.occasion else None,
                "occasion_date": (
                    c.occasion_date.isoformat() if c.occasion_date else None
                ),
                "budget_min": c.budget_min,
                "budget_max": c.budget_max,
                "status": c.status.value if c.status else None,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                "converted_order_id": c.converted_order_id,
                "converted_quote_id": c.converted_quote_id,
            }
        )

    return {
        "export_date": datetime.utcnow().isoformat(),
        "customer": {
            "id": customer.id,
            "first_name": customer.first_name,
            "last_name": customer.last_name,
            "company_name": customer.company_name,
            "email": customer.email,
            "phone": customer.phone,
            "mobile": customer.mobile,
            "street": customer.street,
            "city": customer.city,
            "postal_code": customer.postal_code,
            "country": customer.country,
            "customer_type": customer.customer_type,
            "source": customer.source,
            "notes": customer.notes,
            "tags": customer.tags,
            "ring_size": customer.ring_size,
            "chain_length_cm": customer.chain_length_cm,
            "bracelet_length_cm": customer.bracelet_length_cm,
            "allergies": customer.allergies,
            "preferences": customer.preferences,
            "birthday": customer.birthday.isoformat() if customer.birthday else None,
            "is_active": customer.is_active,
            "created_at": (
                customer.created_at.isoformat() if customer.created_at else None
            ),
        },
        "orders": orders_data,
        "measurements": measurements_data,
        "no_gos": no_gos_data,
        "style_profile": customer.style_profile or {},
        "consultations": consultations_data,
        # Machine-readable companion to the docstring's design-IP note —
        # keep true whenever consultations are exported without wishes/
        # notes/source_material/materials_discussed/photos.
        "design_data_excluded": True,
    }


# ---------------------------------------------------------------------------
# H10 helpers — GDPR request lifecycle tracking.
# ---------------------------------------------------------------------------


async def _write_pending_gdpr_request(
    db: AsyncSession,
    *,
    customer_id: int,
    performed_by: int,
    idem: IdempotencyContext,
) -> Optional[int]:
    """Write a ``gdpr_requests`` row with status='PENDING' in its own
    committed transaction. Returns the new row id, or None if the
    write failed (so the caller knows the terminal-state update will
    be skipped).

    The row is committed immediately — the subsequent main erasure
    transaction cannot roll it back, so every erasure attempt
    (including those that 404, 409, or fail inside scrub) appears in
    the Art. 30 Verzeichnis der Verarbeitungstätigkeiten.
    """
    try:
        pending = GDPRRequest(
            customer_id=customer_id,
            request_type="erasure",
            status="PENDING",
            requested_at=datetime.utcnow(),
            requested_by=performed_by,
            notes=(
                "Art. 17 erasure request received — awaiting "
                "scrub + file sweep."
                + (f" idempotency_key={idem.key}" if idem.key is not None else "")
            ),
        )
        db.add(pending)
        await db.commit()
        await db.refresh(pending)
        new_id = pending.id
        logger.info(
            "GDPR request PENDING row written",
            extra={
                "audit": True,
                "action": "gdpr_request_pending_written",
                "gdpr_request_id": new_id,
                "customer_id": customer_id,
                "user_id": performed_by,
            },
        )
        return new_id
    except Exception:  # noqa: BLE001 — pre-request audit is best-effort
        # Roll back so the caller's subsequent commit doesn't carry
        # stale state, then log and fall through — absence of an
        # Art. 30 row is separately visible in the failure log.
        try:
            await db.rollback()
        except Exception:  # noqa: BLE001
            pass
        logger.error(
            "Failed to write PENDING gdpr_requests row — request proceeds "
            "without Art. 30 entry",
            extra={
                "audit": True,
                "action": "gdpr_request_pending_write_failed",
                "customer_id": customer_id,
                "user_id": performed_by,
            },
            exc_info=True,
        )
        return None


async def _finalize_pending_gdpr_request(
    db: AsyncSession,
    *,
    gdpr_request_id: int,
    new_status: str,
    notes_suffix: Optional[str],
) -> None:
    """Update a PENDING ``gdpr_requests`` row to a terminal status.

    Commits on the existing session state. Caller may wrap in its own
    try/except so the original exception of the request is not masked
    if this update fails.
    """
    result = await db.execute(
        select(GDPRRequest).filter(GDPRRequest.id == gdpr_request_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        return
    row.status = new_status
    if new_status not in ("PENDING",):
        row.completed_at = datetime.utcnow()
    if notes_suffix:
        existing = row.notes or ""
        row.notes = f"{existing}\n{notes_suffix}" if existing else notes_suffix
    await db.commit()


@router.delete("/{customer_id}/gdpr-erase")
async def gdpr_erase_customer(
    response: Response,
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.CUSTOMER_DELETE)),
    # Slice 2 (M1) — accept the two idempotency headers. V1.1 does not yet
    # dedupe server-side (check_and_store_idempotency is a stub); the
    # context object is captured here so a retry in V1.1 still surfaces a
    # valid-UUID / within-window check before the expensive scrub runs.
    idem: IdempotencyContext = Depends(get_idempotency_context),
):
    """
    GDPR Art. 17 — Request erasure of all personal data for a customer.

    Lifecycle of the ``gdpr_requests`` Art. 30 row (H10 — audit-complete
    for DPO sign-off):

      * **PENDING** — written as a committed sub-transaction before any
        work. Guarantees that every erasure request — including those
        that 404, 409, or fail before scrub starts — appears in the
        Art. 30 Verzeichnis.
      * **completed** — scrub + file sweep both succeeded.
      * **PARTIAL_FILE_ERASURE** — DB scrub succeeded but at least one
        file deletion failed. Admin follow-up required.
      * **FAILED** — validation / not-found / unexpected exception.
        ``notes`` records the error type (never PII).

    Four things happen during the main transaction:
      1. Customer is deactivated (is_active=False) and scheduled for
         hard-delete after a 30-day grace period.
      2. Customer PII (names, phone, email) is scrubbed from related
         free-text fields — order descriptions, special instructions,
         order comments, time-entry notes, and the customer's own
         ``notes`` column (F1). See `CustomerService.scrub_customer_pii`
         for the full scope. Invoked with ``skip_gdpr_request=True``
         because this endpoint owns the Art. 30 row lifecycle.
      3. Filesystem artefacts referenced by customer-linked rows
         (generated PDFs, order/repair photos, scrap-gold receipts) are
         deleted by `FileErasureService.erase_customer_files` (O1/O2).
      4. ``customer_audit_logs`` rows are written and the
         ``gdpr_requests`` row promoted to its terminal status.

    Response status codes:
      - **200 OK** — every file erased cleanly.
      - **207 Multi-Status** — DB scrub succeeded but at least one file
        deletion failed. The response body reports the failing paths.
      - **404** — customer not found. GDPR request row written with
        ``status='FAILED'``, notes='customer_not_found'.
      - **409** — customer already scheduled for deletion. Row written
        with ``status='FAILED'``, notes='already_scheduled'.
      - **500** — unexpected error during scrub or file sweep; the
        main transaction is rolled back but the PENDING GDPR row is
        promoted to FAILED in a follow-up save.

    The gdpr-cleanup.sh cron job performs the actual customer-row
    hard-delete once the 30-day grace period has passed.

    Permissions: Requires CUSTOMER_DELETE permission (Admin only).
    """

    # Snapshot the admin user id in a plain int so subsequent rollbacks
    # of the session don't trigger an expired-attribute reload on
    # `current_user` (which happens under an exception path and
    # produces a confusing greenlet error).
    admin_user_id: int = int(current_user.id)

    # --- H10: PENDING request row written in its OWN transaction ---------
    # Written before ANY other work so validation / 404 / 409 paths also
    # appear in gdpr_requests. Committed immediately; the main erasure
    # transaction updates this row to the terminal status later.
    gdpr_request_id = await _write_pending_gdpr_request(
        db,
        customer_id=customer_id,
        performed_by=admin_user_id,
        idem=idem,
    )

    async def _finalize_gdpr_request(
        new_status: str, notes_suffix: Optional[str] = None
    ) -> None:
        """Update the PENDING row to a terminal status in a fresh txn.

        Uses a dedicated try/except so that a DB error during the
        audit-row update cannot mask the caller's original exception.
        """
        if gdpr_request_id is None:
            return
        try:
            await _finalize_pending_gdpr_request(
                db,
                gdpr_request_id=gdpr_request_id,
                new_status=new_status,
                notes_suffix=notes_suffix,
            )
        except Exception:  # noqa: BLE001 — audit row update is best-effort
            logger.error(
                "GDPR request finalisation failed — row remains PENDING",
                extra={
                    "audit": True,
                    "action": "gdpr_request_finalize_failed",
                    "gdpr_request_id": gdpr_request_id,
                    "customer_id": customer_id,
                    "attempted_status": new_status,
                },
                exc_info=True,
            )

    result = await db.execute(
        select(CustomerModel).filter(CustomerModel.id == customer_id)
    )
    customer = result.scalar_one_or_none()

    if not customer:
        await _finalize_gdpr_request("FAILED", notes_suffix="customer_not_found")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer {customer_id} not found",
        )

    if customer.deletion_scheduled_at is not None:
        await _finalize_gdpr_request("FAILED", notes_suffix="already_scheduled")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Löschung bereits angefordert. "
                f"Geplantes Löschdatum: {customer.deletion_scheduled_at.date().isoformat()}"
            ),
        )

    deletion_date = datetime.utcnow() + timedelta(days=30)
    file_erasure = FileErasureService(Path(settings.FILE_STORAGE_ROOT))

    # All mutations go through a single transaction — if PII scrub or
    # file-erasure DB side-effects fail, the customer row is NOT left
    # half-deactivated.
    try:
        customer.is_active = False
        customer.deletion_scheduled_at = deletion_date
        customer.updated_at = datetime.utcnow()

        # Scrub PII from related free-text records. skip_gdpr_request=True
        # because THIS endpoint manages the full request lifecycle
        # (PENDING row already written above).
        scrub_counts = await CustomerService.scrub_customer_pii(
            db,
            customer_id=customer_id,
            performed_by=admin_user_id,
            skip_gdpr_request=True,
        )

        # File-level erasure — deletes actual files on disk referenced
        # by customer-linked rows. Partial failures are captured in
        # the result; they do NOT raise.
        file_erasure_result = await file_erasure.erase_customer_files(
            db,
            customer_id=customer_id,
            performed_by=admin_user_id,
        )

        await db.commit()
    except Exception:
        await db.rollback()
        logger.error(
            "GDPR erasure failed — transaction rolled back",
            extra={
                "audit": True,
                "action": "gdpr_erase_request_failed",
                "customer_id": customer_id,
                "user_id": admin_user_id,
                "gdpr_request_id": gdpr_request_id,
            },
            exc_info=True,
        )
        await _finalize_gdpr_request(
            "FAILED", notes_suffix="scrub_or_file_erasure_exception"
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GDPR erasure failed — no changes persisted.",
        )

    # --- Success path — promote PENDING row to terminal status ----------
    if file_erasure_result.files_failed > 0:
        partial_note = (
            f"File-erasure partial failure: "
            f"{file_erasure_result.files_failed} file(s) could not be "
            f"deleted. Admin follow-up required. See "
            f"customer_audit_logs.action='gdpr_file_erasure' for "
            f"per-file errors."
        )
        await _finalize_gdpr_request(
            "PARTIAL_FILE_ERASURE",
            notes_suffix=(
                f"Art. 17 erasure — scrubbed {scrub_counts.get('total', 0)} "
                f"PII occurrence(s); {partial_note}"
            ),
        )
    else:
        await _finalize_gdpr_request(
            "completed",
            notes_suffix=(
                f"Art. 17 erasure — scrubbed {scrub_counts.get('total', 0)} "
                f"PII occurrence(s); all files erased cleanly."
            ),
        )

    # Audit log — GDPR erasure requests are legally significant.
    # Include the idempotency key (if any) so operator-side log analysis
    # can correlate client retries. client_created_at captured for Lena
    # §4 timing even though V1.1 does not yet act on it server-side.
    logger.info(
        "GDPR erasure requested",
        extra={
            "audit": True,
            "action": "gdpr_erase_request",
            "customer_id": customer_id,
            "user_id": admin_user_id,
            "deletion_scheduled": deletion_date.isoformat(),
            "pii_redaction_count": scrub_counts.get("total", 0),
            "idempotency_key": str(idem.key) if idem.key else None,
            "client_created_at": (
                idem.client_created_at.isoformat() if idem.client_created_at else None
            ),
            "files_deleted": file_erasure_result.files_deleted,
            "files_missing": file_erasure_result.files_missing,
            "files_failed": file_erasure_result.files_failed,
        },
    )

    # 207 Multi-Status when partial failure; 200 otherwise.
    is_partial = file_erasure_result.files_failed > 0
    response.status_code = (
        status.HTTP_207_MULTI_STATUS if is_partial else status.HTTP_200_OK
    )

    return {
        "message": (
            "Löschung geplant — Teilweise Dateifehler"
            if is_partial
            else "Löschung geplant"
        ),
        "customer_id": customer_id,
        "deletion_date": deletion_date.date().isoformat(),
        "pii_redactions": scrub_counts,
        "file_erasure": file_erasure_result.as_dict(),
        "partial": is_partial,
    }


@router.delete("/{customer_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_customer(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.CUSTOMER_DELETE)),
):
    """
    Soft delete a customer (sets is_active = False).

    Cannot delete customers with existing orders.

    Permissions: Requires CUSTOMER_DELETE permission (Admin only).
    """
    try:
        success = await CustomerService.delete_customer(db, customer_id)
        if not success:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Customer {customer_id} not found",
            )

    except ValueError as e:
        # Customer has orders
        logger.warning(f"Cannot delete customer {customer_id}: {str(e)}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        logger.error(f"Error deleting customer {customer_id}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete customer",
        )


# ---------------------------------------------------------------------------
# V1.1 consultation module — customer no-gos + style profile (Task 8).
#
# No-gos and the style profile are preference data, not design IP (design
# intent/wishes live on Consultation, which is CONSULTATION_*-gated,
# GOLDSMITH/ADMIN only). These endpoints reuse the existing customer
# CUSTOMER_VIEW/CUSTOMER_EDIT permissions, so a VIEWER with customer-view
# access keeps read access to no-go warnings.
# ---------------------------------------------------------------------------


def _normalize_style_profile(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Coerce ``None`` values in a style-profile dict to ``[]``.

    Final-review fix: ``StyleProfileRead`` declares every field as
    ``List[str] = []``, so a stored/incoming ``None`` fails Pydantic
    validation. ``None`` can reach this dict two ways:

    1. An explicit ``PATCH {"metal_tones": null}`` — the key IS present
       under ``exclude_unset=True`` (the client explicitly set it), just
       to ``None``. We treat that as "reset this field to []" — the
       RESTful, most useful interpretation of a client clearing a
       list-shaped preference field. (The alternative — dropping
       ``None``-valued keys instead of merging them — would silently
       keep the stale value rather than honoring the client's intent to
       clear it.)
    2. A row poisoned by the pre-fix version of this endpoint, where a
       raw ``None`` was already persisted into the JSON column.

    Normalizing here (rather than only in the PATCH merge) means a
    pre-poisoned row self-heals the next time it is read OR patched,
    instead of continuing to 500 on every subsequent GET.
    """
    return {key: ([] if value is None else value) for key, value in raw.items()}


@router.get("/{customer_id}/no-gos", response_model=List[NoGoRead])
async def list_customer_no_gos(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.CUSTOMER_VIEW)),
):
    """
    List all no-gos (persistent exclusions, e.g. allergies) for a customer.

    Permissions: Requires CUSTOMER_VIEW permission.
    """
    return await NoGoService.list_no_gos(db, customer_id)


@router.post(
    "/{customer_id}/no-gos",
    response_model=NoGoRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_customer_no_go(
    customer_id: int,
    no_go_in: NoGoCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.CUSTOMER_EDIT)),
):
    """
    Add a no-go (persistent exclusion, e.g. an allergy) for a customer.

    404 if the customer does not exist. 409 if an equivalent no-go (same
    category, case-insensitively equal value) already exists for this
    customer.

    Permissions: Requires CUSTOMER_EDIT permission.
    """
    try:
        return await NoGoService.add_no_go(db, customer_id, no_go_in)
    except DuplicateNoGoError:
        # SECURITY (binding review note): no-go values are health-adjacent
        # data (e.g. allergies). The 409 detail is a hardcoded generic
        # string, and the exception message is never forwarded or logged —
        # typed handling, no string-matching on user-influenced text.
        logger.warning(
            "Duplicate no-go rejected",
            extra={"customer_id": customer_id},
        )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Dieses No-Go existiert bereits",
        )
    except ValueError:
        # Unknown customer. Generic detail — never forward the message.
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Kunde nicht gefunden",
        )


@router.delete(
    "/{customer_id}/no-gos/{no_go_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_customer_no_go(
    customer_id: int,
    no_go_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.CUSTOMER_EDIT)),
):
    """
    Remove a no-go from a customer.

    Permissions: Requires CUSTOMER_EDIT permission.
    """
    try:
        await NoGoService.delete_no_go(db, customer_id, no_go_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.get("/{customer_id}/no-gos/check", response_model=List[NoGoConflict])
async def check_customer_no_go_conflicts(
    customer_id: int,
    candidate: List[str] = Query(
        ...,
        description="Candidate material/stone/etc. values to check against "
        "the customer's recorded no-gos",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.CUSTOMER_VIEW)),
):
    """
    Check candidate values (e.g. materials being discussed in a consultation)
    against a customer's recorded no-gos. Bidirectional, case-insensitive
    substring match — see ``NoGoService.check_conflicts``.

    Permissions: Requires CUSTOMER_VIEW permission.
    """
    return await NoGoService.check_conflicts(db, customer_id, candidate)


@router.get("/{customer_id}/style-profile", response_model=StyleProfileRead)
async def get_style_profile(
    customer_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.CUSTOMER_VIEW)),
):
    """
    Get a customer's style profile (metal tones, finishes, stone
    preferences, style words). Returns empty lists when the column is NULL.

    Permissions: Requires CUSTOMER_VIEW permission.
    """
    customer = await db.get(CustomerModel, customer_id)
    if customer is None or customer.is_deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Customer {customer_id} not found",
        )
    return StyleProfileRead(**_normalize_style_profile(customer.style_profile or {}))


@router.patch("/{customer_id}/style-profile", response_model=StyleProfileRead)
async def update_style_profile(
    customer_id: int,
    update_in: StyleProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission(Permission.CUSTOMER_EDIT)),
):
    """
    Update a customer's style profile with merge semantics — only the keys
    provided in the request body are replaced; omitted keys keep their
    previously stored value.

    Permissions: Requires CUSTOMER_EDIT permission.
    """
    async with transactional(db):
        customer = await db.get(CustomerModel, customer_id)
        if customer is None or customer.is_deleted:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Customer {customer_id} not found",
            )
        profile = dict(customer.style_profile or {})
        profile.update(update_in.model_dump(exclude_unset=True))
        # See _normalize_style_profile: an explicit null in the PATCH body
        # resets that field to [] rather than poisoning the JSON column
        # with None (which would 500 every subsequent read via
        # StyleProfileRead). Also self-heals any pre-existing poisoned
        # value in a field this request didn't touch.
        profile = _normalize_style_profile(profile)
        customer.style_profile = profile
    return StyleProfileRead(**profile)
