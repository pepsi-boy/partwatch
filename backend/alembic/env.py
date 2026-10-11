from logging.config import fileConfig

from sqlalchemy import create_engine, pool, text

from alembic import context
from app import models  # noqa: F401  (registers tables on Base.metadata)
from app.config import get_settings
from app.db import Base, connect_args

config = context.config

if config.config_file_name is not None:
    # Keep the app's loggers enabled when migrations run in-process (e.g. tests).
    fileConfig(config.config_file_name, disable_existing_loggers=False)

# The URL comes from DATABASE_URL, never from alembic.ini, so no credentials are
# committed. Tests set sqlalchemy.url explicitly to point at the test database.
if not config.get_main_option("sqlalchemy.url"):
    config.set_main_option("sqlalchemy.url", get_settings().database_url)

target_metadata = Base.metadata

# Tests override the schema the same way they override the URL.
schema = config.get_main_option("db_schema", get_settings().db_schema)


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = create_engine(
        config.get_main_option("sqlalchemy.url"),
        poolclass=pool.NullPool,
        connect_args=connect_args(schema),
    )
    with connectable.connect() as connection:
        if schema:
            connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{schema}"'))
            connection.commit()
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # Keep alembic_version in our schema too, so it can't collide with another
            # app's migrations in a shared database.
            version_table_schema=schema or None,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
