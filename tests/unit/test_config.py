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
