# -*- coding: utf-8 -*-
"""
Notification table (notifications)

Notifications are triggered by interaction events:
  - like     : someone liked your video     -> type=like,    target_id=video_id
  - comment  : someone commented on your video -> type=comment, target_id=video_id
  - follow   : someone followed you         -> type=follow,  target_id=follower_id
  - mention  : someone @mentioned you in a comment -> type=mention, target_id=video_id

Query patterns:
  - Notification list: SELECT WHERE recipient_id = ? ORDER BY created_at DESC LIMIT 50
    recipient_id has index, uses index scan (no full table scan)
  - Unread count: SELECT COUNT WHERE recipient_id = ? AND is_read = false
  - Mark read: UPDATE WHERE recipient_id = ? AND id = ? (single) / WHERE recipient_id = ? (all)

Push mechanism:
  Notifications are written to MySQL, then pushed to online users via SSE.
  Offline users don't miss anything -- load from MySQL when they open the list.
"""
from datetime import datetime

from sqlalchemy import String, Integer, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    # Recipient -- who receives this notification. Indexed, core filter for list queries.
    recipient_id: Mapped[int] = mapped_column(Integer, index=True, nullable=False)
    # Sender -- who triggered the notification (the person who liked/commented/followed).
    sender_id: Mapped[int] = mapped_column(Integer, nullable=False)
    # Notification type: like / comment / follow / mention.
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    # Target ID. e.g. video_id (like/comment/mention) or user_id (follow).
    # Frontend uses this to navigate to the relevant page on click.
    target_id: Mapped[int] = mapped_column(Integer, default=0)
    # Notification text. e.g. "tom liked your video".
    content: Mapped[str] = mapped_column(String(255), default="")
    # Whether read. Mark-read endpoint batch-updates this field.
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    # Notification creation time.
    created_at: Mapped[datetime] = mapped_column(DateTime, default=func.now())
