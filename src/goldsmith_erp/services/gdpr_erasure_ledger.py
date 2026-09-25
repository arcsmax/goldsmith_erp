"""Erasure ledger: re-apply Art. 17 erasures after a database restore.

GDPR-07 (docs/review/2026-09-25/07-gdpr-privacy.md): a dump taken *before*
an erasure request contains the customer without ``deletion_scheduled_at``
and without the ``gdpr_requests`` row. Restoring it brings the customer back,
and re-running the cleanup job finds nothing to do. The old policy doc
claimed the re-run "guarantees" re-erasure; it does not.

The fix has two halves:

1. **Export** — every executed erasure recorded in ``gdpr_requests`` is
   written as one JSON line to an append-only ledger file that lives OUTSIDE
   the database and outside the dump rotation (``scripts/backup.sh`` appends
   after each dump; ``scripts/restore.sh`` appends once more from the live
   database right before it is dropped, so nothing since the last backup is
   lost).
2. **Replay** — after the restore, every ledger entry newer than the backup
   is re-applied to the restored database: the customer is deactivated,
   free-text PII is scrubbed, files are erased, the legal hold is recorded,
   and a customer whose grace period had already run out is finalised
   (anonymised or hard-deleted) straight away. Employee erasures
   (``erasure_user``) are re-run through ``UserService.anonymize_user``.

The ledger holds only primary keys, request types and timestamps: no names,
no e-mail addresses (CLAUDE.md: never log customer PII). Replay is
idempotent, so replaying an entry the dump already reflects is harmless.

Dry-run is the default for replay: it reports what it would do and changes
nothing.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, TextIO

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import Customer, GDPRRequest

logger = logging.getLogger("goldsmith_erp.services.gdpr_erasure_ledger")

LEDGER_FORMAT_VERSION = 1

# gdpr_requests.request_type values that mean "personal data was erased".
CUSTOMER_ERASURE_TYPES = frozenset({"erasure", "erasure_cleanup", "erasure_replay"})
USER_ERASURE_TYPES = frozenset({"erasure_user"})
LEDGER_REQUEST_TYPES = CUSTOMER_ERASURE_TYPES | USER_ERASURE_TYPES

# Terminal statuses that mean the erasure actually ran (compared lower-case:
# the router writes "PARTIAL_FILE_ERASURE", the services write "completed").
EXECUTED_STATUSES = frozenset({"completed", "partial_file_erasure"})

# Art. 17 grace period used by the /gdpr-erase endpoint.
ERASURE_GRACE_PERIOD = timedelta(days=30)

# The request type written for every re-applied erasure (≤ 20 chars, the
# width of gdpr_requests.request_type).
REPLAY_REQUEST_TYPE = "erasure_replay"

_USER_ID_IN_NOTES = re.compile(r"anonymize_user\(user_id=(\d+)\)")


class LedgerFormatError(ValueError):
    """A ledger line could not be parsed. Carries the 1-based line number."""


@dataclass(frozen=True)
class LedgerEntry:
    """One executed erasure, as stored in the ledger file."""

    gdpr_request_id: int
    request_type: str
    status: str
    customer_id: Optional[int]
    user_id: Optional[int]
    requested_at: datetime
    completed_at: Optional[datetime]

    @property
    def effective_at(self) -> datetime:
        """When the erasure took effect (completion, else request time)."""
        return self.completed_at or self.requested_at

    @property
    def dedupe_key(self) -> str:
        """Identity across exports.

        The row id alone is not enough: after a restore the id sequence is
        rewound, so a new row can reuse the id of a row the restore lost.
        """
        return "|".join(
            [
                str(self.gdpr_request_id),
                self.request_type,
                str(self.customer_id),
                str(self.user_id),
                self.requested_at.isoformat(),
            ]
        )

    def to_json(self) -> str:
        return json.dumps(
            {
                "v": LEDGER_FORMAT_VERSION,
                "gdpr_request_id": self.gdpr_request_id,
                "request_type": self.request_type,
                "status": self.status,
                "customer_id": self.customer_id,
                "user_id": self.user_id,
                "requested_at": self.requested_at.isoformat(),
                "completed_at": (
                    self.completed_at.isoformat() if self.completed_at else None
                ),
            },
            sort_keys=True,
        )

    @classmethod
    def from_json(cls, raw: str) -> "LedgerEntry":
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError("ledger line is not a JSON object")
        if data.get("v") != LEDGER_FORMAT_VERSION:
            raise ValueError(f"unsupported ledger version {data.get('v')!r}")
        completed = data.get("completed_at")
        return cls(
            gdpr_request_id=int(data["gdpr_request_id"]),
            request_type=str(data["request_type"]),
            status=str(data["status"]),
            customer_id=_optional_int(data.get("customer_id")),
            user_id=_optional_int(data.get("user_id")),
            requested_at=datetime.fromisoformat(str(data["requested_at"])),
            completed_at=datetime.fromisoformat(completed) if completed else None,
        )


def _optional_int(value: object) -> Optional[int]:
    if value is None:
        return None
    return int(str(value))


def _user_id_from_notes(notes: Optional[str]) -> Optional[int]:
    match = _USER_ID_IN_NOTES.search(notes or "")
    return int(match.group(1)) if match else None


def _is_executed(status: Optional[str]) -> bool:
    return (status or "").lower() in EXECUTED_STATUSES


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


async def collect_ledger_entries(db: AsyncSession) -> List[LedgerEntry]:
    """Return every executed erasure recorded in ``gdpr_requests``."""
    result = await db.execute(
        select(GDPRRequest)
        .where(GDPRRequest.request_type.in_(sorted(LEDGER_REQUEST_TYPES)))
        .order_by(GDPRRequest.requested_at.asc(), GDPRRequest.id.asc())
    )
    entries: List[LedgerEntry] = []
    rows: Sequence[Any] = result.scalars().all()  # legacy Column-typed model
    for row in rows:
        if not _is_executed(row.status):
            continue
        user_id = (
            _user_id_from_notes(row.notes)
            if row.request_type in USER_ERASURE_TYPES
            else None
        )
        entries.append(
            LedgerEntry(
                gdpr_request_id=row.id,
                request_type=row.request_type,
                status=row.status,
                customer_id=row.customer_id,
                user_id=user_id,
                requested_at=row.requested_at,
                completed_at=row.completed_at,
            )
        )
    return entries


def read_ledger(lines: Iterable[str]) -> List[LedgerEntry]:
    """Parse ledger lines; blank lines and ``#`` comments are skipped.

    Fails loudly on a malformed line: a silently skipped erasure is exactly
    the failure this ledger exists to prevent.
    """
    entries: List[LedgerEntry] = []
    for number, raw in enumerate(lines, start=1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            entries.append(LedgerEntry.from_json(stripped))
        except (ValueError, KeyError, TypeError) as exc:
            raise LedgerFormatError(
                f"ledger line {number} is not a valid entry: {type(exc).__name__}"
            ) from exc
    return entries


def merge_new_entries(
    existing: Sequence[LedgerEntry], candidates: Sequence[LedgerEntry]
) -> List[LedgerEntry]:
    """Return the candidates not already present in ``existing``."""
    seen = {entry.dedupe_key for entry in existing}
    fresh: List[LedgerEntry] = []
    for entry in candidates:
        if entry.dedupe_key in seen:
            continue
        seen.add(entry.dedupe_key)
        fresh.append(entry)
    return fresh


def write_entries(entries: Sequence[LedgerEntry], out: TextIO) -> int:
    for entry in entries:
        out.write(entry.to_json() + "\n")
    return len(entries)


# ---------------------------------------------------------------------------
# Replay
# ---------------------------------------------------------------------------


@dataclass
class ReplayOutcome:
    """What happened (or would happen) for one data subject."""

    subject: str  # "customer" | "user"
    subject_id: int
    action: str  # re_erased | would_re_erase | absent | failed | ...
    finalize: bool = False
    error: Optional[str] = None


@dataclass
class ReplayReport:
    executed: bool
    since: Optional[datetime]
    entries_total: int = 0
    entries_considered: int = 0
    outcomes: List[ReplayOutcome] = field(default_factory=list)
    finalized_customer_ids: List[int] = field(default_factory=list)
    cleanup_failures: List[int] = field(default_factory=list)

    @property
    def failures(self) -> List[ReplayOutcome]:
        return [o for o in self.outcomes if o.error is not None]

    @property
    def has_failures(self) -> bool:
        return bool(self.failures) or bool(self.cleanup_failures)


@dataclass
class _CustomerPlan:
    customer_id: int
    first_requested_at: datetime
    finalize: bool
    ledger_ids: List[int]


def _plan_customers(
    entries: Sequence[LedgerEntry], now: datetime
) -> Dict[int, _CustomerPlan]:
    plans: Dict[int, _CustomerPlan] = {}
    for entry in entries:
        if entry.request_type not in CUSTOMER_ERASURE_TYPES:
            continue
        if entry.customer_id is None:
            continue
        past_grace = (
            entry.request_type == "erasure_cleanup"
            or entry.requested_at + ERASURE_GRACE_PERIOD <= now
        )
        plan = plans.get(entry.customer_id)
        if plan is None:
            plans[entry.customer_id] = _CustomerPlan(
                customer_id=entry.customer_id,
                first_requested_at=entry.requested_at,
                finalize=past_grace,
                ledger_ids=[entry.gdpr_request_id],
            )
            continue
        plans[entry.customer_id] = _CustomerPlan(
            customer_id=plan.customer_id,
            first_requested_at=min(plan.first_requested_at, entry.requested_at),
            finalize=plan.finalize or past_grace,
            ledger_ids=[*plan.ledger_ids, entry.gdpr_request_id],
        )
    return plans


def _user_ids(entries: Sequence[LedgerEntry]) -> List[int]:
    ids = {
        entry.user_id
        for entry in entries
        if entry.request_type in USER_ERASURE_TYPES and entry.user_id is not None
    }
    return sorted(ids)


async def _reerase_customer(
    db: AsyncSession,
    plan: _CustomerPlan,
    *,
    now: datetime,
    since: Optional[datetime],
    storage_root: Optional[Path],
) -> None:
    """Re-apply one customer's erasure inside its own transaction."""
    from goldsmith_erp.services.customer_service import CustomerService
    from goldsmith_erp.services.file_erasure_service import (
        FileErasureService,
        build_default_service,
    )

    customer: Any = (  # legacy Column-typed model
        await db.execute(select(Customer).where(Customer.id == plan.customer_id))
    ).scalar_one_or_none()
    if customer is None:  # pragma: no cover — caller checks first
        return

    target = now if plan.finalize else plan.first_requested_at + ERASURE_GRACE_PERIOD
    customer.is_active = False
    if (
        customer.deletion_scheduled_at is None
        or customer.deletion_scheduled_at > target
    ):
        customer.deletion_scheduled_at = target
    customer.updated_at = now

    await CustomerService.scrub_customer_pii(
        db, customer_id=plan.customer_id, skip_gdpr_request=True
    )
    await CustomerService.apply_retention_hold(db, plan.customer_id)
    file_service = (
        FileErasureService(storage_root)
        if storage_root is not None
        else build_default_service()
    )
    await file_service.erase_customer_files(db, plan.customer_id)

    db.add(
        GDPRRequest(
            customer_id=plan.customer_id,
            request_type=REPLAY_REQUEST_TYPE,
            status="completed",
            requested_at=now,
            completed_at=datetime.utcnow(),
            requested_by=None,
            notes=(
                "Art. 17 erasure re-applied after a database restore "
                f"(ledger ids {plan.ledger_ids}; backup cut-off "
                f"{since.isoformat() if since else 'none'}; "
                f"finalize={plan.finalize})."
            ),
        )
    )
    await db.commit()


async def _replay_customers(
    db: AsyncSession,
    plans: Dict[int, _CustomerPlan],
    report: ReplayReport,
    *,
    execute: bool,
    now: datetime,
    storage_root: Optional[Path],
) -> None:
    for customer_id in sorted(plans):
        plan = plans[customer_id]
        exists = (
            await db.execute(select(Customer.id).where(Customer.id == customer_id))
        ).scalar_one_or_none()
        if exists is None:
            report.outcomes.append(
                ReplayOutcome("customer", customer_id, "absent", plan.finalize)
            )
            continue
        if not execute:
            report.outcomes.append(
                ReplayOutcome("customer", customer_id, "would_re_erase", plan.finalize)
            )
            continue
        try:
            await _reerase_customer(
                db, plan, now=now, since=report.since, storage_root=storage_root
            )
            report.outcomes.append(
                ReplayOutcome("customer", customer_id, "re_erased", plan.finalize)
            )
        except Exception as exc:  # noqa: BLE001 — isolate, log, continue
            await db.rollback()
            report.outcomes.append(
                ReplayOutcome(
                    "customer",
                    customer_id,
                    "failed",
                    plan.finalize,
                    error=type(exc).__name__,
                )
            )
            logger.error(
                "Erasure replay FAILED for customer — rolled back, continuing",
                extra={"customer_id": customer_id, "error_type": type(exc).__name__},
                exc_info=True,
            )


async def _replay_users(
    db: AsyncSession,
    user_ids: Sequence[int],
    report: ReplayReport,
    *,
    execute: bool,
) -> None:
    from goldsmith_erp.db.models import User
    from goldsmith_erp.services.user_service import UserService

    for user_id in user_ids:
        exists = (
            await db.execute(select(User.id).where(User.id == user_id))
        ).scalar_one_or_none()
        if exists is None:
            report.outcomes.append(ReplayOutcome("user", user_id, "absent"))
            continue
        if not execute:
            report.outcomes.append(ReplayOutcome("user", user_id, "would_re_erase"))
            continue
        try:
            await UserService.anonymize_user(
                db, user_id, reason="erasure_replay_after_restore", requested_by=user_id
            )
            report.outcomes.append(ReplayOutcome("user", user_id, "re_erased"))
        except Exception as exc:  # noqa: BLE001 — isolate, log, continue
            await db.rollback()
            report.outcomes.append(
                ReplayOutcome("user", user_id, "failed", error=type(exc).__name__)
            )
            logger.error(
                "Erasure replay FAILED for user — rolled back, continuing",
                extra={"user_id": user_id, "error_type": type(exc).__name__},
                exc_info=True,
            )


async def replay_erasures(
    db: AsyncSession,
    entries: Sequence[LedgerEntry],
    *,
    since: Optional[datetime],
    execute: bool = False,
    now: Optional[datetime] = None,
    storage_root: Optional[Path] = None,
) -> ReplayReport:
    """Re-apply every ledger entry that took effect at or after ``since``.

    ``since`` is the backup's timestamp (naive UTC). ``None`` replays the
    whole ledger, which is safe because replay is idempotent.
    """
    now = now or datetime.utcnow()
    considered = [e for e in entries if since is None or e.effective_at >= since]
    report = ReplayReport(
        executed=execute,
        since=since,
        entries_total=len(entries),
        entries_considered=len(considered),
    )
    plans = _plan_customers(considered, now)
    await _replay_customers(
        db, plans, report, execute=execute, now=now, storage_root=storage_root
    )
    await _replay_users(db, _user_ids(considered), report, execute=execute)

    to_finalize = [
        o.subject_id
        for o in report.outcomes
        if o.subject == "customer" and o.action == "re_erased" and o.finalize
    ]
    if execute and to_finalize:
        from goldsmith_erp.services.customer_service import CustomerService

        cleanup = await CustomerService.hard_delete_expired_customers(
            db, now=now, storage_root=storage_root
        )
        done = set(cleanup.hard_deleted) | set(cleanup.anonymized)
        report.finalized_customer_ids = [cid for cid in to_finalize if cid in done]
        report.cleanup_failures = [cid for cid, _ in cleanup.failures]
    return report
