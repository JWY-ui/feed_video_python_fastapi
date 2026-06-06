"""
点赞业务逻辑——点赞/取消点赞 + 同步更新视频统计字段。

"写放大换读性能"的设计：
  每次点赞/取消点赞不只是 INSERT/DELETE likes 表，
  还同步 UPDATE videos.likes_count 和 videos.popularity。
  这样 Feed 流展示视频时直接读字段值，不需要 COUNT(likes) 再算一次。

防重机制（两层）：
  1. Service 层：create_ignore_duplicate() 先查是否已赞，是则拒绝
  2. 数据库层：likes 表有 UniqueConstraint(video_id, account_id)
     即使两个并发请求同时通过了 Service 层检查，数据库唯一约束也会阻止重复插入

热度值 (popularity) 的更新：
  每次点赞 +1，取消点赞 -1。GREATEST 防止减成负数。
  热度值综合了点赞、评论、关注等互动，用于热度榜排序。
"""
from datetime import datetime

from app.repositories.like_repo import LikeRepository
from app.repositories.video_repo import VideoRepository


class LikeService:

    def __init__(self, repo: LikeRepository, video_repo: VideoRepository):
        self.repo = repo
        self.video_repo = video_repo

    async def like(self, video_id: int, account_id: int) -> None:
        """
        点赞。

        流程：
          1. 校验视频存在
          2. 尝试插入 likes 表（防重——已点赞则拒绝）
          3. UPDATE videos: likes_count + 1, popularity + 1
        """
        if not await self.video_repo.is_exist(video_id):
            raise ValueError("video not found")

        created = await self.repo.create_ignore_duplicate(
            video_id=video_id, account_id=account_id, created_at=datetime.utcnow(),
        )
        if not created:
            raise ValueError("already liked")

        await self.video_repo.change_likes_count(video_id, 1)
        await self.video_repo.change_popularity(video_id, 1)

    async def unlike(self, video_id: int, account_id: int) -> None:
        """
        取消点赞。

        流程：
          1. 校验视频存在
          2. DELETE likes 表（没赞过则拒绝）
          3. UPDATE videos: likes_count - 1, popularity - 1
             GREATEST(x-1, 0) 防止减成负数
        """
        if not await self.video_repo.is_exist(video_id):
            raise ValueError("video not found")

        deleted = await self.repo.delete_by_video_and_account(video_id, account_id)
        if not deleted:
            raise ValueError("not liked yet")

        await self.video_repo.change_likes_count(video_id, -1)
        await self.video_repo.change_popularity(video_id, -1)

    async def is_liked(self, video_id: int, account_id: int) -> bool:
        """当前用户是否已赞该视频——SELECT COUNT FROM likes WHERE ..."""
        return await self.repo.is_liked(video_id, account_id)

    async def list_liked_videos(self, account_id: int) -> list[dict]:
        """我赞过的视频列表——JOIN likes + videos，按点赞时间倒序"""
        return await self.repo.list_liked_videos(account_id)
