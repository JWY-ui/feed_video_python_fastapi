# -*- coding: utf-8 -*-
"""
Comment table (comments)

Design notes:
  1. username stored redundantly -- like Video table, avoids JOIN for author name display.
  2. author_id stored separately -- used for delete permission check: "only comment author can delete".
  3. Three indexes:
     idx_username  -> rarely used (@mention notification lookup by name)
     idx_video_id  -> video detail page comment list (max 200, ascending by time)
     idx_author_id -> almost unused (no "my comments" feature yet, reserved)

Used by queries:
  - Publish comment: INSERT
  - Delete comment: DELETE WHERE id = ? (PK delete)
  - Comment list: SELECT WHERE video_id = ? ORDER BY created_at ASC LIMIT 200
  - @mention notification: SELECT id FROM accounts WHERE username = ? (cross-table)
"""
from datetime import datetime

from sqlalchemy import String, Integer, Text, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Comment(Base):
    __tablename__ = "comments"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # Redundant author name -- display without JOINing accounts.
    username: Mapped[str] = mapped_column(String(255), index=True)
    # Target video ID -- high-frequency filter for comment list queries.
    video_id: Mapped[int] = mapped_column(Integer, index=True)
    # Author ID -- permission check field for comment deletion.
    author_id: Mapped[int] = mapped_column(Integer, index=True)
    # Comment content. Text type supports long content (MySQL max 65KB).
    content: Mapped[str] = mapped_column(Text)
    # Comment time. List ordered ascending (oldest comments first).
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
