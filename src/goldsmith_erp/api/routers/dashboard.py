# src/goldsmith_erp/api/routers/dashboard.py
"""The "Heute" dashboard endpoint (W2-03; FE-05, DOM-14, DOM-15, DOM-15b).

``GET /dashboard/today`` serves every role (ORDER_VIEW). Lanes the caller
lacks a permission for come back empty, and ``customer_pending[].amount``
(cost-change amount, quote total) is removed for callers without
FINANCIAL_VIEW (SEC-01 / GDPR-03). Reads are audit-logged by
AuditLoggingMiddleware (``dashboard`` family).
"""

import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.api.deps import get_current_user
from goldsmith_erp.api.role_projection import (
    ExcludeSpec,
    build_excludes,
    project_response,
)
from goldsmith_erp.core.permissions import Permission, require_permission
from goldsmith_erp.db.models import User
from goldsmith_erp.db.session import get_db
from goldsmith_erp.models.dashboard import DashboardToday
from goldsmith_erp.services.dashboard_service import DashboardService

router = APIRouter()
logger = logging.getLogger(__name__)


def _dashboard_excludes(user: User) -> ExcludeSpec:
    """Strip the per-item ``amount`` from the pending lane without FINANCIAL_VIEW."""
    return build_excludes(user, nested_financial={"customer_pending": {"amount"}})


@router.get("/today", response_model=DashboardToday)
@require_permission(Permission.ORDER_VIEW)
async def get_dashboard_today(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JSONResponse:
    """Überfällig, bald fällig, Wartet auf Kunde und heutige Timer in einem Aufruf."""
    summary = await DashboardService.get_today(db, current_user)
    return project_response(DashboardToday, summary, _dashboard_excludes(current_user))
