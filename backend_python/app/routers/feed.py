# -*- coding: utf-8 -*-
"""
Feed routes (5 feed types).

Auth mode:
  - listLatest / listLikesCount / listByPopularity / listByTag -> soft auth
      Not logged in: see public content. Logged in: see personalized data (is_liked).
  - listByFollowing -> hard auth
      Following feed must know current user to find who they follow.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.middleware.jwt_auth import get_current_user, get_optional_user
from app.repositories.feed_repo import FeedRepository
from app.repositories.like_repo import LikeRepository
from app.schemas.feed import (
    ListLatestRequest, ListLatestResponse,
    ListLikesCountRequest, ListLikesCountResponse,
    ListByPopularityRequest, ListByPopularityResponse,
    ListByFollowingRequest, ListByFollowingResponse,
    ListByTagRequest,
)
from app.services.feed_service import FeedService

public_router = APIRouter(dependencies=[Depends(get_optional_user)])
protected_router = APIRouter(dependencies=[Depends(get_current_user)])


def _get_feed_service(db: AsyncSession = Depends(get_db)) -> FeedService:
    return FeedService(FeedRepository(db), LikeRepository(db))


def _viewer_id(user: dict | None) -> int:
    return user["account_id"] if user else 0


@public_router.post("/listLatest", response_model=ListLatestResponse)
async def list_latest(
    req: ListLatestRequest,
    user: dict | None = Depends(get_optional_user),
    service: FeedService = Depends(_get_feed_service),
):
    """
    Latest video feed.

    Cursor latest_time is the create_time (ms timestamp) of the previous page's last video.
    First page: pass 0. Returned next_time is used for the next page.
    """
    return await service.list_latest(req.limit, req.latest_time, _viewer_id(user))


@public_router.post("/listLikesCount", response_model=ListLikesCountResponse)
async def list_likes_count(
    req: ListLikesCountRequest,
    user: dict | None = Depends(get_optional_user),
    service: FeedService = Depends(_get_feed_service),
):
    """
    Most-liked ranking.

    Compound cursor (likes_count_before, id_before): both params must be passed together or both omitted.
    First page: omit both. Next page: pass next_likes_count_before and next_id_before from response.
    """
    return await service.list_likes_count(
        req.limit, req.likes_count_before, req.id_before, _viewer_id(user),
    )


@public_router.post("/listByPopularity", response_model=ListByPopularityResponse)
async def list_by_popularity(
    req: ListByPopularityRequest,
    user: dict | None = Depends(get_optional_user),
    service: FeedService = Depends(_get_feed_service),
):
    """
    Hot ranking.

    Uses Redis ZSET minute-level sliding window + snapshot pagination when available,
    falls back to triple compound cursor MySQL query.
    """
    return await service.list_by_popularity(
        req.limit, req.as_of, req.offset, _viewer_id(user),
        req.latest_popularity if req.latest_popularity else None,
        req.latest_before if req.latest_before else None,
        req.latest_id_before,
    )


@protected_router.post("/listByFollowing", response_model=ListByFollowingResponse)
async def list_by_following(
    req: ListByFollowingRequest,
    user: dict = Depends(get_current_user),
    service: FeedService = Depends(_get_feed_service),
):
    """
    Following feed.

    Shows videos from people the current user follows, ordered by time descending.
    Cursor latest_time is Unix second timestamp.
    """
    return await service.list_by_following(req.limit, req.latest_time, user["account_id"])


@public_router.post("/listByTag")
async def list_by_tag(
    req: ListByTagRequest,
    user: dict | None = Depends(get_optional_user),
    service: FeedService = Depends(_get_feed_service),
):
    """Browse videos by #tag."""
    items = await service.list_by_tag(req.tag_name, req.limit, _viewer_id(user))
    return {"video_list": items}
