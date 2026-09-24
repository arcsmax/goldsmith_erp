"""Public customer portal is off by default (SEC-10, decision D-03).

The audit found the portal mounted and internet-reachable although the
product decision (D-03) is "no live portal for now" — numeric order ids plus
a known e-mail let anyone on the LAN enumerate which orders belong to a
customer. The router is now gated behind `settings.CUSTOMER_PORTAL_ENABLED`
(default False); every request 404s while it is off. `test_portal.py` covers
the enabled behaviour by opting back in via an autouse fixture.
"""

import pytest
from httpx import AsyncClient

from goldsmith_erp.api.routers.customer_portal import limiter as portal_limiter
from goldsmith_erp.core.config import Settings, settings

LOOKUP_URL = "/api/v1/portal/lookup"
STATUS_URL = "/api/v1/portal/status/some-token"


@pytest.fixture(autouse=True)
def _reset_portal_limiter():
    """Isolate this file's rate-limit bucket from test_portal.py's traffic."""
    portal_limiter.reset()
    yield
    portal_limiter.reset()


def test_customer_portal_enabled_defaults_to_false():
    """The flag itself defaults off — a fresh checkout never mounts a live portal."""
    assert Settings.model_fields["CUSTOMER_PORTAL_ENABLED"].default is False


@pytest.mark.asyncio
async def test_portal_lookup_returns_404_when_disabled(
    client: AsyncClient, monkeypatch
):
    monkeypatch.setattr(settings, "CUSTOMER_PORTAL_ENABLED", False)

    response = await client.post(
        LOOKUP_URL,
        json={"reference_number": "1", "email": "nobody@example.com"},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_portal_status_by_token_returns_404_when_disabled(
    client: AsyncClient, monkeypatch
):
    monkeypatch.setattr(settings, "CUSTOMER_PORTAL_ENABLED", False)

    response = await client.get(STATUS_URL)

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_disabled_portal_404_is_not_a_business_not_found(
    client: AsyncClient, monkeypatch
):
    """The disabled-router 404 must not be mistaken for "order not found" —
    it never reaches the handler's own 404 branches at all."""
    monkeypatch.setattr(settings, "CUSTOMER_PORTAL_ENABLED", False)

    response = await client.post(
        LOOKUP_URL,
        json={"reference_number": "999999999", "email": "nobody@example.com"},
    )

    assert response.status_code == 404
    assert (
        "Auftrag nicht gefunden" not in response.json()["detail"]
    ), "expected the disabled-router 404, not the business-logic 404"


@pytest.mark.asyncio
async def test_portal_reaches_business_logic_once_enabled(
    client: AsyncClient, monkeypatch
):
    """Regression guard: flipping the flag on unblocks the router again."""
    monkeypatch.setattr(settings, "CUSTOMER_PORTAL_ENABLED", True)

    response = await client.post(
        LOOKUP_URL,
        json={"reference_number": "999999999", "email": "nobody@example.com"},
    )

    assert response.status_code == 404
    assert "Auftrag nicht gefunden" in response.json()["detail"]
