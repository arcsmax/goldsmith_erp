"""Request logs must not contain query strings (SEC-05).

Customer searches send names, emails and phone numbers as query parameters
(``GET /customers/search?q=...``). Logging the full URL wrote that PII into
container logs in plaintext, which GDPR erasure cannot reach.
"""

import logging

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from goldsmith_erp.middleware.logging import RequestLoggingMiddleware

SENTINEL = "Brunhilde-Sentinel-4711"


def _app(fail: bool = False) -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/api/v1/customers/search")
    async def search(q: str) -> dict[str, str]:
        if fail:
            raise RuntimeError("boom")
        return {"ok": "yes"}

    return app


def _record_text(record: logging.LogRecord) -> str:
    return " ".join(str(value) for value in record.__dict__.values())


def _middleware_records(caplog) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.name == "goldsmith_erp.middleware.logging"]


@pytest.mark.asyncio
async def test_completed_request_log_omits_query_string(caplog):
    caplog.set_level(logging.INFO, logger="goldsmith_erp.middleware.logging")
    transport = ASGITransport(app=_app())

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/customers/search", params={"q": SENTINEL})

    assert response.status_code == 200
    records = _middleware_records(caplog)
    assert records, "expected request log records"
    for record in records:
        assert SENTINEL not in _record_text(record)
    assert any(getattr(r, "path", None) == "/api/v1/customers/search" for r in records)


@pytest.mark.asyncio
async def test_failed_request_log_omits_query_string(caplog):
    caplog.set_level(logging.INFO, logger="goldsmith_erp.middleware.logging")
    transport = ASGITransport(app=_app(fail=True), raise_app_exceptions=False)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.get("/api/v1/customers/search", params={"q": SENTINEL})

    records = _middleware_records(caplog)
    assert any(r.levelno == logging.ERROR for r in records)
    for record in records:
        assert SENTINEL not in _record_text(record)
