"""Real client IP resolution behind the Caddy -> nginx -> backend chain (SEC-04).

X-Forwarded-For is honoured only when the direct TCP peer is a configured
trusted proxy, and the chain is walked right-to-left so a client-supplied
(prepended) entry can never win over the hop our own proxy appended.
"""

import pytest
from pydantic import ValidationError
from starlette.requests import Request

from goldsmith_erp.core.client_ip import get_client_ip, parse_trusted_networks
from goldsmith_erp.core.config import Settings

NGINX_PEER = "10.89.0.5"  # compose network (trusted by default)
CADDY_HOP = "10.89.0.4"
LAN_CLIENT = "192.168.1.50"  # workshop LAN device (not a proxy)
SPOOFED = "6.6.6.6"


def _request(peer: str | None, xff: str | None = None, real_ip: str | None = None):
    headers: list[tuple[bytes, bytes]] = []
    if xff is not None:
        headers.append((b"x-forwarded-for", xff.encode()))
    if real_ip is not None:
        headers.append((b"x-real-ip", real_ip.encode()))
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": headers,
        "client": (peer, 12345) if peer else None,
    }
    return Request(scope)


class TestGetClientIp:
    def test_untrusted_peer_ignores_forwarded_header(self):
        request = _request(LAN_CLIENT, xff=SPOOFED)

        assert get_client_ip(request) == LAN_CLIENT

    def test_trusted_proxy_chain_yields_real_client(self):
        request = _request(NGINX_PEER, xff=f"{LAN_CLIENT}, {CADDY_HOP}")

        assert get_client_ip(request) == LAN_CLIENT

    def test_client_prepended_entry_cannot_win(self):
        request = _request(NGINX_PEER, xff=f"{SPOOFED}, {LAN_CLIENT}, {CADDY_HOP}")

        assert get_client_ip(request) == LAN_CLIENT

    def test_trusted_peer_without_header_uses_peer(self):
        request = _request(NGINX_PEER)

        assert get_client_ip(request) == NGINX_PEER

    def test_garbage_forwarded_entry_is_not_used_as_key(self):
        request = _request(NGINX_PEER, xff="not-an-ip")

        assert get_client_ip(request) == NGINX_PEER

    def test_trusted_peer_real_ip_header_fallback(self):
        request = _request(NGINX_PEER, real_ip=LAN_CLIENT)

        assert get_client_ip(request) == LAN_CLIENT

    def test_missing_client_returns_unknown(self):
        assert get_client_ip(_request(None, xff=SPOOFED)) == "unknown"

    def test_custom_trusted_networks_narrow_trust(self):
        only_loopback = parse_trusted_networks(["127.0.0.1/32"])
        request = _request(NGINX_PEER, xff=SPOOFED)

        assert get_client_ip(request, only_loopback) == NGINX_PEER

    def test_all_hops_trusted_returns_leftmost(self):
        # A LAN client whose address is itself inside a trusted range.
        request = _request(NGINX_PEER, xff=f"10.0.0.7, {CADDY_HOP}")

        assert get_client_ip(request) == "10.0.0.7"


class TestTrustedProxiesSetting:
    def test_default_trusts_loopback_and_container_ranges_not_lan(self):
        settings = Settings(_env_file=None, DEBUG=True)
        networks = parse_trusted_networks(settings.TRUSTED_PROXIES)

        request = _request(LAN_CLIENT, xff=SPOOFED)
        assert get_client_ip(request, networks) == LAN_CLIENT
        assert get_client_ip(_request("127.0.0.1", xff=LAN_CLIENT), networks) == (
            LAN_CLIENT
        )

    def test_comma_separated_env_value_parses(self, monkeypatch):
        monkeypatch.setenv("TRUSTED_PROXIES", "127.0.0.1/32, 10.89.0.0/24")

        settings = Settings(_env_file=None, DEBUG=True)

        assert settings.TRUSTED_PROXIES == ["127.0.0.1/32", "10.89.0.0/24"]

    def test_invalid_network_fails_loudly(self):
        with pytest.raises(ValidationError) as exc_info:
            Settings(_env_file=None, DEBUG=True, TRUSTED_PROXIES=["not-a-cidr"])

        assert "TRUSTED_PROXIES" in str(exc_info.value)


class TestLoginLimiterKeys:
    def test_login_key_uses_real_client_ip(self):
        from goldsmith_erp.api.routers.auth import _login_ip_username_key

        request = _request("127.0.0.1", xff=f"{LAN_CLIENT}, {CADDY_HOP}")
        request.state.login_username = "anne@example.test"

        assert _login_ip_username_key(request) == f"{LAN_CLIENT}|anne@example.test"

    def test_auth_limiter_default_key_uses_real_client_ip(self):
        from goldsmith_erp.api.routers.auth import limiter

        request = _request("127.0.0.1", xff=LAN_CLIENT)

        assert limiter._key_func(request) == LAN_CLIENT
