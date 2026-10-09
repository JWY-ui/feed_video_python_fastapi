# -*- coding: utf-8 -*-
"""
Agent conversation table (agent_v3_conversations)

=== Why this table is so thin ===

The chat transcript is NOT stored here. Messages live in LangGraph's checkpoint
tables (checkpoints / checkpoint_blobs / checkpoint_writes), created by
AsyncMySaver.setup() and keyed by thread_id. Those tables are the single source
of truth for the conversation, which is what makes the graph resumable and lets
the agent see its own past tool calls.

But they cannot answer two questions this app has to answer:
  1. "which conversations belong to this account?"  -- they have no account_id
  2. "which order should the sidebar show them in, and what is each called?"

So this table carries exactly ownership + title + ordering, and nothing else.
Deliberately not duplicating messages here: two copies of a transcript drift,
and drift between two sources of truth is the class of bug this codebase has
already been bitten by.

Schema note: `thread_id` is UNIQUE and doubles as the graph's thread key, so a
lookup by thread_id is also the ownership check (`WHERE thread_id = ? AND
account_id = ?`).
"""
from datetime import datetime

from sqlalchemy import String, Integer, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.utils.timeutil import utc_now


class AgentV3Conversation(Base):
    __tablename__ = "agent_v3_conversations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # Graph thread key (uuid4().hex). Matches configurable.thread_id.
    thread_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    # Owner. Every read/write filters on this -- the model never influences it.
    account_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    # Sidebar label. Auto-filled from the first user message; may be empty.
    title: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=utc_now, onupdate=utc_now,
    )

    __table_args__ = (
        # Sidebar query: WHERE account_id = ? ORDER BY updated_at DESC
        Index("idx_agent_v3_conv_account_updated", "account_id", "updated_at"),
    )
