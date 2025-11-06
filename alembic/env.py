# alembic/env.py

import os
import sys
from pathlib import Path
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# Add the project root to the path so we can import our models
sys.path.append(str(Path(__file__).parents[1]))

# Import models to make them available for autogenerate
from src.goldsmith_erp.db.models import Base

# this reads your alembic.ini
config = context.config

# 1) optional override from the env-var you set in docker-compose:
migration_url = os.getenv("MIGRATION_DATABASE_URL")
if migration_url:
    config.set_main_option("sqlalchemy.url", migration_url)
# otherwise it will fall back to whatever `sqlalchemy.url = …` you already put in alembic.ini

# 2) configure Python logging per alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 3) metadata for `--autogenerate` - use Base from our models
target_metadata = Base.metadata

def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()