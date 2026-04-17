"""Unit tests for ``FileErasureService``.

Covers:
- Happy path: multi-customer sweep deletes only the target customer's
  files.
- Path-traversal guard: candidate paths that resolve outside
  ``storage_root`` are refused (``files_failed++``) and never touched.
- Missing file: DB reference with no file on disk is counted as
  ``files_missing`` and the DB column is still nulled.
- Permission error: mocked ``os.unlink`` failure is counted as
  ``files_failed`` and the DB reference is kept.
- Dry-run: no disk writes, no DB writes, result populated correctly.
- Idempotency: second run reports 0 deletions + 0 failures.
- Link-kind resolution: ``order_id`` transitive link resolves photos
  through ``orders.customer_id`` correctly.
- Audit: ``customer_audit_logs`` row with counters + per-target
  breakdown is written.
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import (
    AlloyType,
    Customer,
    CustomerAuditLog,
    Order,
    OrderPhoto,
    OrderStatusEnum,
    RepairItemType,
    RepairJob,
    RepairJobStatus,
    RepairPhoto,
    RepairPhotoPhase,
    ScrapGold,
    ScrapGoldItem,
    ScrapGoldStatus,
    User,
    UserRole,
    ValuationCertificate,
)
from goldsmith_erp.services.file_erasure_service import (
    FILE_ERASURE_TARGETS,
    REDACTED_PATH_SENTINEL,
    FileErasureResult,
    FileErasureService,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def admin(db_session: AsyncSession) -> User:
    from goldsmith_erp.core.security import get_password_hash

    user = User(
        email=f"admin_{uuid.uuid4().hex[:8]}@example.com",
        hashed_password=get_password_hash("AdminPass123!"),
        first_name="Test",
        last_name="Admin",
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def customer_a(db_session: AsyncSession) -> Customer:
    c = Customer(
        first_name="Alice",
        last_name="Alpha",
        email=f"alice_{uuid.uuid4().hex[:8]}@example.de",
        customer_type="private",
        is_active=True,
    )
    db_session.add(c)
    await db_session.commit()
    await db_session.refresh(c)
    return c


@pytest_asyncio.fixture
async def customer_b(db_session: AsyncSession) -> Customer:
    c = Customer(
        first_name="Bob",
        last_name="Beta",
        email=f"bob_{uuid.uuid4().hex[:8]}@example.de",
        customer_type="private",
        is_active=True,
    )
    db_session.add(c)
    await db_session.commit()
    await db_session.refresh(c)
    return c


@pytest_asyncio.fixture
async def customer_c(db_session: AsyncSession) -> Customer:
    c = Customer(
        first_name="Carol",
        last_name="Charlie",
        email=f"carol_{uuid.uuid4().hex[:8]}@example.de",
        customer_type="private",
        is_active=True,
    )
    db_session.add(c)
    await db_session.commit()
    await db_session.refresh(c)
    return c


async def _mk_order(db: AsyncSession, customer: Customer) -> Order:
    order = Order(
        title="Ring",
        description="Trauring",
        customer_id=customer.id,
        status=OrderStatusEnum.NEW,
    )
    db.add(order)
    await db.commit()
    await db.refresh(order)
    return order


async def _mk_repair(db: AsyncSession, customer: Customer, admin: User) -> RepairJob:
    repair = RepairJob(
        repair_number=f"REP-{uuid.uuid4().hex[:6]}",
        bag_number="BAG-1",
        customer_id=customer.id,
        received_by=admin.id,
        item_description="Silberkette",
        item_type=RepairItemType.CHAIN,
        status=RepairJobStatus.RECEIVED,
    )
    db.add(repair)
    await db.commit()
    await db.refresh(repair)
    return repair


async def _mk_scrap(db: AsyncSession, customer: Customer, admin: User) -> ScrapGold:
    order = await _mk_order(db, customer)
    scrap = ScrapGold(
        order_id=order.id,
        customer_id=customer.id,
        created_by=admin.id,
        status=ScrapGoldStatus.RECEIVED,
    )
    db.add(scrap)
    await db.commit()
    await db.refresh(scrap)
    return scrap


def _write_file(storage_root: Path, rel_path: str, content: bytes = b"pdf") -> Path:
    """Create a file under ``storage_root`` and return the absolute path."""
    abs_path = storage_root / rel_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_bytes(content)
    return abs_path


# ---------------------------------------------------------------------------
# Core happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    @pytest.mark.asyncio
    async def test_three_customers_two_files_each_only_target_deleted(
        self,
        db_session: AsyncSession,
        customer_a: Customer,
        customer_b: Customer,
        customer_c: Customer,
        admin: User,
        tmp_path: Path,
    ):
        """Three customers with 2 photos each. Erase customer A.

        Only A's photos are deleted on disk AND in the DB column.
        B + C untouched on both fronts.
        """
        service = FileErasureService(tmp_path)

        # One order per customer, two photos per order.
        photos: dict[int, list[OrderPhoto]] = {}
        for customer in (customer_a, customer_b, customer_c):
            order = await _mk_order(db_session, customer)
            cust_photos = []
            for i in range(2):
                rel = f"cust{customer.id}/photo_{i}.jpg"
                _write_file(tmp_path, rel, b"jpeg-bytes")
                photo = OrderPhoto(
                    order_id=order.id,
                    file_path=rel,
                    taken_by=admin.id,
                )
                db_session.add(photo)
                cust_photos.append(photo)
            await db_session.commit()
            for p in cust_photos:
                await db_session.refresh(p)
            photos[customer.id] = cust_photos

        # Erase customer A only.
        result = await service.erase_customer_files(
            db_session, customer_id=customer_a.id, performed_by=admin.id
        )
        await db_session.commit()

        assert result.files_deleted == 2
        assert result.files_failed == 0
        assert result.files_missing == 0
        assert result.files_checked == 2

        # A's files gone; B + C untouched.
        for p in photos[customer_a.id]:
            abs_path = tmp_path / p.file_path if p.file_path else None
            # After erase, DB column is REDACTED_PATH_SENTINEL (NOT NULL col).
            await db_session.refresh(p)
            assert p.file_path == REDACTED_PATH_SENTINEL

        for customer in (customer_b, customer_c):
            for p in photos[customer.id]:
                await db_session.refresh(p)
                abs_path = tmp_path / p.file_path
                assert (
                    abs_path.exists()
                ), f"Customer {customer.id}'s file was wrongly deleted"
                assert p.file_path != REDACTED_PATH_SENTINEL

    @pytest.mark.asyncio
    async def test_nullable_column_set_to_null(
        self,
        db_session: AsyncSession,
        customer_a: Customer,
        admin: User,
        tmp_path: Path,
    ):
        """scrap_gold.receipt_pdf_path is nullable — after erasure it is NULL."""
        service = FileErasureService(tmp_path)
        scrap = await _mk_scrap(db_session, customer_a, admin)
        rel = f"receipts/scrap_{scrap.id}.pdf"
        _write_file(tmp_path, rel, b"pdf")
        scrap.receipt_pdf_path = rel
        await db_session.commit()
        await db_session.refresh(scrap)

        result = await service.erase_customer_files(
            db_session, customer_id=customer_a.id, performed_by=admin.id
        )
        await db_session.commit()
        await db_session.refresh(scrap)

        assert scrap.receipt_pdf_path is None
        assert result.files_deleted >= 1


# ---------------------------------------------------------------------------
# Path-traversal guard
# ---------------------------------------------------------------------------


class TestPathTraversalGuard:
    @pytest.mark.asyncio
    async def test_dotdot_escape_is_refused(
        self,
        db_session: AsyncSession,
        customer_a: Customer,
        admin: User,
        tmp_path: Path,
    ):
        """``../../../etc/passwd`` → files_failed, file NOT deleted, column kept."""
        service = FileErasureService(tmp_path)

        # Place a real file OUTSIDE the storage root to prove we never touch it.
        outside_dir = tmp_path.parent / "outside"
        outside_dir.mkdir(exist_ok=True)
        outside_file = outside_dir / "keepme.txt"
        outside_file.write_bytes(b"do-not-delete")
        assert outside_file.exists()

        order = await _mk_order(db_session, customer_a)
        # Malicious DB value attempting to escape the storage root.
        photo = OrderPhoto(
            order_id=order.id,
            file_path=f"../outside/keepme.txt",
            taken_by=admin.id,
        )
        db_session.add(photo)
        await db_session.commit()
        await db_session.refresh(photo)

        result = await service.erase_customer_files(
            db_session, customer_id=customer_a.id, performed_by=admin.id
        )
        await db_session.commit()
        await db_session.refresh(photo)

        assert result.files_failed >= 1
        assert result.files_deleted == 0

        # The outside file MUST still exist.
        assert outside_file.exists(), (
            "path-traversal guard breach — file outside storage_root " "was deleted"
        )

        # The DB column is KEPT (not replaced with sentinel / NULL) so
        # the admin can inspect.
        assert photo.file_path != REDACTED_PATH_SENTINEL
        assert "outside" in photo.file_path

        # And the error tuple reports the refused path.
        assert any(
            "outside" in path or "escape" in msg.lower() for path, msg in result.errors
        )

    @pytest.mark.asyncio
    async def test_absolute_path_outside_root_is_refused(
        self,
        db_session: AsyncSession,
        customer_a: Customer,
        admin: User,
        tmp_path: Path,
    ):
        """An ABSOLUTE path like /tmp/whatever is refused when outside root."""
        service = FileErasureService(tmp_path)

        # Different tmpdir (guaranteed outside this service's root).
        import tempfile

        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"keep")
            attack_path = f.name
        try:
            order = await _mk_order(db_session, customer_a)
            photo = OrderPhoto(
                order_id=order.id,
                file_path=attack_path,
                taken_by=admin.id,
            )
            db_session.add(photo)
            await db_session.commit()

            result = await service.erase_customer_files(
                db_session, customer_id=customer_a.id, performed_by=admin.id
            )
            await db_session.commit()

            assert result.files_failed >= 1
            assert result.files_deleted == 0
            assert os.path.exists(
                attack_path
            ), "absolute-path escape breach — attack file was deleted"
        finally:
            if os.path.exists(attack_path):
                os.unlink(attack_path)


# ---------------------------------------------------------------------------
# Missing file
# ---------------------------------------------------------------------------


class TestMissingFile:
    @pytest.mark.asyncio
    async def test_db_path_no_disk_file_counts_missing_and_nulls_column(
        self,
        db_session: AsyncSession,
        customer_a: Customer,
        admin: User,
        tmp_path: Path,
    ):
        """DB references a path that was never / no longer on disk."""
        service = FileErasureService(tmp_path)

        order = await _mk_order(db_session, customer_a)
        photo = OrderPhoto(
            order_id=order.id,
            file_path="ghost/does_not_exist.jpg",
            taken_by=admin.id,
        )
        db_session.add(photo)
        await db_session.commit()
        await db_session.refresh(photo)

        result = await service.erase_customer_files(
            db_session, customer_id=customer_a.id, performed_by=admin.id
        )
        await db_session.commit()
        await db_session.refresh(photo)

        assert result.files_missing >= 1
        assert result.files_failed == 0
        # The DB column is still nulled (sentinel for NOT NULL) so the
        # DB converges with filesystem state.
        assert photo.file_path == REDACTED_PATH_SENTINEL


# ---------------------------------------------------------------------------
# Permission error — mocked os.unlink
# ---------------------------------------------------------------------------


class TestPermissionError:
    @pytest.mark.asyncio
    async def test_unlink_raises_permission_error_keeps_db_reference(
        self,
        db_session: AsyncSession,
        customer_a: Customer,
        admin: User,
        tmp_path: Path,
        monkeypatch,
    ):
        """If os.unlink raises PermissionError: files_failed++, row NOT updated."""
        service = FileErasureService(tmp_path)

        order = await _mk_order(db_session, customer_a)
        rel = "protected/file.jpg"
        _write_file(tmp_path, rel, b"jpeg")
        photo = OrderPhoto(
            order_id=order.id,
            file_path=rel,
            taken_by=admin.id,
        )
        db_session.add(photo)
        await db_session.commit()
        await db_session.refresh(photo)

        def _raise(*args, **kwargs):
            raise PermissionError("EACCES: mocked permission denial")

        monkeypatch.setattr(
            "goldsmith_erp.services.file_erasure_service.os.unlink",
            _raise,
        )

        result = await service.erase_customer_files(
            db_session, customer_id=customer_a.id, performed_by=admin.id
        )
        await db_session.commit()
        await db_session.refresh(photo)

        assert result.files_failed >= 1
        assert result.files_deleted == 0
        # DB reference is KEPT so the admin can inspect / retry.
        assert photo.file_path == rel
        assert any("Permission" in msg for _, msg in result.errors)


# ---------------------------------------------------------------------------
# Dry-run
# ---------------------------------------------------------------------------


class TestDryRun:
    @pytest.mark.asyncio
    async def test_dry_run_no_disk_writes_no_db_writes(
        self,
        db_session: AsyncSession,
        customer_a: Customer,
        admin: User,
        tmp_path: Path,
    ):
        """dry_run=True populates counters without touching disk or DB."""
        service = FileErasureService(tmp_path)

        order = await _mk_order(db_session, customer_a)
        rel = "preview/file.jpg"
        _write_file(tmp_path, rel, b"jpeg")
        photo = OrderPhoto(
            order_id=order.id,
            file_path=rel,
            taken_by=admin.id,
        )
        db_session.add(photo)
        await db_session.commit()
        await db_session.refresh(photo)

        result = await service.erase_customer_files(
            db_session,
            customer_id=customer_a.id,
            performed_by=admin.id,
            dry_run=True,
        )
        await db_session.commit()
        await db_session.refresh(photo)

        assert result.dry_run is True
        # Would-have-been-deleted count populated.
        assert result.files_deleted == 1
        # File still on disk.
        assert (tmp_path / rel).exists()
        # DB column unchanged.
        assert photo.file_path == rel
        # No audit row written in dry-run.
        audit = await db_session.execute(
            select(CustomerAuditLog).filter(
                CustomerAuditLog.customer_id == customer_a.id,
                CustomerAuditLog.action == "gdpr_file_erasure",
            )
        )
        assert audit.scalar_one_or_none() is None


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


class TestIdempotency:
    @pytest.mark.asyncio
    async def test_second_run_is_noop(
        self,
        db_session: AsyncSession,
        customer_a: Customer,
        admin: User,
        tmp_path: Path,
    ):
        """Second erasure on an already-swept customer returns zero counts."""
        service = FileErasureService(tmp_path)
        order = await _mk_order(db_session, customer_a)
        rel = "once/file.jpg"
        _write_file(tmp_path, rel, b"jpeg")
        photo = OrderPhoto(
            order_id=order.id,
            file_path=rel,
            taken_by=admin.id,
        )
        db_session.add(photo)
        await db_session.commit()

        first = await service.erase_customer_files(
            db_session, customer_id=customer_a.id, performed_by=admin.id
        )
        await db_session.commit()

        second = await service.erase_customer_files(
            db_session, customer_id=customer_a.id, performed_by=admin.id
        )
        await db_session.commit()

        assert first.files_deleted == 1
        # Second run finds the sentinel on the NOT NULL column and
        # short-circuits without checking / deleting anything.
        assert second.files_checked == 0
        assert second.files_deleted == 0
        assert second.files_failed == 0


# ---------------------------------------------------------------------------
# Link-kind resolution — order_id + repair_job_id + scrap_gold_id + customer_id
# ---------------------------------------------------------------------------


class TestLinkResolution:
    @pytest.mark.asyncio
    async def test_order_id_link_resolves_photos_through_orders(
        self,
        db_session: AsyncSession,
        customer_a: Customer,
        customer_b: Customer,
        admin: User,
        tmp_path: Path,
    ):
        """order_photos → order_id → orders.customer_id transitive link."""
        service = FileErasureService(tmp_path)

        # A and B each have an order with a photo.
        for cust, label in ((customer_a, "a"), (customer_b, "b")):
            order = await _mk_order(db_session, cust)
            rel = f"{label}/file.jpg"
            _write_file(tmp_path, rel, b"jpeg")
            photo = OrderPhoto(
                order_id=order.id,
                file_path=rel,
                taken_by=admin.id,
            )
            db_session.add(photo)
        await db_session.commit()

        result = await service.erase_customer_files(
            db_session, customer_id=customer_a.id, performed_by=admin.id
        )
        await db_session.commit()

        # Exactly 1 file deleted (A's). B's photo untouched.
        assert result.files_deleted == 1
        assert (tmp_path / "b/file.jpg").exists()
        assert not (tmp_path / "a/file.jpg").exists()

    @pytest.mark.asyncio
    async def test_repair_job_id_link_resolves_repair_photos(
        self,
        db_session: AsyncSession,
        customer_a: Customer,
        admin: User,
        tmp_path: Path,
    ):
        """repair_photos → repair_job_id → repair_jobs.customer_id."""
        service = FileErasureService(tmp_path)
        repair = await _mk_repair(db_session, customer_a, admin)
        rel = "repair/photo.jpg"
        _write_file(tmp_path, rel, b"jpeg")
        rp = RepairPhoto(
            repair_job_id=repair.id,
            phase=RepairPhotoPhase.INTAKE,
            file_path=rel,
            taken_by=admin.id,
        )
        db_session.add(rp)
        await db_session.commit()
        await db_session.refresh(rp)

        result = await service.erase_customer_files(
            db_session, customer_id=customer_a.id, performed_by=admin.id
        )
        await db_session.commit()
        await db_session.refresh(rp)

        assert result.files_deleted == 1
        assert rp.file_path == REDACTED_PATH_SENTINEL

    @pytest.mark.asyncio
    async def test_scrap_gold_id_link_resolves_scrap_items(
        self,
        db_session: AsyncSession,
        customer_a: Customer,
        admin: User,
        tmp_path: Path,
    ):
        """scrap_gold_items → scrap_gold_id → scrap_gold.customer_id."""
        service = FileErasureService(tmp_path)
        scrap = await _mk_scrap(db_session, customer_a, admin)
        rel = "items/gold.jpg"
        _write_file(tmp_path, rel, b"jpeg")
        item = ScrapGoldItem(
            scrap_gold_id=scrap.id,
            description="Ring",
            alloy=AlloyType.GOLD_585,
            weight_g=5.0,
            fine_content_g=2.925,
            photo_path=rel,
        )
        db_session.add(item)
        await db_session.commit()
        await db_session.refresh(item)

        result = await service.erase_customer_files(
            db_session, customer_id=customer_a.id, performed_by=admin.id
        )
        await db_session.commit()
        await db_session.refresh(item)

        assert result.files_deleted == 1
        # photo_path is nullable → NULL after erase.
        assert item.photo_path is None


# ---------------------------------------------------------------------------
# Audit — CustomerAuditLog written per sweep
# ---------------------------------------------------------------------------


class TestAudit:
    @pytest.mark.asyncio
    async def test_audit_row_written_on_real_run(
        self,
        db_session: AsyncSession,
        customer_a: Customer,
        admin: User,
        tmp_path: Path,
    ):
        """One CustomerAuditLog row per sweep, with per-target counters."""
        service = FileErasureService(tmp_path)
        order = await _mk_order(db_session, customer_a)
        rel = "a/one.jpg"
        _write_file(tmp_path, rel, b"jpeg")
        photo = OrderPhoto(
            order_id=order.id,
            file_path=rel,
            taken_by=admin.id,
        )
        db_session.add(photo)
        await db_session.commit()

        await service.erase_customer_files(
            db_session, customer_id=customer_a.id, performed_by=admin.id
        )
        await db_session.commit()

        result = await db_session.execute(
            select(CustomerAuditLog).filter(
                CustomerAuditLog.customer_id == customer_a.id,
                CustomerAuditLog.action == "gdpr_file_erasure",
            )
        )
        log = result.scalar_one()
        assert log.user_id == admin.id
        assert log.entity == "customer"
        # Details carry the aggregated counters + per-target breakdown.
        assert log.details["files_deleted"] >= 1
        assert "order_photos.file_path" in log.details["per_target_counts"]

    @pytest.mark.asyncio
    async def test_path_traversal_error_recorded_in_errors_list(
        self,
        db_session: AsyncSession,
        customer_a: Customer,
        admin: User,
        tmp_path: Path,
    ):
        """Path-traversal refusals appear in result.errors for caller visibility."""
        service = FileErasureService(tmp_path)
        order = await _mk_order(db_session, customer_a)
        photo = OrderPhoto(
            order_id=order.id,
            file_path="../escape.jpg",
            taken_by=admin.id,
        )
        db_session.add(photo)
        await db_session.commit()

        result = await service.erase_customer_files(
            db_session, customer_id=customer_a.id, performed_by=admin.id
        )
        await db_session.commit()

        assert len(result.errors) >= 1
        assert result.files_failed >= 1
