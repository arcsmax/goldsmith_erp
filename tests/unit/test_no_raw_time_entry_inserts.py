"""H12 — CI grep gate against raw-SQL inserts that bypass the
``TimeEntry.extra_metadata`` whitelist validator.

O3 installed a two-layer defence:
  * Layer A — Pydantic ``TimeEntryMetadata`` on the API boundary.
  * Layer B — SQLAlchemy ``before_insert`` / ``before_update`` event
    listener on the ``TimeEntry`` ORM class.

Both layers fire on ORM-mediated writes. Raw-SQL paths that hit the
``time_entries`` table via ``AsyncSession.execute(insert(TimeEntry.
__table__).values(...))`` or similar DBAPI-level constructs bypass
the mapper hook, so they could silently persist PII-bearing JSON into
``extra_metadata``.

Audit finding: zero such raw-SQL writes exist today. This test pins
that invariant. If a new one appears, the test fails with an actionable
message pointing at the offending file + line so the author either:

  1. Converts to ORM-mediated write (preferred — picks up Layer B).
  2. Wraps the raw-SQL call in a Pydantic validation step (explicit
     ``TimeEntryMetadata.model_validate(payload['extra_metadata'])``).
  3. Adds the file to the documented-exception allowlist at the top
     of this test — and explains why in the PR description.

Performance: the walk is bounded to ``src/goldsmith_erp/`` +
``scripts/`` (the only trees that could produce runtime writes) so the
test runs in < 100ms even on cold disk.
"""

from __future__ import annotations

import re
from pathlib import Path

# Files allowed to reference the pattern. Additions need justification
# in the PR description.
_ALLOWLIST: frozenset[str] = frozenset(
    {
        # The ORM model itself references the __table__ attribute in
        # doc-comments explaining the H12 limitation.
        "src/goldsmith_erp/db/models.py",
        # The audit script scans rows — does SELECTs only, never INSERT.
        "scripts/audit_time_entry_metadata.py",
    }
)

# Patterns that indicate a raw-SQL write that could bypass the ORM
# event listener. Matches:
#   insert(TimeEntry.__table__)
#   insert(TimeEntryModel.__table__)
#   TimeEntry.__table__.insert()
#   TimeEntryModel.__table__.insert()
#   session.execute(text("INSERT INTO time_entries ..."))
#   conn.execute(text("INSERT INTO time_entries ..."))
_RAW_INSERT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"insert\s*\(\s*TimeEntry(?:Model)?\.__table__\s*\)"),
    re.compile(r"TimeEntry(?:Model)?\.__table__\s*\.\s*insert\s*\("),
    re.compile(
        r'text\s*\(\s*["\'][^"\']*INSERT\s+INTO\s+time_entries',
        re.IGNORECASE,
    ),
)

# Root of the project (two levels up from tests/unit/).
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SCAN_ROOTS: tuple[Path, ...] = (
    _PROJECT_ROOT / "src" / "goldsmith_erp",
    _PROJECT_ROOT / "scripts",
)


def _iter_python_files() -> list[Path]:
    files: list[Path] = []
    for root in _SCAN_ROOTS:
        if not root.exists():
            continue
        for p in root.rglob("*.py"):
            if p.is_file():
                files.append(p)
    return files


def _relative(path: Path) -> str:
    try:
        return str(path.relative_to(_PROJECT_ROOT))
    except ValueError:
        return str(path)


def test_no_raw_time_entry_inserts_outside_allowlist():
    """Walk src/ + scripts/ — fail if any file outside the allowlist
    matches one of the raw-SQL INSERT patterns.
    """
    violations: list[tuple[str, int, str]] = []
    for py_file in _iter_python_files():
        rel = _relative(py_file)
        if rel in _ALLOWLIST:
            continue
        try:
            text_content = py_file.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for lineno, line in enumerate(text_content.splitlines(), start=1):
            for pattern in _RAW_INSERT_PATTERNS:
                if pattern.search(line):
                    violations.append((rel, lineno, line.strip()))
                    break

    assert not violations, (
        "Raw-SQL inserts into time_entries detected — these bypass the "
        "SQLAlchemy before_insert event listener and the Pydantic "
        "TimeEntryMetadata whitelist (H12 / O3). Either:\n"
        "  1. Convert to ORM-mediated write (db.add(TimeEntry(...))).\n"
        "  2. Validate manually via TimeEntryMetadata.model_validate "
        "before execute().\n"
        "  3. Add to the _ALLOWLIST in this test with a PR-level "
        "justification.\n\n"
        "Offenders:\n"
        + "\n".join(
            f"  {fname}:{lineno}: {line}"
            for fname, lineno, line in violations
        )
    )


def test_allowlisted_files_actually_exist():
    """Catch stale allowlist entries on file rename / delete."""
    missing = [
        rel for rel in _ALLOWLIST
        if not (_PROJECT_ROOT / rel).exists()
    ]
    assert not missing, (
        f"Allowlist entries that no longer exist — update the test: "
        f"{missing}"
    )


def test_event_listener_is_still_installed():
    """Smoke-test that Layer B (SQLAlchemy event listener) is still
    registered on TimeEntry. The H12 grep gate is meaningless if this
    listener has been inadvertently removed."""
    from sqlalchemy import event

    from goldsmith_erp.db.models import TimeEntry

    # `event.contains` returns True if a given listener is bound.
    # We don't have a handle to the function; check that both target
    # events on the TimeEntry mapper have at least one listener.
    # The presence itself is enough — removal is a signal.
    insert_listeners = event.registry._key_to_collection.get(  # type: ignore[attr-defined]
        ("before_insert", TimeEntry, None), []
    )
    update_listeners = event.registry._key_to_collection.get(  # type: ignore[attr-defined]
        ("before_update", TimeEntry, None), []
    )
    # The private API above is brittle across SQLAlchemy versions.
    # Fall back to the documented `event.contains` if introspection
    # returns empty (version mismatch).
    if not insert_listeners and not update_listeners:
        from goldsmith_erp.db.models import _validate_time_entry_metadata

        assert event.contains(
            TimeEntry, "before_insert", _validate_time_entry_metadata
        ), "TimeEntry before_insert listener missing — O3 Layer B gone"
        assert event.contains(
            TimeEntry, "before_update", _validate_time_entry_metadata
        ), "TimeEntry before_update listener missing — O3 Layer B gone"
