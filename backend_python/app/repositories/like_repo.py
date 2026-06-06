# -*- coding: utf-8 -*-
"""Like data access layer."""
from sqlalchemy import select, func, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.like import Like
from app.models.video import Video


def _video_to_dict(v: Video) -> dict:
    return {
        "id": v.id, "author_id": v.author_id, "username": v.username,
        "title": v.title, "description": v.description,
        "play_url": v.play_url, "cover_url": v.cover_url,
        "create_time": v.create_time.isoformat() if v.create_time else "",
        "likes_count": v.likes_count, "popularity": v.popularity,
    }


class LikeRepository:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def is_liked(self, video_id: int, account_id: int) -> bool:
        stmt = select(func.count()).select_from(Like).where(
            Like.video_id == video_id, Like.account_id == account_id
        )
        result = await self.db.execute(stmt)
        return result.scalar() > 0

    async def create_ignore_duplicate(self, **kwargs) -> bool:
        """Returns True=newly created, False=already exists."""
        if await self.is_liked(kwargs["video_id"], kwargs["account_id"]):
            return False
        self.db.add(Like(**kwargs))
        return True

    async def delete_by_video_and_account(self, video_id: int, account_id: int) -> bool:
        stmt = delete(Like).where(Like.video_id == video_id, Like.account_id == account_id)
        result = await self.db.execute(stmt)
        return result.rowcount > 0

    async def batch_get_liked(self, video_ids: list[int], account_id: int) -> dict[int, bool]:
        if not video_ids or account_id == 0:
            return {}
        stmt = select(Like.video_id).where(
            Like.video_id.in_(video_ids), Like.account_id == account_id
        )
        result = await self.db.execute(stmt)
        liked_ids = {row[0] for row in result.all()}
        return {vid: vid in liked_ids for vid in video_ids}

    async def list_liked_videos(self, account_id: int) -> list[dict]:
        if account_id == 0:
            return []
        stmt = (
            select(Video)
            .join(Like, Like.video_id == Video.id)
            .where(Like.account_id == account_id)
            .order_by(Like.created_at.desc())
            .limit(200)
        )
        result = await self.db.execute(stmt)
        return [_video_to_dict(r) for r in result.scalars().all()]
