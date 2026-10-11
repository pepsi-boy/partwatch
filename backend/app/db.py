"""SQLAlchemy engine and session setup."""

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


def connect_args(schema: str) -> dict:
    """Point every connection at `schema` via the Postgres search_path, so models
    need no schema prefix and the same code works with or without one."""
    return {"options": f"-csearch_path={schema}"} if schema else {}


# pool_pre_ping checks a pooled connection is still alive before handing it out,
# so a database restart doesn't surface as errors on the next few requests.
engine = create_engine(
    get_settings().database_url,
    pool_pre_ping=True,
    connect_args=connect_args(get_settings().db_schema),
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
