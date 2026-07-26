"""Unit tests for core.config.Settings validators.

Focused on the SECRET_KEY validator: must accept the .env.example placeholder
with a WARNING (so fresh `make start` boots out of the box), but hard-reject
empty values and other insecure defaults.
"""

import logging

import pytest
from pydantic import ValidationError

from goldsmith_erp.core.config import Settings


class TestSecretKeyValidator:
    """SECRET_KEY must remain accept-the-placeholder-but-warn-on-boot, and
    hard-reject empty / known-insecure values so a typo never ships."""

    def test_settings_accepts_env_example_secret_key_with_warning(self, caplog):
        """The .env.example placeholder should NOT raise — fresh checkouts
        boot. A WARNING must surface so a real deployment can't miss it."""
        placeholder = "CHANGE_THIS_TO_A_SECURE_RANDOM_STRING_AT_LEAST_32_CHARS"

        with caplog.at_level(logging.WARNING, logger="goldsmith_erp.core.config"):
            settings = Settings(SECRET_KEY=placeholder)

        # Value preserved (we return v, don't mangle it)
        assert settings.SECRET_KEY == placeholder

        # At least one WARNING mentions SECRET_KEY so operators see it
        warnings = [
            r
            for r in caplog.records
            if r.levelno == logging.WARNING and "SECRET_KEY" in r.getMessage()
        ]
        assert warnings, (
            "Expected a WARNING log mentioning SECRET_KEY when the .env.example "
            "placeholder is used; got none."
        )

    def test_settings_rejects_empty_secret_key(self):
        """Empty SECRET_KEY is never acceptable — even on dev — and must
        raise so the operator sees the error at startup, not at first JWT."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(SECRET_KEY="")

        # Pydantic wraps the underlying ValueError; the message must reference
        # SECRET_KEY so the operator knows which field to fix.
        assert "SECRET_KEY" in str(exc_info.value)

    @pytest.mark.parametrize(
        "insecure_value",
        [
            "secret",
            "secretkey",
            "your-secret-key",
            "mysecretkey",
            "changeme",
            "password",
            "secret123",
            "supersecret",
            "change_this_to_a_secure_random_string",  # was on the original list
        ],
    )
    def test_settings_rejects_known_insecure_defaults(self, insecure_value):
        """Known insecure defaults must hard-reject. Regression net for the
        original insecure_values list."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(SECRET_KEY=insecure_value)
        assert "SECRET_KEY" in str(exc_info.value)

    def test_settings_rejects_short_secret_key(self):
        """Below the 32-char minimum — even if the value isn't a known
        default — must reject."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(SECRET_KEY="a" * 31)  # 31 chars
        assert "SECRET_KEY" in str(exc_info.value)

    def test_settings_accepts_strong_secret_key(self):
        """A sufficiently long, non-placeholder, high-entropy SECRET_KEY
        must be accepted with no warning."""
        # 64-char key, multiple unique chars — passes the entropy check.
        strong = "aZ9kQ2mNbV7xP4rT8wL3jF5yH6sD1cE0uG2iO5pR8tW4qX7vY3zK9jM2nB6cF"

        settings = Settings(SECRET_KEY=strong)
        assert settings.SECRET_KEY == strong


# ── BACKEND_CORS_ORIGINS parsing (Tier 0 finding 0.1, 2026-07-26 review) ──────
# setup.sh wrote comma-separated origins while the field was list[str];
# NoDecode + before-validator now accept JSON arrays and comma-separated strings.


@pytest.fixture(autouse=True)
def _debug_env(monkeypatch):
    """DEBUG=true so the production-only model validators (ENCRYPTION_KEY,
    ANONYMIZATION_SALT) warn instead of raising while we exercise CORS parsing.
    """
    monkeypatch.setenv("DEBUG", "true")


class TestBackendCorsOriginsFromEnv:
    """Environment-variable path — the one that crashed in production."""

    def test_json_array_string_parses(self, monkeypatch):
        # Arrange — the form setup.sh now writes into .env.production.
        monkeypatch.setenv(
            "BACKEND_CORS_ORIGINS",
            '["http://localhost:3000","http://127.0.0.1:3000",'
            '"http://192.168.1.5:3000"]',
        )

        # Act
        settings = Settings()

        # Assert
        assert settings.BACKEND_CORS_ORIGINS == [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://192.168.1.5:3000",
        ]

    def test_comma_separated_string_parses(self, monkeypatch):
        # Arrange — the legacy form; must load instead of raising SettingsError.
        monkeypatch.setenv(
            "BACKEND_CORS_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000",
        )

        # Act
        settings = Settings()

        # Assert
        assert settings.BACKEND_CORS_ORIGINS == [
            "http://localhost:3000",
            "http://127.0.0.1:3000",
        ]

    def test_comma_separated_with_whitespace_is_trimmed(self, monkeypatch):
        monkeypatch.setenv(
            "BACKEND_CORS_ORIGINS",
            " http://localhost:3000 , http://example.test ",
        )

        settings = Settings()

        assert settings.BACKEND_CORS_ORIGINS == [
            "http://localhost:3000",
            "http://example.test",
        ]

    def test_single_origin_string(self, monkeypatch):
        monkeypatch.setenv("BACKEND_CORS_ORIGINS", "http://localhost:3000")

        settings = Settings()

        assert settings.BACKEND_CORS_ORIGINS == ["http://localhost:3000"]

    def test_empty_string_yields_empty_list(self, monkeypatch):
        monkeypatch.setenv("BACKEND_CORS_ORIGINS", "")

        settings = Settings()

        assert settings.BACKEND_CORS_ORIGINS == []

    def test_default_applies_when_unset(self, monkeypatch):
        monkeypatch.delenv("BACKEND_CORS_ORIGINS", raising=False)

        settings = Settings()

        assert settings.BACKEND_CORS_ORIGINS == [
            "http://localhost:3000",
            "http://localhost:8000",
        ]


class TestBackendCorsOriginsFromKwarg:
    """Constructor path — validator must also handle direct kwargs."""

    def test_real_list_passes_through(self):
        settings = Settings(BACKEND_CORS_ORIGINS=["http://a.test", "http://b.test"])

        assert settings.BACKEND_CORS_ORIGINS == ["http://a.test", "http://b.test"]

    def test_comma_separated_kwarg_parses(self):
        settings = Settings(BACKEND_CORS_ORIGINS="http://a.test,http://b.test")

        assert settings.BACKEND_CORS_ORIGINS == ["http://a.test", "http://b.test"]


# ── COOKIE_SECURE production validator (Tier 1 finding 1.1, 2026-07-26 review) ─
# Credentials + the HttpOnly auth cookie must not cross the LAN in cleartext.
# The auth router sets the cookie with secure=settings.COOKIE_SECURE, so
# production (DEBUG=False) must enforce COOKIE_SECURE=True — mirroring the
# ENCRYPTION_KEY / ANONYMIZATION_SALT / SMTP fail-fast validators.
#
# The autouse `_debug_env` fixture above sets DEBUG=true in the environment;
# these tests pass DEBUG explicitly as an init kwarg, which outranks env vars
# in pydantic-settings, so the production path is exercised deterministically.


def _prod_cookie_kwargs(**overrides) -> dict:
    """Baseline kwargs that satisfy the ENCRYPTION_KEY / ANONYMIZATION_SALT
    production validators (they run before the cookie check), so only the
    COOKIE_SECURE validator under test decides pass/fail.

    ENCRYPTION_KEY's validator is a truthiness check, so any non-empty value
    is sufficient here — no real Fernet key needed.
    """
    kwargs: dict = dict(
        ENCRYPTION_KEY="test-encryption-key-not-a-real-fernet-key",
        ANONYMIZATION_SALT="a-non-empty-test-salt-value",
    )
    kwargs.update(overrides)
    return kwargs


class TestCookieSecureValidator:
    """DEBUG=False must require COOKIE_SECURE=True; DEBUG=True stays permissive."""

    def test_prod_without_cookie_secure_raises_helpful_message(self):
        """DEBUG=False + COOKIE_SECURE=False must fail loudly at startup with a
        message that names the field and points at the fix (TLS + set true)."""
        with pytest.raises(ValidationError) as exc_info:
            Settings(**_prod_cookie_kwargs(DEBUG=False, COOKIE_SECURE=False))

        message = str(exc_info.value)
        assert "COOKIE_SECURE" in message, (
            "The production error must name COOKIE_SECURE so the operator knows "
            "which setting to fix."
        )
        # Actionable: the message tells the operator what to do (set it true).
        assert "true" in message.lower()

    def test_prod_with_cookie_secure_passes(self):
        """DEBUG=False + COOKIE_SECURE=True is the correct production config and
        must construct without raising (other prod validators satisfied)."""
        settings = Settings(**_prod_cookie_kwargs(DEBUG=False, COOKIE_SECURE=True))

        assert settings.COOKIE_SECURE is True
        assert settings.DEBUG is False

    def test_dev_without_cookie_secure_is_allowed(self):
        """DEBUG=True + COOKIE_SECURE=False must stay allowed — local/dev over
        plain HTTP has no TLS to mark the cookie against."""
        settings = Settings(DEBUG=True, COOKIE_SECURE=False)

        assert settings.COOKIE_SECURE is False
        assert settings.DEBUG is True
