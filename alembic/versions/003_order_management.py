"""Order Management Enhancement - Order Items and Status Tracking

Revision ID: 003_order_management
Revises: 002_gdpr_compliance
Create Date: 2025-11-06 16:00:00.000000

This migration implements comprehensive order management by:
1. Creating OrderItem table for material usage tracking
2. Creating OrderStatusHistory table for complete audit trail
3. Enhancing Order table with detailed cost and labor tracking
4. Adding support for planned vs actual material usage
5. Implementing complete order lifecycle tracking
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '003_order_management'
down_revision = '002_gdpr_compliance'
branch_labels = None
depends_on = None


def upgrade():
    """
    Apply order management enhancements to database.
    """

    # ========================================================================
    # 1. Create OrderItem Table (Material Usage Tracking)
    # ========================================================================
    op.create_table(
        'order_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),
        sa.Column('material_id', sa.Integer(), nullable=False),

        # Quantities
        sa.Column('quantity_planned', sa.Float(), nullable=False),
        sa.Column('quantity_used', sa.Float(), server_default='0.0', nullable=False),
        sa.Column('unit', sa.String(), nullable=False),

        # Costs (snapshot at time of order)
        sa.Column('unit_price', sa.Float(), nullable=False),
        sa.Column('total_cost', sa.Float(), server_default='0.0', nullable=False),

        # Status
        sa.Column('is_allocated', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('is_used', sa.Boolean(), server_default='false', nullable=False),

        # Timestamps
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('allocated_at', sa.DateTime(), nullable=True),
        sa.Column('used_at', sa.DateTime(), nullable=True),

        # Notes
        sa.Column('notes', sa.Text(), nullable=True),

        # Constraints
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['material_id'], ['materials.id'], ondelete='RESTRICT')
    )

    # Indexes for OrderItem table
    op.create_index(op.f('ix_order_items_id'), 'order_items', ['id'], unique=False)
    op.create_index(op.f('ix_order_items_order_id'), 'order_items', ['order_id'], unique=False)
    op.create_index(op.f('ix_order_items_material_id'), 'order_items', ['material_id'], unique=False)

    # ========================================================================
    # 2. Create OrderStatusHistory Table (Audit Trail)
    # ========================================================================
    op.create_table(
        'order_status_history',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.Integer(), nullable=False),

        # Status Change
        sa.Column('old_status', sa.String(), nullable=True),
        sa.Column('new_status', sa.String(), nullable=False),

        # Change Information
        sa.Column('changed_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('changed_by', sa.Integer(), nullable=False),
        sa.Column('reason', sa.String(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),

        # Context
        sa.Column('ip_address', sa.String(), nullable=True),
        sa.Column('user_agent', sa.String(), nullable=True),

        # Constraints
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['order_id'], ['orders.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['changed_by'], ['users.id'])
    )

    # Indexes for OrderStatusHistory table
    op.create_index(op.f('ix_order_status_history_id'), 'order_status_history', ['id'], unique=False)
    op.create_index(op.f('ix_order_status_history_order_id'), 'order_status_history', ['order_id'], unique=False)
    op.create_index(op.f('ix_order_status_history_changed_at'), 'order_status_history', ['changed_at'], unique=False)

    # ========================================================================
    # 3. Enhance Orders Table (Add New Fields)
    # ========================================================================

    # Order Type and Classification
    op.add_column('orders', sa.Column('order_type', sa.String(), server_default='custom_jewelry', nullable=False))
    op.create_index(op.f('ix_orders_order_type'), 'orders', ['order_type'], unique=False)

    # Financial Tracking
    op.add_column('orders', sa.Column('material_cost', sa.Float(), server_default='0.0', nullable=False))
    op.add_column('orders', sa.Column('labor_cost', sa.Float(), server_default='0.0', nullable=False))
    op.add_column('orders', sa.Column('additional_cost', sa.Float(), server_default='0.0', nullable=False))
    op.add_column('orders', sa.Column('total_cost', sa.Float(), server_default='0.0', nullable=False))
    op.add_column('orders', sa.Column('customer_price', sa.Float(), server_default='0.0', nullable=False))
    op.add_column('orders', sa.Column('margin', sa.Float(), server_default='0.0', nullable=False))
    op.add_column('orders', sa.Column('currency', sa.String(), server_default='EUR', nullable=False))

    # Labor Tracking
    op.add_column('orders', sa.Column('estimated_hours', sa.Float(), nullable=True))
    op.add_column('orders', sa.Column('actual_hours', sa.Float(), nullable=True))
    op.add_column('orders', sa.Column('hourly_rate', sa.Float(), nullable=True))

    # Additional Information
    op.add_column('orders', sa.Column('customer_notes', sa.Text(), nullable=True))
    op.add_column('orders', sa.Column('attachments', postgresql.JSONB(astext_type=sa.Text()), nullable=True))

    # Audit Trail
    op.add_column('orders', sa.Column('created_by', sa.Integer(), nullable=True))
    op.add_column('orders', sa.Column('updated_by', sa.Integer(), nullable=True))

    # Soft Delete
    op.add_column('orders', sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('orders', sa.Column('deleted_by', sa.Integer(), nullable=True))

    # Add foreign keys for audit trail
    op.create_foreign_key('fk_orders_created_by_users', 'orders', 'users', ['created_by'], ['id'])
    op.create_foreign_key('fk_orders_updated_by_users', 'orders', 'users', ['updated_by'], ['id'])
    op.create_foreign_key('fk_orders_deleted_by_users', 'orders', 'users', ['deleted_by'], ['id'])

    # Add index for soft delete
    op.create_index(op.f('ix_orders_is_deleted'), 'orders', ['is_deleted'], unique=False)

    # ========================================================================
    # 4. Add Legacy Compatibility Fields
    # ========================================================================

    # These fields mirror new fields for backward compatibility
    # Some already exist from migration 002, we'll add the missing ones

    # Date fields (already added in migration 002):
    # - started_at, completed_at, delivered_at, cancelled_at

    # Add order_date, estimated_completion_date, actual_completion_date, delivery_date
    op.add_column('orders', sa.Column('order_date', sa.DateTime(), server_default=sa.text('NOW()'), nullable=False))
    op.add_column('orders', sa.Column('estimated_completion_date', sa.DateTime(), nullable=True))
    op.add_column('orders', sa.Column('actual_completion_date', sa.DateTime(), nullable=True))
    op.add_column('orders', sa.Column('delivery_date', sa.DateTime(), nullable=True))

    # Status field (maps to workflow_state from migration 002)
    op.add_column('orders', sa.Column('status', sa.String(), server_default='draft', nullable=False))
    op.create_index(op.f('ix_orders_status'), 'orders', ['status'], unique=False)

    # ========================================================================
    # 5. Data Migration: Sync existing data
    # ========================================================================

    # Copy workflow_state to status for existing orders
    op.execute("UPDATE orders SET status = COALESCE(workflow_state, 'draft')")

    # Copy started_at to order_date if order_date is NULL and started_at exists
    op.execute("UPDATE orders SET order_date = started_at WHERE started_at IS NOT NULL")

    # Copy completed_at to actual_completion_date
    op.execute("UPDATE orders SET actual_completion_date = completed_at WHERE completed_at IS NOT NULL")

    # Copy delivered_at to delivery_date
    op.execute("UPDATE orders SET delivery_date = delivered_at WHERE delivered_at IS NOT NULL")


def downgrade():
    """
    Rollback order management enhancements.
    WARNING: This will result in data loss for OrderItem and OrderStatusHistory tables!
    """

    # Remove new order columns (in reverse order)
    op.drop_index(op.f('ix_orders_status'), table_name='orders')
    op.drop_column('orders', 'status')
    op.drop_column('orders', 'delivery_date')
    op.drop_column('orders', 'actual_completion_date')
    op.drop_column('orders', 'estimated_completion_date')
    op.drop_column('orders', 'order_date')

    op.drop_index(op.f('ix_orders_is_deleted'), table_name='orders')

    op.drop_constraint('fk_orders_deleted_by_users', 'orders', type_='foreignkey')
    op.drop_constraint('fk_orders_updated_by_users', 'orders', type_='foreignkey')
    op.drop_constraint('fk_orders_created_by_users', 'orders', type_='foreignkey')

    op.drop_column('orders', 'deleted_by')
    op.drop_column('orders', 'is_deleted')
    op.drop_column('orders', 'updated_by')
    op.drop_column('orders', 'created_by')
    op.drop_column('orders', 'attachments')
    op.drop_column('orders', 'customer_notes')
    op.drop_column('orders', 'hourly_rate')
    op.drop_column('orders', 'actual_hours')
    op.drop_column('orders', 'estimated_hours')
    op.drop_column('orders', 'currency')
    op.drop_column('orders', 'margin')
    op.drop_column('orders', 'customer_price')
    op.drop_column('orders', 'total_cost')
    op.drop_column('orders', 'additional_cost')
    op.drop_column('orders', 'labor_cost')
    op.drop_column('orders', 'material_cost')

    op.drop_index(op.f('ix_orders_order_type'), table_name='orders')
    op.drop_column('orders', 'order_type')

    # Drop OrderStatusHistory table
    op.drop_index(op.f('ix_order_status_history_changed_at'), table_name='order_status_history')
    op.drop_index(op.f('ix_order_status_history_order_id'), table_name='order_status_history')
    op.drop_index(op.f('ix_order_status_history_id'), table_name='order_status_history')
    op.drop_table('order_status_history')

    # Drop OrderItem table
    op.drop_index(op.f('ix_order_items_material_id'), table_name='order_items')
    op.drop_index(op.f('ix_order_items_order_id'), table_name='order_items')
    op.drop_index(op.f('ix_order_items_id'), table_name='order_items')
    op.drop_table('order_items')
