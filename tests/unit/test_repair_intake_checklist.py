"""Unit tests for the V1.1 repair intake checklist (Task 2).

Covers three layers:
  - Settings-seeded checklist on RepairJob creation (RepairService.create_repair),
    incl. slug stability across repeated creates.
  - RepairService.update_intake_checklist's photo-linkage validation
    (cross-repair rejection, wrong-phase rejection, valid roundtrip).
  - IntakeChecklistItem schema validation (na/photo/open status consistency).
"""

import io

import pytest
from fastapi import UploadFile
from PIL import Image
from pydantic import ValidationError

from goldsmith_erp.core.config import settings
from goldsmith_erp.db.models import RepairItemType, RepairPhotoPhase
from goldsmith_erp.models.repair import (
    IntakeChecklistItem,
    IntakeChecklistUpdate,
    RepairJobCreate,
)
from goldsmith_erp.services.repair_photo_service import RepairPhotoService
from goldsmith_erp.services.repair_service import (
    InvalidChecklistPhotoError,
    RepairService,
)


def _jpeg_upload(name: str = "intake.jpg") -> UploadFile:
    """A minimal valid 4x4 white JPEG, Pillow-generated in-memory."""
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), "white").save(buf, format="JPEG")
    buf.seek(0)
    return UploadFile(filename=name, file=buf)


def _create_payload() -> RepairJobCreate:
    return RepairJobCreate(
        item_description="Ehering Gelbgold 585",
        item_type=RepairItemType.RING,
    )


def _expected_seed_keys() -> list:
    """Expected slugs for the default REPAIR_INTAKE_CHECKLIST labels —
    umlauts/ß transliterated, accents stripped, non-alnum collapsed to '-'."""
    return [
        "krappen-fassungen",
        "pave-besatz",
        "gravuren",
        "punzen-stempel",
        "vorhandene-tragespuren-und-schaeden",
    ]


# ===========================================================================
# Seeding on create
# ===========================================================================


class TestIntakeChecklistSeeding:
    @pytest.mark.asyncio
    async def test_create_repair_seeds_checklist_from_settings(
        self, db_session, sample_user
    ):
        repair = await RepairService.create_repair(
            db_session, _create_payload(), sample_user.id
        )

        assert repair.intake_checklist is not None
        assert len(repair.intake_checklist) == len(settings.REPAIR_INTAKE_CHECKLIST)

        for item, label in zip(
            repair.intake_checklist, settings.REPAIR_INTAKE_CHECKLIST
        ):
            assert item["label"] == label
            assert item["status"] == "open"
            assert item["photo_id"] is None
            assert item["na_reason"] is None

    @pytest.mark.asyncio
    async def test_seed_keys_are_slugified_and_stable(self, db_session, sample_user):
        """Keys are deterministic slugs of the configured labels — re-seeding
        (a second repair created with the same settings) produces identical
        keys, not random or timestamp-derived ones."""
        repair_a = await RepairService.create_repair(
            db_session, _create_payload(), sample_user.id
        )
        repair_b = await RepairService.create_repair(
            db_session, _create_payload(), sample_user.id
        )

        keys_a = [item["key"] for item in repair_a.intake_checklist]
        keys_b = [item["key"] for item in repair_b.intake_checklist]

        assert keys_a == keys_b == _expected_seed_keys()


# ===========================================================================
# RepairService.update_intake_checklist — photo linkage validation
# ===========================================================================


class TestUpdateIntakeChecklist:
    @pytest.mark.asyncio
    async def test_unknown_repair_raises_plain_value_error(self, db_session):
        with pytest.raises(ValueError) as exc_info:
            await RepairService.update_intake_checklist(db_session, 999999, [])
        assert not isinstance(exc_info.value, InvalidChecklistPhotoError)

    @pytest.mark.asyncio
    async def test_photo_from_other_repair_is_rejected(
        self, db_session, tmp_path, monkeypatch, sample_user
    ):
        monkeypatch.setattr(
            "goldsmith_erp.core.config.settings.PHOTO_STORAGE_PATH", str(tmp_path)
        )
        repair_a = await RepairService.create_repair(
            db_session, _create_payload(), sample_user.id
        )
        repair_b = await RepairService.create_repair(
            db_session, _create_payload(), sample_user.id
        )

        photo = await RepairPhotoService.upload_photo(
            db_session,
            repair_id=repair_a.id,
            file=_jpeg_upload(),
            user_id=sample_user.id,
            phase=RepairPhotoPhase.INTAKE,
        )
        await db_session.commit()

        items = [
            IntakeChecklistItem(
                key="krappen-fassungen",
                label="Krappen/Fassungen",
                status="photo",
                photo_id=photo.id,
            )
        ]

        with pytest.raises(InvalidChecklistPhotoError) as exc_info:
            await RepairService.update_intake_checklist(db_session, repair_b.id, items)

        assert photo.id in exc_info.value.invalid_photo_ids
        # IDs-only message — item label/reason text never embedded (they
        # are user free-text and must not leak into logs/response bodies).
        assert "Krappen" not in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_wrong_phase_photo_is_rejected(
        self, db_session, tmp_path, monkeypatch, sample_user
    ):
        monkeypatch.setattr(
            "goldsmith_erp.core.config.settings.PHOTO_STORAGE_PATH", str(tmp_path)
        )
        repair = await RepairService.create_repair(
            db_session, _create_payload(), sample_user.id
        )

        photo = await RepairPhotoService.upload_photo(
            db_session,
            repair_id=repair.id,
            file=_jpeg_upload(),
            user_id=sample_user.id,
            phase=RepairPhotoPhase.DURING_REPAIR,
        )
        await db_session.commit()

        items = [
            IntakeChecklistItem(
                key="gravuren", label="Gravuren", status="photo", photo_id=photo.id
            )
        ]

        with pytest.raises(InvalidChecklistPhotoError) as exc_info:
            await RepairService.update_intake_checklist(db_session, repair.id, items)
        assert photo.id in exc_info.value.invalid_photo_ids

    @pytest.mark.asyncio
    async def test_valid_intake_photo_and_na_item_persist(
        self, db_session, tmp_path, monkeypatch, sample_user
    ):
        monkeypatch.setattr(
            "goldsmith_erp.core.config.settings.PHOTO_STORAGE_PATH", str(tmp_path)
        )
        repair = await RepairService.create_repair(
            db_session, _create_payload(), sample_user.id
        )

        photo = await RepairPhotoService.upload_photo(
            db_session,
            repair_id=repair.id,
            file=_jpeg_upload(),
            user_id=sample_user.id,
            phase=RepairPhotoPhase.INTAKE,
        )
        await db_session.commit()

        items = [
            IntakeChecklistItem(
                key="gravuren", label="Gravuren", status="photo", photo_id=photo.id
            ),
            IntakeChecklistItem(
                key="punzen-stempel",
                label="Punzen/Stempel",
                status="na",
                na_reason="Kein Punzen vorhanden",
            ),
        ]

        updated = await RepairService.update_intake_checklist(
            db_session, repair.id, items
        )

        assert len(updated.intake_checklist) == 2
        assert updated.intake_checklist[0]["status"] == "photo"
        assert updated.intake_checklist[0]["photo_id"] == photo.id
        assert updated.intake_checklist[1]["status"] == "na"
        assert updated.intake_checklist[1]["na_reason"] == "Kein Punzen vorhanden"


# ===========================================================================
# IntakeChecklistItem / IntakeChecklistUpdate schema validation
# ===========================================================================


class TestIntakeChecklistItemSchema:
    def test_na_without_reason_is_rejected(self):
        with pytest.raises(ValidationError):
            IntakeChecklistItem(key="k", label="L", status="na")

    def test_na_with_too_short_reason_is_rejected(self):
        with pytest.raises(ValidationError):
            IntakeChecklistItem(key="k", label="L", status="na", na_reason="ab")

    def test_na_with_whitespace_only_reason_is_rejected(self):
        with pytest.raises(ValidationError):
            IntakeChecklistItem(key="k", label="L", status="na", na_reason="   ")

    def test_na_with_photo_id_is_rejected(self):
        with pytest.raises(ValidationError):
            IntakeChecklistItem(
                key="k", label="L", status="na", na_reason="Kein Stein", photo_id=1
            )

    def test_open_with_photo_id_is_rejected(self):
        with pytest.raises(ValidationError):
            IntakeChecklistItem(key="k", label="L", status="open", photo_id=5)

    def test_open_with_na_reason_is_rejected(self):
        with pytest.raises(ValidationError):
            IntakeChecklistItem(key="k", label="L", status="open", na_reason="x")

    def test_photo_without_photo_id_is_rejected(self):
        with pytest.raises(ValidationError):
            IntakeChecklistItem(key="k", label="L", status="photo")

    def test_photo_with_na_reason_is_rejected(self):
        with pytest.raises(ValidationError):
            IntakeChecklistItem(
                key="k", label="L", status="photo", photo_id=1, na_reason="x"
            )

    def test_valid_na_item(self):
        item = IntakeChecklistItem(
            key="k", label="L", status="na", na_reason="Kein Stein vorhanden"
        )
        assert item.status == "na"

    def test_valid_photo_item(self):
        item = IntakeChecklistItem(key="k", label="L", status="photo", photo_id=42)
        assert item.photo_id == 42

    def test_valid_open_item_default_status(self):
        item = IntakeChecklistItem(key="k", label="L")
        assert item.status == "open"
        assert item.photo_id is None
        assert item.na_reason is None


class TestIntakeChecklistUpdateSchema:
    def test_rejects_more_than_20_items(self):
        items = [{"key": f"k{i}", "label": f"L{i}"} for i in range(21)]
        with pytest.raises(ValidationError):
            IntakeChecklistUpdate(items=items)

    def test_accepts_up_to_20_items(self):
        items = [{"key": f"k{i}", "label": f"L{i}"} for i in range(20)]
        update = IntakeChecklistUpdate(items=items)
        assert len(update.items) == 20
