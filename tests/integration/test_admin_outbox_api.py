# tests/integration/test_admin_outbox_api.py
"""ADMIN outbox endpoints (ARCH-04 / ARCH-12): list, filter, retry, audit."""

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from goldsmith_erp.db.models import CustomerAuditLog, OutboxMessage, OutboxStatus

pytestmark = pytest.mark.asyncio

URL = "/api/v1/admin/outbox"


@pytest.fixture(autouse=True)
def _patch_middleware_session(monkeypatch, db_session):
    """Audit middleware writes to the test engine (see audit middleware tests)."""
    from goldsmith_erp.middleware import audit_logging

    factory = sessionmaker(
        bind=db_session.bind, class_=AsyncSession, expire_on_commit=False
    )
    monkeypatch.setattr(audit_logging, "AsyncSessionLocal", factory)


async def _add(db: AsyncSession, status: str, attempts: int = 0) -> OutboxMessage:
    msg = OutboxMessage(
        kind="customer_update",
        payload={"update_id": 1, "user_id": 1},
        status=status,
        attempts=attempts,
        last_error="delivery_failed" if status != "pending" else None,
    )
    db.add(msg)
    await db.commit()
    await db.refresh(msg)
    return msg


async def test_admin_lists_with_counts_and_status_filter(
    client: AsyncClient, db_session: AsyncSession, admin_auth_headers: dict
):
    await _add(db_session, "pending")
    dead = await _add(db_session, "dead", attempts=6)

    resp = await client.get(URL, headers=admin_auth_headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["counts"] == {"pending": 1, "sent": 0, "failed": 0, "dead": 1}
    assert body["mode"] in {"inline", "worker"}
    assert len(body["items"]) == 2

    resp = await client.get(URL, params={"status": "dead"}, headers=admin_auth_headers)
    assert [i["id"] for i in resp.json()["items"]] == [dead.id]


async def test_invalid_status_is_422(client: AsyncClient, admin_auth_headers: dict):
    resp = await client.get(URL, params={"status": "bogus"}, headers=admin_auth_headers)
    assert resp.status_code == 422


async def _assert_forbidden(client: AsyncClient, headers: dict) -> None:
    assert (await client.get(URL, headers=headers)).status_code == 403
    assert (await client.post(f"{URL}/1/retry", headers=headers)).status_code == 403


async def test_goldsmith_is_forbidden(
    client: AsyncClient, goldsmith_auth_headers: dict
):
    await _assert_forbidden(client, goldsmith_auth_headers)


async def test_viewer_is_forbidden(client: AsyncClient, viewer_auth_headers: dict):
    await _assert_forbidden(client, viewer_auth_headers)


async def test_retry_dead_row_resets_it_and_is_audited(
    client: AsyncClient, db_session: AsyncSession, admin_auth_headers: dict
):
    dead = await _add(db_session, "dead", attempts=6)

    resp = await client.post(f"{URL}/{dead.id}/retry", headers=admin_auth_headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == OutboxStatus.PENDING.value
    assert resp.json()["attempts"] == 0

    db_session.expire_all()
    audits = (
        (
            await db_session.execute(
                select(CustomerAuditLog).where(
                    CustomerAuditLog.entity == "outbox_message"
                )
            )
        )
        .scalars()
        .all()
    )
    assert audits, "admin/outbox requests must be audit-logged"


async def test_retry_pending_is_409_and_missing_is_404(
    client: AsyncClient, db_session: AsyncSession, admin_auth_headers: dict
):
    pending = await _add(db_session, "pending")
    resp = await client.post(f"{URL}/{pending.id}/retry", headers=admin_auth_headers)
    assert resp.status_code == 409
    resp = await client.post(f"{URL}/999999/retry", headers=admin_auth_headers)
    assert resp.status_code == 404
