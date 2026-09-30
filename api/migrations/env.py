"""Alembic environment.

The database URL comes from, in order of precedence:

1. ``sqlalchemy.url`` set programmatically on the Alembic config (used by tests)
2. the ``DATABASE_URL`` environment variable
3. ``DATABASE_URL`` from the application settings (.env file)

Option 2 means migrations can run with nothing but a database URL configured;
the rest of the application settings are not required.
"""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import create_engine, pool

from parcelpulse_api.models import Base

config = context.config

if config.config_file_name is not None and config.attributes.get("configure_logger", True):
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _database_url() -> str:
    configured = config.get_main_option("sqlalchemy.url")
    if configured:
        return configured
    from_environment = os.environ.get("DATABASE_URL")
    if from_environment:
        return from_environment
    from parcelpulse_api.config import get_settings

    return get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_database_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
