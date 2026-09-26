"""Role-aware response projection for financial data and design IP.

SEC-01 / SEC-09 / GDPR-03 / GDPR-04 (docs/review/2026-09-25/).

CLAUDE.md "Data Privacy Rules":
- Pricing, payment info, material costs -> ADMIN and GOLDSMITH only.
- Design descriptions / design files -> GOLDSMITH or ADMIN only.

Shared read endpoints (repairs, materials, customer stats, orders) keep
serving VIEWER, but the fields in the relevant data class are removed from
the response for callers that lack ``Permission.FINANCIAL_VIEW`` /
``Permission.DESIGN_VIEW``. Endpoints that are financial by nature use
:func:`ensure_financial_view` (403) instead.

This generalises the C5 order projection (api/routers/orders.py), which used a
role check; here the decision is permission-based so a future role only needs
an entry in ``ROLE_PERMISSIONS``.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional, Type, Union

from fastapi import HTTPException, status
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from goldsmith_erp.core.permissions import Permission, has_permission
from goldsmith_erp.db.models import User

# Pydantic ``exclude`` accepts a set of names or a nested mapping
# (e.g. {"materials": {"__all__": {"unit_price"}}}).
ExcludeSpec = Union[set[str], dict[str, Any]]


def can_view_financial(user: User) -> bool:
    """True when the caller may see prices, costs and revenue."""
    return has_permission(user, Permission.FINANCIAL_VIEW)


def can_view_design(user: User) -> bool:
    """True when the caller may see design descriptions and photos."""
    return has_permission(user, Permission.DESIGN_VIEW)


def ensure_financial_view(user: User) -> None:
    """Raise 403 unless the caller holds FINANCIAL_VIEW."""
    if not can_view_financial(user):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Permission denied: {Permission.FINANCIAL_VIEW.value} required",
        )


def build_excludes(
    user: User,
    *,
    financial: Iterable[str] = (),
    design: Iterable[str] = (),
    nested_financial: Optional[Mapping[str, Iterable[str]]] = None,
) -> ExcludeSpec:
    """Return the pydantic ``exclude`` spec for the caller.

    Args:
        financial: top-level fields stripped without FINANCIAL_VIEW.
        design: top-level fields stripped without DESIGN_VIEW.
        nested_financial: list-valued field -> inner fields stripped from
            every item without FINANCIAL_VIEW.

    An empty result means "serialise everything".
    """
    top: set[str] = set()
    nested: dict[str, Any] = {}
    if not can_view_financial(user):
        top.update(financial)
        for list_field, inner in (nested_financial or {}).items():
            nested[list_field] = {"__all__": set(inner)}
    if not can_view_design(user):
        top.update(design)
    if not nested:
        return top
    spec: dict[str, Any] = {name: True for name in top}
    for list_field, inner_spec in nested.items():
        if list_field not in top:
            spec[list_field] = inner_spec
    return spec


def project(schema: Type[BaseModel], obj: Any, exclude: ExcludeSpec) -> dict[str, Any]:
    """Validate one ORM object / dict into ``schema`` and dump without ``exclude``."""
    return schema.model_validate(obj).model_dump(exclude=exclude or None)


def project_response(
    schema: Type[BaseModel], data: Any, exclude: ExcludeSpec
) -> JSONResponse:
    """Serialise a single object or a list through ``schema`` minus ``exclude``."""
    if isinstance(data, (list, tuple)):
        payload: Any = [project(schema, item, exclude) for item in data]
    else:
        payload = project(schema, data, exclude)
    return JSONResponse(content=jsonable_encoder(payload))
