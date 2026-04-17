#!/usr/bin/env python3
"""Read-only audit of `time_entries.extra_metadata` against the O3 schema.

Purpose
-------
Before the SQLAlchemy `before_insert` / `before_update` event listener
in `db/models.py` is deployed, every row in `time_entries` must satisfy
the `TimeEntryMetadata` whitelist — otherwise subsequent ORM updates on
those rows (even unrelated ones) will fail validation and abort.

This script scans every row and prints violations. It MUST NOT mutate
data. Resolving violations (backfill, delete, or normalise) is a
manual decision left to the DPO.

Usage
-----
Run from the project root with the backend container's environment:

    poetry run python scripts/audit_time_entry_metadata.py

Or with a direct `DATABASE_URL`:

    DATABASE_URL="postgresql+asyncpg://user:pass@db:5432/goldsmith" \
        poetry run python scripts/audit_time_entry_metadata.py

Exit codes
----------
* 0 — no violations (safe to deploy the event listener)
* 1 — at least one violation (fix before deploying)
* 2 — script-level error (could not connect, etc.)

Deployment note
---------------
Document in the rollout PR:

    "Run `poetry run python scripts/audit_time_entry_metadata.py`
    against the production DB and resolve any violations before
    deploying the event listener. Existing rows that fail validation
    will cause every subsequent ORM update on that row to fail."
"""

from __future__ import annotations

import asyncio
import os
import sys
from typing import Any

# Make `goldsmith_erp` importable when the script is run from the
# project root (matches the pattern in `scripts/create-admin.py`).
_script_dir = os.path.dirname(os.path.abspath(__file__))
_project_root = os.path.dirname(_script_dir)
_src_dir = os.path.join(_project_root, "src")
if _src_dir not in sys.path:
    sys.path.insert(0, _src_dir)

from pydantic import ValidationError  # noqa: E402
from sqlalchemy import select  # noqa: E402

from goldsmith_erp.db.models import TimeEntry  # noqa: E402
from goldsmith_erp.db.session import AsyncSessionLocal  # noqa: E402
from goldsmith_erp.models.time_entry_metadata import (  # noqa: E402
    TimeEntryMetadata,
)


# --------------------------------------------------------------------------- #
# Audit
# --------------------------------------------------------------------------- #


async def _audit_rows() -> tuple[int, list[tuple[str, dict[str, Any], str]]]:
    """Return (total_rows_examined, list_of_violations).

    Each violation is ``(row_id, extra_metadata_value, failure_message)``.
    """
    violations: list[tuple[str, dict[str, Any], str]] = []
    total = 0

    async with AsyncSessionLocal() as session:
        # Stream via `yield_per` is ideal for huge tables, but the
        # async SQLAlchemy API for that is awkward. We select the two
        # columns we need and page via offset so memory stays bounded
        # even if the table is large.
        page_size = 500
        offset = 0

        while True:
            stmt = (
                select(TimeEntry.id, TimeEntry.extra_metadata)
                .order_by(TimeEntry.id)
                .offset(offset)
                .limit(page_size)
            )
            result = await session.execute(stmt)
            rows = result.all()
            if not rows:
                break

            for row_id, metadata in rows:
                total += 1
                if metadata is None or metadata == {}:
                    continue
                try:
                    TimeEntryMetadata.model_validate(metadata)
                except ValidationError as exc:
                    violations.append((row_id, metadata, str(exc)))

            offset += page_size

    return total, violations


def _format_violation(
    row_id: str, metadata: dict[str, Any], message: str
) -> str:
    # Do not print values that may contain PII — print key names only
    # plus the first 80 chars of the validation error, which is the
    # Pydantic-generated technical message (safe).
    keys = sorted(metadata.keys()) if isinstance(metadata, dict) else ["<not-a-dict>"]
    clipped = message.replace("\n", " | ")[:240]
    return f"  row_id={row_id!s:<36}  keys={keys}  error={clipped}"


async def main() -> int:
    try:
        total, violations = await _audit_rows()
    except Exception as exc:  # noqa: BLE001 — script-level error path
        print(f"[audit] script failed: {exc}", file=sys.stderr)
        return 2

    print(f"[audit] examined {total} time_entries rows")
    if not violations:
        print("[audit] no violations — safe to deploy the event listener")
        return 0

    print(f"[audit] {len(violations)} violation(s) found:")
    for row_id, metadata, message in violations:
        print(_format_violation(row_id, metadata, message))

    print(
        "\n[audit] resolve each violation (backfill to whitelist, "
        "delete, or migrate) before deploying the event listener."
    )
    return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
