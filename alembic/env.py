# alembic/env.py

import os
import sys
from pathlib import Path
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

# if you need your app on the path (for autogenerate), uncomment:
# sys.path.append(str(Path(__file__).parents[1]))

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

# 3) metadata for `--autogenerate` (if you ever use it)
target_metadata = None

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