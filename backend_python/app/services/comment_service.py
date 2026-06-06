# -*- coding: utf-8 -*-
"""
Comment business logic.

Entire chain operates on dicts and primitives, never imports SQLAlchemy Models.
"""
import re
from datetime import datetime

from app.repositories.comment_repo import CommentRepository
from app.repositories.video_repo import VideoRepository

_MENTION_RE = re.compile(r"@(\w+)")


class CommentService:

    def __init__(self, repo: CommentRepository, video_repo: VideoRepository):
        self.repo = repo
        self.video_repo = video_repo

    async def publish(self, video_id: int, author_id: int,
                      username: str, content: str) -> None:
        """Publish comment + @mention notifications."""
        if not await self.video_repo.is_exist(video_id):
            raise ValueError("video not found")

        comment_id = await self.repo.create(
            video_id=video_id, author_id=author_id,
            username=username, content=content.strip(),
            created_at=datetime.utcnow(),
        )

        await self.video_repo.change_popularity(video_id, 1)
        await self._notify_mentions(comment_id, video_id, author_id, username, content)
        return {"message": "comment published successfully"}

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
                                author_id: int, username: str, content: str):
        """@mention notifications -- write to notifications table."""
        matches = _MENTION_RE.findall(content)
        if not matches:
            return

        from app.repositories.account_repo import AccountRepository
        from app.repositories.notification_repo import NotificationRepository

        account_repo = AccountRepository(self.repo.db)
        notif_repo = NotificationRepository(self.repo.db)

        seen: set[str] = set()
        for mentioned_user in matches:
            if mentioned_user in seen or mentioned_user == username:
                continue
            seen.add(mentioned_user)

            target = await account_repo.find_by_username(mentioned_user)
            if target:
                await notif_repo.create(
                    recipient_id=target["id"],
                    sender_id=author_id,
                    type="mention",
                    target_id=video_id,
                    content=f"{username} mentioned you in a comment",
                )
