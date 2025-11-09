"""add_customer_table_and_update_orders

Revision ID: 74ac93690ff6
Revises: a8b90a411a75
Create Date: 2025-11-09 09:32:25.534365

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '74ac93690ff6'
down_revision: Union[str, None] = 'a8b90a411a75'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Create customers table
    op.create_table(
        'customers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('first_name', sa.String(length=100), nullable=False),
        sa.Column('last_name', sa.String(length=100), nullable=False),
        sa.Column('company_name', sa.String(length=200), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('phone', sa.String(length=50), nullable=True),
        sa.Column('mobile', sa.String(length=50), nullable=True),
        sa.Column('street', sa.String(length=200), nullable=True),
        sa.Column('city', sa.String(length=100), nullable=True),
        sa.Column('postal_code', sa.String(length=20), nullable=True),
        sa.Column('country', sa.String(length=100), nullable=True, server_default='Deutschland'),
        sa.Column('customer_type', sa.String(length=50), nullable=True, server_default='private'),
        sa.Column('source', sa.String(length=100), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('tags', sa.JSON(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=True, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=True, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id')
    )

    # Create indexes for customers
    op.create_index(op.f('ix_customers_id'), 'customers', ['id'], unique=False)
    op.create_index(op.f('ix_customers_first_name'), 'customers', ['first_name'], unique=False)
    op.create_index(op.f('ix_customers_last_name'), 'customers', ['last_name'], unique=False)
    op.create_index(op.f('ix_customers_company_name'), 'customers', ['company_name'], unique=False)
    op.create_index(op.f('ix_customers_email'), 'customers', ['email'], unique=True)
    op.create_index(op.f('ix_customers_is_active'), 'customers', ['is_active'], unique=False)
    op.create_index(op.f('ix_customers_created_at'), 'customers', ['created_at'], unique=False)

    # Migrate existing user data to customers (for users who are referenced in orders)
    # This creates customer records from existing users who have orders
    op.execute("""
        INSERT INTO customers (id, first_name, last_name, email, created_at, updated_at)
        SELECT DISTINCT u.id,
               COALESCE(u.first_name, 'Unknown'),
               COALESCE(u.last_name, 'Customer'),
               u.email,
               u.created_at,
               NOW()
        FROM users u
        WHERE u.id IN (SELECT DISTINCT customer_id FROM orders WHERE customer_id IS NOT NULL)
    """)

    # Add deadline column to orders
    op.add_column('orders', sa.Column('deadline', sa.DateTime(), nullable=True))
    op.create_index(op.f('ix_orders_deadline'), 'orders', ['deadline'], unique=False)

    # Note: customer_id foreign key constraint will be updated in the next step
    # For now, the customer_id column already exists and references the migrated customer IDs


def downgrade() -> None:
    """Downgrade schema."""
    # Remove deadline column from orders
    op.drop_index(op.f('ix_orders_deadline'), table_name='orders')
    op.drop_column('orders', 'deadline')

    # Drop customers table
    op.drop_index(op.f('ix_customers_created_at'), table_name='customers')
    op.drop_index(op.f('ix_customers_is_active'), table_name='customers')
    op.drop_index(op.f('ix_customers_email'), table_name='customers')
    op.drop_index(op.f('ix_customers_company_name'), table_name='customers')
    op.drop_index(op.f('ix_customers_last_name'), table_name='customers')
    op.drop_index(op.f('ix_customers_first_name'), table_name='customers')
    op.drop_index(op.f('ix_customers_id'), table_name='customers')
    op.drop_table('customers')
