# F4 — Un-skip or delete 7 stale-skipped encryption/GDPR tests (unblocked after C1)

**Item:** F4 · **Severity:** P0 · **Effort:** S · **Owner:** CI + GDPR
**Status:** ⏳ pending (unblocked 2026-04-24 — C1 landed `EncryptedString` infra)
**Source:** `docs/review/2026-04-23/FIX-PLAN.md` Group F, report 06 finding F4

## Context

Seven tests permanently skipped with reason *"pending GDPR schema migration"*:
- `tests/test_basic_setup.py` lines 52, 62, 95, 109, 132
- `tests/test_customer_repository.py` line 25
- `tests/test_customer_gdpr.py` line 23

The skip reason is stale — the GDPR schema shipped weeks ago + C1 just added PII encryption. The skipped tests cover `test_encryption_key_configured`, `test_encryption_decrypt`, etc. — things that NOW actually work.

## Goal

For each of the 7 skipped tests:
- **Option A**: un-skip, fix imports/fixtures if needed, test runs green.
- **Option B**: delete as superseded by newer tests (e.g., `tests/unit/test_encrypted_string.py` from C1, `tests/integration/test_customer_pii_encryption.py` from C1, `tests/integration/test_gdpr_customer_erasure.py`).

For each of the 7: read the test body, decide A or B, justify briefly.

## Files

- **Modify** `tests/test_basic_setup.py` — 5 skipped tests
- **Modify** `tests/test_customer_repository.py` — 1 skipped test
- **Modify** `tests/test_customer_gdpr.py` — 1 skipped test
- **Possibly delete** the above files entirely if all tests in them are superseded (check)

## Acceptance criteria

- [ ] No `@pytest.mark.skip(reason=".*pending GDPR schema migration.*")` remains in the repo.
- [ ] No `pytest.skip("pending GDPR schema migration")` statements remain.
- [ ] All un-skipped tests pass green.
- [ ] Any deleted tests have a clearly identified superseding test (documented in the commit message).
- [ ] Running `poetry run pytest tests/ -v --no-header -q 2>&1 | grep -i "skip.*gdpr\|skip.*encryption" | wc -l` returns 0.
- [ ] Net test count increases or stays same (never decreases silently).

## Test design (TDD)

This item is test repair, not feature code. The "failing test" equivalent: un-skip a test, run it. If it passes, great — keep un-skipped. If it fails, either fix it or delete it with a documented supersession.

Workflow:
1. For each skipped test, un-skip it locally (don't commit yet).
2. Run it. 
3. **Green?** Commit the unskip.
4. **Red?** Read the test: does it test anything C1/C4/A1/D3 doesn't already cover?
   - **Yes, unique coverage** → fix the test, commit.
   - **No, superseded** → delete the test, commit with a pointer to the superseding test.
5. **Red and hard to fix?** Document in DECISIONS.md and escalate.

## Implementation sketch

Example for one of the tests (adapt per-test):

```python
# tests/test_basic_setup.py — BEFORE
@pytest.mark.skip(reason="pending GDPR schema migration")
def test_encryption_key_configured():
    from goldsmith_erp.core.config import settings
    assert settings.ENCRYPTION_KEY  # was failing pre-C1; now settings validates

# AFTER option A (un-skip):
def test_encryption_key_configured():
    from goldsmith_erp.core.config import settings
    assert settings.ENCRYPTION_KEY
    from goldsmith_erp.core.encryption import check_encryption_configured
    check_encryption_configured()  # C4 helper; fails loud

# AFTER option B (delete with pointer in commit message):
# Test removed — superseded by tests/unit/test_encryption_fail_loud.py::
#   test_succeeds_with_valid_key (C4) which performs the same check and
#   more (malformed key, missing key).
```

## Parallel-safety

Owns:
- MODIFIED: the 3 test files listed above
- NO source code changes

C3 (Wave 3b parallel) modifies `db/models.py` + new migration + `valuation_service.py`. No overlap.

## Commit message

```
test: un-skip/delete 7 stale-skipped encryption/GDPR tests (F4)

Fix item F4 — 7 tests had been @pytest.mark.skip'd with reason
"pending GDPR schema migration" since pre-V1. GDPR schema shipped
months ago + C1 landed encryption infra. For each test:

  tests/test_basic_setup.py::test_encryption_key_configured      → <kept / deleted (superseded by ...)>
  tests/test_basic_setup.py::test_encryption_decrypt              → <kept / deleted>
  tests/test_basic_setup.py::<line 95>                            → <...>
  tests/test_basic_setup.py::<line 109>                           → <...>
  tests/test_basic_setup.py::<line 132>                           → <...>
  tests/test_customer_repository.py::<line 25>                    → <...>
  tests/test_customer_gdpr.py::<line 23>                          → <...>

[Agent fills in the outcomes during implementation.]

Ref: docs/fix-plan/2026-04-23/F4-skipped-tests.md
Ref: docs/review/2026-04-23/FIX-PLAN.md#group-f

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>
```

## Open questions for the implementing agent

- If the 3 test files turn out to be ENTIRELY stale-skipped (no useful tests remaining after triage), delete the files and note in DECISIONS.md.
- If un-skipping reveals a bug in C1/C4 (e.g., `check_encryption_configured` has a subtle flaw that the stale test catches), STOP and escalate — a real bug trumps cleanup.
