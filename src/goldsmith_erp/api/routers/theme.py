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

    primary_color: str = Field(
        default="#d97706",
        description="Hauptfarbe (CSS hex, z. B. #d97706)",
        pattern=r"^#[0-9a-fA-F]{6}$",
    )
    primary_dark: str = Field(
        default="#92400e",
        description="Dunkle Variante der Hauptfarbe",
        pattern=r"^#[0-9a-fA-F]{6}$",
    )
    header_gradient_start: str = Field(
        default="#d97706",
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
    The new settings are validated by Pydantic before being persisted.
    """
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
