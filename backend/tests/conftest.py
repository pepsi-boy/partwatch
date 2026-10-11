"""Shared fixtures.

DB tests run against a real PostgreSQL database named `<db>_test`, created on demand
and migrated with Alembic (so the migrations themselves are exercised). Each test
runs inside a transaction that is rolled back afterwards, so tests never see each
other's data.
"""

import pytest
from sqlalchemy import create_engine, make_url, text
from sqlalchemy.orm import Session

from alembic import command
from alembic.config import Config
from app.config import get_settings


def _test_database_url() -> str:
    url = make_url(get_settings().database_url)
    return url.set(database=f"{url.database}_test").render_as_string(hide_password=False)


def _ensure_database_exists(url: str) -> None:
    target = make_url(url)
    admin = create_engine(target.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": target.database}
        ).scalar()
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{target.database}"'))
    admin.dispose()


@pytest.fixture(scope="session")
def alembic_config() -> Config:
    url = _test_database_url()
    _ensure_database_exists(url)
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


@pytest.fixture(scope="session")
def db_engine(alembic_config):
    command.downgrade(alembic_config, "base")
    command.upgrade(alembic_config, "head")
    engine = create_engine(alembic_config.get_main_option("sqlalchemy.url"))
    yield engine
    engine.dispose()


@pytest.fixture
def db(db_engine):
    connection = db_engine.connect()
    transaction = connection.begin()
    # create_savepoint: code under test can call session.commit() freely; it only
    # releases a savepoint, and the outer transaction is still rolled back below.
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    yield session
    session.close()
    transaction.rollback()
    connection.close()
