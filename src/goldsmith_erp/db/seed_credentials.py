"""Single source of truth for demo/seed staff credentials.

Three independent seed paths (``scripts/seed_demo.py``, ``scripts/seed_data.py``,
``src/goldsmith_erp/db/seed_data.py``) each hardcoded their own set of demo
staff emails and passwords (``demo2026!`` at ``*@werkstatt.de``, ``admin123``/
``goldsmith123``/``viewer123`` at ``*@goldsmith-werkstatt.de``, and per-role
``SEED_*_PASSWORD`` env vars falling back to ``dev-only-change-me`` at
``*@goldschmiede.de`` respectively). A nightly e2e run surfaced the fallout:
three Playwright specs hardcoded a fourth combination
(``admin@goldschmiede.de`` / ``Admin123!``) that matched none of the seeders,
requiring ``.github/workflows/e2e-nightly.yml`` to run two seed scripts back
to back just to get a working login.

Every seed path, ``.github/workflows/e2e-nightly.yml``, and the frontend e2e
config now import the same three staff accounts from here, so there is
exactly one demo email/password combination per role.

Security note: ``DEMO_PASSWORD`` is a single, well-known, non-secret string —
this seeds throwaway local/CI/demo databases only, never a production
deployment (each seeder that uses it is itself development/CI-only). Override
it via the ``SEED_DEMO_PASSWORD`` env var in any shared environment where
that assumption does not hold.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

# The demo password convention established by scripts/seed_demo.py.
DEMO_PASSWORD: str = os.getenv("SEED_DEMO_PASSWORD", "demo2026!")


@dataclass(frozen=True)
class DemoUser:
    """One canonical demo staff account."""

    email: str
    first_name: str
    last_name: str
    role: str  # "admin" | "goldsmith" | "viewer" (UserRole values)


# Canonical demo staff roster — identical to scripts/seed_demo.py's original
# three accounts, now the shared definition every seed path imports.
DEMO_GOLDSMITH = DemoUser(
    email="demo-goldschmied@werkstatt.de",
    first_name="Markus",
    last_name="Goldmann",
    role="goldsmith",
)
DEMO_ADMIN = DemoUser(
    email="demo-inhaber@werkstatt.de",
    first_name="Petra",
    last_name="Goldmann",
    role="admin",
)
DEMO_VIEWER = DemoUser(
    email="demo-buero@werkstatt.de",
    first_name="Lisa",
    last_name="Schreiber",
    role="viewer",
)

DEMO_USERS: tuple[DemoUser, ...] = (DEMO_GOLDSMITH, DEMO_ADMIN, DEMO_VIEWER)

# Sentinel used by idempotency checks (scripts/seed_demo.py,
# scripts/seed_v11_v12_only.py): if this user exists, demo data was seeded.
SENTINEL_EMAIL: str = DEMO_GOLDSMITH.email
