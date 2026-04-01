# src/goldsmith_erp/api/routers/admin_email.py
"""
Admin endpoints for email / SMTP configuration.

All endpoints in this module require ADMIN role (enforced by
``get_current_admin_user`` dependency).

Endpoints
---------
GET  /admin/email-config   — return current SMTP settings (password masked)
PUT  /admin/email-config   — update SMTP settings in the running process
POST /admin/email-test     — send a test email to verify SMTP configuration

Design note: SMTP settings are stored in environment variables / .env and
loaded at startup via pydantic-settings. The PUT endpoint mutates the
in-process ``settings`` object. This is acceptable for a single-process
deployment; in a multi-process setup the container would need restarting
after environment changes, which is a known trade-off documented in ADR.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from goldsmith_erp.api.deps import get_current_admin_user
from goldsmith_erp.core.config import settings
from goldsmith_erp.db.models import User as UserModel
from goldsmith_erp.services.email_service import EmailService

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class EmailConfigRead(BaseModel):
    """SMTP configuration returned to the admin UI — password is always masked."""

    smtp_host: Optional[str]
    smtp_port: int
    smtp_user: Optional[str]
    smtp_from: Optional[str]
    email_notifications_enabled: bool
    password_configured: bool  # True if SMTP_PASSWORD is non-empty, never the value


class EmailConfigUpdate(BaseModel):
    """Partial update for SMTP configuration. Omitted fields are left unchanged."""

    smtp_host: Optional[str] = Field(None, description="SMTP relay hostname")
    smtp_port: Optional[int] = Field(
        None, ge=1, le=65535, description="SMTP port (587 = STARTTLS, 465 = TLS)"
    )
    smtp_user: Optional[str] = Field(None, description="SMTP authentication username")
    smtp_password: Optional[str] = Field(
        None, description="SMTP authentication password (write-only)"
    )
    smtp_from: Optional[str] = Field(None, description="Sender address shown to recipients")
    email_notifications_enabled: Optional[bool] = Field(
        None, description="Master switch for all outgoing customer emails"
    )


class EmailTestRequest(BaseModel):
    """Target address for the test email."""

    to: str = Field(..., description="Recipient address for the test message")


class EmailTestResponse(BaseModel):
    success: bool
    message: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/admin/email-config",
    response_model=EmailConfigRead,
    summary="SMTP-Konfiguration abrufen",
    description="Gibt die aktuellen E-Mail-/SMTP-Einstellungen zurück. ADMIN-only.",
)
async def get_email_config(
    _current_user: UserModel = Depends(get_current_admin_user),
) -> EmailConfigRead:
    return EmailConfigRead(
        smtp_host=settings.SMTP_HOST,
        smtp_port=settings.SMTP_PORT,
        smtp_user=settings.SMTP_USER,
        smtp_from=settings.SMTP_FROM,
        email_notifications_enabled=settings.EMAIL_NOTIFICATIONS_ENABLED,
        password_configured=bool(settings.SMTP_PASSWORD),
    )


@router.put(
    "/admin/email-config",
    response_model=EmailConfigRead,
    summary="SMTP-Konfiguration aktualisieren",
    description=(
        "Aktualisiert SMTP-Einstellungen im laufenden Prozess. "
        "Änderungen gelten sofort, sind aber nicht persistent — "
        "bitte auch .env anpassen. ADMIN-only."
    ),
)
async def update_email_config(
    payload: EmailConfigUpdate,
    _current_user: UserModel = Depends(get_current_admin_user),
) -> EmailConfigRead:
    """
    Mutate the in-process settings object so changes take effect immediately
    without a container restart. Callers must also update .env to make the
    changes durable across restarts.
    """
    if payload.smtp_host is not None:
        settings.SMTP_HOST = payload.smtp_host or None  # empty string → None
    if payload.smtp_port is not None:
        settings.SMTP_PORT = payload.smtp_port
    if payload.smtp_user is not None:
        settings.SMTP_USER = payload.smtp_user or None
    if payload.smtp_password is not None:
        settings.SMTP_PASSWORD = payload.smtp_password or None
    if payload.smtp_from is not None:
        settings.SMTP_FROM = payload.smtp_from or None
    if payload.email_notifications_enabled is not None:
        settings.EMAIL_NOTIFICATIONS_ENABLED = payload.email_notifications_enabled

    logger.info(
        "Email configuration updated",
        extra={
            "smtp_host": settings.SMTP_HOST,
            "smtp_port": settings.SMTP_PORT,
            "email_enabled": settings.EMAIL_NOTIFICATIONS_ENABLED,
            # Never log credentials — log only whether they are set.
            "has_user": bool(settings.SMTP_USER),
            "has_password": bool(settings.SMTP_PASSWORD),
        },
    )

    return EmailConfigRead(
        smtp_host=settings.SMTP_HOST,
        smtp_port=settings.SMTP_PORT,
        smtp_user=settings.SMTP_USER,
        smtp_from=settings.SMTP_FROM,
        email_notifications_enabled=settings.EMAIL_NOTIFICATIONS_ENABLED,
        password_configured=bool(settings.SMTP_PASSWORD),
    )


@router.post(
    "/admin/email-test",
    response_model=EmailTestResponse,
    summary="Test-E-Mail senden",
    description=(
        "Versendet eine Test-E-Mail an die angegebene Adresse, um die "
        "SMTP-Konfiguration zu überprüfen. ADMIN-only."
    ),
)
async def send_test_email(
    payload: EmailTestRequest,
    _current_user: UserModel = Depends(get_current_admin_user),
) -> EmailTestResponse:
    """
    Send a diagnostic test email.

    Does NOT require EMAIL_NOTIFICATIONS_ENABLED to be True — the test
    temporarily forces a send attempt so the admin can verify connectivity
    even before enabling the feature globally.
    """
    if not settings.SMTP_HOST:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                "SMTP_HOST ist nicht konfiguriert. "
                "Bitte zuerst die SMTP-Einstellungen speichern."
            ),
        )

    # Build a minimal test email body inline — no template needed.
    html_body = f"""
    <!DOCTYPE html>
    <html lang="de">
    <head><meta charset="UTF-8"><title>Test-E-Mail</title></head>
    <body style="font-family:Arial,sans-serif;color:#2c2416;padding:24px;">
      <h2 style="color:#7c5c1e;">{settings.WORKSHOP_NAME} — Test-E-Mail</h2>
      <p>Diese E-Mail bestätigt, dass Ihre SMTP-Konfiguration korrekt eingerichtet ist.</p>
      <p style="color:#666;font-size:13px;">Versandt von: {settings.SMTP_FROM or 'nicht konfiguriert'}</p>
    </body>
    </html>
    """

    # Temporarily override the enabled flag for this test send.
    original_enabled = settings.EMAIL_NOTIFICATIONS_ENABLED
    settings.EMAIL_NOTIFICATIONS_ENABLED = True
    try:
        sent = await EmailService.send_email(
            to=payload.to,
            subject=f"Test-E-Mail von {settings.WORKSHOP_NAME}",
            html_body=html_body,
        )
    finally:
        settings.EMAIL_NOTIFICATIONS_ENABLED = original_enabled

    if sent:
        return EmailTestResponse(
            success=True,
            message=f"Test-E-Mail erfolgreich an {payload.to} gesendet.",
        )
    return EmailTestResponse(
        success=False,
        message=(
            "E-Mail konnte nicht gesendet werden. "
            "Bitte Backend-Logs auf SMTP-Fehler prüfen."
        ),
    )
