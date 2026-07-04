"""
API endpoints for the V1.3 statistical labor estimator (Phase 1, Task 5).

Route overview:
  POST /api/v1/estimates/labor      — labor hours + cost estimate
  GET  /api/v1/estimates/accuracy   — estimator calibration (MAPE/bias)

Permissions: ``Permission.ESTIMATE_VIEW`` gates BOTH endpoints — ADMIN +
GOLDSMITH only (financial/pricing data per CLAUDE.md; VIEWER excluded, see
``core/permissions.py`` for why a single permission is enough here).

Audit logging: ``GET /estimates/accuracy`` is covered by
``AuditLoggingMiddleware``'s ``_RESOURCE_ROUTES["estimates"]`` entry
(financial, GET-only). ``POST /estimates/labor`` is a non-GET on a
financial family, which that middleware structurally skips (same
``is_financial`` gate rationale as the ``cost-changes`` family — see that
module) — so this router writes its own ``CustomerAuditLog`` row via
``write_financial_audit_row``, mirroring ``get_order_projected_cost`` in
``customer_updates.py``.
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.api.deps import get_current_user
from goldsmith_erp.core.permissions import Permission, require_permission
from goldsmith_erp.db.models import User
from goldsmith_erp.db.session import get_db
from goldsmith_erp.ml.labor_estimator import EstimateFeatures
from goldsmith_erp.models.estimator import (
    CalibrationResponse,
    LaborEstimateRequest,
    LaborEstimateResponse,
)
from goldsmith_erp.services import estimate_accuracy_service, estimator_service
from goldsmith_erp.services.customer_update_service import write_financial_audit_row

router = APIRouter()
logger = logging.getLogger(__name__)


@router.post(
    "/labor",
    response_model=LaborEstimateResponse,
    summary="Statistische Arbeitszeit- und Kostenschätzung",
)
@require_permission(Permission.ESTIMATE_VIEW)
async def post_labor_estimate(
    data: LaborEstimateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Liefert eine statistische Schätzung der Arbeitsstunden + Arbeitskosten
    für die angegebenen Auftragsmerkmale, basierend auf ähnlichen
    abgeschlossenen Aufträgen (Median + P20/P80).

    ``insufficient_data=true`` bedeutet: zu wenige vergleichbare Aufträge
    im Bestand — sämtliche Zahlenwerte sind dann ``null`` (niemals
    geschätzt/erfunden). Nur für ADMIN/GOLDSMITH sichtbar (Preisdaten);
    jeder Zugriff wird protokolliert (GDPR Art. 30 / CLAUDE.md).
    """
    features = EstimateFeatures(
        order_type=data.order_type,
        finish_type=data.finish_type,
        has_stone_setting=data.has_stone_setting,
        alloy=data.alloy,
        complexity_rating=data.complexity_rating,
    )
    response = await estimator_service.estimate_labor(db, features)

    # Financial-data GET-only middleware audit gate structurally skips this
    # POST (see module docstring) — write the DB-backed CustomerAuditLog
    # row directly, same as get_order_projected_cost in customer_updates.py.
    await write_financial_audit_row(
        db,
        action="financial_read",
        entity="labor_estimate",
        entity_id=None,
        order_id=None,
        user_id=current_user.id,
        endpoint="/api/v1/estimates/labor",
        http_method="POST",
    )
    return response


@router.get(
    "/accuracy",
    response_model=CalibrationResponse,
    summary="Kalibrierung des Arbeitszeitschätzers (MAPE/Bias)",
)
@require_permission(Permission.ESTIMATE_VIEW)
async def get_estimate_accuracy(
    order_type: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Liefert die rollierende Kalibrierung (MAPE + Bias je Auftragstyp) über
    die letzten ``limit`` Estimate-Accuracy-Datensätze, optional gefiltert
    nach ``order_type``.

    Reiner Lesezugriff, kein Seiteneffekt. Nur für ADMIN/GOLDSMITH
    sichtbar (Preisdaten); GET-Zugriffe auf ``/estimates/*`` werden von
    ``AuditLoggingMiddleware`` protokolliert (``financial_read`` /
    ``list_accessed_financial``).
    """
    result = await estimate_accuracy_service.calibration(
        db, order_type=order_type, limit=limit
    )
    return CalibrationResponse.model_validate(result)
