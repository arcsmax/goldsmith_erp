"""Tests for the theme configuration router (GET/PUT /api/v1/theme).

Covers:
  * The default primary_color / header_gradient_start are the AA-compliant
    #b45309 (design tokens phase 1, W4-01) — not the old #d97706, which
    fails WCAG AA's 4.5:1 minimum contrast for white text.
  * contrast_with_white() matches the frontend's independently-implemented
    algorithm (frontend/src/hooks/useTheme.ts) bit for bit, on the same
    documented reference values.
  * PUT rejects an admin-set text-bearing colour whose contrast with white
    falls below 4.5:1, with a German 422 — the frontend already silently
    drops such a colour (useTheme.ts's setTextBearingColour), so a value
    that reached persistence without this check would be accepted by the
    API but never actually rendered.
  * PUT accepts and persists an AA-compliant colour.
"""

from __future__ import annotations

import json

import pytest
from httpx import AsyncClient

from goldsmith_erp.api.routers import theme as theme_router
from goldsmith_erp.api.routers.theme import ThemeSettings, contrast_with_white

THEME_URL = "/api/v1/theme"


@pytest.fixture(autouse=True)
def _isolated_theme_storage(tmp_path, monkeypatch):
    """Point the router's theme.json at a throwaway tmp_path for every test
    in this module, so tests never read or write the repo's real
    uploads/theme.json."""
    theme_file = tmp_path / "theme.json"
    monkeypatch.setattr(theme_router, "_UPLOADS_DIR", tmp_path)
    monkeypatch.setattr(theme_router, "_THEME_FILE", theme_file)
    return theme_file


# ---------------------------------------------------------------------------
# 1. Default colours are AA-compliant
# ---------------------------------------------------------------------------


class TestDefaults:
    def test_primary_color_default_is_aa_compliant(self):
        assert ThemeSettings().primary_color == "#b45309"
        assert contrast_with_white("#b45309") >= 4.5

    def test_header_gradient_start_default_is_aa_compliant(self):
        assert ThemeSettings().header_gradient_start == "#b45309"
        assert contrast_with_white("#b45309") >= 4.5

    def test_old_default_would_have_failed_aa(self):
        """Regression guard: the colour we moved away from must still be
        provably below the threshold, or this whole fix is pointless."""
        assert contrast_with_white("#d97706") < 4.5


# ---------------------------------------------------------------------------
# 2. contrast_with_white() matches the frontend's independent implementation
#    (frontend/src/hooks/useTheme.test.ts documents the same two values).
# ---------------------------------------------------------------------------


class TestContrastWithWhite:
    def test_matches_frontend_reference_values(self):
        assert contrast_with_white("#d97706") == pytest.approx(3.19, abs=0.01)
        assert contrast_with_white("#b45309") == pytest.approx(5.02, abs=0.01)

    def test_black_has_maximum_contrast(self):
        assert contrast_with_white("#000000") == pytest.approx(21.0, abs=0.01)

    def test_white_has_minimum_contrast(self):
        assert contrast_with_white("#ffffff") == pytest.approx(1.0, abs=0.01)


# ---------------------------------------------------------------------------
# 3 + 4. PUT /api/v1/theme contrast enforcement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestUpdateThemeContrastValidation:
    async def _payload(self, **overrides) -> dict:
        base = ThemeSettings().model_dump()
        base.update(overrides)
        return base

    async def test_rejects_low_contrast_primary_color_with_german_422(
        self, client: AsyncClient, admin_auth_headers: dict, _isolated_theme_storage
    ):
        payload = await self._payload(primary_color="#d97706")

        response = await client.put(THEME_URL, json=payload, headers=admin_auth_headers)

        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "Kontrast" in detail
        assert "4,5:1" in detail
        assert "Hauptfarbe" in detail
        # Rejected before persistence — no theme.json must have been written.
        assert not _isolated_theme_storage.exists()

    async def test_rejects_low_contrast_header_gradient_with_german_422(
        self, client: AsyncClient, admin_auth_headers: dict, _isolated_theme_storage
    ):
        payload = await self._payload(header_gradient_start="#f59e0b")

        response = await client.put(THEME_URL, json=payload, headers=admin_auth_headers)

        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "Header-Verlauf Startfarbe" in detail
        assert not _isolated_theme_storage.exists()

    async def test_reports_every_failing_field_in_one_response(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        payload = await self._payload(
            primary_color="#f59e0b", header_gradient_start="#f59e0b"
        )

        response = await client.put(THEME_URL, json=payload, headers=admin_auth_headers)

        assert response.status_code == 422
        detail = response.json()["detail"]
        assert "Hauptfarbe" in detail
        assert "Header-Verlauf Startfarbe" in detail

    async def test_accepts_and_persists_aa_compliant_colour(
        self, client: AsyncClient, admin_auth_headers: dict, _isolated_theme_storage
    ):
        payload = await self._payload(
            primary_color="#92400e", workshop_name="Test-Werkstatt"
        )

        response = await client.put(THEME_URL, json=payload, headers=admin_auth_headers)

        assert response.status_code == 200
        assert response.json()["primary_color"] == "#92400e"
        assert _isolated_theme_storage.exists()
        saved = json.loads(_isolated_theme_storage.read_text(encoding="utf-8"))
        assert saved["primary_color"] == "#92400e"
        assert saved["workshop_name"] == "Test-Werkstatt"

    async def test_accent_color_and_page_background_are_not_contrast_checked(
        self, client: AsyncClient, admin_auth_headers: dict
    ):
        """accent_color and page_background never carry white text in the
        frontend (useTheme.ts never guards them) — a low-contrast value
        there must not be rejected."""
        payload = await self._payload(accent_color="#ffffff", page_background="#ffffff")

        response = await client.put(THEME_URL, json=payload, headers=admin_auth_headers)

        assert response.status_code == 200


@pytest.mark.asyncio
class TestGetTheme:
    async def test_get_theme_returns_aa_compliant_defaults_when_unconfigured(
        self, client: AsyncClient
    ):
        """GET is public (no auth) and must work before any admin has ever
        configured a theme."""
        response = await client.get(THEME_URL)

        assert response.status_code == 200
        body = response.json()
        assert body["primary_color"] == "#b45309"
        assert body["header_gradient_start"] == "#b45309"
