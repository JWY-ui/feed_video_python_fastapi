# -*- coding: utf-8 -*-
"""
Database engine + session factory + ORM base -- MySQL entry point for the entire project.

Tech stack:
  - SQLAlchemy 2.0 async: native async/await, non-blocking with FastAPI event loop
  - asyncmy driver: pure Python impl, no MySQL C client needed
  - async_sessionmaker: one independent session per HTTP request

Data flow:
  HTTP request -> Depends(get_db) -> create AsyncSession -> inject into Router
  -> Router -> Service -> Repo -> Repo executes SQL via self.db
  -> success -> get_db() auto-commit -> session closed
  -> exception -> get_db() auto-rollback -> session closed
"""
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

# Build connection string
# charset=utf8mb4 is required for emoji support (utf8 only supports 3-byte chars)
DATABASE_URL = (
    f"mysql+asyncmy://{settings.mysql_user}:{settings.mysql_password}"
    f"@{settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database}"
    f"?charset=utf8mb4"
)

# Create async engine
# echo=False: no SQL logging (set to True for debugging)
# pool_size=10: keep up to 10 idle connections
# max_overflow=20: up to 20 extra connections when pool is full (30 total)
engine = create_async_engine(DATABASE_URL, echo=False, pool_size=10, max_overflow=20)

# Session factory -- not a session itself, but a factory that creates sessions
# expire_on_commit=False: keep object attributes accessible after commit
AsyncSessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    """
    Base class for all ORM Models.

    Any class that maps to a database table must inherit from Base.
    This is how SQLAlchemy discovers and manages tables.

    Usage:
      class Account(Base):
          __tablename__ = "accounts"
          id: Mapped[int] = mapped_column(primary_key=True)
          ...
    """
    pass


async def get_db():
    """
    FastAPI dependency injection -- one independent session per request.

    Usage: add `db: AsyncSession = Depends(get_db)` to Router function params.

    Why per-request?
      - Sessions are not thread-safe; sharing causes data corruption
      - Each request commits/rollbacks independently
      - Connection is returned to pool automatically when done

    How yield works:
      - Code before yield runs at "request start"
      - yield produces the session object, injected into Router
      - Code after yield runs at "request end" (auto commit/rollback)

    Router doesn't need manual commit -- get_db handles it.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session          # inject into Router
            await session.commit() # success -> commit
        except Exception:
            await session.rollback()  # error -> rollback
            raise                     # re-raise for Router's error handler
        # async with exit calls session.close(), returns connection to pool
