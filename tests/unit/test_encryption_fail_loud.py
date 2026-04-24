"""Tests for fix item C4 — encryption must fail loudly on misconfiguration.

Covers:
  1. `check_encryption_configured()` raises when ENCRYPTION_KEY is empty.
  2. `check_encryption_configured()` raises when ENCRYPTION_KEY is malformed.
  3. `check_encryption_configured()` succeeds with a valid Fernet key.
  4. Service-layer `_encrypt_pii` propagates errors instead of silently
     dropping to plaintext when encryption is configured but broken.

CLAUDE.md: "Fail loudly — never swallow exceptions silently." This test
file locks in that contract for the encryption path.
"""

from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from goldsmith_erp.core import encryption as encryption_mod
from goldsmith_erp.core.encryption import (
    EncryptionError,
    check_encryption_configured,
)


@pytest.fixture(autouse=True)
def _reset_encryption_singleton():
    """Ensure no cached EncryptionService leaks between tests in this module."""
    encryption_mod._encryption_service = None
    yield
    encryption_mod._encryption_service = None


class TestCheckEncryptionConfigured:
    def test_raises_on_missing_key(self, monkeypatch):
        """Empty ENCRYPTION_KEY → EncryptionError mentioning the env var."""
        monkeypatch.setattr(encryption_mod.settings, "ENCRYPTION_KEY", "")
        with pytest.raises(EncryptionError, match="ENCRYPTION_KEY"):
            check_encryption_configured()

    def test_raises_on_none_key(self, monkeypatch):
        """Unset (None) ENCRYPTION_KEY → EncryptionError."""
        monkeypatch.setattr(encryption_mod.settings, "ENCRYPTION_KEY", None)
        with pytest.raises(EncryptionError, match="ENCRYPTION_KEY"):
            check_encryption_configured()

    def test_raises_on_malformed_key(self, monkeypatch):
        """Non-Fernet-shaped key string → EncryptionError."""
        monkeypatch.setattr(
            encryption_mod.settings, "ENCRYPTION_KEY", "not-a-valid-fernet-key"
        )
        with pytest.raises(EncryptionError):
            check_encryption_configured()

    def test_succeeds_with_valid_key(self, monkeypatch):
        """A freshly generated Fernet key must satisfy the check."""
        valid_key = Fernet.generate_key().decode()
        monkeypatch.setattr(
            encryption_mod.settings, "ENCRYPTION_KEY", valid_key
        )
        # Should not raise.
        check_encryption_configured()


class TestEncryptPiiFailsLoud:
    """The service-layer `_encrypt_pii` helper MUST NOT silently swallow
    encryption errors. If encryption is configured and a real failure
    occurs, the exception propagates so callers / middleware can decide
    how to respond (503, audit log, etc.)."""

    def test_encrypt_pii_propagates_service_initialisation_error(
        self, monkeypatch
    ):
        """If the encryption service is configured but construction raises,
        `_encrypt_pii` must raise EncryptionError — not silently fall back
        to storing plaintext."""
        from goldsmith_erp.services import customer_service

        # Valid enough to be "configured" (non-empty), but Fernet() will
        # reject it → EncryptionService.__init__ raises EncryptionError.
        monkeypatch.setattr(
            encryption_mod.settings,
            "ENCRYPTION_KEY",
            "bogus-but-nonempty-value",
        )
        encryption_mod._encryption_service = None

        with pytest.raises(EncryptionError):
            customer_service._encrypt_pii({"phone": "+49 123 456789"})

    def test_encrypt_pii_propagates_mid_encrypt_failure(self, monkeypatch):
        """If the cipher is alive but `.encrypt()` blows up (e.g. on a
        pathological input), `_encrypt_pii` must raise, not swallow."""
        from goldsmith_erp.services import customer_service

        valid_key = Fernet.generate_key().decode()
        monkeypatch.setattr(
            encryption_mod.settings, "ENCRYPTION_KEY", valid_key
        )
        encryption_mod._encryption_service = None

        # Install a broken encrypt() on the singleton after first access.
        service = encryption_mod.get_encryption_service()

        def _broken_encrypt(_plaintext):
            raise RuntimeError("cipher backend exploded")

        monkeypatch.setattr(service, "encrypt", _broken_encrypt)

        with pytest.raises(EncryptionError):
            customer_service._encrypt_pii({"phone": "+49 123 456789"})
