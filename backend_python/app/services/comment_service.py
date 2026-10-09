# -*- coding: utf-8 -*-
"""
Comment business logic.

Entire chain operates on dicts and primitives, never imports SQLAlchemy Models.
"""
import re

from app.repositories.comment_repo import CommentRepository
from app.repositories.video_repo import VideoRepository
from app.utils.timeutil import utc_now

_MENTION_RE = re.compile(r"@(\w+)")


class CommentService:

    def __init__(self, repo: CommentRepository, video_repo: VideoRepository):
        self.repo = repo
        self.video_repo = video_repo

    async def publish(self, video_id: int, author_id: int,
                      username: str, content: str) -> None:
        """Publish comment + notify the video's author + notify @mentions."""
        # get_by_id rather than is_exist: the owner is needed for the notification.
        video = await self.video_repo.get_by_id(video_id)
        if video is None:
            raise ValueError("video not found")

        comment_id = await self.repo.create(
            video_id=video_id, author_id=author_id,
            username=username, content=content.strip(),
            created_at=utc_now(),
        )

        await self.video_repo.change_popularity(video_id, 1)
        await self._notify_video_owner(video, video_id, author_id, username)
        await self._notify_mentions(comment_id, video_id, author_id, username, content,
                                    owner_id=video["author_id"])
        return {"message": "comment published successfully"}

    async def _notify_video_owner(self, video: dict, video_id: int,
                                  author_id: int, username: str) -> None:
        """Tell the video's author someone commented. Self-comments are dropped."""
        from app.repositories.notification_repo import NotificationRepository
        from app.services.notification_service import NotificationService

        service = NotificationService(NotificationRepository(self.repo.db))
        await service.notify(
            recipient_id=video["author_id"], sender_id=author_id, type="comment",
            target_id=video_id, content=f"{username} 评论了你的视频",
        )

    async def delete(self, comment_id: int, account_id: int) -> None:
        comment = await self.repo.get_by_id(comment_id)
        if comment is None:
            raise ValueError("comment not found")
        if comment["author_id"] != account_id:
            raise PermissionError("not the comment author")
        await self.repo.delete(comment_id)

    async def get_all(self, video_id: int) -> list[dict]:
        if not await self.video_repo.is_exist(video_id):
            raise ValueError("video not found")
        return await self.repo.get_all(video_id)

    async def _notify_mentions(self, comment_id: int, video_id: int,
                                author_id: int, username: str, content: str,
                                owner_id: int = 0):
        """
        @mention notifications.

        `owner_id` (the video's author) is skipped: they already received the
        'commented on your video' notification from _notify_video_owner, and
        getting a second row for the same comment is just noise. Their own
        mention still renders in the comment body.
        """
        matches = _MENTION_RE.findall(content)
        if not matches:
            return

        from app.repositories.account_repo import AccountRepository
        from app.repositories.notification_repo import NotificationRepository
        from app.services.notification_service import NotificationService

        account_repo = AccountRepository(self.repo.db)
        service = NotificationService(NotificationRepository(self.repo.db))

        seen: set[str] = set()
        for mentioned_user in matches:
            if mentioned_user in seen or mentioned_user == username:
                continue
            seen.add(mentioned_user)

            target = await account_repo.find_by_username(mentioned_user)
            if target and target["id"] != owner_id:
                await service.notify(
                    recipient_id=target["id"],
                    sender_id=author_id,
                    type="mention",
                    target_id=video_id,
                    content=f"{username} 在评论里提到了你",
                )
