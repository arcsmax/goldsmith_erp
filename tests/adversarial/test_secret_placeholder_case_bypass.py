"""
B1 — Adversarial tests for SEC-02 (core/config.py placeholder rejection).

Target: Settings._reject_placeholder_secrets, Settings.validate_secret_key
(audit 2026-09-25, docs/technical/security/2026-09-AUDIT-FIXES-W1.md).

_reject_placeholder_secrets does an EXACT string equality check against the
literal ENV_EXAMPLE_PLACEHOLDER. validate_secret_key's "known insecure
defaults" list is likewise a small set of exact (lowercased) strings, none of
which is the actual placeholder. Neither check normalises whitespace or case.
"""

import pytest
from pydantic import ValidationError

from goldsmith_erp.core.config import ENV_EXAMPLE_PLACEHOLDER, Settings

STRONG_SECRET = "aZ9kQ2mNbV7xP4rT8wL3jF5yH6sD1cE0uG2iO5pR8tW4qX7vY3zK9jM2nB6cF"


def _prod_kwargs(**overrides) -> dict:
    """Kwargs that satisfy every other production validator (mirrors
    tests/unit/test_config.py::_prod_kwargs so this file is runnable
    standalone)."""
    kwargs: dict = dict(
        _env_file=None,
        DEBUG=False,
        SECRET_KEY=STRONG_SECRET,
        ENCRYPTION_KEY="test-encryption-key-not-a-real-fernet-key",
        ANONYMIZATION_SALT="a-non-empty-test-salt-value",
        COOKIE_SECURE=True,
    )
    kwargs.update(overrides)
    return kwargs


class TestSecretKeyPlaceholderBypass:
    def test_exact_placeholder_is_rejected_baseline(self):
        """Sanity check: the exact placeholder is still rejected (SEC-02
        works for the literal string)."""
        with pytest.raises(ValidationError):
            Settings(**_prod_kwargs(SECRET_KEY=ENV_EXAMPLE_PLACEHOLDER))

    def test_placeholder_with_trailing_whitespace_bypasses_rejection(self):
        """A single trailing space defeats the exact-match placeholder
        check in _reject_placeholder_secrets AND is not in
        validate_secret_key's insecure_values list (also exact-match), so a
        production deployment boots with a publicly-known, guessable
        SECRET_KEY."""
        smuggled = ENV_EXAMPLE_PLACEHOLDER + " "
        assert len(smuggled) >= 32  # passes the length check too

        settings = Settings(**_prod_kwargs(SECRET_KEY=smuggled))

        # BUG: this should have raised ValidationError, exactly like the
        # bare placeholder does above. Instead production boots with a
        # value one whitespace character away from the public placeholder.
        assert settings.SECRET_KEY != smuggled, (
            "SEC-02 bypass: SECRET_KEY = ENV_EXAMPLE_PLACEHOLDER + ' ' "
            "booted with DEBUG=False. "
            "src/goldsmith_erp/core/config.py Settings._reject_placeholder_secrets "
            "does exact string equality only "
            "(getattr(self, name) == ENV_EXAMPLE_PLACEHOLDER) and "
            "Settings.validate_secret_key's insecure_values check is also "
            "exact-match, so a trivially-guessable near-placeholder secret "
            "is accepted in production."
        )

    def test_lowercased_placeholder_bypasses_rejection(self):
        """Case alone defeats both checks: _reject_placeholder_secrets does
        `==` against the uppercase literal, and validate_secret_key's
        insecure_values list contains a DIFFERENT (shorter) lowercase
        string, not this placeholder lowercased. A case-insensitive
        variant of the single most obviously-guessable secret in the
        entire codebase boots successfully in production."""
        smuggled = ENV_EXAMPLE_PLACEHOLDER.lower()
        assert len(smuggled) >= 32

        settings = Settings(**_prod_kwargs(SECRET_KEY=smuggled))

        assert settings.SECRET_KEY != smuggled, (
            "SEC-02 bypass: SECRET_KEY = ENV_EXAMPLE_PLACEHOLDER.lower() "
            "booted with DEBUG=False — a case-insensitive variant of the "
            "public .env.example placeholder is accepted as a 'secure' "
            "production secret. CRITICAL: anyone who has read the public "
            "repository's .env.example can forge admin JWTs against any "
            "installation that made this trivial casing mistake."
        )

    def test_anonymization_salt_lowercased_placeholder_also_bypasses(self):
        """ANONYMIZATION_SALT has NO length/entropy validator at all (unlike
        SECRET_KEY) — its only protection is _reject_placeholder_secrets'
        exact-match check, so this bypass is even more direct: any
        non-exact variant of the placeholder, including a lowercased one,
        is accepted outright with zero strength checking."""
        smuggled = ENV_EXAMPLE_PLACEHOLDER.lower()

        settings = Settings(**_prod_kwargs(ANONYMIZATION_SALT=smuggled))

        assert settings.ANONYMIZATION_SALT != smuggled, (
            "SEC-02 bypass: ANONYMIZATION_SALT = ENV_EXAMPLE_PLACEHOLDER.lower() "
            "booted with DEBUG=False. Since erasure-tracking HMACs are keyed "
            "on this salt, an installation that makes this casing mistake "
            "has its GDPR Art. 17 tracking tokens recomputable by anyone "
            "who knows the public placeholder."
        )


class TestSecretKeyLengthValidatorRegression:
    """Confirms the always-on length floor still works (should PASS)."""

    def test_31_char_secret_key_rejected_even_in_debug(self):
        thirty_one = "a" * 31
        with pytest.raises(ValidationError):
            Settings(_env_file=None, DEBUG=True, SECRET_KEY=thirty_one)

    def test_32_char_secret_key_accepted(self):
        thirty_two = "aB3" * 10 + "xy"  # 32 chars, decent diversity
        assert len(thirty_two) == 32
        settings = Settings(**_prod_kwargs(SECRET_KEY=thirty_two))
        assert settings.SECRET_KEY == thirty_two
