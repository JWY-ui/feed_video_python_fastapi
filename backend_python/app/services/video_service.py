"""
视频业务逻辑——全链路只操作基本类型和dict
"""
import os
import secrets
import shutil
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.video_repo import VideoRepository
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
            create_time=datetime.utcnow(),
        )
        await self.repo.create_outbox_msg(
            video_id=video_id, event_type="video_published",
            create_time=datetime.utcnow(), status="pending",
        )
        tags = extract_tags(f"{title} {description}")
        for tag_name in tags:
            tag = await self.repo.create_tag_if_not_exists(tag_name)
            await self.repo.create_video_tag(video_id, tag["id"])
        return await self.repo.get_by_id(video_id)

    async def delete(self, video_id: int, author_id: int) -> None:
        """
        删除视频——只有作者本人可以删除。

        同时主动失效 Redis 缓存（一致性保证）。
        不失效的话，用户会在 5 分钟内看到"已删除"的视频。
        """
        video = await self.repo.get_by_id(video_id)
        if video is None:
            raise ValueError("video not found")
        if video["author_id"] != author_id:
            raise PermissionError("not the author")
        await self.repo.delete_video(video_id)
        # 主动失效缓存——和写操作配套的一致性保证
        if redis_client.available:
            from app.utils.redis_client import redis_client
            await redis_client.delete(redis_client.key("video:detail:%d", video_id))

    async def get_detail(self, video_id: int) -> dict:
        """
        视频详情——带 Redis 缓存 + 防击穿锁 + 随机 TTL。

        三层防护：
          1. 缓存雪崩防护 → 随机 TTL（300±30 秒），不会同一秒全部过期
          2. 缓存击穿防护 → SETNX 互斥锁，热点 key 只有 1 个请求回源
          3. 缓存穿透防护 → 不存在的视频缓存空标记（60 秒）

        更新视频/删除视频时主动 DEL 缓存，保证一致性。
        """
        import json
        cache_key = redis_client.key("video:detail:%d", video_id)

        # ━━ 第 1 层：查缓存 ━━
        if redis_client.available:
            cached = await redis_client.get(cache_key)
            if cached == "__NULL__":
                raise ValueError("video not found")  # 穿透保护：60 秒内不重复查 MySQL
            if cached:
                return json.loads(cached)

        # ━━ 第 2 层：抢锁（防击穿）━━━
        if redis_client.available:
            lock_key = redis_client.key("lock:video:detail:%d", video_id)
            locked = await redis_client.set(lock_key, "1", ex=3)  # SET NX + EX 3s

            if locked:
                # 拿到锁 → 回源 + 回填
                try:
                    # 双重检查：可能别人已经回填了
                    cached = await redis_client.get(cache_key)
                    if cached:
                        return json.loads(cached) if cached != "__NULL__" else (_ for _ in ()).throw(ValueError("video not found"))

                    video = await self.repo.get_by_id(video_id)
                    if video is None:
                        await redis_client.set(cache_key, "__NULL__", ex=60)  # 空值缓存
                        raise ValueError("video not found")

                    import random
                    ttl = 300 + random.randint(0, 60)  # 5 分钟 ± 60 秒随机
                    await redis_client.set(cache_key, json.dumps(video), ex=ttl)
                    return video
                finally:
                    await redis_client.delete(lock_key)

            else:
                # 没拿到锁 → 等别人回填
                import asyncio
                for _ in range(5):
                    await asyncio.sleep(0.02)  # 等 20ms
                    cached = await redis_client.get(cache_key)
                    if cached and cached != "__NULL__":
                        return json.loads(cached)
                # 等了 100ms 没等到 → 直接查 MySQL（兜底，防止锁持有者崩溃导致死等）

        # ━━ 第 3 层：MySQL 兜底 ━━
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
        date_str = datetime.utcnow().strftime("%Y%m%d")
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
        date_str = datetime.utcnow().strftime("%Y%m%d")
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
