"""W2-06 (DOM-04): gemstone intake on the order.

The ``gemstones`` table has existed since the first schema but nothing wrote
to it. W2-06 adds the CRUD under ``/orders/{id}/gemstones``; this migration
adds the one column the intake needs that the table lacks:

* ``gemstones.is_customer_stone`` (Kundenstein): the customer brought the
  stone. NOT NULL, server default false, so existing rows read as
  workshop stones.

``setting_type`` (Fassungsart) stays a ``String(100)``; the API restricts new
values to the codes the ML encoder already knows (``bezel``, ``prong``,
``channel``, ``pave``, ``tension``, ``invisible``). Existing free-text values
are left untouched.

Downgrade drops the column (lossy: the Kundenstein flag is gone).

Revision ID: 20260925_w206_gemstone_intake
Revises: 20260925_w204_invoice_ustg14
Create Date: 2026-09-25
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "20260925_w206_gemstone_intake"
down_revision: Union[str, None] = "20260925_w204_invoice_ustg14"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "gemstones"
COLUMN = "is_customer_stone"


def upgrade() -> None:
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        add_column_if_not_exists,
        table_exists,
    )

    if not table_exists(TABLE):
        return
    add_column_if_not_exists(
        TABLE,
        sa.Column(
            COLUMN,
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    from goldsmith_erp.db.migration_helpers import (  # noqa: PLC0415
        drop_column_if_exists,
        table_exists,
    )

    if not table_exists(TABLE):
        return
    drop_column_if_exists(TABLE, COLUMN)
