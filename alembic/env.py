# alembic/env.py

import os
import sys
from pathlib import Path
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# Add the parent directory to sys.path so we can import our models
sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

# this reads your alembic.ini
config = context.config

# 1) optional override from the env-var you set in docker-compose:
migration_url = os.getenv("MIGRATION_DATABASE_URL")
if migration_url:
    config.set_main_option("sqlalchemy.url", migration_url)
# otherwise it will fall back to whatever `sqlalchemy.url = …` you already put in alembic.ini

# 2) configure Python logging per alembic.ini
if config.config_file_name is not None:
    # disable_existing_loggers defaults to True, which silently disables every
    # goldsmith_erp.* logger created before a migration runs in-process (the
    # PostgreSQL round-trip test in CI) and empties caplog for later tests.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# 3) Import models for autogenerate support
from goldsmith_erp.db.models import Base

# 4) metadata for `--autogenerate`
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