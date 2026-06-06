# -*- coding: utf-8 -*-
"""
FastAPI application entry point.

Start command:
  uvicorn app.main:app --reload --port 8080

Startup (lifespan):
  1. Connect to MySQL (no database specified) -> CREATE DATABASE IF NOT EXISTS
  2. Connect to target database -> Base.metadata.create_all() create all tables
  3. Connect to Redis (optional, failure is non-blocking)

Shutdown:
  1. Close Redis connection
  2. Dispose MySQL connection pool

Route registration: app.include_router() mounts each module under its prefix.
Rate limiting: injected via rate_limit Depends during include_router.
Static files: app.mount("/static", ...) serves uploaded videos/avatars via URL.
"""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.database import engine, Base
from app.utils.redis_client import redis_client

# Import all Models -- so Base.metadata knows about every table.
# These imports look "unused" but they trigger __init_subclass__ in SQLAlchemy,
# registering each Model in Base.metadata. create_all() needs this registry.
from app.models import (
    Account, Video, OutboxMsg, Like, Comment,
    Social, Tag, VideoTag, Message, Notification,
)  # noqa: F401

# Import all routers
from app.routers.account import public_router as account_public_router
from app.routers.account import protected_router as account_protected_router
from app.routers.video import public_router as video_public_router
from app.routers.video import protected_router as video_protected_router
from app.routers.like import router as like_router
from app.routers.comment import public_router as comment_public_router
from app.routers.comment import protected_router as comment_protected_router
from app.routers.social import router as social_router
from app.routers.feed import public_router as feed_public_router
from app.routers.feed import protected_router as feed_protected_router
from app.routers.message import router as message_router
from app.routers.notification import router as notification_router

# Rate limiting config
from app.middleware.rate_limit import rate_limit

# Login: max 10 per IP per minute (brute force protection)
login_limiter = rate_limit("account_login", 10, 60)
# Register: max 5 per IP per hour (anti-bulk-registration)
register_limiter = rate_limit("account_register", 5, 3600)
# Like: max 30 per account per minute
like_limiter = rate_limit("like_write", 30, 60)
# Comment: max 10 per account per minute
comment_limiter = rate_limit("comment_write", 10, 60)
# Follow: max 20 per account per minute
social_limiter = rate_limit("social_write", 20, 60)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle -- runs automatically at FastAPI startup and shutdown.

    @asynccontextmanager turns an async function into a context manager.
    Code before yield runs at startup, code after yield runs at shutdown.
    """
    from app.config import settings
    import asyncmy

    # Startup: create database if not exists
    # Note: connect without specifying database name, since DB may not exist yet
    try:
        conn = await asyncmy.connect(
            host=settings.mysql_host, port=settings.mysql_port,
            user=settings.mysql_user, password=settings.mysql_password,
        )
        await conn.execute(
            f"CREATE DATABASE IF NOT EXISTS `{settings.mysql_database}` "
            f"DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
        await conn.ensure_closed()
    except Exception:
        pass  # Can't reach MySQL -- table creation step will surface the real error

    # Startup: auto-create tables
    # Base.metadata.create_all() checks each table, creates if missing.
    # Note: only creates tables, does NOT alter existing ones.
    # If Model fields change, manual ALTER or drop-recreate is needed.
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Startup: connect to Redis (optional, failure is non-blocking)
    await redis_client.connect()
    if redis_client.available:
        print("Redis connected")
    else:
        print("Redis unavailable -- running in degraded mode")

    yield  # Application is running -- requests are processed after this line

    # Shutdown: clean up resources
    await redis_client.close()
    await engine.dispose()


# FastAPI instance -- this is the 'app' object uvicorn looks for
app = FastAPI(
    title="Feed Video System",
    description="Short video feed API",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS config
# Frontend may run on different port (localhost:5173 vs localhost:8080 = cross-origin)
# Without CORS middleware, browsers block all cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],       # Restrict to specific domains in production
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static file serving
# Uploaded videos/avatars/covers are stored in uploads/ directory.
# After mount, files are accessible via http://localhost:8080/static/videos/1/20240601/abc.mp4
app.mount("/static", StaticFiles(directory="uploads"), name="static")

# Register all routes (44 endpoints)
# Each include_router mounts one module under its URL prefix.
# 'tags' parameter groups routes in Swagger docs.

# Account: 12 endpoints (register/login/query/rename/change-password/logout/avatar/bio)
app.include_router(account_public_router, prefix="/account", tags=["1. Account"])
app.include_router(account_protected_router, prefix="/account", tags=["1. Account"])

# Video: 9 endpoints (upload/publish/chunk/detail)
app.include_router(video_public_router, prefix="/video", tags=["2. Video"])
app.include_router(video_protected_router, prefix="/video", tags=["2. Video"])

# Like: 4 endpoints + rate limiting
app.include_router(like_router, prefix="/like", tags=["3. Like"],
                   dependencies=[Depends(like_limiter)])

# Comment: 3 endpoints (listAll public, publish/delete need login + rate limiting)
app.include_router(comment_public_router, prefix="/comment", tags=["4. Comment"])
app.include_router(comment_protected_router, prefix="/comment", tags=["4. Comment"],
                   dependencies=[Depends(comment_limiter)])

# Social: 5 endpoints + rate limiting
app.include_router(social_router, prefix="/social", tags=["5. Follow"],
                   dependencies=[Depends(social_limiter)])

# Feed: 5 feed types (soft auth -- browsing allowed without login)
app.include_router(feed_public_router, prefix="/feed", tags=["6. Feed"])
app.include_router(feed_protected_router, prefix="/feed", tags=["6. Feed"])

# Message: 2 endpoints (send/list)
app.include_router(message_router, prefix="/message", tags=["7. Message"])

# Notification: 4 endpoints (SSE real-time push / list / mark-read / count)
app.include_router(notification_router, prefix="/notification", tags=["8. Notification"])


@app.get("/healthz")
async def healthz():
    """
    Health check endpoint -- for load balancer / K8s liveness probe.

    Returns {"status": "ok"} meaning the service is alive and can handle HTTP.
    Does not check DB connectivity -- add DB ping for a more thorough check.
    """
    return {"status": "ok"}
