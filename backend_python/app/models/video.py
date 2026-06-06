# -*- coding: utf-8 -*-
"""
Video table (videos) + outbox message table (outbox_msgs)

=== Video ===
Design notes:
  1. author_id + username stored redundantly.
     Why break 3NF? Feed shows 10-20 videos per page, each needs author name.
     JOINing accounts for each row = 20 extra queries. Redundancy = one query.
     "Read-heavy, space-for-time" tradeoff.

  2. likes_count is a field, not COUNT(*).
     Showing 20 videos = 20 COUNT(likes) queries. As a field, increment on like.
     Write amplification for read performance.

  3. popularity = weighted sum of likes + comments + follows.
     Used for hot ranking. Can add time decay later.

  4. Three descending composite indexes serving three feed types:
     idx_videos_create_time         -> Latest feed: WHERE create_time < ? ORDER BY create_time DESC
     idx_videos_likes_count_id      -> Most-liked: WHERE (likes_count < ?) OR (...) ORDER BY likes_count DESC, id DESC
     idx_videos_popularity_time_id  -> Hot ranking: WHERE (popularity < ?) OR (...) ORDER BY popularity DESC, create_time DESC, id DESC

     All descending because feeds always want "newest/highest", never ascending.
     Composite includes id as tiebreaker for cursor pagination.

=== OutboxMsg ===
  Transactional consistency: when publishing a video, INSERT videos and outbox_msgs
  in one transaction. Even if subsequent message queue delivery fails, outbox_msgs
  retains the record for retry. Simplified Outbox Pattern implementation.
"""
from datetime import datetime

from sqlalchemy import String, Integer, BigInteger, DateTime, func, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # Author ID. Indexed for listByAuthorID queries.
    author_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    # Redundant author name. Avoids JOINing accounts in feed display.
    username: Mapped[str] = mapped_column(String(255), nullable=False)
    # Video title. #tags are extracted from title+description on publish.
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    # Video description. Nullable.
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # Video playback URL (mp4 file URL).
    play_url: Mapped[str] = mapped_column(String(255), nullable=False)
    # Cover image URL (jpg/png/webp file URL).
    cover_url: Mapped[str] = mapped_column(String(255), nullable=False)
    # Creation time. Core sort field for feed cursor pagination.
    create_time: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    # Like count. +1 on like, -1 on unlike. GREATEST prevents negative.
    likes_count: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    # Popularity score. Likes +1, comments +1, follows +1 all increase popularity.
    popularity: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)

    # Three descending composite indexes, each serving one feed type.
    __table_args__ = (
        # Latest feed: WHERE create_time < cursor_time ORDER BY create_time DESC LIMIT N
        Index("idx_videos_create_time", "create_time"),
        # Most-liked: WHERE (likes_count < ?) OR (likes_count = ? AND id < ?) ORDER BY likes_count DESC, id DESC
        Index("idx_videos_likes_count_id", likes_count.desc(), id.desc()),
        # Hot ranking: WHERE (popularity < ?) OR (popularity = ? AND create_time < ?) OR (...) ORDER BY ...
        Index("idx_videos_popularity_time_id", popularity.desc(), create_time.desc(), id.desc()),
    )


class OutboxMsg(Base):
    """
    Local message table -- Outbox Pattern.

    Written in same transaction as videos to guarantee "video published" event
    is never lost. status: pending -> to-deliver -> delivered -> delete or mark sent.
    """
    __tablename__ = "outbox_msgs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # Associated video ID.
    video_id: Mapped[int] = mapped_column(Integer, index=True)
    # Event type: video_published.
    event_type: Mapped[str] = mapped_column(String(50))
    # Creation time (equals video publish time, used for timeline sorting).
    create_time: Mapped[datetime] = mapped_column(DateTime, default=func.now())
    # Status: pending (to-deliver) / sent (delivered) / failed (needs retry).
    status: Mapped[str] = mapped_column(String(50), index=True, default="pending")
