"""Job spine endpoints (ARCH-02, ARCH phase 5, ADR-2026-09-25-jobs-spine).

``GET /jobs`` lists orders and repairs together (future kanban);
``GET /jobs/{id}`` returns one card and ``GET /jobs/{id}/timeline``
delegates to the per-kind timeline.

Access: ORDER_VIEW (every role). Repairs are only listed for callers who
also hold REPAIR_VIEW. SEC-01 / GDPR-03: ``agreed_price`` is removed for
callers without FINANCIAL_VIEW; the timelines are projected by their
builders (no prices, design photos only with DESIGN_VIEW). Reads are
audit-logged by AuditLoggingMiddleware (``jobs`` family).
"""

from __future__ import annotations

import logging
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.api.deps import get_current_user
from goldsmith_erp.api.role_projection import (
    ExcludeSpec,
    build_excludes,
    can_view_design,
    can_view_financial,
    project,
    project_response,
)
from goldsmith_erp.core.permissions import (
    Permission,
    has_permission,
    require_permission,
)
from goldsmith_erp.db.models import JobKind, JobStatus, User
from goldsmith_erp.db.session import get_db
from goldsmith_erp.models.job import JobListItem, JobTimelineRead, job_list_item
from goldsmith_erp.models.pagination import (
    MAX_PAGE_LIMIT,
    Page,
    PageParams,
    page_response,
)
from goldsmith_erp.services import list_queries
from goldsmith_erp.services.job_service import JOB_STATUS_LABELS, JobService
from goldsmith_erp.services.order_timeline import (
    build_order_timeline,
    build_repair_timeline,
)

router = APIRouter()
logger = logging.getLogger(__name__)

_JOB_FINANCIAL_FIELDS: frozenset[str] = frozenset({"agreed_price"})
DEFAULT_JOB_PAGE_LIMIT = 50


def _job_excludes(user: User) -> ExcludeSpec:
    return build_excludes(user, financial=_JOB_FINANCIAL_FIELDS)


def _item(job: object) -> JobListItem:
    return job_list_item(job, JOB_STATUS_LABELS[JobStatus(getattr(job, "status"))])


def _visible_kind(user: User, kind: Optional[JobKind]) -> Optional[JobKind]:
    """Callers without REPAIR_VIEW only see orders."""
    if has_permission(user, Permission.REPAIR_VIEW):
        return kind
    if kind is JobKind.REPAIR:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: {Permission.REPAIR_VIEW.value} required",
        )
    return JobKind.ORDER


@router.get("/", response_model=Page[JobListItem])
@require_permission(Permission.ORDER_VIEW)  # type: ignore[misc]
async def list_jobs(
    kind: Optional[JobKind] = Query(None, description="order oder repair"),
    status_filter: Optional[List[JobStatus]] = Query(
        None, alias="status", description="Einheitlicher Status (mehrfach möglich)"
    ),
    customer_id: Optional[int] = Query(None, gt=0),
    q: Optional[str] = Query(
        None, min_length=1, max_length=100, description="Nummer, Titel oder Kunde"
    ),
    offset: int = Query(0, ge=0),
    limit: int = Query(DEFAULT_JOB_PAGE_LIMIT, ge=1, le=MAX_PAGE_LIMIT),
    sort: Optional[str] = Query(
        None,
        max_length=200,
        description=(
            "Kommagetrennt, absteigend mit '-': "
            + ", ".join(sorted(list_queries.JOB_SORT_FIELDS))
        ),
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JSONResponse:
    """Aufträge und Reparaturen gemeinsam, seitenweise (Grundlage Kanban)."""
    params = PageParams(limit=limit, offset=offset, is_paged=True, sort=sort)
    stmt = await list_queries.jobs_statement(
        db,
        kind=_visible_kind(current_user, kind),
        statuses=status_filter or (),
        customer_id=customer_id,
        q=q,
        sort=sort,
    )
    result = await list_queries.fetch_page(
        db, stmt, params, list_queries.JOB_LIST_OPTIONS
    )
    excludes = _job_excludes(current_user)
    rows = [project(JobListItem, _item(job), excludes) for job in result.items]
    return page_response(rows, result.total, params)


async def _job_or_404(db: AsyncSession, job_id: int, user: User) -> object:
    job = await JobService.get_job(db, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Vorgang #{job_id} nicht gefunden")
    _visible_kind(user, JobKind(getattr(job, "kind")))
    return job


@router.get("/{job_id}", response_model=JobListItem)
@require_permission(Permission.ORDER_VIEW)  # type: ignore[misc]
async def get_job(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JSONResponse:
    """Ein Vorgang (Auftrag oder Reparatur)."""
    job = await _job_or_404(db, job_id, current_user)
    return project_response(JobListItem, _item(job), _job_excludes(current_user))


@router.get("/{job_id}/timeline", response_model=JobTimelineRead)
@require_permission(Permission.ORDER_VIEW)  # type: ignore[misc]
async def get_job_timeline(
    job_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JobTimelineRead:
    """Verlauf eines Vorgangs; nutzt die Timeline der jeweiligen Art."""
    job: object = await _job_or_404(db, job_id, current_user)
    financial = can_view_financial(current_user)
    design = can_view_design(current_user)
    order, repair = getattr(job, "order"), getattr(job, "repair")
    if order is not None:
        timeline = await build_order_timeline(
            db, int(order.id), financial=financial, design=design
        )
        items = timeline.items
    elif repair is not None:
        items = await build_repair_timeline(
            db, int(repair.id), financial=financial, design=design
        )
    else:  # pragma: no cover - a job always wraps one row
        items = []
    return JobTimelineRead(
        job_id=job_id,
        kind=JobKind(getattr(job, "kind")),
        order_id=int(order.id) if order is not None else None,
        repair_id=int(repair.id) if repair is not None else None,
        items=items,
    )
