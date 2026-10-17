# -*- coding: utf-8 -*-
"""
Notification business logic -- the single place a notification is created.

Before this existed, only @mentions wrote rows (comment_service._notify_mentions)
and nothing ever pushed them, so the notification list was permanently empty and
push_sse() was dead code. Every producer now goes through notify().

Operates on dicts/primitives only, never imports SQLAlchemy Models -- same rule
as the other services.
"""
from app.repositories.notification_repo import NotificationRepository
from app.services import notification_bus
from app.utils.timeutil import utc_now

VALID_TYPES = {"like", "comment", "follow", "mention"}


class NotificationService:

    def __init__(self, repo: NotificationRepository):
        self.repo = repo

    # ==================== Reads ====================

    async def list_by_user(self, user_id: int, limit: int = 50) -> list[dict]:
        return await self.repo.list_by_user(user_id, limit)

    async def unread_count(self, user_id: int) -> int:
        return await self.repo.unread_count(user_id)

    async def mark_read(self, user_id: int, notif_id: int | None) -> None:
        await self.repo.mark_read(user_id, notif_id)

    # ==================== The one write primitive ====================

    async def notify(self, *, recipient_id: int, sender_id: int, type: str,
                     target_id: int = 0, content: str = "") -> int | None:
        """
        Record a notification and best-effort push it to any open SSE stream.

        Returns the new row id, or None when nothing was written (self-action).

        Runs on the caller's session, so the row commits atomically with the
        like/comment/follow that triggered it: either both land or neither does.
        The push happens after the flush but before that commit -- a tiny window
        where a client could be told about a row that then rolls back. The next
        list refresh reconciles it, and the alternative (pushing after commit)
        would mean the producer can no longer be a plain service call.
        """
        if recipient_id <= 0 or recipient_id == sender_id:
            return None
        if type not in VALID_TYPES:
            raise ValueError(f"unknown notification type: {type}")

        # Pass created_at explicitly: the model default is a safety net, but the
        # value pushed to the client must match what is stored.
        now = utc_now()
        notif_id = await self.repo.create(
            recipient_id=recipient_id, sender_id=sender_id, type=type,
            target_id=target_id, content=content, created_at=now,
        )

        await notification_bus.publish(recipient_id, {
            # 'event' is the frame discriminator; the notification's own 'type'
            # (like/comment/...) would collide with it if used here.
            "event": "notification",
            "notification": {
                "id": notif_id, "recipient_id": recipient_id,
                "sender_id": sender_id, "type": type,
                "target_id": target_id, "content": content,
                "is_read": False, "created_at": now.isoformat(),
            },
        })
        return notif_id
