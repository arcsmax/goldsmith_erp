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
        """A single trailing space must NOT defeat the placeholder check.

        Fixed 2026-09-25: _reject_placeholder_secrets now strips whitespace
        before comparing, so a value one whitespace character away from the
        public placeholder is rejected exactly like the bare placeholder."""
        smuggled = ENV_EXAMPLE_PLACEHOLDER + " "
        assert len(smuggled) >= 32  # passes the length check too

        with pytest.raises(ValidationError, match="(?i)placeholder"):
            Settings(**_prod_kwargs(SECRET_KEY=smuggled))

    def test_lowercased_placeholder_bypasses_rejection(self):
        """Case alone must NOT defeat the placeholder check.

        Fixed 2026-09-25: _reject_placeholder_secrets now case-folds before
        comparing, so a case-insensitive variant of the single most
        obviously-guessable secret in the entire codebase is rejected in
        production, not silently accepted."""
        smuggled = ENV_EXAMPLE_PLACEHOLDER.lower()
        assert len(smuggled) >= 32

        with pytest.raises(ValidationError, match="(?i)placeholder"):
            Settings(**_prod_kwargs(SECRET_KEY=smuggled))

    def test_anonymization_salt_lowercased_placeholder_also_bypasses(self):
        """ANONYMIZATION_SALT has NO length/entropy validator at all (unlike
        SECRET_KEY) — its only protection is _reject_placeholder_secrets'
        match check, so this bypass would otherwise be even more direct.

        Fixed 2026-09-25: the same whitespace/case normalisation covers
        ANONYMIZATION_SALT too, so a lowercased variant of the placeholder
        is rejected in production rather than accepted outright with zero
        strength checking."""
        smuggled = ENV_EXAMPLE_PLACEHOLDER.lower()

        with pytest.raises(ValidationError, match="(?i)placeholder"):
            Settings(**_prod_kwargs(ANONYMIZATION_SALT=smuggled))


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
