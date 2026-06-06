# -*- coding: utf-8 -*-
"""
Feed request/response Pydantic models.

Defines request params and response format for 5 feed types.

Cursor pagination: each Request has cursor fields, each Response has next_xxx fields.
Frontend passes previous page's next_xxx into the next page's xxx field for infinite scroll.
"""
from pydantic import BaseModel, Field


class FeedAuthor(BaseModel):
    """Video author -- author info included with every feed item."""
    id: int
    username: str


class FeedVideoItem(BaseModel):
    """
    Single video entry in a feed list.

    Difference from VideoInfo (schemas/video.py):
      - FeedVideoItem is "summary in list", includes is_liked (personalized)
      - VideoInfo is "detail", does not include is_liked (detail page queries separately)
    """
    id: int
    author: FeedAuthor
    title: str
    description: str | None = None
    play_url: str
    cover_url: str
    create_time: int          # Unix second timestamp
    likes_count: int
    is_liked: bool = False    # Whether current user liked this (always false for anonymous)


# ==================== 1. Latest feed ====================

class ListLatestRequest(BaseModel):
    """Latest feed request -- cursor is create_time millisecond timestamp."""
    limit: int = Field(default=10, gt=0, le=50)
    latest_time: int = 0     # 0=first page; non-zero=prev page last item's create_time (ms)


class ListLatestResponse(BaseModel):
    """Latest feed response."""
    video_list: list[FeedVideoItem]
    next_time: int = 0       # This page's last item create_time (ms), passed to next page's latest_time
    has_more: bool = False   # False=no more data


# ==================== 2. Most-liked feed ====================

class ListLikesCountRequest(BaseModel):
    """Most-liked feed request -- compound cursor (likes_count, id)."""
    limit: int = Field(default=10, gt=0, le=50)
    likes_count_before: int | None = None   # Prev page last item's like count
    id_before: int | None = None            # Prev page last item's video ID
    # Both params must be passed together or both omitted


class ListLikesCountResponse(BaseModel):
    """Most-liked feed response."""
    video_list: list[FeedVideoItem]
    next_likes_count_before: int | None = None   # This page last item's like count
    next_id_before: int | None = None            # This page last item's video ID
    has_more: bool = False


# ==================== 3. Hot ranking ====================

class ListByPopularityRequest(BaseModel):
    """Hot ranking request -- triple compound cursor."""
    limit: int = Field(default=10, gt=0, le=50)
    as_of: int = 0                          # Snapshot time (for Redis). 0=server auto-selects current minute
    offset: int = 0                         # Pagination offset within snapshot
    latest_id_before: int | None = None     # Prev page last item's video ID
    latest_popularity: int = 0              # Prev page last item's popularity
    latest_before: str = ""                 # Prev page last item's create time (ISO format)


class ListByPopularityResponse(BaseModel):
    """Hot ranking response."""
    video_list: list[FeedVideoItem]
    as_of: int = 0                                    # Snapshot time used for this page
    next_offset: int = 0                              # Next page offset
    has_more: bool = False
    next_latest_popularity: int | None = None         # Cursor for MySQL degradation path
    next_latest_before: str | None = None
    next_latest_id_before: int | None = None


# ==================== 4. Following feed ====================

class ListByFollowingRequest(BaseModel):
    """Following feed request -- cursor is create_time Unix second timestamp."""
    limit: int = Field(default=10, gt=0, le=50)
    latest_time: int = 0     # 0=first page; non-zero=prev page last item's create_time (seconds)


class ListByFollowingResponse(BaseModel):
    """Following feed response."""
    video_list: list[FeedVideoItem]
    next_time: int = 0       # This page last item's create_time (seconds)
    has_more: bool = False


# ==================== 5. Tag feed ====================

class ListByTagRequest(BaseModel):
    """Tag feed request -- no pagination, single load."""
    tag_name: str = Field(..., min_length=1)
    limit: int = Field(default=10, gt=0, le=50)
