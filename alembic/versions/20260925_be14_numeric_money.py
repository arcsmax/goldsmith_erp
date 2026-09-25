"""BE-14: money, weight, per-gram price and percentage columns as NUMERIC.

Every Float column that carries money (price, cost, rate, amount, total, VAT,
credit), a weight / quantity, a metal price per gram or a percentage becomes
an exact NUMERIC, see docs/architecture/ADR-2026-09-25-numeric-and-tz.md:

* money                   NUMERIC(12, 2)
* weights, quantities     NUMERIC(12, 3)
* price per gram          NUMERIC(12, 4)
* percentages (VAT, ...)  NUMERIC(5, 2)

PostgreSQL converts in place with ``USING round(col::numeric, scale)`` (half
away from zero, the commercial rounding the documents use). The downgrade
casts back to ``double precision``; it is lossless for every value the
upgrade produced.

Columns that are measurements or ratios (ring size, chain length, hours,
fine-content ratio, activity duration) stay Float on purpose.

SQLite (tests) has no ALTER COLUMN TYPE; batch mode recreates the table.

Revision ID: 20260925_be14_numeric
Revises: 20260925_w6_outbox
Create Date: 2026-09-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "20260925_be14_numeric"
down_revision: Union[str, None] = "20260925_w6_outbox"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

MONEY = (12, 2)
WEIGHT = (12, 3)
PER_GRAM = (12, 4)
PERCENT = (5, 2)

# (table, column, (precision, scale)) — the inventory in the ADR.
COLUMNS: tuple[tuple[str, str, tuple[int, int]], ...] = (
    ("orders", "price", MONEY),
    ("orders", "estimated_weight_g", WEIGHT),
    ("orders", "actual_weight_g", WEIGHT),
    ("orders", "scrap_percentage", PERCENT),
    ("orders", "material_cost_calculated", MONEY),
    ("orders", "material_cost_override", MONEY),
    ("orders", "hourly_rate", MONEY),
    ("orders", "labor_cost", MONEY),
    ("orders", "profit_margin_percent", PERCENT),
    ("orders", "vat_rate", PERCENT),
    ("orders", "calculated_price", MONEY),
    ("materials", "unit_price", MONEY),
    ("materials", "stock", WEIGHT),
    ("materials", "min_stock", WEIGHT),
    ("gemstones", "carat", WEIGHT),
    ("gemstones", "cost", MONEY),
    ("gemstones", "total_cost", MONEY),
    ("metal_purchases", "weight_g", WEIGHT),
    ("metal_purchases", "remaining_weight_g", WEIGHT),
    ("metal_purchases", "price_total", MONEY),
    ("metal_purchases", "price_per_gram", PER_GRAM),
    ("material_usage", "weight_used_g", WEIGHT),
    ("material_usage", "cost_at_time", MONEY),
    ("material_usage", "price_per_gram_at_time", PER_GRAM),
    ("inventory_adjustments", "weight_change_g", WEIGHT),
    ("scrap_gold", "total_fine_gold_g", WEIGHT),
    ("scrap_gold", "total_value_eur", MONEY),
    ("scrap_gold", "gold_price_per_g", PER_GRAM),
    ("scrap_gold_items", "weight_g", WEIGHT),
    ("scrap_gold_items", "fine_content_g", WEIGHT),
    ("metal_price_history", "price_per_gram_eur", PER_GRAM),
    ("invoices", "subtotal", MONEY),
    ("invoices", "tax_rate", PERCENT),
    ("invoices", "tax_amount", MONEY),
    ("invoices", "total", MONEY),
    ("invoice_line_items", "quantity", WEIGHT),
    ("invoice_line_items", "unit_price", MONEY),
    ("invoice_line_items", "total", MONEY),
    ("workshop_settings", "default_vat_rate", PERCENT),
    ("quotes", "subtotal", MONEY),
    ("quotes", "tax_rate", PERCENT),
    ("quotes", "tax_amount", MONEY),
    ("quotes", "total", MONEY),
    ("quote_line_items", "quantity", WEIGHT),
    ("quote_line_items", "unit_price", MONEY),
    ("quote_line_items", "total", MONEY),
    ("repair_jobs", "estimated_value", MONEY),
    ("repair_jobs", "estimated_cost", MONEY),
    ("repair_jobs", "actual_cost", MONEY),
    ("consultations", "budget_min", MONEY),
    ("consultations", "budget_max", MONEY),
    ("valuation_certificates", "metal_weight_g", WEIGHT),
    ("cost_change_requests", "original_amount", MONEY),
    ("cost_change_requests", "new_amount", MONEY),
    ("cost_change_requests", "delta_percent", MONEY),
    ("order_items", "unit_price", MONEY),
    ("estimate_accuracy", "estimated_total", MONEY),
    ("estimate_accuracy", "actual_total", MONEY),
)


def _by_table() -> dict[str, list[tuple[str, tuple[int, int]]]]:
    grouped: dict[str, list[tuple[str, tuple[int, int]]]] = {}
    for table, column, spec in COLUMNS:
        grouped.setdefault(table, []).append((column, spec))
    return grouped


def _existing_columns(table: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table(table):
        return set()
    return {col["name"] for col in inspector.get_columns(table)}


def _convert(to_numeric: bool) -> None:
    dialect = op.get_bind().dialect.name
    for table, columns in _by_table().items():
        present = _existing_columns(table)
        missing = [name for name, _ in columns if name not in present]
        if missing:
            raise RuntimeError(
                f"BE-14 migration: {table} is missing {missing}; the schema has "
                "drifted from the model, fix that before converting."
            )
        if dialect == "postgresql":
            for name, (precision, scale) in columns:
                if to_numeric:
                    op.alter_column(
                        table,
                        name,
                        existing_type=sa.Float(),
                        type_=sa.Numeric(precision, scale),
                        postgresql_using=f"round({name}::numeric, {scale})",
                    )
                else:
                    op.alter_column(
                        table,
                        name,
                        existing_type=sa.Numeric(precision, scale),
                        type_=sa.Float(),
                        postgresql_using=f"{name}::double precision",
                    )
            continue
        with op.batch_alter_table(table) as batch:
            for name, (precision, scale) in columns:
                old: sa.types.TypeEngine = (
                    sa.Float() if to_numeric else sa.Numeric(precision, scale)
                )
                new: sa.types.TypeEngine = (
                    sa.Numeric(precision, scale) if to_numeric else sa.Float()
                )
                batch.alter_column(name, existing_type=old, type_=new)


def upgrade() -> None:
    _convert(to_numeric=True)


def downgrade() -> None:
    _convert(to_numeric=False)
