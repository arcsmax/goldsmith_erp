# C4 — Fail loudly when encryption key missing + startup health check

**Item:** C4 · **Severity:** P0 · **Effort:** S · **Owner:** GDPR + BE
**Source:** `docs/review/2026-04-23/FIX-PLAN.md` Group C, report 04 finding F-03

## Context

`services/customer_service.py:279-315` — `_encrypt_pii` / `_decrypt_pii` catch `Exception` and silently keep plaintext. CLAUDE.md: **"Fail loudly — never swallow exceptions silently."** Combined with the missing `ENCRYPTION_KEY` scenario, a production deployment with a misconfigured key silently persists plaintext PII.

Additionally per report 04 finding F-15: **no startup assertion** that `ENCRYPTION_KEY` is set when real customer data exists. Config validator (`core/config.py:137-177`) already refuses to start if `ENCRYPTION_KEY` is missing in non-DEBUG mode — good — but does NOT check at request time whether encryption is actually working.

## Goal

1. Encryption failures raise, not swallow. Every encrypt/decrypt code path is fail-loud.
2. A startup health check logs CRITICAL if `ENCRYPTION_KEY` is unset AND any non-deleted customer row exists in the DB.
3. If C1 is landing EncryptedString (ORM-level), service-layer encrypt/decrypt may become dead code — but the principle still applies: ANY encryption path must be fail-loud.

## Files

- **Modify** `src/goldsmith_erp/services/customer_service.py` — replace the broad `except Exception: pass` with a narrow catch that logs + re-raises (or just remove the try/except if C1 moved encryption to ORM).
- **Modify** `src/goldsmith_erp/core/encryption.py` — add a `check_encryption_configured() -> None` function that raises `EncryptionError` if key is missing/invalid. Add `EncryptionError` class.
- **Modify** `src/goldsmith_erp/main.py` — in the lifespan startup (or the existing `@app.on_event("startup")` — but note this is deprecated per report 01 P1 1.2b; keep consistent with whatever's there now), add a call to `check_encryption_configured()` AND run a SQL `SELECT COUNT(*) FROM customers WHERE NOT is_deleted` check — if count > 0 AND key invalid, log CRITICAL. Do NOT crash the app — refusing customer endpoints is enough.
- **Possibly modify** `src/goldsmith_erp/api/routers/customers.py` — add a dependency that checks encryption health and returns 503 if unhealthy. OR gate via a middleware. Prefer dependency for targeted scope.
- **Create** `tests/unit/test_encryption_fail_loud.py` — tests:
  - `check_encryption_configured` raises `EncryptionError` when key env var is missing
  - Encrypting with invalid key raises
  - Decrypting ciphertext with wrong key raises
  - `_encrypt_pii` (if it still exists post-C1) propagates the error (doesn't swallow)

## Acceptance criteria

- [ ] `grep -rn "except Exception:" src/goldsmith_erp/services/customer_service.py` returns 0 matches (no catch-all swallow).
- [ ] `grep -rn "except.*pass" src/goldsmith_erp/core/encryption.py src/goldsmith_erp/services/customer_service.py` — 0 matches.
- [ ] Unit tests for encryption failures pass.
- [ ] Backend startup with missing `ENCRYPTION_KEY` + DEBUG=false still refuses to start (existing behavior preserved).
- [ ] Backend startup with valid `ENCRYPTION_KEY` but DB has customer rows: logs INFO "encryption health: OK" or similar.
- [ ] Test: intentionally set `ENCRYPTION_KEY` to an invalid Fernet key (wrong length) in DEBUG mode → `check_encryption_configured()` raises.

## Test design (TDD)

```python
# tests/unit/test_encryption_fail_loud.py
import pytest
from goldsmith_erp.core.encryption import (
    encrypt_string, decrypt_string, check_encryption_configured, EncryptionError,
)

class TestFailLoud:
    def test_check_configured_raises_on_missing_key(self, monkeypatch):
        from goldsmith_erp.core import config
        monkeypatch.setattr(config.settings, "ENCRYPTION_KEY", "")
        with pytest.raises(EncryptionError, match="ENCRYPTION_KEY"):
            check_encryption_configured()

    def test_check_configured_raises_on_malformed_key(self, monkeypatch):
        from goldsmith_erp.core import config
        monkeypatch.setattr(config.settings, "ENCRYPTION_KEY", "not-a-valid-fernet-key")
        with pytest.raises(EncryptionError):
            check_encryption_configured()

    def test_encrypt_raises_on_invalid_input(self):
        with pytest.raises((TypeError, EncryptionError)):
            encrypt_string(None)  # None should be caller's responsibility to check; or document behavior

    def test_decrypt_wrong_key_raises(self, monkeypatch):
        ciphertext = encrypt_string("hello")
        # switch key
        from cryptography.fernet import Fernet
        new_key = Fernet.generate_key().decode()
        monkeypatch.setattr("goldsmith_erp.core.encryption.settings.ENCRYPTION_KEY", new_key)
        # Reload the Fernet cipher if cached
        import goldsmith_erp.core.encryption as mod
        mod._fernet = None  # reset cache if present
        with pytest.raises(EncryptionError):
            decrypt_string(ciphertext)
```

## Implementation sketch

```python
# core/encryption.py additions
class EncryptionError(Exception):
    """Raised when encryption/decryption fails or is misconfigured."""

def check_encryption_configured() -> None:
    """Raise EncryptionError if ENCRYPTION_KEY is unset or malformed.
    Call on startup (customer endpoints refuse to serve otherwise)."""
    from goldsmith_erp.core.config import settings
    if not settings.ENCRYPTION_KEY:
        raise EncryptionError("ENCRYPTION_KEY is not set")
    try:
        from cryptography.fernet import Fernet
        Fernet(settings.ENCRYPTION_KEY.encode())
    except Exception as e:
        raise EncryptionError(f"ENCRYPTION_KEY is malformed: {e}") from e
```

Wire into `main.py` startup — after logging init, before serving:
```python
from goldsmith_erp.core.encryption import check_encryption_configured, EncryptionError

try:
    check_encryption_configured()
    logger.info("encryption_health", extra={"status": "ok"})
except EncryptionError as e:
    logger.critical("encryption_health_failed", extra={"error": str(e), "audit": True})
    if not settings.DEBUG:
        raise  # fail app startup in prod
    # In DEBUG: warn but allow startup (tests without encryption)
```

## Parallel-safety

Owns:
- MODIFIED: `src/goldsmith_erp/core/encryption.py`, `src/goldsmith_erp/services/customer_service.py`, `src/goldsmith_erp/main.py`
- NEW: `tests/unit/test_encryption_fail_loud.py`

**NOTE**: `main.py` was touched by A1 (audit middleware). `core/encryption.py` is touched by C1 (EncryptedString). You're both modifying these files.

**COORDINATION PROTOCOL**:
- For `main.py`: C4 adds a startup hook. C1 doesn't touch main.py. OK.
- For `core/encryption.py`: C1 adds HMAC helper + (possibly) refactors Fernet init. C4 adds `EncryptionError` + `check_encryption_configured`. **Potential conflict**. Mitigation: C4 agent should read the file at dispatch time; if C1 has already committed changes to it, rebase your additions on top. If your changes collide at the diff level, STOP and escalate — don't force-merge.
- `services/customer_service.py`: C1 expands PII_FIELDS + removes try/except-catch-all. C4 removes try/except-catch-all. They converge on the same file. **Sequence: C1 lands first** (C1 is Wave 3a, C4 is Wave 3a — but C1 is larger, takes longer). If C4 finishes first and C1 starts with C4's changes in place, C1 agent doesn't need to do the except-removal (already done). OK to dispatch both in parallel if they're aware of each other.

**PRACTICAL**: the C4 agent should attempt its changes; if it sees `customer_service.py` already has the swallow-exception removed (because C1 got there first), it only needs to handle `core/encryption.py` + `main.py`. Document in report.

## Commit message

```
feat(encryption): fail loudly on encryption misconfiguration (C4)

Fix item C4 — swapped broad `except Exception: pass` in
customer_service PII helpers for targeted raises, added
check_encryption_configured() + EncryptionError, wired into
startup so a misconfigured ENCRYPTION_KEY is visible
immediately (CRITICAL log + refuse to start in prod).

CLAUDE.md "Fail loudly — never swallow exceptions silently"
is now enforced on the encryption path.

Ref: docs/fix-plan/2026-04-23/C4-fail-loudly.md
Ref: docs/review/2026-04-23/FIX-PLAN.md#group-c

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

## Open questions for the implementing agent

- If C1 is landing first and moves encryption to ORM-level via `EncryptedString`, the service-layer `_encrypt_pii` may be gone. In that case, C4's customer_service changes are no-op. Adjust scope to just encryption.py + main.py + tests.
- Whether to crash in prod on encryption failure or just log CRITICAL + 503 on customer endpoints: spec says log+503 (don't crash). Reason: partial availability > full outage when non-PII endpoints work fine.
