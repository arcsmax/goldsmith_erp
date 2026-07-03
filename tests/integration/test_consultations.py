"""Integration tests for /api/v1/consultations.

Endpoint coverage:
  POST   /api/v1/consultations/                          - create consultation
  GET    /api/v1/consultations/                           - list consultations
  GET    /api/v1/consultations/{id}                       - get single consultation
  PATCH  /api/v1/consultations/{id}                        - autosave update
  POST   /api/v1/consultations/{id}/photos                 - upload photo (multipart)
  GET    /api/v1/consultations/{id}/photos                 - list photos
  GET    /api/v1/consultations/photos/{photo_id}            - serve original
  GET    /api/v1/consultations/photos/{photo_id}/thumbnail  - serve thumbnail
  DELETE /api/v1/consultations/photos/{photo_id}            - delete photo

Permission matrix (design IP — Beratung is business-confidential):
  - ADMIN / GOLDSMITH  — full create + view + edit workflow
  - VIEWER             — no access at all (403 everywhere)
  - No auth            — 401
"""

import io

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import Consultation, ConsultationStatus, Customer

CONSULTATIONS_URL = "/api/v1/consultations/"


def _create_payload(customer_id: int) -> dict:
    return {
        "customer_id": customer_id,
        "occasion": "engagement",
        "wishes": "Verlobungsring, Rotgold 585, schlicht",
        "budget_min": 800,
        "budget_max": 1500,
    }


def _jpeg_bytes() -> bytes:
    """A minimal valid 4x4 white JPEG, Pillow-generated in-memory."""
    buf = io.BytesIO()
    Image.new("RGB", (4, 4), "white").save(buf, format="JPEG")
    return buf.getvalue()


async def _create_consultation(
    client: AsyncClient, headers: dict, customer_id: int
) -> int:
    resp = await client.post(
        CONSULTATIONS_URL, json=_create_payload(customer_id), headers=headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


# ===========================================================================
# Auth / permission matrix
# ===========================================================================


class TestConsultationAuth:
    @pytest.mark.asyncio
    async def test_unauthenticated_create_returns_401(
        self, client: AsyncClient, test_customer: Customer
    ):
        response = await client.post(
            CONSULTATIONS_URL, json=_create_payload(test_customer.id)
        )
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_unauthenticated_list_returns_401(self, client: AsyncClient):
        response = await client.get(CONSULTATIONS_URL)
        assert response.status_code == 401

    @pytest.mark.asyncio
    async def test_viewer_cannot_view_consultations(
        self, client: AsyncClient, viewer_auth_headers: dict
    ):
        response = await client.get(CONSULTATIONS_URL, headers=viewer_auth_headers)
        assert response.status_code == 403  # design IP — no VIEWER access

    @pytest.mark.asyncio
    async def test_viewer_cannot_create_consultation(
        self,
        client: AsyncClient,
        viewer_auth_headers: dict,
        test_customer: Customer,
    ):
        response = await client.post(
            CONSULTATIONS_URL,
            json=_create_payload(test_customer.id),
            headers=viewer_auth_headers,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_cannot_edit_consultation(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        viewer_auth_headers: dict,
        test_customer: Customer,
    ):
        cid = await _create_consultation(
            client, goldsmith_auth_headers, test_customer.id
        )
        response = await client.patch(
            f"{CONSULTATIONS_URL}{cid}",
            json={"notes": "darf ich nicht"},
            headers=viewer_auth_headers,
        )
        assert response.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_cannot_get_consultation(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        viewer_auth_headers: dict,
        test_customer: Customer,
    ):
        cid = await _create_consultation(
            client, goldsmith_auth_headers, test_customer.id
        )
        response = await client.get(
            f"{CONSULTATIONS_URL}{cid}", headers=viewer_auth_headers
        )
        assert response.status_code == 403


# ===========================================================================
# CRUD
# ===========================================================================


class TestConsultationCrud:
    @pytest.mark.asyncio
    async def test_create_get_patch_roundtrip(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        test_customer: Customer,
    ):
        create = await client.post(
            CONSULTATIONS_URL,
            json=_create_payload(test_customer.id),
            headers=goldsmith_auth_headers,
        )
        assert create.status_code == 201
        cid = create.json()["id"]

        got = await client.get(
            f"{CONSULTATIONS_URL}{cid}", headers=goldsmith_auth_headers
        )
        assert got.status_code == 200
        assert got.json()["status"] == "draft"

        patched = await client.patch(
            f"{CONSULTATIONS_URL}{cid}",
            json={"notes": "Skizze folgt"},
            headers=goldsmith_auth_headers,
        )
        assert patched.status_code == 200
        assert patched.json()["notes"] == "Skizze folgt"

    @pytest.mark.asyncio
    async def test_get_unknown_returns_404(
        self, client: AsyncClient, goldsmith_auth_headers: dict
    ):
        response = await client.get(
            f"{CONSULTATIONS_URL}999999", headers=goldsmith_auth_headers
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_patch_unknown_returns_404(
        self, client: AsyncClient, goldsmith_auth_headers: dict
    ):
        response = await client.patch(
            f"{CONSULTATIONS_URL}999999",
            json={"notes": "x"},
            headers=goldsmith_auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_unknown_customer_returns_404(
        self, client: AsyncClient, goldsmith_auth_headers: dict
    ):
        response = await client.post(
            CONSULTATIONS_URL,
            json=_create_payload(999999),
            headers=goldsmith_auth_headers,
        )
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_list_returns_created_consultation(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        test_customer: Customer,
    ):
        cid = await _create_consultation(
            client, goldsmith_auth_headers, test_customer.id
        )
        resp = await client.get(
            CONSULTATIONS_URL,
            params={"customer_id": test_customer.id},
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 200
        ids = [c["id"] for c in resp.json()]
        assert cid in ids

    @pytest.mark.asyncio
    async def test_list_filters_by_status(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        test_customer: Customer,
    ):
        await _create_consultation(client, goldsmith_auth_headers, test_customer.id)
        resp = await client.get(
            CONSULTATIONS_URL,
            params={"status": "archived"},
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json() == []  # freshly created ones are draft, not archived

    @pytest.mark.asyncio
    async def test_patch_converted_consultation_returns_409(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        test_customer: Customer,
        db_session: AsyncSession,
    ):
        cid = await _create_consultation(
            client, goldsmith_auth_headers, test_customer.id
        )
        consultation = await db_session.get(Consultation, cid)
        consultation.status = ConsultationStatus.CONVERTED
        await db_session.commit()

        resp = await client.patch(
            f"{CONSULTATIONS_URL}{cid}",
            json={"wishes": "Neuer Wunsch"},
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 409


# ===========================================================================
# Convert
# ===========================================================================


class TestConsultationConvert:
    @pytest.mark.asyncio
    async def test_convert_to_order_then_second_call_returns_409(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        test_customer: Customer,
    ):
        cid = await _create_consultation(
            client, goldsmith_auth_headers, test_customer.id
        )

        resp = await client.post(
            f"{CONSULTATIONS_URL}{cid}/convert",
            json={"target": "order"},
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["status"] == "converted"
        assert body["converted_order_id"] is not None
        order_id = body["converted_order_id"]

        again = await client.post(
            f"{CONSULTATIONS_URL}{cid}/convert",
            json={"target": "order"},
            headers=goldsmith_auth_headers,
        )
        assert again.status_code == 409
        assert again.json()["detail"]["order_id"] == order_id

    @pytest.mark.asyncio
    async def test_convert_to_quote(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        test_customer: Customer,
    ):
        cid = await _create_consultation(
            client, goldsmith_auth_headers, test_customer.id
        )
        resp = await client.post(
            f"{CONSULTATIONS_URL}{cid}/convert",
            json={"target": "quote"},
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["converted_quote_id"] is not None
        assert body["converted_order_id"] is None

    @pytest.mark.asyncio
    async def test_unconvert_quote_conversion_resets_and_deletes_draft(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        test_customer: Customer,
    ):
        cid = await _create_consultation(
            client, goldsmith_auth_headers, test_customer.id
        )
        convert = await client.post(
            f"{CONSULTATIONS_URL}{cid}/convert",
            json={"target": "quote"},
            headers=goldsmith_auth_headers,
        )
        quote_id = convert.json()["converted_quote_id"]

        unconvert = await client.post(
            f"{CONSULTATIONS_URL}{cid}/unconvert", headers=goldsmith_auth_headers
        )
        assert unconvert.status_code == 200, unconvert.text
        body = unconvert.json()
        assert body["status"] == "completed"
        assert body["converted_quote_id"] is None
        # The empty draft quote is gone.
        gone = await client.get(
            f"/api/v1/quotes/{quote_id}", headers=goldsmith_auth_headers
        )
        assert gone.status_code == 404

    @pytest.mark.asyncio
    async def test_unconvert_order_conversion_returns_409(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        test_customer: Customer,
    ):
        cid = await _create_consultation(
            client, goldsmith_auth_headers, test_customer.id
        )
        await client.post(
            f"{CONSULTATIONS_URL}{cid}/convert",
            json={"target": "order"},
            headers=goldsmith_auth_headers,
        )
        resp = await client.post(
            f"{CONSULTATIONS_URL}{cid}/unconvert", headers=goldsmith_auth_headers
        )
        assert resp.status_code == 409, resp.text

    @pytest.mark.asyncio
    async def test_viewer_cannot_unconvert(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        viewer_auth_headers: dict,
        test_customer: Customer,
    ):
        cid = await _create_consultation(
            client, goldsmith_auth_headers, test_customer.id
        )
        await client.post(
            f"{CONSULTATIONS_URL}{cid}/convert",
            json={"target": "quote"},
            headers=goldsmith_auth_headers,
        )
        resp = await client.post(
            f"{CONSULTATIONS_URL}{cid}/unconvert", headers=viewer_auth_headers
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_convert_rejects_dangerous_wishes_with_generic_422(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        test_customer: Customer,
    ):
        """SECURITY (issue #13, item 1): the consultation's `wishes` text
        becomes the target order's `description`, which OrderCreate's
        SQL-keyword sanitizer validates. pydantic.ValidationError IS a
        ValueError subclass, so an untyped except-ValueError branch would
        misroute this to 404 AND echo the raw validation message — which
        embeds the offending wish text (business-confidential design
        intent). Must be 422 with a generic detail instead."""
        cid = await _create_consultation(
            client, goldsmith_auth_headers, test_customer.id
        )
        secret_wish = "Ring mit DROP TABLE orders Gravur"
        patch_resp = await client.patch(
            f"{CONSULTATIONS_URL}{cid}",
            json={"wishes": secret_wish},
            headers=goldsmith_auth_headers,
        )
        assert patch_resp.status_code == 200, patch_resp.text

        resp = await client.post(
            f"{CONSULTATIONS_URL}{cid}/convert",
            json={"target": "order"},
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 422, resp.text
        assert "DROP TABLE" not in resp.text
        assert secret_wish not in resp.text

    @pytest.mark.asyncio
    async def test_convert_unknown_consultation_returns_404(
        self, client: AsyncClient, goldsmith_auth_headers: dict
    ):
        resp = await client.post(
            f"{CONSULTATIONS_URL}999999/convert",
            json={"target": "order"},
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_viewer_cannot_convert_consultation(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        viewer_auth_headers: dict,
        test_customer: Customer,
    ):
        cid = await _create_consultation(
            client, goldsmith_auth_headers, test_customer.id
        )
        resp = await client.post(
            f"{CONSULTATIONS_URL}{cid}/convert",
            json={"target": "order"},
            headers=viewer_auth_headers,
        )
        assert resp.status_code == 403


# ===========================================================================
# Photos
# ===========================================================================


class TestConsultationPhotos:
    @pytest.mark.asyncio
    async def test_upload_list_get_thumbnail_delete_roundtrip(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        test_customer: Customer,
        tmp_path,
        monkeypatch,
    ):
        monkeypatch.setattr(
            "goldsmith_erp.core.config.settings.PHOTO_STORAGE_PATH", str(tmp_path)
        )
        cid = await _create_consultation(
            client, goldsmith_auth_headers, test_customer.id
        )

        files = {"file": ("sketch.jpg", _jpeg_bytes(), "image/jpeg")}
        data = {"kind": "sketch", "notes": "Erste Skizze"}
        upload = await client.post(
            f"{CONSULTATIONS_URL}{cid}/photos",
            files=files,
            data=data,
            headers=goldsmith_auth_headers,
        )
        assert upload.status_code == 201, upload.text
        photo_id = upload.json()["id"]
        assert upload.json()["kind"] == "sketch"

        # List — route "/{consultation_id}/photos" must not be shadowed
        listed = await client.get(
            f"{CONSULTATIONS_URL}{cid}/photos", headers=goldsmith_auth_headers
        )
        assert listed.status_code == 200
        assert any(p["id"] == photo_id for p in listed.json())

        # Serve original — route "/photos/{photo_id}" must not be shadowed by
        # "/{consultation_id}"
        file_resp = await client.get(
            f"{CONSULTATIONS_URL}photos/{photo_id}", headers=goldsmith_auth_headers
        )
        assert file_resp.status_code == 200
        assert file_resp.headers["content-type"] == "image/jpeg"

        thumb_resp = await client.get(
            f"{CONSULTATIONS_URL}photos/{photo_id}/thumbnail",
            headers=goldsmith_auth_headers,
        )
        assert thumb_resp.status_code == 200

        delete_resp = await client.delete(
            f"{CONSULTATIONS_URL}photos/{photo_id}", headers=goldsmith_auth_headers
        )
        assert delete_resp.status_code == 204

        missing = await client.get(
            f"{CONSULTATIONS_URL}photos/{photo_id}", headers=goldsmith_auth_headers
        )
        assert missing.status_code == 404

    @pytest.mark.asyncio
    async def test_upload_rejects_non_image(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        test_customer: Customer,
        tmp_path,
        monkeypatch,
    ):
        monkeypatch.setattr(
            "goldsmith_erp.core.config.settings.PHOTO_STORAGE_PATH", str(tmp_path)
        )
        cid = await _create_consultation(
            client, goldsmith_auth_headers, test_customer.id
        )

        files = {"file": ("x.pdf", b"%PDF-1.4 not an image", "application/pdf")}
        resp = await client.post(
            f"{CONSULTATIONS_URL}{cid}/photos",
            files=files,
            data={"kind": "sketch"},
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_upload_unknown_consultation_returns_404(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        tmp_path,
        monkeypatch,
    ):
        monkeypatch.setattr(
            "goldsmith_erp.core.config.settings.PHOTO_STORAGE_PATH", str(tmp_path)
        )
        files = {"file": ("sketch.jpg", _jpeg_bytes(), "image/jpeg")}
        resp = await client.post(
            f"{CONSULTATIONS_URL}999999/photos",
            files=files,
            data={"kind": "sketch"},
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_get_unknown_photo_returns_404(
        self, client: AsyncClient, goldsmith_auth_headers: dict
    ):
        resp = await client.get(
            f"{CONSULTATIONS_URL}photos/does-not-exist",
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_unknown_photo_returns_404(
        self, client: AsyncClient, goldsmith_auth_headers: dict
    ):
        resp = await client.delete(
            f"{CONSULTATIONS_URL}photos/does-not-exist",
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_viewer_cannot_upload_photo(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        viewer_auth_headers: dict,
        test_customer: Customer,
        tmp_path,
        monkeypatch,
    ):
        monkeypatch.setattr(
            "goldsmith_erp.core.config.settings.PHOTO_STORAGE_PATH", str(tmp_path)
        )
        cid = await _create_consultation(
            client, goldsmith_auth_headers, test_customer.id
        )
        files = {"file": ("sketch.jpg", _jpeg_bytes(), "image/jpeg")}
        resp = await client.post(
            f"{CONSULTATIONS_URL}{cid}/photos",
            files=files,
            data={"kind": "sketch"},
            headers=viewer_auth_headers,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_cannot_list_photos(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        viewer_auth_headers: dict,
        test_customer: Customer,
    ):
        cid = await _create_consultation(
            client, goldsmith_auth_headers, test_customer.id
        )
        resp = await client.get(
            f"{CONSULTATIONS_URL}{cid}/photos", headers=viewer_auth_headers
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_cannot_get_photo_file(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        viewer_auth_headers: dict,
        test_customer: Customer,
        tmp_path,
        monkeypatch,
    ):
        monkeypatch.setattr(
            "goldsmith_erp.core.config.settings.PHOTO_STORAGE_PATH", str(tmp_path)
        )
        cid = await _create_consultation(
            client, goldsmith_auth_headers, test_customer.id
        )
        files = {"file": ("sketch.jpg", _jpeg_bytes(), "image/jpeg")}
        upload = await client.post(
            f"{CONSULTATIONS_URL}{cid}/photos",
            files=files,
            data={"kind": "sketch"},
            headers=goldsmith_auth_headers,
        )
        assert upload.status_code == 201, upload.text
        photo_id = upload.json()["id"]

        resp = await client.get(
            f"{CONSULTATIONS_URL}photos/{photo_id}", headers=viewer_auth_headers
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_cannot_get_photo_thumbnail(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        viewer_auth_headers: dict,
        test_customer: Customer,
        tmp_path,
        monkeypatch,
    ):
        monkeypatch.setattr(
            "goldsmith_erp.core.config.settings.PHOTO_STORAGE_PATH", str(tmp_path)
        )
        cid = await _create_consultation(
            client, goldsmith_auth_headers, test_customer.id
        )
        files = {"file": ("sketch.jpg", _jpeg_bytes(), "image/jpeg")}
        upload = await client.post(
            f"{CONSULTATIONS_URL}{cid}/photos",
            files=files,
            data={"kind": "sketch"},
            headers=goldsmith_auth_headers,
        )
        assert upload.status_code == 201, upload.text
        photo_id = upload.json()["id"]

        resp = await client.get(
            f"{CONSULTATIONS_URL}photos/{photo_id}/thumbnail",
            headers=viewer_auth_headers,
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_viewer_cannot_delete_photo(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        viewer_auth_headers: dict,
        test_customer: Customer,
        tmp_path,
        monkeypatch,
    ):
        monkeypatch.setattr(
            "goldsmith_erp.core.config.settings.PHOTO_STORAGE_PATH", str(tmp_path)
        )
        cid = await _create_consultation(
            client, goldsmith_auth_headers, test_customer.id
        )
        files = {"file": ("sketch.jpg", _jpeg_bytes(), "image/jpeg")}
        upload = await client.post(
            f"{CONSULTATIONS_URL}{cid}/photos",
            files=files,
            data={"kind": "sketch"},
            headers=goldsmith_auth_headers,
        )
        assert upload.status_code == 201, upload.text
        photo_id = upload.json()["id"]

        resp = await client.delete(
            f"{CONSULTATIONS_URL}photos/{photo_id}", headers=viewer_auth_headers
        )
        assert resp.status_code == 403

        # Still retrievable by GOLDSMITH — the VIEWER call must not have
        # deleted the photo despite the 403.
        still_there = await client.get(
            f"{CONSULTATIONS_URL}photos/{photo_id}", headers=goldsmith_auth_headers
        )
        assert still_there.status_code == 200
