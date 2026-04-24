"""Unit tests for the EncryptedString TypeDecorator + HMAC blind-index helper.

Fix item **C1** — foundational PII encryption infrastructure.

These tests lock in the contract that ``EncryptedString`` round-trips any
string value through Fernet at the ORM layer and that ``hmac_blind_index``
produces a deterministic, non-reversible tag suitable for equality-search
over ciphertext columns.

Scope
-----
- ``EncryptedString`` (SQLAlchemy TypeDecorator) — unit-only, no DB bind.
- ``hmac_blind_index()`` — deterministic, 64-char hex, normalised input.

The key is set via ``monkeypatch.setenv`` + a fresh singleton reset so the
module-level test harness never inherits the runtime key. See
``test_customer_pii_encryption.py`` for the DB-round-trip integration test.
"""

from __future__ import annotations

import os

import pytest
from cryptography.fernet import Fernet


# ---------------------------------------------------------------------------
# Environment priming — done BEFORE we import the modules under test so the
# singleton cipher sees a valid key on first construction.
# ---------------------------------------------------------------------------

_TEST_KEY = Fernet.generate_key().decode("utf-8")
os.environ.setdefault("ENCRYPTION_KEY", _TEST_KEY)
os.environ.setdefault("DEBUG", "true")
os.environ.setdefault("ANONYMIZATION_SALT", "abcdefghijklmnop")
os.environ.setdefault(
    "SECRET_KEY",
    "abcdefghijklmnopqrstuvwxyz0123456789ABCDEF0123",
)
os.environ.setdefault("POSTGRES_PASSWORD", "test")


from goldsmith_erp.core import encryption as encryption_mod  # noqa: E402
from goldsmith_erp.core.encryption import hmac_blind_index  # noqa: E402
from goldsmith_erp.db.types import EncryptedString  # noqa: E402


@pytest.fixture(autouse=True)
def _force_valid_key(monkeypatch):
    """Ensure every test in this module operates under a fresh valid key.

    We also reset the singleton so a test that changed the key doesn't bleed
    a stale cipher into the next test.
    """
    key = _TEST_KEY
    monkeypatch.setattr(encryption_mod.settings, "ENCRYPTION_KEY", key)
    # Refresh the derived blind-index key too so hmac_blind_index sees the
    # current ENCRYPTION_KEY value, not whatever was cached at import.
    monkeypatch.setattr(
        encryption_mod,
        "_BLIND_INDEX_KEY",
        encryption_mod._derive_blind_index_key(),
    )
    encryption_mod._encryption_service = None
    yield
    encryption_mod._encryption_service = None


class TestEncryptedString:
    """Round-trip contract for the TypeDecorator."""

    def test_round_trip(self):
        """Bind → result must return the original plaintext."""
        col = EncryptedString()
        ciphertext = col.process_bind_param("alice@example.com", None)
        assert ciphertext != "alice@example.com"  # not plaintext
        plaintext = col.process_result_value(ciphertext, None)
        assert plaintext == "alice@example.com"

    def test_non_deterministic(self):
        """Fernet is non-deterministic; same input → different ciphertext."""
        col = EncryptedString()
        c1 = col.process_bind_param("alice@example.com", None)
        c2 = col.process_bind_param("alice@example.com", None)
        assert c1 != c2  # different ciphertexts
        # …but both decrypt to the same plaintext.
        assert col.process_result_value(c1, None) == "alice@example.com"
        assert col.process_result_value(c2, None) == "alice@example.com"

    def test_none_passes_through(self):
        """NULL values must round-trip unchanged without raising."""
        col = EncryptedString()
        assert col.process_bind_param(None, None) is None
        assert col.process_result_value(None, None) is None

    def test_empty_string_passes_through_as_none(self):
        """Empty strings map to NULL (parity with the service-layer helper)."""
        col = EncryptedString()
        # Either None or "" is acceptable for storage; the round-trip must
        # not yield a ciphertext that decrypts to a non-empty value.
        stored = col.process_bind_param("", None)
        if stored is not None:
            assert col.process_result_value(stored, None) == ""

    def test_ciphertext_looks_like_fernet_token(self):
        """Stored ciphertext is url-safe base64 (Fernet contract)."""
        col = EncryptedString()
        ciphertext = col.process_bind_param("hello world", None)
        # Fernet tokens begin with gAAAAA… (version byte 0x80 + timestamp).
        assert ciphertext.startswith("gAAAAA")
        # Tokens are significantly longer than the plaintext.
        assert len(ciphertext) > len("hello world") * 2

    def test_legacy_plaintext_tolerated_on_read(self):
        """Reading a row that was written BEFORE encryption was enabled
        (i.e. raw plaintext in the column) must not blow up — it should
        return the value as-is so mixed-state tables stay readable during
        migration. This is the same tolerance the service-layer
        ``_decrypt_pii`` helper already provides.
        """
        col = EncryptedString()
        # "not-a-fernet-token" is not valid base64-encoded ciphertext. The
        # TypeDecorator must not throw on read; it must treat it as legacy
        # plaintext.
        result = col.process_result_value("legacy-plaintext-value", None)
        assert result == "legacy-plaintext-value"


class TestHmacBlindIndex:
    """Deterministic keyed hash — same input → same output, not reversible."""

    def test_deterministic(self):
        """Two calls with the same input produce the same tag."""
        h1 = hmac_blind_index("alice@example.com")
        h2 = hmac_blind_index("alice@example.com")
        assert h1 == h2

    def test_different_inputs_different_hashes(self):
        """Distinct inputs must produce distinct tags."""
        assert hmac_blind_index("alice@example.com") != hmac_blind_index(
            "bob@example.com"
        )

    def test_length_64_hex(self):
        """SHA-256 hex digest = 64 characters, all hex."""
        h = hmac_blind_index("x")
        assert len(h) == 64
        int(h, 16)  # Raises ValueError if any char is non-hex.

    def test_case_insensitive_normalisation(self):
        """Email normalisation: the tag for 'Alice@Example.COM' must match
        the tag for 'alice@example.com' so users can search by either form.
        """
        assert hmac_blind_index("Alice@Example.COM") == hmac_blind_index(
            "alice@example.com"
        )

    def test_whitespace_stripped(self):
        """Leading / trailing whitespace is stripped so search forms with
        stray spaces still find the row."""
        assert hmac_blind_index("  alice@example.com  ") == hmac_blind_index(
            "alice@example.com"
        )

    def test_key_bound(self, monkeypatch):
        """Rotating the key changes the tag — confirms the HMAC is keyed
        and not just a bare SHA-256."""
        baseline = hmac_blind_index("alice@example.com")

        # Swap in a different ENCRYPTION_KEY + re-derive the blind-index key.
        other_key = Fernet.generate_key().decode("utf-8")
        monkeypatch.setattr(encryption_mod.settings, "ENCRYPTION_KEY", other_key)
        monkeypatch.setattr(
            encryption_mod,
            "_BLIND_INDEX_KEY",
            encryption_mod._derive_blind_index_key(),
        )

        rotated = hmac_blind_index("alice@example.com")
        assert rotated != baseline
