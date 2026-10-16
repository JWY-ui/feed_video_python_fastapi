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

    # ---- Agent (app/agent_v3) ----
    # The LLM is reached over the OpenAI-compatible protocol; DeepSeek is the
    # default endpoint. Unlike Redis, the agent has NO degraded mode: without a
    # key the /agent/* routes return 503 rather than silently doing nothing.
    llm_model: str = "deepseek-chat"
    llm_base_url: str = "https://api.deepseek.com/v1"
    openai_api_key: str = ""
    # SDK-level retry + per-request timeout handed to the chat model client.
    agent_llm_max_retries: int = 2
    agent_llm_timeout: float = 60.0
    # Hard budget on one turn, so a looping model cannot run forever or bill
    # without bound. Exceeding tool turns ends the graph with a notice.
    agent_max_tool_turns: int = 8
    # Approximate context budget; older tool results get trimmed past this.
    agent_max_context_tokens: int = 12000
    # Per-thread lock (app/agent_v3/lock.py). TTL must outlive one graph run --
    # a single turn may call the model several times, each with
    # agent_llm_timeout -- or the lock expires mid-run and two runs overlap.
    agent_lock_ttl_seconds: int = 300
    # How long a second run on the same thread waits for the lock before giving
    # up. Long enough to queue behind a normal turn; finite so a wedged run
    # cannot pile up requests forever.
    agent_lock_wait_seconds: int = 120

    # Tell pydantic-settings to load from .env file
    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "extra": "ignore"}


# Global singleton
settings = Settings()
