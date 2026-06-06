# -*- coding: utf-8 -*-
"""
Global config -- the single source of truth for all settings.

Usage:
    from app.config import settings
    print(settings.mysql_host)

Why pydantic-settings instead of os.environ?
  1. Auto-loads from .env file
  2. Environment variables override .env values (Docker/K8s friendly)
  3. Type validation (port is int, not str)
  4. IDE autocompletion
"""
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings -- all fields have defaults, overridable via .env or env vars."""

    # Server port, default 8080.
    server_port: int = 8080

    # MySQL connection
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = "123456"
    mysql_database: str = "feedsystem"

    # JWT signing key -- MUST override in production!
    # Generate: python -c "import secrets; print(secrets.token_hex(32))"
    jwt_secret: str = "change-me-to-a-random-string"

    # Redis cache (optional -- app degrades gracefully if unavailable)
    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str | None = None
    redis_db: int = 0

    # Tell pydantic-settings to load from .env file
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


# Global singleton
settings = Settings()
