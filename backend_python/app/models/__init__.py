# -*- coding: utf-8 -*-
"""Model exports -- all ORM Models are imported here for unified access.

Why a __init__.py?
  1. main.py just needs `from app.models import Account, Video, ...` one line
  2. Import triggers SQLAlchemy __init_subclass__, registering each Model
     in Base.metadata. Base.metadata.create_all() relies on this registry.

Adding a new table:
  1. Create a new file under models/ defining the Model
  2. Add `from app.models.xxx import Xxx` below
  3. Add "Xxx" to __all__
"""
from app.models.account import Account
from app.models.video import Video, OutboxMsg
from app.models.like import Like
from app.models.comment import Comment
from app.models.social import Social
from app.models.tag import Tag, VideoTag
from app.models.message import Message
from app.models.notification import Notification

__all__ = [
    "Account",
    "Video", "OutboxMsg",
    "Like",
    "Comment",
    "Social",
    "Tag", "VideoTag",
    "Message",
    "Notification",
]
