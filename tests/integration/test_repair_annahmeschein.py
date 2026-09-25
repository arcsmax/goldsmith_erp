"""
W2-12 (FE-17, DOM-08): counter intake and the Annahmeschein PDF.

Covers
  POST /api/v1/repairs/                        intake fields (problem, condition,
                                               price indication, promised date)
  GET  /api/v1/repairs/{id}/annahmeschein.pdf  the intake receipt

fpdf2 embeds subset fonts, so the PDF bytes are not greppable; the drawn text
is captured by wrapping ``_GoldsmithPDF.cell`` / ``multi_cell`` (same seam as
tests/integration/test_invoice_ustg14.py). Embedded images are captured by
wrapping ``pdf_service._embed_image_bytes``.
"""

from __future__ import annotations

import io
from typing import Any, List, Tuple

import pytest
from httpx import AsyncClient
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import Customer
from goldsmith_erp.services import pdf_service

pytestmark = pytest.mark.asyncio

REPAIRS_URL = "/api/v1/repairs/"
SETTINGS_URL = "/api/v1/admin/workshop-settings"

WORKSHOP = {
    "name": "Goldschmiede Anne Beispiel",
    "owner_name": "Anne Beispiel",
    "street": "Werkstattweg 5",
    "postal_code": "80331",
    "city": "München",
    "country": "Deutschland",
    "phone": "+49 89 7654321",
    "email": "werkstatt@example.com",
    "tax_number": "143/123/45678",
    "vat_id": None,
    "iban": None,
    "bic": None,
    "bank_name": None,
    "is_kleinunternehmer": False,
    "default_vat_rate": 19.0,
    "invoice_footer": None,
}

LARGE_PHOTO_PX = (1600, 1200)
THUMBNAIL_MAX_PX = 400


@pytest.fixture
def pdf_text(monkeypatch) -> List[str]:
    """Every string drawn by the renderer, in order."""
    drawn: List[str] = []
    cls = pdf_service._GoldsmithPDF
    original_cell = cls.cell
    original_multi = cls.multi_cell

    def _text(args: tuple, kwargs: dict) -> str:
        if "text" in kwargs:
            return str(kwargs["text"])
        return str(args[2]) if len(args) > 2 else ""

    def cell(self, *args: Any, **kwargs: Any):
        drawn.append(_text(args, kwargs))
        return original_cell(self, *args, **kwargs)

    def multi_cell(self, *args: Any, **kwargs: Any):
        drawn.append(_text(args, kwargs))
        return original_multi(self, *args, **kwargs)

    monkeypatch.setattr(cls, "cell", cell)
    monkeypatch.setattr(cls, "multi_cell", multi_cell)
    return drawn


@pytest.fixture
def embedded_images(monkeypatch) -> List[Tuple[int, int]]:
    """Pixel size of every image the renderer embeds."""
    sizes: List[Tuple[int, int]] = []
    original = pdf_service._embed_image_bytes

    def spy(pdf: Any, img_data: bytes, rect: Any, suffix: str = ".png") -> None:
        with Image.open(io.BytesIO(img_data)) as img:
            sizes.append(img.size)
        original(pdf, img_data, rect, suffix=suffix)

    monkeypatch.setattr(pdf_service, "_embed_image_bytes", spy)
    return sizes


@pytest.fixture
def photo_storage(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "goldsmith_erp.core.config.settings.PHOTO_STORAGE_PATH", str(tmp_path)
    )
    return tmp_path


def _jpeg(size: Tuple[int, int]) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, "white").save(buf, format="JPEG")
    return buf.getvalue()


def _intake_payload(customer_id: int) -> dict:
    return {
        "customer_id": customer_id,
        "item_description": "Ehering Gelbgold 585",
        "item_type": "ring",
        "metal_type": "585 Gelbgold",
        "customer_problem": "Stein locker, beim Tragen verloren gegangen",
        "condition_notes": ["Kratzer", "Tragespuren"],
        "estimated_cost": 85.0,
        "estimated_completion_date": "2026-10-02T00:00:00.000Z",
    }


async def _save_workshop(client: AsyncClient, headers: dict) -> None:
    resp = await client.put(SETTINGS_URL, json=WORKSHOP, headers=headers)
    assert resp.status_code == 200, resp.text


async def _create_intake(client: AsyncClient, headers: dict, customer_id: int) -> dict:
    resp = await client.post(
        REPAIRS_URL, json=_intake_payload(customer_id), headers=headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _upload_photo(
    client: AsyncClient, headers: dict, repair_id: int, size: Tuple[int, int]
) -> None:
    resp = await client.post(
        f"{REPAIRS_URL}{repair_id}/photos",
        files={"file": ("intake.jpg", _jpeg(size), "image/jpeg")},
        data={"phase": "intake"},
        headers=headers,
    )
    assert resp.status_code == 201, resp.text


def _pdf_url(repair_id: int) -> str:
    return f"{REPAIRS_URL}{repair_id}/annahmeschein.pdf"


# --------------------------------------------------------------------------
# Intake fields on create
# --------------------------------------------------------------------------


async def test_intake_stores_problem_condition_price_and_date(
    client: AsyncClient, admin_auth_headers: dict, test_customer: Customer
) -> None:
    repair = await _create_intake(client, admin_auth_headers, test_customer.id)

    assert repair["customer_id"] == test_customer.id
    assert repair["estimated_cost"] == 85.0
    assert repair["estimated_completion_date"].startswith("2026-10-02")
    description = repair["item_description"]
    assert description.startswith("Ehering Gelbgold 585")
    assert "Kundenangabe: Stein locker, beim Tragen verloren gegangen" in description
    assert "Zustand bei Annahme: Kratzer, Tragespuren" in description


async def test_intake_without_optional_fields_keeps_plain_description(
    client: AsyncClient, admin_auth_headers: dict
) -> None:
    resp = await client.post(
        REPAIRS_URL,
        json={"item_description": "Kette 750", "item_type": "chain"},
        headers=admin_auth_headers,
    )

    assert resp.status_code == 201, resp.text
    assert resp.json()["item_description"] == "Kette 750"
    assert resp.json()["estimated_cost"] is None


async def test_intake_rejects_negative_price_indication(
    client: AsyncClient, admin_auth_headers: dict, test_customer: Customer
) -> None:
    payload = {**_intake_payload(test_customer.id), "estimated_cost": -1}

    resp = await client.post(REPAIRS_URL, json=payload, headers=admin_auth_headers)

    assert resp.status_code == 422


# --------------------------------------------------------------------------
# Annahmeschein PDF
# --------------------------------------------------------------------------


async def test_annahmeschein_contains_mandatory_elements(
    client: AsyncClient,
    admin_auth_headers: dict,
    test_customer: Customer,
    pdf_text: List[str],
) -> None:
    await _save_workshop(client, admin_auth_headers)
    repair = await _create_intake(client, admin_auth_headers, test_customer.id)
    pdf_text.clear()

    resp = await client.get(_pdf_url(repair["id"]), headers=admin_auth_headers)

    assert resp.status_code == 200, resp.text
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")
    assert "Annahmeschein" in resp.headers["content-disposition"]
    text = "\n".join(pdf_text)
    # Workshop data from the workshop settings
    assert "Goldschmiede Anne Beispiel" in text
    assert "Werkstattweg 5" in text
    assert "80331 München" in text
    assert "+49 89 7654321" in text
    # Identity of the job
    assert "Annahmeschein" in text
    assert repair["repair_number"] in text
    assert repair["bag_number"] in text
    # Customer
    assert "Maria Mustermann" in text
    # Piece, problem and condition
    assert "Ring" in text
    assert "585 Gelbgold" in text
    assert "Stein locker" in text
    assert "Kratzer, Tragespuren" in text
    # Price indication, dates
    assert "85,00 €" in text
    assert "02.10.2026" in text
    # Liability clause and signature line
    assert any("Steine" in line and "Haftung" in line for line in pdf_text)
    assert "Unterschrift Kundin/Kunde" in text


async def test_annahmeschein_falls_back_to_configured_workshop_name(
    client: AsyncClient,
    admin_auth_headers: dict,
    test_customer: Customer,
    pdf_text: List[str],
) -> None:
    from goldsmith_erp.core.config import settings

    repair = await _create_intake(client, admin_auth_headers, test_customer.id)
    pdf_text.clear()

    resp = await client.get(_pdf_url(repair["id"]), headers=admin_auth_headers)

    assert resp.status_code == 200, resp.text
    assert settings.WORKSHOP_NAME in "\n".join(pdf_text)


async def test_annahmeschein_embeds_intake_photos_as_thumbnails(
    client: AsyncClient,
    goldsmith_auth_headers: dict,
    test_customer: Customer,
    photo_storage,
    embedded_images: List[Tuple[int, int]],
) -> None:
    repair = await _create_intake(client, goldsmith_auth_headers, test_customer.id)
    await _upload_photo(client, goldsmith_auth_headers, repair["id"], LARGE_PHOTO_PX)
    await _upload_photo(client, goldsmith_auth_headers, repair["id"], LARGE_PHOTO_PX)
    embedded_images.clear()

    resp = await client.get(_pdf_url(repair["id"]), headers=goldsmith_auth_headers)

    assert resp.status_code == 200, resp.text
    assert len(embedded_images) == 2
    for width, height in embedded_images:
        assert max(width, height) <= THUMBNAIL_MAX_PX


async def test_annahmeschein_without_photos_still_renders(
    client: AsyncClient,
    admin_auth_headers: dict,
    test_customer: Customer,
    photo_storage,
    embedded_images: List[Tuple[int, int]],
) -> None:
    repair = await _create_intake(client, admin_auth_headers, test_customer.id)

    resp = await client.get(_pdf_url(repair["id"]), headers=admin_auth_headers)

    assert resp.status_code == 200, resp.text
    assert embedded_images == []


async def test_annahmeschein_viewer_gets_403(
    client: AsyncClient,
    admin_auth_headers: dict,
    viewer_auth_headers: dict,
    test_customer: Customer,
) -> None:
    repair = await _create_intake(client, admin_auth_headers, test_customer.id)

    resp = await client.get(_pdf_url(repair["id"]), headers=viewer_auth_headers)

    assert resp.status_code == 403


async def test_annahmeschein_unknown_repair_gets_404(
    client: AsyncClient, admin_auth_headers: dict
) -> None:
    resp = await client.get(_pdf_url(999999), headers=admin_auth_headers)

    assert resp.status_code == 404


async def test_annahmeschein_requires_authentication(client: AsyncClient) -> None:
    resp = await client.get(_pdf_url(1))

    assert resp.status_code == 401


async def test_renderer_draws_signature_when_given(
    embedded_images: List[Tuple[int, int]],
) -> None:
    """The renderer takes an optional PNG signature (W2-12 part 3): no
    signature column exists yet, so the router passes None, but the PDF
    function is ready for it."""
    from types import SimpleNamespace

    buf = io.BytesIO()
    Image.new("RGB", (300, 100), "white").save(buf, format="PNG")
    repair = SimpleNamespace(
        repair_number="REP-2026-0001",
        bag_number="TU-2026-0001",
        item_type=SimpleNamespace(value="ring"),
        item_description="Ring",
        metal_type=None,
        estimated_cost=None,
        estimated_completion_date=None,
        created_at=None,
        intake_checklist=None,
    )

    pdf = pdf_service.render_repair_intake_receipt_pdf(
        repair=repair,
        customer=None,
        workshop={"name": "Werkstatt"},
        photos=[],
        signature_png=buf.getvalue(),
        include_price=True,
    )

    assert pdf.startswith(b"%PDF")
    assert embedded_images == [(300, 100)]
