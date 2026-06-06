# -*- coding: utf-8 -*-
"""
Feed core algorithms.

Five feed types. listLatest and listByPopularity support Redis hot-cold separation:
  - Hot data uses Redis ZSET (millisecond latency)
  - Cold data falls back to MySQL (index ensures tens of ms)
  - Redis unavailable -> all MySQL (degradation tolerance)
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

# Global timeline ZSET key
TIMELINE_KEY = "feed:global_timeline"
# Max entries retained in ZSET
TIMELINE_MAX_SIZE = 1000

# Lock to prevent concurrent ZSET rebuilds
_rebuild_lock = asyncio.Lock()


class FeedService:

    def __init__(self, repo: FeedRepository, like_repo: LikeRepository):
        self.repo = repo
        self.like_repo = like_repo

    # ==================== Latest feed ====================

    async def list_latest(self, limit: int, latest_time_ms: int,
                          viewer_id: int) -> ListLatestResponse:
        """
        Latest feed -- with Redis hot-cold separation.

        Hot: Redis ZSET feed:global_timeline (score = create_time ms).
        Cold: MySQL idx_videos_create_time index.

        Cursor > ZSET oldest score -> hot, use Redis
        Cursor <= ZSET oldest score -> cold, use MySQL
        Redis unavailable -> all MySQL
        """
        # Pure MySQL path (Redis unavailable)
        if not redis_client.available:
            return await self._list_latest_from_mysql(limit, latest_time_ms, viewer_id)

        # Redis path
        # 1. Get watermark: oldest score in ZSET
        tail = await redis_client.zrange_with_scores(TIMELINE_KEY, 0, 0)

        # 2. ZSET empty -> try rebuild
        if not tail:
            return await self._rebuild_and_retry(limit, latest_time_ms, viewer_id)

        watermark = int(tail[0][1])   # oldest time in ZSET
        cursor = latest_time_ms if latest_time_ms > 0 else float("inf")

        # 3. Cold data: cursor has paged beyond what's in ZSET -> query MySQL directly
        if cursor <= watermark:
            return await self._list_latest_from_mysql(limit, latest_time_ms, viewer_id)

        # 4. Hot data: fetch from Redis ZSET
        max_score = "+inf" if latest_time_ms == 0 else str(cursor - 1)
        video_ids_str = await redis_client.zrevrangebyscore(
            TIMELINE_KEY, max_score, "-inf", 0, limit,
        )

        video_ids = [int(s) for s in video_ids_str]

        # 5. Batch-fetch full video data
        hot_videos = await self.repo.get_by_ids(video_ids) if video_ids else []

        # 6. Hot data insufficient -> stitch with cold data
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
        """Pure MySQL fallback path."""
        before = datetime.utcfromtimestamp(latest_time_ms / 1000) if latest_time_ms > 0 else None
        videos = await self.repo.list_latest(limit, before)
        items = await self._build_items(videos, viewer_id)
        next_time = 0
        if videos and len(videos) == limit:
            next_time = int(videos[-1]["create_time"].timestamp() * 1000)
        return ListLatestResponse(video_list=items, next_time=next_time, has_more=len(videos) == limit)

    async def _rebuild_and_retry(self, limit, latest_time_ms, viewer_id):
        """
        Rebuild timeline when ZSET is empty.

        Uses asyncio.Lock to ensure only one request fetches from MySQL to rebuild.
        Other requests wait for lock release, then retry (ZSET now has data).
        """
        async with _rebuild_lock:
            # Double-check: another request may have already rebuilt
            card = await redis_client.zcard(TIMELINE_KEY)
            if card > 0:
                return await self.list_latest(limit, latest_time_ms, viewer_id)

            # Fetch latest 1000 from MySQL
            db_videos = await self.repo.list_latest(TIMELINE_MAX_SIZE, None)
            if not db_videos:
                return ListLatestResponse(video_list=[], next_time=0, has_more=False)

            # Write to ZSET
            mapping = {
                str(v["id"]): v["create_time"].timestamp() * 1000
                for v in db_videos
            }
            await redis_client.zadd(TIMELINE_KEY, mapping)

            # Retry
            return await self.list_latest(limit, latest_time_ms, viewer_id)

    # ==================== Most-liked feed ====================

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

    # ==================== Hot ranking feed ====================

    async def list_by_popularity(self, limit: int, as_of: int, offset: int,
                                  viewer_id: int,
                                  popularity_before: int | None,
                                  time_before: str | None,
                                  id_before: int | None) -> ListByPopularityResponse:
        """
        Hot ranking -- with Redis sliding window snapshot.

        Redis path:
          1. Merge last 60 minute-window ZSETs (ZUNIONSTORE)
          2. Paginate from merged snapshot (ZREVRANGE + offset)
          3. Batch-fetch full fields from MySQL by IDs

        MySQL path (Redis unavailable):
          Triple compound cursor (popularity, create_time, id)
        """
        # Redis sliding window snapshot
        if redis_client.available:
            now = datetime.utcnow().replace(second=0, microsecond=0)
            if as_of > 0:
                now = datetime.utcfromtimestamp(as_of).replace(second=0, microsecond=0)

            # Last 60 minute windows
            window_keys = []
            for i in range(60):
                ts = int((now.timestamp() - i * 60))
                key = redis_client.key("hot:video:1m:%s",
                                       datetime.utcfromtimestamp(ts).strftime("%Y%m%d%H%M"))
                window_keys.append(key)

            dest = redis_client.key("hot:video:merge:1m:%s", now.strftime("%Y%m%d%H%M"))

            # Only generate snapshot on offset=0 (pagination reuses same snapshot)
            if offset == 0:
                await redis_client.zunionstore(dest, window_keys, "SUM")

            # Paginate from snapshot
            members = await redis_client.zrevrange(dest, offset, offset + limit - 1)
            if members:
                ids = [int(m) for m in members]
                videos = await self.repo.get_by_ids(ids)
                # Maintain ZSET order
                by_id = {v["id"]: v for v in videos}
                ordered = [by_id[i] for i in ids if i in by_id]
                items = await self._build_items(ordered, viewer_id)
                return ListByPopularityResponse(
                    video_list=items, as_of=int(now.timestamp()),
                    next_offset=offset + len(items), has_more=len(items) == limit,
                )

        # MySQL fallback path
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

    # ==================== Following feed ====================

    async def list_by_following(self, limit: int, latest_time: int,
                                 viewer_id: int) -> ListByFollowingResponse:
        before = datetime.utcfromtimestamp(latest_time) if latest_time > 0 else None
        videos = await self.repo.list_by_following(limit, viewer_id, before)
        items = await self._build_items(videos, viewer_id)
        next_time = 0
        if videos and len(videos) == limit:
            next_time = int(videos[-1]["create_time"].timestamp())
        return ListByFollowingResponse(video_list=items, next_time=next_time, has_more=len(videos) == limit)

    # ==================== Tag feed ====================

    async def list_by_tag(self, tag_name: str, limit: int, viewer_id: int) -> list[FeedVideoItem]:
        videos = await self.repo.list_by_tag(tag_name, limit)
        return await self._build_items(videos, viewer_id)

    # ==================== Build feed items ====================

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

    # ==================== Timeline write (called on video publish) ====================

    async def add_to_timeline(self, video_id: int, create_time: datetime) -> None:
        """
        Write to global timeline ZSET on video publish.

        Also trims old data exceeding TIMELINE_MAX_SIZE.
        """
        if not redis_client.available:
            return
        score = create_time.timestamp() * 1000
        await redis_client.zadd(TIMELINE_KEY, {str(video_id): score})
        # Trim: keep latest 1000
        card = await redis_client.zcard(TIMELINE_KEY)
        if card > TIMELINE_MAX_SIZE:
            # ZREMRANGEBYRANK removes the oldest entries
            if redis_client._available:
                try:
                    await redis_client._redis.zremrangebyrank(
                        TIMELINE_KEY, 0, card - TIMELINE_MAX_SIZE - 1
                    )
                except Exception:
                    pass
