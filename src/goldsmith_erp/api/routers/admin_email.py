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
from fastapi.responses import HTMLResponse
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


# ---------------------------------------------------------------------------
# Email template preview (dry-run — no SMTP required)
# ---------------------------------------------------------------------------

_AVAILABLE_TEMPLATES = [
    "order_confirmed",
    "repair_received",
    "quote_sent",
    "ready_for_pickup",
    "pickup_complete",
    "fitting_reminder",
]


@router.get(
    "/admin/email-preview/{template_name}",
    response_class=HTMLResponse,
    summary="E-Mail-Vorlage als HTML-Vorschau rendern",
    description=(
        "Rendert eine E-Mail-Vorlage mit Beispieldaten und gibt das fertige HTML "
        "zurück, ohne eine E-Mail zu versenden. Nützlich zum Prüfen des Layouts "
        "ohne SMTP-Konfiguration. ADMIN-only.\n\n"
        f"Verfügbare Vorlagen: ``{'``, ``'.join(_AVAILABLE_TEMPLATES)}``"
    ),
    responses={
        200: {"content": {"text/html": {}}, "description": "Rendered HTML email body"},
        404: {"description": "Template not found"},
        422: {"description": "Unknown template name"},
    },
)
async def preview_email_template(
    template_name: str,
    _current_user: UserModel = Depends(get_current_admin_user),
) -> HTMLResponse:
    """
    Render a named email template with sample data.

    When SMTP is not configured this is the primary way admins can verify
    that templates render correctly before going live.  The rendered HTML is
    wrapped in a thin outer document so browsers display it faithfully.

    Parameters
    ----------
    template_name:
        One of the known template stems:
        order_confirmed | repair_received | quote_sent |
        ready_for_pickup | pickup_complete | fitting_reminder
    """
    if template_name not in _AVAILABLE_TEMPLATES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Unbekannte Vorlage '{template_name}'. "
                f"Verfügbar: {', '.join(_AVAILABLE_TEMPLATES)}"
            ),
        )

    try:
        html, subject = EmailService.render_preview(template_name)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

    # Wrap in a minimal chrome so the browser shows it as a stand-alone page
    # and the admin can see the subject line at the top.
    preview_wrapper = f"""<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Vorschau: {template_name}</title>
  <style>
    body {{ margin: 0; font-family: Arial, sans-serif; background: #f5f5f5; }}
    .preview-banner {{
      background: #1e293b; color: #f1f5f9;
      padding: 12px 24px; font-size: 13px;
      display: flex; gap: 24px; align-items: center;
    }}
    .preview-banner strong {{ color: #fbbf24; }}
    .preview-frame {{ padding: 24px; }}
  </style>
</head>
<body>
  <div class="preview-banner">
    <span>Vorlage: <strong>{template_name}</strong></span>
    <span>Betreff: <strong>{subject}</strong></span>
    <span style="margin-left:auto;opacity:0.6;">Nur Vorschau — keine E-Mail wurde versendet</span>
  </div>
  <div class="preview-frame">
    {html}
  </div>
</body>
</html>"""

    logger.info(
        "Email template preview rendered",
        extra={"template": template_name, "admin_id": _current_user.id},
    )
    return HTMLResponse(content=preview_wrapper, status_code=200)
