"""DomainError hierarchy and the single error envelope (ARCH-08, W3-07)."""

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient

from goldsmith_erp.core.errors import (
    ConflictError,
    DomainError,
    DomainValidationError,
    ForbiddenError,
    NotFoundError,
    domain_error_handler,
    register_domain_error_handler,
)
from goldsmith_erp.db.models import OrderStatusEnum
from goldsmith_erp.services.order_workflow import (
    InvalidStatusTransitionError,
    PunzierungRequiredError,
    TransitionReasonRequiredError,
)
from goldsmith_erp.services.scrap_gold_service import ScrapGoldLockedError
from goldsmith_erp.services.time_tracking_service import (
    CrossUserTimerError,
    TimerAlreadyRunningError,
    TimerPossiblyStaleError,
)


def _app_raising(exc: Exception) -> FastAPI:
    app = FastAPI()
    register_domain_error_handler(app)

    @app.get("/boom")
    async def boom() -> None:
        raise exc

    return app


async def _get(app: FastAPI):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://t") as client:
        return await client.get("/boom")


@pytest.mark.parametrize(
    ("cls", "status"),
    [
        (NotFoundError, 404),
        (ConflictError, 409),
        (ForbiddenError, 403),
        (DomainValidationError, 422),
    ],
)
def test_subclasses_carry_status_codes(cls, status):
    err = cls("Nicht gefunden", code="x.y")
    assert err.status_code == status
    assert err.code == "x.y"
    assert isinstance(err, DomainError)
    # Transitional: routers still catch HTTPException.
    assert isinstance(err, HTTPException)
    assert str(err) == "Nicht gefunden"


def test_default_code_when_none_given():
    assert NotFoundError("x").code == "not_found"
    assert ConflictError("x").code == "conflict"


@pytest.mark.asyncio
async def test_handler_renders_detail_code_extra():
    app = _app_raising(
        ConflictError(
            "Auftrag ist gesperrt.",
            code="order.locked",
            extra={"order_id": 7},
        )
    )
    response = await _get(app)
    assert response.status_code == 409
    assert response.json() == {
        "detail": "Auftrag ist gesperrt.",
        "code": "order.locked",
        "extra": {"order_id": 7},
    }


@pytest.mark.asyncio
async def test_handler_keeps_legacy_structured_detail():
    app = _app_raising(TimerPossiblyStaleError(old_entry_id="abc", running_minutes=45))
    response = await _get(app)
    body = response.json()
    assert response.status_code == 409
    assert body["code"] == "time_entry.possibly_stale"
    # The frontend reads detail.code today (TimeTrackingContext.tsx).
    assert body["detail"]["code"] == "TIMER_POSSIBLY_STALE"
    assert body["extra"] == {"old_entry_id": "abc", "running_minutes": 45}


@pytest.mark.asyncio
async def test_plain_http_exception_is_untouched():
    app = _app_raising(HTTPException(status_code=404, detail="weg"))
    response = await _get(app)
    assert response.json() == {"detail": "weg"}


def test_main_app_registers_the_handler():
    from goldsmith_erp.main import app

    assert app.exception_handlers.get(DomainError) is domain_error_handler


@pytest.mark.parametrize(
    ("exc", "code", "status"),
    [
        (
            InvalidStatusTransitionError(
                OrderStatusEnum.NEW, OrderStatusEnum.DELIVERED
            ),
            "order.invalid_transition",
            409,
        ),
        (
            TransitionReasonRequiredError(OrderStatusEnum.ON_HOLD),
            "order.reason_required",
            422,
        ),
        (
            PunzierungRequiredError(order_id=3, alloy="585"),
            "order.hallmark_required",
            409,
        ),
        (TimerAlreadyRunningError("e1"), "time_entry.already_running", 409),
        (
            CrossUserTimerError(old_entry_id="e", caller_user_id=1, owner_user_id=2),
            "time_entry.cross_user_forbidden",
            403,
        ),
        (ScrapGoldLockedError(5), "scrap_gold.locked", 409),
    ],
)
def test_service_errors_have_code_slugs(exc, code, status):
    assert isinstance(exc, DomainError)
    assert exc.code == code
    assert exc.status_code == status
    assert "." in exc.code


def test_cross_user_error_does_not_leak_owner_in_extra():
    exc = CrossUserTimerError(old_entry_id="e", caller_user_id=1, owner_user_id=2)
    assert "owner_user_id" not in exc.extra
    assert exc.owner_user_id == 2


def test_scrap_gold_locked_message_is_german_text():
    exc = ScrapGoldLockedError(5)
    assert "unterschrieben" in str(exc)
    assert exc.extra == {"scrap_gold_id": 5}
