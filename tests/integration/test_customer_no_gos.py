"""Integration tests for customer no-gos and style profile (V1.1
consultation module, Task 8).

Endpoint coverage:
  GET    /api/v1/customers/{id}/no-gos              - list no-gos
  POST   /api/v1/customers/{id}/no-gos              - add no-go
  DELETE /api/v1/customers/{id}/no-gos/{no_go_id}   - remove no-go
  GET    /api/v1/customers/{id}/no-gos/check        - conflict check
  GET    /api/v1/customers/{id}/style-profile       - read style profile
  PATCH  /api/v1/customers/{id}/style-profile       - merge-patch style profile

Permissions: no-gos and the style profile are preference data (not design
IP) — they reuse the existing CUSTOMER_VIEW/CUSTOMER_EDIT permissions, so
VIEWER keeps read access (unlike /consultations, which is GOLDSMITH/ADMIN
only — see test_consultations.py).
"""

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from goldsmith_erp.db.models import Customer


def _no_gos_url(customer_id: int) -> str:
    return f"/api/v1/customers/{customer_id}/no-gos"


def _style_profile_url(customer_id: int) -> str:
    return f"/api/v1/customers/{customer_id}/style-profile"


class TestNoGos:
    @pytest.mark.asyncio
    async def test_no_go_crud_and_duplicate(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        test_customer: Customer,
    ):
        base = _no_gos_url(test_customer.id)
        created = await client.post(
            base,
            json={"category": "allergy", "value": "Nickel"},
            headers=goldsmith_auth_headers,
        )
        assert created.status_code == 201, created.text
        no_go_id = created.json()["id"]

        dup = await client.post(
            base,
            json={"category": "allergy", "value": "nickel"},
            headers=goldsmith_auth_headers,
        )
        assert dup.status_code == 409

        listed = await client.get(base, headers=goldsmith_auth_headers)
        assert listed.status_code == 200
        assert [n["value"] for n in listed.json()] == ["Nickel"]

        deleted = await client.delete(
            f"{base}/{no_go_id}", headers=goldsmith_auth_headers
        )
        assert deleted.status_code == 204

        listed_after = await client.get(base, headers=goldsmith_auth_headers)
        assert listed_after.json() == []

    @pytest.mark.asyncio
    async def test_duplicate_no_go_409_does_not_leak_value(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        test_customer: Customer,
    ):
        """SECURITY (binding review note): the 409 response body must never
        contain the submitted no-go value — it is health-adjacent data
        (e.g. an allergy). NoGoService.add_no_go's duplicate ValueError
        embeds the raw value; the router must map it to a generic detail."""
        base = _no_gos_url(test_customer.id)
        secret_value = "Nickelsulfat-Allergie-XYZ"
        await client.post(
            base,
            json={"category": "allergy", "value": secret_value},
            headers=goldsmith_auth_headers,
        )
        dup = await client.post(
            base,
            json={"category": "allergy", "value": secret_value},
            headers=goldsmith_auth_headers,
        )
        assert dup.status_code == 409
        assert secret_value not in dup.text

    @pytest.mark.asyncio
    async def test_duplicate_with_not_found_substring_still_409_no_leak(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        test_customer: Customer,
    ):
        """SECURITY (fix round 1): error routing must be typed, not
        string-matched. A duplicate whose VALUE contains the literal
        substring "not found" must still be a 409 (not misrouted to a
        404 branch that forwards the raw message) and must not leak the
        value in the response body."""
        base = _no_gos_url(test_customer.id)
        tricky_value = "Rosegold — not found in stock"
        first = await client.post(
            base,
            json={"category": "metal", "value": tricky_value},
            headers=goldsmith_auth_headers,
        )
        assert first.status_code == 201, first.text

        dup = await client.post(
            base,
            json={"category": "metal", "value": tricky_value},
            headers=goldsmith_auth_headers,
        )
        assert dup.status_code == 409
        assert tricky_value not in dup.text
        assert "Rosegold" not in dup.text

    @pytest.mark.asyncio
    async def test_create_no_go_unknown_customer_returns_404(
        self, client: AsyncClient, goldsmith_auth_headers: dict
    ):
        response = await client.post(
            _no_gos_url(999999),
            json={"category": "allergy", "value": "Nickel"},
            headers=goldsmith_auth_headers,
        )
        assert response.status_code == 404
        assert response.json()["detail"] == "Kunde nicht gefunden"

    @pytest.mark.asyncio
    async def test_list_no_gos_unknown_customer_returns_404(
        self, client: AsyncClient, goldsmith_auth_headers: dict
    ):
        """Regression (issue #13, item 4): GET used to return an empty
        list for any unknown customer_id instead of 404 — matching the
        style-profile endpoint's existing guard."""
        response = await client.get(_no_gos_url(999999), headers=goldsmith_auth_headers)
        assert response.status_code == 404
        assert response.json()["detail"] == "Kunde nicht gefunden"

    @pytest.mark.asyncio
    async def test_no_go_endpoints_404_for_deactivated_customer(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        test_customer: Customer,
        db_session: AsyncSession,
    ):
        """Regression (issue #13, item 5): CustomerService.delete_customer
        soft-deletes via is_active=False (not is_deleted). The V1.1 no-go
        endpoints previously guarded only is_deleted, so a customer removed
        through DELETE /customers/{id} stayed fully visible here."""
        test_customer.is_active = False
        db_session.add(test_customer)
        await db_session.commit()

        base = _no_gos_url(test_customer.id)

        listed = await client.get(base, headers=goldsmith_auth_headers)
        assert listed.status_code == 404
        assert listed.json()["detail"] == "Kunde nicht gefunden"

        created = await client.post(
            base,
            json={"category": "allergy", "value": "Nickel"},
            headers=goldsmith_auth_headers,
        )
        assert created.status_code == 404
        assert created.json()["detail"] == "Kunde nicht gefunden"

        checked = await client.get(
            f"{base}/check",
            params=[("candidate", "Nickel")],
            headers=goldsmith_auth_headers,
        )
        assert checked.status_code == 404
        assert checked.json()["detail"] == "Kunde nicht gefunden"

        deleted = await client.delete(f"{base}/1", headers=goldsmith_auth_headers)
        assert deleted.status_code == 404
        assert deleted.json()["detail"] == "Kunde nicht gefunden"

    @pytest.mark.asyncio
    async def test_check_endpoint_rejects_more_than_50_candidates(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        test_customer: Customer,
    ):
        """Input bounds (issue #13, item 2): the candidate query list is
        capped at 50 items — beyond that is a 422, not an unbounded scan."""
        base = _no_gos_url(test_customer.id)
        params = [("candidate", str(i)) for i in range(51)]
        resp = await client.get(
            f"{base}/check", params=params, headers=goldsmith_auth_headers
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_check_endpoint_flags_conflict(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        test_customer: Customer,
    ):
        base = _no_gos_url(test_customer.id)
        await client.post(
            base,
            json={"category": "metal", "value": "Weißgold"},
            headers=goldsmith_auth_headers,
        )
        check = await client.get(
            f"{base}/check",
            params=[("candidate", "Weißgold 585"), ("candidate", "Saphir")],
            headers=goldsmith_auth_headers,
        )
        assert check.status_code == 200
        assert len(check.json()) == 1
        assert check.json()[0]["matched_against"] == "Weißgold 585"

    @pytest.mark.asyncio
    async def test_viewer_can_list_no_gos_but_cannot_create(
        self,
        client: AsyncClient,
        viewer_auth_headers: dict,
        test_customer: Customer,
    ):
        """No-gos are preference data, not design IP — VIEWER keeps
        CUSTOMER_VIEW read access, unlike /consultations (CONSULTATION_*,
        no VIEWER access at all)."""
        base = _no_gos_url(test_customer.id)
        listed = await client.get(base, headers=viewer_auth_headers)
        assert listed.status_code == 200

        created = await client.post(
            base,
            json={"category": "allergy", "value": "Nickel"},
            headers=viewer_auth_headers,
        )
        assert created.status_code == 403


class TestStyleProfile:
    @pytest.mark.asyncio
    async def test_style_profile_merge_patch(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        test_customer: Customer,
    ):
        url = _style_profile_url(test_customer.id)
        empty = await client.get(url, headers=goldsmith_auth_headers)
        assert empty.status_code == 200
        assert empty.json() == {
            "metal_tones": [],
            "finishes": [],
            "stone_preferences": [],
            "style_words": [],
        }
        await client.patch(
            url, json={"metal_tones": ["rosé"]}, headers=goldsmith_auth_headers
        )
        second = await client.patch(
            url, json={"style_words": ["schlicht"]}, headers=goldsmith_auth_headers
        )
        assert second.status_code == 200
        assert second.json()["metal_tones"] == ["rosé"]  # merge, not replace
        assert second.json()["style_words"] == ["schlicht"]

    @pytest.mark.asyncio
    async def test_style_profile_unknown_customer_returns_404(
        self, client: AsyncClient, goldsmith_auth_headers: dict
    ):
        get_resp = await client.get(
            _style_profile_url(999999), headers=goldsmith_auth_headers
        )
        assert get_resp.status_code == 404
        # Unified German detail (issue #13, item 8) — matches every other
        # V1.1 customer-endpoint 404 (see create_customer_no_go).
        assert get_resp.json()["detail"] == "Kunde nicht gefunden"

        patch_resp = await client.patch(
            _style_profile_url(999999),
            json={"metal_tones": ["rosé"]},
            headers=goldsmith_auth_headers,
        )
        assert patch_resp.status_code == 404
        assert patch_resp.json()["detail"] == "Kunde nicht gefunden"

    @pytest.mark.asyncio
    async def test_style_profile_404_for_deactivated_customer(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        test_customer: Customer,
        db_session: AsyncSession,
    ):
        """Regression (issue #13, item 5): is_active=False (the flag
        CustomerService.delete_customer actually sets) must 404 here, not
        just is_deleted=True."""
        test_customer.is_active = False
        db_session.add(test_customer)
        await db_session.commit()

        url = _style_profile_url(test_customer.id)
        get_resp = await client.get(url, headers=goldsmith_auth_headers)
        assert get_resp.status_code == 404
        assert get_resp.json()["detail"] == "Kunde nicht gefunden"

        patch_resp = await client.patch(
            url, json={"metal_tones": ["rosé"]}, headers=goldsmith_auth_headers
        )
        assert patch_resp.status_code == 404
        assert patch_resp.json()["detail"] == "Kunde nicht gefunden"

    @pytest.mark.asyncio
    async def test_style_profile_rejects_oversized_list(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        test_customer: Customer,
    ):
        """Input bounds (issue #13, item 2): each style-profile list is
        capped at 50 items."""
        url = _style_profile_url(test_customer.id)
        resp = await client.patch(
            url,
            json={"metal_tones": [f"ton-{i}" for i in range(51)]},
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_style_profile_rejects_oversized_item(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        test_customer: Customer,
    ):
        """Input bounds (issue #13, item 2): each item is capped at 100
        characters."""
        url = _style_profile_url(test_customer.id)
        resp = await client.patch(
            url,
            json={"metal_tones": ["x" * 101]},
            headers=goldsmith_auth_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_viewer_can_view_style_profile_but_not_edit(
        self,
        client: AsyncClient,
        viewer_auth_headers: dict,
        test_customer: Customer,
    ):
        url = _style_profile_url(test_customer.id)
        viewed = await client.get(url, headers=viewer_auth_headers)
        assert viewed.status_code == 200

        patched = await client.patch(
            url, json={"metal_tones": ["rosé"]}, headers=viewer_auth_headers
        )
        assert patched.status_code == 403

    @pytest.mark.asyncio
    async def test_patch_explicit_null_resets_field_to_empty_list(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        test_customer: Customer,
    ):
        """Regression (final-review fix): {"metal_tones": null} used to
        survive exclude_unset=True (the key IS set, just to None), persist
        None into the JSON column, then blow up StyleProfileRead with a
        ValidationError -> 500 on every subsequent style-profile request
        for that customer. Explicit null is now treated as "reset this
        field to []" — the RESTful, most useful interpretation of a
        client explicitly clearing a list-shaped preference field.
        """
        url = _style_profile_url(test_customer.id)
        seeded = await client.patch(
            url, json={"metal_tones": ["rosé"]}, headers=goldsmith_auth_headers
        )
        assert seeded.status_code == 200
        assert seeded.json()["metal_tones"] == ["rosé"]

        cleared = await client.patch(
            url, json={"metal_tones": None}, headers=goldsmith_auth_headers
        )
        assert cleared.status_code == 200, cleared.text
        assert cleared.json()["metal_tones"] == []

        # Subsequent GET must not 500 — the poisoned-None regression this
        # guards against broke every future read, not just the PATCH.
        get_resp = await client.get(url, headers=goldsmith_auth_headers)
        assert get_resp.status_code == 200, get_resp.text
        assert get_resp.json()["metal_tones"] == []

    @pytest.mark.asyncio
    async def test_get_tolerates_pre_poisoned_none_value(
        self,
        client: AsyncClient,
        goldsmith_auth_headers: dict,
        test_customer: Customer,
        db_session: AsyncSession,
    ):
        """Regression: a row poisoned by the pre-fix PATCH bug (raw
        ``{"metal_tones": None}`` written directly to the JSON column,
        bypassing the endpoint) must not 500 the GET path either. The GET
        handler coerces None values to [] when building StyleProfileRead.
        """
        test_customer.style_profile = {"metal_tones": None}
        db_session.add(test_customer)
        await db_session.commit()

        resp = await client.get(
            _style_profile_url(test_customer.id), headers=goldsmith_auth_headers
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["metal_tones"] == []
