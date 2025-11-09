"""Add user role column for RBAC

Revision ID: a8b90a411a75
Revises: a35005826b5d
Create Date: 2025-11-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a8b90a411a75'
down_revision: Union[str, None] = 'a35005826b5d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add role column to users table for RBAC."""
    # Create UserRole enum
    user_role_enum = sa.Enum('ADMIN', 'USER', name='userrole', create_type=True)
    user_role_enum.create(op.get_bind())

    # Add role column with default value 'user'
    op.add_column(
        'users',
        sa.Column('role', user_role_enum, nullable=False, server_default='USER')
    )

    # Create index on role column for faster lookups
    op.create_index(op.f('ix_users_role'), 'users', ['role'], unique=False)


def downgrade() -> None:
    """Remove role column from users table."""
    # Drop index
    op.drop_index(op.f('ix_users_role'), table_name='users')

    # Drop column
    op.drop_column('users', 'role')

    # Drop enum type
    sa.Enum(name='userrole').drop(op.get_bind())
