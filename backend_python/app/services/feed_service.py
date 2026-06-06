"""
Feed 流核心算法

五种 Feed 流，listLatest 和 listByPopularity 支持 Redis 冷热分离：
  - 热数据走 Redis ZSET（毫秒级）
  - 冷数据降级 MySQL（索引保证几十毫秒）
  - Redis 不可用 → 全走 MySQL（降级容错）
"""
import asyncio
from datetime import datetime

from app.repositories.feed_repo import FeedRepository
from app.repositories.like_repo import LikeRepository
from app.schemas.feed import (
    FeedAuthor, FeedVideoItem,
    ListLatestResponse, ListLikesCountResponse,
    ListByPopularityResponse, ListByFollowingResponse,
)
from app.utils.redis_client import redis_client

# 全局时间线 ZSET 的 key
TIMELINE_KEY = "feed:global_timeline"
# ZSET 保留的最大条目数
TIMELINE_MAX_SIZE = 1000

# 防止并发重建 ZSET 的锁
_rebuild_lock = asyncio.Lock()


class FeedService:

    def __init__(self, repo: FeedRepository, like_repo: LikeRepository):
        self.repo = repo
        self.like_repo = like_repo

    # ═══════════════════ 最新视频流 ═══════════════════

    async def list_latest(self, limit: int, latest_time_ms: int,
                          viewer_id: int) -> ListLatestResponse:
        """
        最新视频流——带 Redis 冷热分离

        热数据：Redis ZSET feed:global_timeline（score = create_time 毫秒）
        冷数据：MySQL idx_videos_create_time 索引

        游标 > ZSET 最老 score → 热，走 Redis
        游标 ≤ ZSET 最老 score → 冷，走 MySQL
        Redis 不可用 → 全走 MySQL
        """
        # ━━ 纯 MySQL 路径（Redis 不可用时）━━━
        if not redis_client.available:
            return await self._list_latest_from_mysql(limit, latest_time_ms, viewer_id)

        # ━━ Redis 路径 ━━
        # 1. 获取水位线：ZSET 中最老一条的 score
        tail = await redis_client.zrange_with_scores(TIMELINE_KEY, 0, 0)

        # 2. ZSET 为空 → 尝试重建
        if not tail:
            return await self._rebuild_and_retry(limit, latest_time_ms, viewer_id)

        watermark = int(tail[0][1])   # ZSET 中最老的时间
        cursor = latest_time_ms if latest_time_ms > 0 else float("inf")

        # 3. 冷数据：游标已经翻到比 ZSET 更老的位置 → 直接查 MySQL
        if cursor <= watermark:
            return await self._list_latest_from_mysql(limit, latest_time_ms, viewer_id)

        # 4. 热数据：从 Redis ZSET 取
        max_score = "+inf" if latest_time_ms == 0 else str(cursor - 1)
        video_ids_str = await redis_client.zrevrangebyscore(
            TIMELINE_KEY, max_score, "-inf", 0, limit,
        )

        video_ids = [int(s) for s in video_ids_str]

        # 5. 批量取完整视频数据
        hot_videos = await self.repo.get_by_ids(video_ids) if video_ids else []

        # 6. 热数据不够 → 拼接冷数据（stitch）
        if len(hot_videos) < limit:
            cold_cursor = hot_videos[-1]["create_time"] if hot_videos else datetime.utcfromtimestamp(latest_time_ms / 1000)
            cold_videos = await self.repo.list_latest(limit - len(hot_videos), cold_cursor)
            hot_videos.extend(cold_videos)

        items = await self._build_items(hot_videos, viewer_id)
        next_time = 0
        if hot_videos and len(hot_videos) == limit:
            next_time = int(hot_videos[-1]["create_time"].timestamp() * 1000)

        return ListLatestResponse(
            video_list=items, next_time=next_time, has_more=len(hot_videos) == limit,
        )

    async def _list_latest_from_mysql(self, limit, latest_time_ms, viewer_id):
        """纯 MySQL 回退路径"""
        before = datetime.utcfromtimestamp(latest_time_ms / 1000) if latest_time_ms > 0 else None
        videos = await self.repo.list_latest(limit, before)
        items = await self._build_items(videos, viewer_id)
        next_time = 0
        if videos and len(videos) == limit:
            next_time = int(videos[-1]["create_time"].timestamp() * 1000)
        return ListLatestResponse(video_list=items, next_time=next_time, has_more=len(videos) == limit)

    async def _rebuild_and_retry(self, limit, latest_time_ms, viewer_id):
        """
        ZSET 为空时重建时间线

        用 asyncio.Lock 保证只有一个请求去 MySQL 捞数据重建 ZSET。
        其他请求等锁释放后重试（此时 ZSET 已有数据）。
        """
        async with _rebuild_lock:
            # 双重检查：可能别的请求已经重建好了
            card = await redis_client.zcard(TIMELINE_KEY)
            if card > 0:
                return await self.list_latest(limit, latest_time_ms, viewer_id)

            # 从 MySQL 捞最新 1000 条
            db_videos = await self.repo.list_latest(TIMELINE_MAX_SIZE, None)
            if not db_videos:
                return ListLatestResponse(video_list=[], next_time=0, has_more=False)

            # 写入 ZSET
            mapping = {
                str(v["id"]): v["create_time"].timestamp() * 1000
                for v in db_videos
            }
            await redis_client.zadd(TIMELINE_KEY, mapping)

            # 重试
            return await self.list_latest(limit, latest_time_ms, viewer_id)

    # ═══════════════ 点赞排行 ═══════════════════

    async def list_likes_count(self, limit: int,
                                likes_before: int | None, id_before: int | None,
                                viewer_id: int) -> ListLikesCountResponse:
        videos = await self.repo.list_likes_count(limit, likes_before, id_before)
        items = await self._build_items(videos, viewer_id)
        resp = ListLikesCountResponse(video_list=items, has_more=len(videos) == limit)
        if videos and len(videos) == limit:
            resp.next_likes_count_before = videos[-1]["likes_count"]
            resp.next_id_before = videos[-1]["id"]
        return resp

    # ═══════════════════ 热度榜 ═══════════════════

    async def list_by_popularity(self, limit: int, as_of: int, offset: int,
                                  viewer_id: int,
                                  popularity_before: int | None,
                                  time_before: str | None,
                                  id_before: int | None) -> ListByPopularityResponse:
        """
        热度榜——带 Redis 滑动窗口快照

        Redis 路径：
          1. 合并最近 60 个分钟窗口 ZSET（ZUNIONSTORE）
          2. 从合并快照分页取（ZREVRANGE + offset）
          3. 根据 ID 批量查 MySQL 补全字段

        MySQL 路径（Redis 不可用）：
          三元复合游标 (popularity, create_time, id)
        """
        # ━━ Redis 滑动窗口快照 ━━
        if redis_client.available:
            now = datetime.utcnow().replace(second=0, microsecond=0)
            if as_of > 0:
                now = datetime.utcfromtimestamp(as_of).replace(second=0, microsecond=0)

            # 最近 60 个分钟窗口
            window_keys = []
            for i in range(60):
                ts = int((now.timestamp() - i * 60))
                key = redis_client.key("hot:video:1m:%s",
                                       datetime.utcfromtimestamp(ts).strftime("%Y%m%d%H%M"))
                window_keys.append(key)

            dest = redis_client.key("hot:video:merge:1m:%s", now.strftime("%Y%m%d%H%M"))

            # 只在 offset=0 时生成快照（翻页复用同一个快照）
            if offset == 0:
                await redis_client.zunionstore(dest, window_keys, "SUM")

            # 从快照分页取
            members = await redis_client.zrevrange(dest, offset, offset + limit - 1)
            if members:
                ids = [int(m) for m in members]
                videos = await self.repo.get_by_ids(ids)
                # 按 ZSET 顺序排列
                by_id = {v["id"]: v for v in videos}
                ordered = [by_id[i] for i in ids if i in by_id]
                items = await self._build_items(ordered, viewer_id)
                return ListByPopularityResponse(
                    video_list=items, as_of=int(now.timestamp()),
                    next_offset=offset + len(items), has_more=len(items) == limit,
                )

        # ━━ MySQL 回退路径 ━━
        tb = datetime.fromisoformat(time_before) if time_before else None
        videos = await self.repo.list_by_popularity(limit, popularity_before, tb, id_before)
        items = await self._build_items(videos, viewer_id)
        resp = ListByPopularityResponse(
            video_list=items, as_of=0, next_offset=0, has_more=len(videos) == limit,
        )
        if videos and len(videos) == limit:
            last = videos[-1]
            resp.next_latest_popularity = last["popularity"]
            resp.next_latest_before = last["create_time"].isoformat() if last["create_time"] else None
            resp.next_latest_id_before = last["id"]
        return resp

    # ═══════════════════ 关注流 ═══════════════════

    async def list_by_following(self, limit: int, latest_time: int,
                                 viewer_id: int) -> ListByFollowingResponse:
        before = datetime.utcfromtimestamp(latest_time) if latest_time > 0 else None
        videos = await self.repo.list_by_following(limit, viewer_id, before)
        items = await self._build_items(videos, viewer_id)
        next_time = 0
        if videos and len(videos) == limit:
            next_time = int(videos[-1]["create_time"].timestamp())
        return ListByFollowingResponse(video_list=items, next_time=next_time, has_more=len(videos) == limit)

    # ═══════════════════ 话题流 ═══════════════════

    async def list_by_tag(self, tag_name: str, limit: int, viewer_id: int) -> list[FeedVideoItem]:
        videos = await self.repo.list_by_tag(tag_name, limit)
        return await self._build_items(videos, viewer_id)

    # ═══════════════════ 构建 Feed 条目 ═══════════════════

    async def _build_items(self, videos: list[dict], viewer_id: int) -> list[FeedVideoItem]:
        if not videos:
            return []
        video_ids = [v["id"] for v in videos]
        liked_map = await self.like_repo.batch_get_liked(video_ids, viewer_id)
        return [
            FeedVideoItem(
                id=v["id"],
                author=FeedAuthor(id=v["author_id"], username=v["username"]),
                title=v["title"], description=v.get("description"),
                play_url=v["play_url"], cover_url=v["cover_url"],
                create_time=int(v["create_time"].timestamp()) if v["create_time"] else 0,
                likes_count=v["likes_count"],
                is_liked=liked_map.get(v["id"], False),
            )
            for v in videos
        ]

    # ═══════════════════ 时间线写入（发布视频时调用）═══════════════════

    async def add_to_timeline(self, video_id: int, create_time: datetime) -> None:
        """
        发布视频时写入全局时间线 ZSET

        同时修剪超过 TIMELINE_MAX_SIZE 的旧数据。
        """
        if not redis_client.available:
            return
        score = create_time.timestamp() * 1000
        await redis_client.zadd(TIMELINE_KEY, {str(video_id): score})
        # 修剪：保留最新 1000 条
        card = await redis_client.zcard(TIMELINE_KEY)
        if card > TIMELINE_MAX_SIZE:
            # ZREMRANGEBYRANK 删除最旧的
            if redis_client._available:
                try:
                    await redis_client._redis.zremrangebyrank(
                        TIMELINE_KEY, 0, card - TIMELINE_MAX_SIZE - 1
                    )
                except Exception:
                    pass
