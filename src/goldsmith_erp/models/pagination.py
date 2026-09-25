"""Generic paged list envelope and its query dependency (ARCH-08, W3-08).

Paged mode
    A list request that carries ``offset`` gets a :class:`Page`::

        {"items": [...], "total": 137, "limit": 50, "offset": 0,
         "next_offset": 50}

    ``limit`` defaults to 50 and is capped at 200 (422 above that);
    ``next_offset`` is ``None`` on the last page.

Legacy mode (one release only)
    A request WITHOUT ``offset`` keeps the old response shape (a plain list;
    for quotes the old ``QuoteListResponse``) and the old ``skip``/``limit``
    semantics, now capped at 500 (SEC-16). Such responses carry the header
    ``X-Deprecated-List: true`` so the frontend can migrate page by page.

    The trigger is ``offset`` rather than "any of limit/offset" because the
    current frontend already sends ``limit`` (and ``skip``) on every list
    call; switching on ``limit`` would break those screens today.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Generic, Iterable, List, Optional, TypeVar

from fastapi import Query
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from goldsmith_erp.core.errors import DomainValidationError

T = TypeVar("T")

DEFAULT_PAGE_LIMIT = 50
MAX_PAGE_LIMIT = 200
LEGACY_MAX_LIMIT = 500
DEPRECATED_LIST_HEADER = "X-Deprecated-List"


class Page(BaseModel, Generic[T]):
    """One page of a server-side filtered, sorted list."""

    items: List[T]
    total: int = Field(ge=0, description="Anzahl aller Treffer über alle Seiten")
    limit: int = Field(ge=1, le=MAX_PAGE_LIMIT)
    offset: int = Field(ge=0)
    next_offset: Optional[int] = Field(
        default=None, description="Offset der nächsten Seite; null auf der letzten"
    )


@dataclass(frozen=True)
class PageParams:
    """Resolved paging parameters for one list request."""

    limit: int
    offset: int
    is_paged: bool

    def next_offset(self, total: int) -> Optional[int]:
        following = self.offset + self.limit
        return following if following < total else None


def make_page_params(
    legacy_default_limit: int = 100,
    legacy_max_limit: int = LEGACY_MAX_LIMIT,
) -> Callable[..., PageParams]:
    """Build a ``Depends`` callable that keeps an endpoint's legacy defaults."""

    def page_params(
        offset: Optional[int] = Query(
            None,
            ge=0,
            description=(
                "Offset der Seite. Wenn gesetzt, antwortet der Endpunkt mit "
                "einer Page-Hülle {items, total, limit, offset, next_offset}."
            ),
        ),
        limit: Optional[int] = Query(
            None,
            ge=1,
            le=legacy_max_limit,
            description=(
                f"Seitengröße (Standard {DEFAULT_PAGE_LIMIT}, "
                f"maximal {MAX_PAGE_LIMIT} mit offset)"
            ),
        ),
        skip: int = Query(
            0,
            ge=0,
            deprecated=True,
            description="Veraltet: nur ohne offset (Listenantwort).",
        ),
    ) -> PageParams:
        if offset is None:
            return PageParams(
                limit=limit if limit is not None else legacy_default_limit,
                offset=skip,
                is_paged=False,
            )
        effective = limit if limit is not None else DEFAULT_PAGE_LIMIT
        if effective > MAX_PAGE_LIMIT:
            raise DomainValidationError(
                f"limit darf höchstens {MAX_PAGE_LIMIT} sein.",
                code="pagination.limit_too_large",
                extra={"max_limit": MAX_PAGE_LIMIT},
            )
        return PageParams(limit=effective, offset=offset, is_paged=True)

    return page_params


def page_response(items: Iterable[Any], total: int, params: PageParams) -> JSONResponse:
    """Render already-projected ``items`` (dicts) as a :class:`Page` body."""
    body = {
        "items": list(items),
        "total": total,
        "limit": params.limit,
        "offset": params.offset,
        "next_offset": params.next_offset(total),
    }
    return JSONResponse(content=jsonable_encoder(body))


def legacy_list_response(payload: Any) -> JSONResponse:
    """Render the old response shape and flag it as deprecated."""
    return JSONResponse(
        content=jsonable_encoder(payload),
        headers={DEPRECATED_LIST_HEADER: "true"},
    )
