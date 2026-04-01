"""Update user roles for RBAC system

Revision ID: b1c2d3e4f5g6
Revises: a8b90a411a75
Create Date: 2025-11-09 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b1c2d3e4f5g6'
down_revision: Union[str, None] = 'a8b90a411a75'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Update UserRole enum from (ADMIN, USER) to (ADMIN, GOLDSMITH, VIEWER)."""
    
    # PostgreSQL doesn't allow direct enum modification, so we need to:
    # 1. Create new enum type
    # 2. Alter column to use new type
    # 3. Drop old enum type
    
    # Create new enum with desired values
    op.execute("CREATE TYPE userrole_new AS ENUM ('admin', 'goldsmith', 'viewer')")
    
    # Migrate existing data: USER -> GOLDSMITH
    op.execute("""
        ALTER TABLE users 
        ALTER COLUMN role TYPE userrole_new 
        USING CASE 
            WHEN role::text = 'USER' THEN 'goldsmith'::userrole_new
            WHEN role::text = 'ADMIN' THEN 'admin'::userrole_new
            ELSE 'viewer'::userrole_new
        END
    """)
    
    # Update default value to viewer
    op.execute("ALTER TABLE users ALTER COLUMN role SET DEFAULT 'viewer'::userrole_new")
    
    # Drop old enum type
    op.execute("DROP TYPE userrole")
    
    # Rename new enum to match old name
    op.execute("ALTER TYPE userrole_new RENAME TO userrole")


def downgrade() -> None:
    """Revert UserRole enum from (ADMIN, GOLDSMITH, VIEWER) back to (ADMIN, USER)."""
    
    # Create old enum
    op.execute("CREATE TYPE userrole_new AS ENUM ('ADMIN', 'USER')")
    
    # Migrate data: GOLDSMITH -> USER, VIEWER -> USER, ADMIN -> ADMIN
    op.execute("""
        ALTER TABLE users 
        ALTER COLUMN role TYPE userrole_new 
        USING CASE 
            WHEN role::text = 'admin' THEN 'ADMIN'::userrole_new
            ELSE 'USER'::userrole_new
        END
    """)
    
    # Update default to USER
    op.execute("ALTER TABLE users ALTER COLUMN role SET DEFAULT 'USER'::userrole_new")
    
    # Drop current enum
    op.execute("DROP TYPE userrole")
    
    # Rename old enum back
    op.execute("ALTER TYPE userrole_new RENAME TO userrole")
