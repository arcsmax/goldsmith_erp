"""Deployment compose hardening (SEC-08, SEC-F2, OPS-15 / W1-01, W1-02).

Static assertions against the compose YAML files:

- the dev stacks (``podman-compose.yml``, ``docker-compose.yml``) publish
  Redis and the backend to loopback only, never ``0.0.0.0`` (SEC-08) — real
  data must only ever run on ``podman-compose.prod.yml``;
- the prod stack (``podman-compose.prod.yml``) publishes host ports on the
  Caddy proxy service alone (80/443), every other service is internal-only;
- every service, in every compose file, declares both a ``restart`` policy
  and a ``healthcheck``;
- no service pins the ``:latest`` image tag (or omits a tag, which resolves
  to ``:latest`` implicitly);
- the dev stacks take every published host port from a ``${VAR:-default}``
  variable, so a second stack on the same machine can move it (LV-17).
"""

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DEV_COMPOSE_FILES = (REPO_ROOT / "podman-compose.yml", REPO_ROOT / "docker-compose.yml")
PROD_COMPOSE_FILE = REPO_ROOT / "podman-compose.prod.yml"
ALL_COMPOSE_FILES = (*DEV_COMPOSE_FILES, PROD_COMPOSE_FILE)

# Matches the `${VAR:-default}` shell-interpolation syntax used throughout
# these compose files (e.g. `${REDIS_HOST_IP:-127.0.0.1}`), and resolves it
# to its default value so the rest of a port spec can be parsed positionally.
_VAR_DEFAULT = re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*:-([^}]*)\}")


def _resolve_defaults(value: str) -> str:
    return _VAR_DEFAULT.sub(r"\1", value)


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _services(compose: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return compose["services"]


def _published_host(port_entry: str) -> str | None:
    """The bound host IP of a short-syntax `ports:` entry, or None if the
    entry has no explicit host (which binds every interface, i.e. 0.0.0.0)."""
    resolved = _resolve_defaults(str(port_entry))
    parts = resolved.split(":")
    if len(parts) >= 3:
        return parts[0]
    return None


@pytest.fixture(scope="module", params=DEV_COMPOSE_FILES, ids=lambda p: p.name)
def dev_compose(request: pytest.FixtureRequest) -> dict[str, Any]:
    return _load(request.param)


@pytest.fixture(scope="module")
def prod_compose() -> dict[str, Any]:
    return _load(PROD_COMPOSE_FILE)


@pytest.fixture(scope="module", params=ALL_COMPOSE_FILES, ids=lambda p: p.name)
def any_compose(request: pytest.FixtureRequest) -> dict[str, Any]:
    return _load(request.param)


def test_dev_redis_bound_to_loopback(dev_compose: dict[str, Any]):
    redis = _services(dev_compose)["redis"]
    ports = redis.get("ports", [])
    assert ports, "redis must publish a port in the dev stack"
    for entry in ports:
        host = _published_host(entry)
        assert host == "127.0.0.1", (
            f"redis port {entry!r} must bind to 127.0.0.1, not the LAN (SEC-08)"
        )


def test_dev_backend_bound_to_loopback(dev_compose: dict[str, Any]):
    backend = _services(dev_compose)["backend"]
    ports = backend.get("ports", [])
    assert ports, "backend must publish a port in the dev stack"
    for entry in ports:
        host = _published_host(entry)
        assert host == "127.0.0.1", (
            f"backend port {entry!r} must bind to 127.0.0.1, not the LAN (SEC-08)"
        )


def test_dev_db_stays_bound_to_loopback(dev_compose: dict[str, Any]):
    """Regression guard: the DB fix (SEC-08 sibling) must not regress."""
    db = _services(dev_compose)["db"]
    for entry in db.get("ports", []):
        assert _published_host(entry) == "127.0.0.1"


# LV-17: docker-compose.yml hard-coded the Redis host port 6379 although
# podman-compose.yml already read REDIS_EXT_PORT, so the dev stack collided
# with any other Redis on the machine. Both dev files must use the same
# variable (and default) for each published host port.
_DEV_HOST_PORT_VARS = (
    ("db", "DB_PORT", "5432"),
    ("redis", "REDIS_EXT_PORT", "6379"),
    ("backend", "BACKEND_PORT", "8000"),
    ("frontend", "FRONTEND_PORT", "3000"),
)


@pytest.mark.parametrize(
    ("service", "variable", "default"),
    _DEV_HOST_PORT_VARS,
    ids=[row[0] for row in _DEV_HOST_PORT_VARS],
)
def test_dev_host_ports_are_configurable(
    dev_compose: dict[str, Any], service: str, variable: str, default: str
):
    ports = [str(p) for p in _services(dev_compose)[service].get("ports", [])]
    assert ports, f"{service} must publish a port in the dev stack"
    expected = f"${{{variable}:-{default}}}:{default}"
    for entry in ports:
        assert entry.endswith(expected), (
            f"{service} port {entry!r} must publish its host port via "
            f"${{{variable}:-{default}}} (LV-17), not a hard-coded number"
        )


def test_prod_only_proxy_publishes_ports(prod_compose: dict[str, Any]):
    services = _services(prod_compose)
    assert "caddy" in services

    for name, svc in services.items():
        ports = svc.get("ports", [])
        if name == "caddy":
            assert ports, "caddy must publish the LAN-facing ports"
        else:
            assert not ports, (
                f"{name} must not publish host ports in production — "
                "only the Caddy proxy is LAN-facing"
            )


def test_prod_proxy_publishes_only_80_and_443(prod_compose: dict[str, Any]):
    caddy = _services(prod_compose)["caddy"]
    container_ports = set()
    for entry in caddy["ports"]:
        resolved = _resolve_defaults(str(entry))
        container_ports.add(resolved.split(":")[-1])
    assert container_ports == {"80", "443"}


def test_every_service_has_restart_policy(any_compose: dict[str, Any]):
    for name, svc in _services(any_compose).items():
        assert "restart" in svc, f"service {name!r} has no restart policy"


def test_every_service_has_healthcheck(any_compose: dict[str, Any]):
    for name, svc in _services(any_compose).items():
        assert "healthcheck" in svc, f"service {name!r} has no healthcheck"
        test = svc["healthcheck"].get("test")
        assert test, f"service {name!r} healthcheck has no test command"


def test_no_latest_image_tags(any_compose: dict[str, Any]):
    for name, svc in _services(any_compose).items():
        image = svc.get("image")
        if image is None:
            # build-based service (backend/frontend): no pull tag to pin.
            continue
        assert not image.endswith(":latest"), f"{name} pins the :latest tag: {image}"
        last_segment = image.rsplit("/", 1)[-1]
        assert ":" in last_segment, (
            f"{name} image {image!r} has no explicit tag (implicit :latest)"
        )
