"""Custom SQLAlchemy column types for Goldsmith ERP.

This module currently exposes :class:`EncryptedString` — a ``TypeDecorator``
that transparently Fernet-encrypts every value on its way into the database
and decrypts every value on its way out. It is the foundation of the PII
encryption path mandated by CLAUDE.md:

    > Names, addresses, phone numbers, email → MUST be encrypted at rest
    > (EncryptedString type)

Design
------
* **``impl = Text``** — ciphertext is variable-length (Fernet base64 +
  timestamp + AES-128-CBC + HMAC); a fixed ``String(N)`` would either
  silently truncate or require per-column size tuning. ``TEXT`` sidesteps
  that entirely. The tradeoff vs. a fixed ``String`` is negligible on PG
  (both become ``text``) and irrelevant on SQLite (no VARCHAR length
  enforcement).

* **Non-deterministic ciphertext** — Fernet uses a fresh IV every call,
  so the same plaintext maps to different ciphertexts each time it is
  written. This breaks equality-search and uniqueness constraints at the
  DB level. For the one column we need to search by equality (email),
  the caller writes a separate HMAC blind-index tag — see
  :func:`goldsmith_erp.core.encryption.hmac_blind_index`.

* **Legacy-plaintext tolerance on read** — a value that is not a valid
  Fernet token is assumed to be pre-encryption plaintext (legacy row
  written before this column type was introduced, or mid-migration). We
  return it unchanged rather than raise. This mirrors the defensive
  posture of ``customer_service._decrypt_pii`` and keeps mixed-state
  tables readable during the backfill window.

* **Dev-mode pass-through** — if ``ENCRYPTION_KEY`` is not configured
  (dev with no key), the type degrades to a plain ``Text`` column: values
  are stored as-is. CLAUDE.md flags this as dev-only; production boots
  require ``ENCRYPTION_KEY`` (enforced in ``core.config``).

Usage
-----
    from goldsmith_erp.db.types import EncryptedString

    class Customer(Base):
        email = Column(EncryptedString, nullable=False)

The column type is ``cache_ok=True`` so SQLAlchemy can cache compiled
statements involving it without warnings.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from sqlalchemy.types import Text, TypeDecorator

logger = logging.getLogger(__name__)


class EncryptedString(TypeDecorator):
    """Transparent Fernet encryption for string columns.

    See the module docstring for the design rationale. Inherits from
    :class:`sqlalchemy.types.TypeDecorator` so it can be dropped into any
    ``Column(...)`` definition where ``String`` / ``Text`` would appear.
    """

    impl = Text
    cache_ok = True

    # Column-level opt-in for "this might hold legacy plaintext". Default
    # True keeps mid-migration tables readable; set False on new-only
    # columns to make a bad read fail loudly instead.
    def __init__(self, *args: Any, tolerate_plaintext: bool = True, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._tolerate_plaintext = tolerate_plaintext

    # ── Encrypt on write ──────────────────────────────────────────────
    def process_bind_param(
        self, value: Optional[str], dialect: Any
    ) -> Optional[str]:
        """Encrypt ``value`` for persistence. ``None``/``""`` pass through.

        If ``ENCRYPTION_KEY`` is unset (dev-only fallback), the value is
        stored as plaintext so the app still boots without a key. The
        fail-loud guard for production is in ``core.config``.
        """
        if value is None:
            return None
        # Fernet rejects empty input. Treat empty string as NULL.
        if value == "":
            return None

        enc = _get_encryption_service_or_none()
        if enc is None:
            # Dev / migration fallback. Log once per process to make the
            # pass-through visible without flooding the logs on each row.
            _warn_plaintext_once()
            return value
        # EncryptionService.encrypt wraps Fernet and re-raises on failure
        # as EncryptionError — we let that propagate so the caller aborts
        # the transaction rather than silently storing plaintext. This is
        # the "fail loudly" policy from CLAUDE.md.
        return enc.encrypt(value)

    # ── Decrypt on read ───────────────────────────────────────────────
    def process_result_value(
        self, value: Optional[str], dialect: Any
    ) -> Optional[str]:
        """Decrypt ``value`` after loading from the DB. Legacy plaintext
        passes through unchanged when ``tolerate_plaintext`` is True.
        """
        if value is None:
            return None

        enc = _get_encryption_service_or_none()
        if enc is None:
            # No key configured — the value was stored plaintext; return
            # it as-is.
            return value

        try:
            return enc.decrypt(value)
        except Exception:
            # Decryption failed — either the value is legacy plaintext,
            # was written under a previous key, or the backend is
            # genuinely broken. The former two are recoverable; the latter
            # isn't, but there's no reliable way to distinguish them from
            # inside this method. Tolerance is the safer default for a
            # mid-migration window; flip ``tolerate_plaintext=False`` on
            # columns where every row must be ciphertext.
            if self._tolerate_plaintext:
                return value
            raise


# ---------------------------------------------------------------------------
# Helpers (private)
# ---------------------------------------------------------------------------


def _get_encryption_service_or_none():
    """Return the global ``EncryptionService`` or ``None`` if no key is set.

    Kept as a thin helper so the TypeDecorator doesn't import encryption
    at module load time (circular-import risk: encryption → config →
    logging → …). Safe to call from bind/result hooks at runtime.
    """
    from goldsmith_erp.core.config import settings  # noqa: PLC0415
    if not settings.ENCRYPTION_KEY:
        return None
    from goldsmith_erp.core.encryption import (  # noqa: PLC0415
        get_encryption_service,
    )
    return get_encryption_service()


_plaintext_warn_emitted = False


def _warn_plaintext_once() -> None:
    """Emit a single warning per process when PII is being stored plaintext.

    Logging every row would flood production logs; logging none would hide
    the fact that the app is running in a degraded state. One message per
    process is the usual compromise.
    """
    global _plaintext_warn_emitted
    if _plaintext_warn_emitted:
        return
    _plaintext_warn_emitted = True
    logger.warning(
        "EncryptedString columns are storing PLAINTEXT — ENCRYPTION_KEY "
        "is not configured. This is acceptable only in development; "
        "production startup must abort when ENCRYPTION_KEY is unset."
    )
