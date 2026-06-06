# -*- coding: utf-8 -*-
"""
Follow relationship table (socials)

Unique constraint (follower_id, vlogger_id): cannot follow the same person twice.

Field naming:
  follower -> the person who follows (active side)
  vlogger  -> the content creator being followed (passive side)

Used by queries:
  - Follow: INSERT + unique constraint conflict detection
  - Unfollow: DELETE WHERE follower_id = ? AND vlogger_id = ?
  - Follower list: SELECT follower_id WHERE vlogger_id = ? -> JOIN accounts
  - Following list: SELECT vlogger_id WHERE follower_id = ? -> JOIN accounts
  - Is following: SELECT COUNT WHERE follower_id = ? AND vlogger_id = ?
  - Following feed: subquery SELECT vlogger_id WHERE follower_id = ?
    used in listByFollowing's IN subquery
  - Follower/following count: COUNT WHERE vlogger_id/follower_id = ?
"""
from sqlalchemy import Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Social(Base):
    __tablename__ = "socials"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # Follower -- the person who clicked follow. Used for: "who I follow", following feed subquery.
    follower_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    # Vlogger -- the person being followed. Used for: "who follows me" (follower list).
    vlogger_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)

    # Compound unique: same follow relationship cannot be stored twice.
    __table_args__ = (UniqueConstraint("follower_id", "vlogger_id"),)
