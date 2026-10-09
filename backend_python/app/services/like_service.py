# -*- coding: utf-8 -*-
"""
Like business logic -- like/unlike + sync update video stats.

"Write amplification for read performance" design:
  Each like/unlike not only INSERT/DELETE in likes table,
  but also sync UPDATE videos.likes_count and videos.popularity.
  Feed display reads field values directly, no COUNT(likes) needed.

Anti-duplicate mechanism (two layers):
  1. Service layer: create_ignore_duplicate() checks if already liked, rejects if so
  2. Database layer: likes table has UniqueConstraint(video_id, account_id)
     Even if two concurrent requests pass Service layer check, DB unique constraint blocks duplicate insert.

Popularity updates:
  Each like +1, unlike -1. GREATEST prevents negative.
  Popularity aggregates likes, comments, follows for hot ranking.
"""
from app.repositories.like_repo import LikeRepository
from app.repositories.video_repo import VideoRepository
from app.utils.timeutil import utc_now


class LikeService:

    def __init__(self, repo: LikeRepository, video_repo: VideoRepository):
        self.repo = repo
        self.video_repo = video_repo

    async def like(self, video_id: int, account_id: int,
                   sender_username: str | None = None) -> None:
        """
        Like a video.

        Flow:
          1. Validate video exists (and fetch the owner, needed for the notification)
          2. Try insert into likes (anti-duplicate -- reject if already liked)
          3. UPDATE videos: likes_count + 1, popularity + 1
          4. Notify the video's author

        `sender_username` is optional: callers that already have it (the HTTP
        route, from the JWT) pass it to avoid a lookup; others fall back to one.
        """
        video = await self.video_repo.get_by_id(video_id)
        if video is None:
            raise ValueError("video not found")

        created = await self.repo.create_ignore_duplicate(
            video_id=video_id, account_id=account_id, created_at=utc_now(),
        )
        if not created:
            raise ValueError("already liked")

        await self.video_repo.change_likes_count(video_id, 1)
        await self.video_repo.change_popularity(video_id, 1)
        # Only reached on a NEW like, so re-liking never re-notifies.
        await self._notify_like(video, account_id, sender_username)

    async def _notify_like(self, video: dict, account_id: int,
                           sender_username: str | None) -> None:
        """Tell the video's author. Self-likes are dropped inside notify()."""
        from app.repositories.account_repo import AccountRepository
        from app.repositories.notification_repo import NotificationRepository
        from app.services.notification_service import NotificationService

        username = sender_username
        if not username:
            account = await AccountRepository(self.repo.db).find_by_id(account_id)
            username = account["username"] if account else "有人"

        service = NotificationService(NotificationRepository(self.repo.db))
        await service.notify(
            recipient_id=video["author_id"], sender_id=account_id, type="like",
            target_id=video["id"], content=f"{username} 赞了你的视频",
        )

    async def unlike(self, video_id: int, account_id: int) -> None:
        """
        Unlike a video.

        Flow:
          1. Validate video exists
          2. DELETE from likes (reject if not liked)
          3. UPDATE videos: likes_count - 1, popularity - 1
             GREATEST(x-1, 0) prevents negative.
        """
        if not await self.video_repo.is_exist(video_id):
            raise ValueError("video not found")

        deleted = await self.repo.delete_by_video_and_account(video_id, account_id)
        if not deleted:
            raise ValueError("not liked yet")

        await self.video_repo.change_likes_count(video_id, -1)
        await self.video_repo.change_popularity(video_id, -1)

    async def is_liked(self, video_id: int, account_id: int) -> bool:
        """Check if current user already liked this video -- SELECT COUNT FROM likes WHERE ..."""
        return await self.repo.is_liked(video_id, account_id)

    async def list_liked_videos(self, account_id: int) -> list[dict]:
        """My liked videos list -- JOIN likes + videos, ordered by like time descending."""
        return await self.repo.list_liked_videos(account_id)
