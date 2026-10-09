# -*- coding: utf-8 -*-
"""
Account data access layer (Repository).

The only place that imports SQLAlchemy Models.
All methods return dicts or primitives, never Model objects.
Internally uses Redis -> MySQL self-healing, transparent to callers.
"""
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.utils.redis_client import redis_client
from app.utils.sql import escape_like

CACHE_TTL = 86400
REVOKED_TTL = 60
REFRESH_TTL = 7 * 86400


def _to_dict(row: Account) -> dict:
    """Model -> dict. Upper layers never see SQLAlchemy objects."""
    return {
        "id": row.id,
        "username": row.username,
        "password": row.password,
        "token": row.token,
        "refresh_token": row.refresh_token,
        "avatar_url": row.avatar_url,
        "bio": row.bio,
    }


class AccountRepository:

    def __init__(self, db: AsyncSession):
        self.db = db

    # ---- Create ----

    async def create(self, username: str, password_hash: str) -> None:
        """Create user -- pass values, not a Model object.

        flush() is deliberate: it forces the unique-username constraint to fire
        HERE, inside the request, so the router's `except IntegrityError` can
        turn it into a 409. Without it the INSERT is only sent by the commit in
        get_db()'s teardown -- which FastAPI runs AFTER the response is sent, so
        the caller would receive "account created" for a duplicate username and
        the rollback would happen behind its back.
        """
        self.db.add(Account(username=username, password=password_hash))
        await self.db.flush()

    # ---- Read ----

    async def find_by_id(self, account_id: int) -> dict | None:
        """Look up by PK -- returns dict or None."""
        row = await self.db.get(Account, account_id)
        return _to_dict(row) if row else None

    async def find_by_username(self, username: str) -> dict | None:
        """Look up by username -- returns dict or None."""
        stmt = select(Account).where(Account.username == username)
        result = await self.db.execute(stmt)
        row = result.scalar_one_or_none()
        return _to_dict(row) if row else None

    async def search(self, query: str, limit: int = 10) -> list[dict]:
        """Fuzzy username search -- returns candidates, never raises.

        Exact matches sort first: the model asked for "小明" and will usually take
        the first candidate, so "小明" must outrank "小明123". The LIKE wildcards
        in `query` are escaped -- searching "%" must not match every account.
        """
        pattern = f"%{escape_like(query)}%"
        stmt = (
            select(Account)
            .where(Account.username.like(pattern))
            .order_by((Account.username == query).desc(), Account.id.asc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return [_to_dict(row) for row in result.scalars().all()]

    # ---- Token cache ----

    async def get_token_cache(self, account_id: int) -> str | None:
        """
        Check token cache -- Redis first, fallback to MySQL with write-back.
        Returns token string, "REVOKED", or None (user doesn't exist).
        """
        if redis_client.available:
            cached = await redis_client.get(
                redis_client.key("account:%d", account_id)
            )
            if cached is not None:
                return cached

        user = await self.find_by_id(account_id)
        if user is None:
            if redis_client.available:
                await redis_client.set(
                    redis_client.key("account:%d", account_id),
                    "REVOKED", ex=REVOKED_TTL,
                )
            return None

        if redis_client.available:
            await redis_client.set(
                redis_client.key("account:%d", account_id),
                user["token"], ex=CACHE_TTL,
            )

        return user["token"]

    async def set_token_cache(self, account_id: int, token: str) -> None:
        """Write token cache."""
        if redis_client.available:
            await redis_client.set(
                redis_client.key("account:%d", account_id), token, ex=CACHE_TTL,
            )

    async def revoke_token_cache(self, account_id: int) -> None:
        """Revoke token cache."""
        if redis_client.available:
            await redis_client.set(
                redis_client.key("account:%d", account_id), "REVOKED", ex=REVOKED_TTL,
            )

    async def set_refresh_cache(self, account_id: int, refresh_token: str) -> None:
        """Write refresh token cache."""
        if redis_client.available:
            await redis_client.set(
                redis_client.key("account:%d:refresh", account_id),
                refresh_token, ex=REFRESH_TTL,
            )
            await redis_client.set(
                redis_client.key("refresh:%s", refresh_token),
                str(account_id), ex=REFRESH_TTL,
            )

    # ---- Update ----

    async def update_token(self, account_id: int, token: str, refresh_token: str) -> None:
        """Login/refresh -- write dual tokens (MySQL + Redis)."""
        stmt = (
            update(Account)
            .where(Account.id == account_id)
            .values(token=token, refresh_token=refresh_token)
        )
        await self.db.execute(stmt)
        await self.set_token_cache(account_id, token)
        await self.set_refresh_cache(account_id, refresh_token)

    async def clear_token(self, account_id: int) -> None:
        """Logout -- clear dual tokens (MySQL + Redis revoke marker)."""
        stmt = (
            update(Account)
            .where(Account.id == account_id)
            .values(token="", refresh_token="")
        )
        await self.db.execute(stmt)
        await self.revoke_token_cache(account_id)

    async def update_password(self, account_id: int, new_password_hash: str) -> None:
        """Change password (MySQL + revoke Redis cache)."""
        stmt = (
            update(Account)
            .where(Account.id == account_id)
            .values(password=new_password_hash)
        )
        await self.db.execute(stmt)
        await self.revoke_token_cache(account_id)

    async def rename(self, account_id: int, new_username: str, new_token: str) -> None:
        """Rename + update token in MySQL. Caller updates the Redis cache.

        flush() is deliberate -- same reason as create(): the unique-username
        constraint must fire inside the request so the caller can report 409
        instead of silently succeeding and rolling back afterwards.

        The Redis write deliberately does NOT happen here: if the flush raises,
        the transaction rolls back but Redis would already hold the new token,
        leaving cache and DB disagreeing. The caller writes the cache only after
        this returns without raising.
        """
        await self.db.execute(
            update(Account)
            .where(Account.id == account_id)
            .values(username=new_username, token=new_token)
        )
        await self.db.flush()

    async def update_avatar(self, account_id: int, avatar_url: str) -> None:
        await self.db.execute(
            update(Account).where(Account.id == account_id).values(avatar_url=avatar_url)
        )

    async def update_fields(self, account_id: int, **kwargs) -> None:
        await self.db.execute(
            update(Account).where(Account.id == account_id).values(**kwargs)
        )
