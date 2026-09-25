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
    ``sort`` (below) is accepted but ignored in this mode — the legacy
    ordering stays exactly what it was before W3-sort.

    The trigger is ``offset`` rather than "any of limit/offset" because the
    current frontend already sends ``limit`` (and ``skip``) on every list
    call; switching on ``limit`` would break those screens today.

Sort (paged mode only, W3-sort)
    ``sort`` is a comma-separated list of ``field`` (ascending) or
    ``-field`` (descending), e.g. ``-created_at,status``. Each endpoint
    whitelists its own sortable fields (see the per-endpoint
    ``*_SORT_FIELDS`` mapping in ``services/list_queries.py``); an unknown
    field is a 422 ``DomainValidationError`` with code
    ``pagination.invalid_sort_field`` rather than being silently ignored or
    guessed at. Encrypted PII columns (e.g. customer name) are never
    whitelisted — Fernet ciphertext has no stable sort order.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Generic, Iterable, List, Optional, Sequence, TypeVar

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
    sort: Optional[str] = None

    def next_offset(self, total: int) -> Optional[int]:
        following = self.offset + self.limit
        return following if following < total else None


def make_page_params(
    legacy_default_limit: int = 100,
    legacy_max_limit: int = LEGACY_MAX_LIMIT,
    sort_fields: Sequence[str] = (),
) -> Callable[..., PageParams]:
    """Build a ``Depends`` callable that keeps an endpoint's legacy defaults.

    ``sort_fields`` only documents the endpoint's whitelist in OpenAPI; the
    whitelist itself — and the 422 on an unknown field — is enforced where
    ``PageParams.sort`` is consumed (``services/list_queries.apply_sort``).
    """

    if sort_fields:
        sort_description = (
            "Sortierung (nur mit offset): kommagetrennte Feldnamen, "
            "absteigend mit vorangestelltem '-' (z. B. '-"
            f"{sort_fields[0]}'). Erlaubte Felder: {', '.join(sort_fields)}. "
            "Ein unbekanntes Feld ergibt 422 (code "
            "pagination.invalid_sort_field)."
        )
    else:
        sort_description = "Sortierung (nur mit offset)."

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
        sort: Optional[str] = Query(
            None,
            max_length=200,
            description=sort_description,
        ),
    ) -> PageParams:
        if offset is None:
            return PageParams(
                limit=limit if limit is not None else legacy_default_limit,
                offset=skip,
                is_paged=False,
                sort=sort,
            )
        effective = limit if limit is not None else DEFAULT_PAGE_LIMIT
        if effective > MAX_PAGE_LIMIT:
            raise DomainValidationError(
                f"limit darf höchstens {MAX_PAGE_LIMIT} sein.",
                code="pagination.limit_too_large",
                extra={"max_limit": MAX_PAGE_LIMIT},
            )
        return PageParams(limit=effective, offset=offset, is_paged=True, sort=sort)

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
