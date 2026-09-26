"""Export the erasure ledger, or replay it after a database restore (GDPR-07).

Run inside the backend container (the wrappers in ``scripts/`` do this)::

    # Print ledger lines not yet in the known ledger (read from stdin):
    python -m goldsmith_erp.cli.gdpr_replay_erasures export --known - < ledger.jsonl

    # Show what a replay would do (DRY-RUN, the default):
    python -m goldsmith_erp.cli.gdpr_replay_erasures replay --ledger - \
        --since 2026-09-20T03:00:00+0200 < ledger.jsonl

    # Actually re-apply the erasures:
    python -m goldsmith_erp.cli.gdpr_replay_erasures replay --ledger - \
        --since 2026-09-20T03:00:00+0200 --execute < ledger.jsonl

Exit codes: ``0`` ok, ``1`` at least one subject failed or a fatal error,
``2`` bad arguments or a malformed ledger.

Logs carry primary keys only, never names or e-mail addresses.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import List, Optional, Sequence, TextIO

from goldsmith_erp.services.gdpr_erasure_ledger import (
    LedgerEntry,
    LedgerFormatError,
    ReplayReport,
    collect_ledger_entries,
    merge_new_entries,
    read_ledger,
    replay_erasures,
    write_entries,
)

logger = logging.getLogger("goldsmith_erp.cli.gdpr_replay_erasures")

EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_USAGE = 2

# Subtracted from --since so that clock skew between the host (backup file
# name) and the database (UTC timestamps) can never drop an entry. Replay is
# idempotent, so replaying a few entries too many is harmless.
DEFAULT_MARGIN_HOURS = 24


def parse_since(raw: str) -> datetime:
    """Parse an ISO timestamp into naive UTC (the DB's convention).

    Accepts an offset (``+0200`` / ``+02:00`` / ``Z``); a value without an
    offset is taken as UTC.
    """
    value = raw.strip()
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    if len(value) > 5 and value[-5] in "+-" and value[-4:].isdigit():
        value = f"{value[:-2]}:{value[-2:]}"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def _open_text(path: str) -> TextIO:
    if path == "-":
        return sys.stdin
    return Path(path).open("r", encoding="utf-8")


def _load(path: Optional[str]) -> List[LedgerEntry]:
    if path is None:
        return []
    handle = _open_text(path)
    try:
        return read_ledger(handle)
    finally:
        if handle is not sys.stdin:
            handle.close()


async def _export(known: Sequence[LedgerEntry]) -> List[LedgerEntry]:
    from goldsmith_erp.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        current = await collect_ledger_entries(db)
    return merge_new_entries(known, current)


async def _replay(
    entries: Sequence[LedgerEntry], since: Optional[datetime], execute: bool
) -> ReplayReport:
    from goldsmith_erp.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        return await replay_erasures(db, entries, since=since, execute=execute)


def report_exit_code(report: ReplayReport) -> int:
    """Log the replay summary and map it to an exit code."""
    mode = "EXECUTE" if report.executed else "DRY-RUN"
    for outcome in report.outcomes:
        logger.info(
            "%s %s id=%d action=%s finalize=%s%s",
            mode,
            outcome.subject,
            outcome.subject_id,
            outcome.action,
            outcome.finalize,
            f" error={outcome.error}" if outcome.error else "",
        )
    logger.info(
        "Erasure replay (%s) finished: ledger_entries=%d considered=%d "
        "subjects=%d finalized_customers=%s failures=%d cleanup_failures=%s",
        mode,
        report.entries_total,
        report.entries_considered,
        len(report.outcomes),
        report.finalized_customer_ids,
        len(report.failures),
        report.cleanup_failures,
    )
    return EXIT_FAILURE if report.has_failures else EXIT_OK


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m goldsmith_erp.cli.gdpr_replay_erasures",
        description="Export or replay the GDPR Art. 17 erasure ledger.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    export = sub.add_parser("export", help="print new ledger lines to stdout")
    export.add_argument(
        "--known",
        help="existing ledger file ('-' = stdin); only entries not in it are printed",
    )

    replay = sub.add_parser("replay", help="re-apply erasures after a restore")
    replay.add_argument("--ledger", required=True, help="ledger file ('-' = stdin)")
    replay.add_argument(
        "--since",
        help="backup timestamp (ISO 8601, offset allowed); omit to replay all",
    )
    replay.add_argument(
        "--margin-hours",
        type=int,
        default=DEFAULT_MARGIN_HOURS,
        help=f"safety margin subtracted from --since (default {DEFAULT_MARGIN_HOURS})",
    )
    replay.add_argument(
        "--execute",
        action="store_true",
        help="actually re-apply; without it the run is a DRY-RUN",
    )
    return parser.parse_args(list(argv))


def _run_export(args: argparse.Namespace) -> int:
    known = _load(args.known)
    fresh = asyncio.run(_export(known))
    write_entries(fresh, sys.stdout)
    sys.stdout.flush()
    logger.info("Erasure ledger export: %d new entries", len(fresh))
    return EXIT_OK


def _run_replay(args: argparse.Namespace) -> int:
    if args.margin_hours < 0:
        logger.error("--margin-hours must not be negative")
        return EXIT_USAGE
    since: Optional[datetime] = None
    if args.since:
        try:
            since = parse_since(args.since) - timedelta(hours=args.margin_hours)
        except ValueError:
            logger.error("--since is not an ISO 8601 timestamp")
            return EXIT_USAGE
    entries = _load(args.ledger)
    logger.info(
        "Erasure replay starting (mode=%s, since=%s, entries=%d)",
        "EXECUTE" if args.execute else "DRY-RUN",
        since.isoformat() if since else "all",
        len(entries),
    )
    report = asyncio.run(_replay(entries, since, args.execute))
    return report_exit_code(report)


def main(argv: Optional[Sequence[str]] = None) -> int:
    # Logs go to stderr so that `export` can stream ledger lines on stdout.
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stderr,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    try:
        if args.command == "export":
            return _run_export(args)
        return _run_replay(args)
    except LedgerFormatError as exc:
        logger.error("Malformed erasure ledger: %s", exc)
        return EXIT_USAGE
    except Exception:  # noqa: BLE001 — top-level guard: log + nonzero exit
        logger.error("Erasure ledger command crashed", exc_info=True)
        return EXIT_FAILURE


if __name__ == "__main__":
    sys.exit(main())
