"""GDPR erasure cascade for the consultation module (Task 10).

Extends the existing Art. 17 machinery covered by
``tests/unit/test_gdpr_customer_erasure.py`` (``CustomerService.scrub_customer_pii``)
and ``tests/unit/test_file_erasure.py`` (``FileErasureService``) to the
consultation tables added in V1.1:

- ``consultations.wishes`` / ``notes`` / ``source_material`` → PII-token
  scrubbed via ``SCRUBBABLE_FIELDS`` (same mechanism as ``repair_jobs``).
- ``consultations.budget_min`` / ``budget_max`` → NULLed explicitly (financial
  data of the erased person; doesn't fit the string-scrub ScrubTarget shape).
- ``customer_no_gos`` rows → hard-deleted (pure preference data, no Art. 30
  retention duty).
- ``consultation_photos`` → file + thumbnail deleted from disk, row deleted,
  via ``FileErasureService``'s parent-id collection pattern.
- The ``consultations`` row itself survives (anonymised) for Art. 30 records,
  matching the ``RepairJob`` precedent.
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import (
    Consultation,
    ConsultationPhotoKind,
    Customer,
    CustomerNoGo,
    User,
    UserRole,
)
from goldsmith_erp.models.consultation import ConsultationCreate, NoGoCreate
from goldsmith_erp.services.consultation_photo_service import ConsultationPhotoService
from goldsmith_erp.services.consultation_service import ConsultationService
from goldsmith_erp.services.customer_service import REDACTION_TOKEN, CustomerService
from goldsmith_erp.services.file_erasure_service import FileErasureService
from goldsmith_erp.services.no_go_service import NoGoService

# ---------------------------------------------------------------------------
# Fixtures — mirrors tests/unit/test_gdpr_customer_erasure.py's mueller_maria
# / admin fixtures so the customer's name is a real PII token the scrubber
# can match inside the consultation free-text fields.
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def mueller_maria(db_session: AsyncSession) -> Customer:
    customer = Customer(
        first_name="Maria",
        last_name="Mueller",
        email=f"maria.mueller_{uuid.uuid4().hex[:8]}@example.de",
        phone="+49 89 1234567",
        mobile=None,
        customer_type="private",
        is_active=True,
    )
    db_session.add(customer)
    await db_session.commit()
    await db_session.refresh(customer)
    return customer


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


def _jpeg_upload(name: str = "sketch.jpg"):
    """A minimal valid 4x4 white JPEG, Pillow-generated in-memory."""
    import io

    from fastapi import UploadFile
    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", (4, 4), "white").save(buf, format="JPEG")
    buf.seek(0)
    return UploadFile(filename=name, file=buf)


# ---------------------------------------------------------------------------
# CustomerService.scrub_customer_pii — free-text + budget + no-gos
# ---------------------------------------------------------------------------


class TestScrubConsultationPii:
    @pytest.mark.asyncio
    async def test_erasure_scrubs_wishes_notes_source_material(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        admin: User,
    ):
        consultation = await ConsultationService.create_consultation(
            db_session,
            ConsultationCreate(
                customer_id=mueller_maria.id,
                wishes="Rotgold-Ring fuer Maria Mueller",
                notes="Privater Wunsch von Maria Mueller",
                source_material="Erbstueck von Maria Mueller",
                budget_min=500.0,
                budget_max=900.0,
            ),
            conducted_by_user_id=admin.id,
        )

        counts = await CustomerService.scrub_customer_pii(
            db_session,
            customer_id=mueller_maria.id,
            performed_by=admin.id,
        )
        await db_session.commit()

        row = (
            await db_session.execute(select(Consultation).filter_by(id=consultation.id))
        ).scalar_one()

        assert row.wishes == f"Rotgold-Ring fuer {REDACTION_TOKEN} {REDACTION_TOKEN}"
        assert row.notes == f"Privater Wunsch von {REDACTION_TOKEN} {REDACTION_TOKEN}"
        assert (
            row.source_material == f"Erbstueck von {REDACTION_TOKEN} {REDACTION_TOKEN}"
        )
        assert counts["consultations.wishes"] == 2
        assert counts["consultations.notes"] == 2
        assert counts["consultations.source_material"] == 2

    @pytest.mark.asyncio
    async def test_erasure_nulls_budget_fields(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        admin: User,
    ):
        consultation = await ConsultationService.create_consultation(
            db_session,
            ConsultationCreate(
                customer_id=mueller_maria.id,
                budget_min=500.0,
                budget_max=900.0,
            ),
            conducted_by_user_id=admin.id,
        )

        counts = await CustomerService.scrub_customer_pii(
            db_session,
            customer_id=mueller_maria.id,
            performed_by=admin.id,
        )
        await db_session.commit()

        row = (
            await db_session.execute(select(Consultation).filter_by(id=consultation.id))
        ).scalar_one()
        assert row.budget_min is None
        assert row.budget_max is None
        # Audit counter reflects the one row whose budget was NULLed.
        assert counts["consultations.budget"] == 1

    @pytest.mark.asyncio
    async def test_erasure_nulls_materials_discussed_and_occasion_date(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        admin: User,
    ):
        """Final-review fix (Fix 3): materials_discussed (preference data —
        which metals/stones were discussed) and occasion_date (personal
        data — e.g. an anniversary or birthday date) are erasure surfaces
        added on this branch that weren't wired into scrub_customer_pii.
        """
        from datetime import date

        consultation = await ConsultationService.create_consultation(
            db_session,
            ConsultationCreate(
                customer_id=mueller_maria.id,
                occasion_date=date(2026, 6, 1),
                materials_discussed=[{"metal": "gold_585"}],
            ),
            conducted_by_user_id=admin.id,
        )

        counts = await CustomerService.scrub_customer_pii(
            db_session,
            customer_id=mueller_maria.id,
            performed_by=admin.id,
        )
        await db_session.commit()

        row = (
            await db_session.execute(select(Consultation).filter_by(id=consultation.id))
        ).scalar_one()
        assert row.materials_discussed is None
        assert row.occasion_date is None
        assert counts["consultations.materials_discussed"] == 1
        assert counts["consultations.occasion_date"] == 1

    @pytest.mark.asyncio
    async def test_erasure_nulls_customer_style_profile(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        admin: User,
    ):
        """Final-review fix (Fix 3): style_profile is preference data on the
        customer row itself (same rationale as the no-go hard-delete) and
        must be NULLed on erasure.
        """
        mueller_maria.style_profile = {"metal_tones": ["rose"]}
        db_session.add(mueller_maria)
        await db_session.commit()

        counts = await CustomerService.scrub_customer_pii(
            db_session,
            customer_id=mueller_maria.id,
            performed_by=admin.id,
        )
        await db_session.commit()

        row = (
            await db_session.execute(select(Customer).filter_by(id=mueller_maria.id))
        ).scalar_one()
        assert row.style_profile is None
        assert counts["customers.style_profile"] == 1

    @pytest.mark.asyncio
    async def test_erasure_hard_deletes_no_gos(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        admin: User,
    ):
        await NoGoService.add_no_go(
            db_session,
            mueller_maria.id,
            NoGoCreate(category="allergy", value="Nickel"),
        )
        await db_session.commit()

        counts = await CustomerService.scrub_customer_pii(
            db_session,
            customer_id=mueller_maria.id,
            performed_by=admin.id,
        )
        await db_session.commit()

        no_gos = (
            (
                await db_session.execute(
                    select(CustomerNoGo).filter_by(customer_id=mueller_maria.id)
                )
            )
            .scalars()
            .all()
        )
        assert no_gos == []
        # Audit counter reflects the one hard-deleted preference row.
        assert counts["customer_no_gos.deleted"] == 1

    @pytest.mark.asyncio
    async def test_consultation_row_survives_erasure(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        admin: User,
    ):
        """Art. 30 retention: the consultation row itself is not deleted."""
        consultation = await ConsultationService.create_consultation(
            db_session,
            ConsultationCreate(customer_id=mueller_maria.id, wishes="Ring"),
            conducted_by_user_id=admin.id,
        )

        await CustomerService.scrub_customer_pii(
            db_session,
            customer_id=mueller_maria.id,
            performed_by=admin.id,
        )
        await db_session.commit()

        row = (
            await db_session.execute(select(Consultation).filter_by(id=consultation.id))
        ).scalar_one_or_none()
        assert row is not None


# ---------------------------------------------------------------------------
# FileErasureService — consultation photo files + thumbnails + rows
# ---------------------------------------------------------------------------


class TestErasureConsultationPhotos:
    @pytest.mark.asyncio
    async def test_erasure_deletes_photo_file_thumb_and_row(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        admin: User,
        tmp_path: Path,
        monkeypatch,
    ):
        monkeypatch.setattr(
            "goldsmith_erp.core.config.settings.PHOTO_STORAGE_PATH", str(tmp_path)
        )

        consultation = await ConsultationService.create_consultation(
            db_session,
            ConsultationCreate(customer_id=mueller_maria.id, wishes="Anhaenger"),
            conducted_by_user_id=admin.id,
        )
        photo = await ConsultationPhotoService.upload_photo(
            db_session,
            consultation_id=consultation.id,
            file=_jpeg_upload(),
            user_id=admin.id,
            kind=ConsultationPhotoKind.SKETCH,
        )
        await db_session.commit()

        original_path = Path(photo.file_path)
        thumb_path = original_path.parent / "thumbs" / f"{original_path.stem}.jpg"
        assert original_path.exists()
        assert thumb_path.exists()

        service = FileErasureService(tmp_path)
        result = await service.erase_customer_files(
            db_session,
            customer_id=mueller_maria.id,
            performed_by=admin.id,
        )
        await db_session.commit()

        assert not original_path.exists()
        assert not thumb_path.exists()
        assert result.per_target_counts["consultation_photos.file_path"]["deleted"] == 1

        remaining = await ConsultationPhotoService.list_photos(
            db_session, consultation.id
        )
        assert remaining == []

    @pytest.mark.asyncio
    async def test_erasure_does_not_touch_other_customers_photos(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        admin: User,
        tmp_path: Path,
        monkeypatch,
    ):
        monkeypatch.setattr(
            "goldsmith_erp.core.config.settings.PHOTO_STORAGE_PATH", str(tmp_path)
        )

        other = Customer(
            first_name="Other",
            last_name="Person",
            email=f"other_{uuid.uuid4().hex[:8]}@example.de",
            customer_type="private",
            is_active=True,
        )
        db_session.add(other)
        await db_session.commit()
        await db_session.refresh(other)

        other_consultation = await ConsultationService.create_consultation(
            db_session,
            ConsultationCreate(customer_id=other.id),
            conducted_by_user_id=admin.id,
        )
        other_photo = await ConsultationPhotoService.upload_photo(
            db_session,
            consultation_id=other_consultation.id,
            file=_jpeg_upload(),
            user_id=admin.id,
            kind=ConsultationPhotoKind.SKETCH,
        )
        await db_session.commit()

        consultation = await ConsultationService.create_consultation(
            db_session,
            ConsultationCreate(customer_id=mueller_maria.id),
            conducted_by_user_id=admin.id,
        )
        await ConsultationPhotoService.upload_photo(
            db_session,
            consultation_id=consultation.id,
            file=_jpeg_upload(),
            user_id=admin.id,
            kind=ConsultationPhotoKind.SKETCH,
        )
        await db_session.commit()

        service = FileErasureService(tmp_path)
        await service.erase_customer_files(
            db_session,
            customer_id=mueller_maria.id,
            performed_by=admin.id,
        )
        await db_session.commit()

        assert Path(other_photo.file_path).exists()
        other_remaining = await ConsultationPhotoService.list_photos(
            db_session, other_consultation.id
        )
        assert len(other_remaining) == 1

    @pytest.mark.asyncio
    async def test_failed_thumb_unlink_counts_failure_and_keeps_row(
        self,
        db_session: AsyncSession,
        mueller_maria: Customer,
        admin: User,
        tmp_path: Path,
        monkeypatch,
    ):
        """Regression: a failed unlink of an EXISTING thumbnail must count
        as ``files_failed`` (→ 207 / PARTIAL_FILE_ERASURE upstream) and
        KEEP the row for admin retry — the sweep must never report
        "all files erased cleanly" while design-IP remains on disk.

        Implementation choice under test: the original is attempted FIRST
        and is deleted; the thumb failure then keeps the row and surfaces
        in ``errors``, so a re-run retries the thumb (original counts as
        missing).
        """
        monkeypatch.setattr(
            "goldsmith_erp.core.config.settings.PHOTO_STORAGE_PATH", str(tmp_path)
        )

        consultation = await ConsultationService.create_consultation(
            db_session,
            ConsultationCreate(customer_id=mueller_maria.id),
            conducted_by_user_id=admin.id,
        )
        photo = await ConsultationPhotoService.upload_photo(
            db_session,
            consultation_id=consultation.id,
            file=_jpeg_upload(),
            user_id=admin.id,
            kind=ConsultationPhotoKind.SKETCH,
        )
        await db_session.commit()

        original_path = Path(photo.file_path)
        thumb_path = original_path.parent / "thumbs" / f"{original_path.stem}.jpg"
        assert original_path.exists()
        assert thumb_path.exists()

        import os as real_os

        real_unlink = real_os.unlink

        def _unlink_fails_on_thumbs(path, *args, **kwargs):
            if "thumbs" in str(path):
                raise PermissionError("EACCES: mocked thumb permission denial")
            return real_unlink(path, *args, **kwargs)

        monkeypatch.setattr(
            "goldsmith_erp.services.file_erasure_service.os.unlink",
            _unlink_fails_on_thumbs,
        )

        service = FileErasureService(tmp_path)
        result = await service.erase_customer_files(
            db_session,
            customer_id=mueller_maria.id,
            performed_by=admin.id,
        )
        await db_session.commit()

        # Failure is surfaced, not swallowed.
        assert result.files_failed >= 1
        assert any("thumbs" in path for path, _ in result.errors)
        assert result.per_target_counts["consultation_photos.file_path"]["failed"] == 1

        # Original was attempted first and deleted; thumb remains on disk.
        assert not original_path.exists()
        assert thumb_path.exists()

        # Row is KEPT so the admin can inspect / retry.
        remaining = await ConsultationPhotoService.list_photos(
            db_session, consultation.id
        )
        assert len(remaining) == 1

        # Retry after the permission problem is fixed: sweep converges —
        # thumb deleted, row removed, no failures.
        monkeypatch.setattr(
            "goldsmith_erp.services.file_erasure_service.os.unlink",
            real_unlink,
        )
        retry = await service.erase_customer_files(
            db_session,
            customer_id=mueller_maria.id,
            performed_by=admin.id,
        )
        await db_session.commit()

        assert retry.files_failed == 0
        assert not thumb_path.exists()
        remaining_after_retry = await ConsultationPhotoService.list_photos(
            db_session, consultation.id
        )
        assert remaining_after_retry == []
