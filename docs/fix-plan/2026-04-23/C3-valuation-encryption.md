# C3 — Encrypt `ValuationCertificate.appraised_value`

**Item:** C3 · **Severity:** P0 · **Effort:** M · **Owner:** DB + GDPR
**Source:** `docs/review/2026-04-23/FIX-PLAN.md` Group C, report 04 finding F-02
**Decision locked (2026-04-24):** `EncryptedString` + HMAC hash for equality lookups.

## Context

CLAUDE.md "Data Privacy Rules (CRITICAL)":
> **Insurance Valuations:** Valuation data MUST be encrypted at rest

Current state:
- `src/goldsmith_erp/db/models.py:2039` — `ValuationCertificate.appraised_value = Column(Float, nullable=False)` — stored plaintext.
- The class docstring at `db/models.py:1996-1998` acknowledges the sensitivity ("financial data") — yet plaintext.

C1 (`e515d73`) landed `EncryptedString` + `hmac_blind_index`. We use the same pattern here, but over a numeric value (stored as string inside ciphertext).

## Goal

`appraised_value` is stored as ciphertext at rest. Equality search (e.g., "find the valuation for €12500") works via an HMAC column. Existing app-level reads/writes see the value as a numeric type.

## Files

- **Modify** `src/goldsmith_erp/db/models.py` — `ValuationCertificate` class:
  - Replace `appraised_value = Column(Float, nullable=False)` with an `EncryptedString` column holding the **string representation** of the value (preserves decimal precision; `Float` in Python loses it on round-trips). Store as `"12500.00"` with 2-decimal fixed.
  - Add `appraised_value_hmac = Column(String(64), index=True, nullable=False)` for equality lookups.
  - OPTIONAL: add a Python `@property` on the ORM class that converts ciphertext-string back to `Decimal` for callers. Cleaner than every caller doing the cast.
- **Create** `alembic/versions/20260424_c3_valuation_encryption.py` — migration:
  1. Add `appraised_value_hmac` (nullable first)
  2. Backfill: for each row, read plaintext `appraised_value`, compute `hmac_blind_index(f"{value:.2f}")`, write hash
  3. Add an EncryptedString column `appraised_value_encrypted` (for migration purposes — we can't change column TYPE from Float to Text directly in one ALTER if data exists; easier: add new col, backfill, drop old)
  4. Actually for dev-only: simpler — drop `appraised_value`, re-add as Text with EncryptedString, backfill from a saved dict. Since dev-only, document that seed data may need recreation.
  5. Add index on `appraised_value_hmac`, make NOT NULL
  6. Downgrade: reverse (decrypt, cast back to Float, re-add column, drop hash)
- **Modify** `src/goldsmith_erp/services/valuation_service.py` (if exists — otherwise wherever the valuation write path lives):
  - On write: compute `hmac_blind_index(str(appraised_value))` alongside setting the value
  - Ensure equality-search uses the hash column, not the decrypted field
- **Create** `tests/integration/test_valuation_encryption.py` — tests:
  - Writing a valuation persists ciphertext in the DB (raw-SQL check)
  - Reading via ORM returns numeric value (decrypted + cast)
  - Searching by exact appraised value via hash finds the row
  - Migration round-trip passes on PG

## Acceptance criteria

- [ ] Raw SQL `SELECT appraised_value FROM valuation_certificates LIMIT 1` returns ciphertext text (not a number).
- [ ] ORM access returns `Decimal` (preferred) or `float` value.
- [ ] `grep -rn "\.appraised_value\b" src/goldsmith_erp/ | grep -v "\.appraised_value_hmac"` — all callers handle it as numeric as before, not as a string.
- [ ] New integration tests pass.
- [ ] Migration round-trip (upgrade → downgrade → upgrade) is clean on fresh PG.
- [ ] Existing valuation tests still pass.

## Test design (TDD)

```python
# tests/integration/test_valuation_encryption.py
import pytest
from decimal import Decimal
from sqlalchemy import text
from goldsmith_erp.db.models import ValuationCertificate
from goldsmith_erp.core.encryption import hmac_blind_index

pytestmark = pytest.mark.asyncio

class TestValuationEncryption:
    async def test_appraised_value_stored_encrypted(self, db_session, test_valuation_kwargs):
        v = ValuationCertificate(**test_valuation_kwargs, appraised_value=12500.0)
        db_session.add(v)
        await db_session.commit()

        raw = await db_session.execute(
            text("SELECT appraised_value FROM valuation_certificates WHERE id = :id"),
            {"id": v.id},
        )
        raw_value = raw.scalar()
        # Expect Fernet ciphertext (base64-ish, long, not "12500.00")
        assert raw_value != "12500.00"
        assert raw_value != "12500"
        assert "12500" not in str(raw_value) or len(str(raw_value)) > 40

    async def test_appraised_value_round_trip(self, db_session, test_valuation_kwargs):
        v = ValuationCertificate(**test_valuation_kwargs, appraised_value=12500.0)
        db_session.add(v)
        await db_session.commit()

        fetched = await db_session.get(ValuationCertificate, v.id)
        # Value comes back numeric (Decimal preferred; float acceptable)
        assert float(fetched.appraised_value) == 12500.0

    async def test_search_by_appraised_value_via_hash(self, db_session, test_valuation_kwargs):
        v = ValuationCertificate(**test_valuation_kwargs, appraised_value=9876.54)
        db_session.add(v)
        await db_session.commit()

        # Direct hash-column query — the canonical equality-search path
        from sqlalchemy import select
        result = await db_session.execute(
            select(ValuationCertificate).where(
                ValuationCertificate.appraised_value_hmac == hmac_blind_index("9876.54")
            )
        )
        assert result.scalar_one_or_none() is not None
```

## Implementation sketch

### `db/models.py` change

Current (line 2039):
```python
appraised_value = Column(Float, nullable=False)
```

New:
```python
from goldsmith_erp.db.types import EncryptedString
from goldsmith_erp.core.encryption import hmac_blind_index
from sqlalchemy import event

# ... inside ValuationCertificate class:
appraised_value_encrypted = Column("appraised_value", EncryptedString, nullable=False)
appraised_value_hmac = Column(String(64), index=True, nullable=False)

@property
def appraised_value(self) -> Decimal:
    """Decrypted numeric value."""
    return Decimal(self.appraised_value_encrypted)

@appraised_value.setter
def appraised_value(self, value: Union[Decimal, float, int, str]) -> None:
    self.appraised_value_encrypted = f"{Decimal(value):.2f}"
    self.appraised_value_hmac = hmac_blind_index(f"{Decimal(value):.2f}")
```

Note: naming the column `"appraised_value"` at the SQL level (first arg to `Column`) keeps the DB-side column name unchanged while letting the Python attribute be `appraised_value_encrypted`. Callers continue to use `.appraised_value` via the property.

Alternatively, mirror C1's approach: use a SQLAlchemy event hook (`before_insert`/`before_update`) to auto-populate `appraised_value_hmac` whenever `appraised_value_encrypted` is set. Check which pattern C1 adopted and match it.

### Migration

Follow the pattern from `alembic/versions/20260424_c1_customer_pii_encryption.py`:
1. Use `migration_helpers.py` idempotent helpers where applicable.
2. Python-level backfill loop (dev-only — no prod data).

## Parallel-safety

Owns:
- MODIFIED: `src/goldsmith_erp/db/models.py` (ValuationCertificate section only — do NOT touch Customer, that's C1's done scope)
- POSSIBLY MODIFIED: `src/goldsmith_erp/services/valuation_service.py` if it exists
- NEW: `alembic/versions/20260424_c3_*.py`, `tests/integration/test_valuation_encryption.py`

No conflict with F4 (Wave 3b in parallel — touches test files).

## Commit message

```
feat(valuation): encrypt ValuationCertificate.appraised_value (C3)

Fix item C3 — appraised_value was a plain Column(Float), violating
CLAUDE.md "Valuation data MUST be encrypted at rest." Migrated to
EncryptedString (ciphertext at rest, numeric via property) + HMAC
blind-index column for equality-search. Same pattern C1 used for
Customer.email; reuses the EncryptedString TypeDecorator and
hmac_blind_index helper.

Ref: docs/fix-plan/2026-04-23/C3-valuation-encryption.md
Ref: docs/review/2026-04-23/FIX-PLAN.md#group-c

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

## Open questions for the implementing agent

- **Decimal precision**: `appraised_value` is often money-like (€). Consider storing with 2 decimals always (`f"{value:.2f}"`). If the valuation ever needs sub-cent precision, document and use 4. Stick with 2 for now.
- **Range queries** (e.g., "show valuations over €10k"): HMAC supports equality only, not ranges. If range queries exist in services/routers, they'll need to decrypt + filter in-app (slow for large tables). Grep: `grep -rn "appraised_value" src/goldsmith_erp/services/ src/goldsmith_erp/api/routers/`. If range queries exist, document in DECISIONS.md as C3.1 follow-up — for now, keep the value decryptable for in-app range filters.
- **Service-layer property vs ORM property**: if C1 used SQLAlchemy events for Customer, match that here (consistency > personal preference).
