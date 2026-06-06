# -*- coding: utf-8 -*-
"""
Like table (likes)

Unique constraint (video_id, account_id): one user can like each video only once.
This is the last line of defense at the DB level -- Service layer also checks
for duplicates, but under concurrency two requests can both see "not liked"
and both try to INSERT. The DB unique constraint guarantees no duplicate rows.

Used by queries:
  - Like: INSERT + unique constraint conflict detection
  - Unlike: DELETE WHERE video_id = ? AND account_id = ?
  - Is liked: SELECT COUNT WHERE video_id = ? AND account_id = ?
  - Batch check liked status: SELECT video_id WHERE video_id IN (...) AND account_id = ?
  - My liked videos: JOIN likes + videos WHERE account_id = ?
"""
from datetime import datetime

from sqlalchemy import Integer, DateTime, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Like(Base):
    __tablename__ = "likes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # ID of the liked video.
    video_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # ID of the user who liked.
    account_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # Like time. List queries ordered descending by this field.
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())

    # Compound unique: same user cannot like the same video twice.
    __table_args__ = (UniqueConstraint("video_id", "account_id"),)
