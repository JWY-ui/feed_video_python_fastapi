"""
Account 数据访问层（Repository）

唯一能 import SQLAlchemy Model 的地方。
所有方法返回 dict 或基本类型，绝不返回 Model 对象。
内部用 Redis → MySQL 自愈，调用方无感知。
"""
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.utils.redis_client import redis_client

CACHE_TTL = 86400
REVOKED_TTL = 60
REFRESH_TTL = 7 * 86400


def _to_dict(row: Account) -> dict:
    """Model → dict，上层永远看不到 SQLAlchemy 对象"""
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

    # ━━━ 增 ━━━

    async def create(self, username: str, password_hash: str) -> None:
        """创建用户——传值不传 Model"""
        self.db.add(Account(username=username, password=password_hash))

    # ━━━ 查 ━━━

    async def find_by_id(self, account_id: int) -> dict | None:
        """按主键查——返回 dict 或 None"""
        row = await self.db.get(Account, account_id)
        return _to_dict(row) if row else None

    async def find_by_username(self, username: str) -> dict | None:
        """按用户名查——返回 dict 或 None"""
        stmt = select(Account).where(Account.username == username)
        result = await self.db.execute(stmt)
        row = result.scalar_one_or_none()
        return _to_dict(row) if row else None



    # ━━━ Token 缓存 ━━━

    async def get_token_cache(self, account_id: int) -> str | None:
        """
        查 Token 缓存——优先 Redis，未命中降级 MySQL 并回写
        返回 token 字符串、"REVOKED" 或 None（用户不存在）
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
        """写 Token 缓存"""
        if redis_client.available:
            await redis_client.set(
                redis_client.key("account:%d", account_id), token, ex=CACHE_TTL,
            )

    async def revoke_token_cache(self, account_id: int) -> None:
        """撤销 Token 缓存"""
        if redis_client.available:
            await redis_client.set(
                redis_client.key("account:%d", account_id), "REVOKED", ex=REVOKED_TTL,
            )

    async def set_refresh_cache(self, account_id: int, refresh_token: str) -> None:
        """写 Refresh Token 缓存"""
        if redis_client.available:
            await redis_client.set(
                redis_client.key("account:%d:refresh", account_id),
                refresh_token, ex=REFRESH_TTL,
            )
            await redis_client.set(
                redis_client.key("refresh:%s", refresh_token),
                str(account_id), ex=REFRESH_TTL,
            )

    # ━━━ 改 ━━━

    async def update_token(self, account_id: int, token: str, refresh_token: str) -> None:
        """登录/刷新时写双 Token（MySQL + Redis）"""
        stmt = (
            update(Account)
            .where(Account.id == account_id)
            .values(token=token, refresh_token=refresh_token)
        )
        await self.db.execute(stmt)
        await self.set_token_cache(account_id, token)
        await self.set_refresh_cache(account_id, refresh_token)

    async def clear_token(self, account_id: int) -> None:
        """登出时清空双 Token（MySQL + Redis 标记撤销）"""
        stmt = (
            update(Account)
            .where(Account.id == account_id)
            .values(token="", refresh_token="")
        )
        await self.db.execute(stmt)
        await self.revoke_token_cache(account_id)

    async def update_password(self, account_id: int, new_password_hash: str) -> None:
        """改密（MySQL + 撤销 Redis 缓存）"""
        stmt = (
            update(Account)
            .where(Account.id == account_id)
            .values(password=new_password_hash)
        )
        await self.db.execute(stmt)
        await self.revoke_token_cache(account_id)

    async def rename(self, account_id: int, new_username: str, new_token: str) -> None:
        """改名 + 更新 token（MySQL + Redis）"""
        await self.db.execute(
            update(Account).where(Account.id == account_id).values(username=new_username)
        )
        await self.db.execute(
            update(Account).where(Account.id == account_id).values(token=new_token)
        )
        await self.set_token_cache(account_id, new_token)

    async def update_avatar(self, account_id: int, avatar_url: str) -> None:
        await self.db.execute(
            update(Account).where(Account.id == account_id).values(avatar_url=avatar_url)
        )

    async def update_fields(self, account_id: int, **kwargs) -> None:
        await self.db.execute(
            update(Account).where(Account.id == account_id).values(**kwargs)
        )
