"""
B2 — Adversarial tests for core/client_ip.get_client_ip (SEC-04), beyond
tests/unit/test_client_ip.py's existing coverage (untrusted-peer spoofing,
3-hop chains, garbage-at-the-rightmost-position, all-hops-trusted).

New angles: IPv6 peers/chains, a malformed hop INSIDE (not at the edge of)
an otherwise-trusted chain, and an IPv4-mapped-IPv6 peer representation.
"""

from starlette.requests import Request

from goldsmith_erp.core.client_ip import get_client_ip

NGINX_PEER_V4 = "10.89.0.5"
CADDY_HOP_V4 = "10.89.0.4"


def _request(peer: str | None, xff: str | None = None):
    headers: list[tuple[bytes, bytes]] = []
    if xff is not None:
        headers.append((b"x-forwarded-for", xff.encode()))
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": headers,
        "client": (peer, 12345) if peer else None,
    }
    return Request(scope)


class TestIPv6Chains:
    def test_ipv6_loopback_peer_trusted_real_ipv6_client_extracted(self):
        """::1 is in the default TRUSTED_PROXIES (fc00::/7 does NOT cover
        loopback; ::1/128 is listed explicitly) — confirm an IPv6 client
        behind an IPv6 loopback proxy is still resolved correctly."""
        request = _request("::1", xff="2001:db8::dead:beef, ::1")
        assert get_client_ip(request) == "2001:db8::dead:beef"

    def test_ipv6_unique_local_peer_trusted_spoofed_header_from_lan_ignored(self):
        """fc00::/7 (ULA) is trusted by default. An untrusted public IPv6
        client behind it must still be extracted, not the peer itself,
        and a spoofed prepended hop must not win."""
        request = _request(
            "fdaa::1", xff="2001:4860:4860::8888, fdaa::1"
        )
        assert get_client_ip(request) == "2001:4860:4860::8888"

    def test_untrusted_ipv6_peer_ignores_forwarded_header(self):
        request = _request("2001:db8::1", xff="10.0.0.1")
        assert get_client_ip(request) == "2001:db8::1"


class TestMalformedHopInsideTrustedChain:
    def test_malformed_hop_between_two_trusted_hops_returns_proxy_not_peer(self):
        """Documents an intentional but narrow limitation: '_client_from_chain'
        stops at the FIRST malformed token it meets while walking
        right-to-left and returns whatever was verified so far. If a
        malformed entry sits between two trusted hops (e.g. a
        misconfigured mid-chain proxy that injects a non-IP token, since a
        client's own prepended content always sits to the LEFT of every
        real proxy append), the function returns a trusted PROXY address as
        the rate-limit / audit-log key — not the real client, and not a
        clearly-flagged 'unknown' sentinel either. This cannot be triggered
        by an external client alone in the documented 2-hop
        Caddy->nginx topology (verified in test_client_ip.py's
        test_garbage_forwarded_entry_is_not_used_as_key, where the garbage
        sits at the rightmost/first-checked position and correctly falls
        back to peer) — but it silently degrades observability the moment
        an intermediate hop ever forwards a malformed value.
        """
        request = _request(
            NGINX_PEER_V4, xff=f"garbage-not-an-ip, {CADDY_HOP_V4}"
        )
        result = get_client_ip(request)
        # This is the documented (if debatable) fallback behaviour: the
        # last verified TRUSTED hop, not the untrusted peer and not the
        # unreachable "real" client further left.
        assert result == CADDY_HOP_V4, (
            f"get_client_ip returned {result!r}; expected the documented "
            f"fallback {CADDY_HOP_V4!r} (a proxy address, not a client "
            "address) — if this changed, re-check whether rate-limit keys "
            "can now collapse onto a shared value instead."
        )


class TestIPv4MappedIPv6PeerNotRecognisedAsTrusted:
    def test_ipv4_mapped_ipv6_peer_is_not_matched_against_ipv4_trusted_cidrs(self):
        """Some ASGI servers / proxies can present a dual-stack peer address
        as an IPv4-mapped IPv6 literal ('::ffff:10.89.0.5'). Python's
        ipaddress module does NOT consider that address a member of an
        IPv4Network CIDR (mismatched .version), so a genuinely-trusted
        proxy reachable this way is treated as an ORDINARY, untrusted
        client: X-Forwarded-For is ignored entirely and every real client
        behind that proxy collapses onto the proxy's mapped address as the
        rate-limit / audit key. Fails safe (no spoofing), but is a real
        correctness/availability gap worth flagging if any deployment
        target ever surfaces peers in this form.
        """
        mapped_peer = "::ffff:10.89.0.5"  # same host as NGINX_PEER_V4, IPv6-mapped
        request = _request(mapped_peer, xff=f"203.0.113.9, {mapped_peer}")

        result = get_client_ip(request)

        assert result == mapped_peer, (
            "if this assertion ever fails, IPv4-mapped-IPv6 trust matching "
            "was fixed — this test documents the current gap, not a "
            "must-fix regression"
        )
