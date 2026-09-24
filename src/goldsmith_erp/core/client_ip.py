# src/goldsmith_erp/core/client_ip.py
"""Resolve the real client IP behind the reverse-proxy chain (SEC-04).

Production traffic is Caddy -> nginx -> backend, so the TCP peer of every
request is the nginx container. Rate limiters, audit logs and other IP-based
logic must key on the originating client instead.

Trust model:

* ``X-Forwarded-For`` / ``X-Real-IP`` are honoured only when the direct TCP
  peer lies in ``settings.TRUSTED_PROXIES``. Any other peer is the client.
* The forwarded chain is walked right-to-left, skipping trusted proxy hops.
  The first untrusted hop is the client. Entries a client prepends itself sit
  left of the hop our own proxy appended, so they can never win.
* If every hop is trusted (for example a LAN client inside a trusted range),
  the leftmost hop is the client.
* A malformed hop stops the walk; the last address verified so far is used,
  so garbage from a client never becomes a rate-limit key.
"""

import ipaddress
from functools import lru_cache
from typing import Iterable, Optional, Union

from starlette.requests import Request

from goldsmith_erp.core.config import settings

IPNetwork = Union[ipaddress.IPv4Network, ipaddress.IPv6Network]
TrustedNetworks = tuple[IPNetwork, ...]

UNKNOWN_CLIENT = "unknown"


def parse_trusted_networks(entries: Iterable[str]) -> TrustedNetworks:
    """Parse CIDR strings (a bare address means a single host)."""
    return tuple(ipaddress.ip_network(entry.strip(), strict=False) for entry in entries)


@lru_cache(maxsize=1)
def _default_networks(entries: tuple[str, ...]) -> TrustedNetworks:
    return parse_trusted_networks(entries)


def _parse_ip(
    value: str,
) -> Optional[Union[ipaddress.IPv4Address, ipaddress.IPv6Address]]:
    try:
        return ipaddress.ip_address(value.strip())
    except ValueError:
        return None


def _is_trusted(value: str, networks: TrustedNetworks) -> bool:
    address = _parse_ip(value)
    return address is not None and any(address in net for net in networks)


def _client_from_chain(peer: str, header: str, networks: TrustedNetworks) -> str:
    hops = [hop.strip() for hop in header.split(",") if hop.strip()]
    candidate = peer
    for hop in reversed(hops):
        if _parse_ip(hop) is None:
            return candidate
        if not _is_trusted(hop, networks):
            return hop
        candidate = hop
    return candidate


def get_client_ip(request: Request, networks: Optional[TrustedNetworks] = None) -> str:
    """Return the originating client IP for *request*.

    ``networks`` defaults to ``settings.TRUSTED_PROXIES``; tests pass their own.
    """
    peer = request.client.host if request.client else None
    if not peer:
        return UNKNOWN_CLIENT

    trusted = (
        networks
        if networks is not None
        else _default_networks(tuple(settings.TRUSTED_PROXIES))
    )
    if not _is_trusted(peer, trusted):
        return peer

    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return _client_from_chain(peer, forwarded_for, trusted)

    real_ip = request.headers.get("x-real-ip")
    if real_ip and _parse_ip(real_ip) is not None:
        return real_ip.strip()

    return peer
