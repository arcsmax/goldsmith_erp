"""GDPR Compliance - Customer Model and Audit Logging

Revision ID: 002_gdpr_compliance
Revises: 001_initial_schema
Create Date: 2025-11-06 14:00:00.000000

This migration implements GDPR compliance by:
1. Creating separate Customer table (from conflated User table)
2. Adding CustomerAuditLog for GDPR accountability
3. Adding GDPRRequest for data subject rights tracking
4. Adding DataRetentionPolicy for storage limitation
5. Adding UserSession for secure authentication
6. Updating Order table to reference customers
7. Migrating existing user-customers to new customer table
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from datetime import datetime, timedelta

# revision identifiers, used by Alembic.
revision = '002_gdpr_compliance'
down_revision = '001_initial_schema'
branch_labels = None
depends_on = None


def upgrade():
    """
    Apply GDPR compliance changes to database.
    """

    # ========================================================================
    # 1. Create Customers Table
    # ========================================================================
    op.create_table(
        'customers',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('customer_number', sa.String(), nullable=False),

        # Personal Data
        sa.Column('first_name', sa.String(), nullable=False),
        sa.Column('last_name', sa.String(), nullable=False),
        sa.Column('email', sa.String(), nullable=False),
        sa.Column('phone', sa.String(), nullable=True),

        # Address
        sa.Column('address_line1', sa.String(), nullable=True),
        sa.Column('address_line2', sa.String(), nullable=True),
        sa.Column('postal_code', sa.String(), nullable=True),
        sa.Column('city', sa.String(), nullable=True),
        sa.Column('country', sa.String(), server_default='DE', nullable=True),

        # GDPR Compliance
        sa.Column('legal_basis', sa.String(), server_default='contract', nullable=False),
        sa.Column('consent_marketing', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('consent_date', sa.DateTime(), nullable=True),
        sa.Column('consent_version', sa.String(), nullable=True),
        sa.Column('consent_ip_address', sa.String(), nullable=True),
        sa.Column('consent_method', sa.String(), nullable=True),

        # Data Retention
        sa.Column('data_retention_category', sa.String(), server_default='active', nullable=False),
        sa.Column('last_order_date', sa.DateTime(), nullable=True),
        sa.Column('retention_deadline', sa.DateTime(), nullable=True),
        sa.Column('deletion_scheduled', sa.DateTime(), nullable=True),

        # Privacy Preferences
        sa.Column('data_processing_consent', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('email_communication_consent', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('phone_communication_consent', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('sms_communication_consent', sa.Boolean(), server_default='false', nullable=False),

        # Audit Trail
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_by', sa.Integer(), nullable=True),

        # Soft Delete
        sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.Column('deleted_by', sa.Integer(), nullable=True),
        sa.Column('deletion_reason', sa.Text(), nullable=True),

        # Business Fields
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('tags', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('custom_fields', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('total_orders_count', sa.Integer(), server_default='0', nullable=True),
        sa.Column('total_orders_value', sa.Float(), server_default='0.0', nullable=True),

        # Constraints
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['updated_by'], ['users.id'], ),
        sa.ForeignKeyConstraint(['deleted_by'], ['users.id'], )
    )

    # Indexes for Customer table
    op.create_index(op.f('ix_customers_id'), 'customers', ['id'], unique=False)
    op.create_index(op.f('ix_customers_customer_number'), 'customers', ['customer_number'], unique=True)
    op.create_index(op.f('ix_customers_email'), 'customers', ['email'], unique=False)
    op.create_index(op.f('ix_customers_data_retention_category'), 'customers', ['data_retention_category'], unique=False)
    op.create_index(op.f('ix_customers_is_deleted'), 'customers', ['is_deleted'], unique=False)

    # ========================================================================
    # 2. Create Customer Audit Log Table
    # ========================================================================
    op.create_table(
        'customer_audit_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('customer_id', sa.Integer(), nullable=False),

        # Action Details
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('entity', sa.String(), nullable=False),
        sa.Column('entity_id', sa.Integer(), nullable=True),

        # Change Tracking
        sa.Column('field_name', sa.String(), nullable=True),
        sa.Column('old_value', sa.Text(), nullable=True),
        sa.Column('new_value', sa.Text(), nullable=True),

        # Who & When
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('user_email', sa.String(), nullable=True),
        sa.Column('user_role', sa.String(), nullable=True),
        sa.Column('timestamp', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),

        # Context
        sa.Column('ip_address', sa.String(), nullable=True),
        sa.Column('user_agent', sa.String(), nullable=True),
        sa.Column('endpoint', sa.String(), nullable=True),
        sa.Column('http_method', sa.String(), nullable=True),
        sa.Column('request_id', sa.String(), nullable=True),
        sa.Column('session_id', sa.String(), nullable=True),

        # Legal & Compliance
        sa.Column('legal_basis', sa.String(), nullable=True),
        sa.Column('purpose', sa.String(), nullable=True),

        # Additional Context
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('audit_metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=True),

        # Constraints
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], )
    )

    # Indexes for Audit Log
    op.create_index(op.f('ix_customer_audit_logs_id'), 'customer_audit_logs', ['id'], unique=False)
    op.create_index(op.f('ix_customer_audit_logs_customer_id'), 'customer_audit_logs', ['customer_id'], unique=False)
    op.create_index(op.f('ix_customer_audit_logs_action'), 'customer_audit_logs', ['action'], unique=False)
    op.create_index(op.f('ix_customer_audit_logs_timestamp'), 'customer_audit_logs', ['timestamp'], unique=False)
    op.create_index(op.f('ix_customer_audit_logs_request_id'), 'customer_audit_logs', ['request_id'], unique=False)

    # ========================================================================
    # 3. Create GDPR Request Table
    # ========================================================================
    op.create_table(
        'gdpr_requests',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('customer_id', sa.Integer(), nullable=False),

        # Request Type
        sa.Column('request_type', sa.String(), nullable=False),

        # Status & Timeline
        sa.Column('status', sa.String(), server_default='pending', nullable=False),
        sa.Column('requested_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('due_date', sa.DateTime(), nullable=False),
        sa.Column('completed_at', sa.DateTime(), nullable=True),

        # Request Details
        sa.Column('request_details', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('response_details', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('rejection_reason', sa.Text(), nullable=True),

        # Processing
        sa.Column('assigned_to', sa.Integer(), nullable=True),
        sa.Column('priority', sa.String(), server_default='normal', nullable=True),

        # Verification
        sa.Column('verified', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('verification_method', sa.String(), nullable=True),
        sa.Column('verification_date', sa.DateTime(), nullable=True),

        # Files
        sa.Column('export_file_path', sa.String(), nullable=True),
        sa.Column('certificate_file_path', sa.String(), nullable=True),
        sa.Column('attachments', postgresql.JSONB(astext_type=sa.Text()), nullable=True),

        # Communication
        sa.Column('communication_log', postgresql.JSONB(astext_type=sa.Text()), nullable=True),

        # Constraints
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['assigned_to'], ['users.id'], )
    )

    # Indexes for GDPR Request
    op.create_index(op.f('ix_gdpr_requests_id'), 'gdpr_requests', ['id'], unique=False)
    op.create_index(op.f('ix_gdpr_requests_customer_id'), 'gdpr_requests', ['customer_id'], unique=False)
    op.create_index(op.f('ix_gdpr_requests_request_type'), 'gdpr_requests', ['request_type'], unique=False)
    op.create_index(op.f('ix_gdpr_requests_status'), 'gdpr_requests', ['status'], unique=False)
    op.create_index(op.f('ix_gdpr_requests_requested_at'), 'gdpr_requests', ['requested_at'], unique=False)

    # ========================================================================
    # 4. Create Data Retention Policy Table
    # ========================================================================
    op.create_table(
        'data_retention_policies',
        sa.Column('id', sa.Integer(), nullable=False),

        # Policy Definition
        sa.Column('category', sa.String(), nullable=False),
        sa.Column('retention_period_days', sa.Integer(), nullable=False),

        # Legal Basis
        sa.Column('legal_basis', sa.String(), nullable=False),
        sa.Column('jurisdiction', sa.String(), server_default='EU', nullable=True),

        # Actions
        sa.Column('action_after_expiry', sa.String(), nullable=False),
        sa.Column('auto_apply', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('warning_days_before', sa.Integer(), server_default='30', nullable=True),

        # Documentation
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('policy_document_url', sa.String(), nullable=True),

        # Metadata
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('created_by', sa.Integer(), nullable=True),

        # Constraints
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('category'),
        sa.ForeignKeyConstraint(['created_by'], ['users.id'], )
    )

    # Indexes for Retention Policy
    op.create_index(op.f('ix_data_retention_policies_id'), 'data_retention_policies', ['id'], unique=False)
    op.create_index(op.f('ix_data_retention_policies_category'), 'data_retention_policies', ['category'], unique=True)

    # ========================================================================
    # 5. Create User Session Table
    # ========================================================================
    op.create_table(
        'user_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),

        # Token Information
        sa.Column('token_hash', sa.String(), nullable=False),
        sa.Column('refresh_token_hash', sa.String(), nullable=True),

        # Session Timing
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('refresh_expires_at', sa.DateTime(), nullable=False),
        sa.Column('last_activity', sa.DateTime(), nullable=False, server_default=sa.text('NOW()')),

        # Client Information
        sa.Column('ip_address', sa.String(), nullable=True),
        sa.Column('user_agent', sa.String(), nullable=True),
        sa.Column('device_type', sa.String(), nullable=True),

        # Session Status
        sa.Column('is_active', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('revoked_at', sa.DateTime(), nullable=True),
        sa.Column('revocation_reason', sa.String(), nullable=True),

        # Constraints
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE')
    )

    # Indexes for User Session
    op.create_index(op.f('ix_user_sessions_id'), 'user_sessions', ['id'], unique=False)
    op.create_index(op.f('ix_user_sessions_user_id'), 'user_sessions', ['user_id'], unique=False)
    op.create_index(op.f('ix_user_sessions_token_hash'), 'user_sessions', ['token_hash'], unique=True)
    op.create_index(op.f('ix_user_sessions_refresh_token_hash'), 'user_sessions', ['refresh_token_hash'], unique=True)
    op.create_index(op.f('ix_user_sessions_is_active'), 'user_sessions', ['is_active'], unique=False)

    # ========================================================================
    # 6. Update Users Table (add security fields)
    # ========================================================================
    op.add_column('users', sa.Column('last_login_at', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column('failed_login_attempts', sa.Integer(), server_default='0', nullable=True))
    op.add_column('users', sa.Column('locked_until', sa.DateTime(), nullable=True))
    op.add_column('users', sa.Column('password_changed_at', sa.DateTime(), server_default=sa.text('NOW()'), nullable=True))
    op.add_column('users', sa.Column('password_expires_at', sa.DateTime(), nullable=True))

    # Add index for user role
    op.create_index(op.f('ix_users_role'), 'users', ['role'], unique=False)

    # ========================================================================
    # 7. Update Orders Table (reference customers, add new fields)
    # ========================================================================

    # Add new order fields
    op.add_column('orders', sa.Column('order_number', sa.String(), nullable=True))
    op.add_column('orders', sa.Column('subtotal', sa.Float(), server_default='0.0', nullable=True))
    op.add_column('orders', sa.Column('tax_rate', sa.Float(), server_default='19.0', nullable=True))
    op.add_column('orders', sa.Column('tax_amount', sa.Float(), server_default='0.0', nullable=True))
    op.add_column('orders', sa.Column('total_amount', sa.Float(), server_default='0.0', nullable=True))
    op.add_column('orders', sa.Column('workflow_state', sa.String(), server_default='draft', nullable=True))
    op.add_column('orders', sa.Column('assigned_to', sa.Integer(), nullable=True))
    op.add_column('orders', sa.Column('priority', sa.String(), server_default='normal', nullable=True))
    op.add_column('orders', sa.Column('started_at', sa.DateTime(), nullable=True))
    op.add_column('orders', sa.Column('completed_at', sa.DateTime(), nullable=True))
    op.add_column('orders', sa.Column('delivered_at', sa.DateTime(), nullable=True))
    op.add_column('orders', sa.Column('cancelled_at', sa.DateTime(), nullable=True))

    # Add foreign key for assigned_to
    op.create_foreign_key('fk_orders_assigned_to_users', 'orders', 'users', ['assigned_to'], ['id'])

    # Create index for order_number
    op.create_index(op.f('ix_orders_order_number'), 'orders', ['order_number'], unique=True)
    op.create_index(op.f('ix_orders_workflow_state'), 'orders', ['workflow_state'], unique=False)

    # ========================================================================
    # 8. Update order_materials association table
    # ========================================================================
    op.add_column('order_materials', sa.Column('quantity', sa.Float(), server_default='1.0', nullable=True))
    op.add_column('order_materials', sa.Column('unit_price_at_time', sa.Float(), nullable=True))

    # ========================================================================
    # 9. Data Migration: Create customers from existing users with orders
    # ========================================================================

    # Note: This data migration should be done carefully in production
    # For now, we'll prepare the structure. Actual data migration will be
    # handled by a separate script to ensure no data loss.

    # We'll add a temporary new customer_id_new column to orders
    # to reference the new customers table
    op.add_column('orders', sa.Column('customer_id_new', sa.Integer(), nullable=True))

    # Add foreign key to new customers table (nullable for now)
    op.create_foreign_key(
        'fk_orders_customer_id_new_customers',
        'orders', 'customers',
        ['customer_id_new'], ['id'],
        ondelete='RESTRICT'
    )

    # ========================================================================
    # 10. Insert Default Retention Policies
    # ========================================================================

    # This will be handled by seed data script, but we define the structure here
    # Example policies:
    # - customer_active: 3650 days (10 years from last order)
    # - financial_records: 3650 days (German tax law §147 AO)
    # - marketing_consent: 730 days (2 years without activity)
    # - audit_logs: 1095 days (3 years minimum for GDPR)


def downgrade():
    """
    Rollback GDPR compliance changes.
    WARNING: This will result in data loss!
    """

    # Remove new order columns
    op.drop_constraint('fk_orders_customer_id_new_customers', 'orders', type_='foreignkey')
    op.drop_column('orders', 'customer_id_new')

    op.drop_index(op.f('ix_orders_workflow_state'), table_name='orders')
    op.drop_index(op.f('ix_orders_order_number'), table_name='orders')

    op.drop_constraint('fk_orders_assigned_to_users', 'orders', type_='foreignkey')

    op.drop_column('orders', 'cancelled_at')
    op.drop_column('orders', 'delivered_at')
    op.drop_column('orders', 'completed_at')
    op.drop_column('orders', 'started_at')
    op.drop_column('orders', 'priority')
    op.drop_column('orders', 'assigned_to')
    op.drop_column('orders', 'workflow_state')
    op.drop_column('orders', 'total_amount')
    op.drop_column('orders', 'tax_amount')
    op.drop_column('orders', 'tax_rate')
    op.drop_column('orders', 'subtotal')
    op.drop_column('orders', 'order_number')

    # Remove order_materials columns
    op.drop_column('order_materials', 'unit_price_at_time')
    op.drop_column('order_materials', 'quantity')

    # Remove user security fields
    op.drop_index(op.f('ix_users_role'), table_name='users')
    op.drop_column('users', 'password_expires_at')
    op.drop_column('users', 'password_changed_at')
    op.drop_column('users', 'locked_until')
    op.drop_column('users', 'failed_login_attempts')
    op.drop_column('users', 'last_login_at')

    # Drop all new tables
    op.drop_index(op.f('ix_user_sessions_is_active'), table_name='user_sessions')
    op.drop_index(op.f('ix_user_sessions_refresh_token_hash'), table_name='user_sessions')
    op.drop_index(op.f('ix_user_sessions_token_hash'), table_name='user_sessions')
    op.drop_index(op.f('ix_user_sessions_user_id'), table_name='user_sessions')
    op.drop_index(op.f('ix_user_sessions_id'), table_name='user_sessions')
    op.drop_table('user_sessions')

    op.drop_index(op.f('ix_data_retention_policies_category'), table_name='data_retention_policies')
    op.drop_index(op.f('ix_data_retention_policies_id'), table_name='data_retention_policies')
    op.drop_table('data_retention_policies')

    op.drop_index(op.f('ix_gdpr_requests_requested_at'), table_name='gdpr_requests')
    op.drop_index(op.f('ix_gdpr_requests_status'), table_name='gdpr_requests')
    op.drop_index(op.f('ix_gdpr_requests_request_type'), table_name='gdpr_requests')
    op.drop_index(op.f('ix_gdpr_requests_customer_id'), table_name='gdpr_requests')
    op.drop_index(op.f('ix_gdpr_requests_id'), table_name='gdpr_requests')
    op.drop_table('gdpr_requests')

    op.drop_index(op.f('ix_customer_audit_logs_request_id'), table_name='customer_audit_logs')
    op.drop_index(op.f('ix_customer_audit_logs_timestamp'), table_name='customer_audit_logs')
    op.drop_index(op.f('ix_customer_audit_logs_action'), table_name='customer_audit_logs')
    op.drop_index(op.f('ix_customer_audit_logs_customer_id'), table_name='customer_audit_logs')
    op.drop_index(op.f('ix_customer_audit_logs_id'), table_name='customer_audit_logs')
    op.drop_table('customer_audit_logs')

    op.drop_index(op.f('ix_customers_is_deleted'), table_name='customers')
    op.drop_index(op.f('ix_customers_data_retention_category'), table_name='customers')
    op.drop_index(op.f('ix_customers_email'), table_name='customers')
    op.drop_index(op.f('ix_customers_customer_number'), table_name='customers')
    op.drop_index(op.f('ix_customers_id'), table_name='customers')
    op.drop_table('customers')
