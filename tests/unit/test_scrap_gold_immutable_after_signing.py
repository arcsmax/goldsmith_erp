"""BE-11 (W1-08 remaining part): an Altgold record is immutable once signed.

docs/review/2026-09-25/03-backend-correctness.md BE-11: after the customer
signs for 20 g 585 (702.00), staff could still add a 50 g silver chain,
change the gold price, or re-sign; ``calculate_and_update`` even demoted the
status from SIGNED back to CALCULATED while ``signature_data`` stayed. The
signed receipt then no longer matched the DB.

Rule enforced here (service layer, mapped to 409 by the router):
- SIGNED or CREDITED: items, weights, alloys, photos, the gold price and the
  signature are frozen. Only status progression (SIGNED -> CREDITED, done by
  the invoice service) and ``notes`` may change.
- ``calculate_and_update`` never demotes the status.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pytest

from goldsmith_erp.db.models import (
    AlloyType,
    MetalPriceSource,
    MetalType,
    ScrapGoldStatus,
)
from goldsmith_erp.models.scrap_gold import (
    ScrapGoldCreate,
    ScrapGoldItemCreate,
    ScrapGoldUpdate,
)
from goldsmith_erp.services.metal_price_service import MetalPriceService
from goldsmith_erp.services.scrap_gold_service import (
    ScrapGoldLockedError,
    ScrapGoldService,
)

_SIGNATURE = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAAB"
_FIXED_SPOT_PRICES = {
    MetalType.GOLD_24K: (60.0, MetalPriceSource.MANUAL, datetime.utcnow()),
    MetalType.SILVER_999: (0.90, MetalPriceSource.MANUAL, datetime.utcnow()),
    MetalType.PLATINUM_950: (32.0, MetalPriceSource.MANUAL, datetime.utcnow()),
}


@pytest.fixture(autouse=True)
def mock_spot_prices(monkeypatch):
    async def _fake_get_spot_prices(db: Any = None):
        return _FIXED_SPOT_PRICES

    monkeypatch.setattr(MetalPriceService, "get_spot_prices", _fake_get_spot_prices)


async def _signed_record(db_session, sample_customer, sample_order, admin_user):
    """20 g 585 at 60.00/g fine -> 11.7 g fine, 702.00, then signed."""
    scrap_gold = await ScrapGoldService.create(
        db_session,
        admin_user.id,
        ScrapGoldCreate(
            order_id=sample_order.id,
            customer_id=sample_customer.id,
            gold_price_per_g=60.0,
        ),
    )
    item = await ScrapGoldService.add_item(
        db_session,
        scrap_gold.id,
        ScrapGoldItemCreate(
            description="Alter Ehering", alloy=AlloyType.GOLD_585, weight_g=20.0
        ),
    )
    await ScrapGoldService.calculate_and_update(db_session, scrap_gold.id)
    await ScrapGoldService.sign(db_session, scrap_gold.id, _SIGNATURE)
    signed = await ScrapGoldService.get_by_id(db_session, scrap_gold.id)
    assert signed is not None
    assert signed.status == ScrapGoldStatus.SIGNED
    assert signed.total_value_eur == pytest.approx(702.0)
    return signed, item


@pytest.mark.asyncio
class TestServiceGuards:
    async def test_add_item_after_signing_is_rejected(
        self, db_session, sample_customer, sample_order, admin_user
    ) -> None:
        signed, _ = await _signed_record(
            db_session, sample_customer, sample_order, admin_user
        )

        with pytest.raises(ScrapGoldLockedError):
            await ScrapGoldService.add_item(
                db_session,
                signed.id,
                ScrapGoldItemCreate(
                    description="Silberkette", alloy=AlloyType.SILVER_925, weight_g=50
                ),
            )

        after = await ScrapGoldService.get_by_id(db_session, signed.id)
        assert len(after.items) == 1
        assert after.total_value_eur == pytest.approx(702.0)

    async def test_remove_item_after_signing_is_rejected(
        self, db_session, sample_customer, sample_order, admin_user
    ) -> None:
        signed, item = await _signed_record(
            db_session, sample_customer, sample_order, admin_user
        )

        with pytest.raises(ScrapGoldLockedError):
            await ScrapGoldService.remove_item(db_session, signed.id, item.id)

        after = await ScrapGoldService.get_by_id(db_session, signed.id)
        assert len(after.items) == 1

    async def test_price_change_via_calculate_after_signing_is_rejected(
        self, db_session, sample_customer, sample_order, admin_user
    ) -> None:
        signed, _ = await _signed_record(
            db_session, sample_customer, sample_order, admin_user
        )

        with pytest.raises(ScrapGoldLockedError):
            await ScrapGoldService.calculate_and_update(
                db_session, signed.id, gold_price_per_g=99.0
            )

        after = await ScrapGoldService.get_by_id(db_session, signed.id)
        assert after.gold_price_per_g == pytest.approx(60.0)
        assert after.total_value_eur == pytest.approx(702.0)

    async def test_calculate_without_price_keeps_signed_status_and_totals(
        self, db_session, sample_customer, sample_order, admin_user
    ) -> None:
        signed, _ = await _signed_record(
            db_session, sample_customer, sample_order, admin_user
        )

        result = await ScrapGoldService.calculate_and_update(db_session, signed.id)

        assert result is not None
        assert result.status == ScrapGoldStatus.SIGNED
        assert result.total_value_eur == pytest.approx(702.0)
        assert result.signature_data == _SIGNATURE

    async def test_resigning_is_rejected(
        self, db_session, sample_customer, sample_order, admin_user
    ) -> None:
        signed, _ = await _signed_record(
            db_session, sample_customer, sample_order, admin_user
        )

        with pytest.raises(ScrapGoldLockedError):
            await ScrapGoldService.sign(
                db_session, signed.id, "data:image/png;base64,OTHERSIGNATURE"
            )

        after = await ScrapGoldService.get_by_id(db_session, signed.id)
        assert after.signature_data == _SIGNATURE

    async def test_credited_record_is_locked_too(
        self, db_session, sample_customer, sample_order, admin_user
    ) -> None:
        signed, item = await _signed_record(
            db_session, sample_customer, sample_order, admin_user
        )
        signed.status = ScrapGoldStatus.CREDITED  # what invoice creation does
        await db_session.commit()

        with pytest.raises(ScrapGoldLockedError):
            await ScrapGoldService.remove_item(db_session, signed.id, item.id)
        result = await ScrapGoldService.calculate_and_update(db_session, signed.id)
        assert result.status == ScrapGoldStatus.CREDITED

    async def test_notes_may_change_after_signing(
        self, db_session, sample_customer, sample_order, admin_user
    ) -> None:
        signed, _ = await _signed_record(
            db_session, sample_customer, sample_order, admin_user
        )

        updated = await ScrapGoldService.update(
            db_session, signed.id, ScrapGoldUpdate(notes="Kunde holt Beleg ab")
        )

        assert updated is not None
        assert updated.notes == "Kunde holt Beleg ab"
        assert updated.status == ScrapGoldStatus.SIGNED

    async def test_price_update_after_signing_is_rejected(
        self, db_session, sample_customer, sample_order, admin_user
    ) -> None:
        signed, _ = await _signed_record(
            db_session, sample_customer, sample_order, admin_user
        )

        with pytest.raises(ScrapGoldLockedError):
            await ScrapGoldService.update(
                db_session, signed.id, ScrapGoldUpdate(gold_price_per_g=80.0)
            )

    async def test_unsigned_record_stays_editable(
        self, db_session, sample_customer, sample_order, admin_user
    ) -> None:
        scrap_gold = await ScrapGoldService.create(
            db_session,
            admin_user.id,
            ScrapGoldCreate(order_id=sample_order.id, customer_id=sample_customer.id),
        )
        item = await ScrapGoldService.add_item(
            db_session,
            scrap_gold.id,
            ScrapGoldItemCreate(
                description="Ring", alloy=AlloyType.GOLD_585, weight_g=5.0
            ),
        )
        sg_id, item_id = scrap_gold.id, item.id
        await ScrapGoldService.calculate_and_update(db_session, sg_id, 61.0)
        assert await ScrapGoldService.remove_item(db_session, sg_id, item_id)


@pytest.mark.asyncio
class TestHttpContract:
    async def _sign_via_api(self, client, headers, sample_customer, sample_order):
        create = await client.post(
            f"/api/v1/orders/{sample_order.id}/scrap-gold",
            json={
                "order_id": sample_order.id,
                "customer_id": sample_customer.id,
                "gold_price_per_g": 60.0,
            },
            headers=headers,
        )
        assert create.status_code == 201, create.text
        sg_id = create.json()["id"]
        add = await client.post(
            f"/api/v1/scrap-gold/{sg_id}/items",
            json={"description": "Ehering", "alloy": "585", "weight_g": 20.0},
            headers=headers,
        )
        assert add.status_code == 201, add.text
        sign = await client.post(
            f"/api/v1/scrap-gold/{sg_id}/sign",
            json={"signature_data": _SIGNATURE},
            headers=headers,
        )
        assert sign.status_code == 200, sign.text
        return sg_id, add.json()["id"]

    async def test_mutations_after_signing_return_409_german(
        self, client, admin_auth_headers, sample_customer, sample_order
    ) -> None:
        sg_id, item_id = await self._sign_via_api(
            client, admin_auth_headers, sample_customer, sample_order
        )

        add = await client.post(
            f"/api/v1/scrap-gold/{sg_id}/items",
            json={"description": "Kette", "alloy": "ag925", "weight_g": 50.0},
            headers=admin_auth_headers,
        )
        remove = await client.delete(
            f"/api/v1/scrap-gold/{sg_id}/items/{item_id}", headers=admin_auth_headers
        )
        calc = await client.post(
            f"/api/v1/scrap-gold/{sg_id}/calculate?gold_price_per_g=99",
            headers=admin_auth_headers,
        )
        resign = await client.post(
            f"/api/v1/scrap-gold/{sg_id}/sign",
            json={"signature_data": "data:image/png;base64,ANOTHERONE"},
            headers=admin_auth_headers,
        )
        photo = await client.post(
            f"/api/v1/scrap-gold/{sg_id}/items/{item_id}/photo",
            files={"file": ("x.png", b"\x89PNG\r\n\x1a\n" + b"0" * 32, "image/png")},
            headers=admin_auth_headers,
        )

        for resp in (add, remove, calc, resign, photo):
            assert resp.status_code == 409, resp.text
            assert "unterschrieben" in resp.json()["detail"]

        body = (
            await client.get(
                f"/api/v1/orders/{sample_order.id}/scrap-gold",
                headers=admin_auth_headers,
            )
        ).json()
        assert body["status"] == "signed"
        assert len(body["items"]) == 1
        assert body["total_value_eur"] == pytest.approx(702.0)

    async def test_notes_patch_after_signing_is_allowed(
        self, client, admin_auth_headers, sample_customer, sample_order
    ) -> None:
        sg_id, _ = await self._sign_via_api(
            client, admin_auth_headers, sample_customer, sample_order
        )

        notes = await client.patch(
            f"/api/v1/scrap-gold/{sg_id}",
            json={"notes": "Beleg ausgehaendigt"},
            headers=admin_auth_headers,
        )
        price = await client.patch(
            f"/api/v1/scrap-gold/{sg_id}",
            json={"gold_price_per_g": 70.0},
            headers=admin_auth_headers,
        )

        assert notes.status_code == 200, notes.text
        assert notes.json()["notes"] == "Beleg ausgehaendigt"
        assert notes.json()["status"] == "signed"
        assert price.status_code == 409, price.text
