"""H10 — ``gdpr_requests`` row written on BOTH success AND failure paths.

Anna Becker's post-wave-5 compliance audit §4 finding H10 requires that
EVERY Art. 17 erasure request — including those that 404, 409, or fail
mid-flight — leaves a trail in the ``gdpr_requests`` table so the DPO
can audit the Verzeichnis der Verarbeitungstätigkeiten (Art. 30).

Flow:
  1. Endpoint writes ``status='PENDING'`` row BEFORE any validation.
  2. On success → promoted to ``'completed'``.
  3. On partial file failure → promoted to ``'PARTIAL_FILE_ERASURE'``.
  4. On validation / not-found / 409 → promoted to ``'FAILED'`` with a
     non-PII error summary.
  5. On unexpected exception during scrub / file sweep → promoted to
     ``'FAILED'``; the original exception still propagates as HTTP 500.

Tests use the mounted FastAPI app (via ``client``) so the full router
path runs, including the dependency-injected idempotency context and
the permission check.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import Customer, GDPRRequest


def _erase_url(customer_id: int) -> str:
    return f"/api/v1/customers/{customer_id}/gdpr-erase"


async def _all_gdpr_rows(
    db: AsyncSession, customer_id: int
) -> list[GDPRRequest]:
    result = await db.execute(
        select(GDPRRequest)
        .filter(GDPRRequest.customer_id == customer_id)
        .order_by(GDPRRequest.id.asc())
    )
    return list(result.scalars())


class TestH10HappyPath:
    """Row transitions PENDING → completed on successful erasure."""

    @pytest.mark.asyncio
    async def test_success_path_row_written_as_pending_then_completed(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_customer: Customer,
        admin_auth_headers: dict,
    ):
        response = await client.delete(
            _erase_url(test_customer.id), headers=admin_auth_headers
        )
        assert response.status_code == 200

        rows = await _all_gdpr_rows(db_session, test_customer.id)
        # Exactly one row — the router owns the full lifecycle.
        assert len(rows) == 1, (
            f"Expected exactly one gdpr_requests row, got {len(rows)}: "
            f"{[r.status for r in rows]}"
        )
        row = rows[0]
        assert row.status == "completed"
        assert row.request_type == "erasure"
        assert row.requested_at is not None
        assert row.completed_at is not None
        # Notes carry both the PENDING preamble and the terminal suffix.
        assert "received" in (row.notes or "").lower()
        assert "scrubbed" in (row.notes or "").lower()


class TestH10NotFoundPath:
    """404 → FAILED row with a non-PII error summary."""

    @pytest.mark.asyncio
    async def test_customer_not_found_writes_failed_row(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        admin_auth_headers: dict,
    ):
        nonexistent_id = 9_999_999
        response = await client.delete(
            _erase_url(nonexistent_id), headers=admin_auth_headers
        )
        assert response.status_code == 404

        rows = await _all_gdpr_rows(db_session, nonexistent_id)
        assert len(rows) == 1, (
            "404 path must still leave an Art. 30 trail"
        )
        row = rows[0]
        assert row.status == "FAILED"
        assert "customer_not_found" in (row.notes or "")
        # No PII in error notes.
        assert row.completed_at is not None


class TestH10ConflictPath:
    """409 (already scheduled) → FAILED row with 'already_scheduled'."""

    @pytest.mark.asyncio
    async def test_already_scheduled_writes_failed_row(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_customer: Customer,
        admin_auth_headers: dict,
    ):
        # First erasure succeeds.
        first = await client.delete(
            _erase_url(test_customer.id), headers=admin_auth_headers
        )
        assert first.status_code == 200

        rows_after_first = await _all_gdpr_rows(db_session, test_customer.id)
        assert len(rows_after_first) == 1
        assert rows_after_first[0].status == "completed"

        # Second request conflicts — customer already scheduled.
        second = await client.delete(
            _erase_url(test_customer.id), headers=admin_auth_headers
        )
        assert second.status_code == 409

        rows_after_second = await _all_gdpr_rows(db_session, test_customer.id)
        # Now TWO rows — first completed, second FAILED/already_scheduled.
        assert len(rows_after_second) == 2
        second_row = rows_after_second[1]
        assert second_row.status == "FAILED"
        assert "already_scheduled" in (second_row.notes or "")


class TestH10PartialFilePath:
    """Partial file failure → PARTIAL_FILE_ERASURE terminal status."""

    @pytest.mark.asyncio
    async def test_partial_file_failure_writes_partial_status(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_customer: Customer,
        admin_user,
        admin_auth_headers: dict,
        tmp_path,
        monkeypatch,
    ):
        import uuid as _uuid

        from goldsmith_erp.db.models import (
            Order,
            OrderPhoto,
            OrderStatusEnum,
        )

        monkeypatch.setattr(
            "goldsmith_erp.core.config.settings.FILE_STORAGE_ROOT",
            str(tmp_path),
        )

        order = Order(
            title="X",
            customer_id=test_customer.id,
            status=OrderStatusEnum.NEW,
        )
        db_session.add(order)
        await db_session.commit()
        await db_session.refresh(order)

        rel_path = f"photos/{_uuid.uuid4().hex}.jpg"
        abs_path = tmp_path / rel_path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_bytes(b"jpeg")
        photo = OrderPhoto(
            order_id=order.id,
            file_path=rel_path,
            taken_by=admin_user.id,
        )
        db_session.add(photo)
        await db_session.commit()

        def _raise(*args, **kwargs):
            raise PermissionError("EACCES: mocked")

        monkeypatch.setattr(
            "goldsmith_erp.services.file_erasure_service.os.unlink",
            _raise,
        )

        response = await client.delete(
            _erase_url(test_customer.id), headers=admin_auth_headers
        )
        assert response.status_code == 207

        rows = await _all_gdpr_rows(db_session, test_customer.id)
        assert len(rows) == 1
        assert rows[0].status == "PARTIAL_FILE_ERASURE"
        assert "File-erasure partial failure" in (rows[0].notes or "")


class TestH10UnexpectedExceptionPath:
    """Exception during scrub → original error propagates, row marked FAILED."""

    @pytest.mark.asyncio
    async def test_scrub_exception_still_writes_failed_row(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_customer: Customer,
        admin_auth_headers: dict,
    ):
        """Patch CustomerService.scrub_customer_pii to raise; verify the
        PENDING row is promoted to FAILED and the endpoint returns 500.
        """
        # Capture the id as a plain int — the test's db_session is also
        # the endpoint's session, and a rollback on the endpoint side
        # expires attributes on attached objects.
        customer_id = int(test_customer.id)

        with patch(
            "goldsmith_erp.api.routers.customers."
            "CustomerService.scrub_customer_pii",
            side_effect=RuntimeError("simulated scrub failure"),
        ):
            response = await client.delete(
                _erase_url(customer_id), headers=admin_auth_headers
            )
        assert response.status_code == 500

        rows = await _all_gdpr_rows(db_session, customer_id)
        assert len(rows) == 1, (
            "Unexpected-exception path must still leave an Art. 30 trail"
        )
        row = rows[0]
        assert row.status == "FAILED"
        assert "scrub_or_file_erasure_exception" in (row.notes or "")


class TestH10AuditRowCount:
    """Query-only test: per-scenario row count + status matrix."""

    @pytest.mark.asyncio
    async def test_scenarios_produce_expected_row_status(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_customer: Customer,
        admin_auth_headers: dict,
    ):
        """404 (nonexistent) → 1 FAILED row; 200 (existing) → 1 completed
        row. Separately visible queries."""
        await client.delete(
            _erase_url(9_999_998), headers=admin_auth_headers
        )
        await client.delete(
            _erase_url(test_customer.id), headers=admin_auth_headers
        )

        not_found_rows = await _all_gdpr_rows(db_session, 9_999_998)
        success_rows = await _all_gdpr_rows(db_session, test_customer.id)

        assert [r.status for r in not_found_rows] == ["FAILED"]
        assert [r.status for r in success_rows] == ["completed"]
