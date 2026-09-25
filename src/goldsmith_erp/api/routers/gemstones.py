"""Order gemstones (W2-06, DOM-04): ``/orders/{id}/gemstones`` and ``/gemstones/{id}``.

Reads need ORDER_VIEW; a caller without FINANCIAL_VIEW gets no cost fields and
one without DESIGN_VIEW (VIEWER) only type, count and the Kundenstein flag.
Writes need ORDER_EDIT (GOLDSMITH, ADMIN).
"""

from __future__ import annotations

from typing import Any, Dict, List

from fastapi import APIRouter, Depends, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.api.deps import get_current_user
from goldsmith_erp.api.role_projection import build_excludes, project
from goldsmith_erp.core.permissions import Permission, require_permission
from goldsmith_erp.db.models import User
from goldsmith_erp.db.session import get_db
from goldsmith_erp.models.gemstone import (
    GEMSTONE_DESIGN_FIELDS,
    GEMSTONE_FINANCIAL_FIELDS,
    GemstoneCreate,
    GemstoneRead,
    GemstoneUpdate,
)
from goldsmith_erp.services.gemstone_service import GemstoneService

router = APIRouter()


def project_gemstones(user: User, stones: List[Any]) -> List[Dict[str, Any]]:
    """Serialise stones for ``user`` (cost: FINANCIAL_VIEW, details: DESIGN_VIEW)."""
    exclude = build_excludes(
        user, financial=GEMSTONE_FINANCIAL_FIELDS, design=GEMSTONE_DESIGN_FIELDS
    )
    return [project(GemstoneRead, stone, exclude) for stone in stones]


def _json(user: User, stones: List[Any], status_code: int = 200) -> JSONResponse:
    return JSONResponse(
        content=jsonable_encoder(project_gemstones(user, stones)),
        status_code=status_code,
    )


@router.get("/orders/{order_id}/gemstones", response_model=List[GemstoneRead])
@require_permission(Permission.ORDER_VIEW)  # type: ignore[misc]
async def list_gemstones(
    order_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JSONResponse:
    """Steine eines Auftrags."""
    stones = await GemstoneService.list_for_order(db, order_id, current_user)
    return _json(current_user, stones)


@router.post(
    "/orders/{order_id}/gemstones",
    response_model=GemstoneRead,
    status_code=status.HTTP_201_CREATED,
)
@require_permission(Permission.ORDER_EDIT)  # type: ignore[misc]
async def create_gemstone(
    order_id: int,
    body: GemstoneCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JSONResponse:
    """Stein zum Auftrag hinzufügen."""
    stone = await GemstoneService.create(db, order_id, body, current_user)
    payload = project_gemstones(current_user, [stone])[0]
    return JSONResponse(content=jsonable_encoder(payload), status_code=201)


@router.patch("/gemstones/{gemstone_id}", response_model=GemstoneRead)
@require_permission(Permission.ORDER_EDIT)  # type: ignore[misc]
async def update_gemstone(
    gemstone_id: int,
    body: GemstoneUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> JSONResponse:
    """Stein bearbeiten."""
    stone = await GemstoneService.update(db, gemstone_id, body, current_user)
    return JSONResponse(
        content=jsonable_encoder(project_gemstones(current_user, [stone])[0])
    )


@router.delete("/gemstones/{gemstone_id}", status_code=status.HTTP_204_NO_CONTENT)
@require_permission(Permission.ORDER_EDIT)  # type: ignore[misc]
async def delete_gemstone(
    gemstone_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Stein entfernen."""
    await GemstoneService.delete(db, gemstone_id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
