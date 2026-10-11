"""Application settings, loaded from environment variables (and .env if present)."""

import re
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    bestbuy_api_key: str = ""
    # Celery rate limit per worker. Best Buy allows 5 calls/sec per key, so with
    # N workers set this to about 4/N per second.
    bestbuy_rate_limit: str = "4/s"
    database_url: str = "postgresql+psycopg://partwatch:partwatch@localhost:5432/partwatch"
    # Optional Postgres schema for all tables. Lets PartWatch share a database with
    # another app (Render allows one free database per workspace). Empty = public.
    db_schema: str = ""
    redis_url: str = "redis://localhost:6379/0"

    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    alert_email_to: str = ""

    admin_token: str = ""

    check_interval_hours: float = 3
    deal_threshold_percent: float = 10
    min_snapshots_for_deal: int = 5

    @field_validator("db_schema")
    @classmethod
    def safe_schema_name(cls, name: str) -> str:
        # The name ends up in SQL (CREATE SCHEMA, search_path), so allow only plain identifiers.
        if name and not re.fullmatch(r"[a-z_][a-z0-9_]{0,62}", name):
            raise ValueError("DB_SCHEMA must be lowercase letters, digits, and underscores")
        return name

    @field_validator("database_url")
    @classmethod
    def use_psycopg_driver(cls, url: str) -> str:
        """Render (and most hosts) hand out postgres:// or postgresql:// URLs. SQLAlchemy
        needs the driver named explicitly to use psycopg 3."""
        for prefix in ("postgres://", "postgresql://"):
            if url.startswith(prefix):
                return "postgresql+psycopg://" + url.removeprefix(prefix)
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
