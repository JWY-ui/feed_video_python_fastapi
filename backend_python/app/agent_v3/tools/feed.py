"""feed 域工具。全是只读，直接执行。

一律复用 FeedService / VideoService，不自己写 SQL —— 这样 `is_liked` 之类的
个性化标记、缓存、通知等既有逻辑白拿，也不会长出第二套查询。
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.agent_v3.tools.registry import (
    Tier,
    ToolContext,
    ToolResult,
    ToolSpec,
    register,
)
from app.database import AsyncSessionLocal
from app.repositories.feed_repo import FeedRepository
from app.repositories.like_repo import LikeRepository
from app.repositories.video_repo import VideoRepository
from app.services.feed_service import FeedService
from app.services.video_service import VideoService


class ListVideosArgs(BaseModel):
    limit: int = Field(default=10, gt=0, le=50, description="最多返回多少个视频")


class SearchVideosArgs(BaseModel):
    query: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="搜索关键词，会同时匹配视频标题、简介和标签",
    )
    limit: int = Field(default=10, gt=0, le=50, description="最多返回多少个视频")


class ListByTagArgs(BaseModel):
    tag: str = Field(..., min_length=1, max_length=100, description="标签名，不要带 #")
    limit: int = Field(default=10, gt=0, le=50, description="最多返回多少个视频")


class VideoDetailArgs(BaseModel):
    video_id: int = Field(..., description="视频 ID")


def project_video(item) -> dict:
    """精简投影：只留模型判断需要的字段，不含 play_url / cover_url 这类长字段。"""
    return {
        "id": item.id,
        "title": item.title,
        "author": item.author.username,
        "author_id": item.author.id,
        "likes": item.likes_count,
        "liked_by_me": item.is_liked,
    }


def _list_result(items) -> ToolResult:
    return ToolResult(
        summary=f"找到 {len(items)} 个视频",
        data=[project_video(v) for v in items],
    )


async def _feed_service(session) -> FeedService:
    return FeedService(FeedRepository(session), LikeRepository(session))


# ── 搜索 ────────────────────────────────────────────────────────

async def _search_videos(ctx: ToolContext, args: SearchVideosArgs) -> ToolResult:
    async with AsyncSessionLocal() as session:
        svc = await _feed_service(session)
        items = await svc.search(args.query, args.limit, ctx.account_id)
    return _list_result(items)


# ── 三种信息流 ──────────────────────────────────────────────────

async def _list_latest_videos(ctx: ToolContext, args: ListVideosArgs) -> ToolResult:
    async with AsyncSessionLocal() as session:
        svc = await _feed_service(session)
        # latest_time_ms=0：不要游标，从最新开始
        resp = await svc.list_latest(args.limit, 0, ctx.account_id)
    return _list_result(resp.video_list)


async def _list_hot_videos(ctx: ToolContext, args: ListVideosArgs) -> ToolResult:
    async with AsyncSessionLocal() as session:
        svc = await _feed_service(session)
        resp = await svc.list_likes_count(args.limit, None, None, ctx.account_id)
    return _list_result(resp.video_list)


async def _list_following_videos(ctx: ToolContext, args: ListVideosArgs) -> ToolResult:
    async with AsyncSessionLocal() as session:
        svc = await _feed_service(session)
        resp = await svc.list_by_following(args.limit, 0, ctx.account_id)
    return _list_result(resp.video_list)


async def _list_by_tag(ctx: ToolContext, args: ListByTagArgs) -> ToolResult:
    async with AsyncSessionLocal() as session:
        svc = await _feed_service(session)
        items = await svc.list_by_tag(args.tag, args.limit, ctx.account_id)
    return _list_result(items)


# ── 详情 ────────────────────────────────────────────────────────

async def _get_video_detail(ctx: ToolContext, args: VideoDetailArgs) -> ToolResult:
    async with AsyncSessionLocal() as session:
        svc = VideoService(VideoRepository(session), session)
        try:
            video = await svc.get_detail(args.video_id)
        except ValueError:
            # 模型猜错 id 是常事，回一句就好，不该让整轮对话塌掉
            return ToolResult(summary="视频不存在", data=None)

    return ToolResult(
        summary=f"视频《{video['title']}》",
        data={
            "id": video["id"],
            "title": video["title"],
            "description": video.get("description"),
            "author": video.get("username"),
            "likes": video.get("likes_count"),
        },
    )


# ── 注册 ────────────────────────────────────────────────────────

register(
    ToolSpec(
        name="search_videos",
        description=(
            "按关键词搜索视频。关键词会匹配标题、简介和标签三处。"
            "用户想找某类内容（例如「找几个做菜的视频」）时用这个。"
        ),
        args_model=SearchVideosArgs,
        tier=Tier.READ,
        handler=_search_videos,
    )
)

register(
    ToolSpec(
        name="list_latest_videos",
        description="看最新发布的视频。用户说「有什么新视频」时用。",
        args_model=ListVideosArgs,
        tier=Tier.READ,
        handler=_list_latest_videos,
    )
)

register(
    ToolSpec(
        name="list_hot_videos",
        description="看最受欢迎（点赞最多）的视频。用户想知道「最近什么火」时用。",
        args_model=ListVideosArgs,
        tier=Tier.READ,
        handler=_list_hot_videos,
    )
)

register(
    ToolSpec(
        name="list_following_videos",
        description="看用户关注的人发了什么。",
        args_model=ListVideosArgs,
        tier=Tier.READ,
        handler=_list_following_videos,
    )
)

register(
    ToolSpec(
        name="list_by_tag",
        description="按标签看视频。用户明确提到某个标签时用；只是想找某类内容优先用 search_videos。",
        args_model=ListByTagArgs,
        tier=Tier.READ,
        handler=_list_by_tag,
    )
)

register(
    ToolSpec(
        name="get_video_detail",
        description="看某个视频的详细信息和简介。用户问「这个视频讲了啥」时用。",
        args_model=VideoDetailArgs,
        tier=Tier.READ,
        handler=_get_video_detail,
    )
)
