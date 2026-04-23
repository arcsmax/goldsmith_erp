# F4 — Un-skip or delete 7 stale-skipped encryption/GDPR tests

**Item:** F4 · **Severity:** P0 · **Effort:** S · **Owner:** CI + GDPR · **Status:** ⏸ DEFERRED to Week 2
**Deferred because:** Un-skipping without Group C (PII encryption infra) = red CI with no fix available this week. See `DECISIONS.md`.

## Context

Seven tests permanently skipped with reason *"pending GDPR schema migration"*:
- `tests/test_basic_setup.py:52, 62, 95, 109, 132`
- `tests/test_customer_repository.py:25`
- `tests/test_customer_gdpr.py:23`

The reason string is stale — the GDPR schema shipped weeks ago. But the tests cover `test_encryption_key_configured`, `test_encryption_decrypt`, etc. — things that only really pass once Group C's `EncryptedString` TypeDecorator + PII_FIELDS expansion are in.

## Goal (in Week 2)

For each of the 7 skipped tests: either
1. Un-skip, fix imports/fixtures, and the test runs green (aligned with C1–C4); OR
2. Delete as superseded by post-Slice-2 tests (e.g., `test_gdpr_customer_erasure.py` if it already covers the same surface).

## Next step

Land Group C first. Then a focused investigation agent triages each of the 7, decides un-skip vs. delete, and updates tests in one commit.
