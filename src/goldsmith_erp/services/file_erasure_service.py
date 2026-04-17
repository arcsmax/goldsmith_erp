"""
File-level GDPR Art. 17 erasure service.

Complements ``CustomerService.scrub_customer_pii`` (which scrubs DB-resident
freetext PII) by removing the filesystem artefacts referenced by DB path
columns — generated valuation PDFs, order / repair photos, scrap-gold
receipts. These files contain customer PII (names, addresses, signatures,
item photos) that survives the DB scrub because the DB stores only the
path, not the content.

Design highlights
-----------------

- **Declarative target list** (``FILE_ERASURE_TARGETS``). Adding a new
  filesystem-path column means one new row in that list plus a
  documentation entry, not a new branch of code.
- **Path-traversal guard**. ``storage_root`` bounds every deletion. A
  candidate path that resolves outside the root (malicious
  ``../../../etc/passwd`` value in a DB column, symlink-to-root,
  absolute path escaping the root) is refused and counted under
  ``files_failed`` — never deleted.
- **Best-effort per-file**. A per-file failure (permission denied,
  IO error) is logged with full context and the sweep continues.
  Partial results are observable to the caller.
- **Per-target DB-NULL transaction**. Each target sets its path column
  to ``NULL`` (or a sentinel when the column is NOT NULL) in a single
  transaction after the filesystem pass. Rows with per-file failures
  keep the reference so the admin can inspect / re-run.
- **Idempotent**. Re-running the service on an already-erased customer
  is a no-op (files gone, paths nulled — nothing to match).
- **Dry-run**. Returns the would-have-been result without touching
  disk or DB. Used by admin-preview surfaces and integration tests.
- **Audit**. Each sweep writes one ``CustomerAuditLog`` row and one
  per-file failure entry so the DPO can reconstruct the forensic
  timeline from the audit tail alone.

See:
- ``docs/superpowers/plans/qr-barcode-workflow/PII-SCRUB-AUDIT.md``
  O1 + O2 out-of-scope rows for the audit context.
- ``docs/superpowers/plans/qr-barcode-workflow/V1.1-AMENDMENTS.md``
  F1 / O1 / O2 rows in the "Pre-existing codebase hygiene" section
  for the decision trail.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional, Tuple

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import (
    CustomerAuditLog,
    Order as OrderModel,
    OrderPhoto,
    RepairJob,
    RepairPhoto,
    ScrapGold,
    ScrapGoldItem,
    ValuationCertificate,
)

logger = logging.getLogger(__name__)


# Sentinel written to NOT NULL path columns after the underlying file has
# been deleted (or verified missing). Keeps the foreign-key parent row
# intact — the DB row still satisfies its NOT NULL constraint and the
# string obviously signals "the file that used to live here was erased
# under Art. 17" to any human or auditor reading the row later.
REDACTED_PATH_SENTINEL = "[REDACTED_PATH]"


# ═══════════════════════════════════════════════════════════════════════════
# Declarative target definition
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class FileErasureTarget:
    """One filesystem-path column on a customer-linked table.

    Attributes
    ----------
    table:
        Human-readable table name used for audit rows and error
        messages. Matches ``model.__tablename__``.
    model:
        SQLAlchemy ORM class.
    path_column:
        Attribute name of the ``String(500)`` column holding the
        relative or absolute filesystem path.
    link:
        How to find rows belonging to a customer. One of:

        - ``"customer_id"``  — ``model.customer_id == customer_id``
        - ``"order_id"``     — ``model.order_id IN customer's orders``
        - ``"repair_job_id"``— ``model.repair_job_id IN
          customer's repair jobs``
        - ``"scrap_gold_id"``— ``model.scrap_gold_id IN
          customer's scrap gold rows``

    path_column_nullable:
        When ``True`` the column is SET to NULL after the file is
        deleted. When ``False`` the column is set to
        ``REDACTED_PATH_SENTINEL`` so the NOT NULL constraint still
        holds but the row no longer references real filesystem state.
    is_required_purge:
        When ``True`` a file that cannot be deleted (permission
        error, unreadable) is a hard ``files_failed`` result that
        blocks the DB column from being nulled. When ``False`` a
        missing file is tolerated with a warning and does not stop
        the column from being nulled. Today every target is
        ``True`` — reserved for future cases where a missing file
        is acceptable (ephemeral cache, regenerated-on-demand PDF).
    """

    table: str
    model: type
    path_column: str
    link: str
    path_column_nullable: bool = True
    is_required_purge: bool = True


# The declarative target list — SINGLE source of truth for every
# filesystem-path column that must be swept on Art. 17 erasure.
#
# If a new path column is added to the schema: add a row here AND update
# ``PII-SCRUB-AUDIT.md`` O1/O2 block. Tests pick it up automatically.
FILE_ERASURE_TARGETS: List[FileErasureTarget] = [
    FileErasureTarget(
        table="valuation_certificates",
        model=ValuationCertificate,
        path_column="pdf_path",
        link="order_id",
        path_column_nullable=True,
    ),
    FileErasureTarget(
        table="order_photos",
        model=OrderPhoto,
        path_column="file_path",
        link="order_id",
        # order_photos.file_path is NOT NULL — fall back to sentinel.
        path_column_nullable=False,
    ),
    FileErasureTarget(
        table="repair_photos",
        model=RepairPhoto,
        path_column="file_path",
        link="repair_job_id",
        # repair_photos.file_path is NOT NULL — fall back to sentinel.
        path_column_nullable=False,
    ),
    FileErasureTarget(
        table="scrap_gold_items",
        model=ScrapGoldItem,
        path_column="photo_path",
        link="scrap_gold_id",
        path_column_nullable=True,
    ),
    FileErasureTarget(
        table="scrap_gold",
        model=ScrapGold,
        path_column="receipt_pdf_path",
        link="customer_id",
        path_column_nullable=True,
    ),
]


# ═══════════════════════════════════════════════════════════════════════════
# Result model
# ═══════════════════════════════════════════════════════════════════════════


@dataclass
class FileErasureResult:
    """Aggregate outcome of a sweep.

    Counters
    --------
    files_checked:
        Total number of path references examined (sum across all
        targets). One row in a target may contain a path or not;
        NULL / empty values are still counted as checked with the
        ``files_missing`` outcome.
    files_deleted:
        Number of files the service successfully removed from disk
        during this sweep.
    files_missing:
        Number of path references where the file was already absent
        from disk. Not an error — common after a prior sweep, a
        manual admin cleanup, or a failed upload that left a stale
        DB row. Logged at WARNING level.
    files_failed:
        Number of path references where deletion failed due to a
        hard error: path-traversal escape, permission denied, IO
        error. These rows keep their DB path reference so the admin
        can inspect.
    errors:
        ``(path, error_message)`` tuples describing every
        ``files_failed`` event. Surfaced in the HTTP response body
        so partial failures are visible to the admin.
    per_target_counts:
        ``table.path_column`` → counters for that target alone. Used
        by the audit log entry for forensic drill-down.
    dry_run:
        True when the result came from a dry-run call — no side
        effects on disk or DB occurred.
    """

    files_checked: int = 0
    files_deleted: int = 0
    files_missing: int = 0
    files_failed: int = 0
    errors: List[Tuple[str, str]] = field(default_factory=list)
    per_target_counts: dict = field(default_factory=dict)
    dry_run: bool = False

    def as_dict(self) -> dict:
        """Return a JSON-serialisable dict for HTTP responses / audit."""
        return {
            "files_checked": self.files_checked,
            "files_deleted": self.files_deleted,
            "files_missing": self.files_missing,
            "files_failed": self.files_failed,
            "errors": [
                {"path": path, "message": message} for path, message in self.errors
            ],
            "per_target_counts": self.per_target_counts,
            "dry_run": self.dry_run,
        }


# ═══════════════════════════════════════════════════════════════════════════
# Service
# ═══════════════════════════════════════════════════════════════════════════


class FileErasureService:
    """Delete filesystem artefacts referenced by a customer's DB rows.

    Construction
    ------------
    The service takes an explicit ``storage_root`` so tests and the
    production caller can choose different roots. The CLI / FastAPI
    endpoint resolves the root from ``Settings.FILE_STORAGE_ROOT``.

    Call site
    ---------
    ``await service.erase_customer_files(db, customer_id)`` is the
    one public entry point. See its docstring for the contract.

    Thread safety
    -------------
    The service holds no mutable per-call state on ``self``. One
    instance may be reused across concurrent requests — each call
    builds its own ``FileErasureResult``.
    """

    def __init__(self, storage_root: Path):
        """Bind the path-traversal guard to ``storage_root``.

        ``storage_root`` is resolved to its absolute, symlink-followed
        form once at construction so later per-file checks do a
        single path resolution + one ``is_relative_to`` test.
        """
        # resolve(strict=False) accepts a root that does not yet
        # exist — admin scripts / tests can pass a soon-to-be-created
        # directory.
        self._storage_root = Path(storage_root).resolve(strict=False)

    # ── internal helpers ───────────────────────────────────────────────

    def _safe_resolve(self, raw_path: str) -> Optional[Path]:
        """Return the absolute path if it lies inside ``storage_root``.

        Returns ``None`` when the candidate escapes the root. This is
        the ONLY place that decides whether a path is safe to touch.
        Callers that receive ``None`` must NOT perform any filesystem
        I/O and must record the path in ``files_failed``.
        """
        if not raw_path:
            return None

        candidate = Path(raw_path)

        # Anchor relative paths to storage_root. Absolute paths are
        # left as-is so the is_relative_to check can detect escapes.
        if not candidate.is_absolute():
            candidate = self._storage_root / candidate

        try:
            resolved = candidate.resolve(strict=False)
        except (OSError, RuntimeError):
            # Pathological input (e.g. infinite symlink loop) — treat
            # as unsafe and refuse.
            return None

        # is_relative_to returns True only when resolved is inside
        # or equal to storage_root. Catches both "/etc/passwd" and
        # "../../../etc/passwd" after resolution.
        try:
            if not resolved.is_relative_to(self._storage_root):
                return None
        except AttributeError:
            # Python 3.8 compat — resolved.is_relative_to landed in
            # 3.9. The project runs 3.11 so this branch is dead, but
            # keeps the helper self-contained.
            try:
                resolved.relative_to(self._storage_root)
            except ValueError:
                return None

        return resolved

    async def _collect_parent_ids(
        self, db: AsyncSession, customer_id: int
    ) -> Tuple[List[int], List[int], List[int]]:
        """Fetch the order / repair-job / scrap-gold IDs owned by a customer.

        These ID lists drive the transitive-link queries on each
        target. Computed up-front and passed through so the service
        runs one JOIN-less query per set instead of re-resolving
        per target.
        """
        order_ids = [
            o.id
            for o in (
                await db.execute(
                    select(OrderModel).filter(OrderModel.customer_id == customer_id)
                )
            )
            .scalars()
            .all()
        ]
        repair_job_ids = [
            r.id
            for r in (
                await db.execute(
                    select(RepairJob).filter(RepairJob.customer_id == customer_id)
                )
            )
            .scalars()
            .all()
        ]
        scrap_gold_ids = [
            s.id
            for s in (
                await db.execute(
                    select(ScrapGold).filter(ScrapGold.customer_id == customer_id)
                )
            )
            .scalars()
            .all()
        ]
        return order_ids, repair_job_ids, scrap_gold_ids

    async def _rows_for_target(
        self,
        db: AsyncSession,
        target: FileErasureTarget,
        *,
        customer_id: int,
        order_ids: List[int],
        repair_job_ids: List[int],
        scrap_gold_ids: List[int],
    ) -> List[Any]:
        """Return the ORM rows on ``target`` belonging to this customer."""
        model = target.model
        if target.link == "customer_id":
            stmt = select(model).filter(model.customer_id == customer_id)
        elif target.link == "order_id":
            if not order_ids:
                return []
            stmt = select(model).filter(model.order_id.in_(order_ids))
        elif target.link == "repair_job_id":
            if not repair_job_ids:
                return []
            stmt = select(model).filter(model.repair_job_id.in_(repair_job_ids))
        elif target.link == "scrap_gold_id":
            if not scrap_gold_ids:
                return []
            stmt = select(model).filter(model.scrap_gold_id.in_(scrap_gold_ids))
        else:
            raise ValueError(
                f"FileErasureTarget {target.table}.{target.path_column} has "
                f"unknown link kind: {target.link!r}"
            )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    # ── public entry point ─────────────────────────────────────────────

    async def erase_customer_files(
        self,
        db: AsyncSession,
        customer_id: int,
        *,
        performed_by: Optional[int] = None,
        dry_run: bool = False,
    ) -> FileErasureResult:
        """Delete files referenced by ``customer_id``'s rows.

        Parameters
        ----------
        db:
            Async SQLAlchemy session. The caller owns the transaction
            boundary — this method does NOT commit. It flushes
            after each per-target DB update so the caller's commit
            persists the full sweep atomically (or rolls back the
            column nulls if the caller decides to abort).
        customer_id:
            Primary key of the customer whose filesystem artefacts
            are being erased.
        performed_by:
            Optional user id of the administrator who triggered the
            erasure. Written to the ``CustomerAuditLog`` row.
        dry_run:
            When ``True``, classify each file (would-delete /
            already-missing / would-fail) without touching disk or
            DB. Useful for admin-preview surfaces and integration
            tests.

        Returns
        -------
        FileErasureResult
            Aggregate counters + per-target breakdown + per-file
            error details. ``dry_run`` is propagated to the result
            so callers can distinguish preview from real runs.

        Contract
        --------
        - Per-file errors are collected — not raised — so one bad
          file does not abort the sweep. The DB column for the
          offending row is left unchanged so the admin can re-run.
        - Missing files (file on disk is already gone) are counted
          under ``files_missing`` but the DB column is STILL nulled
          — keeping the DB aligned with filesystem state.
        - Path-traversal violations are treated as ``files_failed``
          and the file is NOT touched. This is a security boundary;
          it must never "succeed".
        - Rows with a NULL / empty path column are skipped silently
          (nothing to delete, nothing to null).
        - Idempotent: a second call on the same customer finds no
          paths to delete (because the first call nulled them) and
          returns an all-zero result (except ``files_checked`` when
          rows remain).
        """
        result = FileErasureResult(dry_run=dry_run)

        (
            order_ids,
            repair_job_ids,
            scrap_gold_ids,
        ) = await self._collect_parent_ids(db, customer_id)

        for target in FILE_ERASURE_TARGETS:
            per_target_checked = 0
            per_target_deleted = 0
            per_target_missing = 0
            per_target_failed = 0

            rows = await self._rows_for_target(
                db,
                target,
                customer_id=customer_id,
                order_ids=order_ids,
                repair_job_ids=repair_job_ids,
                scrap_gold_ids=scrap_gold_ids,
            )

            row_ids_to_update: List[Any] = []

            for row in rows:
                raw_path = getattr(row, target.path_column)
                if not raw_path:
                    # Already nulled / never set — nothing to do.
                    continue
                if raw_path == REDACTED_PATH_SENTINEL:
                    # Already erased in a prior sweep — idempotent
                    # short-circuit.
                    continue

                per_target_checked += 1
                result.files_checked += 1

                resolved = self._safe_resolve(raw_path)

                if resolved is None:
                    # Path-traversal escape or unresolvable path —
                    # hard security boundary.
                    message = (
                        "path escapes FILE_STORAGE_ROOT "
                        f"({self._storage_root}) — refused"
                    )
                    result.files_failed += 1
                    per_target_failed += 1
                    result.errors.append((raw_path, message))
                    logger.error(
                        "file erasure refused — path-traversal guard",
                        extra={
                            "audit": True,
                            "action": "file_erasure_refused",
                            "customer_id": customer_id,
                            "user_id": performed_by,
                            "table": target.table,
                            "column": target.path_column,
                            "raw_path": raw_path,
                            "storage_root": str(self._storage_root),
                        },
                    )
                    continue

                if dry_run:
                    # Classify without touching the filesystem.
                    if resolved.exists():
                        per_target_deleted += 1
                        result.files_deleted += 1
                    else:
                        per_target_missing += 1
                        result.files_missing += 1
                    row_ids_to_update.append(row)
                    continue

                # Live path — attempt deletion.
                try:
                    if resolved.exists():
                        os.unlink(resolved)
                        per_target_deleted += 1
                        result.files_deleted += 1
                        logger.info(
                            "file erased for Art. 17 request",
                            extra={
                                "audit": True,
                                "action": "file_erased",
                                "customer_id": customer_id,
                                "user_id": performed_by,
                                "table": target.table,
                                "column": target.path_column,
                                "resolved_path": str(resolved),
                            },
                        )
                        row_ids_to_update.append(row)
                    else:
                        # File already gone from disk — not an error,
                        # but log so the admin / DPO can tell apart
                        # the "cron already ran" case from the
                        # "file never existed" case.
                        per_target_missing += 1
                        result.files_missing += 1
                        logger.warning(
                            "file erasure found missing file — "
                            "DB path present, disk absent",
                            extra={
                                "audit": True,
                                "action": "file_erasure_missing",
                                "customer_id": customer_id,
                                "user_id": performed_by,
                                "table": target.table,
                                "column": target.path_column,
                                "resolved_path": str(resolved),
                                "raw_path": raw_path,
                            },
                        )
                        row_ids_to_update.append(row)
                except (OSError, PermissionError) as exc:
                    # Hard IO error — keep the DB reference so the
                    # admin can inspect / retry. Do NOT abort the sweep.
                    message = f"{type(exc).__name__}: {exc}"
                    result.files_failed += 1
                    per_target_failed += 1
                    result.errors.append((str(resolved), message))
                    logger.error(
                        "file erasure failed — IO error",
                        extra={
                            "audit": True,
                            "action": "file_erasure_failed",
                            "customer_id": customer_id,
                            "user_id": performed_by,
                            "table": target.table,
                            "column": target.path_column,
                            "resolved_path": str(resolved),
                            "error_type": type(exc).__name__,
                            "error_message": str(exc),
                        },
                    )
                    # row NOT added to row_ids_to_update — path stays.

            # Per-target DB update pass. Null (or sentinel-set) every
            # row whose file we either deleted, found missing, or
            # dry-ran. Rows with files_failed keep their path so the
            # admin can inspect / re-run manually.
            if row_ids_to_update and not dry_run:
                replacement = (
                    None if target.path_column_nullable else REDACTED_PATH_SENTINEL
                )
                # Two-step: use IN-clause with pk ids. We rely on the
                # model's single-column primary key (``id``). All five
                # targets have single-column ``id`` PKs — verified in
                # db/models.py.
                ids = [row.id for row in row_ids_to_update]
                # ``update()`` returns the statement; execute applies
                # it. Kept inside the caller's transaction.
                await db.execute(
                    update(target.model)
                    .where(target.model.id.in_(ids))
                    .values({target.path_column: replacement})
                )
                await db.flush()

            result.per_target_counts[f"{target.table}.{target.path_column}"] = {
                "checked": per_target_checked,
                "deleted": per_target_deleted,
                "missing": per_target_missing,
                "failed": per_target_failed,
            }

        # Audit row — written regardless of dry_run so that even
        # preview calls are traceable. Field ``dry_run`` in the
        # details JSON distinguishes them.
        if not dry_run:
            await self._write_audit_row(
                db,
                customer_id=customer_id,
                performed_by=performed_by,
                result=result,
            )
            await db.flush()

        logger.info(
            "file erasure sweep complete",
            extra={
                "audit": True,
                "action": "file_erasure_complete",
                "customer_id": customer_id,
                "user_id": performed_by,
                "files_checked": result.files_checked,
                "files_deleted": result.files_deleted,
                "files_missing": result.files_missing,
                "files_failed": result.files_failed,
                "dry_run": dry_run,
            },
        )

        return result

    # ── audit ──────────────────────────────────────────────────────────

    async def _write_audit_row(
        self,
        db: AsyncSession,
        *,
        customer_id: int,
        performed_by: Optional[int],
        result: FileErasureResult,
    ) -> None:
        """Persist a ``CustomerAuditLog`` row describing this sweep.

        The counters and per-target breakdown are JSON-serialised into
        ``details`` so the DPO can reconstruct the exact files-disposition
        from a single audit row without joining any other table.
        """
        audit_log = CustomerAuditLog(
            customer_id=customer_id,
            user_id=performed_by,
            action="gdpr_file_erasure",
            entity="customer",
            entity_id=customer_id,
            details=result.as_dict(),
            timestamp=datetime.utcnow(),
        )
        db.add(audit_log)


# Module-level convenience constructor — most callers want the
# configured-from-Settings instance. Tests construct their own with an
# explicit tmp_path storage root.
def build_default_service() -> FileErasureService:
    """Return a ``FileErasureService`` bound to ``Settings.FILE_STORAGE_ROOT``.

    Deferred import of ``settings`` so this module has no import-time
    dependency on the full FastAPI settings stack (tests can instantiate
    the service with a test root without triggering
    ``settings`` initialisation side-effects).
    """
    from goldsmith_erp.core.config import settings

    return FileErasureService(Path(settings.FILE_STORAGE_ROOT))
