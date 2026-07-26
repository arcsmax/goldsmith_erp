"""Unit tests for the out-of-band health-alert CLI (finding 2.6).

Verifies the two contractual behaviours:
  * SMTP unconfigured  → log + exit 0 (documented no-op; no send attempted).
  * SMTP configured     → send via EmailService; exit 0 on success, 1 on failure.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from goldsmith_erp.jobs import health_alert


@pytest.fixture
def smtp_settings(monkeypatch):
    """Return a callable that flips the SMTP-related settings for a test."""
    from goldsmith_erp.core.config import settings

    def _configure(*, enabled: bool, host: str | None, sender: str | None):
        monkeypatch.setattr(settings, "EMAIL_NOTIFICATIONS_ENABLED", enabled)
        monkeypatch.setattr(settings, "SMTP_HOST", host)
        monkeypatch.setattr(settings, "SMTP_FROM", sender)

    return _configure


def test_smtp_configured_false_when_disabled(smtp_settings):
    smtp_settings(enabled=False, host="smtp.example.com", sender="from@example.com")
    assert health_alert._smtp_configured() is False


def test_smtp_configured_true_when_all_present(smtp_settings):
    smtp_settings(enabled=True, host="smtp.example.com", sender="from@example.com")
    assert health_alert._smtp_configured() is True


def test_recipient_prefers_env_override(smtp_settings, monkeypatch):
    smtp_settings(enabled=True, host="smtp.example.com", sender="from@example.com")
    monkeypatch.setenv("HEALTH_ALERT_EMAIL", "ops@example.com")
    assert health_alert._recipient() == "ops@example.com"


def test_recipient_falls_back_to_smtp_from(smtp_settings, monkeypatch):
    smtp_settings(enabled=True, host="smtp.example.com", sender="from@example.com")
    monkeypatch.delenv("HEALTH_ALERT_EMAIL", raising=False)
    assert health_alert._recipient() == "from@example.com"


# NOTE: these three exercise the CLI logic via the awaitable ``run(args)``
# core, NOT via ``main()`` — main() calls ``asyncio.run``, which closes the
# current event loop and poisons pytest-asyncio's session-scoped loop for
# every async test collected after this file (broke 389 tests in the full
# suite on 2026-07-26). main() itself is a thin parse+asyncio.run wrapper.


async def test_run_noop_when_smtp_unconfigured(smtp_settings, monkeypatch):
    """No SMTP → exit 0 and EmailService is never invoked (no send attempt)."""
    smtp_settings(enabled=False, host=None, sender=None)
    send_spy = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "goldsmith_erp.services.email_service.EmailService.send_email", send_spy
    )

    args = health_alert._parse_args(["--reason", "test", "--target", "http://x/health"])
    rc = await health_alert.run(args)

    assert rc == 0
    send_spy.assert_not_called()


async def test_run_exits_zero_on_successful_send(smtp_settings, monkeypatch):
    smtp_settings(enabled=True, host="smtp.example.com", sender="from@example.com")
    monkeypatch.delenv("HEALTH_ALERT_EMAIL", raising=False)
    send_mock = AsyncMock(return_value=True)
    monkeypatch.setattr(
        "goldsmith_erp.services.email_service.EmailService.send_email", send_mock
    )

    args = health_alert._parse_args(["--reason", "boom", "--target", "http://x/health"])
    rc = await health_alert.run(args)

    assert rc == 0
    send_mock.assert_awaited_once()
    kwargs = send_mock.await_args.kwargs
    assert kwargs["to"] == "from@example.com"
    assert "ALARM" in kwargs["subject"]
    # PII/other note: reason is echoed into the body; that is operator text.
    assert "boom" in kwargs["plain_body"]


async def test_run_exits_one_when_configured_send_fails(smtp_settings, monkeypatch):
    smtp_settings(enabled=True, host="smtp.example.com", sender="from@example.com")
    monkeypatch.delenv("HEALTH_ALERT_EMAIL", raising=False)
    send_mock = AsyncMock(return_value=False)  # SMTP up but send rejected
    monkeypatch.setattr(
        "goldsmith_erp.services.email_service.EmailService.send_email", send_mock
    )

    args = health_alert._parse_args(["--reason", "boom", "--target", "http://x/health"])
    rc = await health_alert.run(args)

    assert rc == 1
    send_mock.assert_awaited_once()
