import uuid
from datetime import datetime, timezone

from sqlalchemy import select, update, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_v2 import AgentV2Conversation, AgentV2Message


def _conv_to_dict(c: AgentV2Conversation) -> dict:
    return {
        "id": c.id,
        "thread_id": c.thread_id,
        "account_id": c.account_id,
        "title": c.title,
        "created_at": c.created_at,
        "updated_at": c.updated_at,
    }


def _msg_to_dict(m: AgentV2Message) -> dict:
    return {
        "id": m.id,
        "thread_id": m.thread_id,
        "account_id": m.account_id,
        "role": m.role,
        "content": m.content,
        "model": m.model,
        "prompt_tokens": m.prompt_tokens,
        "completion_tokens": m.completion_tokens,
        "total_tokens": m.total_tokens,
        "duration_ms": m.duration_ms,
        "created_at": m.created_at,
    }


class AgentV2Repository:

    def __init__(self, db: AsyncSession):
        self.db = db

    # ── Conversation ────────────────────────────────────────────

    async def create_conversation(self, account_id: int) -> dict:
        thread_id = uuid.uuid4().hex
        conv = AgentV2Conversation(
            thread_id=thread_id,
            account_id=account_id,
        )
        self.db.add(conv)
        await self.db.flush()
        return _conv_to_dict(conv)

    async def get_conversation(self, thread_id: str) -> dict | None:
        stmt = select(AgentV2Conversation).where(
            AgentV2Conversation.thread_id == thread_id
        )
        result = await self.db.execute(stmt)
        row = result.scalar_one_or_none()
        return _conv_to_dict(row) if row else None

    async def list_conversations(self, account_id: int, limit: int = 20,
                                 before_id: int | None = None) -> list[dict]:
        stmt = (
            select(AgentV2Conversation)
            .where(AgentV2Conversation.account_id == account_id)
            .order_by(AgentV2Conversation.updated_at.desc())
        )
        if before_id is not None:
            stmt = stmt.where(AgentV2Conversation.id < before_id)
        stmt = stmt.limit(limit)
        result = await self.db.execute(stmt)
        return [_conv_to_dict(r) for r in result.scalars().all()]

    async def update_title(self, thread_id: str, title: str) -> None:
        stmt = (
            update(AgentV2Conversation)
            .where(AgentV2Conversation.thread_id == thread_id)
            .values(title=title, updated_at=datetime.now(timezone.utc))
        )
        await self.db.execute(stmt)

    async def delete_conversation(self, thread_id: str) -> None:
        await self.db.execute(
            sa_delete(AgentV2Message).where(AgentV2Message.thread_id == thread_id)
        )
        await self.db.execute(
            sa_delete(AgentV2Conversation).where(AgentV2Conversation.thread_id == thread_id)
        )

    # ── Message ─────────────────────────────────────────────────

    async def add_message(self, thread_id: str, account_id: int,
                          role: str, content: str,
                          model: str | None = None,
                          prompt_tokens: int | None = None,
                          completion_tokens: int | None = None,
                          total_tokens: int | None = None,
                          duration_ms: int | None = None) -> int:
        msg = AgentV2Message(
            thread_id=thread_id,
            account_id=account_id,
            role=role,
            content=content,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            duration_ms=duration_ms,
        )
        self.db.add(msg)
        await self.db.flush()
        return msg.id

    async def get_messages(self, thread_id: str, limit: int = 20,
                           before_id: int | None = None) -> list[dict]:
        stmt = (
            select(AgentV2Message)
            .where(AgentV2Message.thread_id == thread_id)
            .order_by(AgentV2Message.id.asc())
        )
        if before_id is not None:
            stmt = stmt.where(AgentV2Message.id < before_id)
        stmt = stmt.limit(limit)
        result = await self.db.execute(stmt)
        return [_msg_to_dict(r) for r in result.scalars().all()]
