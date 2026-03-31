"""Unit tests for core security module."""
import pytest
from datetime import timedelta
from jose import jwt

from goldsmith_erp.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    ALGORITHM,
)
from goldsmith_erp.core.config import settings


class TestPasswordHashing:
    def test_hash_password_returns_hash(self):
        hashed = get_password_hash("MyPassword123")
        assert hashed != "MyPassword123"
        assert hashed.startswith("$2b$")

    def test_verify_correct_password(self):
        hashed = get_password_hash("MyPassword123")
        assert verify_password("MyPassword123", hashed) is True

    def test_verify_wrong_password(self):
        hashed = get_password_hash("MyPassword123")
        assert verify_password("WrongPassword", hashed) is False

    def test_different_passwords_produce_different_hashes(self):
        hash1 = get_password_hash("Password1")
        hash2 = get_password_hash("Password2")
        assert hash1 != hash2

    def test_same_password_produces_different_hashes(self):
        hash1 = get_password_hash("SamePassword")
        hash2 = get_password_hash("SamePassword")
        assert hash1 != hash2  # bcrypt uses random salt


class TestJWTTokens:
    def test_create_token_returns_string(self):
        token = create_access_token(data={"sub": "1"})
        assert isinstance(token, str)

    def test_token_contains_subject(self):
        token = create_access_token(data={"sub": "42"})
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["sub"] == "42"

    def test_token_contains_expiration(self):
        token = create_access_token(data={"sub": "1"})
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        assert "exp" in payload

    def test_custom_expiration(self):
        token = create_access_token(
            data={"sub": "1"},
            expires_delta=timedelta(minutes=5),
        )
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        assert "exp" in payload

    def test_invalid_secret_key_fails_verification(self):
        token = create_access_token(data={"sub": "1"})
        with pytest.raises(Exception):
            jwt.decode(token, "wrong-secret-key-that-is-long-enough-32chars!", algorithms=[ALGORITHM])

    def test_token_with_extra_data(self):
        token = create_access_token(data={"sub": "1", "role": "admin"})
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM])
        assert payload["role"] == "admin"
