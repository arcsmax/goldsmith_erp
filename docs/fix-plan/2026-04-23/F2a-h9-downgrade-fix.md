# F2a — Fix broken `downgrade()` in migration `20260420_h9_explicit_ondelete_restrict.py`

**Item:** F2a · **Severity:** P0 · **Effort:** S · **Owner:** DB · **Status:** 🛑 BLOCKED on decision
**Source:** Escalation from F2 agent, 2026-04-23. Contradicts report 05's "all reversible" claim.

## Context

The F2 implementation agent ran the mandatory local smoke-test cycle before touching `ci.yml`:

```bash
alembic upgrade head       # PASSED — 6 migrations applied
alembic downgrade base     # FAILED at first step
```

Failure at `20260420_h9_restrict → 20260419_security_floor`:

```
psycopg2.errors.DuplicateObject:
  constraint "fk_customers_deleted_by_users" for relation "customers"
  already exists
```

### Root cause (preliminary)

- `20260420_h9_explicit_ondelete_restrict.py::upgrade()` drops FKs by their existing (likely auto-generated) names and re-creates them with the deterministic name `fk_{table}_{column}_users_restrict`.
- `downgrade()` re-creates them with the deterministic name `fk_{table}_{column}_users`.
- For `customers.deleted_by` specifically, an earlier migration (likely `20260406_add_audit_gdpr_order_items_status_history.py`) already created an FK named `fk_customers_deleted_by_users`. The H9 `upgrade()` path drops this by its auto-generated name (which differs from the deterministic one), renames the FK, but never reconciles the rename with the downgrade. On downgrade, `create_foreign_key(name="fk_customers_deleted_by_users", ...)` collides with a constraint that never got dropped.

Needs code-reading to confirm the exact sequence. Reading the two migrations + the full history of FK creation on `customers.deleted_by` gives the certain answer.

## Goal

`alembic upgrade head && alembic downgrade base && alembic upgrade head` completes cleanly against a fresh Postgres 15. Acceptance: **F2 becomes implementable** (the CI smoke test it adds will pass on HEAD).

## Decision needed from user (before F2a implementation proceeds)

Two options, both S-effort:

### Option 1 — Idempotent downgrade (recommended)

Guard `op.create_foreign_key(...)` in `20260420_h9_restrict::downgrade()` with a drop-if-exists step first. Works even when the pre-existing FK survived `upgrade()`. Matches the pattern the repo already uses in `db/migration_helpers.py` for idempotent schema changes.

```python
def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for table_name, column_name in [("customers", "deleted_by"), ...]:
        # Drop any existing FK on (table, column) before recreating
        for fk in inspector.get_foreign_keys(table_name):
            if fk["constrained_columns"] == [column_name]:
                op.drop_constraint(fk["name"], table_name, type_="foreignkey")
        op.create_foreign_key(
            f"fk_{table_name}_{column_name}_users",
            table_name, "users", [column_name], ["id"],
        )
```

**Pro:** robust, handles the case where `upgrade()` left the old-named FK intact; no data change. **Con:** slightly more code.

### Option 2 — Repair `upgrade()` to drop ALL existing FKs on the 11 columns first

Before recreating as `..._restrict`, drop every existing FK on each affected column (matching Option 1's approach, but applied upward). Keeps `downgrade()` simple.

**Pro:** cleaner conceptual inversion. **Con:** rewrites an already-shipped migration's `upgrade()` — which, if anyone ran H9 on a live DB, would require a data-repair migration in addition.

### What we need from you

- **If the project has never run H9 against a live production DB** (likely true, given Week-1 scope and the pre-production state), **Option 2** is cleaner.
- **If H9 has run in production or a shared dev DB**, **Option 1** is safer (no re-run side-effects).

## Files (once decision lands)

- Modify `alembic/versions/20260420_h9_explicit_ondelete_restrict.py` — either `downgrade()` (Option 1) or `upgrade()` (Option 2).
- Extend the existing `tests/integration/test_migration_*.py` (or create `test_migration_h9_roundtrip.py`) — asserts upgrade→downgrade→upgrade is clean.

## Acceptance criteria

- [ ] Against fresh PG 15: `alembic upgrade head && alembic downgrade base && alembic upgrade head` exits zero at every step.
- [ ] New integration test covers the round-trip.
- [ ] Existing H9 forward-path tests still pass.
- [ ] After this lands, F2 can be dispatched.

## Next step

Orchestrator asks user: Option 1 vs. Option 2 (based on prod-runs-yet question). Then dispatches a DB-focused agent to implement with TDD.
