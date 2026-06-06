# -*- coding: utf-8 -*-
"""
Video business logic -- entire chain operates on primitives and dicts.
"""
import os
import secrets
import shutil
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.video_repo import VideoRepository
from app.utils.redis_client import redis_client
from app.utils.tag_parser import extract_tags


class VideoService:

    def __init__(self, repo: VideoRepository, db: AsyncSession):
        self.repo = repo
        self.db = db

    async def publish(self, author_id: int, username: str,
                      title: str, description: str,
                      play_url: str, cover_url: str) -> dict:
        video_id = await self.repo.create(
            author_id=author_id, username=username,
            title=title.strip(), description=description.strip(),
            play_url=play_url.strip(), cover_url=cover_url.strip(),
            create_time=datetime.now(datetime.UTC),
        )
        await self.repo.create_outbox_msg(
            video_id=video_id, event_type="video_published",
            create_time=datetime.now(datetime.UTC), status="pending",
        )
        tags = extract_tags(f"{title} {description}")
        for tag_name in tags:
            tag = await self.repo.create_tag_if_not_exists(tag_name)
            await self.repo.create_video_tag(video_id, tag["id"])
        return await self.repo.get_by_id(video_id)

    async def delete(self, video_id: int, author_id: int) -> None:
        """
        Delete video -- only the author can delete.

        Also proactively invalidates Redis cache (consistency guarantee).
        Without invalidation, users would see "deleted" videos for up to 5 minutes.
        """
        video = await self.repo.get_by_id(video_id)
        if video is None:
            raise ValueError("video not found")
        if video["author_id"] != author_id:
            raise PermissionError("not the author")
        await self.repo.delete_video(video_id)
        # Proactive cache invalidation -- consistency paired with write operations
        if redis_client.available:
            await redis_client.delete(redis_client.key("video:detail:%d", video_id))

    async def get_detail(self, video_id: int) -> dict:
        """
        Video detail -- with Redis cache + anti-stampede lock + random TTL.

        Three-layer protection:
          1. Cache avalanche protection -> random TTL (300 +/- 30 sec), no simultaneous expiry
          2. Cache stampede protection -> SETNX mutex lock, only 1 request fills cache
          3. Cache penetration protection -> cache null marker for non-existent videos (60 sec)

        Video update/delete proactively DEL cache to maintain consistency.
        """
        import json
        cache_key = redis_client.key("video:detail:%d", video_id)

        # Layer 1: Check cache
        if redis_client.available:
            cached = await redis_client.get(cache_key)
            if cached == "__NULL__":
                raise ValueError("video not found")  # penetration protection: no repeat MySQL query for 60s
            if cached:
                return json.loads(cached)

        # Layer 2: Acquire lock (anti-stampede)
        if redis_client.available:
            lock_key = redis_client.key("lock:video:detail:%d", video_id)
            locked = await redis_client.set(lock_key, "1", ex=3, nx=True)

            if locked:
                # Got lock -> fetch from source + backfill
                try:
                    # Double-check: maybe someone already backfilled
                    cached = await redis_client.get(cache_key)
                    if cached:
                        if cached == "__NULL__":
                            raise ValueError("video not found")
                        return json.loads(cached)

                    video = await self.repo.get_by_id(video_id)
                    if video is None:
                        await redis_client.set(cache_key, "__NULL__", ex=60)  # null value cache
                        raise ValueError("video not found")

                    import random
                    ttl = 300 + random.randint(0, 60)  # 5 min +/- 60 sec random
                    await redis_client.set(cache_key, json.dumps(video), ex=ttl)
                    return video
                finally:
                    await redis_client.delete(lock_key)

            else:
                # Didn't get lock -> wait for others to backfill
                import asyncio
                for _ in range(5):
                    await asyncio.sleep(0.02)  # wait 20ms
                    cached = await redis_client.get(cache_key)
                    if cached and cached != "__NULL__":
                        return json.loads(cached)
                # Waited 100ms with no result -> query MySQL directly (fallback, prevents infinite wait if lock holder crashes)

        # Layer 3: MySQL fallback
        video = await self.repo.get_by_id(video_id)
        if video is None:
            raise ValueError("video not found")
        return video

    async def list_by_author(self, author_id: int) -> list[dict]:
        return await self.repo.list_by_author(author_id)

    @staticmethod
    def save_upload(file_data: bytes, filename: str, subdir: str,
                    author_id: int, allowed_exts: set[str], max_size: int) -> str:
        if len(file_data) == 0 or len(file_data) > max_size:
            raise ValueError(f"invalid file size, max {max_size // (1024*1024)}MB")
        _, ext = os.path.splitext(filename)
        ext = ext.lower()
        if ext not in allowed_exts:
            raise ValueError(f"only {allowed_exts} allowed")
        date_str = datetime.now(datetime.UTC).strftime("%Y%m%d")
        dir_path = os.path.join("uploads", subdir, str(author_id), date_str)
        os.makedirs(dir_path, exist_ok=True)
        new_filename = secrets.token_hex(16) + ext
        filepath = os.path.join(dir_path, new_filename)
        with open(filepath, "wb") as f:
            f.write(file_data)
        return f"/static/{subdir}/{author_id}/{date_str}/{new_filename}"

    @staticmethod
    def save_chunk(upload_id: str, chunk_index: int, chunk_data: bytes) -> str:
        tmp_dir = os.path.join("uploads", "tmp", upload_id)
        os.makedirs(tmp_dir, exist_ok=True)
        chunk_path = os.path.join(tmp_dir, f"{chunk_index:06d}")
        with open(chunk_path, "wb") as f:
            f.write(chunk_data)
        return chunk_path

    @staticmethod
    def merge_chunks(upload_id: str, total_chunks: int, filename: str,
                     author_id: int) -> str:
        tmp_dir = os.path.join("uploads", "tmp", upload_id)
        date_str = datetime.now(datetime.UTC).strftime("%Y%m%d")
        out_dir = os.path.join("uploads", "videos", str(author_id), date_str)
        os.makedirs(out_dir, exist_ok=True)
        _, ext = os.path.splitext(filename)
        new_filename = secrets.token_hex(16) + ext
        out_path = os.path.join(out_dir, new_filename)
        with open(out_path, "wb") as out:
            for i in range(total_chunks):
                chunk_path = os.path.join(tmp_dir, f"{i:06d}")
                if not os.path.exists(chunk_path):
                    raise ValueError(f"chunk {i} missing")
                with open(chunk_path, "rb") as chunk_file:
                    out.write(chunk_file.read())
        shutil.rmtree(tmp_dir, ignore_errors=True)
        return f"/static/videos/{author_id}/{date_str}/{new_filename}"
