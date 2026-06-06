# -*- coding: utf-8 -*-
"""
Tag table (tags) + Video-Tag association table (video_tags)

Many-to-many relationship between videos and tags:
  One video can have multiple #tags
  One #tag can belong to multiple videos

Connected via video_tags junction table.

Data flow:
  Publish video -> regex extract #tags -> INSERT tags (FirstOrCreate) -> INSERT video_tags
  Tag feed query -> JOIN videos + video_tags + tags WHERE tags.name = ?

Why not comma-separated field (e.g. tag_list = "food,travel")?
  1. No index possible -- WHERE tag_list LIKE '%food%' can't use index, full table scan
  2. Hard to update/delete -- removing one tag requires string manipulation
  3. Tag table is extensible -- can add tag icon, description etc. later
"""
from sqlalchemy import String, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # Tag name (without #). Unique index ensures no duplicate tag creation.
    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)


class VideoTag(Base):
    __tablename__ = "video_tags"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # Video ID. Indexed for JOIN in tag feed queries.
    video_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    # Tag ID. Indexed same as above.
    tag_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
