"""Video 数据访问层"""
from sqlalchemy import select, func, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.video import Video, OutboxMsg
from app.models.tag import Tag, VideoTag


def _to_dict(v: Video) -> dict:
    return {
        "id": v.id, "author_id": v.author_id, "username": v.username,
        "title": v.title, "description": v.description,
        "play_url": v.play_url, "cover_url": v.cover_url,
        "create_time": v.create_time.isoformat() if v.create_time else "",
        "likes_count": v.likes_count, "popularity": v.popularity,
    }


class VideoRepository:

    def __init__(self, db: AsyncSession):
        self.db = db

    # ━━━ 增 ━━━
    async def create(self, **kwargs) -> int:
        v = Video(**kwargs)
        self.db.add(v)
        await self.db.flush()
        return v.id

    async def create_outbox_msg(self, **kwargs) -> None:
        self.db.add(OutboxMsg(**kwargs))

    async def create_tag_if_not_exists(self, name: str) -> dict:
        stmt = select(Tag).where(Tag.name == name)
        result = await self.db.execute(stmt)
        tag = result.scalar_one_or_none()
        if tag is None:
            tag = Tag(name=name)
            self.db.add(tag)
            await self.db.flush()
        return {"id": tag.id, "name": tag.name}

    async def create_video_tag(self, video_id: int, tag_id: int) -> None:
        self.db.add(VideoTag(video_id=video_id, tag_id=tag_id))

    # ━━━ 删 ━━━
    async def delete_video(self, video_id: int) -> None:
        stmt = delete(Video).where(Video.id == video_id)
        await self.db.execute(stmt)

    # ━━━ 查 ━━━
    async def get_by_id(self, video_id: int) -> dict | None:
        row = await self.db.get(Video, video_id)
        return _to_dict(row) if row else None

    async def is_exist(self, video_id: int) -> bool:
        v = await self.db.get(Video, video_id)
        return v is not None

    async def list_by_author(self, author_id: int, limit: int = 200) -> list[dict]:
        stmt = (
            select(Video)
            .where(Video.author_id == author_id)
            .order_by(Video.create_time.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return [_to_dict(r) for r in result.scalars().all()]

    async def count_by_author(self, author_id: int) -> int:
        stmt = select(func.count()).select_from(Video).where(Video.author_id == author_id)
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    async def total_likes_by_author(self, author_id: int) -> int:
        stmt = (
            select(func.coalesce(func.sum(Video.likes_count), 0))
            .where(Video.author_id == author_id)
        )
        result = await self.db.execute(stmt)
        return result.scalar() or 0

    # ━━━ 改 ━━━
    async def change_likes_count(self, video_id: int, delta: int) -> None:
        await self.db.execute(
            update(Video).where(Video.id == video_id)
            .values(likes_count=func.greatest(Video.likes_count + delta, 0))
        )

    async def change_popularity(self, video_id: int, delta: int) -> None:
        await self.db.execute(
            update(Video).where(Video.id == video_id)
            .values(popularity=func.greatest(Video.popularity + delta, 0))
        )
