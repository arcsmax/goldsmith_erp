"""The nginx-served SPA must send security headers (SEC-06) and must not log
query strings (SEC-05).

nginx drops every inherited ``add_header`` in a location that declares its
own, so the headers live in one snippet that each static location includes.
The backend's proxied locations (/api, /uploads, /ws) keep the headers the
backend sets itself.
"""

import base64
import hashlib
import re
from pathlib import Path

import pytest

FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
NGINX_CONF = FRONTEND / "nginx.conf"
SNIPPET = FRONTEND / "nginx-security-headers.conf"
CONTAINERFILE = FRONTEND / "Containerfile.prod"
INDEX_HTML = FRONTEND / "index.html"
SNIPPET_TARGET = "/etc/nginx/snippets/security-headers.conf"
STATIC_LOCATIONS = ("location / {", "location = /index.html {", "location /assets/ {")
PROXY_LOCATIONS = ("location /api/ {", "location /uploads/ {", "location /ws/ {")


def _location_block(conf: str, opener: str) -> str:
    start = conf.index(opener)
    end = conf.index("\n    }", start)
    return conf[start:end]


def _header_value(snippet: str, name: str) -> str:
    match = re.search(rf'add_header\s+{re.escape(name)}\s+"([^"]+)"\s+always;', snippet)
    assert match, f"{name} missing or not marked 'always'"
    return match.group(1)


def _inline_script_hash() -> str:
    html = INDEX_HTML.read_text(encoding="utf-8")
    match = re.search(r"<script>(.*?)</script>", html, re.S)
    assert match, "index.html inline theme script not found"
    digest = hashlib.sha256(match.group(1).encode("utf-8")).digest()
    return base64.b64encode(digest).decode()


@pytest.fixture(scope="module")
def snippet() -> str:
    return SNIPPET.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def conf() -> str:
    return NGINX_CONF.read_text(encoding="utf-8")


def test_csp_blocks_framing_and_foreign_scripts(snippet: str):
    csp = _header_value(snippet, "Content-Security-Policy")

    assert "default-src 'self'" in csp
    assert "frame-ancestors 'none'" in csp
    assert "base-uri 'self'" in csp
    assert "form-action 'self'" in csp
    assert "object-src 'none'" in csp
    assert "'unsafe-inline'" not in csp.split("script-src", 1)[1].split(";", 1)[0]


def test_csp_allows_the_inline_theme_script_by_hash(snippet: str):
    csp = _header_value(snippet, "Content-Security-Policy")

    assert f"'sha256-{_inline_script_hash()}'" in csp, (
        "index.html's inline script changed; update its hash in "
        "frontend/nginx-security-headers.conf"
    )


def test_frame_sniff_referrer_hsts_and_permissions_headers(snippet: str):
    assert _header_value(snippet, "X-Frame-Options") == "DENY"
    assert _header_value(snippet, "X-Content-Type-Options") == "nosniff"
    assert (
        _header_value(snippet, "Referrer-Policy") == "strict-origin-when-cross-origin"
    )
    assert "max-age=" in _header_value(snippet, "Strict-Transport-Security")
    permissions = _header_value(snippet, "Permissions-Policy")
    assert "camera=(self)" in permissions  # QR scanner needs the camera
    assert "microphone=()" in permissions


@pytest.mark.parametrize("opener", STATIC_LOCATIONS)
def test_every_static_location_includes_the_snippet(conf: str, opener: str):
    assert f"include {SNIPPET_TARGET};" in _location_block(conf, opener)


@pytest.mark.parametrize("opener", PROXY_LOCATIONS)
def test_proxied_locations_keep_backend_headers(conf: str, opener: str):
    assert SNIPPET_TARGET not in _location_block(conf, opener)


def test_containerfile_ships_the_snippet():
    containerfile = CONTAINERFILE.read_text(encoding="utf-8")

    assert f"COPY nginx-security-headers.conf {SNIPPET_TARGET}" in containerfile


def test_access_log_omits_query_strings(conf: str):
    log_format = re.search(r"^log_format\s+(\w+)\s+([^;]+);", conf, re.M)
    assert log_format, "custom log_format missing"
    name, fmt = log_format.groups()
    assert "$request_uri" not in fmt and "$args" not in fmt
    assert "$request " not in fmt and '$request"' not in fmt
    assert "$http_referer" not in fmt
    assert re.search(rf"access_log\s+\S+\s+{name};", conf)


def test_client_max_body_size_covers_the_largest_upload(conf: str):
    """SEC-F2: nginx's 1m default 413s every photo (8 MB) and material (10 MB)
    upload the backend otherwise accepts."""
    match = re.search(r"client_max_body_size\s+(\d+)\s*([kKmM]?)\s*;", conf)
    assert match, "client_max_body_size not set (nginx defaults to 1m)"
    value, unit = match.groups()
    multiplier = {"": 1, "k": 1024, "m": 1024 * 1024}[unit.lower()]
    size_bytes = int(value) * multiplier
    min_required = 10 * 1024 * 1024
    assert size_bytes >= min_required, (
        f"client_max_body_size {value}{unit} is smaller than the 10 MB material upload limit"
    )
