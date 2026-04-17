"""Scanner HTTP surface — Slice 4 of the V1.1 QR/Barcode workflow.

This router is a thin transport wrapper. All role-based content filtering
(ORDER_FIELDS_BY_ROLE etc.), idempotency de-duplication, and action
allow-listing lives in ``scanner_service``. The router is responsible
for:

  * JWT authentication (via ``get_current_user``).
  * A single permission gate (``Permission.SCAN_READ``) — granted to
    VIEWER, GOLDSMITH and ADMIN. Service-layer projection enforces
    role-appropriate content.
  * ``Idempotency-Key`` + ``X-Client-Created-At`` header validation via
    the Slice 2 :class:`IdempotencyContext` dependency — attached only to
    the two state-mutating endpoints (``/log`` and ``/log/batch``).
  * Turning service-layer DTOs / ORM rows into their Pydantic response
    shapes.

Endpoints (all mounted at ``/api/v1/scan`` — see ``main.py``):

  * ``POST /resolve``      — role-filtered entity resolution (no DB write).
  * ``POST /log``          — single scan_logs insert with per-row
                             idempotency dedupe. ``user_id`` ALWAYS from JWT.
  * ``POST /log/batch``    — up to 100 events in one round-trip. Each row
                             independently deduped; summary returned.
  * ``GET  /search``       — multi-entity search for alias registration.
                             Role-filtered at the service layer — VIEWER
                             never sees ``metal_purchase`` results.

**Explicit invariants**

  * The router NEVER reads ``user_id`` from the request body. The
    :class:`StrictRequestBase` schema layer would reject it at
    validation, but the router's single source of truth is
    ``current_user.id`` derived from the validated JWT. This is a
    load-bearing defence: if ``StrictRequestBase`` ever regresses, the
    router does not become the weak link.
  * ``Idempotency-Key`` on the ``/log`` endpoints is a **transport-level**
    replay token (HTTP header). The application-level
    :attr:`ScanLogCreate.idempotency_key` on the body is the value
    persisted to ``scan_logs.idempotency_key`` and drives DB-level
    dedupe. A well-behaved client sends both headers and body values
    consistent with each other. The server only uses the body value for
    dedupe lookup; the header is validated for shape (UUIDv4) for
    symmetry with the Slice 2 security floor.
  * ``/resolve`` is a *read* (no state mutation), so it does NOT depend
    on ``IdempotencyContext``. Per-scan analytics timing lives on
    ``/log`` where the payload is actually persisted.

**Rate limiting**

  * Not enforced at the router layer in V1.1. A busy workshop could drive
    ``/resolve`` at burst rates (bench scanner with hot-swap habits).
    Rate limiting is an ops / middleware concern and out of Slice 4
    scope — flagged for follow-up when the scan_logs ingestion volume
    is observable post-ship.
"""

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.api.deps import get_current_user
from goldsmith_erp.core.idempotency import (
    IdempotencyContext,
    get_idempotency_context,
)
from goldsmith_erp.core.permissions import Permission, require_permission
from goldsmith_erp.db.models import User
from goldsmith_erp.db.session import get_db
from goldsmith_erp.models.scanner import (
    BatchLogResponse,
    ResolveRequest,
    ResolveResponse,
    ScanLogBatchCreate,
    ScanLogCreate,
    ScanLogRead,
)
from goldsmith_erp.services.scanner_service import ScannerService

router = APIRouter()


# --------------------------------------------------------------------------- #
# Allowed entity types on the search endpoint — single source of truth.
# --------------------------------------------------------------------------- #
#
# Matches the service-layer ``_allowed_search_types`` allow-list. The router
# pre-validates the client input against this set so malformed type tokens
# produce a clean 400 rather than silently being filtered out.
_SEARCH_ENTITY_TYPES = frozenset(
    {"order", "repair", "metal_purchase", "material"}
)


# --------------------------------------------------------------------------- #
# POST /resolve  — role-filtered entity resolution (no persistence)
# --------------------------------------------------------------------------- #


@router.post(
    "/resolve",
    response_model=ResolveResponse,
    summary="Resolve a scanned payload (server-side, role-filtered)",
    description=(
        "Resolve a raw scan payload into an entity projection plus a list "
        "of Quick Actions. The response is filtered by the caller's role: "
        "VIEWER receives non-financial fields only, GOLDSMITH gains "
        "production-floor fields, ADMIN additionally receives financial "
        "fields. No state mutation — this endpoint is a read."
    ),
)
@require_permission(Permission.SCAN_READ)
async def resolve_scan(
    body: ResolveRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ResolveResponse:
    """Pass-through to :meth:`ScannerService.resolve_payload`.

    The Pydantic validation on ``body`` already:

      * Rejects control characters (except TAB) in ``raw_payload``.
      * Rejects null bytes outright.
      * Caps ``raw_payload`` at 500 chars.
      * Enforces the B1 strict-whitelist on :class:`ScanContext`.
    """
    return await ScannerService.resolve_payload(
        db=db,
        raw_payload=body.raw_payload,
        context=body.context,
        user=current_user,
    )


# --------------------------------------------------------------------------- #
# POST /log  — single scan_logs insert
# --------------------------------------------------------------------------- #


@router.post(
    "/log",
    response_model=ScanLogRead,
    status_code=status.HTTP_201_CREATED,
    summary="Log a single scan event",
    description=(
        "Append a single scan event to scan_logs. Idempotency is enforced "
        "via the body-level ``idempotency_key`` (UUIDv4) against the "
        "``UNIQUE WHERE idempotency_key IS NOT NULL`` partial index on "
        "scan_logs — a second POST with the same key returns the original "
        "row rather than inserting a duplicate."
    ),
)
@require_permission(Permission.SCAN_READ)
async def log_scan(
    body: ScanLogCreate,
    idem: IdempotencyContext = Depends(get_idempotency_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> ScanLogRead:
    """Insert (or dedupe-return) a scan_logs row.

    ``user_id`` is sourced from ``current_user.id`` — the JWT-derived
    user — never from the request body. The :class:`StrictRequestBase`
    base class rejects any attempt to smuggle ``user_id`` via the body
    at the Pydantic layer; this router additionally never consults the
    payload for identity.

    ``idem`` is validated transport-level (UUIDv4 + 30-day age cap) even
    though the body's :attr:`ScanLogCreate.idempotency_key` is what drives
    DB dedupe. The header contract is uniform with other mutating
    endpoints introduced from Slice 4 onward.
    """
    # Intentionally NOT using idem.key as the DB dedupe value — the
    # authoritative value lives on the body so that offline replays
    # (queue-drain) can reconstruct the exact same key-to-row mapping
    # even if the transport header is absent on retry.
    del idem  # transport-layer idempotency; DB dedupe uses body.idempotency_key

    db_row = await ScannerService.log_scan(
        db=db,
        user_id=current_user.id,
        event=body,
    )
    return _scan_log_to_read(db_row)


# --------------------------------------------------------------------------- #
# POST /log/batch  — up to 100 events per call
# --------------------------------------------------------------------------- #


@router.post(
    "/log/batch",
    response_model=BatchLogResponse,
    summary="Log up to 100 scan events in one request (offline-queue drain)",
    description=(
        "Batch insert. Each row is independently deduped by its body-level "
        "``idempotency_key``. Response carries counts and a capped list of "
        "distinct rejection reasons — per-row error payloads are withheld "
        "so the endpoint cannot be used to enumerate client-queue contents."
    ),
)
@require_permission(Permission.SCAN_READ)
async def log_scan_batch(
    body: ScanLogBatchCreate,
    idem: IdempotencyContext = Depends(get_idempotency_context),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BatchLogResponse:
    """Pass-through to :meth:`ScannerService.log_scan_batch`.

    Schema-level guards (Pydantic):
      * ``events`` min_length=1, max_length=100.
      * Every event's :attr:`raw_payload` runs the control-char sanitiser.
    """
    del idem  # transport-layer idempotency; body-level keys drive DB dedupe
    dto = await ScannerService.log_scan_batch(
        db=db,
        user_id=current_user.id,
        events=body.events,
    )
    return BatchLogResponse(
        ingested=dto.ingested,
        deduplicated=dto.deduplicated,
        rejected=dto.rejected,
        reasons=dto.reasons,
    )


# --------------------------------------------------------------------------- #
# GET /log  — recent scan history for the calling user (Slice 12)
# --------------------------------------------------------------------------- #


@router.get(
    "/log",
    response_model=List[ScanLogRead],
    summary="Recent scan history for the calling user",
    description=(
        "Return the most recent ``scan_logs`` rows for the authenticated "
        "user. Backs the 'Letzte Scans' list on the ScannerPage (Slice 12). "
        "Cross-user lookups are NOT allowed in V1.1 — the user_id is "
        "derived from the JWT; the optional ``user_id`` query parameter "
        "accepts only the sentinel value ``me`` (kept in the signature "
        "so the frontend spec can round-trip without surprises)."
    ),
)
@require_permission(Permission.SCAN_READ)
async def list_scan_logs(
    user_id: str = Query(
        "me",
        description=(
            "Must be the literal string 'me'. Provided for self-"
            "documenting URL shape; the authoritative user id is "
            "sourced from the JWT."
        ),
    ),
    limit: int = Query(
        20,
        ge=1,
        le=100,
        description="Max rows to return. Hard-capped at 100.",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[ScanLogRead]:
    """Return the JWT user's most recent scan events."""
    if user_id != "me":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only 'me' is accepted for user_id in V1.1.",
        )
    rows = await ScannerService.list_scan_logs_for_user(
        db=db,
        user_id=current_user.id,
        limit=limit,
    )
    return [_scan_log_to_read(row) for row in rows]


# --------------------------------------------------------------------------- #
# GET /search  — multi-entity search (role-filtered)
# --------------------------------------------------------------------------- #


@router.get(
    "/search",
    summary="Multi-entity substring search for alias-registration UI",
    description=(
        "Returns up to 20 matches per requested entity type. The query "
        "string must be 2–100 characters. The ``types`` query parameter "
        "is a comma-separated list, at least one of: ``order``, "
        "``repair``, ``metal_purchase``, ``material``. Result set is "
        "role-filtered: VIEWER never receives ``metal_purchase`` hits "
        "even if requested; financial fields are stripped from every "
        "projection per ORDER_FIELDS_BY_ROLE etc."
    ),
)
@require_permission(Permission.SCAN_READ)
async def search_entities(
    q: str = Query(
        ...,
        min_length=2,
        max_length=100,
        description="Substring to match.",
    ),
    types: str = Query(
        ...,
        description=(
            "Comma-separated entity types. Allowed values: order, repair, "
            "metal_purchase, material."
        ),
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> List[Dict[str, Any]]:
    """Parse the ``types`` param, validate it, dispatch to the service."""
    types_list = [token.strip() for token in types.split(",") if token.strip()]
    if not types_list:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "At least one entity type is required in the 'types' "
                "query parameter."
            ),
        )
    unknown = [t for t in types_list if t not in _SEARCH_ENTITY_TYPES]
    if unknown:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Unknown entity type(s): "
                + ", ".join(sorted(unknown))
                + ". Allowed: "
                + ", ".join(sorted(_SEARCH_ENTITY_TYPES))
            ),
        )
    return await ScannerService.search_entities(
        db=db,
        query=q,
        types=types_list,
        user=current_user,
    )


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #


def _scan_log_to_read(row: Any) -> ScanLogRead:
    """Map a :class:`ScanLog` ORM row to a :class:`ScanLogRead` response.

    Explicit construction rather than ``from_attributes`` so the response
    schema's ``extra='forbid'`` config stays effective — a developer who
    adds an ORM column does NOT auto-leak it through this endpoint.
    """
    return ScanLogRead(
        id=row.id,
        scanned_at=row.scanned_at,
        user_id=row.user_id,
        raw_payload=row.raw_payload,
        resolved_type=row.resolved_type,
        resolved_id=row.resolved_id,
        resolution_path=row.resolution_path,
        action_taken=row.action_taken,
        offline_queued=row.offline_queued,
        synced_at=row.synced_at,
    )
