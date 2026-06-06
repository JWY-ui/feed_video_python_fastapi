# -*- coding: utf-8 -*-
"""
Direct message table (messages)

Query for chat history between two users:
  SELECT * FROM messages
  WHERE (from_id = ? AND to_id = ?) OR (from_id = ? AND to_id = ?)
  ORDER BY created_at DESC
  LIMIT 50

Two single-column indexes (from_id, to_id) serve respectively:
  - Messages I sent to everyone (from_id index)
  - Messages everyone sent to me (to_id index)
  - Combined query: MySQL does index_merge on both indexes
"""
from datetime import datetime

from sqlalchemy import String, Integer, Text, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # Sender ID.
    from_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    # Recipient ID.
    to_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    # Message content. Text supports long content.
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # Whether read. Reserved field, not used in current version.
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    # Send time.
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
