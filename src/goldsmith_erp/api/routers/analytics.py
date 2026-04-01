# src/goldsmith_erp/api/routers/analytics.py
"""
Analytics endpoints — Soll/Ist-Vergleich (quote vs. actual comparison).

Financial data — restricted to ADMIN and GOLDSMITH roles.
All endpoints audit-log financial data access per CLAUDE.md requirements.
"""

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.api.deps import get_current_user
from goldsmith_erp.core.permissions import Permission, require_permission
from goldsmith_erp.db.session import get_db
from goldsmith_erp.db.models import User
from goldsmith_erp.models.comparison import OrderComparison, UserAccuracy, WorkshopStats
from goldsmith_erp.services.comparison_service import ComparisonService

router = APIRouter()
logger = logging.getLogger(__name__)


def _audit_log_financial_access(
    endpoint: str,
    user: User,
    context: dict,
) -> None:
    """
    Structured audit log for financial data access.

    Per CLAUDE.md: all financial data access MUST be audit-logged.
    Uses structured logging so log aggregators can parse and alert on access.
    Customer PII is never logged — only anonymized IDs.
    """
    logger.info(
        "Financial data access — analytics",
        extra={
            "audit": True,
            "endpoint": endpoint,
            "user_id": user.id,          # Never log email or name here
            "user_role": user.role.value if hasattr(user.role, "value") else str(user.role),
            "context": context,
            "timestamp": datetime.utcnow().isoformat(),
        },
    )


# ---------------------------------------------------------------------------
# GET /api/v1/orders/{id}/comparison
# ---------------------------------------------------------------------------


@router.get(
    "/orders/{order_id}/comparison",
    response_model=OrderComparison,
    summary="Soll/Ist-Vergleich fuer einen Auftrag",
    description=(
        "Vergleicht geschaetzte mit tatsaechlichen Stunden, Materialgewicht, "
        "Materialkosten und Endpreis fuer einen abgeschlossenen Auftrag. "
        "Abweichungen > 20% werden als signifikant markiert."
    ),
    tags=["analytics"],
)
@require_permission(Permission.REPORTS_VIEW)
async def get_order_comparison(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> OrderComparison:
    """
    Soll/Ist-Vergleich fuer einen einzelnen Auftrag.

    Zugriffsrechte: ADMIN und GOLDSMITH (REPORTS_VIEW).
    Alle Zugriffe werden audit-geloggt (finanzielle Daten).
    """
    _audit_log_financial_access(
        endpoint=f"GET /orders/{order_id}/comparison",
        user=current_user,
        context={"order_id": order_id},
    )

    comparison = await ComparisonService.get_order_comparison(db, order_id)
    if not comparison:
        raise HTTPException(
            status_code=404,
            detail=f"Auftrag {order_id} nicht gefunden.",
        )
    return comparison


# ---------------------------------------------------------------------------
# GET /api/v1/analytics/workshop-stats
# ---------------------------------------------------------------------------


@router.get(
    "/analytics/workshop-stats",
    response_model=WorkshopStats,
    summary="Werkstatt-weite Soll/Ist-Statistiken",
    description=(
        "Aggregiert Abweichungen ueber alle abgeschlossenen Auftraege im angegebenen "
        "Zeitraum. Zeigt Trends, systematisch unterschaetzte Auftragstypen und "
        "Aktivitaeten mit regelmaessigem Mehraufwand."
    ),
    tags=["analytics"],
)
@require_permission(Permission.REPORTS_VIEW)
async def get_workshop_stats(
    date_from: Optional[datetime] = Query(
        None,
        description=(
            "Startdatum des Auswertungszeitraums (ISO 8601). "
            "Standard: 90 Tage vor heute."
        ),
        alias="from",
    ),
    date_to: Optional[datetime] = Query(
        None,
        description=(
            "Enddatum des Auswertungszeitraums (ISO 8601). "
            "Standard: jetzt."
        ),
        alias="to",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> WorkshopStats:
    """
    Werkstatt-weite Soll/Ist-Statistiken fuer einen Zeitraum.

    Zugriffsrechte: ADMIN und GOLDSMITH (REPORTS_VIEW).
    Standard-Zeitraum: letzte 90 Tage.
    Alle Zugriffe werden audit-geloggt (finanzielle Daten).
    """
    now = datetime.utcnow()
    effective_from = date_from or (now - timedelta(days=90))
    effective_to = date_to or now

    if effective_from >= effective_to:
        raise HTTPException(
            status_code=422,
            detail="'from' muss vor 'to' liegen.",
        )

    _audit_log_financial_access(
        endpoint="GET /analytics/workshop-stats",
        user=current_user,
        context={
            "date_from": effective_from.isoformat(),
            "date_to": effective_to.isoformat(),
        },
    )

    return await ComparisonService.get_workshop_statistics(db, effective_from, effective_to)


# ---------------------------------------------------------------------------
# GET /api/v1/analytics/goldsmith-accuracy/{user_id}
# ---------------------------------------------------------------------------


@router.get(
    "/analytics/goldsmith-accuracy/{user_id}",
    response_model=UserAccuracy,
    summary="Schaetzgenauigkeit eines Goldschmieds",
    description=(
        "Berechnet die persoenliche Soll/Ist-Genauigkeit eines Goldschmieds "
        "und vergleicht sie mit dem Werkstatt-Durchschnitt der letzten 90 Tage. "
        "Zeigt die besten und schlechtesten Auftragstypen sowie den Entwicklungstrend."
    ),
    tags=["analytics"],
)
@require_permission(Permission.REPORTS_VIEW)
async def get_goldsmith_accuracy(
    user_id: int,
    date_from: Optional[datetime] = Query(
        None,
        description="Startdatum fuer den Vergleichszeitraum (ISO 8601). Standard: 90 Tage.",
        alias="from",
    ),
    date_to: Optional[datetime] = Query(
        None,
        description="Enddatum fuer den Vergleichszeitraum (ISO 8601). Standard: jetzt.",
        alias="to",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> UserAccuracy:
    """
    Soll/Ist-Genauigkeit eines einzelnen Goldschmieds.

    Zugriffsrechte: ADMIN und GOLDSMITH (REPORTS_VIEW).
    Ein Goldschmied darf nur seine eigenen Daten abrufen.
    ADMINs duerfen beliebige User-IDs abfragen.
    Alle Zugriffe werden audit-geloggt (finanzielle Daten).
    """
    from goldsmith_erp.db.models import UserRole

    # Goldsmiths may only query their own accuracy
    if (
        current_user.role != UserRole.ADMIN
        and current_user.id != user_id
    ):
        raise HTTPException(
            status_code=403,
            detail="Goldschmiede duerfen nur ihre eigene Genauigkeit abrufen.",
        )

    now = datetime.utcnow()
    effective_from = date_from or (now - timedelta(days=90))
    effective_to = date_to or now

    _audit_log_financial_access(
        endpoint=f"GET /analytics/goldsmith-accuracy/{user_id}",
        user=current_user,
        context={
            "queried_user_id": user_id,
            "date_from": effective_from.isoformat(),
            "date_to": effective_to.isoformat(),
        },
    )

    # Fetch workshop stats for the same period to enable comparison
    workshop_stats = await ComparisonService.get_workshop_statistics(
        db, effective_from, effective_to
    )

    accuracy = await ComparisonService.get_goldsmith_accuracy(
        db, user_id, workshop_stats=workshop_stats
    )
    if not accuracy:
        raise HTTPException(
            status_code=404,
            detail=f"Kein Benutzer mit ID {user_id} gefunden.",
        )
    return accuracy
