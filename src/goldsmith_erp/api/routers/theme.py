"""
Theme configuration router.

Allows an ADMIN to customise brand colours and the workshop name.
Settings are persisted as JSON at uploads/theme.json so no database
migration is needed and the file survives container restarts as long
as the uploads directory is on a persistent volume.

Public endpoints (no auth) — GET /api/v1/theme
  Needed by the login page and the useTheme hook before a user logs in.

Protected endpoints (ADMIN only) — PUT /api/v1/theme
  Validated and written atomically (write-then-rename) to avoid
  partially-written files being read by concurrent requests.
"""

import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from goldsmith_erp.api.deps import get_current_user
from goldsmith_erp.core.config import settings
from goldsmith_erp.core.permissions import Permission, require_permission  # noqa: F401
from goldsmith_erp.db.models import User

logger = logging.getLogger(__name__)

router = APIRouter()

# ─── Storage ─────────────────────────────────────────────────────────────────

# Resolve theme file path relative to the project uploads directory.
# UPLOAD_DIR comes from settings (defaults to "uploads/").
_UPLOADS_DIR = Path(getattr(settings, "UPLOAD_DIR", "uploads"))
_THEME_FILE = _UPLOADS_DIR / "theme.json"


# ─── Pydantic schemas ─────────────────────────────────────────────────────────


class ThemeSettings(BaseModel):
    """Complete theme settings — returned by GET, accepted by PUT."""

    # Design tokens phase 1 (W4-01): #d97706 carries white text at only a
    # 3.19:1 contrast ratio, below WCAG AA's 4.5:1 minimum for normal text.
    # #b45309 (5.02:1) is the same swatch the frontend defaults to — see
    # frontend/src/hooks/useTheme.ts and styles/brand-tokens.css.
    primary_color: str = Field(
        default="#b45309",
        description="Hauptfarbe (CSS hex, z. B. #b45309)",
        pattern=r"^#[0-9a-fA-F]{6}$",
    )
    primary_dark: str = Field(
        default="#92400e",
        description="Dunkle Variante der Hauptfarbe",
        pattern=r"^#[0-9a-fA-F]{6}$",
    )
    header_gradient_start: str = Field(
        default="#b45309",
        description="Header-Verlauf Startfarbe",
        pattern=r"^#[0-9a-fA-F]{6}$",
    )
    header_gradient_end: str = Field(
        default="#92400e",
        description="Header-Verlauf Endfarbe",
        pattern=r"^#[0-9a-fA-F]{6}$",
    )
    accent_color: str = Field(
        default="#f59e0b",
        description="Akzentfarbe fuer interaktive Elemente",
        pattern=r"^#[0-9a-fA-F]{6}$",
    )
    page_background: str = Field(
        default="#faf8f4",
        description="Seitenhintergrundfarbe",
        pattern=r"^#[0-9a-fA-F]{6}$",
    )
    workshop_name: str = Field(
        default="Goldschmiede Werkstatt",
        max_length=100,
        description="Name der Werkstatt — wird im Header angezeigt",
    )
    logo_url: Optional[str] = Field(
        default=None,
        max_length=512,
        description="URL zum Werkstatt-Logo (optional)",
    )


# ─── Helpers ──────────────────────────────────────────────────────────────────

_DEFAULTS = ThemeSettings()

# WCAG AA minimum contrast ratio for normal-size text (mirrors
# frontend/src/hooks/useTheme.ts's MIN_TEXT_CONTRAST so both layers agree).
_MIN_TEXT_CONTRAST = 4.5

# The theme fields that render white text on top of them (buttons, header
# gradient) — see useTheme.ts's setTextBearingColour(). Every other field
# (accent_color, page_background) is not text-bearing and is not checked.
_TEXT_BEARING_FIELDS: tuple[str, ...] = (
    "primary_color",
    "primary_dark",
    "header_gradient_start",
    "header_gradient_end",
)

_FIELD_LABELS_DE: dict[str, str] = {
    "primary_color": "Hauptfarbe",
    "primary_dark": "Dunkle Variante der Hauptfarbe",
    "header_gradient_start": "Header-Verlauf Startfarbe",
    "header_gradient_end": "Header-Verlauf Endfarbe",
}


def _relative_luminance(hex_color: str) -> float:
    """WCAG relative luminance of a #rrggbb colour (sRGB, gamma-corrected).

    Mirrors frontend/src/hooks/useTheme.ts's relativeLuminance() exactly so
    both layers agree on which colours pass.
    """
    hex_digits = hex_color.lstrip("#")

    def channel(offset: int) -> float:
        c = int(hex_digits[offset : offset + 2], 16) / 255
        return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4

    return 0.2126 * channel(0) + 0.7152 * channel(2) + 0.0722 * channel(4)


def contrast_with_white(hex_color: str) -> float:
    """Contrast ratio of white text on `hex_color` (WCAG 2.x)."""
    return 1.05 / (_relative_luminance(hex_color) + 0.05)


def _find_low_contrast_fields(theme: ThemeSettings) -> list[str]:
    """Return the text-bearing field names whose contrast with white text
    falls below the WCAG AA minimum."""
    return [
        field_name
        for field_name in _TEXT_BEARING_FIELDS
        if contrast_with_white(getattr(theme, field_name)) < _MIN_TEXT_CONTRAST
    ]


def _load_theme() -> ThemeSettings:
    """Read theme.json; return defaults if the file is missing or corrupt."""
    try:
        if _THEME_FILE.exists():
            raw = _THEME_FILE.read_text(encoding="utf-8")
            data = json.loads(raw)
            return ThemeSettings(**data)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Could not read theme file — using defaults",
            extra={"path": str(_THEME_FILE), "error": str(exc)},
        )
    return ThemeSettings()


def _save_theme(theme: ThemeSettings) -> None:
    """Persist theme atomically using write-then-rename."""
    _UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

    payload = theme.model_dump()
    fd, tmp_path = tempfile.mkstemp(
        dir=str(_UPLOADS_DIR), prefix="theme_", suffix=".json"
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, str(_THEME_FILE))
        logger.info(
            "Theme settings saved",
            extra={"path": str(_THEME_FILE), "workshop_name": theme.workshop_name},
        )
    except Exception:
        # Clean up temp file on failure
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.get(
    "/theme",
    response_model=ThemeSettings,
    summary="Aktuelle Theme-Einstellungen abrufen (oeffentlich)",
)
async def get_theme() -> ThemeSettings:
    """
    Returns the current theme settings.

    This endpoint is intentionally public — the frontend needs to apply
    brand colours before a user has logged in (login page styling, etc.).
    """
    return _load_theme()


@router.put(
    "/theme",
    response_model=ThemeSettings,
    summary="Theme-Einstellungen aktualisieren (nur ADMIN)",
)
@require_permission(Permission.SYSTEM_CONFIG)
async def update_theme(
    payload: ThemeSettings,
    current_user: User = Depends(get_current_user),
) -> ThemeSettings:
    """
    Replaces all theme settings.

    Only users with the ADMIN role may call this endpoint.
    The new settings are validated by Pydantic before being persisted, and
    every text-bearing colour (primary_color, primary_dark,
    header_gradient_start, header_gradient_end) must meet the WCAG AA
    minimum contrast ratio (4.5:1) against white text — the frontend already
    silently drops a failing colour and falls back to the default token
    (useTheme.ts's setTextBearingColour), so the backend rejects it outright
    instead of persisting a value the UI would never actually apply.
    """
    low_contrast_fields = _find_low_contrast_fields(payload)
    if low_contrast_fields:
        details = "; ".join(
            f"{_FIELD_LABELS_DE[field_name]} ({getattr(payload, field_name)}, "
            f"Kontrast {contrast_with_white(getattr(payload, field_name)):.2f}:1)"
            for field_name in low_contrast_fields
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "Folgende Farben erfüllen nicht den WCAG-AA-Mindestkontrast von "
                f"4,5:1 mit weißer Schrift: {details}."
            ),
        )

    try:
        _save_theme(payload)
    except OSError as exc:
        logger.error(
            "Failed to save theme",
            extra={"error": str(exc), "user_id": current_user.id},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Theme-Einstellungen konnten nicht gespeichert werden.",
        ) from exc

    return payload
