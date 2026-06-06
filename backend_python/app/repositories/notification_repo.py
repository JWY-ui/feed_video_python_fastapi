# -*- coding: utf-8 -*-
"""Notification data access layer."""
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification


def _to_dict(n: Notification) -> dict:
    return {
        "id": n.id, "recipient_id": n.recipient_id, "sender_id": n.sender_id,
        "type": n.type, "target_id": n.target_id, "content": n.content,
        "is_read": n.is_read,
        "created_at": n.created_at.isoformat() if n.created_at else "",
    }


class NotificationRepository:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create(self, **kwargs) -> int:
        n = Notification(**kwargs)
        self.db.add(n)
        await self.db.flush()
        return n.id

    async def list_by_user(self, user_id: int, limit: int = 50) -> list[dict]:
        stmt = (
            select(Notification)
            .where(Notification.recipient_id == user_id)
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return [_to_dict(r) for r in result.scalars().all()]

    async def mark_read(self, user_id: int, notif_id: int | None) -> None:
        if notif_id:
            stmt = (
                update(Notification)
                .where(Notification.id == notif_id, Notification.recipient_id == user_id)
                .values(is_read=True)
            )
        else:
            stmt = (
                update(Notification)
                .where(Notification.recipient_id == user_id)
                .values(is_read=True)
            )
        await self.db.execute(stmt)

    async def unread_count(self, user_id: int) -> int:
        stmt = (
            select(func.count())
            .select_from(Notification)
            .where(Notification.recipient_id == user_id, Notification.is_read == False)
        )
        result = await self.db.execute(stmt)
        return result.scalar() or 0
