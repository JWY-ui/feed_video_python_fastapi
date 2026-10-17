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

from sqlalchemy import DateTime, Index, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.utils.timeutil import utc_now


class Like(Base):
    __tablename__ = "likes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # ID of the liked video.
    video_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # ID of the user who liked.
    account_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # Like time. List queries ordered descending by this field.
    # utc_now, not func.now(): see app/utils/timeutil.py for the time convention.
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    __table_args__ = (
        # Compound unique: same user cannot like the same video twice.
        # Its column order (video_id first) serves the "did this user like this
        # video" / batch checks, but NOT "my liked videos".
        UniqueConstraint("video_id", "account_id"),
        # "My liked videos": WHERE account_id = ? ORDER BY created_at DESC, id DESC.
        # The unique index above cannot serve it (wrong leading column) -- the
        # dev DB EXPLAIN showed a full scan + filesort. InnoDB secondary indexes
        # implicitly end with the primary key, so (account_id, created_at) also
        # gives the (created_at, id) tiebreaker order without naming id.
        Index("idx_likes_account_created", "account_id", created_at.desc()),
    )
