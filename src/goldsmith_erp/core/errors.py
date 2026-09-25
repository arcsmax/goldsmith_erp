"""Domain error hierarchy and the single API error envelope (ARCH-08, W3-07).

Services raise a :class:`DomainError` subclass instead of building an
``HTTPException`` by hand. One exception handler (registered in ``main.py``
via :func:`register_domain_error_handler`) renders every domain error as::

    {"detail": <German message>, "code": "<area>.<reason>", "extra": {...}}

``detail`` stays so the existing frontend error handling (which reads
``response.data.detail``) keeps working; ``code`` is the new machine-readable
slug the frontend can branch on; ``extra`` carries non-sensitive context
(ids, allowed next states). Never put PII, prices or free text into
``extra`` or ``detail``.

Legacy structured detail
    A few errors predate this module and already ship a dict ``detail``
    that the frontend reads (e.g. ``detail.code == "TIMER_POSSIBLY_STALE"``).
    Those pass ``legacy_detail=`` so the wire ``detail`` is unchanged for one
    release; the top-level ``code``/``extra`` are added alongside.

Transitional base class
    ``DomainError`` still subclasses ``HTTPException`` so the routers' existing
    ``except HTTPException: raise`` guards and the service tests that assert
    ``pytest.raises(HTTPException)`` keep working during the migration. The
    registered handler takes precedence over FastAPI's default one (Starlette
    resolves handlers along the exception's MRO). Drop the ``HTTPException``
    base once no router or test depends on it.
"""

from __future__ import annotations

import logging
from typing import Any, ClassVar, Mapping, Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class DomainError(HTTPException):
    """Base class: a business rule refused the request."""

    status_code_default: ClassVar[int] = 400
    code_default: ClassVar[str] = "domain.error"

    def __init__(
        self,
        detail: str,
        *,
        code: Optional[str] = None,
        extra: Optional[Mapping[str, Any]] = None,
        legacy_detail: Optional[Mapping[str, Any]] = None,
        headers: Optional[dict[str, str]] = None,
    ) -> None:
        self.message = detail
        self.code = code or self.code_default
        self.extra: dict[str, Any] = dict(extra or {})
        wire_detail: Any = dict(legacy_detail) if legacy_detail else detail
        super().__init__(
            status_code=self.status_code_default,
            detail=wire_detail,
            headers=headers,
        )

    def __str__(self) -> str:
        # The German message, not Starlette's "<status>: <detail>" form, so
        # callers that surface ``str(exc)`` keep showing user-facing text.
        return self.message

    def to_body(self) -> dict[str, Any]:
        """The JSON envelope rendered by the registered handler."""
        return {"detail": self.detail, "code": self.code, "extra": self.extra}


class NotFoundError(DomainError):
    """404: the referenced entity does not exist (or is not visible)."""

    status_code_default = 404
    code_default = "not_found"


class ConflictError(DomainError):
    """409: the entity's current state forbids the action."""

    status_code_default = 409
    code_default = "conflict"


class ForbiddenError(DomainError):
    """403: the caller may not perform this action on this entity."""

    status_code_default = 403
    code_default = "forbidden"


class DomainValidationError(DomainError):
    """422: the input is well-formed but violates a business rule.

    Named ``DomainValidationError`` to avoid shadowing pydantic's
    ``ValidationError``.
    """

    status_code_default = 422
    code_default = "validation_failed"


class UpstreamError(DomainError):
    """502: a dependency (SMTP, price feed) failed."""

    status_code_default = 502
    code_default = "upstream_failed"


async def domain_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Render any :class:`DomainError` as the ``{detail, code, extra}`` envelope."""
    if not isinstance(exc, DomainError):  # pragma: no cover - registration guard
        raise exc
    logger.info(
        "domain_error",
        extra={
            "code": exc.code,
            "status_code": exc.status_code,
            "path": request.url.path,
            "method": request.method,
        },
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_body(),
        headers=exc.headers,
    )


def register_domain_error_handler(app: FastAPI) -> None:
    """Attach the one domain error handler to ``app``."""
    app.add_exception_handler(DomainError, domain_error_handler)
