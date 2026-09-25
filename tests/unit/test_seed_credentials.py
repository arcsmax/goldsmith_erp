"""Tests that every seed path agrees on the same demo staff credentials.

Three seed scripts (``scripts/seed_demo.py``, ``scripts/seed_data.py``,
``src/goldsmith_erp/db/seed_data.py``) used to each hardcode their own demo
email/password convention, and three Playwright specs hardcoded a fourth
combination that matched none of them. ``goldsmith_erp.db.seed_credentials``
is now the single source of truth every seed path imports from — these tests
assert that import wiring holds, not just that the module itself is
internally consistent.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from goldsmith_erp.db import seed_credentials
from goldsmith_erp.db.seed_credentials import (
    DEMO_ADMIN,
    DEMO_GOLDSMITH,
    DEMO_PASSWORD,
    DEMO_USERS,
    DEMO_VIEWER,
    SENTINEL_EMAIL,
)
from goldsmith_erp.db.seed_data import STANDARD_USERS

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))


def _load_script_module(name: str, filename: str):
    """Load a scripts/*.py file as a module without running its __main__ body.

    Mirrors the pattern already established in tests/unit/test_seed_demo.py:
    scripts/ is not a package on sys.path, and these files run
    module-level code that legitimately imports goldsmith_erp — but their
    actual DB-writing work sits behind ``if __name__ == "__main__":``, which
    never fires under this loader.
    """
    script_path = _SCRIPTS_DIR / filename
    spec = importlib.util.spec_from_file_location(name, str(script_path))
    assert spec is not None and spec.loader is not None, f"Could not load {script_path}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# 1. seed_credentials.py is internally consistent
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_demo_password_matches_existing_convention() -> None:
    """Absent SEED_DEMO_PASSWORD, the default must be the value every seed
    path and CI workflow has always documented: demo2026!."""
    assert DEMO_PASSWORD == "demo2026!"


@pytest.mark.unit
def test_demo_users_are_the_three_canonical_roles() -> None:
    roles = {user.role for user in DEMO_USERS}
    assert roles == {"admin", "goldsmith", "viewer"}
    assert len(DEMO_USERS) == 3
    assert DEMO_GOLDSMITH.email == SENTINEL_EMAIL
    assert DEMO_ADMIN.role == "admin"
    assert DEMO_GOLDSMITH.role == "goldsmith"
    assert DEMO_VIEWER.role == "viewer"


# ---------------------------------------------------------------------------
# 2. scripts/seed_demo.py imports the shared credentials (not its own copy)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_seed_demo_imports_shared_credentials() -> None:
    sd = _load_script_module("seed_demo_credentials_under_test", "seed_demo.py")

    assert sd.DEMO_USERS is seed_credentials.DEMO_USERS
    assert sd.DEMO_PASSWORD == seed_credentials.DEMO_PASSWORD
    assert sd.SENTINEL_EMAIL == seed_credentials.SENTINEL_EMAIL

    # No stray hardcoded "demo2026!" literal left behind in the source —
    # every occurrence must flow through DEMO_PASSWORD.
    src = (_SCRIPTS_DIR / "seed_demo.py").read_text(encoding="utf-8")
    assert '"demo2026!"' not in src
    assert "'demo2026!'" not in src


# ---------------------------------------------------------------------------
# 3. scripts/seed_data.py imports the shared credentials (not its own copy)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_seed_data_script_imports_shared_credentials() -> None:
    sd = _load_script_module("seed_data_credentials_under_test", "seed_data.py")

    assert sd.DEMO_USERS is seed_credentials.DEMO_USERS
    assert sd.DEMO_PASSWORD == seed_credentials.DEMO_PASSWORD
    assert sd.DEMO_ADMIN.email == seed_credentials.DEMO_ADMIN.email

    # No stray hardcoded legacy passwords left behind (admin123 etc., the
    # convention this script used before it shared credentials.py).
    src = (_SCRIPTS_DIR / "seed_data.py").read_text(encoding="utf-8")
    for legacy_password in ("admin123", "goldsmith123", "viewer123"):
        assert (
            legacy_password not in src
        ), f"legacy password {legacy_password!r} still present"


# ---------------------------------------------------------------------------
# 4. src/goldsmith_erp/db/seed_data.py's STANDARD_USERS matches the shared
#    credentials exactly (email, password, name, role per canonical user)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_db_seed_data_standard_users_matches_shared_credentials() -> None:
    assert len(STANDARD_USERS) == len(DEMO_USERS)

    by_email = {demo_user.email: demo_user for demo_user in DEMO_USERS}
    for entry in STANDARD_USERS:
        canonical = by_email.get(entry["email"])
        assert canonical is not None, f"{entry['email']} is not a canonical demo user"
        assert entry["password"] == DEMO_PASSWORD
        assert entry["first_name"] == canonical.first_name
        assert entry["last_name"] == canonical.last_name
        assert entry["role"] == canonical.role


# ---------------------------------------------------------------------------
# 5. Cross-check: no email is ever paired with two different passwords
#    across every seed path (the actual bug this module fixes).
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_no_seed_path_disagrees_on_a_shared_email() -> None:
    seed_demo_module = _load_script_module(
        "seed_demo_crosscheck_under_test", "seed_demo.py"
    )
    seed_data_script_module = _load_script_module(
        "seed_data_crosscheck_under_test", "seed_data.py"
    )

    credentials_by_source: dict[str, dict[str, str]] = {
        "seed_credentials.DEMO_USERS": {
            user.email: DEMO_PASSWORD for user in DEMO_USERS
        },
        "scripts/seed_demo.py": {
            user.email: seed_demo_module.DEMO_PASSWORD
            for user in seed_demo_module.DEMO_USERS
        },
        "scripts/seed_data.py (canonical subset)": {
            user.email: seed_data_script_module.DEMO_PASSWORD
            for user in seed_data_script_module.DEMO_USERS
        },
        "db/seed_data.py STANDARD_USERS": {
            entry["email"]: entry["password"] for entry in STANDARD_USERS
        },
    }

    seen: dict[str, tuple[str, str]] = {}
    for source_name, email_to_password in credentials_by_source.items():
        for email, password in email_to_password.items():
            if email in seen:
                previous_source, previous_password = seen[email]
                assert password == previous_password, (
                    f"{email} has password {password!r} in {source_name} but "
                    f"{previous_password!r} in {previous_source}"
                )
            else:
                seen[email] = (source_name, password)

    # Sanity: the canonical admin login used by e2e-nightly.yml and the
    # frontend Playwright specs must actually be present and resolve to the
    # documented default.
    assert seen[DEMO_ADMIN.email] == ("seed_credentials.DEMO_USERS", DEMO_PASSWORD)
