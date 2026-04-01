#!/usr/bin/env python3
"""
Create an admin user in the Goldsmith ERP database.

Usage:
    ADMIN_PASSWORD="SecurePassword123!" python scripts/create-admin.py \
        --email admin@example.com \
        --first-name Max \
        --last-name Mustermann

The password is read from the ADMIN_PASSWORD environment variable.
Passing --password on the command line is supported for backwards compatibility
but is strongly discouraged because the value is visible in /proc/<pid>/cmdline.

Skips creation silently if a user with the given email already exists.
Must be run from the project root or with PYTHONPATH set to include src/.
"""

import argparse
import asyncio
import os
import sys

# Ensure the src directory is on the path so goldsmith_erp imports resolve
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
src_dir = os.path.join(project_root, "src")
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from sqlalchemy import select

from goldsmith_erp.core.security import get_password_hash
from goldsmith_erp.db.models import User, UserRole
from goldsmith_erp.db.session import AsyncSessionLocal


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create an ADMIN user in the Goldsmith ERP database."
    )
    parser.add_argument("--email", required=True, help="Admin email address")
    parser.add_argument(
        "--password",
        required=False,
        default=None,
        help=(
            "Admin password (plaintext, will be hashed). "
            "Prefer passing via ADMIN_PASSWORD env var to avoid exposure in "
            "/proc/<pid>/cmdline."
        ),
    )
    parser.add_argument("--first-name", required=True, dest="first_name", help="First name")
    parser.add_argument("--last-name", required=True, dest="last_name", help="Last name")
    return parser.parse_args()


async def create_admin(email: str, password: str, first_name: str, last_name: str) -> None:
    async with AsyncSessionLocal() as session:
        # Check if user already exists
        result = await session.execute(select(User).where(User.email == email))
        existing = result.scalar_one_or_none()

        if existing is not None:
            print(f"[INFO] Benutzer '{email}' existiert bereits – kein Erstellen nötig.")
            return

        admin_user = User(
            email=email,
            hashed_password=get_password_hash(password),
            first_name=first_name,
            last_name=last_name,
            role=UserRole.ADMIN,
            is_active=True,
        )
        session.add(admin_user)
        await session.commit()
        await session.refresh(admin_user)

    print(f"[OK] Admin-Benutzer erstellt: {first_name} {last_name} <{email}> (ID={admin_user.id})")


def main() -> None:
    args = parse_args()

    # Resolve password: CLI arg (legacy, insecure) → env var (preferred)
    password: str | None = args.password or os.environ.get("ADMIN_PASSWORD")
    if not password:
        print(
            "[FEHLER] Kein Passwort angegeben. "
            "Bitte ADMIN_PASSWORD als Umgebungsvariable setzen.",
            file=sys.stderr,
        )
        sys.exit(1)

    if len(password) < 8:
        print("[FEHLER] Passwort muss mindestens 8 Zeichen lang sein.", file=sys.stderr)
        sys.exit(1)

    asyncio.run(create_admin(
        email=args.email,
        password=password,
        first_name=args.first_name,
        last_name=args.last_name,
    ))


if __name__ == "__main__":
    main()
