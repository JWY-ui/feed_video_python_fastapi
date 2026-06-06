"""
Feed 流数据访问层——5 种 Feed 流的核心 SQL。

每条 SQL 都对应一个特定的查询模式，走不同的索引。

Model → dict 转换在这里完成——上层永远看不到 SQLAlchemy Model。
"""
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.video import Video
from app.models.social import Social
from app.models.tag import Tag, VideoTag


def _to_dict(v: Video) -> dict:
    """SQLAlchemy Model → 普通 dict——上层不需要知道 ORM 的存在"""
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

    # ═══════════════════ 1. 最新视频流 ═══════════════════

    async def list_latest(self, limit: int, before: datetime | None) -> list[dict]:
        """
        最新视频——游标分页。

        SQL:
          SELECT * FROM videos
          WHERE create_time < ?          -- 游标（before）。首页不传，翻页传上页最后一条的时间
          ORDER BY create_time DESC
          LIMIT ?

        走的索引：idx_videos_create_time（降序）
        为什么这个索引够用？WHERE 和 ORDER BY 都是 create_time，索引一次覆盖。

        参数：
          before=None → 首页（取最新的 N 条）
          before=某时间 → 翻页（取该时间之前的 N 条）
        """
        stmt = select(Video).order_by(Video.create_time.desc())
        if before is not None:
            stmt = stmt.where(Video.create_time < before)
        stmt = stmt.limit(limit)
        result = await self.db.execute(stmt)
        return [_to_dict(r) for r in result.scalars().all()]

    # ═══════════════════ 2. 点赞排行 ═══════════════════

    async def list_likes_count(self, limit: int,
                                likes_before: int | None,
                                id_before: int | None) -> list[dict]:
        """
        点赞排行——复合游标分页 (likes_count DESC, id DESC)。

        SQL:
          SELECT * FROM videos
          WHERE (likes_count < 100)                       -- 点赞更少
             OR (likes_count = 100 AND id < 50)           -- 点赞相同，ID 更小
          ORDER BY likes_count DESC, id DESC
          LIMIT ?

        为什么需要复合游标？
          点赞数相同的视频排序不稳定——这次第 5 名是视频 A，下次翻页可能又是 A。
          加上 id 作为第二排序键后排序唯一且可复现，翻页不重不漏。

        走的索引：idx_videos_likes_count_id (likes_count DESC, id DESC)
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

    # ═══════════════════ 3. 热度榜 ═══════════════════

    async def list_by_popularity(self, limit: int,
                                  popularity_before: int | None,
                                  time_before: datetime | None,
                                  id_before: int | None) -> list[dict]:
        """
        热度榜——三元复合游标 (popularity DESC, create_time DESC, id DESC)。

        SQL:
          SELECT * FROM videos
          WHERE (popularity < 1000)
             OR (popularity = 1000 AND create_time < '2024-06-03')
             OR (popularity = 1000 AND create_time = '2024-06-03' AND id < 50)
          ORDER BY popularity DESC, create_time DESC, id DESC
          LIMIT ?

        为什么需要三元？
          popularity 相同 → 用 create_time 区分（热度相同时，越新越靠前）
          popularity + create_time 都相同 → 用 id 区分（几乎不会发生，但加了保证绝对稳定）

        走的索引：idx_videos_popularity_time_id

        三个参数要么全传（翻页），要么全不传（首页）。
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

    # ═══════════════════ 4. 关注流 ═══════════════════

    async def list_by_following(self, limit: int, viewer_id: int,
                                before: datetime | None) -> list[dict]:
        """
        关注流——子查询聚合。

        SQL:
          SELECT * FROM videos
          WHERE author_id IN (
              SELECT vlogger_id FROM socials WHERE follower_id = ?   -- 我关注了谁
          )
          ORDER BY create_time DESC
          LIMIT ?

        MySQL 对 IN 子查询的优化：先执行子查询拿到 vlogger_id 列表，
        再对每个 vlogger_id 走 author_id 索引查视频。

        走的索引：socials.follower_id（子查询）+ videos.author_id（外层）
        """
        stmt = select(Video).order_by(Video.create_time.desc())
        if viewer_id > 0:
            # 子查询：我关注的所有 UP 主 ID
            sub = select(Social.vlogger_id).where(Social.follower_id == viewer_id)
            stmt = stmt.where(Video.author_id.in_(sub))
        if before is not None:
            stmt = stmt.where(Video.create_time < before)  # 游标
        stmt = stmt.limit(limit)
        result = await self.db.execute(stmt)
        return [_to_dict(r) for r in result.scalars().all()]

    # ═══════════════════ 5. 批量查视频 ═══════════════════

    async def get_by_ids(self, ids: list[int]) -> list[dict]:
        """
        按 ID 列表批量取视频。

        用途：
          - Redis ZSET 返回视频 ID 列表后，用此方法批量取完整数据
          - 热度榜快照返回 ID 列表后，用此方法补全字段

        SQL:
          SELECT * FROM videos WHERE id IN (101, 102, 103, ...)

        走主键索引——最快的查询方式。
        """
        if not ids:
            return []
        stmt = select(Video).where(Video.id.in_(ids))
        result = await self.db.execute(stmt)
        return [_to_dict(r) for r in result.scalars().all()]

    # ═══════════════════ 6. 话题流 ═══════════════════

    async def list_by_tag(self, tag_name: str, limit: int) -> list[dict]:
        """
        话题流——三表 JOIN。

        SQL:
          SELECT v.* FROM videos v
          JOIN video_tags vt ON vt.video_id = v.id
          JOIN tags t ON t.id = vt.tag_id
          WHERE t.name = '美食'
          ORDER BY v.create_time DESC
          LIMIT ?

        执行计划：
          1. tags.name 唯一索引 → 快速找到 '美食' 的 tag_id
          2. video_tags.tag_id 索引 → 找到所有带该标签的视频 ID
          3. videos.id 主键 → 取完整视频数据

        为什么用 JOIN 而不用逗号分隔字段（如 tag_list = "美食,旅游"）？
          逗号分隔无法建索引 → WHERE 只能全表扫描 → 数据量大了会非常慢。
          多对多关联表可以建索引 → 查询走索引而不是全表扫描。
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
