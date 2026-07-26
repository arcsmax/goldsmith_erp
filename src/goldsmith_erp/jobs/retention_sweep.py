"""Per-entity ``retention_class`` enforcement sweep — runnable entry point.

Production-readiness.md 2026-07-26, **finding 2.3**. Companion to the
customer-level Art. 17 cleanup (finding 1.3, ``jobs/gdpr_cleanup.py``): that
job disposes of *customers* past their 30-day grace; **this** job enforces the
per-row statutory retention buckets tagged by ``retention_class`` on the
operational + financial tables. The repository methods that were meant to
drive this were deleted in the pre-V1.1 GDPR hotfix
(``db/repositories/customer.py``) and never rebuilt.

Invocation (inside the backend container, weekly, via the systemd timer in
``deploy/systemd/``)::

    python -m goldsmith_erp.jobs.retention_sweep            # DRY-RUN (default)
    python -m goldsmith_erp.jobs.retention_sweep --execute  # actually delete

Exit codes:

- ``0`` — the sweep completed cleanly (dry-run OR execute). Finding candidates
  in dry-run is **not** a failure — it is the report.
- ``1`` — at least one table/rule failed (each failure is logged with PRIMARY
  KEY ids only — never PII), OR a fatal error occurred (import failure, DB
  unreachable). The systemd unit's ``OnFailure=`` fires the alert unit.

SAFETY (CLAUDE.md ``security > correctness > performance``):

- **DRY-RUN is the default.** Without ``--execute`` the job only counts + logs
  candidate PKs and touches nothing. The scheduled systemd unit ships in
  dry-run mode; an operator flips it to execute only after reviewing the log
  output and getting an Anna+Henrik sign-off (see
  ``docs/technical/GDPR_ERASURE_RETENTION.md``).
- **Financial rows are never touched inside their statutory period.** The
  ``financial_10y`` clock is *year-end-anchored* (§147 AO / HGB §257 retention
  runs to the end of the calendar year in which the record arose), so the
  cutoff is deliberately conservative — it never deletes a euro-relevant row
  early.
- **Orders are excluded and flagged, not guessed** — see ``EXCLUDED_NOTE``.

Retention-class map (verified against ``db/models.py`` + the
``20260419_slice_2_security_floor_and_audit_columns`` /
``20260418_add_qr_barcode_core_tables`` migrations):

===============  ===================  ==============  ===================  ==============================
table            retention_class      anchor column   period               action
===============  ===================  ==============  ===================  ==============================
scan_logs        standard_24m         scanned_at      24 months rolling    DELETE (operational log)
time_entries     financial_10y        created_at      10y (year-end)       DELETE (post §147 AO / §257)
material_usage   financial_10y        used_at         10y (year-end)       DELETE (post §147 AO / §257)
orders           indefinite_business  —               indefinite           EXCLUDED (never expires)
orders           hallmark_10y         —               ≥10y (floor)         EXCLUDED + flagged (ambiguous)
===============  ===================  ==============  ===================  ==============================
"""

from __future__ import annotations

import argparse
import asyncio
import calendar
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional, Sequence

from sqlalchemy import select

from goldsmith_erp.db.models import MaterialUsage, ScanLog, TimeEntry

if TYPE_CHECKING:  # pragma: no cover — typing only
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger("goldsmith_erp.jobs.retention_sweep")


# ---------------------------------------------------------------------------
# What we deliberately do NOT sweep (flagged, not guessed).
# ---------------------------------------------------------------------------
#
# ``orders.retention_class`` carries two values, neither of which maps to a
# safe delete trigger:
#   * ``indefinite_business`` (the column default) — an order is a core
#     business record kept indefinitely; nothing ever expires.
#   * ``hallmark_10y`` — promoted the first time a Punzierungs mark is recorded
#     (Feingehaltsgesetz / DIN 8238 evidence). This is a retention *floor*
#     ("must survive ≥10 years"), NOT a "delete at 10 years" instruction; the
#     order may still be an indefinite business record afterwards. Deleting an
#     order also cascades to ``material_usage`` / ``gemstones`` / ``comments``
#     and touches customer PII + design-IP, overlapping the customer-level
#     erasure path (``jobs/gdpr_cleanup.py``). The 10-year anchor is itself
#     ambiguous (``created_at`` vs ``completed_at`` vs ``punzierung_verified_at``).
# Per the "exclude when ambiguous" rule this table is FLAGGED for an explicit
# Anna+Henrik policy decision and left untouched by the sweep.
EXCLUDED_NOTE = (
    "orders (indefinite_business = never expires; hallmark_10y = retention "
    "FLOOR, not a delete trigger; destructive cascade + design-IP + ambiguous "
    "anchor) — EXCLUDED, needs an explicit Anna+Henrik policy decision"
)


# ---------------------------------------------------------------------------
# Date maths
# ---------------------------------------------------------------------------


def _subtract_months(dt: datetime, months: int) -> datetime:
    """Return ``dt`` shifted back ``months`` whole months, clamping the day.

    Dependency-free (no python-dateutil). Clamps e.g. 31 Mar − 1 month → 28/29
    Feb so the result is always a valid date.
    """
    total = dt.year * 12 + (dt.month - 1) - months
    year, month0 = divmod(total, 12)
    month = month0 + 1
    day = min(dt.day, calendar.monthrange(year, month)[1])
    return dt.replace(year=year, month=month, day=day)


@dataclass(frozen=True)
class RetentionRule:
    """One (table, retention_class) sweep rule with its legal anchor."""

    label: str  # table name, used only in logs
    model: type  # ORM model class
    retention_class: str  # the tag value this rule matches
    anchor_attr: str  # column that anchors the retention clock
    pk_attr: str  # primary identifying column (for PK-only structured logs)
    legal_basis: str  # human-readable legal citation
    period_human: str  # human-readable period description
    # Exactly one anchoring strategy is set:
    financial_year_end_years: Optional[int] = None  # §147 AO / HGB §257 year-end
    rolling_months: Optional[int] = None  # operational rolling window

    def cutoff(self, now: datetime) -> datetime:
        """Anchor date: rows with ``anchor < cutoff`` are expired candidates."""
        if self.financial_year_end_years is not None:
            # German statutory retention (§147 AO / HGB §257) runs to the END
            # of the calendar year in which the record arose. A row is
            # deletable only once ``year(anchor) + N < year(now)`` — i.e.
            # ``anchor < 1 Jan of (year(now) - N)``. This is intentionally
            # conservative: a 2015-03 record with N=10 is retained through
            # 2025-12-31 and only becomes a candidate from 2026 onward.
            return datetime(now.year - self.financial_year_end_years, 1, 1)
        if self.rolling_months is not None:
            return _subtract_months(now, self.rolling_months)
        raise ValueError(  # pragma: no cover — guarded by construction
            f"RetentionRule {self.label!r} has no anchoring strategy"
        )


# The sweep rules. ``orders`` is intentionally absent — see ``EXCLUDED_NOTE``.
RETENTION_RULES: tuple[RetentionRule, ...] = (
    RetentionRule(
        label="scan_logs",
        model=ScanLog,
        retention_class="standard_24m",
        anchor_attr="scanned_at",
        pk_attr="id",
        legal_basis=(
            "Operativer Scan-Log — keine gesetzliche Aufbewahrungspflicht; "
            "Datenminimierung Art. 5(1)(e) DSGVO"
        ),
        period_human="24 Monate (rollierendes Fenster)",
        rolling_months=24,
    ),
    RetentionRule(
        label="time_entries",
        model=TimeEntry,
        retention_class="financial_10y",
        # created_at = when the labour record was booked (never NULL; start_time
        # is also non-null but end_time can be NULL for a running timer). The
        # financial-retention clock runs from record creation, so created_at is
        # the correct, always-present anchor.
        anchor_attr="created_at",
        pk_attr="id",
        legal_basis="HGB §257 / §147 AO — 10 Jahre (Arbeitszeit-/Lohnkosten)",
        period_human="10 Jahre (Jahresende-Anker, §147 AO / HGB §257)",
        financial_year_end_years=10,
    ),
    RetentionRule(
        label="material_usage",
        model=MaterialUsage,
        retention_class="financial_10y",
        # used_at = when the metal was consumed (NOT NULL, indexed) — the
        # natural completion timestamp of the consumption event.
        anchor_attr="used_at",
        pk_attr="id",
        legal_basis="HGB §257 / §147 AO — 10 Jahre (Materialverbrauchskosten)",
        period_human="10 Jahre (Jahresende-Anker, §147 AO / HGB §257)",
        financial_year_end_years=10,
    ),
)


# ---------------------------------------------------------------------------
# Result / report types
# ---------------------------------------------------------------------------


@dataclass
class TableResult:
    """Outcome for a single sweep rule."""

    label: str
    retention_class: str
    candidates: int = 0
    deleted: int = 0
    candidate_pks: List[object] = field(default_factory=list)
    error: Optional[str] = None


@dataclass
class RetentionSweepReport:
    """Aggregate report across all rules."""

    executed: bool
    now: datetime
    results: List[TableResult] = field(default_factory=list)

    @property
    def total_candidates(self) -> int:
        return sum(r.candidates for r in self.results)

    @property
    def total_deleted(self) -> int:
        return sum(r.deleted for r in self.results)

    @property
    def failures(self) -> List[TableResult]:
        return [r for r in self.results if r.error is not None]

    @property
    def has_failures(self) -> bool:
        return bool(self.failures)


# ---------------------------------------------------------------------------
# Sweep implementation (testable — takes an explicit session + now)
# ---------------------------------------------------------------------------


async def _sweep_rule(
    db: "AsyncSession",
    rule: RetentionRule,
    result: TableResult,
    *,
    execute: bool,
    now: datetime,
) -> None:
    """Apply one rule: find expired rows, and (only with execute) delete them."""
    model = rule.model
    anchor = getattr(model, rule.anchor_attr)
    cutoff = rule.cutoff(now)

    stmt = (
        select(model)
        .where(getattr(model, "retention_class") == rule.retention_class)
        .where(anchor < cutoff)
    )
    rows = list((await db.execute(stmt)).scalars().all())
    result.candidate_pks = [getattr(row, rule.pk_attr) for row in rows]
    result.candidates = len(rows)

    if not execute:
        logger.info(
            "DRY-RUN table=%s class=%s period=%s cutoff=%s candidates=%d pks=%s",
            rule.label,
            rule.retention_class,
            rule.period_human,
            cutoff.isoformat(),
            result.candidates,
            result.candidate_pks,
        )
        return

    # EXECUTE: delete via ORM objects so delete-orphan cascades fire
    # (e.g. time_entries → interruptions); OrderPhoto.time_entry_id is
    # ON DELETE SET NULL, so photos are detached, not destroyed. Commit
    # atomically for this rule.
    for row in rows:
        await db.delete(row)
    await db.commit()
    result.deleted = len(rows)
    logger.info(
        "DELETED table=%s class=%s period=%s cutoff=%s rows=%d pks=%s",
        rule.label,
        rule.retention_class,
        rule.period_human,
        cutoff.isoformat(),
        result.deleted,
        result.candidate_pks,
    )


async def sweep_retention(
    db: "AsyncSession",
    *,
    execute: bool = False,
    now: Optional[datetime] = None,
    rules: Sequence[RetentionRule] = RETENTION_RULES,
) -> RetentionSweepReport:
    """Run the retention sweep over ``rules`` and return a structured report.

    Each rule is applied independently: a failure in one rule is caught,
    logged with PK ids only, its (uncommitted) work rolled back, and the sweep
    continues with the next rule. The report flags any failure so the CLI can
    exit nonzero (fail-loud — CLAUDE.md).
    """
    now = now or datetime.utcnow()
    report = RetentionSweepReport(executed=execute, now=now)

    for rule in rules:
        result = TableResult(label=rule.label, retention_class=rule.retention_class)
        try:
            await _sweep_rule(db, rule, result, execute=execute, now=now)
        except Exception as exc:  # noqa: BLE001 — per-rule guard: log + continue
            try:
                await db.rollback()
            except Exception:  # pragma: no cover — rollback best-effort
                logger.error("Rollback failed after %s sweep error", rule.label)
            result.error = type(exc).__name__
            logger.error(
                "Retention sweep FAILED table=%s class=%s error=%s pks=%s",
                rule.label,
                rule.retention_class,
                type(exc).__name__,
                result.candidate_pks,
                exc_info=True,
            )
        report.results.append(result)

    return report


# ---------------------------------------------------------------------------
# CLI plumbing (mirrors jobs/gdpr_cleanup.py)
# ---------------------------------------------------------------------------


async def _run(execute: bool) -> RetentionSweepReport:
    """Open a session, run the sweep, return the report.

    The session import is deferred into the coroutine so a misconfigured
    environment surfaces as a logged fatal error (exit 1) rather than an
    import-time crash the shell wrapper cannot classify.
    """
    from goldsmith_erp.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        return await sweep_retention(db, execute=execute)


def _report_exit_code(report: RetentionSweepReport) -> int:
    """Map a sweep report to a process exit code + emit the summary log.

    Pure (no I/O beyond logging) so the exit-code contract is unit-testable.
    Returns ``1`` when any rule failed, ``0`` otherwise (dry-run candidates are
    a report, not a failure).
    """
    mode = "EXECUTE" if report.executed else "DRY-RUN"
    if report.has_failures:
        logger.error(
            "Retention sweep (%s) finished WITH FAILURES: tables_failed=%s "
            "total_candidates=%d total_deleted=%d",
            mode,
            [r.label for r in report.failures],
            report.total_candidates,
            report.total_deleted,
        )
        return 1

    per_table = {
        r.label: (r.deleted if report.executed else r.candidates)
        for r in report.results
    }
    logger.info(
        "Retention sweep (%s) finished OK: total_candidates=%d total_deleted=%d "
        "per_table=%s",
        mode,
        report.total_candidates,
        report.total_deleted,
        per_table,
    )
    return 0


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m goldsmith_erp.jobs.retention_sweep",
        description=(
            "Enforce per-entity retention_class buckets. DRY-RUN by default "
            "(counts + logs candidates, deletes nothing)."
        ),
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help=(
            "Actually delete expired rows. Without this flag the job runs in "
            "DRY-RUN mode (default) and touches nothing."
        ),
    )
    return parser.parse_args(list(argv))


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point. Returns the process exit code (0 ok, 1 failure)."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    logger.info(
        "Retention sweep starting (mode=%s). Excluded: %s",
        "EXECUTE" if args.execute else "DRY-RUN",
        EXCLUDED_NOTE,
    )

    try:
        report = asyncio.run(_run(args.execute))
    except Exception:  # noqa: BLE001 — top-level guard: log + nonzero exit
        logger.error("Retention sweep crashed before completing", exc_info=True)
        return 1

    return _report_exit_code(report)


if __name__ == "__main__":
    sys.exit(main())
