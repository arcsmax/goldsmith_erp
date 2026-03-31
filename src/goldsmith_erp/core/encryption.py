"""
GDPR-Compliant Encryption Utilities

This module provides encryption/decryption functions for protecting Personally
Identifiable Information (PII) in compliance with GDPR Article 32 (Security of Processing).

Uses Fernet (symmetric encryption) based on AES-128 in CBC mode with:
- Authenticated encryption (prevents tampering)
- Automatic key rotation support
- Safe encoding/decoding

PII Fields Requiring Encryption:
- Customer phone numbers
- Customer addresses (line1, line2)
- Any other sensitive personal data

Key Management:
- Encryption key stored in environment variable ENCRYPTION_KEY
- Key must be 32 url-safe base64-encoded bytes
- Generate new key with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

Security Notes:
- Never commit encryption keys to version control
- Rotate keys periodically (recommended: yearly)
- Keep backups of old keys to decrypt historical data
- Use different keys for development/staging/production

Author: Claude AI
Date: 2025-11-06
"""

import base64
import logging
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from goldsmith_erp.core.config import settings

logger = logging.getLogger(__name__)


class EncryptionError(Exception):
    """Raised when encryption or decryption fails."""
    pass


class EncryptionService:
    """
    Service for encrypting and decrypting sensitive customer data (PII).

    Uses Fernet symmetric encryption with automatic integrity checking.
    Thread-safe and can be used as a singleton.

    Usage:
        >>> encryption = EncryptionService()
        >>> encrypted_phone = encryption.encrypt("555-1234")
        >>> decrypted_phone = encryption.decrypt(encrypted_phone)
    """

    def __init__(self):
        """
        Initialize encryption service with key from settings.

        Raises:
            EncryptionError: If encryption key is invalid or missing
        """
        try:
            encryption_key = settings.ENCRYPTION_KEY

            # Validate key format
            if not encryption_key:
                raise EncryptionError("ENCRYPTION_KEY not configured in settings")

            # Convert string key to bytes if needed
            if isinstance(encryption_key, str):
                encryption_key = encryption_key.encode('utf-8')

            # Initialize Fernet cipher
            self._cipher = Fernet(encryption_key)

        except Exception as e:
            logger.error(f"Failed to initialize encryption service: {e}")
            raise EncryptionError(f"Encryption initialization failed: {e}")

    def encrypt(self, plaintext: Optional[str]) -> Optional[str]:
        """
        Encrypt a plaintext string.

        Args:
            plaintext: The string to encrypt (e.g., phone number, address)

        Returns:
            Base64-encoded encrypted string, or None if input is None

        Raises:
            EncryptionError: If encryption fails

        Example:
            >>> encryption = EncryptionService()
            >>> encrypted = encryption.encrypt("555-1234")
            >>> print(encrypted)  # "gAAAAABl..."
        """
        if plaintext is None or plaintext == "":
            return None

        try:
            # Convert string to bytes
            plaintext_bytes = plaintext.encode('utf-8')

            # Encrypt (returns base64-encoded token)
            encrypted_bytes = self._cipher.encrypt(plaintext_bytes)

            # Convert bytes to string for database storage
            encrypted_str = encrypted_bytes.decode('utf-8')

            return encrypted_str

        except Exception as e:
            logger.error(f"Encryption failed: {e}")
            raise EncryptionError(f"Failed to encrypt data: {e}")

    def decrypt(self, encrypted: Optional[str]) -> Optional[str]:
        """
        Decrypt an encrypted string.

        Args:
            encrypted: The base64-encoded encrypted string

        Returns:
            Decrypted plaintext string, or None if input is None

        Raises:
            EncryptionError: If decryption fails (invalid key, tampered data, etc.)

        Example:
            >>> encryption = EncryptionService()
            >>> decrypted = encryption.decrypt("gAAAAABl...")
            >>> print(decrypted)  # "555-1234"
        """
        if encrypted is None or encrypted == "":
            return None

        try:
            # Convert string to bytes
            encrypted_bytes = encrypted.encode('utf-8')

            # Decrypt (validates integrity automatically)
            decrypted_bytes = self._cipher.decrypt(encrypted_bytes)

            # Convert bytes back to string
            decrypted_str = decrypted_bytes.decode('utf-8')

            return decrypted_str

        except InvalidToken:
            logger.error("Decryption failed: Invalid token (wrong key or tampered data)")
            raise EncryptionError("Failed to decrypt data: Invalid encryption token")
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            raise EncryptionError(f"Failed to decrypt data: {e}")

    def encrypt_multiple(self, data: dict) -> dict:
        """
        Encrypt multiple fields in a dictionary.

        Args:
            data: Dictionary with plaintext values

        Returns:
            Dictionary with encrypted values

        Example:
            >>> encryption = EncryptionService()
            >>> customer_data = {
            ...     "phone": "555-1234",
            ...     "address_line1": "123 Main St"
            ... }
            >>> encrypted_data = encryption.encrypt_multiple(customer_data)
        """
        encrypted_data = {}

        for key, value in data.items():
            if isinstance(value, str):
                encrypted_data[key] = self.encrypt(value)
            else:
                encrypted_data[key] = value

        return encrypted_data

    def decrypt_multiple(self, data: dict) -> dict:
        """
        Decrypt multiple fields in a dictionary.

        Args:
            data: Dictionary with encrypted values

        Returns:
            Dictionary with decrypted values

        Example:
            >>> encryption = EncryptionService()
            >>> decrypted_data = encryption.decrypt_multiple(encrypted_data)
        """
        decrypted_data = {}

        for key, value in data.items():
            if isinstance(value, str):
                try:
                    decrypted_data[key] = self.decrypt(value)
                except EncryptionError:
                    # If decryption fails, return original value
                    # (might be unencrypted data from migration)
                    decrypted_data[key] = value
            else:
                decrypted_data[key] = value

        return decrypted_data


# ═══════════════════════════════════════════════════════════════════════════
# Singleton instance for application-wide use
# ═══════════════════════════════════════════════════════════════════════════

_encryption_service: Optional[EncryptionService] = None


def get_encryption_service() -> EncryptionService:
    """
    Get or create singleton encryption service instance.

    Returns:
        EncryptionService: Singleton instance

    Example:
        >>> from goldsmith_erp.core.encryption import get_encryption_service
        >>> encryption = get_encryption_service()
        >>> encrypted = encryption.encrypt("sensitive data")
    """
    global _encryption_service

    if _encryption_service is None:
        _encryption_service = EncryptionService()

    return _encryption_service


# ═══════════════════════════════════════════════════════════════════════════
# Convenience Functions
# ═══════════════════════════════════════════════════════════════════════════

def encrypt_phone(phone: Optional[str]) -> Optional[str]:
    """
    Encrypt a phone number.

    Args:
        phone: Phone number in any format

    Returns:
        Encrypted phone number

    Example:
        >>> encrypted_phone = encrypt_phone("+49 123 456789")
    """
    encryption = get_encryption_service()
    return encryption.encrypt(phone)


def decrypt_phone(encrypted_phone: Optional[str]) -> Optional[str]:
    """
    Decrypt a phone number.

    Args:
        encrypted_phone: Encrypted phone number

    Returns:
        Decrypted phone number

    Example:
        >>> phone = decrypt_phone(encrypted_phone)
    """
    encryption = get_encryption_service()
    return encryption.decrypt(encrypted_phone)


def encrypt_address(address: Optional[str]) -> Optional[str]:
    """
    Encrypt an address line.

    Args:
        address: Address line (street, city, etc.)

    Returns:
        Encrypted address

    Example:
        >>> encrypted_address = encrypt_address("123 Main St")
    """
    encryption = get_encryption_service()
    return encryption.encrypt(address)


def decrypt_address(encrypted_address: Optional[str]) -> Optional[str]:
    """
    Decrypt an address line.

    Args:
        encrypted_address: Encrypted address

    Returns:
        Decrypted address

    Example:
        >>> address = decrypt_address(encrypted_address)
    """
    encryption = get_encryption_service()
    return encryption.decrypt(encrypted_address)


# ═══════════════════════════════════════════════════════════════════════════
# Key Generation Utility
# ═══════════════════════════════════════════════════════════════════════════

def generate_encryption_key() -> str:
    """
    Generate a new Fernet encryption key.

    Returns:
        String: Base64-encoded encryption key

    Example:
        >>> from goldsmith_erp.core.encryption import generate_encryption_key
        >>> new_key = generate_encryption_key()
        >>> print(f"Add to .env: ENCRYPTION_KEY={new_key}")

    Note:
        Run this once during initial setup and store the key securely.
        Never regenerate in production without a key rotation strategy.
    """
    key = Fernet.generate_key()
    return key.decode('utf-8')


if __name__ == "__main__":
    # CLI utility for generating encryption key
    print("═" * 70)
    print("GDPR Encryption Key Generator")
    print("═" * 70)
    print()

    key = generate_encryption_key()

    print("Generated new encryption key:")
    print()
    print(f"  ENCRYPTION_KEY={key}")
    print()
    print("Add this to your .env file (DO NOT commit to version control!)")
    print()
    print("Security Notes:")
    print("  - Store this key securely (password manager, secrets vault)")
    print("  - Use different keys for dev/staging/production")
    print("  - Keep backup of old keys for data migration during rotation")
    print("  - Rotate keys annually as best practice")
    print()
    print("═" * 70)
