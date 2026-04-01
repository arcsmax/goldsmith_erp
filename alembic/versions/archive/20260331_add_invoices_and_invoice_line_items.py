"""Add invoices and invoice_line_items tables (Rechnungswesen)

Revision ID: 1a2b3c4d5e6f
Revises: 9c5d4e3f2a1b
Create Date: 2026-03-31

Creates:
  - invoices table with German invoice format (RE-YYYY-NNNN)
    - invoice_number: unique sequential identifier per year
    - order_id FK (RESTRICT — cannot delete order with active invoice)
    - customer_id FK (RESTRICT)
    - created_by FK to users
    - status: InvoiceStatus enum (draft, sent, paid, overdue, cancelled)
    - issue_date, due_date, paid_date
    - subtotal (Zwischensumme), tax_rate (MwSt-Satz), tax_amount, total (Gesamtbetrag)
    - notes, payment_method

  - invoice_line_items table (Rechnungspositionen)
    - line_type: InvoiceLineType enum (material, labor, gemstone, other)
    - description, quantity, unit_price, total

Rollback strategy:
  downgrade() drops invoice_line_items first (FK dependency), then invoices,
  then drops the two custom enum types. Safe to re-run: all operations use
  checkfirst=True on enums.

Financial data note:
  These tables store billing data. Access control is enforced at the API layer
  (ADMIN and GOLDSMITH roles only). All access is audit-logged in application logs.
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = '1a2b3c4d5e6f'
down_revision: Union[str, None] = '9c5d4e3f2a1b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Enum: InvoiceStatus (Rechnungsstatus) ---
    invoice_status = sa.Enum(
        'draft', 'sent', 'paid', 'overdue', 'cancelled',
        name='invoicestatus',
    )
    invoice_status.create(op.get_bind(), checkfirst=True)

    # --- Enum: InvoiceLineType (Rechnungspositionstyp) ---
    invoice_line_type = sa.Enum(
        'material', 'labor', 'gemstone', 'other',
        name='invoicelinetype',
    )
    invoice_line_type.create(op.get_bind(), checkfirst=True)

    # --- Table: invoices ---
    op.create_table(
        'invoices',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('invoice_number', sa.String(20), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('customer_id', sa.Integer(), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('status', invoice_status, server_default='draft', nullable=False),
        sa.Column('issue_date', sa.DateTime(), nullable=False),
        sa.Column('due_date', sa.DateTime(), nullable=False),
        sa.Column('paid_date', sa.DateTime(), nullable=True),
        sa.Column('subtotal', sa.Float(), server_default='0.0', nullable=False),
        sa.Column('tax_rate', sa.Float(), server_default='19.0', nullable=False),
        sa.Column('tax_amount', sa.Float(), server_default='0.0', nullable=False),
        sa.Column('total', sa.Float(), server_default='0.0', nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('payment_method', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='RESTRICT'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('invoice_number', name='uq_invoices_invoice_number'),
    )
    op.create_index('ix_invoices_id', 'invoices', ['id'])
    op.create_index('ix_invoices_invoice_number', 'invoices', ['invoice_number'], unique=True)
    op.create_index('ix_invoices_order_id', 'invoices', ['order_id'])
    op.create_index('ix_invoices_customer_id', 'invoices', ['customer_id'])
    op.create_index('ix_invoices_status', 'invoices', ['status'])
    op.create_index('ix_invoices_issue_date', 'invoices', ['issue_date'])

    # --- Table: invoice_line_items ---
    op.create_table(
        'invoice_line_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('invoice_id', sa.Integer(), nullable=False),
        sa.Column('line_type', invoice_line_type, server_default='other', nullable=False),
        sa.Column('description', sa.String(500), nullable=False),
        sa.Column('quantity', sa.Float(), server_default='1.0', nullable=False),
        sa.Column('unit_price', sa.Float(), nullable=False),
        sa.Column('total', sa.Float(), nullable=False),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_invoice_line_items_id', 'invoice_line_items', ['id'])
    op.create_index('ix_invoice_line_items_invoice_id', 'invoice_line_items', ['invoice_id'])


def downgrade() -> None:
    # Drop tables in reverse dependency order
    op.drop_index('ix_invoice_line_items_invoice_id', table_name='invoice_line_items')
    op.drop_index('ix_invoice_line_items_id', table_name='invoice_line_items')
    op.drop_table('invoice_line_items')

    op.drop_index('ix_invoices_issue_date', table_name='invoices')
    op.drop_index('ix_invoices_status', table_name='invoices')
    op.drop_index('ix_invoices_customer_id', table_name='invoices')
    op.drop_index('ix_invoices_order_id', table_name='invoices')
    op.drop_index('ix_invoices_invoice_number', table_name='invoices')
    op.drop_index('ix_invoices_id', table_name='invoices')
    op.drop_table('invoices')

    # Drop enums last (after all tables that reference them are gone)
    sa.Enum(name='invoicelinetype').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='invoicestatus').drop(op.get_bind(), checkfirst=True)
