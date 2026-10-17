# -*- coding: utf-8 -*-
"""Like data access layer."""
from sqlalchemy import and_, delete, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.like import Like
from app.models.video import Video
from app.utils.timeutil import as_utc


def _video_to_dict(v: Video) -> dict:
    return {
        "id": v.id, "author_id": v.author_id, "username": v.username,
        "title": v.title, "description": v.description,
        "play_url": v.play_url, "cover_url": v.cover_url,
        # Emit the offset so any datetime.fromisoformat() downstream lands on an
        # aware value -- the column itself only holds a naive UTC wall clock.
        "create_time": as_utc(v.create_time).isoformat() if v.create_time else "",
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
        """
        Returns True=newly created, False=already exists.

        Check-then-insert has a race window under concurrency.
        We catch IntegrityError at flush time as the DB-level last line of defense,
        and return False (already liked) instead of crashing with 500.
        """
        if await self.is_liked(kwargs["video_id"], kwargs["account_id"]):
            return False
        self.db.add(Like(**kwargs))
        try:
            await self.db.flush()
            return True
        except IntegrityError:
            return False

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

    async def list_liked_videos(self, account_id: int, limit: int = 200,
                                before_time=None, before_id: int | None = None) -> list[dict]:
        """My liked videos, keyset-paginated by (like.created_at, like.id).

        The cursor is the previous page's last item; both parts are required so
        videos liked in the same second cannot repeat or be skipped. `like_id`
        and `liked_at` are returned on every item for the client to pass back.
        """
        if account_id == 0:
            return []
        stmt = (
            select(Video, Like.id.label("like_id"),
                   Like.created_at.label("liked_at"))
            .join(Like, Like.video_id == Video.id)
            .where(Like.account_id == account_id)
        )
        if before_time is not None and before_id is not None:
            stmt = stmt.where(
                or_(
                    Like.created_at < before_time,
                    and_(Like.created_at == before_time, Like.id < before_id),
                )
            )
        stmt = stmt.order_by(Like.created_at.desc(), Like.id.desc()).limit(limit)

        rows = (await self.db.execute(stmt)).all()
        items = []
        for video, like_id, liked_at in rows:
            item = _video_to_dict(video)
            item["like_id"] = like_id
            item["liked_at"] = as_utc(liked_at).isoformat() if liked_at else ""
            items.append(item)
        return items
