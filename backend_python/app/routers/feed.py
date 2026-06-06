"""
Feed 流路由（5 种流）

鉴权模式：
  - listLatest / listLikesCount / listByPopularity / listByTag → 软鉴权
      没登录可看公共内容，登录后可看个性化数据（是否已赞）
  - listByFollowing → 强制鉴权
      关注流必须知道当前用户是谁，才能查他关注的人的視頻
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
    最新视频流

    游标 latest_time 是上一页最后一条视频的 create_time（毫秒时间戳），
    首页传 0。返回的 next_time 用于请求下一页。
    """
    return await service.list_latest(req.limit, req.latest_time, _viewer_id(user))


@public_router.post("/listLikesCount", response_model=ListLikesCountResponse)
async def list_likes_count(
    req: ListLikesCountRequest,
    user: dict | None = Depends(get_optional_user),
    service: FeedService = Depends(_get_feed_service),
):
    """
    点赞排行

    复合游标 (likes_count_before, id_before)：两个参数必须同时传或同时不传。
    首页不传，后续传上一页返回的 next_likes_count_before 和 next_id_before。
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
    热度榜

    当前版本使用三元复合游标直接查 MySQL。
    后续优化方向：Redis ZSET 分钟级滑动窗口 + 快照分页。
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
    关注流

    只显示当前用户关注的人发布的视频，按时间倒序。
    游标 latest_time 是 Unix 秒时间戳。
    """
    return await service.list_by_following(req.limit, req.latest_time, user["account_id"])


@public_router.post("/listByTag")
async def list_by_tag(
    req: ListByTagRequest,
    user: dict | None = Depends(get_optional_user),
    service: FeedService = Depends(_get_feed_service),
):
    """按 #话题 浏览视频"""
    items = await service.list_by_tag(req.tag_name, req.limit, _viewer_id(user))
    return {"video_list": items}
