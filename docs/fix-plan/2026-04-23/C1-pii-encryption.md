# C1 — `EncryptedString` TypeDecorator + HMAC blind-index + Customer PII migration

**Item:** C1 (+ C2 subsumed) · **Severity:** P0 · **Effort:** L · **Owner:** DB + GDPR
**Source:** `docs/review/2026-04-23/FIX-PLAN.md` Group C, reports 04 + 05
**Decision context (2026-04-24):** system is **pre-production / dev-only** — no live customer data. Migration can assume an empty or dev-seeded `customers` table. Backfill of existing rows is still implemented for completeness, but does not need prod-like testing.

## Context

CLAUDE.md "Data Privacy Rules (CRITICAL)":
> **Customer PII:** Names, addresses, phone numbers, email → MUST be encrypted at rest (EncryptedString type)

Current state (verified 2026-04-23):
- `src/goldsmith_erp/db/models.py:221-234` — `Customer.first_name`, `last_name`, `company_name`, `email`, `phone`, `mobile`, `street`, `city`, `postal_code` are plain `Column(String(...))`.
- `Customer.email` has `unique=True, index=True` — incompatible with non-deterministic Fernet encryption.
- `services/customer_service.py:267` — `PII_FIELDS = ["phone", "mobile", "street", "city", "postal_code"]` (omits names + email + birthday).
- `services/customer_service.py:573` — `email.ilike(...)` search cannot work against Fernet ciphertext → implies email is currently plaintext, silently violating CLAUDE.md.
- `core/encryption.py` — Fernet helpers exist; no HMAC blind-index helper yet.

## Goal

Customer PII is encrypted at rest. Searchable fields (email) are queryable via deterministic HMAC blind-index. The `EncryptedString` TypeDecorator is reusable for other tables (C3 uses it). CLAUDE.md rule satisfied.

## Files

- **Create** `src/goldsmith_erp/db/types.py` — `EncryptedString` TypeDecorator (wraps Fernet) + helper for computing blind-index hash
- **Modify** `src/goldsmith_erp/core/encryption.py` — add `hmac_blind_index(value: str, key: bytes) -> str` helper (SHA-256 HMAC hex digest, 64 chars) keyed by a new `BLIND_INDEX_KEY` derived from `ENCRYPTION_KEY` via HKDF or a dedicated env var
- **Modify** `src/goldsmith_erp/db/models.py` — `Customer` class: change PII columns to `EncryptedString`, add `email_hash: String(64) unique index nullable=False`, drop unique constraint on `email` itself (ciphertext can't be unique-constrained usefully)
- **Create** `alembic/versions/20260424_c1_customer_pii_encryption.py` — migration:
  1. Add `email_hash` column (nullable first), populate from plaintext emails
  2. Add unique index on `email_hash`
  3. Drop unique index on `email`
  4. For each PII field: read existing plaintext rows, encrypt, write back (Python-level backfill in the migration)
  5. Change column types to `EncryptedString` (which is TEXT at the DB level — no size constraint needed since ciphertext is larger)
  6. Make `email_hash` NOT NULL post-backfill
  7. Downgrade: reverse the steps (decrypt and write back plaintext, drop hash column)
- **Modify** `src/goldsmith_erp/services/customer_service.py`:
  - Expand `PII_FIELDS` to include `first_name`, `last_name`, `email`, `company_name`, `birthday` (if stored — it's a `Date`, needs slightly different handling; prefer keeping birthday plaintext for now + log in DECISIONS.md as separate item)
  - Replace `email.ilike(...)` with `email_hash == hmac_blind_index(email)`
  - Ensure existing `_encrypt_pii` / `_decrypt_pii` helpers still work (they may need updating if EncryptedString does the work at the ORM level — in which case service-layer encryption becomes a no-op and can be removed; document which approach)
- **Create** `tests/unit/test_encrypted_string.py` — unit tests for the TypeDecorator (round-trip, HMAC is deterministic, HMAC is not reversible, etc.)
- **Create** `tests/integration/test_customer_pii_encryption.py` — integration tests:
  - Writing a customer persists ciphertext in the DB (raw-SQL check to confirm)
  - Reading via ORM returns plaintext
  - Searching by email via `email_hash` finds the row
  - Two customers with same name but different emails both have unique `email_hash`es
  - Migration round-trip (upgrade → downgrade → upgrade) preserves data

## Acceptance criteria

- [ ] `EncryptedString` TypeDecorator exists, tested with round-trip.
- [ ] Raw SQL `SELECT email FROM customers LIMIT 1` returns ciphertext (not plaintext).
- [ ] ORM `db.execute(select(Customer)).scalar().email` returns plaintext.
- [ ] `customer_service.search_customers(email="...")` finds the row via `email_hash` comparison (NOT `.ilike()`).
- [ ] `grep -rn "\.ilike(.*email" src/goldsmith_erp/` returns 0 matches (no leftover plaintext searches).
- [ ] New migration's upgrade → downgrade → upgrade cycle passes on a fresh PG (leverage the `test_migration_h9_roundtrip.py` pattern from F2a).
- [ ] Existing customer tests still pass.
- [ ] Backend still boots (critical — EncryptedString must not break the app).

## Test design (TDD)

Write these tests first. They must FAIL against HEAD (no EncryptedString exists, PII is plaintext).

```python
# tests/unit/test_encrypted_string.py
import pytest
from goldsmith_erp.db.types import EncryptedString
from goldsmith_erp.core.encryption import hmac_blind_index, ENCRYPTION_KEY_BYTES, BLIND_INDEX_KEY_BYTES

class TestEncryptedString:
    def test_round_trip(self):
        col = EncryptedString()
        ciphertext = col.process_bind_param("alice@example.com", None)
        plaintext = col.process_result_value(ciphertext, None)
        assert plaintext == "alice@example.com"
        assert ciphertext != "alice@example.com"  # not plaintext

    def test_non_deterministic(self):
        """Fernet is non-deterministic; same input → different ciphertext each time."""
        col = EncryptedString()
        c1 = col.process_bind_param("alice@example.com", None)
        c2 = col.process_bind_param("alice@example.com", None)
        assert c1 != c2  # different ciphertexts
        # but both decrypt to same plaintext
        assert col.process_result_value(c1, None) == col.process_result_value(c2, None)

    def test_none_passes_through(self):
        col = EncryptedString()
        assert col.process_bind_param(None, None) is None
        assert col.process_result_value(None, None) is None

class TestHmacBlindIndex:
    def test_deterministic(self):
        h1 = hmac_blind_index("alice@example.com")
        h2 = hmac_blind_index("alice@example.com")
        assert h1 == h2

    def test_different_inputs_different_hashes(self):
        assert hmac_blind_index("alice@example.com") != hmac_blind_index("bob@example.com")

    def test_length(self):
        """SHA-256 hex digest = 64 chars."""
        assert len(hmac_blind_index("x")) == 64
```

```python
# tests/integration/test_customer_pii_encryption.py
@pytest.mark.asyncio
async def test_customer_email_stored_encrypted(db_session):
    from sqlalchemy import text
    from goldsmith_erp.db.models import Customer
    customer = Customer(
        first_name="Alice", last_name="Smith", email="alice@example.com",
    )
    db_session.add(customer)
    await db_session.commit()

    # Verify DB stores ciphertext
    raw = await db_session.execute(text("SELECT email FROM customers WHERE id = :id"), {"id": customer.id})
    raw_value = raw.scalar()
    assert raw_value != "alice@example.com"  # ciphertext
    assert len(raw_value) > 20  # Fernet ciphertext is base64-encoded, longer than plaintext

    # Verify ORM returns plaintext
    orm_customer = await db_session.get(Customer, customer.id)
    assert orm_customer.email == "alice@example.com"

@pytest.mark.asyncio
async def test_customer_email_searchable_via_hash(db_session):
    from goldsmith_erp.services.customer_service import CustomerService
    # create customer with known email
    customer = Customer(first_name="Bob", last_name="Jones", email="bob@example.com")
    db_session.add(customer)
    await db_session.commit()

    result = await CustomerService.search_customers(db_session, email="bob@example.com")
    assert any(c.id == customer.id for c in result)
```

## Implementation sketch

### `db/types.py`

```python
from sqlalchemy.types import TypeDecorator, Text
from goldsmith_erp.core.encryption import encrypt_string, decrypt_string

class EncryptedString(TypeDecorator):
    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None:
            return None
        return encrypt_string(value)

    def process_result_value(self, value, dialect):
        if value is None:
            return None
        return decrypt_string(value)
```

### `core/encryption.py` additions

```python
import hmac
import hashlib
from goldsmith_erp.core.config import settings

def _derive_blind_index_key() -> bytes:
    """HKDF-derive a separate key from ENCRYPTION_KEY for blind-index.
    Or use a separate BLIND_INDEX_KEY env var — pick one, document in DECISIONS.md."""
    # Simplest: SHA-256 of ENCRYPTION_KEY bytes + a fixed salt.
    return hashlib.sha256(settings.ENCRYPTION_KEY.encode() + b"blind-index-v1").digest()

_BLIND_INDEX_KEY = _derive_blind_index_key()

def hmac_blind_index(value: str) -> str:
    """Deterministic keyed hash — same input → same output, not reversible.
    Used for equality-search on encrypted fields (blind-index pattern)."""
    return hmac.new(_BLIND_INDEX_KEY, value.lower().strip().encode("utf-8"), hashlib.sha256).hexdigest()
```

Email normalization (`.lower().strip()`) matters — matches what users expect when searching. Document this in the function docstring.

## Parallel-safety

Owns:
- NEW: `src/goldsmith_erp/db/types.py`, `tests/unit/test_encrypted_string.py`, `tests/integration/test_customer_pii_encryption.py`, `alembic/versions/20260424_c1_*.py`
- MODIFIED: `src/goldsmith_erp/db/models.py` (Customer section only), `src/goldsmith_erp/core/encryption.py`, `src/goldsmith_erp/services/customer_service.py`

No other Wave-3a agent touches `db/models.py`, `services/customer_service.py`, or `core/encryption.py`. C3 (Wave 3b) touches `db/models.py` (ValuationCertificate) — sequenced AFTER C1.

## Commit message

```
feat(db): EncryptedString TypeDecorator + HMAC blind-index; encrypt Customer PII

Fix item C1 + C2 — Customer first_name/last_name/company_name/email/
phone/mobile/address fields migrated from plain Column(String) to
EncryptedString. `email_hash` added for HMAC-based equality search
(replaces .ilike which could not work against Fernet ciphertext).
Drops unique constraint on email (ciphertext can't be unique-indexed);
email_hash is the new unique index.

CLAUDE.md "Data Privacy Rules (CRITICAL)" — Customer PII now
encrypted at rest as mandated.

Ref: docs/fix-plan/2026-04-23/C1-pii-encryption.md
Ref: docs/review/2026-04-23/FIX-PLAN.md#group-c

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

## Open questions for the implementing agent

- **`birthday`**: currently a `Date` column. Encrypting a date = encoding-as-string + encrypt. Adds complexity. Recommend: keep `birthday` plaintext for now, log in DECISIONS.md as follow-up C1.1. C1 scope = string PII only.
- **Service-layer encrypt/decrypt vs ORM-layer**: if EncryptedString does all the work via the TypeDecorator, `customer_service.py`'s `_encrypt_pii`/`_decrypt_pii` become dead code. Delete them. Document in DECISIONS.md.
- **HMAC key derivation**: this spec suggests deriving from `ENCRYPTION_KEY` via SHA-256. Alternative is a dedicated `BLIND_INDEX_KEY` env var. Former is simpler (one key to manage), latter is more separation-of-concerns. Pick simpler unless there's a security reason not to.
- **Alembic migration backfill**: for dev-only data, a Python-level loop inside the migration that reads/encrypts/writes is fine. For prod, this would block — dev-only decision removes that concern.
