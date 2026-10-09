"""会话表（agent_v3_conversations）的 CRUD。

只返回 dict，不外泄 ORM 对象 —— 与项目其它 repo 一致的约定。

消息**不在**这里：它们由 LangGraph checkpointer 持有（见 app/models/agent_v3.py
的说明）。这张表只负责归属、标题和排序。
"""
from __future__ import annotations

import uuid

from sqlalchemy import delete as sa_delete
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_v3 import AgentV3Conversation
from app.utils.timeutil import utc_now

DEFAULT_LIMIT = 20


def _to_dict(c: AgentV3Conversation) -> dict:
    return {
        "id": c.id,
        "thread_id": c.thread_id,
        "account_id": c.account_id,
        "title": c.title,
        "created_at": c.created_at,
        "updated_at": c.updated_at,
    }


class AgentV3Repository:

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_conversation(self, account_id: int) -> dict:
        conv = AgentV3Conversation(
            thread_id=uuid.uuid4().hex,
            account_id=account_id,
        )
        self.db.add(conv)
        await self.db.flush()
        return _to_dict(conv)

    async def get_conversation(self, thread_id: str) -> dict | None:
        stmt = select(AgentV3Conversation).where(
            AgentV3Conversation.thread_id == thread_id
        )
        row = (await self.db.execute(stmt)).scalar_one_or_none()
        return _to_dict(row) if row else None

    async def list_conversations(
        self, account_id: int, limit: int = DEFAULT_LIMIT
    ) -> list[dict]:
        stmt = (
            select(AgentV3Conversation)
            .where(AgentV3Conversation.account_id == account_id)
            # id 兜底：同一事务里建的多条会话 updated_at 可能同微秒
            .order_by(
                AgentV3Conversation.updated_at.desc(),
                AgentV3Conversation.id.desc(),
            )
            .limit(limit)
        )
        return [_to_dict(r) for r in (await self.db.execute(stmt)).scalars().all()]

    async def update_title(self, thread_id: str, title: str) -> None:
        stmt = (
            update(AgentV3Conversation)
            .where(AgentV3Conversation.thread_id == thread_id)
            .values(title=title, updated_at=utc_now())
        )
        await self.db.execute(stmt)

    async def delete_conversation(self, thread_id: str) -> None:
        stmt = sa_delete(AgentV3Conversation).where(
            AgentV3Conversation.thread_id == thread_id
        )
        await self.db.execute(stmt)
