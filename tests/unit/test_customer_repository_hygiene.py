"""
Hygiene tests for CustomerRepository.

These tests pin a narrow invariant: the repository module must import cleanly
and must not reference Customer columns that do not exist on the ORM model.

Background: the pre-V1.1 GDPR hotfix (H1 in V1.1-AMENDMENTS.md) removed two
methods — `get_customers_for_deletion` and `update_retention_deadline` —
because they referenced `Customer.retention_deadline`,
`Customer.data_retention_category`, and `Customer.last_order_date`, none of
which exist on the Customer model. Any call would have raised AttributeError.

These tests guard against regressions in two ways:
1. Import-time smoke test (no hidden `getattr` on nonexistent columns at
   class body evaluation).
2. Explicit assertion that the removed methods stay removed until someone
   re-implements them against columns that actually exist.
"""

import pytest


def test_customer_repository_module_imports_cleanly():
    """The module must import without raising AttributeError on missing cols."""
    import importlib

    module = importlib.import_module(
        "goldsmith_erp.db.repositories.customer"
    )

    assert hasattr(module, "CustomerRepository")


def test_removed_retention_methods_stay_removed():
    """H1 guard: the zombie retention methods must not reappear without a migration.

    If someone re-adds `get_customers_for_deletion` or `update_retention_deadline`
    on CustomerRepository, this test fails — forcing them to justify the columns
    on the Customer model first (or implement the retention engine against
    `orders.retention_class` etc. as V1.1 Migration 2 plans).
    """
    from goldsmith_erp.db.repositories.customer import CustomerRepository

    assert not hasattr(CustomerRepository, "get_customers_for_deletion"), (
        "get_customers_for_deletion was removed in the pre-V1.1 GDPR hotfix "
        "because it references columns that do not exist on Customer. "
        "Re-introducing it requires adding `retention_deadline` and "
        "`data_retention_category` columns via Alembic migration first. "
        "See V1.1-AMENDMENTS.md H1."
    )
    assert not hasattr(CustomerRepository, "update_retention_deadline"), (
        "update_retention_deadline was removed in the pre-V1.1 GDPR hotfix "
        "because it writes to columns that do not exist on Customer. "
        "Re-introducing it requires adding `last_order_date` and "
        "`retention_deadline` columns via Alembic migration first. "
        "See V1.1-AMENDMENTS.md H1."
    )


def test_customer_model_does_not_have_retention_columns():
    """Pin the Customer model: retention columns must NOT exist yet.

    V1.1 Migration 2 (Amendment A2.7) places retention_class on
    `orders` / `material_usage` / `time_entries`, not on `customers`.
    If anyone adds these columns to `customers` directly, this test
    fires and makes them reconsider.
    """
    from goldsmith_erp.db.models import Customer

    columns = {c.name for c in Customer.__table__.columns}

    forbidden_on_customers = {
        "retention_deadline",
        "data_retention_category",
        "last_order_date",
    }
    leaked = forbidden_on_customers & columns
    assert not leaked, (
        f"Columns {leaked} were added to `customers` — reconsider whether "
        "retention should live here or on `orders` / `material_usage` / "
        "`time_entries` per V1.1-AMENDMENTS.md A2.7."
    )
