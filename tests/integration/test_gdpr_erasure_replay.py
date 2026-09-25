"""Erasure ledger export + replay after a restore (GDPR-07), on SQLite.

The scenario the ledger exists for: a customer is erased, then the database
is restored from a dump taken BEFORE the erasure. The restored row is active
again and carries no ``deletion_scheduled_at``; the cleanup job alone would
never touch it. Replaying the ledger must re-erase it.
"""

from __future__ import annotations

import io
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.cli import gdpr_replay_erasures as cli
from goldsmith_erp.db.models import Customer, GDPRRequest
from goldsmith_erp.services.gdpr_erasure_ledger import (
    ERASURE_GRACE_PERIOD,
    REPLAY_REQUEST_TYPE,
    LedgerEntry,
    LedgerFormatError,
    collect_ledger_entries,
    merge_new_entries,
    read_ledger,
    replay_erasures,
    write_entries,
)


async def _restored_customer(db: AsyncSession) -> Customer:
    """A customer as it looks after restoring a pre-erasure dump."""
    customer = Customer(
        first_name="Erika",
        last_name="Musterfrau",
        email=f"replay_{uuid.uuid4().hex[:8]}@example.com",
        phone="+49 30 1234567",
        customer_type="private",
        is_active=True,
        notes="Kundin Erika Musterfrau ruft oft an",
    )
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    return customer


def _entry(
    customer_id: int,
    *,
    request_type: str = "erasure",
    requested_at: datetime,
    request_id: int = 9000,
) -> LedgerEntry:
    return LedgerEntry(
        gdpr_request_id=request_id,
        request_type=request_type,
        status="completed",
        customer_id=customer_id,
        user_id=None,
        requested_at=requested_at,
        completed_at=requested_at,
    )


@pytest.mark.asyncio
async def test_dry_run_reports_but_changes_nothing(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    customer = await _restored_customer(db_session)
    now = datetime.utcnow()
    entry = _entry(customer.id, requested_at=now - timedelta(days=2))

    report = await replay_erasures(
        db_session,
        [entry],
        since=now - timedelta(days=5),
        execute=False,
        now=now,
        storage_root=tmp_path,
    )

    assert report.executed is False
    assert [(o.subject_id, o.action) for o in report.outcomes] == [
        (customer.id, "would_re_erase")
    ]
    await db_session.refresh(customer)
    assert customer.is_active is True
    assert customer.deletion_scheduled_at is None
    replay_rows = (
        (
            await db_session.execute(
                select(GDPRRequest).where(
                    GDPRRequest.request_type == REPLAY_REQUEST_TYPE,
                    GDPRRequest.customer_id == customer.id,
                )
            )
        )
        .scalars()
        .all()
    )
    assert replay_rows == []


@pytest.mark.asyncio
async def test_execute_reerases_customer_inside_grace_period(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    customer = await _restored_customer(db_session)
    now = datetime.utcnow()
    requested = now - timedelta(days=2)

    report = await replay_erasures(
        db_session,
        [_entry(customer.id, requested_at=requested)],
        since=now - timedelta(days=5),
        execute=True,
        now=now,
        storage_root=tmp_path,
    )

    assert not report.has_failures
    assert report.outcomes[0].action == "re_erased"
    assert report.outcomes[0].finalize is False
    await db_session.refresh(customer)
    assert customer.is_active is False
    # The original grace period is kept, not restarted.
    assert customer.deletion_scheduled_at == requested + ERASURE_GRACE_PERIOD
    assert "Musterfrau" not in (customer.notes or "")
    replay_row = (
        await db_session.execute(
            select(GDPRRequest).where(
                GDPRRequest.request_type == REPLAY_REQUEST_TYPE,
                GDPRRequest.customer_id == customer.id,
            )
        )
    ).scalar_one()
    assert replay_row.status == "completed"


@pytest.mark.asyncio
async def test_execute_finalizes_customer_whose_cleanup_had_run(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    customer = await _restored_customer(db_session)
    customer_id = customer.id
    now = datetime.utcnow()
    entries = [
        _entry(customer_id, requested_at=now - timedelta(days=40), request_id=1),
        _entry(
            customer_id,
            request_type="erasure_cleanup",
            requested_at=now - timedelta(days=9),
            request_id=2,
        ),
    ]

    report = await replay_erasures(
        db_session,
        entries,
        since=now - timedelta(days=60),
        execute=True,
        now=now,
        storage_root=tmp_path,
    )

    assert not report.has_failures
    assert report.finalized_customer_ids == [customer_id]
    db_session.expire_all()
    gone = (
        await db_session.execute(select(Customer).where(Customer.id == customer_id))
    ).scalar_one_or_none()
    assert gone is None  # no retained financial records → hard delete


@pytest.mark.asyncio
async def test_entries_older_than_backup_are_skipped_and_missing_rows_reported(
    db_session: AsyncSession, tmp_path: Path
) -> None:
    customer = await _restored_customer(db_session)
    now = datetime.utcnow()
    old = _entry(customer.id, requested_at=now - timedelta(days=90), request_id=1)
    absent = _entry(987654, requested_at=now - timedelta(days=1), request_id=2)

    report = await replay_erasures(
        db_session,
        [old, absent],
        since=now - timedelta(days=10),
        execute=True,
        now=now,
        storage_root=tmp_path,
    )

    assert report.entries_total == 2
    assert report.entries_considered == 1
    assert [(o.subject_id, o.action) for o in report.outcomes] == [(987654, "absent")]
    await db_session.refresh(customer)
    assert customer.is_active is True


@pytest.mark.asyncio
async def test_collect_ledger_keeps_only_executed_erasures(
    db_session: AsyncSession,
) -> None:
    now = datetime.utcnow()
    db_session.add_all(
        [
            GDPRRequest(
                customer_id=501,
                request_type="erasure",
                status="completed",
                requested_at=now,
                completed_at=now,
            ),
            GDPRRequest(
                customer_id=502,
                request_type="erasure",
                status="PARTIAL_FILE_ERASURE",
                requested_at=now,
                completed_at=now,
            ),
            GDPRRequest(
                customer_id=503,
                request_type="erasure",
                status="FAILED",
                requested_at=now,
            ),
            GDPRRequest(
                customer_id=504,
                request_type="erasure",
                status="PENDING",
                requested_at=now,
            ),
            GDPRRequest(
                customer_id=505,
                request_type="export",
                status="completed",
                requested_at=now,
            ),
            GDPRRequest(
                customer_id=None,
                request_type="erasure_user",
                status="completed",
                requested_at=now,
                completed_at=now,
                notes="anonymize_user(user_id=77) hmac=abc reason=test",
            ),
        ]
    )
    await db_session.commit()

    entries = await collect_ledger_entries(db_session)

    customer_ids = {e.customer_id for e in entries if e.customer_id}
    assert {501, 502} <= customer_ids
    assert not {503, 504, 505} & customer_ids
    assert 77 in {e.user_id for e in entries if e.request_type == "erasure_user"}


def test_ledger_round_trip_and_dedupe() -> None:
    now = datetime(2026, 9, 25, 3, 0, 0)
    entries = [_entry(1, requested_at=now), _entry(2, requested_at=now, request_id=2)]
    buffer = io.StringIO()
    write_entries(entries, buffer)

    parsed = read_ledger(io.StringIO("# comment\n\n" + buffer.getvalue()))

    assert parsed == entries
    assert merge_new_entries(parsed, entries) == []
    # Same row id after a sequence rewind but a different request: kept.
    reused = _entry(3, requested_at=now + timedelta(days=1), request_id=1)
    assert merge_new_entries(parsed, [reused]) == [reused]


def test_malformed_ledger_line_fails_loudly() -> None:
    with pytest.raises(LedgerFormatError, match="line 2"):
        read_ledger(io.StringIO("\nnot-json\n"))


def test_cli_rejects_malformed_ledger_with_exit_2(tmp_path: Path) -> None:
    ledger = tmp_path / "ledger.jsonl"
    ledger.write_text("garbage\n", encoding="utf-8")

    code = cli.main(["replay", "--ledger", str(ledger)])

    assert code == cli.EXIT_USAGE


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("2026-09-20T03:00:00+0200", datetime(2026, 9, 20, 1, 0, 0)),
        ("2026-09-20T03:00:00+02:00", datetime(2026, 9, 20, 1, 0, 0)),
        ("2026-09-20T03:00:00Z", datetime(2026, 9, 20, 3, 0, 0)),
        ("2026-09-20T03:00:00", datetime(2026, 9, 20, 3, 0, 0)),
    ],
)
def test_parse_since_normalises_to_naive_utc(raw: str, expected: datetime) -> None:
    assert cli.parse_since(raw) == expected
