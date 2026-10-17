# -*- coding: utf-8 -*-
"""Like module -- Pydantic request/response models."""
from datetime import datetime

from pydantic import BaseModel, Field


class LikeRequest(BaseModel):
    video_id: int = Field(..., gt=0)


class IsLikedResponse(BaseModel):
    is_liked: bool


class ListMyLikedRequest(BaseModel):
    """Cursor for "my liked videos".

    `before_time` / `before_id` are the previous page's last item's `liked_at`
    and `like_id` (both are returned on every item). Omit both for the first
    page. Keeping the response a bare list means existing clients are unaffected.
    """

    before_time: datetime | None = None
    before_id: int | None = None
    limit: int = Field(default=200, gt=0, le=200)
