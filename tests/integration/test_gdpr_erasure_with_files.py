"""Integration tests for /customers/{id}/gdpr-erase + FileErasureService.

End-to-end through the HTTP endpoint:
  - Setup: customer + order + valuation PDF (real file on disk under
    a tmp_path-rooted storage root).
  - DELETE /customers/{id}/gdpr-erase.
  - Assert: HTTP 200, response body carries files_deleted >= 1, file
    is gone from disk, DB path column is NULL.
  - Partial-failure variant: mocked permission-denied on one file,
    assert HTTP 207 and ``partial=True`` in the response body.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import (
    Customer,
    Order,
    OrderPhoto,
    OrderStatusEnum,
    ValuationCertificate,
)


# ---------------------------------------------------------------------------
# Fixtures — bind a tmp_path to FILE_STORAGE_ROOT for each test
# ---------------------------------------------------------------------------


@pytest.fixture
def storage_root(tmp_path, monkeypatch) -> Path:
    """Per-test isolated storage root for FileErasureService.

    The endpoint builds the service from ``settings.FILE_STORAGE_ROOT``;
    patching the attribute keeps every test independent.
    """
    monkeypatch.setattr(
        "goldsmith_erp.core.config.settings.FILE_STORAGE_ROOT",
        str(tmp_path),
    )
    return tmp_path


async def _mk_order(db: AsyncSession, customer_id: int) -> Order:
    order = Order(
        title="Trauringe",
        description="750er Gelbgold",
        customer_id=customer_id,
        status=OrderStatusEnum.NEW,
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)
    return order


async def _mk_valuation(
    db: AsyncSession,
    *,
    order: Order,
    customer_id: int,
    created_by: int,
    pdf_path: str,
) -> ValuationCertificate:
    cert = ValuationCertificate(
        certificate_number=f"WG-{uuid.uuid4().hex[:6]}",
        order_id=order.id,
        customer_id=customer_id,
        created_by=created_by,
        item_description="Ring",
        appraised_value=1000.0,
        valuation_date=datetime.utcnow(),
        valid_until=datetime.utcnow() + timedelta(days=730),
        goldsmith_name="Test Goldsmith",
        pdf_path=pdf_path,
    )
    db.add(cert)
    await db.commit()
    await db.refresh(cert)
    return cert


# ---------------------------------------------------------------------------
# Happy path — 200 OK, file deleted, DB nulled
# ---------------------------------------------------------------------------


class TestGdprEraseDeletesFiles:
    @pytest.mark.asyncio
    async def test_endpoint_deletes_valuation_pdf_and_returns_200(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_customer: Customer,
        admin_user,
        admin_auth_headers: dict,
        storage_root: Path,
    ):
        order = await _mk_order(db_session, test_customer.id)
        rel_path = f"certificates/{uuid.uuid4().hex}.pdf"
        abs_path = storage_root / rel_path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_bytes(b"%PDF-1.4 fake")
        cert = await _mk_valuation(
            db_session,
            order=order,
            customer_id=test_customer.id,
            created_by=admin_user.id,
            pdf_path=rel_path,
        )
        assert abs_path.exists()

        response = await client.delete(
            f"/api/v1/customers/{test_customer.id}/gdpr-erase",
            headers=admin_auth_headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["customer_id"] == test_customer.id
        assert body["partial"] is False
        assert body["file_erasure"]["files_deleted"] >= 1
        assert body["file_erasure"]["files_failed"] == 0

        # File gone from disk.
        assert not abs_path.exists(), "valuation PDF was not deleted"

        # DB pdf_path nulled.
        refreshed = await db_session.execute(
            select(ValuationCertificate).filter(ValuationCertificate.id == cert.id)
        )
        cert_after = refreshed.scalar_one()
        assert cert_after.pdf_path is None

    @pytest.mark.asyncio
    async def test_endpoint_is_207_on_partial_file_failure(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_customer: Customer,
        admin_user,
        admin_auth_headers: dict,
        storage_root: Path,
        monkeypatch,
    ):
        """Mock os.unlink to raise → endpoint returns 207 Multi-Status."""
        order = await _mk_order(db_session, test_customer.id)
        rel_path = f"photos/{uuid.uuid4().hex}.jpg"
        abs_path = storage_root / rel_path
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        abs_path.write_bytes(b"jpeg-bytes")
        photo = OrderPhoto(
            order_id=order.id,
            file_path=rel_path,
            taken_by=admin_user.id,
        )
        db_session.add(photo)
        await db_session.commit()
        await db_session.refresh(photo)

        def _raise(*args, **kwargs):
            raise PermissionError("EACCES: mocked")

        monkeypatch.setattr(
            "goldsmith_erp.services.file_erasure_service.os.unlink",
            _raise,
        )

        response = await client.delete(
            f"/api/v1/customers/{test_customer.id}/gdpr-erase",
            headers=admin_auth_headers,
        )

        assert response.status_code == 207
        body = response.json()
        assert body["partial"] is True
        assert body["file_erasure"]["files_failed"] >= 1
        assert body["file_erasure"]["files_deleted"] == 0
        # Errors list carries the failing path for admin follow-up.
        assert any(
            "Permission" in err["message"] for err in body["file_erasure"]["errors"]
        )

        # File is STILL on disk — PermissionError mock kept it.
        assert abs_path.exists()

        # DB reference preserved so the admin can inspect.
        refreshed = await db_session.execute(
            select(OrderPhoto).filter(OrderPhoto.id == photo.id)
        )
        photo_after = refreshed.scalar_one()
        assert photo_after.file_path == rel_path

    @pytest.mark.asyncio
    async def test_endpoint_records_partial_status_in_gdpr_requests(
        self,
        client: AsyncClient,
        db_session: AsyncSession,
        test_customer: Customer,
        admin_user,
        admin_auth_headers: dict,
        storage_root: Path,
        monkeypatch,
    ):
        """On partial failure, the gdpr_requests row status = 'PARTIAL_FILE_ERASURE'."""
        from goldsmith_erp.db.models import GDPRRequest

        order = await _mk_order(db_session, test_customer.id)
        rel_path = f"photos/{uuid.uuid4().hex}.jpg"
        abs_path = storage_root / rel_path
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
            f"/api/v1/customers/{test_customer.id}/gdpr-erase",
            headers=admin_auth_headers,
        )
        assert response.status_code == 207

        gdpr_row = await db_session.execute(
            select(GDPRRequest).filter(GDPRRequest.customer_id == test_customer.id)
        )
        gdpr = gdpr_row.scalar_one()
        assert gdpr.status == "PARTIAL_FILE_ERASURE"
        assert "File-erasure partial failure" in (gdpr.notes or "")
