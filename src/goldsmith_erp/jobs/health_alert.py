"""Out-of-band health alert — email dead-man's-switch (finding 2.6).

Production-readiness.md 2026-07-26, **finding 2.6**. In-app health
notifications are useless when the backend itself is down, so an *external*
watchdog (``scripts/health-watchdog.sh``) curls ``/health`` on a 5-minute
timer and, when it cannot reach it, invokes this module to send an email.

This module is deliberately **import-light**: it imports only the settings
object and ``EmailService`` (SMTP + Jinja, no DB, no FastAPI app). It must run
even when the backend process is dead — either via ``poetry run`` on the host
or via ``podman run --rm --env-file .env <backend-image>``. It never opens a
database session and never initialises the application.

It reuses the backend's own SMTP configuration from ``.env`` (``SMTP_*``,
``EMAIL_NOTIFICATIONS_ENABLED``) via ``EmailService`` — no duplicate SMTP
credentials in the shell. The alert recipient is ``HEALTH_ALERT_EMAIL`` (read
straight from the environment so no new Settings field / migration is needed),
falling back to ``SMTP_FROM``.

Invocation::

    python -m goldsmith_erp.jobs.health_alert --reason "..." [--target URL]

Exit codes:

- ``0`` — the alert email was sent, OR SMTP is unconfigured (documented no-op:
  a workshop may not have SMTP set up yet).
- ``1`` — SMTP *is* configured but the send failed, or a fatal error occurred.
  Surfaced to the watchdog / systemd so a broken alerting path is itself
  visible.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import socket
import sys
from datetime import datetime, timezone
from html import escape
from typing import Optional, Sequence

logger = logging.getLogger("goldsmith_erp.jobs.health_alert")


def _smtp_configured() -> bool:
    """True when EmailService would actually attempt a send.

    Mirrors the guards in ``EmailService.send_email`` so we can distinguish an
    intentional no-op (SMTP not set up) from a real send failure.
    """
    from goldsmith_erp.core.config import settings

    return bool(
        settings.EMAIL_NOTIFICATIONS_ENABLED
        and settings.SMTP_HOST
        and settings.SMTP_FROM
    )


def _recipient() -> Optional[str]:
    """Alert recipient: HEALTH_ALERT_EMAIL env override, else SMTP_FROM."""
    from goldsmith_erp.core.config import settings

    return os.environ.get("HEALTH_ALERT_EMAIL") or settings.SMTP_FROM


async def _send_alert(reason: str, target: str, recipient: str) -> bool:
    """Render + send the outage email. Returns EmailService's bool result."""
    from goldsmith_erp.core.config import settings
    from goldsmith_erp.services.email_service import EmailService

    host = socket.gethostname()
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ")
    workshop = settings.WORKSHOP_NAME

    subject = f"[{workshop}] ALARM: Backend-Health-Check fehlgeschlagen"
    html_body = (
        "<h2>Backend nicht erreichbar</h2>"
        "<p>Der externe Health-Watchdog konnte den Backend-Health-Endpoint "
        "nicht erreichen. Das Backend ist mit hoher Wahrscheinlichkeit "
        "ausgefallen.</p>"
        "<ul>"
        f"<li><b>Zeitpunkt (UTC):</b> {escape(ts)}</li>"
        f"<li><b>Watchdog-Host:</b> {escape(host)}</li>"
        f"<li><b>Ziel-URL:</b> {escape(target)}</li>"
        f"<li><b>Details:</b> {escape(reason)}</li>"
        "</ul>"
        "<p>Bitte den Dienst umgehend prüfen "
        "(<code>podman ps</code> / <code>podman logs</code>).</p>"
    )
    plain_body = (
        f"ALARM: Backend-Health-Check fehlgeschlagen ({workshop})\n\n"
        "Der externe Health-Watchdog konnte den Backend-Health-Endpoint nicht "
        "erreichen. Das Backend ist mit hoher Wahrscheinlichkeit ausgefallen.\n\n"
        f"Zeitpunkt (UTC): {ts}\n"
        f"Watchdog-Host:   {host}\n"
        f"Ziel-URL:        {target}\n"
        f"Details:         {reason}\n\n"
        "Bitte den Dienst umgehend prüfen (podman ps / podman logs)."
    )
    return await EmailService.send_email(
        to=recipient,
        subject=subject,
        html_body=html_body,
        plain_body=plain_body,
    )


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m goldsmith_erp.jobs.health_alert",
        description=(
            "Send an out-of-band email alert that the backend /health endpoint "
            "is unreachable. Import-light: no DB, no app. Reuses the backend "
            "SMTP config from .env."
        ),
    )
    parser.add_argument(
        "--reason",
        default="Backend /health endpoint unreachable.",
        help="Human-readable failure detail for the email body.",
    )
    parser.add_argument(
        "--target",
        default=os.environ.get("HEALTH_URL", "http://localhost:8000/health"),
        help="The health URL that was probed (for the email body).",
    )
    return parser.parse_args(list(argv))


async def run(args: argparse.Namespace) -> int:
    """Async core of the CLI. Returns the process exit code.

    Kept separate from :func:`main` so tests can ``await`` it inside an
    existing event loop — calling ``asyncio.run`` from a test poisons
    pytest-asyncio's session-scoped loop for every async test collected
    after it (the same trap ``jobs/gdpr_cleanup`` documents on its
    ``_report_exit_code`` helper).
    """
    try:
        if not _smtp_configured():
            logger.warning(
                "Health alert requested but SMTP is not configured "
                "(EMAIL_NOTIFICATIONS_ENABLED / SMTP_HOST / SMTP_FROM). "
                "Logging and exiting 0 (documented no-op). reason=%s target=%s",
                args.reason,
                args.target,
            )
            return 0

        recipient = _recipient()
        if not recipient:
            logger.warning(
                "SMTP is configured but no alert recipient resolved "
                "(HEALTH_ALERT_EMAIL / SMTP_FROM). No-op exit 0."
            )
            return 0

        sent = await _send_alert(args.reason, args.target, recipient)
        if sent:
            logger.info("Health alert email dispatched (target=%s)", args.target)
            return 0

        logger.error(
            "Health alert email FAILED to send although SMTP is configured "
            "(target=%s)",
            args.target,
        )
        return 1
    except Exception:  # noqa: BLE001 — top-level guard: log + nonzero exit
        logger.error("Health alert crashed before completing", exc_info=True)
        return 1


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entry point. Returns the process exit code (0 ok/no-op, 1 send failed)."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    return asyncio.run(run(args))


if __name__ == "__main__":
    sys.exit(main())
