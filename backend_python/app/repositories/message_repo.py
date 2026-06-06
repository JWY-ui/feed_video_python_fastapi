# -*- coding: utf-8 -*-
"""Message data access layer."""
from datetime import datetime

from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message import Message


def _to_dict(m: Message) -> dict:
    return {
        "id": m.id, "from_id": m.from_id, "to_id": m.to_id,
        "content": m.content, "is_read": m.is_read,
        "created_at": m.created_at.isoformat() if m.created_at else "",
    }


class MessageRepository:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def send(self, from_id: int, to_id: int, content: str) -> dict:
        m = Message(
            from_id=from_id, to_id=to_id, content=content.strip(),
            created_at=datetime.utcnow(),
        )
        self.db.add(m)
        await self.db.flush()
        return _to_dict(m)

    async def list(self, user_id: int, peer_id: int, limit: int = 50) -> list[dict]:
        stmt = (
            select(Message)
            .where(
                or_(
                    (Message.from_id == user_id) & (Message.to_id == peer_id),
                    (Message.from_id == peer_id) & (Message.to_id == user_id),
                )
            )
            .order_by(Message.created_at.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        return [_to_dict(r) for r in result.scalars().all()]
