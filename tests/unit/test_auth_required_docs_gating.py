"""Unit tests for the DEBUG-gating of the API-docs whitelist entries.

Tier 2 finding 2.7 (2026-07-26 review): ``/docs``, ``/redoc`` and
``/openapi.json`` were unconditionally whitelisted in
``middleware/auth_required.py`` — public in every environment. In production
(DEBUG=False) they must not be public: main.py disables them at the app level
(openapi_url/docs_url/redoc_url=None) and the middleware drops them from its
public whitelist (defense in depth).

The whitelist lists are built once at import time from ``settings.DEBUG``, so
the DEBUG=False variant is exercised in a subprocess with a clean environment
(no in-process module reload → no pollution of the app the other tests share).
The DEBUG=True variant is asserted in-process against the live module, which
under the CI env (DEBUG=true) is the state the running app actually uses.
"""

import json
import os
import subprocess
import sys

from goldsmith_erp.middleware import auth_required

_DOCS_ENTRIES = {"/docs", "/redoc", "/openapi.json"}


def _whitelist_with_debug(debug: str) -> dict:
    """Import the whitelist in a subprocess with DEBUG set to ``debug``.

    The subprocess must satisfy the production fail-fast validators
    (ENCRYPTION_KEY / ANONYMIZATION_SALT / COOKIE_SECURE) so ``Settings()`` can
    construct at config import even when DEBUG=false.
    """
    code = (
        "import json;"
        "from goldsmith_erp.middleware import auth_required as a;"
        "print(json.dumps({'paths': a.PUBLIC_PATHS, 'prefixes': a.PUBLIC_PREFIXES}))"
    )
    env = {
        **os.environ,
        "DEBUG": debug,
        "ENCRYPTION_KEY": "V0Ae_U1MhSkUCNugAmmQV7Jl2GnxkizHeurQnglXVOc=",
        "ANONYMIZATION_SALT": "testsalt1234567890abcdef",
        "COOKIE_SECURE": "true",
    }
    out = subprocess.check_output([sys.executable, "-c", code], env=env, text=True)
    return json.loads(out.strip().splitlines()[-1])


class TestDocsWhitelistGating:
    def test_docs_public_in_debug_mode(self):
        """DEBUG=True (the CI/test env) keeps the docs paths whitelisted so the
        interactive docs stay reachable in development."""
        assert "/docs" in auth_required.PUBLIC_PATHS
        assert "/redoc" in auth_required.PUBLIC_PATHS
        assert "/openapi.json" in auth_required.PUBLIC_PATHS
        assert "/docs" in auth_required.PUBLIC_PREFIXES
        assert "/redoc" in auth_required.PUBLIC_PREFIXES

    def test_docs_public_subprocess_debug_true(self):
        """Same assertion via the subprocess harness (sanity check that the
        harness reflects the in-process result for DEBUG=true)."""
        wl = _whitelist_with_debug("true")
        assert _DOCS_ENTRIES.issubset(set(wl["paths"]))
        assert "/docs" in wl["prefixes"]

    def test_docs_not_public_in_production(self):
        """DEBUG=False drops every docs entry from both whitelist lists so an
        unauthenticated docs request hits the deny-by-default 401."""
        wl = _whitelist_with_debug("false")
        assert _DOCS_ENTRIES.isdisjoint(
            set(wl["paths"])
        ), f"docs paths must not be whitelisted in production; got {wl['paths']}"
        assert "/docs" not in wl["prefixes"]
        assert "/redoc" not in wl["prefixes"]

    def test_health_stays_public_in_production(self):
        """/health must remain public in production so external monitors can
        reach it without a token."""
        wl = _whitelist_with_debug("false")
        assert "/health" in wl["paths"]
