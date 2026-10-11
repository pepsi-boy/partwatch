"""PartWatch can live in its own Postgres schema inside a shared database."""

import pytest
from sqlalchemy import create_engine, inspect, text

from alembic import command
from alembic.config import Config
from app.config import Settings
from app.db import connect_args

SCHEMA = "partwatch_schema_test"


@pytest.fixture
def schema_config(alembic_config):
    cfg = Config("alembic.ini")
    cfg.set_main_option("sqlalchemy.url", alembic_config.get_main_option("sqlalchemy.url"))
    cfg.set_main_option("db_schema", SCHEMA)
    engine = create_engine(cfg.get_main_option("sqlalchemy.url"))
    yield cfg, engine
    with engine.begin() as conn:
        conn.execute(text(f'DROP SCHEMA IF EXISTS "{SCHEMA}" CASCADE'))
    engine.dispose()


def test_migrations_create_tables_in_own_schema(schema_config):
    cfg, engine = schema_config

    command.upgrade(cfg, "head")

    tables = set(inspect(engine).get_table_names(schema=SCHEMA))
    assert {"parts", "price_snapshots", "deals", "job_runs", "alembic_version"} <= tables

    command.downgrade(cfg, "base")
    assert "parts" not in inspect(engine).get_table_names(schema=SCHEMA)


def test_app_connections_use_schema(schema_config):
    cfg, engine = schema_config
    command.upgrade(cfg, "head")

    app_engine = create_engine(
        cfg.get_main_option("sqlalchemy.url"), connect_args=connect_args(SCHEMA)
    )
    with app_engine.begin() as conn:
        conn.execute(text("INSERT INTO parts (sku, name, category) VALUES ('1', 'x', 'gpu')"))
        found = conn.execute(text(f'SELECT count(*) FROM "{SCHEMA}".parts')).scalar()
    app_engine.dispose()
    assert found == 1


def test_no_schema_means_default_search_path():
    assert connect_args("") == {}


@pytest.mark.parametrize("bad", ["Partwatch", "part-watch", "x; DROP TABLE parts", "1abc"])
def test_schema_name_is_validated(bad):
    with pytest.raises(ValueError):
        Settings(db_schema=bad)
