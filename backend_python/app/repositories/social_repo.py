# -*- coding: utf-8 -*-
"""Social data access layer."""
from sqlalchemy import select, func, delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.social import Social
from app.models.account import Account


def _account_to_dict(a: Account) -> dict:
    return {
        "id": a.id, "username": a.username,
        "avatar_url": a.avatar_url, "bio": a.bio,
    }


class SocialRepository:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def follow(self, follower_id: int, vlogger_id: int) -> bool:
        """
        Returns True=followed, False=already following (concurrent duplicate).

        Flush immediately to catch IntegrityError from the unique constraint
        at this point rather than during commit, giving the caller a clean result.
        """
        self.db.add(Social(follower_id=follower_id, vlogger_id=vlogger_id))
        try:
            await self.db.flush()
            return True
        except IntegrityError:
            return False

    async def unfollow(self, follower_id: int, vlogger_id: int) -> None:
        await self.db.execute(
            delete(Social).where(
                Social.follower_id == follower_id, Social.vlogger_id == vlogger_id
            )
        )

    async def is_followed(self, follower_id: int, vlogger_id: int) -> bool:
        stmt = select(func.count()).select_from(Social).where(
            Social.follower_id == follower_id, Social.vlogger_id == vlogger_id
        )
        result = await self.db.execute(stmt)
        return result.scalar() > 0

    async def get_all_followers(self, vlogger_id: int) -> list[dict]:
        stmt = select(Social.follower_id).where(Social.vlogger_id == vlogger_id).limit(200)
        result = await self.db.execute(stmt)
        ids = [row[0] for row in result.all()]
        if not ids:
            return []
        stmt2 = select(Account).where(Account.id.in_(ids))
        result2 = await self.db.execute(stmt2)
        return [_account_to_dict(r) for r in result2.scalars().all()]

    async def get_all_vloggers(self, follower_id: int) -> list[dict]:
        stmt = select(Social.vlogger_id).where(Social.follower_id == follower_id).limit(200)
        result = await self.db.execute(stmt)
        ids = [row[0] for row in result.all()]
        if not ids:
            return []
        stmt2 = select(Account).where(Account.id.in_(ids))
        result2 = await self.db.execute(stmt2)
        return [_account_to_dict(r) for r in result2.scalars().all()]

    async def count_followers(self, vlogger_id: int) -> int:
        stmt = select(func.count()).select_from(Social).where(Social.vlogger_id == vlogger_id)
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    async def count_vloggers(self, follower_id: int) -> int:
        stmt = select(func.count()).select_from(Social).where(Social.follower_id == follower_id)
        result = await self.db.execute(stmt)
        return result.scalar() or 0
