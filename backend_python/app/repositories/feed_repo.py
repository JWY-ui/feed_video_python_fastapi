# -*- coding: utf-8 -*-
"""
Feed data access layer -- core SQL for 5 feed types.

Each SQL corresponds to a specific query pattern, using different indexes.
Model -> dict conversion happens here -- upper layers never see SQLAlchemy Models.
"""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.video import Video
from app.models.social import Social
from app.models.tag import Tag, VideoTag


def _to_dict(v: Video) -> dict:
    """SQLAlchemy Model -> plain dict. Upper layers don't need to know about ORM."""
    return {
        "id": v.id, "author_id": v.author_id, "username": v.username,
        "title": v.title, "description": v.description,
        "play_url": v.play_url, "cover_url": v.cover_url,
        "create_time": v.create_time,
        "likes_count": v.likes_count, "popularity": v.popularity,
    }


class FeedRepository:

    def __init__(self, db: AsyncSession):
        self.db = db

    # ==================== 1. Latest feed ====================

    async def list_latest(self, limit: int, before: datetime | None) -> list[dict]:
        """
        Latest videos -- cursor pagination.

        SQL:
          SELECT * FROM videos
          WHERE create_time < ?          -- cursor (before). First page: no WHERE.
          ORDER BY create_time DESC
          LIMIT ?

        Uses index: idx_videos_create_time (descending).
        Covers both WHERE and ORDER BY on create_time, single index is enough.

        Args:
          before=None -> first page (newest N)
          before=some_time -> next page (N items before that time)
        """
        stmt = select(Video).order_by(Video.create_time.desc())
        if before is not None:
            stmt = stmt.where(Video.create_time < before)
        stmt = stmt.limit(limit)
        result = await self.db.execute(stmt)
        return [_to_dict(r) for r in result.scalars().all()]

    # ==================== 2. Most-liked feed ====================

    async def list_likes_count(self, limit: int,
                                likes_before: int | None,
                                id_before: int | None) -> list[dict]:
        """
        Most-liked -- compound cursor pagination (likes_count DESC, id DESC).

        SQL:
          SELECT * FROM videos
          WHERE (likes_count < 100)
             OR (likes_count = 100 AND id < 50)
          ORDER BY likes_count DESC, id DESC
          LIMIT ?

        Why compound cursor?
          Videos with the same like count have unstable ordering -- #5 might be
          video A this time, and video A again next page. Adding id as secondary
          sort key makes ordering unique and reproducible, no gaps or dups.

        Uses index: idx_videos_likes_count_id (likes_count DESC, id DESC).
        """
        stmt = select(Video).order_by(Video.likes_count.desc(), Video.id.desc())
        if likes_before is not None and id_before is not None:
            stmt = stmt.where(
                (Video.likes_count < likes_before) |
                ((Video.likes_count == likes_before) & (Video.id < id_before))
            )
        stmt = stmt.limit(limit)
        result = await self.db.execute(stmt)
        return [_to_dict(r) for r in result.scalars().all()]

    # ==================== 3. Hot ranking feed ====================

    async def list_by_popularity(self, limit: int,
                                  popularity_before: int | None,
                                  time_before: datetime | None,
                                  id_before: int | None) -> list[dict]:
        """
        Hot ranking -- triple compound cursor (popularity DESC, create_time DESC, id DESC).

        SQL:
          SELECT * FROM videos
          WHERE (popularity < 1000)
             OR (popularity = 1000 AND create_time < '2024-06-03')
             OR (popularity = 1000 AND create_time = '2024-06-03' AND id < 50)
          ORDER BY popularity DESC, create_time DESC, id DESC
          LIMIT ?

        Why triple?
          Same popularity -> use create_time to break ties (newer ranks higher).
          Same popularity + create_time -> use id (almost never happens, but guarantees stability).

        Uses index: idx_videos_popularity_time_id.

        Three params either all passed (next page) or all None (first page).
        """
        stmt = select(Video).order_by(
            Video.popularity.desc(), Video.create_time.desc(), Video.id.desc()
        )
        if popularity_before is not None and time_before is not None and id_before is not None:
            stmt = stmt.where(
                (Video.popularity < popularity_before) |
                ((Video.popularity == popularity_before) & (Video.create_time < time_before)) |
                ((Video.popularity == popularity_before) & (Video.create_time == time_before) & (Video.id < id_before))
            )
        stmt = stmt.limit(limit)
        result = await self.db.execute(stmt)
        return [_to_dict(r) for r in result.scalars().all()]

    # ==================== 4. Following feed ====================

    async def list_by_following(self, limit: int, viewer_id: int,
                                before: datetime | None) -> list[dict]:
        """
        Following feed -- subquery aggregation.

        SQL:
          SELECT * FROM videos
          WHERE author_id IN (
              SELECT vlogger_id FROM socials WHERE follower_id = ?   -- who I follow
          )
          ORDER BY create_time DESC
          LIMIT ?

        MySQL optimizes IN subquery: runs subquery to get vlogger_id list first,
        then for each vlogger_id uses author_id index to find videos.

        Uses indexes: socials.follower_id (subquery) + videos.author_id (outer).
        """
        stmt = select(Video).order_by(Video.create_time.desc())
        if viewer_id > 0:
            # Subquery: all vlogger IDs I follow
            sub = select(Social.vlogger_id).where(Social.follower_id == viewer_id)
            stmt = stmt.where(Video.author_id.in_(sub))
        if before is not None:
            stmt = stmt.where(Video.create_time < before)  # cursor
        stmt = stmt.limit(limit)
        result = await self.db.execute(stmt)
        return [_to_dict(r) for r in result.scalars().all()]

    # ==================== 5. Batch get by IDs ====================

    async def get_by_ids(self, ids: list[int]) -> list[dict]:
        """
        Batch fetch videos by ID list.

        Uses:
          - Redis ZSET returns video ID list, then this method fetches full data
          - Hot ranking snapshot returns IDs, this method fills in full fields

        SQL:
          SELECT * FROM videos WHERE id IN (101, 102, 103, ...)

        Uses PK index -- the fastest query.
        """
        if not ids:
            return []
        stmt = select(Video).where(Video.id.in_(ids))
        result = await self.db.execute(stmt)
        return [_to_dict(r) for r in result.scalars().all()]

    # ==================== 6. Tag feed ====================

    async def list_by_tag(self, tag_name: str, limit: int) -> list[dict]:
        """
        Tag feed -- three-table JOIN.

        SQL:
          SELECT v.* FROM videos v
          JOIN video_tags vt ON vt.video_id = v.id
          JOIN tags t ON t.id = vt.tag_id
          WHERE t.name = 'food'
          ORDER BY v.create_time DESC
          LIMIT ?

        Execution plan:
          1. tags.name unique index -> quickly find 'food' tag_id
          2. video_tags.tag_id index -> find all video IDs with that tag
          3. videos.id PK -> fetch full video data

        Why JOIN instead of comma-separated field (e.g. tag_list = "food,travel")?
          Comma-separated can't be indexed -> WHERE only full table scan -> slow at scale.
          Many-to-many junction table can be indexed -> queries use indexes.
        """
        stmt = (
            select(Video)
            .join(VideoTag, VideoTag.video_id == Video.id)
            .join(Tag, Tag.id == VideoTag.tag_id)
            .where(Tag.name == tag_name)
            .order_by(Video.create_time.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return [_to_dict(r) for r in result.scalars().all()]
